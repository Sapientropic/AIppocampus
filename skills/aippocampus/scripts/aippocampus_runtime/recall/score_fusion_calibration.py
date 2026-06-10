"""Public-safe score-fusion calibration fixtures for #309.

The report measures post-source-join ranking pressure without serializing
candidate text or source refs, so score components remain navigation hints.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

PUBLIC_CALIBRATION_KIND = "aippocampus_public_score_fusion_calibration"


def _public_calibration_ref(case_id: str, line: int) -> dict[str, Any]:
    return {
        "thread_key": "public-score-fusion-calibration",
        "message_id": case_id,
        "source_line": line,
    }


def _rank_for_source(ranked: Sequence[Mapping[str, Any]], source_id: str) -> int | None:
    for index, row in enumerate(ranked, start=1):
        if row.get("source_id") == source_id:
            return index
    return None


def _public_case_row(
    case: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    safe_float_fn: Callable[[Any], float],
) -> dict[str, Any]:
    ranked = [row for row in payload.get("ranked") or [] if isinstance(row, Mapping)]
    top = ranked[0] if ranked else {}
    expected_top = str(case.get("expected_top_source_id") or "")
    wrong_stance_source_id = str(case.get("wrong_stance_source_id") or "")
    top_source_id = str(top.get("source_id") or "")
    wrong_stance_rank = _rank_for_source(ranked, wrong_stance_source_id)
    weights = payload.get("weights") if isinstance(payload.get("weights"), Mapping) else {}
    exact_text_guard_applied = bool(
        isinstance(top.get("score_components"), Mapping)
        and "exact_text_guard" in top["score_components"]
    )
    vectors_disabled_fallback = bool(
        case.get("vectors_unavailable")
        and top_source_id == expected_top
        and safe_float_fn(weights.get("vector")) == 0.0
    )
    return {
        "case_id": str(case.get("case_id") or "case"),
        "case_family": str(case.get("case_family") or ""),
        "context": str(payload.get("context") or ""),
        "expected_top_source_id": expected_top,
        "top_source_id": top_source_id,
        "top_matches_expected": bool(top_source_id and top_source_id == expected_top),
        "ranked_source_ids": [str(row.get("source_id") or "") for row in ranked],
        "top_score_components": dict(top.get("score_components") or {}),
        "weights": {str(key): safe_float_fn(value) for key, value in weights.items()},
        "skipped_count": len(payload.get("skipped") or []),
        "source_join_gate_reject_count": len(payload.get("skipped") or []),
        "semantic_bridge_lift": bool(case.get("semantic_bridge") and top_source_id == expected_top),
        "wrong_stance_source_id": wrong_stance_source_id,
        "wrong_stance_rank": wrong_stance_rank,
        "wrong_stance_lure_suppressed": bool(
            wrong_stance_source_id and wrong_stance_rank and wrong_stance_rank > 1
        ),
        "wrong_stance_ranked_above_evidence": bool(wrong_stance_rank == 1),
        "exact_text_guard_applied": exact_text_guard_applied,
        "vectors_disabled_fallback": vectors_disabled_fallback,
        "source_reopen_required_for_claims": True,
        "candidate_text_serialized": False,
        "source_refs_serialized": False,
    }


def build_public_score_fusion_calibration_report(
    *,
    blend_fn: Callable[..., Mapping[str, Any]],
    safe_float_fn: Callable[[Any], float],
    schema_version: int,
    now_utc_fn: Callable[[], str],
) -> dict[str, Any]:
    case_defs: list[dict[str, Any]] = [
        {
            "case_id": "exact_quote_guard",
            "case_family": "exact_quote_guard",
            "context": "exact_quote",
            "expected_top_source_id": "public:exact",
            "candidates": [
                {
                    "source_id": "public:exact",
                    "text_score": 100.0,
                    "vector_score": 0.10,
                    "graph_score": 0.05,
                    "source_refs": [_public_calibration_ref("exact", 10)],
                },
                {
                    "source_id": "public:semantic-neighbor",
                    "text_score": 18.0,
                    "vector_score": 1.0,
                    "graph_score": 1.0,
                    "source_refs": [_public_calibration_ref("neighbor", 20)],
                },
            ],
        },
        {
            "case_id": "question_tracking_bridge",
            "case_family": "question_tracking_semantic_bridge",
            "context": "question_tracking",
            "expected_top_source_id": "public:bridge",
            "semantic_bridge": True,
            "candidates": [
                {
                    "source_id": "public:lexical",
                    "text_score": 75.0,
                    "vector_score": 0.10,
                    "source_refs": [_public_calibration_ref("lexical", 30)],
                },
                {
                    "source_id": "public:bridge",
                    "text_score": 30.0,
                    "vector_score": 0.98,
                    "source_refs": [_public_calibration_ref("bridge", 40)],
                },
            ],
        },
        {
            "case_id": "wrong_stance_lure",
            "case_family": "wrong_stance_vector_lure",
            "context": "normal_recall",
            "expected_top_source_id": "public:current",
            "wrong_stance_source_id": "public:wrong-stance",
            "candidates": [
                {
                    "source_id": "public:current",
                    "text_score": 70.0,
                    "vector_score": 0.72,
                    "source_refs": [_public_calibration_ref("current", 50)],
                },
                {
                    "source_id": "public:wrong-stance",
                    "text_score": 15.0,
                    "vector_score": 1.0,
                    "source_refs": [_public_calibration_ref("wrong-stance", 60)],
                },
            ],
        },
        {
            "case_id": "vector_unavailable_fallback",
            "case_family": "vector_unavailable_fallback",
            "context": "question_tracking",
            "expected_top_source_id": "public:text",
            "vectors_unavailable": True,
            "candidates": [
                {
                    "source_id": "public:text",
                    "text_score": 75.0,
                    "vector_score": 0.10,
                    "source_refs": [_public_calibration_ref("fallback-text", 70)],
                },
                {
                    "source_id": "public:bridge",
                    "text_score": 30.0,
                    "vector_score": 0.98,
                    "source_refs": [_public_calibration_ref("fallback-bridge", 80)],
                },
            ],
        },
        {
            "case_id": "source_join_gate",
            "case_family": "missing_source_join_gate",
            "context": "question_tracking",
            "expected_top_source_id": "public:safe",
            "candidates": [
                {"score_kind": "vector", "score": 1.0},
                {
                    "source_id": "public:safe",
                    "text_score": 5.0,
                    "vector_score": 0.2,
                    "source_refs": [_public_calibration_ref("safe", 90)],
                },
            ],
        },
    ]

    cases: list[dict[str, Any]] = []
    for case in case_defs:
        payload = blend_fn(
            case["candidates"],
            context=str(case.get("context") or "normal_recall"),
            vectors_available=not bool(case.get("vectors_unavailable")),
            limit=5,
        )
        cases.append(_public_case_row(case, payload, safe_float_fn=safe_float_fn))

    case_count = len(cases)
    source_join_gate_reject_count = sum(
        int(row.get("source_join_gate_reject_count") or 0) for row in cases
    )
    semantic_bridge_lift_count = sum(1 for row in cases if row.get("semantic_bridge_lift"))
    wrong_stance_lure_suppressed_count = sum(
        1 for row in cases if row.get("wrong_stance_lure_suppressed")
    )
    wrong_stance_ranked_above_evidence_count = sum(
        1 for row in cases if row.get("wrong_stance_ranked_above_evidence")
    )
    vectors_disabled_fallback_count = sum(
        1 for row in cases if row.get("vectors_disabled_fallback")
    )
    exact_text_guard_preserved_count = sum(
        1 for row in cases if row.get("exact_text_guard_applied")
    )
    expected_top_match_count = sum(1 for row in cases if row.get("top_matches_expected"))
    metrics = {
        "case_count": case_count,
        "expected_top_match_count": expected_top_match_count,
        "expected_top_match_rate": round(expected_top_match_count / case_count, 3)
        if case_count
        else 0.0,
        "semantic_bridge_lift_count": semantic_bridge_lift_count,
        "wrong_stance_lure_suppressed_count": wrong_stance_lure_suppressed_count,
        "wrong_stance_ranked_above_evidence_count": wrong_stance_ranked_above_evidence_count,
        "vectors_disabled_fallback_count": vectors_disabled_fallback_count,
        "source_join_gate_reject_count": source_join_gate_reject_count,
        "exact_text_guard_preserved_count": exact_text_guard_preserved_count,
        "ranking_scores_as_truth_claim_count": 0,
    }
    return {
        "schema_version": schema_version,
        "kind": PUBLIC_CALIBRATION_KIND,
        "created_at": now_utc_fn(),
        "ok": bool(
            expected_top_match_count == case_count
            and wrong_stance_ranked_above_evidence_count == 0
            and source_join_gate_reject_count >= 1
        ),
        "config": {
            "fixture": "public_synthetic_score_fusion",
            "default_vector_prefilter_enabled": False,
            "local_embedding_adapter_enabled": False,
            "external_model_calls": False,
            "live_retrieval_path": False,
        },
        "metrics": metrics,
        "cases": cases,
        "issue_readouts": {
            "github_309": {
                "score_fusion_calibration_measured": True,
                "case_count": case_count,
                "semantic_bridge_lift_count": semantic_bridge_lift_count,
                "wrong_stance_lure_suppressed_count": (
                    wrong_stance_lure_suppressed_count
                ),
                "wrong_stance_ranked_above_evidence_count": (
                    wrong_stance_ranked_above_evidence_count
                ),
                "source_join_gate_reject_count": source_join_gate_reject_count,
                "vectors_disabled_fallback_count": vectors_disabled_fallback_count,
                "default_vector_prefilter_enabled": False,
                "local_embedding_adapter_enabled": False,
                "live_score_fusion_quality": "not_measured",
                "closeout_eligible": False,
            }
        },
        "metric_notes": {
            "semantic_bridge_lift_count": (
                "Synthetic cases where question-tracking weights allow a "
                "source-joined semantic neighbor to outrank a weaker lexical "
                "candidate. This is navigation lift, not source evidence."
            ),
            "wrong_stance_lure_suppressed_count": (
                "Synthetic cases where a high-vector wrong-stance lure does "
                "not outrank the stronger current source under normal recall."
            ),
            "vectors_disabled_fallback_count": (
                "Cases where vector weights are explicitly disabled and the "
                "text fallback remains usable."
            ),
        },
        "policy_boundary": {
            "scores_are_ranking_hints_only": True,
            "source_join_gate_required": True,
            "source_reopen_required_for_claims": True,
            "candidate_pool_is_not_evidence": True,
            "default_vector_prefilter_not_enabled": True,
            "local_embedding_adapter_not_enabled": True,
            "cannot_claim_live_answer_quality": True,
            "cannot_claim_default_vector_safety": True,
        },
        "privacy": {
            "raw_source_refs_serialized": False,
            "raw_candidate_text_serialized": False,
            "absolute_paths_serialized": False,
            "fixture_contains_private_user_data": False,
        },
    }
