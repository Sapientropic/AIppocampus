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

    attention_saved_vs_spent = (
        useful_bytes
        - noise_bytes
        - manual_query_count * 120
        - blind_deepen_count * 80
        - wrong_route_drag_count * 100
    )
    safety_gate_ok = _red_line_total(surface) == 0
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


__all__ = ["continuity_usefulness_metrics"]
