#!/usr/bin/env python3
"""Privacy-safe concept graph health diagnostics.

This module is deliberately separate from graph build/query logic. Health
reports are operator diagnostics for deciding whether graph-derived navigation
is trustworthy enough to experiment with; they do not make recall/source claims
and should not grow the hot graph owner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation.concept_graph_schema import connect, init_schema
from aippocampus_runtime.navigation.concept_lifecycle import (
    graph_source_boundary,
    safe_diagnostic_hash,
    safe_edge_type,
)
from aippocampus_runtime.text import is_low_value_cjk_fragment


def _bucket_count(value: int) -> str:
    count = int(value or 0)
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 3:
        return "2-3"
    if count <= 7:
        return "4-7"
    return "8+"


def _public_scope_key(value: Any) -> str:
    text = str(value or "unknown").strip() or "unknown"
    if text in {"global", "unknown"}:
        return text
    return safe_diagnostic_hash(text)


def _group_counts(con: Any, sql: str) -> dict[str, int]:
    rows = con.execute(sql).fetchall()
    return {str(row["value"] or "unknown"): int(row["count"] or 0) for row in rows}


def _scope_distribution(con: Any, table: str) -> dict[str, int]:
    if table not in {"concepts", "concept_edges"}:
        return {}
    rows = con.execute(
        f"SELECT scope_key AS value, COUNT(*) AS count FROM {table} GROUP BY scope_key"
    ).fetchall()
    out: dict[str, int] = {}
    for row in rows:
        key = _public_scope_key(row["value"])
        out[key] = out.get(key, 0) + int(row["count"] or 0)
    return out


def _edge_type_status_counts(con: Any) -> dict[str, dict[str, int]]:
    rows = con.execute(
        """
        SELECT edge_type, status, COUNT(*) AS count
        FROM concept_edges
        GROUP BY edge_type, status
        """
    ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        edge_type = safe_edge_type(row["edge_type"])
        status = str(row["status"] or "unknown")
        out.setdefault(edge_type, {})[status] = int(row["count"] or 0)
    return out


def _edge_confidence_distribution(con: Any, *, limit: int = 80) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT edge_type, ROUND(confidence, 3) AS confidence, COUNT(*) AS count
        FROM concept_edges
        GROUP BY edge_type, ROUND(confidence, 3)
        ORDER BY count DESC, edge_type ASC, confidence DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()
    return [
        {
            "edge_type": safe_edge_type(row["edge_type"]),
            "confidence": float(row["confidence"] or 0.0),
            "count": int(row["count"] or 0),
        }
        for row in rows
    ]


def _quality_buckets(con: Any, column: str) -> dict[str, int]:
    if column not in {"thread_count", "evidence_count"}:
        return {}
    rows = con.execute(f"SELECT {column} AS value, COUNT(*) AS count FROM concept_edges").fetchall()
    out: dict[str, int] = {}
    for row in rows:
        bucket = _bucket_count(int(row["value"] or 0))
        out[bucket] = out.get(bucket, 0) + int(row["count"] or 0)
    return out


def _hub_concentration(con: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT src_concept_id AS concept_id, COUNT(*) AS degree
        FROM concept_edges
        WHERE status IN ('verified', 'staging')
        GROUP BY src_concept_id
        ORDER BY degree DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()
    return [
        {
            "concept_hash": safe_diagnostic_hash(row["concept_id"]),
            "active_out_degree": int(row["degree"] or 0),
        }
        for row in rows
    ]


def _cjk_fragment_indicator(con: Any) -> dict[str, int]:
    rows = con.execute("SELECT label FROM concepts").fetchall()
    fragment_count = 0
    cjk_label_count = 0
    long_cjk_label_count = 0
    for row in rows:
        label = str(row["label"] or "")
        if not any("\u4e00" <= ch <= "\u9fff" for ch in label):
            continue
        cjk_label_count += 1
        cjk_len = sum(1 for ch in label if "\u4e00" <= ch <= "\u9fff")
        if cjk_len >= 8:
            long_cjk_label_count += 1
        if is_low_value_cjk_fragment(label):
            fragment_count += 1
    return {
        "cjk_label_count": cjk_label_count,
        "long_cjk_label_count": long_cjk_label_count,
        "low_value_cjk_fragment_count": fragment_count,
    }


def concept_graph_health(db_path: Path) -> dict[str, Any]:
    """Return bounded, privacy-safe operator diagnostics for graph quality."""

    db_path = Path(db_path)
    if not db_path.exists():
        return {
            "kind": "aippocampus_concept_graph_health",
            "ok": False,
            "status": "missing",
            "recall_useful_claimed": False,
            "source_boundary": graph_source_boundary(),
        }
    con = connect(db_path)
    try:
        init_schema(con)
        concept_count = int(con.execute("SELECT COUNT(*) AS count FROM concepts").fetchone()["count"] or 0)
        edge_count = int(
            con.execute("SELECT COUNT(*) AS count FROM concept_edges").fetchone()["count"] or 0
        )
        edge_counts = _group_counts(
            con,
            "SELECT edge_type AS value, COUNT(*) AS count FROM concept_edges GROUP BY edge_type",
        )
        co_occurs_count = int(edge_counts.get("co_occurs", 0))
        confidence_distribution = _edge_confidence_distribution(con)
        top_co_occurs_confidence = next(
            (
                row
                for row in confidence_distribution
                if row.get("edge_type") == "co_occurs"
            ),
            None,
        )
        global_edge_count = _scope_distribution(con, "concept_edges").get("global", 0)
        warnings: list[dict[str, Any]] = []
        if edge_count and global_edge_count == edge_count:
            warnings.append(
                {
                    "code": "statistical_unit_collapse",
                    "severity": "warning",
                    "message": (
                        "All concept edges use scope_key=global; graph-level rows no "
                        "longer preserve document/window units for phrase statistics."
                    ),
                }
            )
        if edge_count and co_occurs_count / edge_count >= 0.6:
            warnings.append(
                {
                    "code": "co_occurs_dominance",
                    "severity": "warning",
                    "ratio": round(co_occurs_count / edge_count, 4),
                    "message": "Automatic co_occurs edges dominate the graph; treat expansion as navigation-only.",
                }
            )
        if top_co_occurs_confidence and co_occurs_count:
            share = int(top_co_occurs_confidence["count"]) / max(1, co_occurs_count)
            if share >= 0.75:
                warnings.append(
                    {
                        "code": "constant_confidence_co_occurs",
                        "severity": "warning",
                        "confidence": top_co_occurs_confidence["confidence"],
                        "share": round(share, 4),
                        "message": "Most co_occurs rows share one confidence value; do not infer semantic quality from confidence alone.",
                    }
                )
        health_state = (
            "quality_gated_operator_diagnostics"
            if not warnings
            else "operator_only_attention_required"
        )
        return {
            "kind": "aippocampus_concept_graph_health",
            "schema_version": "concept_graph_health_v1",
            "ok": True,
            "status": health_state,
            "concept_count": concept_count,
            "edge_count": edge_count,
            "concept_scope_key_distribution": _scope_distribution(con, "concepts"),
            "edge_scope_key_distribution": _scope_distribution(con, "concept_edges"),
            "edge_type_status_counts": _edge_type_status_counts(con),
            "edge_confidence_distribution_top": confidence_distribution,
            "source_diversity_buckets": _quality_buckets(con, "thread_count"),
            "evidence_count_buckets": _quality_buckets(con, "evidence_count"),
            "hub_concentration_top": _hub_concentration(con),
            "cjk_fragment_indicators": _cjk_fragment_indicator(con),
            "count_semantics": {
                "thread_count": "bounded_source_thread_reference_count_not_raw_df",
                "evidence_count": "bounded_source_reference_or_hit_count_not_raw_df",
                "exact_document_frequency_available": False,
                "clean_source_window_count_available": False,
            },
            "warnings": warnings,
            "recall_useful_claimed": False,
            "source_boundary": graph_source_boundary(),
        }
    finally:
        con.close()


__all__ = ["concept_graph_health"]
