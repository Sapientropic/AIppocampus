"""H5 consolidation delta projection for hippocampal recall fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from benchmarks.aippocampus.families import hippocampal_fixture_schema as schema
from benchmarks.aippocampus.families.hippocampal_d5_d6_gate import (
    CORRECT_OUTCOMES,
    SEPARATION_FAILURES,
)

H5_BEFORE_ARM = "keyword_only"
H5_CONSOLIDATION_ARMS = (
    "no_consolidation",
    "aippocampus_dream_consolidation",
    "random_consolidation",
    "simple_summary_consolidation",
)
H5_OVERGENERALIZATION_OUTCOMES = {
    "overconfident_evidence",
    "overactive_scent",
    "wrong_twin_selection",
    "confabulation",
}
H5_FALSE_FORGETTING_OUTCOMES = {"unsupported_skip"}

RunAdapterArm = Callable[[Mapping[str, Any], str], dict[str, Any]]
ScoreResponse = Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]
WithAdapterMetadata = Callable[..., dict[str, Any]]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _h5_frozen_label_sha1(case: Mapping[str, Any]) -> str:
    label_payload = {
        "case_id": case.get("case_id"),
        "expected_decision": case.get("expected_decision"),
        "expected_source_refs": _as_list(case.get("expected_source_refs")),
        "acceptable_scent_refs": _as_list(case.get("acceptable_scent_refs")),
        "distractor_source_refs": _as_list(case.get("distractor_source_refs")),
        "ambiguity_policy": case.get("ambiguity_policy"),
        "forbidden_claims": _as_list(case.get("forbidden_claims")),
    }
    return schema.sha1_text(json.dumps(label_payload, sort_keys=True))[:16]


def _h5_consolidation_cost(arm: str, case: Mapping[str, Any]) -> dict[str, Any]:
    expected_decision = str(case.get("expected_decision") or "skip")
    candidate_count = len(_as_list(case.get("candidate_source_refs")))
    if arm == "no_consolidation":
        return {
            "work_units": 0,
            "model_calls": 0,
            "tokens": 0,
            "latency_ms": 0.0,
            "association_edges_created": 0,
            "summary_units": 0,
        }
    if arm == "random_consolidation":
        return {
            "work_units": 1,
            "model_calls": 0,
            "tokens": 0,
            "latency_ms": 0.0,
            "association_edges_created": 1 if candidate_count else 0,
            "summary_units": 0,
        }
    if arm == "simple_summary_consolidation":
        return {
            "work_units": 2,
            "model_calls": 0,
            "tokens": 0,
            "latency_ms": 0.0,
            "association_edges_created": 0,
            "summary_units": 1,
        }
    return {
        "work_units": 4 if expected_decision != "skip" else 2,
        "model_calls": 0,
        "tokens": 0,
        "latency_ms": 0.0,
        "association_edges_created": 1 if expected_decision != "skip" else 0,
        "summary_units": 0,
    }


def _h5_fixture_guided_response(case: Mapping[str, Any]) -> dict[str, Any]:
    """Fixture-authored after arm for delta math, not a live Dream worker score."""

    expected_decision = str(case.get("expected_decision") or "skip")
    expected_refs = _as_list(case.get("expected_source_refs"))
    acceptable_scent_refs = _as_list(case.get("acceptable_scent_refs")) or expected_refs
    if expected_decision == "evidence":
        return {
            "decision": "evidence",
            "confidence": 0.78,
            "evidence_refs": expected_refs[:1],
            "scent_refs": [],
            "source_reopened": bool(expected_refs),
            "claims": [],
        }
    if expected_decision == "scent":
        return {
            "decision": "scent",
            "confidence": 0.58,
            "evidence_refs": [],
            "scent_refs": acceptable_scent_refs[:1],
            "source_reopened": False,
            "claims": [],
        }
    return {
        "decision": "skip",
        "confidence": 0.18,
        "evidence_refs": [],
        "scent_refs": [],
        "source_reopened": False,
        "claims": [],
    }


def _h5_random_response(case: Mapping[str, Any]) -> dict[str, Any]:
    distractor_refs = _as_list(case.get("distractor_source_refs"))
    if distractor_refs:
        return {
            "decision": "evidence",
            "confidence": 0.51,
            "evidence_refs": distractor_refs[:1],
            "scent_refs": [],
            "source_reopened": True,
            "claims": [],
        }
    return {
        "decision": "skip",
        "confidence": 0.08,
        "evidence_refs": [],
        "scent_refs": [],
        "source_reopened": False,
        "claims": [],
    }


def _h5_simple_summary_response(case: Mapping[str, Any]) -> dict[str, Any]:
    refs = _as_list(case.get("candidate_source_refs"))
    if not refs:
        return {
            "decision": "skip",
            "confidence": 0.1,
            "evidence_refs": [],
            "scent_refs": [],
            "source_reopened": False,
            "claims": [],
        }
    return {
        "decision": "scent",
        "confidence": 0.49,
        "evidence_refs": [],
        "scent_refs": refs,
        "source_reopened": False,
        "claims": [],
    }


def _h5_after_response(
    case: Mapping[str, Any],
    arm: str,
    *,
    run_adapter_arm: RunAdapterArm,
    with_adapter_metadata: WithAdapterMetadata,
) -> dict[str, Any]:
    if arm == "no_consolidation":
        response = run_adapter_arm(case, H5_BEFORE_ARM)
    elif arm == "aippocampus_dream_consolidation":
        response = _h5_fixture_guided_response(case)
    elif arm == "random_consolidation":
        response = _h5_random_response(case)
    elif arm == "simple_summary_consolidation":
        response = _h5_simple_summary_response(case)
    else:
        response = {
            "decision": "skip",
            "confidence": 0.0,
            "evidence_refs": [],
            "scent_refs": [],
            "source_reopened": False,
            "claims": [],
        }
    payload = with_adapter_metadata(
        response,
        arm=arm,
        candidate_count=len(_as_list(case.get("candidate_source_refs"))),
    )
    payload["consolidation_cost"] = _h5_consolidation_cost(arm, case)
    return payload


def _h5_score_value(score: Mapping[str, Any]) -> float:
    value = score.get("score")
    return float(value) if isinstance(value, int | float) else 0.0


def _h5_is_separation_failure(score: Mapping[str, Any]) -> bool:
    outcome = str(score.get("outcome") or "")
    return outcome in SEPARATION_FAILURES or bool(score.get("low_separation"))


def _h5_is_overgeneralized(score: Mapping[str, Any]) -> bool:
    outcome = str(score.get("outcome") or "")
    return outcome in H5_OVERGENERALIZATION_OUTCOMES or bool(score.get("low_separation"))


def _h5_is_false_forgetting(
    case: Mapping[str, Any],
    before_score: Mapping[str, Any],
    after_score: Mapping[str, Any],
) -> bool:
    if str(case.get("expected_decision") or "skip") == "skip":
        return False
    return (
        str(before_score.get("outcome") or "") in CORRECT_OUTCOMES
        and str(after_score.get("outcome") or "") in H5_FALSE_FORGETTING_OUTCOMES
    )


def _h5_is_stale_as_current(case: Mapping[str, Any], score: Mapping[str, Any]) -> bool:
    if str(case.get("interference_level") or "") != "I5":
        return False
    return str(score.get("outcome") or "") in {
        "wrong_twin_selection",
        "confabulation",
        "overconfident_evidence",
    }


def _h5_case_delta(
    case: Mapping[str, Any],
    arm: str,
    *,
    run_adapter_arm: RunAdapterArm,
    score_response: ScoreResponse,
    with_adapter_metadata: WithAdapterMetadata,
) -> dict[str, Any]:
    before_response = run_adapter_arm(case, H5_BEFORE_ARM)
    after_response = _h5_after_response(
        case,
        arm,
        run_adapter_arm=run_adapter_arm,
        with_adapter_metadata=with_adapter_metadata,
    )
    before_score = score_response(case, before_response)
    after_score = score_response(case, after_response)
    before_value = _h5_score_value(before_score)
    after_value = _h5_score_value(after_score)
    score_delta = round(after_value - before_value, 6)
    before_separation_failure = _h5_is_separation_failure(before_score)
    after_separation_failure = _h5_is_separation_failure(after_score)
    before_stale = _h5_is_stale_as_current(case, before_score)
    after_stale = _h5_is_stale_as_current(case, after_score)
    before_wrong_twin = str(before_score.get("outcome") or "") == "wrong_twin_selection"
    after_wrong_twin = str(after_score.get("outcome") or "") == "wrong_twin_selection"
    expected_decision = str(case.get("expected_decision") or "skip")
    return {
        "arm": arm,
        "case_id": case.get("case_id"),
        "scene_id": case.get("scene_id"),
        "degradation_level": case.get("degradation_level"),
        "interference_level": case.get("interference_level"),
        "same_case_id_after_rerun": True,
        "truth_relabeling_allowed": False,
        "frozen_expected_decision": expected_decision,
        "frozen_label_sha1": _h5_frozen_label_sha1(case),
        "before_arm": H5_BEFORE_ARM,
        "before_outcome": before_score.get("outcome"),
        "after_outcome": after_score.get("outcome"),
        "before_score": before_value,
        "after_score": after_value,
        "score_delta": score_delta,
        "improved": score_delta > 0,
        "regressed": score_delta < 0,
        "new_association_discovered": (
            expected_decision == "evidence"
            and before_score.get("outcome") != "correct_evidence"
            and after_score.get("outcome") == "correct_evidence"
        ),
        "separation_improved": before_separation_failure and not after_separation_failure,
        "false_forgetting": _h5_is_false_forgetting(case, before_score, after_score),
        "overgeneralization": (
            _h5_is_overgeneralized(after_score)
            and not _h5_is_overgeneralized(before_score)
        ),
        "stale_as_current_before": before_stale,
        "stale_as_current_after": after_stale,
        "wrong_twin_before": before_wrong_twin,
        "wrong_twin_after": after_wrong_twin,
        "consolidation_cost": after_response.get("consolidation_cost") or {},
    }


def _h5_blank_delta_view() -> dict[str, Any]:
    return {
        "case_count": 0,
        "score_delta_total": 0.0,
        "improvement_count": 0,
        "regression_count": 0,
        "new_association_discovery_count": 0,
        "separation_improvement_count": 0,
        "false_forgetting_count": 0,
        "overgeneralization_count": 0,
        "stale_as_current_before_count": 0,
        "stale_as_current_after_count": 0,
        "stale_as_current_delta": 0,
        "wrong_twin_before_count": 0,
        "wrong_twin_after_count": 0,
        "wrong_twin_delta": 0,
    }


def _h5_add_delta(view: dict[str, Any], delta: Mapping[str, Any]) -> None:
    view["case_count"] += 1
    view["score_delta_total"] = round(
        float(view["score_delta_total"]) + float(delta.get("score_delta") or 0.0),
        6,
    )
    count_fields = {
        "improved": "improvement_count",
        "regressed": "regression_count",
        "new_association_discovered": "new_association_discovery_count",
        "separation_improved": "separation_improvement_count",
        "false_forgetting": "false_forgetting_count",
        "overgeneralization": "overgeneralization_count",
        "stale_as_current_before": "stale_as_current_before_count",
        "stale_as_current_after": "stale_as_current_after_count",
        "wrong_twin_before": "wrong_twin_before_count",
        "wrong_twin_after": "wrong_twin_after_count",
    }
    for field, count_field in count_fields.items():
        if bool(delta.get(field)):
            view[count_field] += 1


def _h5_finalize_delta_view(view: dict[str, Any]) -> dict[str, Any]:
    view["average_score_delta"] = _rate(
        int(round(float(view["score_delta_total"]) * 1_000_000)),
        int(view["case_count"]) * 1_000_000,
    )
    view["stale_as_current_delta"] = (
        int(view["stale_as_current_before_count"])
        - int(view["stale_as_current_after_count"])
    )
    view["wrong_twin_delta"] = (
        int(view["wrong_twin_before_count"]) - int(view["wrong_twin_after_count"])
    )
    return view


def _h5_cost_totals(deltas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = {
        "work_units": 0,
        "model_calls": 0,
        "tokens": 0,
        "latency_ms": 0.0,
        "association_edges_created": 0,
        "summary_units": 0,
    }
    for delta in deltas:
        cost = _as_mapping(delta.get("consolidation_cost"))
        for key in (
            "work_units",
            "model_calls",
            "tokens",
            "association_edges_created",
            "summary_units",
        ):
            totals[key] += int(cost.get(key) or 0)
        if isinstance(cost.get("latency_ms"), int | float):
            totals["latency_ms"] += float(cost["latency_ms"])
    totals["latency_ms"] = round(totals["latency_ms"], 6)
    return totals


def _h5_view_for_arm(
    rows: Sequence[Mapping[str, Any]],
    deltas: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_degradation = {level: _h5_blank_delta_view() for level in schema.DEGRADATION_LEVELS}
    by_interference = {level: _h5_blank_delta_view() for level in schema.INTERFERENCE_LEVELS}
    matrix = {
        f"{degradation}/{interference}": _h5_blank_delta_view()
        for degradation in schema.DEGRADATION_LEVELS
        for interference in schema.INTERFERENCE_LEVELS
    }
    aggregate = _h5_blank_delta_view()
    for delta in deltas:
        degradation = str(delta.get("degradation_level") or "")
        interference = str(delta.get("interference_level") or "")
        _h5_add_delta(aggregate, delta)
        if degradation in by_degradation:
            _h5_add_delta(by_degradation[degradation], delta)
        if interference in by_interference:
            _h5_add_delta(by_interference[interference], delta)
        key = f"{degradation}/{interference}"
        if key in matrix:
            _h5_add_delta(matrix[key], delta)

    cost_totals = _h5_cost_totals(deltas)
    aggregate = _h5_finalize_delta_view(aggregate)
    aggregate["cost"] = cost_totals
    improvement_count = int(aggregate["improvement_count"])
    aggregate["cost_per_improvement"] = (
        {
            "work_units": round(cost_totals["work_units"] / improvement_count, 6),
            "model_calls": round(cost_totals["model_calls"] / improvement_count, 6),
            "tokens": round(cost_totals["tokens"] / improvement_count, 6),
            "latency_ms": round(cost_totals["latency_ms"] / improvement_count, 6),
        }
        if improvement_count
        else None
    )
    return {
        "aggregate": aggregate,
        "by_degradation": {
            level: _h5_finalize_delta_view(view)
            for level, view in by_degradation.items()
            if view["case_count"] or any(row.get("degradation_level") == level for row in rows)
        },
        "by_interference": {
            level: _h5_finalize_delta_view(view)
            for level, view in by_interference.items()
            if view["case_count"] or any(row.get("interference_level") == level for row in rows)
        },
        "matrix": {
            key: _h5_finalize_delta_view(view)
            for key, view in matrix.items()
            if view["case_count"]
        },
    }


def h5_consolidation_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_adapter_arm: RunAdapterArm,
    score_response: ScoreResponse,
    with_adapter_metadata: WithAdapterMetadata,
) -> dict[str, Any]:
    case_deltas = [
        _h5_case_delta(
            case,
            arm,
            run_adapter_arm=run_adapter_arm,
            score_response=score_response,
            with_adapter_metadata=with_adapter_metadata,
        )
        for arm in H5_CONSOLIDATION_ARMS
        for case in rows
    ]
    views_by_arm = {
        arm: _h5_view_for_arm(
            rows,
            [delta for delta in case_deltas if delta.get("arm") == arm],
        )
        for arm in H5_CONSOLIDATION_ARMS
    }
    return {
        "version": "aippocampus.h5_consolidation_delta_report.v1",
        "status": "diagnostic_control_slice",
        "source_issue": "https://github.com/Sapientropic/AIppocampus/issues/233",
        "parent_issue": "https://github.com/Sapientropic/AIppocampus/issues/228",
        "before_arm": H5_BEFORE_ARM,
        "arms": list(H5_CONSOLIDATION_ARMS),
        "truth_boundary": {
            "labels_frozen_before_after": True,
            "source_state_frozen_before_after": True,
            "reruns_same_case_ids": True,
            "allows_relabeling_after_consolidation": False,
            "uses_live_dream_worker": False,
            "uses_private_history": False,
        },
        "prospective_validation_boundary": {
            "supported": False,
            "shape_recorded": True,
            "requires_time_sliced_future_source_evidence": True,
            "similar_vocabulary_alone_counts_as_support": False,
        },
        "arm_contracts": {
            "no_consolidation": "same frozen H1/H2 cases rerun with the before arm and no memory-surface change",
            "aippocampus_dream_consolidation": "fixture-authored diagnostic consolidation output; not a live Dream worker score",
            "random_consolidation": "deterministic distractor/skip control standing in for unrelated association creation",
            "simple_summary_consolidation": "summary-scent control that broadens candidates without clean source evidence",
        },
        "views_by_arm": views_by_arm,
        "case_deltas": case_deltas,
        "cannot_claim": [
            "user_visible_dream_benefit",
            "live_dream_worker_quality",
            "predictive_validity",
            "private_real_history_consolidation_quality",
            "aippocampus_specific_lift_without_live_controls",
        ],
    }
