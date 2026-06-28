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
        "claim_boundary",
        "operator_boundary",
        "operator_detail_command",
        "operator_detail_command_template",
        "operator_details_available",
        "operator_json_available",
        "operator_json_command",
        "operator_json_command_template",
        "operator_json_requires",
        "output_boundary",
        "policy_boundary",
        "source_reopen_boundary",
    }
)


def strip_compact_policy_vocabulary(
    value: Any,
    *,
    extra_denied_keys: set[str] | frozenset[str] | None = None,
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
            )
            if projected in (None, "", [], {}):
                continue
            cleaned[str(key)] = projected
        return cleaned
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [
            strip_compact_policy_vocabulary(item, extra_denied_keys=extra_denied_keys)
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
            "operator_details_available",
            "operator_json_available",
            "operator_json_command",
            "operator_json_command_template",
            "full_schema_command",
        )
    )
    return {"details_available": True} if has_detail else {}
