"""Small foreground signals for architecture-native recall navigation.

These labels make route-selection lift visible without turning topology,
attention, macro, or local/global internals into facts. The payload is
navigation-only: no source text, source refs, local paths, or private ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ARCHITECTURE_CUE_LABELS = {
    "attention_router": ("attention router", "attention-router", "attention_router"),
    "topology": ("topology", "拓扑"),
    "macro_orientation": ("macro orientation", "macro-orientation", "macro_orientation"),
    "local_global": ("sheaf", "local-global", "local global", "local_global", "胶合"),
    "architecture_navigation": ("architecture", "架构"),
}


def _architecture_cues(query: Any) -> list[str]:
    text = str(query or "").casefold()
    cues: list[str] = []
    for label, needles in ARCHITECTURE_CUE_LABELS.items():
        if any(needle.casefold() in text for needle in needles):
            cues.append(label)
    return cues


def navigation_signals_for_recall(
    *,
    query: str,
    macro_navigation: Mapping[str, Any],
    attention_navigation: Mapping[str, Any],
    memory_packets: list[dict[str, Any]],
) -> dict[str, Any]:
    cues = _architecture_cues(query)
    signals: list[str] = []
    why_visible: list[str] = []

    if cues:
        why_visible.append("explicit_architecture_prompt")
        for cue in cues:
            signals.append(f"{cue}_requested")

    if attention_navigation.get("enabled"):
        if attention_navigation.get("applied"):
            signals.append("attention_router_applied")
        if attention_navigation.get("top_route_changed"):
            signals.append("attention_router_top_route_changed")
        selected_route_id = str(attention_navigation.get("selected_route_id") or "").strip()
        if selected_route_id:
            signals.append("attention_router_selected_route")
    elif "attention_router" in cues:
        signals.append("attention_router_not_enabled")

    if macro_navigation.get("applied"):
        signals.append("macro_orientation_applied")
    elif "macro_orientation" in cues:
        signals.append("macro_orientation_missing_or_gated")

    route_delta = any(packet.get("route_delta_reason_codes") for packet in memory_packets)
    if route_delta:
        why_visible.append("router_or_macro_changed_route")

    if not signals or (not cues and not route_delta):
        return {}

    next_safe_action = "deepen_selected_route" if route_delta else "run_explain_or_recall_diagnostic"
    return {
        "kind": "architecture_navigation_affordance",
        "signals": list(dict.fromkeys(signals))[:6],
        "action_grammar": "reopenable_route" if route_delta else "direction_only",
        "claim_permission": "no_claim_before_reopen",
        "next_safe_action": next_safe_action,
        "why_visible": list(dict.fromkeys(why_visible))[:3],
        "not_claim_ready": True,
    }


__all__ = ["navigation_signals_for_recall"]
