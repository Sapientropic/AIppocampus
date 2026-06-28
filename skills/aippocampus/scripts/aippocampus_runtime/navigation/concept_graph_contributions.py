"""Contribution-owned incremental materialization for the concept graph.

The public concept graph tables are a read model. Incremental updates are only
safe when every node and edge knows which ingress family and logical slice
contributed it. This module owns that contribution ledger and the projection
back into the read model so changed slices can be replaced without resetting
unrelated graph rows.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, NamedTuple, Protocol

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.navigation import concept_graph_edge_policy as edge_policy
from aippocampus_runtime.navigation.associations import load_associations, normalize_term
from aippocampus_runtime.navigation.concept_graph_subconscious_ingress import (
    collect_subconscious_edges,
)
from aippocampus_runtime.navigation.concept_graph_term_quality import (
    ConceptTermQualityTracker,
    TermQualityContext,
)
from aippocampus_runtime.navigation.concept_graph_timeline_ingress import (
    collect_timeline_edges,
)
from aippocampus_runtime.navigation.concept_kinds import classify_concept_kind
from aippocampus_runtime.navigation.concept_lifecycle import normalize_graph_status
from aippocampus_runtime.navigation.trace_graph_ingress import (
    SEMANTIC_CUE_KIND as SEMANTIC_CUE_KIND,
)
from aippocampus_runtime.navigation.trace_graph_ingress import (
    TRACE_DERIVED_GRAPH_SOURCE_FAMILY as TRACE_DERIVED_GRAPH_SOURCE_FAMILY,
)
from aippocampus_runtime.navigation.trace_graph_ingress import (
    trace_derived_graph_contribution_candidates as trace_derived_graph_contribution_candidates,
)
from aippocampus_runtime.registry.api import unique_preserve

CONTRIBUTION_MANIFEST_META_KEY = "contribution_manifest"
CONTRIBUTION_MANIFEST_SCHEMA_VERSION = "concept_graph_contribution_manifest_v1"

NODE_CONTRIBUTION_TABLE = "concept_node_contributions"
EDGE_CONTRIBUTION_TABLE = "concept_edge_contributions"
TEMP_NODE_CONTRIBUTION_TABLE = "temp_concept_node_contributions"
TEMP_EDGE_CONTRIBUTION_TABLE = "temp_concept_edge_contributions"

_CONTRIBUTION_NODE_TABLES = {
    NODE_CONTRIBUTION_TABLE,
    TEMP_NODE_CONTRIBUTION_TABLE,
}
_CONTRIBUTION_EDGE_TABLES = {
    EDGE_CONTRIBUTION_TABLE,
    TEMP_EDGE_CONTRIBUTION_TABLE,
}

_GRAPH_STATUS_RANK = {
    "staging": 0,
    "verified": 1,
    "parked": 2,
    "retired": 3,
}

NODE_CONTRIBUTION_COLUMNS = [
    "source_family",
    "slice_key",
    "concept_id",
    "label",
    "normalized_label",
    "kind",
    "kind_source",
    "kind_confidence",
    "status",
    "scope_key",
    "hit_count",
    "thread_count",
    "lifecycle_reason",
]

EDGE_CONTRIBUTION_COLUMNS = [
    "source_family",
    "slice_key",
    "src_concept_id",
    "dst_concept_id",
    "edge_type",
    "scope_key",
    "weight",
    "confidence",
    "status",
    "evidence_count",
    "thread_count",
    "lifecycle_reason",
    "source_thread_key",
    "source_message_id",
]

EdgeKey = tuple[str, str, str, str]
SliceRef = tuple[str, str]


class ConceptResolver(Protocol):
    def resolve(self, con: sqlite3.Connection, label: str, **kwargs: Any) -> str | None:
        ...


class ConceptGraphContributionModel(NamedTuple):
    concept_id_for: Callable[[str], str]
    concept_normalized: Callable[[str], str]
    concept_is_noise: Callable[[str], bool]
    edge_weight: Callable[[float, str, int], float]
    add_bidirectional_edge: Callable[..., None]


def stable_slice_key(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def phrase_stat_for_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    stat = item.get("term_quality") or item.get("phrase_stat")
    return dict(stat) if isinstance(stat, dict) else None


def association_item_reviewed(item: dict[str, Any]) -> bool:
    kind_status = str(
        item.get("concept_kind_status") or item.get("kind_status") or ""
    ).casefold()
    if kind_status == "reviewed":
        return True
    return any(
        isinstance(source, dict) and source.get("source") == "registry_anchor"
        for source in item.get("threads") or []
    )


def association_term_quality_context(
    item: dict[str, Any],
    *,
    ingress: str,
    source_threads: list[str],
) -> TermQualityContext:
    return TermQualityContext(
        ingress=ingress,
        reviewed=association_item_reviewed(item),
        static_anchor=association_item_reviewed(item),
        source_backed=bool(source_threads),
        hit_count=int(item.get("hit_count") or 0),
        thread_count=len(source_threads),
        phrase_stat=phrase_stat_for_item(item),
    )


def validate_contribution_table(table: str, *, edge: bool = False) -> str:
    allowed = _CONTRIBUTION_EDGE_TABLES if edge else _CONTRIBUTION_NODE_TABLES
    if table not in allowed:
        raise ValueError(f"unexpected contribution table: {table}")
    return table


def _status_rank(status: Any) -> int:
    return _GRAPH_STATUS_RANK.get(normalize_graph_status(status), 0)


def _higher_status(left: Any, right: Any) -> str:
    left_status = normalize_graph_status(left)
    right_status = normalize_graph_status(right)
    return right_status if _status_rank(right_status) >= _status_rank(left_status) else left_status


def create_temp_contribution_tables(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS temp_concept_node_contributions;
        DROP TABLE IF EXISTS temp_concept_edge_contributions;

        CREATE TEMP TABLE temp_concept_node_contributions (
            source_family TEXT NOT NULL,
            slice_key TEXT NOT NULL,
            concept_id TEXT NOT NULL,
            label TEXT NOT NULL,
            normalized_label TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'topic',
            kind_source TEXT NOT NULL DEFAULT 'fallback',
            kind_confidence REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'staging',
            scope_key TEXT NOT NULL DEFAULT 'global',
            hit_count INTEGER NOT NULL DEFAULT 0,
            thread_count INTEGER NOT NULL DEFAULT 0,
            lifecycle_reason TEXT NOT NULL DEFAULT 'staging_default',
            PRIMARY KEY (source_family, slice_key, concept_id)
        );

        CREATE TEMP TABLE temp_concept_edge_contributions (
            source_family TEXT NOT NULL,
            slice_key TEXT NOT NULL,
            src_concept_id TEXT NOT NULL,
            dst_concept_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            scope_key TEXT NOT NULL DEFAULT 'global',
            weight REAL NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'staging',
            evidence_count INTEGER NOT NULL DEFAULT 0,
            thread_count INTEGER NOT NULL DEFAULT 0,
            lifecycle_reason TEXT NOT NULL DEFAULT 'staging_default',
            source_thread_key TEXT,
            source_message_id TEXT,
            PRIMARY KEY (
                source_family, slice_key, src_concept_id, dst_concept_id, edge_type, scope_key
            )
        );
        """
    )


