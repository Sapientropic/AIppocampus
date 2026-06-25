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
    normalize_term,
    term_is_noise,
)
from aippocampus_runtime.navigation.concept_graph_build_state import (
    CONCEPT_GRAPH_BUILD_POLICY_VERSION,
    build_input_manifest,
    load_meta_json,
    unchanged_input_reuse_payload,
)
from aippocampus_runtime.navigation.concept_graph_contributions import (
    CONTRIBUTION_MANIFEST_META_KEY,
    CONTRIBUTION_MANIFEST_SCHEMA_VERSION,
    EDGE_CONTRIBUTION_COLUMNS,
    EDGE_CONTRIBUTION_TABLE,
    NODE_CONTRIBUTION_COLUMNS,
    NODE_CONTRIBUTION_TABLE,
    TEMP_EDGE_CONTRIBUTION_TABLE,
    TEMP_NODE_CONTRIBUTION_TABLE,
    ConceptGraphContributionModel,
    ConceptResolver,
    all_contribution_keys,
    collect_affected_contribution_keys,
    contribution_rows,
    copy_all_temp_contributions,
    copy_temp_contribution_slices,
    delete_official_contribution_slices,
    diff_contribution_manifests,
    manifest_entries,
    materialize_input_contributions,
    project_contribution_read_model,
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


def _write_build_meta(
    con: sqlite3.Connection,
    *,
    metadata: dict[str, Any],
    quality_gate: dict[str, Any],
    input_manifest: dict[str, Any],
    contribution_manifest: dict[str, Any],
    build_diagnostics: dict[str, Any],
) -> None:
    payloads = {
        **metadata,
        "quality_gate": quality_gate,
        "input_manifest": input_manifest,
        CONTRIBUTION_MANIFEST_META_KEY: contribution_manifest,
        "build_metadata": metadata,
        "build_diagnostics": build_diagnostics,
    }
    for key, value in payloads.items():
        con.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True)),
        )


