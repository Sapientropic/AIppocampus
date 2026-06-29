"""Frontstage vocabulary cleanup for default compact JSON.

Compact foreground surfaces should tell an agent what happened and what to do
next. They should not ask the agent to reason over internal claim-boundary,
operator, or posture taxonomies. Detail/full/operator profiles still own those
diagnostics; this helper is only for default compact projections.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

COMPACT_POLICY_FIELD_DENYLIST = frozenset(
    {
        "cannot_claim",
        "claim_boundary",
        "action_boundary",
        "boundary",
        "last_recall_boundary",
        "last_recall_fallback_boundary",
        "local_private_fields",
        "manage_command",
        "operator_boundary",
        "operator_detail_command",
        "operator_detail_command_template",
        "operator_detail_available",
        "operator_detail_fields",
        "operator_details_available",
        "operator_json_available",
        "operator_json_command",
        "operator_json_command_template",
        "operator_json_requires",
        "output_boundary",
        "policy_boundary",
        "privacy_boundary",
        "source_boundary",
        "source_reopen_boundary",
        "write_boundary",
    }
)

COMPACT_CONTROL_SURFACE_FIELD_DENYLIST = frozenset(
    {
        "diagnostic_fields_omitted",
        "detail_actions_available",
        "event_log",
        "foreground_action_card",
        "foreground_action_menu",
        "foreground_latency_red_line_violation_count",
        "historical_foreground_latency_red_line_violation_count",
        "historical_prompt_hook_near_timeout_event_count",
        "official_contract",
        "operator_detail",
        "operator_diagnostics",
        "prompt_hook_near_timeout_event_count",
        "reader_diagnostic",
        "red_lines",
        "runtime_provenance",
        "status_vocabulary",
        "write_contract",
    }
)


def strip_compact_policy_vocabulary(
    value: Any,
    *,
    extra_denied_keys: set[str] | frozenset[str] | None = None,
    max_safe_actions: int | None = None,
) -> Any:
    """Remove internal policy vocabulary from frontstage compact payloads."""

    denied = COMPACT_POLICY_FIELD_DENYLIST | frozenset(extra_denied_keys or ())
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) in denied:
                continue
            projected = strip_compact_policy_vocabulary(
                item,
                extra_denied_keys=extra_denied_keys,
                max_safe_actions=max_safe_actions,
            )
            if (
                max_safe_actions is not None
                and str(key) == "safe_next_actions"
                and isinstance(projected, list)
            ):
                projected = projected[: max(0, max_safe_actions)]
            if projected in (None, "", [], {}):
                continue
            cleaned[str(key)] = projected
        return cleaned
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [
            strip_compact_policy_vocabulary(
                item,
                extra_denied_keys=extra_denied_keys,
                max_safe_actions=max_safe_actions,
            )
            for item in value
        ]
    return value


def compact_details_flag(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Translate detail/operator affordances into a small frontstage signal."""

    has_detail = any(
        key in payload
        for key in (
            "detail_command",
            "diagnostic_detail_command",
            "operator_detail_command",
            "operator_detail_command_template",
            "operator_detail_available",
            "operator_detail_fields",
            "operator_details_available",
            "operator_json_available",
            "operator_json_command",
            "operator_json_command_template",
            "full_schema_command",
            "detail_actions_available",
        )
    )
    return {"details_available": True} if has_detail else {}


def compact_frontstage_projection(
    payload: Mapping[str, Any],
    *,
    extra_denied_keys: set[str] | frozenset[str] | None = None,
    max_safe_actions: int | None = 1,
) -> dict[str, Any]:
    """Project a default compact CLI/MCP card into an action-sized surface.

    The recurrent failure mode is hand-built status cards that carry internal
    proof fields forward. Keep the raw diagnostics in explicit detail/operator
    output, but make the default surface small enough for a foreground agent to
    act on without reconciling policy ledgers.
    """

    denied = COMPACT_CONTROL_SURFACE_FIELD_DENYLIST | frozenset(extra_denied_keys or ())
    working = dict(payload)
    working.update(compact_details_flag(working))
    projected = strip_compact_policy_vocabulary(
        working,
        extra_denied_keys=denied,
        max_safe_actions=max_safe_actions,
    )
    return dict(projected) if isinstance(projected, Mapping) else {}