def upsert_node_contribution(
    con: sqlite3.Connection,
    *,
    model: ConceptGraphContributionModel,
    table: str,
    source_family: str,
    slice_key: str,
    label: str,
    status: str,
    lifecycle_reason: str = "staging_default",
    hit_count: int = 0,
    thread_count: int = 0,
    scope_key: str = "global",
    supplied_kind: Any = None,
    supplied_kind_status: Any = None,
    source_backed_kind: bool = False,
) -> str | None:
    table = validate_contribution_table(table)
    label = normalize_term(label)
    if model.concept_is_noise(label):
        return None
    concept_id = model.concept_id_for(label)
    normalized = model.concept_normalized(label)
    kind = classify_concept_kind(
        label,
        supplied_kind=supplied_kind,
        supplied_kind_status=supplied_kind_status,
        source_backed_kind=source_backed_kind,
    )
    existing = con.execute(
        f"""
        SELECT status, hit_count, thread_count, kind, kind_source, kind_confidence,
               lifecycle_reason
        FROM {table}
        WHERE source_family = ? AND slice_key = ? AND concept_id = ?
        """,
        (source_family, slice_key, concept_id),
    ).fetchone()
    if existing:
        best_status = _higher_status(existing["status"], status)
        existing_confidence = float(existing["kind_confidence"] or 0.0)
        if float(kind["kind_confidence"]) >= existing_confidence:
            next_kind = str(kind["kind"])
            next_kind_source = str(kind["kind_source"])
            next_kind_confidence = float(kind["kind_confidence"])
        else:
            next_kind = str(existing["kind"])
            next_kind_source = str(existing["kind_source"])
            next_kind_confidence = existing_confidence
        next_reason = (
            lifecycle_reason
            if best_status == normalize_graph_status(status)
            else str(existing["lifecycle_reason"] or "staging_default")
        )
        con.execute(
            f"""
            UPDATE {table}
            SET label = ?, normalized_label = ?, kind = ?, kind_source = ?,
                kind_confidence = ?, status = ?, hit_count = MAX(hit_count, ?),
                thread_count = MAX(thread_count, ?), lifecycle_reason = ?
            WHERE source_family = ? AND slice_key = ? AND concept_id = ?
            """,
            (
                label,
                normalized,
                next_kind,
                next_kind_source,
                next_kind_confidence,
                best_status,
                int(hit_count or 0),
                int(thread_count or 0),
                next_reason,
                source_family,
                slice_key,
                concept_id,
            ),
        )
        return concept_id
    con.execute(
        f"""
        INSERT INTO {table}
        (source_family, slice_key, concept_id, label, normalized_label, kind,
         kind_source, kind_confidence, status, scope_key, hit_count, thread_count,
         lifecycle_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_family,
            slice_key,
            concept_id,
            label,
            normalized,
            str(kind["kind"]),
            str(kind["kind_source"]),
            float(kind["kind_confidence"]),
            normalize_graph_status(status),
            scope_key,
            int(hit_count or 0),
            int(thread_count or 0),
            lifecycle_reason,
        ),
    )
    return concept_id


def upsert_edge_contribution(
    con: sqlite3.Connection,
    src_id: str,
    dst_id: str,
    *,
    model: ConceptGraphContributionModel,
    table: str,
    source_family: str,
    slice_key: str,
    edge_type: str,
    confidence: float,
    status: str,
    evidence_count: int,
    lifecycle_reason: str = "staging_default",
    thread_count: int = 0,
    scope_key: str = "global",
    source_thread_key: str | None = None,
    source_message_id: str | None = None,
) -> None:
    if src_id == dst_id:
        return
    table = validate_contribution_table(table, edge=True)
    weight = model.edge_weight(confidence, edge_type, evidence_count)
    existing = con.execute(
        f"""
        SELECT confidence, status, evidence_count, thread_count, lifecycle_reason,
               source_thread_key, source_message_id
        FROM {table}
        WHERE source_family = ? AND slice_key = ? AND src_concept_id = ?
          AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
        """,
        (source_family, slice_key, src_id, dst_id, edge_type, scope_key),
    ).fetchone()
    if existing:
        best_status = _higher_status(existing["status"], status)
        best_confidence = max(float(existing["confidence"] or 0.0), confidence)
        best_evidence = max(int(existing["evidence_count"] or 0), int(evidence_count or 0))
        best_thread_count = max(int(existing["thread_count"] or 0), int(thread_count or 0))
        next_reason = (
            lifecycle_reason
            if best_status == normalize_graph_status(status)
            else str(existing["lifecycle_reason"] or "staging_default")
        )
        con.execute(
            f"""
            UPDATE {table}
            SET weight = ?, confidence = ?, status = ?, evidence_count = ?,
                thread_count = ?, lifecycle_reason = ?,
                source_thread_key = COALESCE(source_thread_key, ?),
                source_message_id = COALESCE(source_message_id, ?)
            WHERE source_family = ? AND slice_key = ? AND src_concept_id = ?
              AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
            """,
            (
                model.edge_weight(best_confidence, edge_type, best_evidence),
                best_confidence,
                best_status,
                best_evidence,
                best_thread_count,
                next_reason,
                source_thread_key,
                source_message_id,
                source_family,
                slice_key,
                src_id,
                dst_id,
                edge_type,
                scope_key,
            ),
        )
        return
    con.execute(
        f"""
        INSERT INTO {table}
        (source_family, slice_key, src_concept_id, dst_concept_id, edge_type, scope_key,
         weight, confidence, status, evidence_count, thread_count, lifecycle_reason,
         source_thread_key, source_message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_family,
            slice_key,
            src_id,
            dst_id,
            edge_type,
            scope_key,
            weight,
            confidence,
            normalize_graph_status(status),
            int(evidence_count or 0),
            int(thread_count or 0),
            lifecycle_reason,
            source_thread_key,
            source_message_id,
        ),
    )


