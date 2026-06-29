"""Foreground projections for macro-orientation recovery cards."""

from __future__ import annotations

# aippocampus-instruction-surface: macro compact recovery projection owner; ledgers and source proof stay in detail/operator paths.
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.foreground_compact_language import strip_compact_policy_vocabulary


def compact_missing_state_card(
    *,
    kind: str,
    schema_version: str,
    macro_packet_schema_version: str,
    suggested_next: str,
    foreground_action: Mapping[str, Any],
    safe_next_actions: Sequence[Mapping[str, Any]],
    producer_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep missing-state recovery foreground-first; ledgers stay in detail."""

    card = {
        "kind": kind,
        "schema_version": schema_version,
        "macro_packet_schema_version": macro_packet_schema_version,
        "mode": "macro",
        "surface": "macro_orientation",
        "detail": "compact",
        "status": "missing_macro_state_path",
        "ok": True,
        "suggested_next": suggested_next,
        "state_ready": False,
        "fallback_available": True,
        "message": "No macro-orientation state is available yet; use recall or inspect the schema before creating local macro state.",
        "producer_status": dict(
            producer_status
            or {
                "state_producer": "available_as_staged_review_path",
                "state_ready": False,
                "candidate_queue": ".aippocampus/macro-orientation-candidates.jsonl",
                "next_action": "collect source-backed router observations, stage a candidate, then review before writing macro state",
                "hot_path_write_allowed": False,
                "total_hexagram_status": "not_produced_by_minimal_producer",
            }
        ),
        **canonical_foreground_action_fields(foreground_action, safe_next_actions=safe_next_actions),
        "claim_boundary": "macro_orientation_is_navigation_not_source_truth",
        "operator_detail_command": "aippocampus agent macro --json --detail full",
        "output_boundary": "compact_foreground_no_audit_ledgers",
    }
    return strip_compact_policy_vocabulary(card)


def momentum_block(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    momentum = entry.get("momentum")
    return momentum if isinstance(momentum, Mapping) else {}


def state_has_route_signal(entry: Mapping[str, Any]) -> bool:
    movement = entry.get("movement")
    if not isinstance(movement, Mapping):
        return False
    if str(movement.get("mode") or "") != "standing_state":
        return True
    producer = entry.get("producer")
    producer_map: Mapping[str, Any] = producer if isinstance(producer, Mapping) else {}
    if producer_map.get("kind") != "macro_orientation_staged_producer":
        return False
    basis = momentum_block(entry).get("basis")
    if isinstance(basis, Mapping) and any(float(value or 0.0) != 0.0 for value in basis.values()):
        return True
    relation = entry.get("relation_position")
    relation_map: Mapping[str, Any] = relation if isinstance(relation, Mapping) else {}
    return bool(relation_map.get("active_layer"))


def _momentum_foreground_text(entry: Mapping[str, Any]) -> str:
    momentum = momentum_block(entry)
    direction = str(momentum.get("direction") or "")
    route_policy = str(momentum.get("route_policy") or "")
    if not direction:
        return ""
    if route_policy == "closeout_with_overconfidence_watch":
        return "derived momentum peak; recheck currentness and overconfidence before closeout"
    if direction == "rising":
        return "derived momentum rising"
    if direction == "turning":
        return "derived momentum turning; recheck currentness before pushing"
    if direction == "declining":
        return "derived momentum declining; reduce push and reopen currentness"
    if direction == "hibernating":
        return "derived momentum hibernating; stay quiet until new source changes"
    return f"derived momentum {direction}"


def foreground_text(entry: Mapping[str, Any]) -> str:
    raw_hexagram = entry.get("hexagram")
    hexagram: Mapping[str, Any] = raw_hexagram if isinstance(raw_hexagram, Mapping) else {}
    raw_movement = entry.get("movement")
    movement: Mapping[str, Any] = raw_movement if isinstance(raw_movement, Mapping) else {}
    raw_relation = entry.get("relation_position")
    relation: Mapping[str, Any] = raw_relation if isinstance(raw_relation, Mapping) else {}
    current = str(hexagram.get("name") or "unknown")
    toward = str(movement.get("toward") or current)
    layer = str(relation.get("active_layer") or "unknown")
    role = str(relation.get("current_agent_default_role") or "unknown")
    momentum_text = _momentum_foreground_text(entry)
    momentum_clause = f"; {momentum_text}" if momentum_text else ""
    producer = entry.get("producer")
    producer_map: Mapping[str, Any] = producer if isinstance(producer, Mapping) else {}
    if producer_map.get("total_hexagram_status") == "not_produced":
        return (
            "Macro orientation heuristic (active-layer/momentum only): "
            f"human-action layer ({layer}){momentum_clause}; agent posture {role}. "
            "Six-line total hexagram is not produced by this path. "
            "Use as navigation only; reopen before exact/public/disputed claims."
        )
    return (
        f"Macro orientation heuristic (initial calibration): {current} -> {toward}; "
        f"human-action layer ({layer}){momentum_clause}; agent posture {role}. "
        f"Use as navigation only; reopen before exact/public/disputed claims."
    )
