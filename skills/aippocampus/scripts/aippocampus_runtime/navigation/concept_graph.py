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
import time
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.navigation import concept_graph_edge_policy as edge_policy
from aippocampus_runtime.navigation.associations import (
    load_associations,
    normalize_term,
    term_is_noise,
)
from aippocampus_runtime.navigation.concept_graph_build_state import (
    CONCEPT_GRAPH_BUILD_POLICY_VERSION,
    BuildConceptResolver,
    build_input_manifest,
    unchanged_input_reuse_payload,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    DEFAULT_MAX_DEGREE as DEFAULT_MAX_DEGREE,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    DEFAULT_MAX_NEIGHBOR_FETCHES as DEFAULT_MAX_NEIGHBOR_FETCHES,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    DEFAULT_MAX_TERMS as DEFAULT_MAX_TERMS,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    concept_ids_for_terms as concept_ids_for_terms,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    edge_query_plan as edge_query_plan,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    edge_rows as edge_rows,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    edge_rows_with_diagnostics as edge_rows_with_diagnostics,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    expand_concepts as expand_concepts,
)
from aippocampus_runtime.navigation.concept_graph_expand import (
    expand_concepts_with_diagnostics as expand_concepts_with_diagnostics,
)
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
from aippocampus_runtime.navigation.concept_kinds import (
    classify_concept_kind,
)
from aippocampus_runtime.navigation.concept_kinds import (
    infer_concept_kind as _infer_concept_kind,
)
from aippocampus_runtime.navigation.concept_lifecycle import (
    choose_status,
    graph_source_boundary,
    lifecycle_diagnostics,
    normalize_graph_status,
)
from aippocampus_runtime.registry.api import unique_preserve

# Public graph artifact schema. Additive rebuildable SQLite cache columns are
# migrated in concept_graph_schema.py without changing this artifact contract.
CONCEPT_GRAPH_SCHEMA_VERSION = 1
DEFAULT_MAX_RELATED_PER_TERM = 10

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

def concept_normalized(value: str) -> str:
    return normalize_term(value).casefold()


