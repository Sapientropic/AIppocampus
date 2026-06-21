"""Macro-orientation fixture helpers for the recall-navigation promotion harness."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.recall import macro_live_recall

ACTIVE_PROMOTION_OWNER_ISSUE = "#2559"
HISTORICAL_MACRO_PROMOTION_ISSUES = ["#1300"]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _packet_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(dict(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _arm_row(
    *,
    source_backed_success: bool,
    route_actionable: bool,
    source_reopen_attempted: bool,
    source_reopen_follow_through: bool,
    manual_search_fallback_count: int = 0,
    foreground_packet_bytes: int = 0,
    correct_but_useless_warning_count: int = 0,
    selected_next_tool: str = "",
    selected_route_family: str = "",
    route_family_selected_before_manual_search: bool = False,
) -> dict[str, Any]:
    return {
        "source_backed_success": source_backed_success,
        "route_actionable": route_actionable,
        "source_reopen_attempted": source_reopen_attempted,
        "source_reopen_follow_through": source_reopen_follow_through,
        "manual_search_fallback_count": manual_search_fallback_count,
        "wrong_source_route_count": 0,
        "wrong_route_drag_count": 0,
        "foreground_packet_bytes": foreground_packet_bytes,
        "correct_but_useless_warning_count": correct_but_useless_warning_count,
        "selected_next_tool": selected_next_tool,
        "expected_fail_closed": False,
        "failure_class": "",
        "selected_route_family": selected_route_family,
        "route_family_selected_before_manual_search": route_family_selected_before_manual_search,
        "privacy_bypass_count": 0,
        "masked_source_resurrection_count": 0,
        "claim_without_source_reopen_count": 0,
        "stale_as_current_count": 0,
    }


def _macro_fixture_routes() -> list[dict[str, Any]]:
    return [
        {
            "route_id": "macro_roadmap",
            "route_label": "roadmap north star product claim direction thesis",
            "route_topic": "roadmap",
            "handle": "handle_roadmap",
        },
        {
            "route_id": "macro_benchmark",
            "route_label": "benchmark evidence fixture quality gate measured result",
            "route_topic": "benchmark",
            "handle": "handle_benchmark",
        },
        {
            "route_id": "macro_issue",
            "route_label": "issue backlog workflow handoff project triage next action",
            "route_topic": "issue",
            "handle": "handle_issue",
        },
    ]


def _macro_context_fixture() -> dict[str, Any]:
    state = macro_state.build_macro_orientation_state(
        project="AIppocampus",
        hexagram="乾",
        changing_lines=(1, 2, 3),
        source_refs=({"source_id": "macro-promotion-fixture"},),
        updated_at="2026-06-11T10:00:00Z",
        active_layer="人",
        momentum={"basis": {"counter_evidence_delta": 0.2}},
    )
    projection = macro_state.latest_project_macro_orientation([state], project="AIppocampus")
    context = macro_live_recall.context_from_projection(projection)
    if context is None:
        raise RuntimeError("macro promotion fixture must produce a current context")
    return context


def _macro_selected_family(routes: Sequence[Mapping[str, Any]]) -> str:
    if not routes:
        return ""
    return macro_live_recall.route_source_family(routes[0])


def fixture_macro_navigation_cases(
    *,
    arm_baseline: str,
    arm_nav_only: str,
    arm_plus_deepen: str,
) -> list[dict[str, Any]]:
    requested_limit = 2
    context = _macro_context_fixture()
    effective_limit = macro_live_recall.effective_route_limit(
        requested_limit=requested_limit,
        context=context,
    )
    routes = _macro_fixture_routes()
    baseline_selected = routes[:requested_limit]
    biased_routes, navigation, _macro_metrics = macro_live_recall.apply_recall_bias(
        query="macro active layer issue workflow",
        routes=[dict(route) for route in routes],
        context=context,
        requested_limit=requested_limit,
        effective_limit=effective_limit,
    )
    baseline_family = _macro_selected_family(baseline_selected)
    macro_family = _macro_selected_family(biased_routes)
    order_changed = bool(macro_family and macro_family != baseline_family)
    fanout_delta = effective_limit != requested_limit
    momentum_recheck = bool(navigation.get("recheck_on"))
    manual_baseline = 2

    nav_only = _arm_row(
        source_backed_success=False,
        route_actionable=True,
        source_reopen_attempted=False,
        source_reopen_follow_through=False,
        foreground_packet_bytes=_packet_bytes(
            {
                "macro_navigation": navigation,
                "selected_route_family": macro_family,
            }
        ),
        correct_but_useless_warning_count=1,
        selected_next_tool="recall_deepen",
        selected_route_family=macro_family,
        route_family_selected_before_manual_search=order_changed,
    )
    nav_only.update(
        {
            "macro_prior_applied": True,
            "macro_active_layer_order_changed": order_changed,
            "macro_hamming_fanout_delta": fanout_delta,
            "macro_momentum_recheck_diagnostic": momentum_recheck,
            "macro_effective_max_routes": effective_limit,
            "macro_requested_max_routes": requested_limit,
        }
    )
    plus_deepen = _arm_row(
        source_backed_success=True,
        route_actionable=True,
        source_reopen_attempted=True,
        source_reopen_follow_through=True,
        foreground_packet_bytes=_packet_bytes(
            {
                "selected_route_family": macro_family,
                "deepen_source_ref_count": 1,
            }
        ),
        selected_next_tool="recall_deepen",
        selected_route_family=macro_family,
        route_family_selected_before_manual_search=order_changed,
    )
    plus_deepen.update(
        {
            "macro_prior_applied": True,
            "macro_active_layer_order_changed": order_changed,
            "macro_hamming_fanout_delta": fanout_delta,
            "macro_momentum_recheck_diagnostic": momentum_recheck,
            "macro_effective_max_routes": effective_limit,
            "macro_requested_max_routes": requested_limit,
        }
    )
    return [
        {
            "case_id": "macro_active_layer_and_fanout_prior",
            "case_family": "macro_navigation",
            "expected_behavior": (
                "Scoped macro state may change navigation order and candidate fanout, "
                "but it remains direction-only until deepen/source reopen."
            ),
            "promotion_outcome": "feature_win",
            "arms": {
                arm_baseline: _arm_row(
                    source_backed_success=True,
                    route_actionable=True,
                    source_reopen_attempted=False,
                    source_reopen_follow_through=False,
                    manual_search_fallback_count=manual_baseline,
                    foreground_packet_bytes=112,
                    selected_next_tool="search_memory",
                    selected_route_family=baseline_family,
                ),
                arm_nav_only: nav_only,
                arm_plus_deepen: plus_deepen,
            },
        }
    ]


def macro_navigation_readout(
    cases: Sequence[Mapping[str, Any]],
    *,
    arm_baseline: str,
    arm_nav_only: str,
) -> dict[str, Any]:
    macro_cases = [
        case
        for case in cases
        if str(case.get("case_family") or "") == "macro_navigation"
    ]
    manual_reductions = 0
    active_layer_delta = 0
    fanout_delta = 0
    momentum_recheck = 0
    stale_as_current = 0
    claim_without_reopen = 0
    wrong_source = 0
    for case in macro_cases:
        arms = _as_dict(case.get("arms"))
        baseline = _as_dict(arms.get(arm_baseline))
        nav_only = _as_dict(arms.get(arm_nav_only))
        if _int(baseline.get("manual_search_fallback_count")) > _int(
            nav_only.get("manual_search_fallback_count")
        ):
            manual_reductions += 1
        active_layer_delta += int(bool(nav_only.get("macro_active_layer_order_changed")))
        fanout_delta += int(bool(nav_only.get("macro_hamming_fanout_delta")))
        momentum_recheck += int(bool(nav_only.get("macro_momentum_recheck_diagnostic")))
        stale_as_current += _int(nav_only.get("stale_as_current_count"))
        claim_without_reopen += _int(nav_only.get("claim_without_source_reopen_count"))
        wrong_source += _int(nav_only.get("wrong_source_route_count"))
    return {
        "measured": bool(macro_cases),
        "status": "fixture_candidate_not_promoted",
        "promotion_issue": ACTIVE_PROMOTION_OWNER_ISSUE,
        "historical_promotion_issues": HISTORICAL_MACRO_PROMOTION_ISSUES,
        "case_count": len(macro_cases),
        "active_layer_order_delta_count": active_layer_delta,
        "hamming_fanout_delta_count": fanout_delta,
        "momentum_recheck_diagnostic_count": momentum_recheck,
        "manual_search_fallback_reduction_count": manual_reductions,
        "wrong_source_route_count": wrong_source,
        "stale_as_current_count": stale_as_current,
        "claim_without_source_reopen_count": claim_without_reopen,
        "boundary": {
            "fixture_only": True,
            "macro_prior_not_evidence": True,
            "default_adoption_requires_promotion_gate": True,
        },
    }


__all__ = ["fixture_macro_navigation_cases", "macro_navigation_readout"]