class ContributionBuildContext:
    """Collect graph contributions with explicit ingress/slice ownership."""

    def __init__(self, con: sqlite3.Connection, model: ConceptGraphContributionModel) -> None:
        self.con = con
        self.model = model
        self.node_table = TEMP_NODE_CONTRIBUTION_TABLE
        self.edge_table = TEMP_EDGE_CONTRIBUTION_TABLE
        self.source_family = "unknown"
        self.slice_key = "unknown"
        self.resolve_requests = 0
        self.unique_concept_ids: set[str] = set()
        self.concept_cache_hits = 0
        self.none_results = 0
        self.edge_upsert_attempts = 0

    @contextmanager
    def slice(self, source_family: str, slice_key: str) -> Iterator[None]:
        previous = (self.source_family, self.slice_key)
        self.source_family = source_family
        self.slice_key = slice_key
        try:
            yield
        finally:
            self.source_family, self.slice_key = previous

    def resolve(self, con: sqlite3.Connection, label: str, **kwargs: Any) -> str | None:
        source_family = str(kwargs.pop("contribution_source_family", "") or self.source_family)
        slice_key = str(kwargs.pop("contribution_slice_key", "") or self.slice_key)
        self.resolve_requests += 1
        concept_id = upsert_node_contribution(
            con,
            model=self.model,
            table=self.node_table,
            source_family=source_family,
            slice_key=slice_key,
            label=label,
            **kwargs,
        )
        if concept_id is None:
            self.none_results += 1
            return None
        if concept_id in self.unique_concept_ids:
            self.concept_cache_hits += 1
        self.unique_concept_ids.add(concept_id)
        return concept_id

    def upsert_edge(self, con: sqlite3.Connection, *args: Any, **kwargs: Any) -> None:
        source_family = str(kwargs.pop("contribution_source_family", "") or self.source_family)
        slice_key = str(kwargs.pop("contribution_slice_key", "") or self.slice_key)
        self.edge_upsert_attempts += 1
        upsert_edge_contribution(
            con,
            *args,
            model=self.model,
            table=self.edge_table,
            source_family=source_family,
            slice_key=slice_key,
            **kwargs,
        )

    def diagnostics(self) -> dict[str, int]:
        return {
            "edge_upsert_attempts": self.edge_upsert_attempts,
            "concept_resolve_requests": self.resolve_requests,
            "unique_concept_labels": len(self.unique_concept_ids),
            "concept_db_upsert_attempts": len(self.unique_concept_ids),
            "concept_cache_hits": self.concept_cache_hits,
            "concept_cache_refreshes": 0,
            "concept_none_results": self.none_results,
        }


