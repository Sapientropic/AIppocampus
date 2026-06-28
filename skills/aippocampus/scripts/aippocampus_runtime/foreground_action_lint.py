"""Semantic foreground-action lint for compact default surfaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from aippocampus_runtime.contracts import (
    _normalized_action_command,
    foreground_action_contract_violations,
    foreground_action_is_read_only,
)


def compact_foreground_action_violations(
    payload: Mapping[str, object],
    *,
    max_safe_actions: int = 1,
    allow_write_safe_actions: bool = False,
    current_status_command: str | None = None,
    allow_manual_safe_actions: bool = False,
) -> list[dict[str, str]]:
    """Return default-compact UX violations on top of the base contract.

    This intentionally lives outside the core contract module so agents can add
    frontstage UX guardrails without turning the low-level action schema into a
    dumping ground. It guards the recurring failure mode: a compact status card
    that looks runnable but actually becomes a menu, a write prompt, or a
    status self-loop.
    """

    violations = foreground_action_contract_violations(payload)
    foreground = payload.get("foreground_action")
    if (
        isinstance(foreground, Mapping)
        and not allow_write_safe_actions
        and not foreground_action_is_read_only(foreground)
    ):
        violations.append(
            {
                "field": "foreground_action.mutation_risk",
                "reason": "write_capable_action_not_allowed_in_default_compact",
            }
        )
    safe_actions = payload.get("safe_next_actions")
    if not isinstance(safe_actions, Sequence) or isinstance(safe_actions, str):
        return violations
    if len(safe_actions) > max_safe_actions:
        violations.append(
            {
                "field": "safe_next_actions",
                "reason": "compact_safe_next_actions_exceeds_budget",
            }
        )
    normalized_status_command = _normalized_action_command(current_status_command)
    for index, action in enumerate(safe_actions):
        if not isinstance(action, Mapping):
            continue
        if not allow_write_safe_actions and not foreground_action_is_read_only(action):
            violations.append(
                {
                    "field": f"safe_next_actions.{index}.mutation_risk",
                    "reason": "write_capable_action_not_allowed_in_default_compact",
                }
            )
        has_target = any(
            isinstance(action.get(key), str) and str(action.get(key)).strip()
            for key in ("command", "command_template", "tool_name")
        )
        has_continue_marker = any(
            bool(action.get(key))
            for key in ("continue_without_command", "no_op", "no_command_needed")
        )
        if not allow_manual_safe_actions and not has_target and not has_continue_marker:
            violations.append(
                {
                    "field": f"safe_next_actions.{index}",
                    "reason": "manual_safe_action_needs_command_or_continue_marker",
                }
            )
        command = _normalized_action_command(
            action.get("command") or action.get("command_template")
        )
        if normalized_status_command and command == normalized_status_command:
            violations.append(
                {
                    "field": f"safe_next_actions.{index}",
                    "reason": "status_self_loop_not_allowed_in_default_compact",
                }
            )
    return violations
