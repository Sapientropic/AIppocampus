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
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
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


def _first_recall_template(*, action_id: str, label: str, why: str) -> dict[str, Any]:
    action = dict(
        foreground_template_action(
            action_id=action_id,
            label=label,
            command_template='aippocampus agent recall "{continuity_cue}" --json',
            requires=["continuity_cue"],
            why=why,
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
    )
    # The shell template is for humans and logs; foreground agents should not
    # have to parse a command string to discover the MCP/CLI-equivalent call.
    action.update(
        {
            "tool_name": "agent_recall",
            "tool_args_template": {
                "cue": "{continuity_cue}",
                "detail": "compact",
            },
        }
    )
    return action


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


def contract_fields(
    card: Mapping[str, Any],
    *,
    safe_next_read_only_only: bool = True,
) -> dict[str, Any]:
    primary = dict(card.get("primary") or {})
    safe_actions = [dict(action) for action in card.get("safe_next_actions") or []]
    action_fields = canonical_foreground_action_fields(
        primary,
        safe_next_actions=safe_actions,
        safe_next_read_only_only=safe_next_read_only_only,
    )
    card_fields = {
        key: value
        for key, value in dict(card).items()
        if key
        not in {
            "foreground_action_contract",
            "foreground_action",
            "agent_next_action",
            "safe_next_actions",
            "primary",
        }
    }
    return {
        **card_fields,
        **action_fields,
        "claim_boundary": str(card.get("claim_boundary") or CLAIM_BOUNDARY),
    }


def hook_install_closeout_contract(
    *,
    surface: str,
    title: str,
    status: str,
    primary: Mapping[str, Any],
    status_command: str,
    rollback_command: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the foreground-safe install closeout shared by hook installers.

    Install closeouts are often pasted back to agents as compact JSON. Keep
    runnable foreground actions, but keep hooks.json paths and host hook command
    strings on operator-only surfaces so a success card cannot become a local
    machine inventory dump.
    """

    card = _hook_card(
        surface=surface,
        title=title,
        status=status,
        installed=status
        in {
            "installed_ready",
            "installed_but_not_ready",
            "installed_useful",
            "installed_active_needs_probe",
            "installed_needs_cache",
        },
        primary=primary,
        safe_actions=[
            primary,
            _status_action(
                action_id="status",
                label="Check hook status",
                command=status_command,
            ),
            _write_action(
                action_id="rollback",
                label="Rollback hook install",
                command=rollback_command,
                why="Explicit rollback removes the hook wiring installed by this command.",
            ),
        ],
        extra={
            "install_closeout": True,
            **dict(extra or {}),
        },
    )
    card["kind"] = "aippocampus_hook_install_closeout_foreground_action"
    fields = contract_fields(card, safe_next_read_only_only=False)
    fields["privacy_boundary"] = dict(card["privacy_boundary"])
    return fields


def no_action_needed_install_primary(*, label: str, message: str) -> dict[str, Any]:
    return _no_action_needed(label=label, message=message)


def action_hint_cache_refresh_primary(*, claim_boundary: str = CLAIM_BOUNDARY) -> dict[str, Any]:
    return dict(
        foreground_shell_action(
            action_id="refresh_action_hint_cache",
            label="Refresh action-hint cache",
            command="aippocampus hooks action refresh-cache --write --json",
            why="Prepare trusted action-hint input before treating the hook as useful.",
            mutation_risk="explicit_local_cache_write",
            claim_boundary=claim_boundary,
        )
    )


def prompt_status_contract(
    *,
    status: str,
    installed: bool,
    command_count: int,
    provider_key_bridge_installed: bool,
    last_prompt_hook: Mapping[str, Any] | None = None,
    latency_risk: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    last_summary = (
        last_prompt_hook.get("last_prompt_hook")
        if isinstance(last_prompt_hook, Mapping)
        and isinstance(last_prompt_hook.get("last_prompt_hook"), Mapping)
        else None
    )
    useful_last_count = 0
    if isinstance(last_summary, Mapping):
        useful_last_count = sum(
            int(last_summary.get(key) or 0)
            for key in ("source_backed_count", "candidate_count", "scent_count", "wayfinding_count")
        )
    last_repair = str((last_summary or {}).get("next_repair") or "")
    latency_status = str((latency_risk or {}).get("status") or "")
    latency_current_status = str((latency_risk or {}).get("current_status") or latency_status)
    latency_freshness_status = str((latency_risk or {}).get("freshness_status") or "")
    latency_historical_status = str((latency_risk or {}).get("historical_status") or "")
    latency_repair = str((latency_risk or {}).get("repair_action") or "")
    latency_repair_action = None
    last_prompt_hook_review = None
    if status == "installed" and latency_current_status == "near_host_timeout_risk":
        primary = _status_action(
            action_id="inspect_prompt_hook_output",
            label="Inspect prompt hook output",
            command="aippocampus hooks prompt status --last --json",
        )
        primary["why"] = (
            "Fresh prompt-hook telemetry is near the host timeout; keep the foreground "
            "step read-only and refresh only if the user chooses repair."
        )
        latency_repair_action = _write_action(
            action_id="refresh_prompt_hook_safe_budget",
            label="Refresh prompt hook safe budget",
            command=latency_repair or "aippocampus hooks prompt install --json",
            why=(
                "Fresh prompt-hook telemetry shows near-host-timeout runs; "
                "reinstall with the safer foreground budget only as an explicit repair."
            ),
        )
    elif status == "installed" and useful_last_count:
        surface = str((last_summary or {}).get("memory_surface") or "memory")
        last_prompt_hook_review = {
            "id": "review_last_prompt_hook_recall",
            "label": "Review last prompt-hook recall",
            "message": (
                f"Last prompt hook surfaced {useful_last_count} {surface} signal(s); "
                "use the compact counters as navigation and reopen/deepen source before claims."
            ),
            "signal_count": useful_last_count,
            "memory_surface": surface,
        }
        primary = _first_recall_template(
            action_id="try_first_recall_after_prompt_hook",
            label="Try first recall",
            why=(
                "Last prompt-hook counters are setup telemetry, not a source route; run "
                "a bounded recall cue and deepen/open source before claims."
            ),
        )
    elif status == "installed" and last_repair:
        primary = _status_action(
            action_id="repair_last_prompt_hook_result",
            label="Repair last prompt-hook result",
            command=last_repair,
        )
        primary["claim_boundary"] = "last_prompt_hook_repair_not_memory_evidence"
    elif status == "installed":
        primary = _status_action(
            action_id="inspect_prompt_hook_output",
            label="Inspect prompt hook output",
            command="aippocampus hooks prompt status --last --json",
        )
        primary["why"] = (
            "Installed wiring is only setup state; inspect the last hook output or "
            "try ordinary recall before treating continuity as useful."
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
            _first_recall_template(
                action_id="try_first_recall_after_prompt_hook",
                label="Try first recall",
                why="Use source-backed recall to verify the foreground continuity path, not hook installation alone.",
            ),
            _status_action(
                action_id="check_prompt_hook_status",
                label="Check prompt hook status",
                command="aippocampus hooks prompt status --last --json",
            ),
            *([latency_repair_action] if latency_repair_action else []),
        ],
        extra={
            "command_count": int(command_count),
            "provider_key_bridge_installed": bool(provider_key_bridge_installed),
            "prompt_hook_latency_risk_status": latency_current_status,
            "prompt_hook_latency_current_status": latency_current_status,
            "prompt_hook_latency_freshness_status": latency_freshness_status,
            "prompt_hook_latency_historical_status": latency_historical_status,
            "foreground_latency_red_line_violation_count": int(
                (latency_risk or {}).get("foreground_latency_red_line_violation_count") or 0
            ),
            "prompt_hook_near_timeout_event_count": int(
                (latency_risk or {}).get("near_timeout_event_count") or 0
            ),
            **(
                {"last_prompt_hook_review": last_prompt_hook_review}
                if last_prompt_hook_review
                else {}
            ),
            "historical_foreground_latency_red_line_violation_count": int(
                (latency_risk or {}).get("historical_foreground_latency_red_line_violation_count")
                or 0
            ),
            "historical_prompt_hook_near_timeout_event_count": int(
                (latency_risk or {}).get("historical_near_timeout_event_count") or 0
            ),
            "last_prompt_hook_status": str(last_prompt_hook.get("status") or "")
            if isinstance(last_prompt_hook, Mapping)
            else "",
            "last_prompt_hook_memory_surface": str((last_summary or {}).get("memory_surface") or "")
            if isinstance(last_summary, Mapping)
            else "",
            "last_prompt_hook_useful_signal_count": useful_last_count,
            "manage_command": "aippocampus hooks prompt uninstall --json",
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
        primary = _first_recall_template(
            action_id="try_first_recall_after_lifecycle_hooks",
            label="Try first recall",
            why=(
                "Lifecycle hooks only prove setup wiring; use read-only recall to "
                "check whether useful continuity is available now."
            ),
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
        ],
        extra={
            "installed_events": list(installed_events),
            "missing_events": list(missing_events),
            "provider_key_bridge_installed": bool(provider_key_bridge_installed),
            "windows_hidden_launch_status": windows_hidden_launch_status,
            "manage_command": "aippocampus hooks lifecycle uninstall --json",
        },
    )
    return contract_fields(card)
