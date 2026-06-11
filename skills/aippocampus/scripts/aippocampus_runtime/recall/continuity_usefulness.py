"""Canonical usefulness gates for foreground continuity packets.

Privacy and claim safety are hard constraints, but they are not the product
goal. This helper keeps the usefulness gate explicit so a packet cannot pass
promotion merely because it leaked nothing while still forcing blind deepen,
manual search, route drag, or protocol-heavy foreground noise.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SAFETY_RED_LINE_KEYS = (
    "privacy_leak_count",
    "unsupported_claim_count",
    "source_backed_claim_without_reopen",
    "stale_as_current_count",
    "masked_source_resurrection_count",
    "deleted_or_no_recall_violation_count",
)

DEFAULT_DISTINCTIVENESS_FLOOR = 0.6
DEFAULT_USEFUL_PACKET_RATE_FLOOR = 0.5
DEFAULT_HOT_PACKET_MS_CEILING = 250
DEFAULT_PROTOCOL_NOISE_RATIO_CEILING = 0.45
ACTION_PERMISSION_LADDER = (
    "silent_or_blocked",
    "scent",
    "route_hint",
    "actionable_route",
    "bounded_context",
    "source_open",
    "claim_ready",
)
ACTION_PERMISSION_RANK = {level: index for index, level in enumerate(ACTION_PERMISSION_LADDER)}
DEFAULT_ROUTE_ACTION_PERMISSION_FLOOR = "actionable_route"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _red_line_total(surface: Mapping[str, Any]) -> int:
    explicit = surface.get("red_line_counts")
    total = 0
    if isinstance(explicit, Mapping):
        total += sum(_int(value) for value in explicit.values())
    for key in SAFETY_RED_LINE_KEYS:
        total += _int(surface.get(key))
    return total


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _action_permission_level(surface: Mapping[str, Any], red_line_total: int) -> str:
    explicit = str(surface.get("action_permission_level") or "").strip()
    if explicit in ACTION_PERMISSION_RANK:
        return explicit
    if red_line_total or surface.get("blocked"):
        return "silent_or_blocked"
    if surface.get("claim_ready"):
        return "claim_ready"
    if surface.get("source_open"):
        return "source_open"
    if surface.get("bounded_context"):
        return "bounded_context"
    if _int(surface.get("safe_route_evidence_present_count")):
        return (
            "actionable_route"
            if _int(surface.get("copy_pasteable_deepen_target_present_count"))
            else "route_hint"
        )
    return "scent"


def _minimum_useful_action_permission_level(surface: Mapping[str, Any]) -> str:
    explicit = str(surface.get("minimum_useful_action_permission_level") or "").strip()
    if explicit in ACTION_PERMISSION_RANK:
        return explicit
    if _int(surface.get("safe_route_evidence_present_count")):
        return DEFAULT_ROUTE_ACTION_PERMISSION_FLOOR
    return "scent"


def _permission_below(actual: str, floor: str) -> bool:
    return ACTION_PERMISSION_RANK.get(actual, 0) < ACTION_PERMISSION_RANK.get(floor, 0)


def continuity_usefulness_metrics(
    surface: Mapping[str, Any],
    *,
    distinctiveness_floor: float = DEFAULT_DISTINCTIVENESS_FLOOR,
    useful_packet_rate_floor: float = DEFAULT_USEFUL_PACKET_RATE_FLOOR,
    hot_packet_ms_ceiling: int = DEFAULT_HOT_PACKET_MS_CEILING,
    protocol_noise_ratio_ceiling: float = DEFAULT_PROTOCOL_NOISE_RATIO_CEILING,
) -> dict[str, Any]:
    """Return the shared `continuity_usefulness` metric group.

    The input shape is intentionally plain mapping data so recall, hook,
    benchmark, router, and AIppo reports can project into the same gate without
    importing one another or changing their source-truth owner.
    """

    red_line_total = _red_line_total(surface)
    packet_count = max(1, _int(surface.get("packet_count")))
    useful_packet_count = _int(surface.get("useful_packet_count"))
    useful_packet_rate = _ratio(useful_packet_count, packet_count)
    noise_bytes = _int(surface.get("foreground_protocol_noise_bytes"))
    useful_bytes = _int(surface.get("useful_guidance_bytes"))
    protocol_noise_ratio = _ratio(noise_bytes, noise_bytes + useful_bytes)
    manual_query_count = _int(surface.get("manual_query_invention_count"))
    blind_deepen_count = _int(surface.get("blind_deepen_required_count"))
    wrong_route_drag_count = _int(surface.get("wrong_route_drag_count"))
    distinctiveness = _float(surface.get("packet_triage_distinctiveness"))
    if distinctiveness == 0 and packet_count == 1:
        distinctiveness = 1.0
    time_to_first = _int(surface.get("time_to_first_useful_packet_ms_proxy"))
    if time_to_first == 0:
        time_to_first = hot_packet_ms_ceiling
    safe_route_evidence_count = _int(surface.get("safe_route_evidence_present_count"))
    action_permission_level = _action_permission_level(surface, red_line_total)
    minimum_permission_level = _minimum_useful_action_permission_level(surface)
    demoted_to_scent_count = max(
        _int(surface.get("usefulness_lost_by_demoting_to_scent_count")),
        int(
            safe_route_evidence_count > 0
            and action_permission_level == "scent"
            and _permission_below(action_permission_level, minimum_permission_level)
        ),
    )
    fresh_agent_active_pull_success_count = _int(
        surface.get("fresh_agent_active_pull_success_count")
    )
    fresh_agent_broad_search_count = _int(
        surface.get("fresh_agent_broad_search_before_recall_count")
    )
    deepen_handle_misuse_count = _int(surface.get("deepen_handle_misuse_count"))
    copy_pasteable_deepen_target_count = _int(
        surface.get("copy_pasteable_deepen_target_present_count")
    )
    reopen_success_count = _int(surface.get("recall_to_source_reopen_success_count"))
    reopen_attempt_count = _int(surface.get("recall_to_source_reopen_attempt_count"))
    recall_to_source_reopen_success_rate = (
        1.0
        if reopen_attempt_count == 0
        else _ratio(min(reopen_success_count, reopen_attempt_count), reopen_attempt_count)
    )
    derived_extra_work_count = (
        manual_query_count
        + blind_deepen_count
        + wrong_route_drag_count
        + fresh_agent_broad_search_count
        + deepen_handle_misuse_count
    )
    main_agent_extra_work_count = max(
        _int(surface.get("main_agent_extra_work_count")),
        derived_extra_work_count,
    )
    missing_copy_pasteable_target_count = 0
    # "Not enough for a claim" must not collapse a safe route back to scent.
    # The copy-pasteable handle is what keeps the foreground agent from trying
    # display-only ids or broad manual grep when route evidence is already safe.
    if safe_route_evidence_count and _permission_below(
        action_permission_level, minimum_permission_level
    ):
        missing_copy_pasteable_target_count = max(
            0, safe_route_evidence_count - copy_pasteable_deepen_target_count
        )
    elif (
        safe_route_evidence_count
        and ACTION_PERMISSION_RANK[action_permission_level]
        >= ACTION_PERMISSION_RANK[DEFAULT_ROUTE_ACTION_PERMISSION_FLOOR]
    ):
        missing_copy_pasteable_target_count = max(
            0, safe_route_evidence_count - copy_pasteable_deepen_target_count
        )

    blockers: list[str] = []
    if manual_query_count:
        blockers.append("manual_query_invention")
    if blind_deepen_count:
        blockers.append("blind_deepen_required")
    if distinctiveness < distinctiveness_floor:
        blockers.append("packet_triage_distinctiveness_below_floor")
    if wrong_route_drag_count:
        blockers.append("wrong_route_drag")
    if useful_packet_rate < useful_packet_rate_floor:
        blockers.append("useful_packet_rate_below_floor")
    if time_to_first > hot_packet_ms_ceiling:
        blockers.append("time_to_first_useful_packet_over_ceiling")
    if demoted_to_scent_count:
        blockers.append("safe_route_demoted_to_scent")
    if fresh_agent_broad_search_count:
        blockers.append("fresh_agent_broad_search_before_recall")
    if deepen_handle_misuse_count:
        blockers.append("deepen_handle_misuse")
    if missing_copy_pasteable_target_count:
        blockers.append("copy_pasteable_deepen_target_missing")
    if reopen_attempt_count and recall_to_source_reopen_success_rate < 1.0:
        blockers.append("recall_to_source_reopen_incomplete")
    if main_agent_extra_work_count:
        blockers.append("main_agent_extra_work")

    attention_saved_vs_spent = (
        useful_bytes
        - noise_bytes
        - manual_query_count * 120
        - blind_deepen_count * 80
        - wrong_route_drag_count * 100
        - fresh_agent_broad_search_count * 160
        - deepen_handle_misuse_count * 120
        - demoted_to_scent_count * 140
    )
    safety_gate_ok = red_line_total == 0
    usefulness_gate_ok = not blockers
    attention_cost_ok = (
        protocol_noise_ratio <= protocol_noise_ratio_ceiling
        and attention_saved_vs_spent > 0
    )

    return {
        "kind": "continuity_usefulness",
        "manual_query_invention_count": manual_query_count,
        "blind_deepen_required_count": blind_deepen_count,
        "packet_triage_distinctiveness": round(distinctiveness, 4),
        "wrong_route_drag_count": wrong_route_drag_count,
        "useful_packet_rate": useful_packet_rate,
        "route_actionability_rate": useful_packet_rate,
        "action_permission_level": action_permission_level,
        "minimum_useful_action_permission_level": minimum_permission_level,
        "safe_route_evidence_present_count": safe_route_evidence_count,
        "usefulness_lost_by_demoting_to_scent_count": demoted_to_scent_count,
        "main_agent_extra_work_count": main_agent_extra_work_count,
        "fresh_agent_active_pull_success_count": fresh_agent_active_pull_success_count,
        "fresh_agent_broad_search_before_recall_count": fresh_agent_broad_search_count,
        "deepen_handle_misuse_count": deepen_handle_misuse_count,
        "copy_pasteable_deepen_target_present_count": copy_pasteable_deepen_target_count,
        "copy_pasteable_deepen_target_missing_count": missing_copy_pasteable_target_count,
        "recall_to_source_reopen_success_rate": recall_to_source_reopen_success_rate,
        "recall_to_source_reopen_success_count": reopen_success_count,
        "recall_to_source_reopen_attempt_count": reopen_attempt_count,
        "foreground_protocol_noise_bytes": noise_bytes,
        "useful_guidance_bytes": useful_bytes,
        "foreground_protocol_noise_ratio": protocol_noise_ratio,
        "attention_saved_vs_spent_proxy": attention_saved_vs_spent,
        "time_to_first_useful_packet_ms_proxy": time_to_first,
        "safety_gate_ok": safety_gate_ok,
        "usefulness_gate_ok": usefulness_gate_ok,
        "attention_cost_ok": attention_cost_ok,
        "quality_gate_ok": safety_gate_ok and usefulness_gate_ok and attention_cost_ok,
        "usefulness_blockers": blockers,
    }


__all__ = [
    "ACTION_PERMISSION_LADDER",
    "continuity_usefulness_metrics",
]
