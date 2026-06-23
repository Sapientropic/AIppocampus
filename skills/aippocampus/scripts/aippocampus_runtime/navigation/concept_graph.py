#!/usr/bin/env python3
"""Build and query a lightweight AIppocampus concept graph.

The graph is an expansion layer for ambient recall. It is not evidence: it can
add query terms or improve candidate scent, but exact claims still need
clean-source or raw-rollout support.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.navigation import concept_graph_edge_policy as edge_policy
from aippocampus_runtime.navigation.associations import (
    load_associations,
    normalize_term,
    term_is_noise,
)
from aippocampus_runtime.navigation.concept_edge_utility import score_bucket
from aippocampus_runtime.navigation.concept_graph_health import (  # noqa: F401
    concept_graph_health as concept_graph_health,
)
from aippocampus_runtime.navigation.concept_graph_schema import (
    connect,
    init_schema,
    reset_graph,
)
from aippocampus_runtime.navigation.concept_graph_schema import (
    default_concept_graph_path as default_concept_graph_path,
)
from aippocampus_runtime.navigation.concept_kinds import (
    classify_concept_kind,
)
from aippocampus_runtime.navigation.concept_kinds import (
    infer_concept_kind as _infer_concept_kind,
)
from aippocampus_runtime.navigation.concept_lifecycle import (
    choose_status,
    graph_source_boundary,
    lifecycle_decision,
    lifecycle_diagnostics,
    normalize_graph_status,
    safe_edge_type,
    source_ref_thread_keys,
    strongest_lifecycle_signal,
    unique_source_refs,
)
from aippocampus_runtime.registry.api import unique_preserve

# Public graph artifact schema. Additive rebuildable SQLite cache columns are
# migrated in concept_graph_schema.py without changing this artifact contract.
CONCEPT_GRAPH_SCHEMA_VERSION = 1
DEFAULT_MAX_RELATED_PER_TERM = 10
DEFAULT_MAX_DEGREE = 12
DEFAULT_MAX_TERMS = 18

GENERIC_CONCEPT_TERMS = {
    "关于",
    "当前",
    "当前线程",
    "前线程",
    "线程",
    "这个",
    "那个",
    "问题",
    "实现",
    "方案",
    "主题是什么",
}

# Edge multipliers are explicit ranking priors. Utility telemetry may report
# whether these priors helped source reopen, but it must not mutate them or make
# graph proximity count as source evidence.
EDGE_TYPE_MULTIPLIER = {
    "alias": 1.0,
    "verified_related": 0.85,
    "same_decision_space": 0.82,
    "decision_about": 0.78,
    "project_topic": 0.72,
    "depends_on": 0.68,
    "contrasts_with": 0.65,
    "supersedes": 0.62,
    "related": 0.58,
    "co_occurs": 0.55,
}

BIDIRECTIONAL_EDGE_TYPES = {
    "alias",
    "same_decision_space",
    "contrasts_with",
    "co_occurs",
    "project_topic",
    "related",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def concept_normalized(value: str) -> str:
    return normalize_term(value).casefold()


def concept_is_noise(value: str) -> bool:
    term = normalize_term(value)
    if not term:
        return True
    if term.casefold() in {item.casefold() for item in GENERIC_CONCEPT_TERMS}:
        return True
    return term_is_noise(term)


def concept_id_for(label: str) -> str:
    normalized = concept_normalized(label)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:20]
    return f"cpt_{digest}"


def infer_concept_kind(label: str) -> str:
    return _infer_concept_kind(label)


def upsert_concept(
    con: sqlite3.Connection,
    label: str,
    *,
    status: str,
    lifecycle_reason: str = "staging_default",
    hit_count: int = 0,
    thread_count: int = 0,
    scope_key: str = "global",
    supplied_kind: Any = None,
    supplied_kind_status: Any = None,
    source_backed_kind: bool = False,
) -> str | None:
    label = normalize_term(label)
    if concept_is_noise(label):
        return None
    concept_id = concept_id_for(label)
    normalized = concept_normalized(label)
    kind = classify_concept_kind(
        label,
        supplied_kind=supplied_kind,
        supplied_kind_status=supplied_kind_status,
        source_backed_kind=source_backed_kind,
    )
    now = now_utc()
    existing = con.execute(
        """
        SELECT concept_id, status, hit_count, thread_count, kind, kind_source, kind_confidence,
               lifecycle_reason
        FROM concepts
        WHERE concept_id = ?
        """,
        (concept_id,),
    ).fetchone()
    if existing:
        best_status = choose_status(str(existing["status"]), status)
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
            """
            UPDATE concepts
            SET label = ?, kind = ?, kind_source = ?, kind_confidence = ?,
                status = ?, hit_count = MAX(hit_count, ?),
                thread_count = MAX(thread_count, ?),
                lifecycle_reason = ?, lifecycle_updated_at = ?, updated_at = ?
            WHERE concept_id = ?
            """,
            (
                label,
                next_kind,
                next_kind_source,
                next_kind_confidence,
                best_status,
                int(hit_count or 0),
                int(thread_count or 0),
                next_reason,
                now,
                now,
                concept_id,
            ),
        )
    else:
        con.execute(
            """
            INSERT INTO concepts
            (concept_id, label, normalized_label, kind, kind_source, kind_confidence,
             status, scope_key, hit_count, thread_count, lifecycle_reason,
             lifecycle_updated_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                now,
                now,
                now,
            ),
        )
    return concept_id