def concept_is_noise(value: str) -> bool:
    term = normalize_term(value)
    if not term:
        return True
    if term.casefold() in {item.casefold() for item in GENERIC_CONCEPT_TERMS}:
        return True
    return term_is_noise(term)


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
    concept_resolver: BuildConceptResolver | None = None,
    upsert_edge_fn: Callable[..., None] | None = None,
) -> None:
    concept_status, concept_lifecycle_reason = edge_policy.concept_lifecycle_for_edge(
        status=status,
        lifecycle_reason=lifecycle_reason,
    )
    resolve_concept = concept_resolver.resolve if concept_resolver else upsert_concept
    write_edge = upsert_edge_fn or upsert_edge
    a_id = resolve_concept(
        con,
        a,
        status=concept_status,
        lifecycle_reason=concept_lifecycle_reason,
        hit_count=evidence_count,
        thread_count=thread_count,
    )
    b_id = resolve_concept(
        con,
        b,
        status=concept_status,
        lifecycle_reason=concept_lifecycle_reason,
        hit_count=evidence_count,
        thread_count=thread_count,
    )
    if not a_id or not b_id:
        return
    write_edge(
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
    write_edge(
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


def build_concept_graph(
    associations_path: Path,
    output_path: Path,
    *,
    project_timeline_path: Path | None = None,
    subconscious_edges_path: Path | None = None,
    max_related_per_term: int = DEFAULT_MAX_RELATED_PER_TERM,
) -> dict[str, Any]:
    start = time.perf_counter()
    input_manifest = build_input_manifest(
        associations_path=associations_path,
        project_timeline_path=project_timeline_path,
        subconscious_edges_path=subconscious_edges_path,
        max_related_per_term=max_related_per_term,
    )
    con = connect(output_path)
    try:
        init_schema(con)
        if reuse := unchanged_input_reuse_payload(
            con,
            output_path=output_path,
            input_manifest=input_manifest,
        ):
            reuse.setdefault("source_boundary", graph_source_boundary())
            reuse.setdefault("concept_kind_counts", count_by_column(con, "kind"))
            reuse.setdefault("concept_kind_source_counts", count_by_column(con, "kind_source"))
            reuse.setdefault("lifecycle", lifecycle_diagnostics(con))
            reuse["build_diagnostics"]["elapsed_ms"] = round(
                (time.perf_counter() - start) * 1000, 3
            )
            return reuse
        associations = load_associations(associations_path)
        reset_graph(con)
        concept_resolver = BuildConceptResolver(
            normalize_key=concept_normalized,
            upsert=upsert_concept,
        )
        edge_upsert_attempts = 0

        def tracked_upsert_edge(edge_con: sqlite3.Connection, *args: Any, **kwargs: Any) -> None:
            nonlocal edge_upsert_attempts
            edge_upsert_attempts += 1
            upsert_edge(edge_con, *args, **kwargs)

        def resolve_concept(
            resolve_con: sqlite3.Connection, label: str, **kwargs: Any
        ) -> str | None:
            return concept_resolver.resolve(resolve_con, label, **kwargs)

        def add_build_edge(
            edge_con: sqlite3.Connection, *args: Any, **kwargs: Any
        ) -> None:
            add_bidirectional_edge(
                edge_con,
                *args,
                concept_resolver=concept_resolver,
                upsert_edge_fn=tracked_upsert_edge,
                **kwargs,
            )

        term_items = list((associations.get("terms") or {}).values())
        item_by_normalized = {
            concept_normalized(str(item.get("term") or "")): item
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
            supplied_kind = item.get("concept_kind")
            supplied_kind_status = item.get("concept_kind_status") or item.get("kind_status")
            term_id = resolve_concept(
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
            upsert_concept=resolve_concept,
            upsert_edge=tracked_upsert_edge,
        )
        quality_gate["term_quality"] = term_quality.to_payload()
        quality_gate["subconscious_hub_quality"] = subconscious_hub_quality
        build_diagnostics = {
            "schema_version": "concept_graph_build_diagnostics_v1",
            "build_mode": "full_rebuild",
            "incremental_update_deferred": True,
            "reset_graph_called": True,
            "policy_version": CONCEPT_GRAPH_BUILD_POLICY_VERSION,
            "edge_upsert_attempts": edge_upsert_attempts,
            **concept_resolver.diagnostics(),
        }
        build_diagnostics["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        metadata = {
            "schema_version": CONCEPT_GRAPH_SCHEMA_VERSION,
            "kind": "aippocampus_concept_graph",
            "created_at": now_utc(),
            "build_mode": "full_rebuild",
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
        con.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            ("quality_gate", json.dumps(quality_gate, ensure_ascii=False)),
        )
        con.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            ("input_manifest", json.dumps(input_manifest, ensure_ascii=False, sort_keys=True)),
        )
        con.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            ("build_metadata", json.dumps(metadata, ensure_ascii=False)),
        )
        con.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            ("build_diagnostics", json.dumps(build_diagnostics, ensure_ascii=False)),
        )
        con.commit()
        concepts = con.execute("SELECT COUNT(*) AS count FROM concepts").fetchone()["count"]
        edges = con.execute("SELECT COUNT(*) AS count FROM concept_edges").fetchone()["count"]
        return {
            **metadata,
            "output": str(output_path),
            "input_manifest": input_manifest,
            "concept_count": concepts,
            "edge_count": edges,
            "timeline_edge_count": timeline_edge_count,
            "subconscious_edge_count": subconscious_edge_count,
            "concept_kind_counts": count_by_column(con, "kind"),
            "concept_kind_source_counts": count_by_column(con, "kind_source"),
            "lifecycle": lifecycle_diagnostics(con),
            "quality_gate": quality_gate,
            "build_diagnostics": build_diagnostics,
            "source_boundary": graph_source_boundary(),
        }
    finally:
        con.close()


def main() -> int:
    cli = importlib.import_module("aippocampus_runtime.navigation.concept_graph_cli")
    return int(cli.main())


if __name__ == "__main__":
    raise SystemExit(main())