def contribution_rows(
    con: sqlite3.Connection,
    table: str,
    columns: list[str],
    *,
    edge: bool = False,
) -> list[dict[str, Any]]:
    table = validate_contribution_table(table, edge=edge)
    rows = con.execute(
        f"SELECT {', '.join(columns)} FROM {table} ORDER BY {', '.join(columns)}"
    ).fetchall()
    return [{column: row[column] for column in columns} for row in rows]


def contribution_manifest_from_tables(
    con: sqlite3.Connection,
    *,
    node_table: str,
    edge_table: str,
) -> dict[str, Any]:
    slices: dict[str, dict[str, Any]] = {}
    rows_by_kind = [
        ("node", row)
        for row in contribution_rows(con, node_table, NODE_CONTRIBUTION_COLUMNS)
    ] + [
        ("edge", row)
        for row in contribution_rows(con, edge_table, EDGE_CONTRIBUTION_COLUMNS, edge=True)
    ]
    for row_kind, row in rows_by_kind:
        source_family = str(row["source_family"])
        slice_key = str(row["slice_key"])
        manifest_key = f"{source_family}|{slice_key}"
        entry = slices.setdefault(
            manifest_key,
            {
                "source_family": source_family,
                "slice_key": slice_key,
                "node_count": 0,
                "edge_count": 0,
                "_rows": [],
            },
        )
        entry[f"{row_kind}_count"] = int(entry.get(f"{row_kind}_count") or 0) + 1
        entry["_rows"].append({"row_kind": row_kind, **row})
    public_slices: dict[str, dict[str, Any]] = {}
    for key, entry in sorted(slices.items()):
        rows = sorted(entry.pop("_rows"), key=lambda item: json.dumps(item, sort_keys=True))
        digest = hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        public_slices[key] = {**entry, "digest": digest}
    return {
        "schema_version": CONTRIBUTION_MANIFEST_SCHEMA_VERSION,
        "policy_version": "",
        "slice_count": len(public_slices),
        "slices": public_slices,
    }


def manifest_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = manifest.get("slices")
    return entries if isinstance(entries, dict) else {}


def _slice_ref(entry: dict[str, Any]) -> SliceRef:
    return (str(entry.get("source_family") or ""), str(entry.get("slice_key") or ""))


