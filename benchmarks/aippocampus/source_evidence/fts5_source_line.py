"""FTS5 source-line Track B summary helpers."""

from __future__ import annotations

from typing import Any

from .reporting import claim_boundary, query_origin, rank_metrics


def sanitize_fts5_case(case: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    raw_fts5 = case.get("fts5")
    fts5: dict[str, Any] = raw_fts5 if isinstance(raw_fts5, dict) else {}
    fts5_rank = fts5.get("rank")
    production = (
        case.get("production_hybrid")
        if isinstance(case.get("production_hybrid"), dict)
        else None
    )
    row: dict[str, Any] = {
        "case_id": case.get("case_id"),
        "case_type": case.get("case_type"),
        "thread_key_sha1": case.get("thread_key_sha1"),
        "clean_source_sha1": case.get("clean_source_sha1"),
        "query_sha1": case.get("query_sha1"),
        "query_terms_count": case.get("query_terms_count"),
        "fts5_rank": fts5_rank,
        f"fts5_hit_top{top_k}": bool(fts5_rank and int(fts5_rank) <= top_k),
        "expected_line_present": fts5.get("expected_line_present"),
    }
    if production is not None:
        row["production_hybrid_rank"] = production.get("rank")
        row[f"production_hybrid_hit_top{top_k}"] = bool(
            production.get("rank") and int(production.get("rank")) <= top_k
        )
    return row

def summarize_fts5_payload(payload: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    cases = [case for case in payload.get("cases") or [] if isinstance(case, dict)]
    thresholds = [1, 3, 5, top_k]
    fts5_metrics = rank_metrics(cases, "fts5", thresholds)
    summary = {
        "kind": payload.get("kind"),
        "ok": bool(payload.get("ok")),
        "total_cases": int((payload.get("metrics") or {}).get("total_cases") or len(cases)),
        "top_k": int(top_k),
        "corpus": payload.get("corpus") or {},
        "case_types": (payload.get("metrics") or {}).get("case_types") or {},
        "hit_top_k": fts5_metrics.get(f"hit_top{top_k}", 0),
        "miss_top_k": fts5_metrics.get(f"miss_top{top_k}", 0),
        "hit_rate_top_k": fts5_metrics.get(f"hit_rate_top{top_k}", 0.0),
        f"hit_rate_top{top_k}": fts5_metrics.get(f"hit_rate_top{top_k}", 0.0),
        "rate_estimates": fts5_metrics.get("rate_estimates") or {},
        "mrr": fts5_metrics.get("mrr", 0.0),
        "fts5": fts5_metrics,
        "miss_categories_top_k": (
            ((payload.get("metrics") or {}).get("fts5") or {}).get("miss_categories_top_k")
            or {}
        ),
        "query_origin": query_origin(
            "source_derived_sparse",
            query_author="benchmark_fts5_recall.query_from_text",
            notes=(
                "Queries are extracted from the expected clean-source message. "
                "This arm is retained as an index-health and stale-SQLite sanity check."
            ),
        ),
        "claim_boundary": claim_boundary(
            measures="index_health_sanity",
            can_claim=[
                "source_derived_source_line_retrieval_sanity",
                "stale_sqlite_detection_signal",
            ],
            cannot_claim=[
                "natural_user_query_recall",
                "semantic_generalized_memory_recall",
                "paraphrase_or_cross_language_recall",
            ],
        ),
        "elapsed_ms": payload.get("elapsed_ms"),
    }
    if any("production_hybrid" in case for case in cases):
        summary["production_hybrid"] = rank_metrics(cases, "production_hybrid", thresholds)
    return summary
