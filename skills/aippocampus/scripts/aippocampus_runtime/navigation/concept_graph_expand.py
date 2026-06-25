"""Live concept graph expansion with query-plan and budget diagnostics."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation import concept_graph_edge_policy as edge_policy
from aippocampus_runtime.navigation.associations import normalize_term, term_is_noise
from aippocampus_runtime.navigation.concept_edge_utility import score_bucket
from aippocampus_runtime.navigation.concept_lifecycle import graph_source_boundary

DEFAULT_MAX_DEGREE = 12
DEFAULT_MAX_TERMS = 18
DEFAULT_MAX_NEIGHBOR_FETCHES = 24
MAX_SEED_LOOKUP_TERMS = 64


def concept_normalized(value: str) -> str:
    return normalize_term(value).casefold()


def concept_is_noise(value: str) -> bool:
    term = normalize_term(value)
    if not term:
        return True
    if term.casefold() in {
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
    }:
        return True
    return term_is_noise(term)


def concept_ids_for_terms(con: sqlite3.Connection, terms: list[str]) -> list[tuple[str, str]]:
    normalized_terms: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = concept_normalized(str(term))
        if not normalized or normalized in seen or concept_is_noise(normalized):
            continue
        seen.add(normalized)
        normalized_terms.append(normalized)
        if len(normalized_terms) >= MAX_SEED_LOOKUP_TERMS:
            break
    if not normalized_terms:
        return []
    placeholders = ",".join("?" for _ in normalized_terms)
    rows = con.execute(
        f"""
        SELECT concept_id, label, normalized_label
        FROM concepts
        WHERE normalized_label IN ({placeholders})
          AND status IN ('verified', 'staging')
        """,
        tuple(normalized_terms),
    ).fetchall()
    by_normalized: dict[str, tuple[str, str]] = {}
    for row in rows:
        by_normalized.setdefault(str(row["normalized_label"]), (row["concept_id"], row["label"]))
    out: list[tuple[str, str]] = []
    for normalized in normalized_terms:
        if row := by_normalized.get(normalized):
            out.append(row)
    return out


def _edge_rows_for_status(
    con: sqlite3.Connection,
    src_id: str,
    *,
    status: str,
    limit: int,
) -> list[sqlite3.Row]:
    return con.execute(
        """
        SELECT e.*, c.label AS dst_label, c.normalized_label AS dst_normalized,
               c.kind AS dst_kind, c.kind_source AS dst_kind_source,
               c.kind_confidence AS dst_kind_confidence
        FROM concept_edges e
        JOIN concepts sc ON sc.concept_id = e.src_concept_id
        JOIN concepts c ON c.concept_id = e.dst_concept_id
        WHERE e.src_concept_id = ?
          AND e.status = ?
          AND sc.status IN ('verified', 'staging')
          AND c.status IN ('verified', 'staging')
          AND NOT (
            e.edge_type = 'co_occurs'
            AND e.status = 'staging'
            AND e.thread_count < ?
          )
        ORDER BY e.weight DESC, e.confidence DESC
        LIMIT ?
        """,
        (
            src_id,
            status,
            edge_policy.MIN_AUTO_COOCCURS_THREAD_COUNT,
            max(1, int(limit)),
        ),
    ).fetchall()


def edge_query_plan(
    con: sqlite3.Connection,
    src_id: str,
    *,
    status: str = "verified",
    max_degree: int = DEFAULT_MAX_DEGREE,
) -> dict[str, Any]:
    rows = con.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT e.*, c.label AS dst_label, c.normalized_label AS dst_normalized,
               c.kind AS dst_kind, c.kind_source AS dst_kind_source,
               c.kind_confidence AS dst_kind_confidence
        FROM concept_edges e
        JOIN concepts sc ON sc.concept_id = e.src_concept_id
        JOIN concepts c ON c.concept_id = e.dst_concept_id
        WHERE e.src_concept_id = ?
          AND e.status = ?
          AND sc.status IN ('verified', 'staging')
          AND c.status IN ('verified', 'staging')
          AND NOT (
            e.edge_type = 'co_occurs'
            AND e.status = 'staging'
            AND e.thread_count < ?
          )
        ORDER BY e.weight DESC, e.confidence DESC
        LIMIT ?
        """,
        (
            src_id,
            status,
            edge_policy.MIN_AUTO_COOCCURS_THREAD_COUNT,
            max(1, int(max_degree)),
        ),
    ).fetchall()
    details = [str(row["detail"] if isinstance(row, sqlite3.Row) else row[3]) for row in rows]
    return {
        "status": status,
        "uses_temp_btree": any("USE TEMP B-TREE" in detail.upper() for detail in details),
        "uses_expand_index": any("idx_concept_edges_expand" in detail for detail in details),
        "plan": details,
    }


def edge_rows_with_diagnostics(
    con: sqlite3.Connection, src_id: str, *, max_degree: int, depth: int
) -> tuple[list[sqlite3.Row], dict[str, Any]]:
    remaining = max(1, int(max_degree))
    rows: list[sqlite3.Row] = []
    status_counts: dict[str, int] = {}
    for status in ("verified", "staging"):
        if remaining <= 0:
            break
        batch = _edge_rows_for_status(con, src_id, status=status, limit=remaining)
        rows.extend(batch)
        status_counts[status] = len(batch)
        remaining -= len(batch)
    if depth <= 1:
        return rows, {
            "rows_returned": len(rows),
            "status_counts": status_counts,
            "query_shape": "two_phase_status_priority",
        }
    # Depth-2 expansion is where semantic drift usually appears. Keep it to
    # verified or very high-confidence edges so a broad co-occurrence chain
    # cannot turn one vague word into a personal-memory flood.
    filtered = [
        row
        for row in rows
        if row["status"] == "verified" or float(row["confidence"] or 0.0) >= 0.88
    ]
    return filtered, {
        "rows_returned": len(filtered),
        "rows_before_depth_filter": len(rows),
        "status_counts": status_counts,
        "query_shape": "two_phase_status_priority",
    }