def edge_weight(confidence: float, edge_type: str, evidence_count: int) -> float:
    multiplier = EDGE_TYPE_MULTIPLIER.get(edge_type, 0.5)
    evidence_bonus = min(0.18, math.log(max(1, evidence_count), 10) * 0.08)
    return round(max(0.01, min(1.0, confidence * multiplier + evidence_bonus)), 4)


def upsert_edge(
    con: sqlite3.Connection,
    src_id: str,
    dst_id: str,
    *,
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
    now = now_utc()
    weight = edge_weight(confidence, edge_type, evidence_count)
    existing = con.execute(
        """
        SELECT confidence, status, evidence_count, thread_count, first_seen_at, lifecycle_reason
        FROM concept_edges
        WHERE src_concept_id = ? AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
        """,
        (src_id, dst_id, edge_type, scope_key),
    ).fetchone()
    if existing:
        best_status = choose_status(str(existing["status"]), status)
        best_confidence = max(float(existing["confidence"] or 0.0), confidence)
        best_evidence = max(int(existing["evidence_count"] or 0), int(evidence_count or 0))
        best_thread_count = max(int(existing["thread_count"] or 0), int(thread_count or 0))
        next_reason = (
            lifecycle_reason
            if best_status == normalize_graph_status(status)
            else str(existing["lifecycle_reason"] or "staging_default")
        )
        con.execute(
            """
            UPDATE concept_edges
            SET weight = ?, confidence = ?, status = ?, evidence_count = ?,
                thread_count = ?, lifecycle_reason = ?, lifecycle_updated_at = ?,
                source_thread_key = COALESCE(source_thread_key, ?),
                source_message_id = COALESCE(source_message_id, ?),
                last_seen_at = ?
            WHERE src_concept_id = ? AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
            """,
            (
                edge_weight(best_confidence, edge_type, best_evidence),
                best_confidence,
                best_status,
                best_evidence,
                best_thread_count,
                next_reason,
                now,
                source_thread_key,
                source_message_id,
                now,
                src_id,
                dst_id,
                edge_type,
                scope_key,
            ),
        )
    else:
        con.execute(
            """
            INSERT INTO concept_edges
            (src_concept_id, dst_concept_id, edge_type, weight, confidence, status, scope_key,
             evidence_count, thread_count, lifecycle_reason, lifecycle_updated_at,
             source_thread_key, source_message_id, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                src_id,
                dst_id,
                edge_type,
                weight,
                confidence,
                normalize_graph_status(status),
                scope_key,
                int(evidence_count or 0),
                int(thread_count or 0),
                lifecycle_reason,
                now,
                source_thread_key,
                source_message_id,
                now,
                now,
            ),
        )


def count_by_column(con: sqlite3.Connection, column: str) -> dict[str, int]:
    if column not in {"kind", "kind_source"}:
        return {}
    rows = con.execute(
        f"SELECT {column} AS value, COUNT(*) AS count FROM concepts GROUP BY {column}"
    ).fetchall()
    return {str(row["value"] or "unknown"): int(row["count"] or 0) for row in rows}


def add_bidirectional_edge(
    con: sqlite3.Connection,
    a: str,
    b: str,
    *,
    edge_type: str,
    confidence: float,
    status: str,
    evidence_count: int,
    thread_count: int = 0,
    lifecycle_reason: str = "staging_default",
    source_thread_key: str | None = None,
) -> None:
    concept_status, concept_lifecycle_reason = edge_policy.concept_lifecycle_for_edge(
        status=status,
        lifecycle_reason=lifecycle_reason,
    )
    a_id = upsert_concept(
        con,
        a,
        status=concept_status,
        lifecycle_reason=concept_lifecycle_reason,
        hit_count=evidence_count,
        thread_count=thread_count,
    )
    b_id = upsert_concept(
        con,
        b,
        status=concept_status,
        lifecycle_reason=concept_lifecycle_reason,
        hit_count=evidence_count,
        thread_count=thread_count,
    )
    if not a_id or not b_id:
        return
    upsert_edge(
        con,
        a_id,
        b_id,
        edge_type=edge_type,
        confidence=confidence,
        status=status,
        evidence_count=evidence_count,
        lifecycle_reason=lifecycle_reason,
        thread_count=thread_count,
        source_thread_key=source_thread_key,
    )
    upsert_edge(
        con,
        b_id,
        a_id,
        edge_type=edge_type,
        confidence=confidence,
        status=status,
        evidence_count=evidence_count,
        lifecycle_reason=lifecycle_reason,
        thread_count=thread_count,
        source_thread_key=source_thread_key,
    )


def collect_timeline_edges(con: sqlite3.Connection, timeline_path: Path | None) -> int:
    if not timeline_path or not timeline_path.exists():
        return 0
    timeline = load_json(timeline_path)
    edge_count = 0
    for project in (timeline.get("projects") or {}).values():
        if not isinstance(project, dict):
            continue
        project_label = str(project.get("project_label") or "").strip()
        project_terms = unique_preserve(
            [project_label, *list(project.get("project_tags") or [])],
            limit=8,
        )
        for turn in project.get("latest_turns") or []:
            if not isinstance(turn, dict):
                continue
            topic_terms = unique_preserve(
                project_terms + list(turn.get("topic_terms") or []), limit=18
            )
            topic_terms = [term for term in topic_terms if not concept_is_noise(term)]
            if len(topic_terms) < 2:
                continue
            source_thread_key = turn.get("thread_key")
            for idx, term in enumerate(topic_terms):
                for related in topic_terms[idx + 1 :]:
                    add_bidirectional_edge(
                        con,
                        term,
                        related,
                        edge_type="project_topic",
                        confidence=0.9,
                        status="staging",
                        evidence_count=1,
                        source_thread_key=source_thread_key,
                    )
                    edge_count += 2
    return edge_count


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def collect_subconscious_edges(con: sqlite3.Connection, staging_path: Path | None) -> int:
    if not staging_path or not staging_path.exists():
        return 0
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in iter_jsonl(staging_path):
        if item.get("kind") != "aippocampus_subconscious_edge":
            continue
        src = str(item.get("src") or "")
        dst = str(item.get("dst") or "")
        if concept_is_noise(src) or concept_is_noise(dst):
            continue
        confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        refs = [ref for ref in item.get("source_refs") or [] if isinstance(ref, dict)]
        if not refs:
            continue
        edge_type = safe_edge_type(item.get("edge_type") or "related")
        key = (normalize_term(src), normalize_term(dst), edge_type)
        group = grouped.setdefault(
            key,
            {
                "src": normalize_term(src),
                "dst": normalize_term(dst),
                "edge_type": edge_type,
                "confidence": 0.0,
                "refs": [],
                "thread_keys": [],
                "statuses": [],
                "signals": [],
                "src_kind": item.get("src_concept_kind") or item.get("source_concept_kind"),
                "dst_kind": item.get("dst_concept_kind") or item.get("target_concept_kind"),
                "kind_status": item.get("concept_kind_status") or item.get("kind_status"),
            },
        )
        group["confidence"] = max(float(group["confidence"] or 0.0), confidence)
        group["refs"] = unique_source_refs(list(group.get("refs") or []) + refs)
        group["thread_keys"] = unique_preserve(
            list(group.get("thread_keys") or []) + source_ref_thread_keys(refs)
        )
        group["statuses"].append(item.get("status") or "staging")
        group["signals"].append(
            item.get("lifecycle_signal")
            or item.get("lifecycle_status")
            or item.get("retirement_signal")
            or item.get("status")
            or "staging"
        )
        if not group.get("src_kind"):
            group["src_kind"] = item.get("src_concept_kind") or item.get("source_concept_kind")
        if not group.get("dst_kind"):
            group["dst_kind"] = item.get("dst_concept_kind") or item.get("target_concept_kind")
        if not group.get("kind_status"):
            group["kind_status"] = item.get("concept_kind_status") or item.get("kind_status")
    inserted = 0
    for group in grouped.values():
        refs = [ref for ref in group.get("refs") or [] if isinstance(ref, dict)]
        thread_keys = [str(key) for key in group.get("thread_keys") or [] if key]
        source_thread_key = thread_keys[0] if thread_keys else refs[0].get("thread_key")
        status_signal = strongest_lifecycle_signal(
            list(group.get("statuses") or []) + list(group.get("signals") or [])
        )
        status, lifecycle_reason = lifecycle_decision(
            requested_status=status_signal,
            confidence=float(group.get("confidence") or 0.0),
            evidence_count=len(refs),
            thread_count=len(thread_keys),
            lifecycle_signal=status_signal,
            source_backed=bool(refs),
        )
        src_id = upsert_concept(
            con,
            str(group["src"]),
            status=status,
            lifecycle_reason=lifecycle_reason,
            hit_count=len(refs),
            thread_count=len(thread_keys),
            supplied_kind=group.get("src_kind"),
            supplied_kind_status=group.get("kind_status"),
            source_backed_kind=bool(refs),
        )
        dst_id = upsert_concept(
            con,
            str(group["dst"]),
            status=status,
            lifecycle_reason=lifecycle_reason,
            hit_count=len(refs),
            thread_count=len(thread_keys),
            supplied_kind=group.get("dst_kind"),
            supplied_kind_status=group.get("kind_status"),
            source_backed_kind=bool(refs),
        )
        if not src_id or not dst_id:
            continue
        upsert_edge(
            con,
            src_id,
            dst_id,
            edge_type=str(group["edge_type"]),
            confidence=float(group.get("confidence") or 0.0),
            status=status,
            evidence_count=len(refs),
            lifecycle_reason=lifecycle_reason,
            thread_count=len(thread_keys),
            source_thread_key=source_thread_key,
        )
        inserted += 1
        if group["edge_type"] in BIDIRECTIONAL_EDGE_TYPES:
            upsert_edge(
                con,
                dst_id,
                src_id,
                edge_type=str(group["edge_type"]),
                confidence=float(group.get("confidence") or 0.0),
                status=status,
                evidence_count=len(refs),
                lifecycle_reason=lifecycle_reason,
                thread_count=len(thread_keys),
                source_thread_key=source_thread_key,
            )
            inserted += 1
    return inserted


def build_concept_graph(
    associations_path: Path,
    output_path: Path,
    *,
    project_timeline_path: Path | None = None,
    subconscious_edges_path: Path | None = None,
    max_related_per_term: int = DEFAULT_MAX_RELATED_PER_TERM,
) -> dict[str, Any]:
    associations = load_associations(associations_path)
    con = connect(output_path)
    try:
        init_schema(con)
        reset_graph(con)
        term_items = list((associations.get("terms") or {}).values())
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
            if concept_is_noise(term):
                continue
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
            supplied_kind = item.get("concept_kind")
            supplied_kind_status = item.get("concept_kind_status") or item.get("kind_status")
            term_id = upsert_concept(
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
            for related in list(item.get("related_terms") or [])[
                : max(0, int(max_related_per_term))
            ]:
                edge_status, gate_reason = edge_policy.automatic_co_occurs_expansion_status(
                    edge_type=edge_type,
                    status=status,
                    thread_count=len(source_threads),
                )
                edge_reason = gate_reason or lifecycle_reason
                edge_policy.quality_gate_bucket(quality_gate, edge_type, edge_status)
                if gate_reason:
                    edge_policy.quality_gate_reason(quality_gate, gate_reason)
                add_bidirectional_edge(
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
        timeline_edge_count = collect_timeline_edges(con, project_timeline_path)
        subconscious_edge_count = collect_subconscious_edges(con, subconscious_edges_path)
        metadata = {
            "schema_version": CONCEPT_GRAPH_SCHEMA_VERSION,
            "kind": "aippocampus_concept_graph",
            "created_at": now_utc(),
            "source_associations": str(associations_path),
            "source_project_timeline": str(project_timeline_path)
            if project_timeline_path
            else None,
            "source_subconscious_edges": str(subconscious_edges_path)
            if subconscious_edges_path
            else None,
            "max_related_per_term": max_related_per_term,
        }
        for key, value in metadata.items():
            con.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        con.commit()
        concepts = con.execute("SELECT COUNT(*) AS count FROM concepts").fetchone()["count"]
        edges = con.execute("SELECT COUNT(*) AS count FROM concept_edges").fetchone()["count"]
        return {
            **metadata,
            "output": str(output_path),
            "concept_count": concepts,
            "edge_count": edges,
            "timeline_edge_count": timeline_edge_count,
            "subconscious_edge_count": subconscious_edge_count,
            "concept_kind_counts": count_by_column(con, "kind"),
            "concept_kind_source_counts": count_by_column(con, "kind_source"),
            "lifecycle": lifecycle_diagnostics(con),
            "quality_gate": quality_gate,
            "source_boundary": graph_source_boundary(),
        }
    finally:
        con.close()


def concept_ids_for_terms(con: sqlite3.Connection, terms: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for term in terms:
        normalized = concept_normalized(str(term))
        if not normalized or normalized in seen or concept_is_noise(normalized):
            continue
        seen.add(normalized)
        row = con.execute(
            """
            SELECT concept_id, label
            FROM concepts
            WHERE normalized_label = ?
              AND status IN ('verified', 'staging')
            """,
            (normalized,),
        ).fetchone()
        if row:
            out.append((row["concept_id"], row["label"]))
    return out


def edge_rows(
    con: sqlite3.Connection, src_id: str, *, max_degree: int, depth: int
) -> list[sqlite3.Row]:
    rows = con.execute(
        """
        SELECT e.*, c.label AS dst_label, c.normalized_label AS dst_normalized,
               c.kind AS dst_kind, c.kind_source AS dst_kind_source,
               c.kind_confidence AS dst_kind_confidence
        FROM concept_edges e
        JOIN concepts sc ON sc.concept_id = e.src_concept_id
        JOIN concepts c ON c.concept_id = e.dst_concept_id
        WHERE e.src_concept_id = ?
          AND e.status IN ('verified', 'staging')
          AND sc.status IN ('verified', 'staging')
          AND c.status IN ('verified', 'staging')
          AND NOT (
            e.edge_type = 'co_occurs'
            AND e.status = 'staging'
            AND e.thread_count < ?
          )
        ORDER BY
          CASE e.status WHEN 'verified' THEN 0 ELSE 1 END,
          e.weight DESC,
          e.confidence DESC
        LIMIT ?
        """,
        (src_id, edge_policy.MIN_AUTO_COOCCURS_THREAD_COUNT, max(1, int(max_degree))),
    ).fetchall()
    if depth <= 1:
        return rows
    # Depth-2 expansion is where semantic drift usually appears. Keep it to
    # verified or very high-confidence edges so a broad co-occurrence chain
    # cannot turn one vague word into a personal-memory flood.
    return [
        row
        for row in rows
        if row["status"] == "verified" or float(row["confidence"] or 0.0) >= 0.88
    ]


def expand_concepts(
    db_path: Path,
    seed_terms: list[str],
    *,
    depth: int = 2,
    max_degree: int = DEFAULT_MAX_DEGREE,
    max_terms: int = DEFAULT_MAX_TERMS,
    min_score: float = 0.15,
) -> list[dict[str, Any]]:
    if not db_path.exists() or depth <= 0:
        return []
    try:
        con = sqlite3.connect(db_path, timeout=2)
    except sqlite3.Error:
        return []
    con.row_factory = sqlite3.Row
    try:
        seeds = concept_ids_for_terms(con, seed_terms)
        if not seeds:
            return []
        seed_norms = {concept_normalized(label) for _, label in seeds}
        queue: list[tuple[str, float, int, list[str], list[str]]] = [
            (concept_id, 1.0, 0, [label], []) for concept_id, label in seeds
        ]
        best: dict[str, dict[str, Any]] = {}
        visited: set[tuple[str, int]] = set()
        while queue:
            concept_id, score, current_depth, path, edge_types = queue.pop(0)
            if current_depth >= depth:
                continue
            if (concept_id, current_depth) in visited:
                continue
            visited.add((concept_id, current_depth))
            next_depth = current_depth + 1
            for edge in edge_rows(con, concept_id, max_degree=max_degree, depth=next_depth):
                label = str(edge["dst_label"] or "")
                normalized = concept_normalized(label)
                if not label or normalized in seed_norms or concept_is_noise(label):
                    continue
                depth_decay = 1.0 if next_depth == 1 else 0.45
                next_score = score * float(edge["weight"] or 0.0) * depth_decay
                if next_score < min_score:
                    continue
                existing = best.get(normalized)
                row = {
                    "term": label,
                    "score": round(next_score, 4),
                    "depth": next_depth,
                    "path": path + [label],
                    "edge_types": edge_types + [edge["edge_type"]],
                    "score_bucket": score_bucket(next_score),
                    "status": edge["status"],
                    "concept_kind": edge["dst_kind"],
                    "concept_kind_source": edge["dst_kind_source"],
                    "concept_kind_confidence": edge["dst_kind_confidence"],
                    "source_boundary": graph_source_boundary(),
                }
                if not existing or next_score > float(existing.get("score") or 0.0):
                    best[normalized] = row
                queue.append(
                    (
                        edge["dst_concept_id"],
                        next_score,
                        next_depth,
                        path + [label],
                        edge_types + [edge["edge_type"]],
                    )
                )
        rows = sorted(
            best.values(),
            key=lambda item: (
                -float(item.get("score") or 0.0),
                int(item.get("depth") or 0),
                str(item.get("term") or "").casefold(),
            ),
        )
        return rows[: max(1, int(max_terms))]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def main() -> int:
    cli = importlib.import_module("aippocampus_runtime.navigation.concept_graph_cli")
    return int(cli.main())


if __name__ == "__main__":
    raise SystemExit(main())
