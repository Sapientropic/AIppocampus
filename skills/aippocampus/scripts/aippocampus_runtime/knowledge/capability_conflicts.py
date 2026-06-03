#!/usr/bin/env python3
"""Deterministic conflict resolver for typed capability actions.

This is intentionally smaller than a planner: it only orders already-proposed
capability actions when their activation or output states conflict. Capability
text remains execution policy, not factual support; source truth and answer
gates still own claim validity.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

CAPABILITY_CONFLICT_POLICY_VERSION = "aippocampus.capability_conflict_policy.v1"

PRECEDENCE_CLASSES = (
    "privacy_boundary",
    "safety_high_risk",
    "source_truth",
    "task_domain",
    "operation_side_effect",
    "communication_style",
)
_PRECEDENCE_RANK = {name: rank for rank, name in enumerate(PRECEDENCE_CLASSES)}
DEFAULT_CANNOT_CLAIM = (
    "capability_text_is_not_fact_source",
    "conflict_resolution_is_activation_policy_not_truth",
    "resolver_does_not_promote_source_claims",
)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value else []


def _as_str_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _precedence_class(packet: Mapping[str, Any]) -> str:
    value = str(packet.get("precedence_class") or "").strip()
    return value if value in _PRECEDENCE_RANK else "communication_style"


def _rank(packet: Mapping[str, Any]) -> int:
    return _PRECEDENCE_RANK[_precedence_class(packet)]


def _action_id(packet: Mapping[str, Any], index: int) -> str:
    return str(packet.get("action_id") or packet.get("capability_id") or f"action_{index}")


def _sanitize_action(packet: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    sanitized: dict[str, Any] = {
        "action_id": _action_id(packet, index),
        "capability_id": str(packet.get("capability_id") or ""),
        "precedence_class": _precedence_class(packet),
        "output_state": str(packet.get("output_state") or "cannot_proceed"),
    }
    tool_id = packet.get("tool_id")
    if tool_id:
        sanitized["tool_id"] = str(tool_id)
    return sanitized


def _suppression_reason(winner: Mapping[str, Any], loser: Mapping[str, Any]) -> str:
    return f"{_precedence_class(winner)}_overrides_{_precedence_class(loser)}"


def resolve_capability_conflicts(
    candidate_actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve mutually applicable capability actions by fixed precedence.

    The resolver accepts sanitized action packets from capability manifests,
    answer gates, privacy guards, or communication policies. It deliberately
    ignores prose fields and raw input text so lower-priority style/task helpers
    cannot launder themselves into truth evidence.
    """

    normalized = [
        dict(action)
        for action in candidate_actions
        if isinstance(action, Mapping) and (action.get("action_id") or action.get("capability_id"))
    ]
    if not normalized:
        return {
            "ok": False,
            "policy_version": CAPABILITY_CONFLICT_POLICY_VERSION,
            "output_state": "cannot_proceed",
            "selected": None,
            "suppressed": [],
            "reason_codes": ["no_candidate_actions"],
            "questions": [],
            "cannot_claim": list(DEFAULT_CANNOT_CLAIM),
            "truth_boundary": "activation_policy_not_fact_source",
            "precedence": list(PRECEDENCE_CLASSES),
        }

    indexed = list(enumerate(normalized))
    selected_index, selected_packet = min(
        indexed,
        key=lambda item: (
            _rank(item[1]),
            _action_id(item[1], item[0]),
            str(item[1].get("capability_id") or ""),
        ),
    )
    selected = _sanitize_action(selected_packet, index=selected_index)

    suppressed: list[dict[str, Any]] = []
    reason_codes = _as_str_list(selected_packet.get("reason_codes"))
    cannot_claim = list(DEFAULT_CANNOT_CLAIM) + _as_str_list(selected_packet.get("cannot_claim"))
    for index, packet in indexed:
        if index == selected_index:
            continue
        suppression_code = _suppression_reason(selected_packet, packet)
        suppressed_action = _sanitize_action(packet, index=index)
        suppressed_action.update(
            {
                "decision": "suppressed",
                "suppressed_by": selected["action_id"],
                "reason_codes": [suppression_code],
            }
        )
        suppressed.append(suppressed_action)
        reason_codes.append(suppression_code)
        cannot_claim.extend(_as_str_list(packet.get("cannot_claim")))

    questions = [
        dict(item)
        for item in _as_list(selected_packet.get("questions"))
        if isinstance(item, Mapping)
    ]
    return {
        "ok": True,
        "policy_version": CAPABILITY_CONFLICT_POLICY_VERSION,
        "output_state": selected["output_state"],
        "selected": selected,
        "suppressed": suppressed,
        "reason_codes": _unique(reason_codes),
        "questions": questions,
        "cannot_claim": _unique(cannot_claim),
        "truth_boundary": "activation_policy_not_fact_source",
        "precedence": list(PRECEDENCE_CLASSES),
    }
