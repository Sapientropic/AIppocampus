"""Route-shape predicates shared by compact MCP recall projections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.recall import associative_path_foreground_gate as apw_gate
from aippocampus_runtime.source.query_match_gate import query_match_gate


def primary_current_source_reopenable(memory_packets: list[dict[str, Any]]) -> bool:
    if not memory_packets:
        return False
    primary = memory_packets[0]
    if primary.get("output_mode") != "reopenable_route":
        return False
    cue_family = str(primary.get("matched_cue_family") or "").strip()
    if cue_family in {"clean_source_hit", "clean_source_turn_anchor_hit"}:
        return True
    return str(primary.get("route_label") or "").casefold().startswith(
        "current_turn source route"
    )


def apw_card_allows_primary(
    *,
    should_replace: bool,
    associative_path_policy: Any,
    raw_associative_path_fallback: Any,
) -> bool:
    explicit_requested = bool(
        isinstance(associative_path_policy, dict)
        and associative_path_policy.get("explicit_requested")
    )
    return (should_replace or explicit_requested) and (
        apw_gate.card_allows_primary_source_action(raw_associative_path_fallback)
    )


def apw_allows_primary_for_current_foreground(
    *,
    should_replace: bool,
    associative_path_policy: Any,
    raw_associative_path_fallback: Any,
    foreground_action: Mapping[str, Any],
    recall_payload: Mapping[str, Any],
) -> bool:
    explicit_requested = bool(
        isinstance(associative_path_policy, dict)
        and associative_path_policy.get("explicit_requested")
    )
    ordinary_source_followthrough_available = (
        not explicit_requested
        and str(foreground_action.get("tool_name") or "") == "agent_deepen"
        and apw_gate.recall_payload_has_target_source_followthrough(recall_payload)
    )
    phrase_like_source_search_first = _phrase_like_current_source_apw_should_defer(
        associative_path_policy=associative_path_policy,
        raw_associative_path_fallback=raw_associative_path_fallback,
        recall_payload=recall_payload,
    )
    return (
        apw_card_allows_primary(
            should_replace=should_replace,
            associative_path_policy=associative_path_policy,
            raw_associative_path_fallback=raw_associative_path_fallback,
        )
        and not ordinary_source_followthrough_available
        and not phrase_like_source_search_first
    )


def _phrase_like_current_source_apw_should_defer(
    *,
    associative_path_policy: Any,
    raw_associative_path_fallback: Any,
    recall_payload: Mapping[str, Any],
) -> bool:
    """Keep original-phrase cues on source search before current-source APW.

    Current clean-source APW is deliberately cheap and can rescue vague route
    cues. For phrase-like cues with many anchors, though, a nearby workflow
    discussion can pass APW anchor coverage while the user's original source is
    findable by registry search. This gate only affects non-explicit APW
    promotion; explicit APW requests remain opt-in navigation.
    """

    if (
        isinstance(associative_path_policy, Mapping)
        and associative_path_policy.get("explicit_requested")
    ):
        return False
    if not isinstance(raw_associative_path_fallback, Mapping):
        return False
    if raw_associative_path_fallback.get("status") != "route_candidate":
        return False
    if raw_associative_path_fallback.get("candidate_source_kind") != "current_clean_source":
        return False
    cue = str(
        recall_payload.get("query")
        or recall_payload.get("intent")
        or recall_payload.get("cue")
        or ""
    ).strip()
    if not cue:
        return False
    gate = query_match_gate(cue)
    return bool(gate.get("phrase_like_query")) and int(gate.get("distinctive_anchor_count") or 0) >= 4
