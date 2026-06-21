"""Public projection helpers for the recall-navigation promotion harness."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.ops import recall_navigation_promotion as promotion
from aippocampus_runtime.ops.recall_navigation_comparison import ARM_ATTENTION_NAV

SUMMARY_METRIC_NAMES = (
    "feature_hurt_case_count feature_noop_case_count manual_search_fallback_count "
    "wrong_source_route_count foreground_packet_bytes correct_but_useless_warning_count "
    "route_family_selected_before_manual_search_count known_alias_cross_language_activation_count "
    "attention_router_applied_but_no_help_count zero_overlap_without_bridge_reason_count "
    "route_label_specificity_below_floor_count why_may_matter_not_specific_count "
    "macro_prior_applied_count macro_active_layer_order_delta_count "
    "macro_hamming_fanout_delta_count macro_momentum_recheck_diagnostic_count"
).split()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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
        "kind": promotion.PROMOTION_KIND,
        "schema_version": promotion.PROMOTION_SCHEMA_VERSION,
        "ok": bool(report.get("ok")),
        "promotion_gate_ok": promotion_gate_ok,
        "default_adoption_allowed": default_allowed,
        "promotion_decision": "promoted" if promotion_gate_ok else "not_promoted",
        "promotion_blocker_count": len(list(report.get("promotion_blockers") or [])),
        "preregistration": {
            "arms": list(promotion.PROMOTION_ARMS),
            "same_source_corpus": True,
            "same_query_set": True,
            "single_variable_feature_delta": True,
            "packet_budget_per_arm": promotion.PACKET_BUDGET,
            "deepen_budget_per_arm": promotion.DEEPEN_BUDGET,
            "red_line_count": len(promotion.RED_LINE_KEYS),
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
        "distractor_families_required": list(promotion.DISTRACTOR_FAMILIES),
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
    return public_smoke_summary(promotion.fixture_recall_navigation_promotion_report())