def edge_rows(
    con: sqlite3.Connection, src_id: str, *, max_degree: int, depth: int
) -> list[sqlite3.Row]:
    rows, _diagnostics = edge_rows_with_diagnostics(
        con, src_id, max_degree=max_degree, depth=depth
    )
    return rows


def expand_concepts_with_diagnostics(
    db_path: Path,
    seed_terms: list[str],
    *,
    depth: int = 2,
    max_degree: int = DEFAULT_MAX_DEGREE,
    max_terms: int = DEFAULT_MAX_TERMS,
    min_score: float = 0.15,
    max_neighbor_fetches: int = DEFAULT_MAX_NEIGHBOR_FETCHES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "schema_version": "concept_expansion_diagnostics_v1",
        "state": "not_attempted",
        "depth_requested": max(0, int(depth)),
        "max_degree": max(1, int(max_degree)),
        "max_terms": max(1, int(max_terms)),
        "max_neighbor_fetches": max(0, int(max_neighbor_fetches)),
        "neighbor_fetches": 0,
        "budget_state": "not_started",
    }
    start = time.perf_counter()
    if not db_path.exists() or depth <= 0:
        diagnostics["state"] = "missing_or_disabled"
        diagnostics["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return [], diagnostics
    try:
        con = sqlite3.connect(db_path, timeout=2)
    except sqlite3.Error as exc:
        diagnostics["state"] = "open_failed"
        diagnostics["error"] = exc.__class__.__name__
        diagnostics["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return [], diagnostics
    con.row_factory = sqlite3.Row
    try:
        seeds = concept_ids_for_terms(con, seed_terms)
        diagnostics["seed_count"] = len(seeds)
        if not seeds:
            diagnostics["state"] = "no_seed_concepts"
            diagnostics["budget_state"] = "within_budget"
            diagnostics["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
            return [], diagnostics
        seed_norms = {concept_normalized(label) for _, label in seeds}
        queue: list[tuple[str, float, int, list[str], list[str]]] = [
            (concept_id, 1.0, 0, [label], []) for concept_id, label in seeds
        ]
        best: dict[str, dict[str, Any]] = {}
        visited: set[tuple[str, int]] = set()
        budget_exceeded = False
        neighbor_fetches_skipped_due_to_budget = 0
        depth_used = 0
        while queue:
            concept_id, score, current_depth, path, edge_types = queue.pop(0)
            if current_depth >= depth:
                continue
            if (concept_id, current_depth) in visited:
                continue
            visited.add((concept_id, current_depth))
            if diagnostics["neighbor_fetches"] >= diagnostics["max_neighbor_fetches"]:
                budget_exceeded = True
                neighbor_fetches_skipped_due_to_budget += 1
                continue
            next_depth = current_depth + 1
            rows, row_diagnostics = edge_rows_with_diagnostics(
                con, concept_id, max_degree=max_degree, depth=next_depth
            )
            diagnostics["neighbor_fetches"] += 1
            diagnostics["last_neighbor_rows"] = row_diagnostics.get("rows_returned", 0)
            depth_used = max(depth_used, next_depth)
            for edge in rows:
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
        expansions = sorted(
            best.values(),
            key=lambda item: (
                -float(item.get("score") or 0.0),
                int(item.get("depth") or 0),
                str(item.get("term") or "").casefold(),
            ),
        )[: max(1, int(max_terms))]
        diagnostics["state"] = "expanded" if expansions else "no_expansions"
        if budget_exceeded and depth_used < int(depth):
            budget_state = "depth_downgraded"
        elif budget_exceeded:
            budget_state = "truncated_by_neighbor_budget"
        else:
            budget_state = "within_budget"
        diagnostics["budget_state"] = budget_state
        diagnostics["depth_used"] = depth_used
        diagnostics["neighbor_fetches_skipped_due_to_budget"] = neighbor_fetches_skipped_due_to_budget
        diagnostics["expansion_count"] = len(expansions)
        diagnostics["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return expansions, diagnostics
    except sqlite3.Error as exc:
        diagnostics["state"] = "query_failed"
        diagnostics["error"] = exc.__class__.__name__
        diagnostics["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return [], diagnostics
    finally:
        con.close()


def expand_concepts(
    db_path: Path,
    seed_terms: list[str],
    *,
    depth: int = 2,
    max_degree: int = DEFAULT_MAX_DEGREE,
    max_terms: int = DEFAULT_MAX_TERMS,
    min_score: float = 0.15,
) -> list[dict[str, Any]]:
    rows, _diagnostics = expand_concepts_with_diagnostics(
        db_path,
        seed_terms,
        depth=depth,
        max_degree=max_degree,
        max_terms=max_terms,
        min_score=min_score,
    )
    return rows


__all__ = [
    "DEFAULT_MAX_DEGREE",
    "DEFAULT_MAX_NEIGHBOR_FETCHES",
    "DEFAULT_MAX_TERMS",
    "concept_ids_for_terms",
    "edge_query_plan",
    "edge_rows",
    "edge_rows_with_diagnostics",
    "expand_concepts",
    "expand_concepts_with_diagnostics",
]
