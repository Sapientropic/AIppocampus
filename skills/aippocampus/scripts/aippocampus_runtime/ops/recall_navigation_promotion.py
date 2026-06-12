"""Promotion harness for recall-navigation features.

This module turns the existing recall-navigation comparison into a reusable
promotion contract. It deliberately evaluates arms under the same public-safe
fixture corpus, query set, packet budget, and deepen budget before any router,
macro, or semantic-navigation feature may be described as default-ready.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.ops import recall_navigation_comparison_fixtures
from aippocampus_runtime.ops.recall_navigation_comparison import ARM_ATTENTION_NAV
from aippocampus_runtime.ops.recall_navigation_macro_fixture import (
    fixture_macro_navigation_cases,
    macro_navigation_readout,
)
from aippocampus_runtime.recall.continuity_usefulness import continuity_usefulness_metrics

PROMOTION_KIND = "aippocampus_recall_navigation_promotion_harness"
PROMOTION_SCHEMA_VERSION = 1
ARM_BASELINE = "baseline_flat_recall"
ARM_NAV_ONLY = "feature_navigation_only"
ARM_PLUS_DEEPEN = "feature_plus_deepen"
PROMOTION_ARMS = (ARM_BASELINE, ARM_NAV_ONLY, ARM_PLUS_DEEPEN)
PACKET_BUDGET = 5
DEEPEN_BUDGET = 5
DISTRACTOR_FAMILIES = ("stale", "conflict", "noise", "wrong_source")
RED_LINE_KEYS = (
    "privacy_bypass_count",
    "masked_source_resurrection_count",
    "claim_without_source_reopen_count",
    "stale_as_current_count",
)
SUMMARY_METRIC_NAMES = (
    "feature_hurt_case_count feature_noop_case_count manual_search_fallback_count "
    "wrong_source_route_count foreground_packet_bytes correct_but_useless_warning_count "
    "route_family_selected_before_manual_search_count known_alias_cross_language_activation_count "
    "macro_prior_applied_count macro_active_layer_order_delta_count "
    "macro_hamming_fanout_delta_count macro_momentum_recheck_diagnostic_count"
).split()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _packet_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(dict(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _blank_red_lines() -> dict[str, int]:
    return {key: 0 for key in RED_LINE_KEYS}


def _arm_row(
    *,
    source_backed_success: bool,
    route_actionable: bool,
    source_reopen_attempted: bool,
    source_reopen_follow_through: bool,
    manual_search_fallback_count: int = 0,
    wrong_source_route_count: int = 0,
    wrong_route_drag_count: int = 0,
    foreground_packet_bytes: int = 0,
    correct_but_useless_warning_count: int = 0,
    selected_next_tool: str = "",
    expected_fail_closed: bool = False,
    failure_class: str = "",
    selected_route_family: str = "",
    route_family_selected_before_manual_search: bool = False,
    known_alias_cross_language_activation: bool = False,
) -> dict[str, Any]:
    return {
        "source_backed_success": source_backed_success,
        "route_actionable": route_actionable,
        "source_reopen_attempted": source_reopen_attempted,
        "source_reopen_follow_through": source_reopen_follow_through,
        "manual_search_fallback_count": manual_search_fallback_count,
        "wrong_source_route_count": wrong_source_route_count,
        "wrong_route_drag_count": wrong_route_drag_count,
        "foreground_packet_bytes": foreground_packet_bytes,
        "correct_but_useless_warning_count": correct_but_useless_warning_count,
        "selected_next_tool": selected_next_tool,
        "expected_fail_closed": expected_fail_closed,
        "failure_class": failure_class,
        "selected_route_family": selected_route_family,
        "route_family_selected_before_manual_search": route_family_selected_before_manual_search,
        "known_alias_cross_language_activation": known_alias_cross_language_activation,
        **_blank_red_lines(),
    }


def _derived_case(row: Mapping[str, Any]) -> dict[str, Any]:
    arms = _as_dict(row.get("arms"))
    direct = _as_dict(arms.get("direct_search"))
    attention = _as_dict(arms.get(ARM_ATTENTION_NAV))
    progressive = _as_dict(arms.get("progressive_recall"))
    case_id = str(row.get("case_id") or "")
    family = str(row.get("case_family") or "unspecified")
    expected_fail_closed = bool(progressive.get("expected_fail_closed"))
    nav_payload = {
        "case_id": case_id,
        "route_count": attention.get("route_count"),
        "attention_route_packet_count": attention.get("attention_route_packet_count"),
        "selected_next_tool": attention.get("selected_next_tool"),
        "selected_route_family": attention.get("selected_route_family"),
    }
    nav_actionable = bool(attention.get("route_actionable"))
    nav_warning = _int(attention.get("correct_but_useless_warning_count"))
    plus_success = bool(progressive.get("source_backed_success"))
    baseline_success = bool(direct.get("source_backed_success"))
    manual_count = _int(direct.get("manual_query_invention_count"))
    wrong_drag = _int(progressive.get("wrong_route_drag_count"))
    outcome = "feature_win"
    if family == "stale_or_irrelevant_route" or wrong_drag:
        outcome = "feature_hurt"
    elif baseline_success and plus_success and manual_count <= 1:
        outcome = "feature_noop"
    return {
        "case_id": case_id,
        "case_family": family,
        "expected_behavior": str(row.get("expected_behavior") or ""),
        "promotion_outcome": outcome,
        "arms": {
            ARM_BASELINE: _arm_row(
                source_backed_success=baseline_success,
                route_actionable=bool(direct.get("route_actionable")),
                source_reopen_attempted=False,
                source_reopen_follow_through=False,
                manual_search_fallback_count=manual_count,
                foreground_packet_bytes=_int(direct.get("input_token_proxy")) * 8,
                selected_next_tool="search_memory" if baseline_success else "",
            ),
            ARM_NAV_ONLY: _arm_row(
                source_backed_success=False,
                route_actionable=nav_actionable,
                source_reopen_attempted=False,
                source_reopen_follow_through=False,
                wrong_route_drag_count=_int(attention.get("wrong_route_drag_count")),
                foreground_packet_bytes=_int(attention.get("foreground_packet_bytes"))
                or _packet_bytes(nav_payload),
                correct_but_useless_warning_count=nav_warning,
                selected_next_tool=str(attention.get("selected_next_tool") or ""),
                expected_fail_closed=False,
                failure_class=str(attention.get("failure_class") or ""),
                selected_route_family=str(attention.get("selected_route_family") or ""),
                route_family_selected_before_manual_search=bool(
                    attention.get("route_family_selected_before_manual_search")
                ),
                known_alias_cross_language_activation=bool(
                    attention.get("known_alias_cross_language_activation")
                ),
            ),
            ARM_PLUS_DEEPEN: _arm_row(
                source_backed_success=plus_success,
                route_actionable=nav_actionable,
                source_reopen_attempted=bool(progressive.get("source_reopen_attempted")),
                source_reopen_follow_through=bool(
                    progressive.get("source_reopen_follow_through")
                ),
                wrong_route_drag_count=wrong_drag,
                foreground_packet_bytes=_packet_bytes(
                    {
                        **nav_payload,
                        "deepen_source_ref_count": progressive.get(
                            "deepen_source_ref_count"
                        ),
                    }
                ),
                selected_next_tool=str(progressive.get("selected_next_tool") or ""),
                expected_fail_closed=expected_fail_closed,
                failure_class=str(progressive.get("failure_class") or ""),
            ),
        },
    }


def _fixture_distractor_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "wrong_source_distractor",
            "case_family": "wrong_source",
            "expected_behavior": (
                "Navigation-only may surface a tempting wrong route, but deepen must "
                "land on the expected source before any claim."
            ),
            "promotion_outcome": "feature_win",
            "arms": {
                ARM_BASELINE: _arm_row(
                    source_backed_success=True,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    manual_search_fallback_count=2,
                    foreground_packet_bytes=112,
                    selected_next_tool="search_memory",
                ),
                ARM_NAV_ONLY: _arm_row(
                    source_backed_success=False,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    wrong_source_route_count=1,
                    foreground_packet_bytes=236,
                    correct_but_useless_warning_count=1,
                    selected_next_tool="recall_deepen",
                ),
                ARM_PLUS_DEEPEN: _arm_row(
                    source_backed_success=True,
                    route_actionable=True,
                    source_reopen_attempted=True,
                    source_reopen_follow_through=True,
                    foreground_packet_bytes=284,
                    selected_next_tool="recall_deepen",
                ),
            },
        },
        {
            "case_id": "conflict_currentness_distractor",
            "case_family": "conflict",
            "expected_behavior": "Conflict/currentness cases require deepen before answer use.",
            "promotion_outcome": "feature_win",
            "arms": {
                ARM_BASELINE: _arm_row(
                    source_backed_success=True,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    manual_search_fallback_count=2,
                    foreground_packet_bytes=120,
                    selected_next_tool="search_memory",
                ),
                ARM_NAV_ONLY: _arm_row(
                    source_backed_success=False,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    foreground_packet_bytes=218,
                    correct_but_useless_warning_count=1,
                    selected_next_tool="recall_deepen",
                ),
                ARM_PLUS_DEEPEN: _arm_row(
                    source_backed_success=True,
                    route_actionable=True,
                    source_reopen_attempted=True,
                    source_reopen_follow_through=True,
                    foreground_packet_bytes=266,
                    selected_next_tool="recall_deepen",
                ),
            },
        },
        {
            "case_id": "noise_suppression_distractor",
            "case_family": "noise",
            "expected_behavior": "Noise should stay quiet; a busy navigation packet is a hurt case.",
            "promotion_outcome": "feature_hurt",
            "arms": {
                ARM_BASELINE: _arm_row(
                    source_backed_success=False,
                    route_actionable=False,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    manual_search_fallback_count=1,
                    foreground_packet_bytes=40,
                ),
                ARM_NAV_ONLY: _arm_row(
                    source_backed_success=False,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    wrong_route_drag_count=1,
                    foreground_packet_bytes=230,
                    correct_but_useless_warning_count=1,
                    selected_next_tool="recall_deepen",
                ),
                ARM_PLUS_DEEPEN: _arm_row(
                    source_backed_success=False,
                    route_actionable=True,
                    source_reopen_attempted=True,
                    source_reopen_follow_through=False,
                    wrong_route_drag_count=1,
                    foreground_packet_bytes=272,
                    selected_next_tool="recall_deepen",
                    expected_fail_closed=True,
                    failure_class="noise_rejected_before_source_use",
                ),
            },
        },
        {
            "case_id": "exact_query_noop_control",
            "case_family": "positive_noop",
            "expected_behavior": "Exact query cases should be reported as no-op, not hidden wins.",
            "promotion_outcome": "feature_noop",
            "arms": {
                ARM_BASELINE: _arm_row(
                    source_backed_success=True,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    manual_search_fallback_count=1,
                    foreground_packet_bytes=80,
                    selected_next_tool="search_memory",
                ),
                ARM_NAV_ONLY: _arm_row(
                    source_backed_success=False,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    foreground_packet_bytes=180,
                    correct_but_useless_warning_count=1,
                    selected_next_tool="recall_deepen",
                ),
                ARM_PLUS_DEEPEN: _arm_row(
                    source_backed_success=True,
                    route_actionable=True,
                    source_reopen_attempted=True,
                    source_reopen_follow_through=True,
                    foreground_packet_bytes=220,
                    selected_next_tool="recall_deepen",
                ),
            },
        },
    ]


def _case_rows(comparison_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return (
        [_derived_case(row) for row in _as_list(comparison_report.get("cases"))]
        + _fixture_distractor_cases()
        + fixture_macro_navigation_cases(
            arm_baseline=ARM_BASELINE,
            arm_nav_only=ARM_NAV_ONLY,
            arm_plus_deepen=ARM_PLUS_DEEPEN,
        )
    )


def _aggregate_metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    metrics = {
        "case_count": len(cases),
        "feature_hurt_case_count": 0,
        "feature_noop_case_count": 0,
        "manual_search_fallback_count": 0,
        "feature_manual_search_fallback_count": 0,
        "wrong_source_route_count": 0,
        "wrong_route_drag_count": 0,
        "foreground_packet_bytes": 0,
        "correct_but_useless_warning_count": 0,
        "route_family_selected_before_manual_search_count": 0,
        "known_alias_cross_language_activation_count": 0,
        "macro_prior_applied_count": 0,
        "macro_active_layer_order_delta_count": 0,
        "macro_hamming_fanout_delta_count": 0,
        "macro_momentum_recheck_diagnostic_count": 0,
        **_blank_red_lines(),
    }
    for case in cases:
        outcome = str(case.get("promotion_outcome") or "")
        metrics["feature_hurt_case_count"] += int(outcome == "feature_hurt")
        metrics["feature_noop_case_count"] += int(outcome == "feature_noop")
        arms = _as_dict(case.get("arms"))
        for arm_name in PROMOTION_ARMS:
            arm = _as_dict(arms.get(arm_name))
            manual = _int(arm.get("manual_search_fallback_count"))
            metrics["manual_search_fallback_count"] += manual
            if arm_name != ARM_BASELINE:
                metrics["feature_manual_search_fallback_count"] += manual
            metrics["wrong_source_route_count"] += _int(arm.get("wrong_source_route_count"))
            metrics["wrong_route_drag_count"] += _int(arm.get("wrong_route_drag_count"))
            metrics["foreground_packet_bytes"] += _int(arm.get("foreground_packet_bytes"))
            metrics["correct_but_useless_warning_count"] += _int(
                arm.get("correct_but_useless_warning_count")
            )
            metrics["route_family_selected_before_manual_search_count"] += int(
                bool(arm.get("route_family_selected_before_manual_search"))
            )
            metrics["known_alias_cross_language_activation_count"] += int(
                bool(arm.get("known_alias_cross_language_activation"))
            )
            metrics["macro_prior_applied_count"] += int(bool(arm.get("macro_prior_applied")))
            metrics["macro_active_layer_order_delta_count"] += int(
                bool(arm.get("macro_active_layer_order_changed"))
            )
            metrics["macro_hamming_fanout_delta_count"] += int(
                bool(arm.get("macro_hamming_fanout_delta"))
            )
            metrics["macro_momentum_recheck_diagnostic_count"] += int(
                bool(arm.get("macro_momentum_recheck_diagnostic"))
            )
            for key in RED_LINE_KEYS:
                metrics[key] += _int(arm.get(key))
    return metrics


def _fixture_coverage(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    family_counts = Counter(str(case.get("case_family") or "unspecified") for case in cases)
    present = [
        family
        for family in DISTRACTOR_FAMILIES
        if family in family_counts
        or (family == "stale" and family_counts.get("stale_or_irrelevant_route"))
    ]
    return {
        "case_family_counts": dict(sorted(family_counts.items())),
        "distractor_families_required": list(DISTRACTOR_FAMILIES),
        "distractor_families_present": present,
        "single_public_safe_fixture_suite": True,
    }


def _usefulness(metrics: Mapping[str, Any], cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    success_count = sum(
        1
        for case in cases
        if _as_dict(_as_dict(case.get("arms")).get(ARM_PLUS_DEEPEN)).get(
            "source_backed_success"
        )
    )
    return continuity_usefulness_metrics(
        {
            "packet_count": len(cases),
            "useful_packet_count": success_count,
            "manual_query_invention_count": metrics["feature_manual_search_fallback_count"],
            "blind_deepen_required_count": metrics["correct_but_useless_warning_count"],
            "wrong_route_drag_count": metrics["wrong_route_drag_count"],
            "safe_route_evidence_present_count": success_count,
            "copy_pasteable_deepen_target_present_count": success_count,
            "recall_to_source_reopen_success_count": success_count,
            "recall_to_source_reopen_attempt_count": sum(
                1
                for case in cases
                if _as_dict(_as_dict(case.get("arms")).get(ARM_PLUS_DEEPEN)).get(
                    "source_reopen_attempted"
                )
            ),
            "foreground_protocol_noise_bytes": metrics["foreground_packet_bytes"],
            "useful_guidance_bytes": success_count * 120,
            "time_to_first_useful_packet_ms_proxy": 250,
            "red_line_counts": {key: metrics[key] for key in RED_LINE_KEYS},
        }
    )


def _promotion_blockers(
    metrics: Mapping[str, Any],
    coverage: Mapping[str, Any],
    usefulness: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if any(_int(metrics.get(key)) for key in RED_LINE_KEYS):
        blockers.append("safety_red_line_present")
    if _int(metrics.get("feature_hurt_case_count")):
        blockers.append("feature_hurt_cases_present")
    if _int(metrics.get("feature_noop_case_count")):
        blockers.append("feature_noop_cases_present")
    if set(coverage.get("distractor_families_present") or []) != set(DISTRACTOR_FAMILIES):
        blockers.append("distractor_coverage_incomplete")
    if not usefulness.get("quality_gate_ok"):
        blockers.append("usefulness_gate_not_satisfied")
    blockers.append("fixture_only_not_live_default_path")
    return blockers


def build_recall_navigation_promotion_report(
    comparison_report: Mapping[str, Any],
) -> dict[str, Any]:
    cases = _case_rows(comparison_report)
    metrics = _aggregate_metrics(cases)
    coverage = _fixture_coverage(cases)
    usefulness = _usefulness(metrics, cases)
    blockers = _promotion_blockers(metrics, coverage, usefulness)
    macro_readout = macro_navigation_readout(
        cases,
        arm_baseline=ARM_BASELINE,
        arm_nav_only=ARM_NAV_ONLY,
    )
    promotion_gate_ok = not blockers
    return {
        "kind": PROMOTION_KIND,
        "schema_version": PROMOTION_SCHEMA_VERSION,
        "ok": True,
        "promotion_gate_ok": promotion_gate_ok,
        "default_adoption_allowed": promotion_gate_ok,
        "promotion_decision": "promoted" if promotion_gate_ok else "not_promoted",
        "promotion_blockers": blockers,
        "preregistration": {
            "arms": list(PROMOTION_ARMS),
            "same_source_corpus": True,
            "same_query_set": True,
            "single_variable_feature_delta": True,
            "packet_budget_per_arm": PACKET_BUDGET,
            "deepen_budget_per_arm": DEEPEN_BUDGET,
            "red_lines_must_stay_zero": list(RED_LINE_KEYS),
        },
        "feature_slots": {
            "attention_router": {
                "status": "candidate",
                "promotion_issue": "#1301",
                "uses_this_harness_before_default": True,
                "comparison_arm": ARM_ATTENTION_NAV,
            },
            "macro_navigation": {
                "status": "candidate",
                "promotion_issue": "#1300",
                "uses_this_harness_before_default": True,
            },
        },
        "cases": cases,
        "cases_by_id": {str(case["case_id"]): case for case in cases},
        "promotion_metrics": metrics,
        "usefulness_metrics": usefulness,
        "attention_router_readout": {
            **_as_dict(comparison_report.get("attention_router_activation")),
            "comparison_arm": ARM_ATTENTION_NAV,
        },
        "macro_navigation_readout": macro_readout,
        "fixture_coverage": coverage,
        "comparison_source": {
            "kind": comparison_report.get("kind"),
            "schema_version": comparison_report.get("schema_version"),
            "deterministic_proxy_only": True,
        },
        "boundary": {
            "public_safe_fixture_only": True,
            "no_private_history": True,
            "no_external_model_calls": True,
            "navigation_only_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
            "not_default_adoption_evidence": not promotion_gate_ok,
        },
        "cannot_claim": [
            "live_default_behavior_lift",
            "private_history_quality",
            "answer_generation_quality",
            "macro_or_router_default_ready",
        ],
    }


def fixture_recall_navigation_promotion_report() -> dict[str, Any]:
    return build_recall_navigation_promotion_report(
        recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
    )


def public_smoke_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the public CLI projection without per-case fixture rows.

    Full case rows stay available to tests and internal callers. The smoke
    command prints only a constant-shaped promotion receipt so it cannot become
    a raw fixture dump if future comparison cases grow more realistic.
    """

    promotion_gate_ok = bool(report.get("promotion_gate_ok"))
    default_allowed = bool(report.get("default_adoption_allowed"))
    macro_readout = _as_dict(report.get("macro_navigation_readout"))
    return {
        "kind": PROMOTION_KIND,
        "schema_version": PROMOTION_SCHEMA_VERSION,
        "ok": bool(report.get("ok")),
        "promotion_gate_ok": promotion_gate_ok,
        "default_adoption_allowed": default_allowed,
        "promotion_decision": "promoted" if promotion_gate_ok else "not_promoted",
        "promotion_blocker_count": len(list(report.get("promotion_blockers") or [])),
        "preregistration": {
            "arms": list(PROMOTION_ARMS),
            "same_source_corpus": True,
            "same_query_set": True,
            "single_variable_feature_delta": True,
            "packet_budget_per_arm": PACKET_BUDGET,
            "deepen_budget_per_arm": DEEPEN_BUDGET,
            "red_line_count": len(RED_LINE_KEYS),
        },
        "feature_slots": {
            "attention_router": {
                "uses_this_harness_before_default": True,
                "comparison_arm": ARM_ATTENTION_NAV,
            },
            "macro_navigation": {"uses_this_harness_before_default": True},
        },
        "summary_metric_names": list(SUMMARY_METRIC_NAMES),
        "macro_navigation_readout": {
            "measured": bool(macro_readout.get("measured")),
            "status": str(macro_readout.get("status") or ""),
            "promotion_issue": str(macro_readout.get("promotion_issue") or "#1300"),
            "active_layer_order_delta_count": _int(
                macro_readout.get("active_layer_order_delta_count")
            ),
            "hamming_fanout_delta_count": _int(
                macro_readout.get("hamming_fanout_delta_count")
            ),
            "momentum_recheck_diagnostic_count": _int(
                macro_readout.get("momentum_recheck_diagnostic_count")
            ),
        },
        "distractor_families_required": list(DISTRACTOR_FAMILIES),
        "boundary": {
            "public_safe_fixture_only": True,
            "no_private_history": True,
            "no_external_model_calls": True,
            "navigation_only_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
        },
        "cannot_claim_count": 4,
    }


def fixture_recall_navigation_promotion_summary() -> dict[str, Any]:
    return public_smoke_summary(fixture_recall_navigation_promotion_report())


def render_text(report: Mapping[str, Any]) -> str:
    metrics = _as_dict(report.get("promotion_metrics"))
    return (
        "AIppocampus recall navigation promotion harness\n"
        f"- Promotion: {report.get('promotion_decision')}\n"
        f"- Cases: {metrics.get('case_count', 0)}\n"
        f"- Feature hurt cases: {metrics.get('feature_hurt_case_count', 0)}\n"
        f"- Feature no-op cases: {metrics.get('feature_noop_case_count', 0)}\n"
        f"- Manual-search fallback count: {metrics.get('manual_search_fallback_count', 0)}\n"
        f"- Correct-but-useless warnings: "
        f"{metrics.get('correct_but_useless_warning_count', 0)}\n"
        "- Boundary: public fixture only; source reopen remains required.\n"
    )
