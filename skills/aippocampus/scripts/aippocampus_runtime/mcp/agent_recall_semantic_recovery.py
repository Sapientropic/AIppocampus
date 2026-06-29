"""Source-shaped semantic recovery promotion for compact agent recall."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import normalize_foreground_action
from aippocampus_runtime.mcp import agent_recall_route_projection as route_projection
from aippocampus_runtime.mcp.agent_recall_compact_choices import (
    EXACT_WORDING_SOURCE_SEARCH_ACTION_ID,
)

SEMANTIC_ROUTE_MARKERS = {
    "semantic_trigger",
    "semantic_trigger_source",
    "semantic_trigger_source_ref",
    "source_semantic_candidate",
}

SOURCE_FIRST_ACTION_IDS = {
    EXACT_WORDING_SOURCE_SEARCH_ACTION_ID,
    "search_current_source_for_cue_anchors",
    "open_registry_search_source_window",
    "reopen_search_match_source",
    "use_opened_source_window",
    "use_opened_route_context",
    "reopen_already_opened_route_context",
}

RECOVERY_ACTION_IDS = {
    "recover_recall_miss",
    "recover_weak_route",
    "search_registry_sources_for_original_cue_anchors",
    "refine_low_specificity_recall_cue",
    "deepen_top_route_low_confidence",
    "repair_last_recall_cache",
    "open_repo_familiarity_source",
}


def _action_id(action: Mapping[str, Any]) -> str:
    return str(action.get("id") or action.get("action_id") or "")


def _reason_codes(packet: Mapping[str, Any]) -> set[str]:
    raw = packet.get("triage_rank_reason_codes") or packet.get("route_delta_reason_codes") or []
    if not isinstance(raw, list | tuple):
        return set()
    return {str(code) for code in raw if str(code).strip()}


def _semantic_packet(packet: Mapping[str, Any]) -> bool:
    fields = {
        str(packet.get("matched_cue_family") or ""),
        str(packet.get("source_chain_role") or ""),
        str(packet.get("route_topic") or ""),
        str(packet.get("scope_bucket") or ""),
        str(packet.get("route_kind") or ""),
    }
    if fields & SEMANTIC_ROUTE_MARKERS:
        return True
    return bool(_reason_codes(packet) & SEMANTIC_ROUTE_MARKERS)


def _semantic_route_index(memory_packets: list[dict[str, Any]]) -> tuple[int, Mapping[str, Any]] | None:
    for index, packet in enumerate(memory_packets, start=1):
        if route_projection.route_anchor_gate_blocks_reopen(packet):
            continue
        if _semantic_packet(packet):
            return index, packet
    return None


def _semantic_route_action(
    *,
    request_index: int,
    packet: Mapping[str, Any],
    recall_selector: str,
) -> dict[str, Any]:
    action = route_projection.route_deepen_action(request_index, recall_selector=recall_selector)
    label = route_projection.public_route_label(packet)
    action.update(
        {
            "id": "deepen_semantic_recovery_route",
            "label": f"Open {label}" if label else "Open semantic recovery route",
            "claim_boundary": "semantic_navigation_only_until_source_reopen",
            "why": (
                "A reviewed source-shaped semantic candidate matched this fuzzy cue; "
                "open the source before using it for claims."
            ),
        }
    )
    return action


def _should_replace_with_semantic(action: Mapping[str, Any]) -> bool:
    action_id = _action_id(action)
    if action_id in SOURCE_FIRST_ACTION_IDS:
        return False
    if action_id in RECOVERY_ACTION_IDS:
        return True
    if action_id.startswith("recover_"):
        return True
    if str(action.get("route_choice_posture") or "") == "labels_low_specificity":
        return True
    return str(action.get("tool_name") or "") == "search_memory"


def _unique_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for action in actions:
        normalized = core.strip_empty(normalize_foreground_action(action), drop_empty_dicts=True)
        if not normalized:
            continue
        key = (
            str(normalized.get("id") or ""),
            str(normalized.get("command") or normalized.get("command_template") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def maybe_promote_semantic_recovery(
    *,
    memory_packets: list[dict[str, Any]],
    foreground_action: dict[str, Any],
    followup_actions: list[dict[str, Any]],
    recall_selector: str,
    anchor_gate: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Prefer source-shaped semantic routes over broad recovery fallbacks.

    Semantic candidates stay navigation-only: this helper only chooses the next
    reopen action when a concrete source-shaped route already exists. It does
    not turn semantic output into source evidence, and it deliberately leaves
    exact/current-source actions alone because those are stronger than semantic
    navigation.
    """

    if (
        _action_id(foreground_action) == "search_registry_sources_for_original_cue_anchors"
        and route_projection.anchor_gate_blocks_reopen(anchor_gate)
    ):
        return foreground_action, followup_actions
    semantic = _semantic_route_index(memory_packets)
    if semantic is None:
        return foreground_action, followup_actions
    request_index, packet = semantic
    semantic_action = _semantic_route_action(
        request_index=request_index,
        packet=packet,
        recall_selector=recall_selector,
    )
    if request_index == 1 and str(foreground_action.get("tool_name") or "") == "agent_deepen":
        merged = dict(foreground_action)
        merged.update(
            {
                "id": "deepen_semantic_recovery_route",
                "label": semantic_action["label"],
                "claim_boundary": semantic_action["claim_boundary"],
                "why": semantic_action["why"],
            }
        )
        return merged, followup_actions
    if not _should_replace_with_semantic(foreground_action):
        return foreground_action, followup_actions
    ordinary = core.strip_empty(
        normalize_foreground_action(foreground_action),
        drop_empty_dicts=True,
    )
    return semantic_action, _unique_actions([ordinary, *followup_actions])