def _build_result_payload(
    con: sqlite3.Connection,
    *,
    output_path: Path,
    metadata: dict[str, Any],
    input_manifest: dict[str, Any],
    quality_gate: dict[str, Any],
    build_diagnostics: dict[str, Any],
    timeline_edge_count: int,
    subconscious_edge_count: int,
) -> dict[str, Any]:
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
    concept_resolver: ConceptResolver | None = None,
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
        previous_contribution_manifest = load_meta_json(con, CONTRIBUTION_MANIFEST_META_KEY)
        if previous_contribution_manifest and (
            reuse := unchanged_input_reuse_payload(
                con,
                output_path=output_path,
                input_manifest=input_manifest,
            )
        ):
            reuse.setdefault("source_boundary", graph_source_boundary())
            reuse.setdefault("concept_kind_counts", count_by_column(con, "kind"))
            reuse.setdefault("concept_kind_source_counts", count_by_column(con, "kind_source"))
            reuse.setdefault("lifecycle", lifecycle_diagnostics(con))
            reuse["build_diagnostics"]["incremental_update_deferred"] = False
            reuse["build_diagnostics"]["contribution_manifest_reused"] = True
            reuse["build_diagnostics"]["elapsed_ms"] = round(
                (time.perf_counter() - start) * 1000, 3
            )
            return reuse

        contribution_model = ConceptGraphContributionModel(
            concept_id_for=concept_id_for,
            concept_normalized=concept_normalized,
            concept_is_noise=concept_is_noise,
            edge_weight=edge_weight,
            add_bidirectional_edge=add_bidirectional_edge,
        )
        materialized = materialize_input_contributions(
            con,
            model=contribution_model,
            associations_path=associations_path,
            project_timeline_path=project_timeline_path,
            subconscious_edges_path=subconscious_edges_path,
            max_related_per_term=max_related_per_term,
            policy_version=CONCEPT_GRAPH_BUILD_POLICY_VERSION,
        )
        quality_gate = materialized["quality_gate"]
        current_contribution_manifest = materialized["contribution_manifest"]
        current_entries = manifest_entries(current_contribution_manifest)
        previous_entries = manifest_entries(previous_contribution_manifest)
        changed_slices, deleted_slices, changed_families = diff_contribution_manifests(
            previous_contribution_manifest,
            current_contribution_manifest,
        )
        previous_slice_count = len(previous_entries)
        current_slice_count = len(current_entries)
        full_rebuild_fallback_reason = ""
        projection_diagnostics: dict[str, int] = {}
        contribution_rows_deleted = {"nodes": 0, "edges": 0}
        contribution_rows_inserted = {"nodes": 0, "edges": 0}
        considered_new_nodes = len(
            contribution_rows(
                con,
                TEMP_NODE_CONTRIBUTION_TABLE,
                NODE_CONTRIBUTION_COLUMNS,
            )
        )
        considered_new_edges = len(
            contribution_rows(
                con,
                TEMP_EDGE_CONTRIBUTION_TABLE,
                EDGE_CONTRIBUTION_COLUMNS,
                edge=True,
            )
        )
        if not previous_contribution_manifest or previous_slice_count <= 0:
            full_rebuild_fallback_reason = "missing_or_legacy_contribution_manifest"
            reset_graph(con)
            inserted_nodes, inserted_edges = copy_all_temp_contributions(con)
            contribution_rows_inserted = {"nodes": inserted_nodes, "edges": inserted_edges}
            all_concept_ids, all_edge_keys = all_contribution_keys(con)
            projection_diagnostics = project_contribution_read_model(
                con,
                model=contribution_model,
                concept_ids=all_concept_ids,
                edge_keys=all_edge_keys,
            )
            build_mode = "full_rebuild"
            reset_graph_called = True
        elif not changed_slices and not deleted_slices:
            build_mode = "skipped_unchanged_contributions"
            reset_graph_called = False
        else:
            affected_slice_refs = changed_slices | deleted_slices
            old_concepts, old_edges, old_node_rows, old_edge_rows = (
                collect_affected_contribution_keys(
                    con,
                    slice_refs=affected_slice_refs,
                    node_table=NODE_CONTRIBUTION_TABLE,
                    edge_table=EDGE_CONTRIBUTION_TABLE,
                )
            )
            new_concepts, new_edges, new_node_rows, new_edge_rows = (
                collect_affected_contribution_keys(
                    con,
                    slice_refs=changed_slices,
                    node_table=TEMP_NODE_CONTRIBUTION_TABLE,
                    edge_table=TEMP_EDGE_CONTRIBUTION_TABLE,
                )
            )
            deleted_nodes, deleted_edges = delete_official_contribution_slices(
                con, affected_slice_refs
            )
            inserted_nodes, inserted_edges = copy_temp_contribution_slices(
                con, changed_slices
            )
            contribution_rows_deleted = {"nodes": deleted_nodes, "edges": deleted_edges}
            contribution_rows_inserted = {"nodes": inserted_nodes, "edges": inserted_edges}
            projection_diagnostics = project_contribution_read_model(
                con,
                model=contribution_model,
                concept_ids=old_concepts | new_concepts,
                edge_keys=old_edges | new_edges,
            )
            projection_diagnostics.update(
                {
                    "old_slice_node_rows_considered": old_node_rows,
                    "old_slice_edge_rows_considered": old_edge_rows,
                    "new_slice_node_rows_considered": new_node_rows,
                    "new_slice_edge_rows_considered": new_edge_rows,
                }
            )
            build_mode = "incremental_update"
            reset_graph_called = False

        parked_edge_contributions = int(
            con.execute(
                "SELECT COUNT(*) AS count FROM concept_edge_contributions WHERE status = 'parked'"
            ).fetchone()["count"]
            or 0
        )
        build_diagnostics = {
            "schema_version": "concept_graph_build_diagnostics_v1",
            "build_mode": build_mode,
            "incremental_update_deferred": False,
            "reset_graph_called": reset_graph_called,
            "policy_version": CONCEPT_GRAPH_BUILD_POLICY_VERSION,
            "contribution_manifest_schema": CONTRIBUTION_MANIFEST_SCHEMA_VERSION,
            "previous_contribution_slice_count": previous_slice_count,
            "current_contribution_slice_count": current_slice_count,
            "changed_contribution_slice_count": len(changed_slices),
            "deleted_contribution_slice_count": len(deleted_slices),
            "changed_families": sorted(changed_families),
            "node_contribution_rows_considered": considered_new_nodes,
            "edge_contribution_rows_considered": considered_new_edges,
            "node_contribution_rows_updated": contribution_rows_inserted["nodes"],
            "edge_contribution_rows_updated": contribution_rows_inserted["edges"],
            "node_contribution_rows_deleted": contribution_rows_deleted["nodes"],
            "edge_contribution_rows_deleted": contribution_rows_deleted["edges"],
            "parked_edge_contribution_rows": parked_edge_contributions,
            "full_rebuild_fallback_reason": full_rebuild_fallback_reason or None,
            **materialized["diagnostics"],
            **projection_diagnostics,
        }
        build_diagnostics["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        metadata = {
            "schema_version": CONCEPT_GRAPH_SCHEMA_VERSION,
            "kind": "aippocampus_concept_graph",
            "created_at": now_utc(),
            "build_mode": build_mode,
            "source_associations": str(associations_path),
            "source_project_timeline": str(project_timeline_path)
            if project_timeline_path
            else None,
            "source_subconscious_edges": str(subconscious_edges_path)
            if subconscious_edges_path
            else None,
            "max_related_per_term": max_related_per_term,
        }
        _write_build_meta(
            con,
            metadata=metadata,
            quality_gate=quality_gate,
            input_manifest=input_manifest,
            contribution_manifest=current_contribution_manifest,
            build_diagnostics=build_diagnostics,
        )
        con.commit()
        return _build_result_payload(
            con,
            output_path=output_path,
            metadata=metadata,
            input_manifest=input_manifest,
            quality_gate=quality_gate,
            build_diagnostics=build_diagnostics,
            timeline_edge_count=int(materialized["timeline_edge_count"]),
            subconscious_edge_count=int(materialized["subconscious_edge_count"]),
        )
    finally:
        con.close()


def main() -> int:
    cli = importlib.import_module("aippocampus_runtime.navigation.concept_graph_cli")
    return int(cli.main())


if __name__ == "__main__":
    raise SystemExit(main())
