"""Accept safe foreground chooser actions without shelling out blindly."""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.cli.command_registry import CommandInvocation, resolve_command
from aippocampus_runtime.contracts import normalize_foreground_action

ACCEPT_FLAGS = {"--accept", "--run-default"}
READ_ONLY_MUTATION_RISKS = {
    "read_only",
    "read_only_preview",
    "read_only_preview_of_delete",
}


@dataclass(frozen=True)
class ChooserTail:
    json_output: bool
    accept_requested: bool
    action_id: str | None
    unsupported_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptedAction:
    action: dict[str, Any]
    invocation: CommandInvocation | None
    block_payload: dict[str, Any] | None = None


def parse_chooser_tail(tail: Sequence[str]) -> ChooserTail:
    json_output = False
    accept_requested = False
    action_id: str | None = None
    unsupported: list[str] = []
    expect_action_id = False
    for arg in tail:
        if arg == "--json":
            json_output = True
            continue
        if arg in ACCEPT_FLAGS:
            accept_requested = True
            expect_action_id = True
            continue
        if expect_action_id and not arg.startswith("-") and action_id is None:
            action_id = arg
            expect_action_id = False
            continue
        unsupported.append(arg)
    return ChooserTail(
        json_output=json_output,
        accept_requested=accept_requested,
        action_id=action_id,
        unsupported_args=tuple(unsupported),
    )


def chooser_tail_supported(tail: Sequence[str]) -> bool:
    return not parse_chooser_tail(tail).unsupported_args


def _action_candidates(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for raw in [
        payload.get("foreground_action"),
        *(payload.get("safe_next_actions") or []),
        *(payload.get("choices") if isinstance(payload.get("choices"), list) else []),
        *(payload.get("write_actions") if isinstance(payload.get("write_actions"), list) else []),
    ]:
        if not isinstance(raw, Mapping):
            continue
        action = normalize_foreground_action(raw)
        if action and action not in candidates:
            candidates.append(dict(action))
    return candidates


def _selected_action(
    payload: Mapping[str, Any],
    action_id: str | None,
) -> dict[str, Any] | None:
    actions = _action_candidates(payload)
    if not action_id:
        return actions[0] if actions else None
    for action in actions:
        if str(action.get("id") or "") == action_id:
            return action
    return None


def _block_payload(
    *,
    chooser_kind: str,
    status: str,
    reason: str,
    action: Mapping[str, Any] | None,
    action_id: str | None,
) -> dict[str, Any]:
    required = action.get("requires") if isinstance(action, Mapping) else []
    if isinstance(required, str):
        required_fields = [required]
    elif isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
        required_fields = [str(item) for item in required if str(item)]
    else:
        required_fields = []
    return {
        "kind": f"{chooser_kind}_accept_result",
        "ok": False,
        "status": status,
        "accepted_action_ran": False,
        "accepted_action_id": action_id or (action or {}).get("id"),
        "reason": reason,
        "requires": required_fields,
        "action": dict(action or {}),
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": status == "explicit_write_required",
        },
    }


def _command_argv(command: str) -> list[str] | None:
    if any(marker in command for marker in ("{", "}", "<", ">")):
        return None
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not parts or parts[0] != "aippocampus":
        return None
    return parts[1:]


def accepted_action_from_payload(
    payload: Mapping[str, Any],
    *,
    action_id: str | None,
) -> AcceptedAction:
    chooser_kind = str(payload.get("kind") or "aippocampus_chooser")
    action = _selected_action(payload, action_id)
    if not action:
        return AcceptedAction(
            {},
            None,
            _block_payload(
                chooser_kind=chooser_kind,
                status="needs_input",
                reason="accepted_action_not_found",
                action=None,
                action_id=action_id,
            ),
        )
    if action.get("template_only") or action.get("requires"):
        return AcceptedAction(
            action,
            None,
            _block_payload(
                chooser_kind=chooser_kind,
                status="needs_input",
                reason="selected_action_needs_input",
                action=action,
                action_id=str(action.get("id") or action_id or ""),
            ),
        )
    mutation_risk = str(action.get("mutation_risk") or "")
    if mutation_risk not in READ_ONLY_MUTATION_RISKS:
        return AcceptedAction(
            action,
            None,
            _block_payload(
                chooser_kind=chooser_kind,
                status="explicit_write_required",
                reason="selected_action_is_not_read_only",
                action=action,
                action_id=str(action.get("id") or action_id or ""),
            ),
        )
    command = str(action.get("command") or "")
    argv = _command_argv(command)
    if not argv:
        return AcceptedAction(
            action,
            None,
            _block_payload(
                chooser_kind=chooser_kind,
                status="needs_input",
                reason="selected_action_has_no_concrete_facade_command",
                action=action,
                action_id=str(action.get("id") or action_id or ""),
            ),
        )
    invocation = resolve_command(argv)
    if invocation is None:
        return AcceptedAction(
            action,
            None,
            _block_payload(
                chooser_kind=chooser_kind,
                status="needs_input",
                reason="selected_action_command_not_supported_by_facade",
                action=action,
                action_id=str(action.get("id") or action_id or ""),
            ),
        )
    return AcceptedAction(action, invocation, None)


def accept_result_payload(
    *,
    chooser_kind: str,
    action: Mapping[str, Any],
    exit_code: int,
    stdout_text: str,
    stderr_text: str,
) -> dict[str, Any]:
    stripped_stdout = stdout_text.strip()
    parsed: Any = None
    if stripped_stdout:
        try:
            parsed = json.loads(stripped_stdout)
        except json.JSONDecodeError:
            parsed = {"stdout": stripped_stdout}
    return {
        "kind": f"{chooser_kind}_accept_result",
        "ok": exit_code == 0,
        "status": "accepted_action_ran" if exit_code == 0 else "accepted_action_failed",
        "accepted_action_ran": True,
        "accepted_action_id": action.get("id"),
        "action": dict(action),
        "exit_code": exit_code,
        "result": parsed,
        "stderr": stderr_text.strip(),
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": False,
        },
    }


__all__ = [
    "AcceptedAction",
    "ChooserTail",
    "accept_result_payload",
    "accepted_action_from_payload",
    "chooser_tail_supported",
    "parse_chooser_tail",
]
