"""Selected source-evidence Track B summary helpers."""

from __future__ import annotations

from typing import Any

from .reporting import claim_boundary, query_origin


def summarize_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "selected_source_evidence_recall_eval",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "claim_level": payload.get("claim_level"),
        "case_count": int(payload.get("case_count") or 0),
        "passed_count": int(payload.get("passed_count") or 0),
        "failed_count": int(payload.get("failed_count") or 0),
        "top_k": int(payload.get("top_k") or 0),
        "top_k_hit_rate": float(payload.get("top_k_hit_rate") or 0.0),
        "rate_estimates": payload.get("rate_estimates") or {},
        "min_cases": int(payload.get("min_cases") or 0),
        "min_hit_rate": float(payload.get("min_hit_rate") or 0.0),
        "label_coverage": payload.get("label_coverage") or [],
        "warning_count": int(payload.get("warning_count") or 0),
        "ranking": payload.get("ranking"),
        "prompt_kind": payload.get("prompt_kind"),
        "selection": payload.get("selection") or {},
        "selection_explanation": payload.get("selection_explanation") or {},
        "failure_diagnostics": payload.get("failure_diagnostics") or {},
        "cannot_claim": payload.get("cannot_claim") or [],
        "query_origin": query_origin(
            "source_derived_sparse",
            query_author="selected source-evidence evaluator",
            notes=(
                "Selected cases are built from source-backed rows and semantic/source labels; "
                "keep this beside user-like query arms rather than merging claims."
            ),
        ),
        "claim_boundary": claim_boundary(
            measures="selected_source_evidence_retrieval_sanity",
            can_claim=["selected_source_evidence_retrieval_on_labeled_slice"],
            cannot_claim=[
                "natural_user_query_recall",
                "unbounded_private_history_semantic_recall",
            ],
        ),
    }