def diff_contribution_manifests(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> tuple[set[SliceRef], set[SliceRef], set[str]]:
    previous_entries = manifest_entries(previous)
    current_entries = manifest_entries(current)
    changed: set[SliceRef] = set()
    deleted: set[SliceRef] = set()
    changed_families: set[str] = set()
    for key, entry in current_entries.items():
        previous_entry = previous_entries.get(key)
        if not previous_entry or previous_entry.get("digest") != entry.get("digest"):
            slice_ref = _slice_ref(entry)
            changed.add(slice_ref)
            changed_families.add(slice_ref[0])
    for key, entry in previous_entries.items():
        if key not in current_entries:
            slice_ref = _slice_ref(entry)
            deleted.add(slice_ref)
            changed_families.add(slice_ref[0])
    return changed, deleted, changed_families


def collect_affected_contribution_keys(
    con: sqlite3.Connection,
    *,
    slice_refs: set[SliceRef],
    node_table: str,
    edge_table: str,
) -> tuple[set[str], set[EdgeKey], int, int]:
    node_table = validate_contribution_table(node_table)
    edge_table = validate_contribution_table(edge_table, edge=True)
    if not slice_refs:
        return set(), set(), 0, 0
    concept_ids: set[str] = set()
    edge_keys: set[EdgeKey] = set()
    con.execute("DROP TABLE IF EXISTS temp_affected_contribution_slices")
    con.execute(
        """
        CREATE TEMP TABLE temp_affected_contribution_slices (
            source_family TEXT NOT NULL,
            slice_key TEXT NOT NULL,
            PRIMARY KEY (source_family, slice_key)
        )
        """
    )
    try:
        con.executemany(
            """
            INSERT OR IGNORE INTO temp_affected_contribution_slices
            (source_family, slice_key)
            VALUES (?, ?)
            """,
            sorted(slice_refs),
        )
        node_rows_data = con.execute(
            f"""
            SELECT n.concept_id
            FROM {node_table} AS n
            JOIN temp_affected_contribution_slices AS s
              ON n.source_family = s.source_family AND n.slice_key = s.slice_key
            """
        ).fetchall()
        edge_rows_data = con.execute(
            f"""
            SELECT e.src_concept_id, e.dst_concept_id, e.edge_type, e.scope_key
            FROM {edge_table} AS e
            JOIN temp_affected_contribution_slices AS s
              ON e.source_family = s.source_family AND e.slice_key = s.slice_key
            """
        ).fetchall()
    finally:
        con.execute("DROP TABLE IF EXISTS temp_affected_contribution_slices")
    for row in node_rows_data:
        concept_ids.add(str(row["concept_id"]))
    for row in edge_rows_data:
        src_id = str(row["src_concept_id"])
        dst_id = str(row["dst_concept_id"])
        concept_ids.update({src_id, dst_id})
        edge_keys.add((src_id, dst_id, str(row["edge_type"]), str(row["scope_key"])))
    return concept_ids, edge_keys, len(node_rows_data), len(edge_rows_data)


def delete_official_contribution_slices(
    con: sqlite3.Connection,
    slice_refs: set[SliceRef],
) -> tuple[int, int]:
    deleted_nodes = 0
    deleted_edges = 0
    for source_family, slice_key in sorted(slice_refs):
        edge_cursor = con.execute(
            """
            DELETE FROM concept_edge_contributions
            WHERE source_family = ? AND slice_key = ?
            """,
            (source_family, slice_key),
        )
        node_cursor = con.execute(
            """
            DELETE FROM concept_node_contributions
            WHERE source_family = ? AND slice_key = ?
            """,
            (source_family, slice_key),
        )
        deleted_edges += max(0, edge_cursor.rowcount)
        deleted_nodes += max(0, node_cursor.rowcount)
    return deleted_nodes, deleted_edges


def copy_temp_contribution_slices(
    con: sqlite3.Connection,
    slice_refs: set[SliceRef],
) -> tuple[int, int]:
    inserted_nodes = 0
    inserted_edges = 0
    for source_family, slice_key in sorted(slice_refs):
        node_cursor = con.execute(
            f"""
            INSERT INTO concept_node_contributions ({', '.join(NODE_CONTRIBUTION_COLUMNS)})
            SELECT {', '.join(NODE_CONTRIBUTION_COLUMNS)}
            FROM temp_concept_node_contributions
            WHERE source_family = ? AND slice_key = ?
            """,
            (source_family, slice_key),
        )
        edge_cursor = con.execute(
            f"""
            INSERT INTO concept_edge_contributions ({', '.join(EDGE_CONTRIBUTION_COLUMNS)})
            SELECT {', '.join(EDGE_CONTRIBUTION_COLUMNS)}
            FROM temp_concept_edge_contributions
            WHERE source_family = ? AND slice_key = ?
            """,
            (source_family, slice_key),
        )
        inserted_nodes += max(0, node_cursor.rowcount)
        inserted_edges += max(0, edge_cursor.rowcount)
    return inserted_nodes, inserted_edges


def copy_all_temp_contributions(con: sqlite3.Connection) -> tuple[int, int]:
    node_cursor = con.execute(
        f"""
        INSERT INTO concept_node_contributions ({', '.join(NODE_CONTRIBUTION_COLUMNS)})
        SELECT {', '.join(NODE_CONTRIBUTION_COLUMNS)}
        FROM temp_concept_node_contributions
        """
    )
    edge_cursor = con.execute(
        f"""
        INSERT INTO concept_edge_contributions ({', '.join(EDGE_CONTRIBUTION_COLUMNS)})
        SELECT {', '.join(EDGE_CONTRIBUTION_COLUMNS)}
        FROM temp_concept_edge_contributions
        """
    )
    return max(0, node_cursor.rowcount), max(0, edge_cursor.rowcount)


def _row_float(row: sqlite3.Row, column: str) -> float:
    return float(row[column] or 0.0) if column in row.keys() else 0.0


def _row_int(row: sqlite3.Row, column: str) -> int:
    return int(row[column] or 0) if column in row.keys() else 0


def _best_row_by_status(rows: list[sqlite3.Row]) -> sqlite3.Row:
    return max(
        rows,
        key=lambda row: (
            _status_rank(row["status"]),
            _row_float(row, "confidence") or _row_float(row, "kind_confidence"),
            _row_int(row, "evidence_count") or _row_int(row, "hit_count"),
        ),
    )


def _first_non_empty(rows: list[sqlite3.Row], column: str) -> str | None:
    for row in rows:
        value = str(row[column] or "").strip()
        if value:
            return value
    return None


def project_edge_key(
    con: sqlite3.Connection,
    key: EdgeKey,
    *,
    model: ConceptGraphContributionModel,
) -> bool:
    src_id, dst_id, edge_type, scope_key = key
    rows = con.execute(
        """
        SELECT *
        FROM concept_edge_contributions
        WHERE src_concept_id = ? AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
        """,
        (src_id, dst_id, edge_type, scope_key),
    ).fetchall()
    if not rows:
        con.execute(
            """
            DELETE FROM concept_edges
            WHERE src_concept_id = ? AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
            """,
            (src_id, dst_id, edge_type, scope_key),
        )
        return False
    best_row = _best_row_by_status(rows)
    status = normalize_graph_status(best_row["status"])
    lifecycle_reason = str(best_row["lifecycle_reason"] or "staging_default")
    confidence = max(float(row["confidence"] or 0.0) for row in rows)
    evidence_count = max(int(row["evidence_count"] or 0) for row in rows)
    thread_count = max(int(row["thread_count"] or 0) for row in rows)
    now = now_utc()
    existing = con.execute(
        """
        SELECT first_seen_at
        FROM concept_edges
        WHERE src_concept_id = ? AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
        """,
        (src_id, dst_id, edge_type, scope_key),
    ).fetchone()
    first_seen_at = str(existing["first_seen_at"]) if existing else now
    con.execute(
        """
        INSERT OR REPLACE INTO concept_edges
        (src_concept_id, dst_concept_id, edge_type, weight, confidence, status, scope_key,
         evidence_count, thread_count, lifecycle_reason, lifecycle_updated_at,
         source_thread_key, source_message_id, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            src_id,
            dst_id,
            edge_type,
            model.edge_weight(confidence, edge_type, evidence_count),
            confidence,
            status,
            scope_key,
            evidence_count,
            thread_count,
            lifecycle_reason,
            now,
            _first_non_empty(rows, "source_thread_key"),
            _first_non_empty(rows, "source_message_id"),
            first_seen_at,
            now,
        ),
    )
    return True


def project_concept_id(con: sqlite3.Connection, concept_id: str) -> bool:
    rows = con.execute(
        """
        SELECT *
        FROM concept_node_contributions
        WHERE concept_id = ?
        """,
        (concept_id,),
    ).fetchall()
    if not rows:
        con.execute("DELETE FROM concepts WHERE concept_id = ?", (concept_id,))
        return False
    best_status_row = max(
        rows,
        key=lambda row: (_status_rank(row["status"]), int(row["hit_count"] or 0)),
    )
    best_kind_row = max(rows, key=lambda row: float(row["kind_confidence"] or 0.0))
    label_row = max(
        rows,
        key=lambda row: (int(row["hit_count"] or 0), int(row["thread_count"] or 0)),
    )
    status = normalize_graph_status(best_status_row["status"])
    now = now_utc()
    existing = con.execute(
        "SELECT created_at FROM concepts WHERE concept_id = ?",
        (concept_id,),
    ).fetchone()
    created_at = str(existing["created_at"]) if existing else now
    con.execute(
        """
        INSERT OR REPLACE INTO concepts
        (concept_id, label, normalized_label, kind, kind_source, kind_confidence,
         status, scope_key, hit_count, thread_count, lifecycle_reason,
         lifecycle_updated_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            concept_id,
            str(label_row["label"]),
            str(label_row["normalized_label"]),
            str(best_kind_row["kind"]),
            str(best_kind_row["kind_source"]),
            float(best_kind_row["kind_confidence"] or 0.0),
            status,
            str(best_status_row["scope_key"] or "global"),
            max(int(row["hit_count"] or 0) for row in rows),
            max(int(row["thread_count"] or 0) for row in rows),
            str(best_status_row["lifecycle_reason"] or "staging_default"),
            now,
            created_at,
            now,
        ),
    )
    return True


def project_contribution_read_model(
    con: sqlite3.Connection,
    *,
    model: ConceptGraphContributionModel,
    concept_ids: set[str],
    edge_keys: set[EdgeKey],
) -> dict[str, int]:
    projected_edges = 0
    deleted_edges = 0
    ordered_edge_keys = list(edge_keys)
    ordered_edge_keys.sort()
    for key in ordered_edge_keys:
        if project_edge_key(con, key, model=model):
            projected_edges += 1
        else:
            deleted_edges += 1
    projected_concepts = 0
    deleted_concepts = 0
    ordered_concept_ids = list(concept_ids)
    ordered_concept_ids.sort()
    for concept_id in ordered_concept_ids:
        if project_concept_id(con, concept_id):
            projected_concepts += 1
        else:
            deleted_concepts += 1
    return {
        "read_model_edge_keys_reprojected": projected_edges,
        "read_model_edge_keys_deleted": deleted_edges,
        "read_model_concept_ids_reprojected": projected_concepts,
        "read_model_concept_ids_deleted": deleted_concepts,
    }


def all_contribution_keys(con: sqlite3.Connection) -> tuple[set[str], set[EdgeKey]]:
    concept_ids = {
        str(row["concept_id"])
        for row in con.execute("SELECT DISTINCT concept_id FROM concept_node_contributions")
        .fetchall()
    }
    edge_keys = {
        (
            str(row["src_concept_id"]),
            str(row["dst_concept_id"]),
            str(row["edge_type"]),
            str(row["scope_key"]),
        )
        for row in con.execute(
            """
            SELECT DISTINCT src_concept_id, dst_concept_id, edge_type, scope_key
            FROM concept_edge_contributions
            """
        ).fetchall()
    }
    for src_id, dst_id, _, _ in edge_keys:
        concept_ids.update({src_id, dst_id})
    return concept_ids, edge_keys


def materialize_input_contributions(
    con: sqlite3.Connection,
    *,
    model: ConceptGraphContributionModel,
    associations_path: Path,
    project_timeline_path: Path | None,
    subconscious_edges_path: Path | None,
    max_related_per_term: int,
    policy_version: str,
) -> dict[str, Any]:
    create_temp_contribution_tables(con)
    associations = load_associations(associations_path)
    contribution_context = ContributionBuildContext(con, model)

    def add_build_edge(edge_con: sqlite3.Connection, *args: Any, **kwargs: Any) -> None:
        source_family = kwargs.pop("contribution_source_family", None)
        slice_key = kwargs.pop("contribution_slice_key", None)
        if source_family and slice_key:
            with contribution_context.slice(str(source_family), str(slice_key)):
                model.add_bidirectional_edge(
                    edge_con,
                    *args,
                    concept_resolver=contribution_context,
                    upsert_edge_fn=contribution_context.upsert_edge,
                    **kwargs,
                )
            return
        model.add_bidirectional_edge(
            edge_con,
            *args,
            concept_resolver=contribution_context,
            upsert_edge_fn=contribution_context.upsert_edge,
            **kwargs,
        )

    term_items = list((associations.get("terms") or {}).values())
    item_by_normalized = {
        model.concept_normalized(str(item.get("term") or "")): item
        for item in term_items
        if isinstance(item, dict) and item.get("term")
    }
    related_phrase_stats = {
        key: stat
        for key, item in item_by_normalized.items()
        if (stat := phrase_stat_for_item(item)) is not None
    }
    term_quality = ConceptTermQualityTracker()
    quality_gate: dict[str, Any] = {
        "schema_version": "concept_graph_quality_gate_v1",
        "min_auto_co_occurs_thread_count": edge_policy.MIN_AUTO_COOCCURS_THREAD_COUNT,
        "edge_type_status_counts": {},
        "reason_counts": {},
    }
    for item in term_items:
        if not isinstance(item, dict):
            continue
        term = normalize_term(str(item.get("term") or ""))
        slice_key = stable_slice_key("association", model.concept_normalized(term))
        status = "verified" if item.get("status") == "verified" else "staging"
        lifecycle_reason = "association_verified" if status == "verified" else "association_staging"
        confidence = float(item.get("confidence") or 0.0)
        sources = item.get("threads") or []
        source_threads = unique_preserve(
            [
                str(source.get("thread_key") or "")
                for source in sources
                if source.get("thread_key")
            ]
        )
        term_context = association_term_quality_context(
            item,
            ingress="association",
            source_threads=source_threads,
        )
        if not term_quality.accepts(term, term_context):
            continue
        with contribution_context.slice("associations", slice_key):
            supplied_kind = item.get("concept_kind")
            supplied_kind_status = item.get("concept_kind_status") or item.get("kind_status")
            term_id = contribution_context.resolve(
                con,
                term,
                status=status,
                lifecycle_reason=lifecycle_reason,
                hit_count=int(item.get("hit_count") or 0),
                thread_count=len(source_threads),
                supplied_kind=supplied_kind,
                supplied_kind_status=supplied_kind_status,
                source_backed_kind=bool(supplied_kind)
                and status == "verified"
                and bool(source_threads),
            )
            if not term_id:
                continue
            edge_type = "verified_related" if status == "verified" else "co_occurs"
            related_context = TermQualityContext(
                ingress="related_term",
                reviewed=association_item_reviewed(item),
                static_anchor=association_item_reviewed(item),
                source_backed=bool(source_threads),
                hit_count=int(item.get("hit_count") or 0),
                thread_count=len(source_threads),
            )
            related_terms = term_quality.filter_terms(
                list(item.get("related_terms") or []),
                related_context,
                phrase_stats_by_term=related_phrase_stats,
                limit=max(0, int(max_related_per_term)),
            )
            for related in related_terms:
                edge_status, gate_reason = edge_policy.automatic_co_occurs_expansion_status(
                    edge_type=edge_type,
                    status=status,
                    thread_count=len(source_threads),
                )
                edge_reason = gate_reason or lifecycle_reason
                edge_policy.quality_gate_bucket(quality_gate, edge_type, edge_status)
                if gate_reason:
                    edge_policy.quality_gate_reason(quality_gate, gate_reason)
                add_build_edge(
                    con,
                    term,
                    str(related),
                    edge_type=edge_type,
                    confidence=confidence,
                    status=edge_status,
                    lifecycle_reason=edge_reason,
                    evidence_count=int(item.get("hit_count") or 0),
                    thread_count=len(source_threads),
                    source_thread_key=source_threads[0] if source_threads else None,
                )

    timeline_edge_count = collect_timeline_edges(
        con,
        project_timeline_path,
        term_quality=term_quality,
        add_bidirectional_edge=add_build_edge,
    )
    subconscious_edge_count, subconscious_hub_quality = collect_subconscious_edges(
        con,
        subconscious_edges_path,
        term_quality=term_quality,
        upsert_concept=contribution_context.resolve,
        upsert_edge=contribution_context.upsert_edge,
    )
    quality_gate["term_quality"] = term_quality.to_payload()
    quality_gate["subconscious_hub_quality"] = subconscious_hub_quality
    contribution_manifest = contribution_manifest_from_tables(
        con,
        node_table=TEMP_NODE_CONTRIBUTION_TABLE,
        edge_table=TEMP_EDGE_CONTRIBUTION_TABLE,
    )
    contribution_manifest["policy_version"] = policy_version
    return {
        "quality_gate": quality_gate,
        "timeline_edge_count": timeline_edge_count,
        "subconscious_edge_count": subconscious_edge_count,
        "contribution_manifest": contribution_manifest,
        "diagnostics": contribution_context.diagnostics(),
    }
