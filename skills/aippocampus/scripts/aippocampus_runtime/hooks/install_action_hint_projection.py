"""Public projections for the Codex action-hint hook installer."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action
from aippocampus_runtime.hooks.action_hint_cache import DEFAULT_ACTION_HINT_CACHE_LABEL
from aippocampus_runtime.hooks.foreground_status import (
    action_hint_cache_refresh_primary,
    hook_install_closeout_contract,
    no_action_needed_install_primary,
)


def action_hint_frontstage_card(
    status_result: Mapping[str, Any],
    *,
    event: str = "PreToolUse",
) -> dict[str, Any]:
    cache_status = str(status_result.get("cache_status") or "not_installed")
    installed = bool(status_result.get("installed"))
    active = installed and cache_status == "with_fresh_records"
    useful = False
    stage = "active" if active else "callable" if installed else "installed"
    warning_state = "" if active else "installed_cache_not_useful" if installed else ""
    hot_path_active = active
    if not installed:
        first_command = "aippocampus learning guidance --json"
    elif not active:
        first_command = "aippocampus hooks action refresh-cache --write --json"
    else:
        first_command = "aippocampus hooks action probe --json"
    next_steps = [{"label": "check", "command": "aippocampus hooks action status --json"}]
    if not installed:
        next_steps.append({"label": "review_guidance", "command": first_command})
        next_steps.append({"label": "install", "command": "aippocampus hooks action install --json"})
        next_steps.append(
            {
                "label": "prepare_cache",
                "command": "aippocampus hooks action refresh-cache --write --json",
            }
        )
    elif not active:
        next_steps.append({"label": "refresh_cache", "command": first_command})
    else:
        next_steps.append({"label": "probe", "command": first_command})
    next_steps.append(
        {
            "label": "rollback",
            "command": "aippocampus hooks action uninstall --json",
        }
    )
    return {
        "kind": "aippocampus_action_hint_frontstage_card",
        "title": "Action-time hints",
        "status": stage,
        "stage": stage,
        "stage_values": ["installed", "callable", "active", "useful"],
        "installed": installed,
        "useful": useful,
        "setup_role": (
            "useful"
            if useful
            else "active_needs_live_probe"
            if active
            else "cleanup_or_prepare_required"
            if installed
            else "recommended_for_trusted_codex"
        ),
        "optional": False,
        "fail_open": True,
        "recall_blocking": False,
        "hot_path_active": hot_path_active,
        "warning_state": warning_state,
        "authority": "navigation_only",
        "event": event,
        "cache_status": cache_status,
        "cache_path_label": str(
            status_result.get("cache_path_label") or DEFAULT_ACTION_HINT_CACHE_LABEL
        ),
        "cache_scope": str(status_result.get("cache_scope") or "unknown"),
        "cache_record_count": int(status_result.get("cache_record_count") or 0),
        "fresh_record_count": int(status_result.get("fresh_record_count") or 0),
        "purpose": "Recommended trusted-Codex PreToolUse nudges for learned source routes; never source evidence.",
        "when_useful": [
            "after learning-loop or AIppo guidance has prepared action hints",
            "after a live PreToolUse probe matches a prepared source route",
            "before broad tests, retries, or source-sensitive edits",
        ],
        "reads": ["prepared action-hint cache"],
        "writes": ["Codex hooks.json only during explicit install/uninstall"],
        "next_steps": next_steps,
        "claim_boundary": "Hints are route guidance only; reopen or deepen source before claims.",
    }


def redact_public_result(result: Mapping[str, Any], *, path: Path) -> dict[str, Any]:
    public = dict(result)
    raw_cache_path = str(public.get("cache_path") or "")
    public["path"] = path.name
    public["path_redacted"] = True
    raw_commands = public.get("commands")
    if isinstance(raw_commands, list) and raw_commands:
        public["commands"] = ["<redacted:hook-command>" for _ in raw_commands]
        public["commands_redacted"] = True
    else:
        public["commands_redacted"] = False
    if public.get("cache_path"):
        public["cache_path"] = "<redacted:cache-jsonl>"
        public["cache_path_redacted"] = True
    else:
        public["cache_path_redacted"] = False
    next_command = public.get("next_command")
    if raw_cache_path and isinstance(next_command, str):
        public["next_command"] = "aippocampus hooks action refresh-cache --write --json"
    public.pop("command", None)
    return public


def public_install_result(result: Mapping[str, Any], *, path: Path) -> dict[str, Any]:
    public = redact_public_result(result, path=path)
    frontstage = public.get("frontstage_card") if isinstance(public.get("frontstage_card"), Mapping) else {}
    useful = bool(frontstage.get("useful"))
    active = bool(frontstage.get("hot_path_active"))
    primary = (
        no_action_needed_install_primary(
            label="Action-time hints installed",
            message="No foreground action-hint setup action is needed.",
        )
        if useful
        else dict(
            foreground_shell_action(
                action_id="probe_action_hint_hot_path",
                label="Probe action-hint hot path",
                command="aippocampus hooks action probe --json",
                why=(
                    "A fresh cache is installed; run a live PreToolUse-shaped probe "
                    "before calling action-time hints useful."
                ),
                mutation_risk="read_only",
                claim_boundary="action_hints_are_navigation_not_source_truth",
            )
        )
        if active
        else action_hint_cache_refresh_primary(
            claim_boundary=str(public.get("claim_boundary") or "host_setup_not_memory_evidence")
        )
    )
    public.pop("path", None)
    public.pop("commands", None)
    public.pop("commands_redacted", None)
    public["local_private_fields"] = ["path", "commands", "command"]
    public["operator_json_available"] = True
    public.update(
        hook_install_closeout_contract(
            surface="action_hint_hook_install",
            title="Action-time hint install",
            status=(
                "installed_useful"
                if useful
                else "installed_active_needs_probe"
                if active
                else "installed_needs_cache"
            ),
            primary=primary,
            status_command="aippocampus hooks action status --json",
            rollback_command="aippocampus hooks action uninstall --json",
            extra={
                "useful": useful,
                "cache_status": str(public.get("cache_status") or "unknown"),
                "cache_path_label": str(public.get("cache_path_label") or ""),
                "cache_scope": str(public.get("cache_scope") or ""),
            },
        )
    )
    return public
