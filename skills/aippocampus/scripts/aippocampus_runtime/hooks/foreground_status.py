"""Foreground action-card helpers for individual hook status surfaces.

These cards are deliberately about host setup, not memory truth. Keep raw hook
commands and local paths out of the foreground contract; installers can still
offer operator-only diagnostics through their existing private flags.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    foreground_shell_action,
)

CLAIM_BOUNDARY = "host_setup_not_memory_evidence"
OWNER_SURFACE = "codex_hooks_json"


def _no_action_needed(*, label: str, message: str) -> dict[str, Any]:
    return {
        "id": "no_action_needed",
        "label": label,
        "message": message,
        "mutation_risk": "read_only",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _dedupe_actions(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for action in actions:
        action_id = str(action.get("id") or "")
        command = str(action.get("command") or "")
        key = (action_id, command)
        if not action_id or key in seen:
            continue
        seen.add(key)
        out.append(dict(action))
    return out


def _status_action(*, action_id: str, label: str, command: str) -> dict[str, Any]:
    return dict(
        foreground_shell_action(
            action_id=action_id,
            label=label,
            command=command,
            why="Read-only status check; does not mutate hooks or prove runtime firing.",
            mutation_risk="read_only",
            claim_boundary=CLAIM_BOUNDARY,
        )
    )


def _write_action(*, action_id: str, label: str, command: str, why: str) -> dict[str, Any]:
    return dict(
        foreground_shell_action(
            action_id=action_id,
            label=label,
            command=command,
            why=why,
            mutation_risk="explicit_config_write",
            claim_boundary=CLAIM_BOUNDARY,
        )
    )


def _hook_card(
    *,
    surface: str,
    title: str,
    status: str,
    installed: bool,
    primary: Mapping[str, Any],
    safe_actions: Sequence[Mapping[str, Any]],
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "aippocampus_hook_status_foreground_action",
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "surface": surface,
        "title": title,
        "status": status,
        "installed": bool(installed),
        "owner_surface": OWNER_SURFACE,
        "owner_path": OWNER_SURFACE,
        "primary": dict(primary),
        "safe_next_actions": _dedupe_actions(safe_actions),
        "claim_boundary": CLAIM_BOUNDARY,
        "privacy_boundary": {
            "local_path_serialized": False,
            "hook_command_serialized": False,
            "status_is_host_setup_not_memory_evidence": True,
        },
        **dict(extra or {}),
    }


def contract_fields(card: Mapping[str, Any]) -> dict[str, Any]:
    primary = dict(card.get("primary") or {})
    safe_actions = [dict(action) for action in card.get("safe_next_actions") or []]
    return {
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "foreground_action": dict(card),
        "agent_next_action": primary,
        "safe_next_actions": safe_actions,
        "claim_boundary": str(card.get("claim_boundary") or CLAIM_BOUNDARY),
    }


def prompt_status_contract(
    *,
    status: str,
    installed: bool,
    command_count: int,
    provider_key_bridge_installed: bool,
) -> dict[str, Any]:
    if status == "installed":
        primary = _no_action_needed(
            label="Prompt hook ready",
            message="No foreground prompt-hook setup action is needed.",
        )
    elif status == "stale":
        primary = _write_action(
            action_id="refresh_prompt_hook",
            label="Refresh prompt hook",
            command="aippocampus hooks prompt install --json",
            why="Reinstall explicitly to replace legacy prompt-hook wiring.",
        )
    else:
        primary = _write_action(
            action_id="install_prompt_hook",
            label="Install prompt hook",
            command="aippocampus hooks prompt install --json",
            why="Install explicitly if Codex prompt-time continuity should be enabled.",
        )
    card = _hook_card(
        surface="prompt_hook_status",
        title="Prompt hook",
        status=status,
        installed=installed,
        primary=primary,
        safe_actions=[
            primary,
            _status_action(
                action_id="check_prompt_hook_status",
                label="Check prompt hook status",
                command="aippocampus hooks prompt status --last --json",
            ),
            _write_action(
                action_id="rollback_prompt_hook",
                label="Rollback prompt hook",
                command="aippocampus hooks prompt uninstall --json",
                why="Explicit rollback removes AIppocampus prompt hook wiring.",
            ),
        ],
        extra={
            "command_count": int(command_count),
            "provider_key_bridge_installed": bool(provider_key_bridge_installed),
        },
    )
    return contract_fields(card)


def lifecycle_status_contract(
    *,
    status: str,
    installed_events: Sequence[str],
    missing_events: Sequence[str],
    provider_key_bridge_installed: bool,
    windows_hidden_launch_status: str,
) -> dict[str, Any]:
    if status == "installed":
        primary = _no_action_needed(
            label="Lifecycle hooks ready",
            message="No foreground lifecycle-hook setup action is needed.",
        )
    elif status == "partial":
        primary = _write_action(
            action_id="refresh_lifecycle_hooks",
            label="Refresh lifecycle hooks",
            command="aippocampus hooks lifecycle install --json",
            why="Reinstall explicitly to restore missing lifecycle events.",
        )
    elif status == "stale":
        primary = _write_action(
            action_id="refresh_lifecycle_hooks",
            label="Refresh lifecycle hooks",
            command="aippocampus hooks lifecycle install --json",
            why="Reinstall explicitly to refresh stale lifecycle hook launchers.",
        )
    else:
        primary = _write_action(
            action_id="install_lifecycle_hooks",
            label="Install lifecycle hooks",
            command="aippocampus hooks lifecycle install --json",
            why="Install explicitly if Codex lifecycle continuity upkeep should be enabled.",
        )
    card = _hook_card(
        surface="lifecycle_hook_status",
        title="Lifecycle hooks",
        status=status,
        installed=status == "installed",
        primary=primary,
        safe_actions=[
            primary,
            _status_action(
                action_id="check_lifecycle_hook_status",
                label="Check lifecycle hook status",
                command="aippocampus hooks lifecycle status --json",
            ),
            _write_action(
                action_id="rollback_lifecycle_hooks",
                label="Rollback lifecycle hooks",
                command="aippocampus hooks lifecycle uninstall --json",
                why="Explicit rollback removes AIppocampus lifecycle hook wiring.",
            ),
        ],
        extra={
            "installed_events": list(installed_events),
            "missing_events": list(missing_events),
            "provider_key_bridge_installed": bool(provider_key_bridge_installed),
            "windows_hidden_launch_status": windows_hidden_launch_status,
        },
    )
    return contract_fields(card)


_ACTION_STEP_IDS = {
    "check": "check_action_hint_status",
    "prepare_cache": "refresh_action_hint_cache",
    "refresh_cache": "refresh_action_hint_cache",
    "install": "install_action_hint_hook",
    "rollback": "rollback_action_hint_hook",
}

_ACTION_STEP_RISK = {
    "check": "read_only",
    "prepare_cache": "explicit_local_cache_write",
    "refresh_cache": "explicit_local_cache_write",
    "install": "explicit_config_write",
    "rollback": "explicit_config_write",
}


def _action_hint_step_action(step: Mapping[str, Any], *, claim_boundary: str) -> dict[str, Any]:
    label = str(step.get("label") or "action")
    command = str(step.get("command") or "")
    return dict(
        foreground_shell_action(
            action_id=_ACTION_STEP_IDS.get(label, f"action_hint_{label}"),
            label=label.replace("_", " ").title(),
            command=command,
            why="Mapped from frontstage_card.next_steps for the shared hook action contract.",
            mutation_risk=_ACTION_STEP_RISK.get(label, "read_only"),
            claim_boundary=claim_boundary,
        )
    )


def action_hint_status_contract(frontstage_card: Mapping[str, Any]) -> dict[str, Any]:
    status = str(frontstage_card.get("status") or "unknown")
    ready = bool(frontstage_card.get("ready"))
    installed = bool(frontstage_card.get("installed"))
    claim_boundary = str(frontstage_card.get("claim_boundary") or CLAIM_BOUNDARY)
    steps = [step for step in frontstage_card.get("next_steps") or [] if isinstance(step, Mapping)]
    mapped_steps = [
        _action_hint_step_action(step, claim_boundary=claim_boundary)
        for step in steps
        if step.get("command")
    ]
    if ready:
        primary = _no_action_needed(
            label="Action-time hints ready",
            message="No foreground action-hint setup action is needed.",
        )
        primary["claim_boundary"] = claim_boundary
    else:
        primary = next(
            (
                action
                for action in mapped_steps
                if action.get("id")
                in {
                    "refresh_action_hint_cache",
                    "install_action_hint_hook",
                }
            ),
            mapped_steps[0]
            if mapped_steps
            else _status_action(
                action_id="check_action_hint_status",
                label="Check action-hint hook status",
                command="aippocampus hooks action status --json",
            ),
        )
    card = _hook_card(
        surface="action_hint_hook_status",
        title="Action-time hints",
        status=status,
        installed=installed,
        primary=primary,
        safe_actions=[primary, *mapped_steps],
        extra={
            "ready": ready,
            "cache_status": str(frontstage_card.get("cache_status") or status),
            "cache_path_label": str(frontstage_card.get("cache_path_label") or ""),
            "cache_scope": str(frontstage_card.get("cache_scope") or ""),
        },
    )
    card["claim_boundary"] = claim_boundary
    return contract_fields(card)
