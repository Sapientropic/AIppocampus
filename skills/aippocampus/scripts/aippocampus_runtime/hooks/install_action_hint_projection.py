"""Public projections for the Codex action-hint hook installer."""

# aippocampus-instruction-surface: action-hint install/status compact projection owner; operator diagnostics stay behind explicit detail commands.

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import foreground_action_is_read_only, foreground_shell_action
from aippocampus_runtime.foreground_compact_language import strip_compact_policy_vocabulary
from aippocampus_runtime.hooks.action_hint_cache import DEFAULT_ACTION_HINT_CACHE_LABEL
from aippocampus_runtime.hooks.foreground_status import (
    CLAIM_BOUNDARY,
    _hook_card,
    _status_action,
    contract_fields,
    hook_install_closeout_contract,
    no_action_needed_install_primary,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


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
        first_command = "aippocampus hooks action probe --compact-json"
    else:
        first_command = "aippocampus hooks action probe --compact-json"
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
        next_steps.append(
            {
                "label": "probe",
                "command": first_command,
                "mutation_risk": "low_risk_local_cache_write",
            }
        )
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
        "writes": [
            "Codex hooks.json only during explicit install/uninstall",
            "prepared action-hint cache during explicit probe auto-chain",
        ],
        "next_steps": next_steps,
        "claim_boundary": "Hints are route guidance only; reopen or deepen source before claims.",
    }


_ACTION_STEP_IDS = {
    "check": "check_action_hint_status",
    "review_guidance": "review_action_hint_guidance",
    "prepare_cache": "refresh_action_hint_cache",
    "refresh_cache": "refresh_action_hint_cache",
    "probe": "probe_action_hint_hot_path",
    "install": "install_action_hint_hook",
    "rollback": "rollback_action_hint_hook",
}

_ACTION_STEP_RISK = {
    "check": "read_only",
    "review_guidance": "read_only",
    "prepare_cache": "explicit_local_cache_write",
    "refresh_cache": "explicit_local_cache_write",
    "probe": "read_only",
    "install": "explicit_config_write",
    "rollback": "explicit_config_write",
}


def _action_hint_step_action(step: Mapping[str, Any], *, claim_boundary: str) -> dict[str, Any]:
    label = str(step.get("label") or "action")
    command = str(step.get("command") or "")
    mutation_risk = str(step.get("mutation_risk") or _ACTION_STEP_RISK.get(label) or "read_only")
    why_by_id = {
        "review_action_hint_guidance": (
            "Review whether prepared or semantic learning guidance exists before "
            "writing the action-hint cache."
        ),
        "refresh_action_hint_cache": (
            "Refresh the prepared action-hint cache so the installed PreToolUse "
            "hook has useful navigation records."
        ),
        "install_action_hint_hook": (
            "Install the action-time hook so trusted Codex sessions can receive "
            "prepared navigation hints without blocking ordinary recall."
        ),
        "rollback_action_hint_hook": (
            "Remove action-time hook wiring if the local host setup needs to be "
            "rolled back."
        ),
        "check_action_hint_status": (
            "Recheck whether action-time hints are installed and have prepared "
            "records available."
        ),
        "probe_action_hint_hot_path": (
            "Run a live PreToolUse-shaped probe; only a matched hint with a "
            "follow-through source route proves useful action-time behavior."
        ),
    }
    action_id = _ACTION_STEP_IDS.get(label, f"action_hint_{label}")
    return dict(
        foreground_shell_action(
            action_id=action_id,
            label=label.replace("_", " ").title(),
            command=command,
            why=why_by_id.get(
                action_id,
                "Use this hook action to keep action-time navigation hints aligned with the installed host setup.",
            ),
            mutation_risk=mutation_risk,
            claim_boundary=claim_boundary,
        )
    )


def action_hint_status_contract(frontstage_card: Mapping[str, Any]) -> dict[str, Any]:
    status = str(frontstage_card.get("status") or "unknown")
    useful = bool(frontstage_card.get("useful"))
    installed = bool(frontstage_card.get("installed"))
    claim_boundary = str(frontstage_card.get("claim_boundary") or CLAIM_BOUNDARY)
    steps = [step for step in frontstage_card.get("next_steps") or [] if isinstance(step, Mapping)]
    mapped_steps = [
        _action_hint_step_action(step, claim_boundary=claim_boundary)
        for step in steps
        if step.get("command")
    ]
    refresh_action = next(
        (action for action in mapped_steps if action.get("id") == "refresh_action_hint_cache"),
        None,
    )
    install_action = next(
        (action for action in mapped_steps if action.get("id") == "install_action_hint_hook"),
        None,
    )
    review_action = next(
        (action for action in mapped_steps if action.get("id") == "review_action_hint_guidance"),
        None,
    )
    if (
        isinstance(install_action, dict)
        and isinstance(refresh_action, dict)
        and foreground_action_is_read_only(refresh_action)
    ):
        install_action["follow_up_action"] = {
            key: refresh_action[key]
            for key in ("id", "label", "command", "mutation_risk", "claim_boundary")
            if key in refresh_action
        }
    if (
        isinstance(review_action, dict)
        and isinstance(install_action, dict)
        and foreground_action_is_read_only(install_action)
    ):
        review_action["follow_up_action"] = {
            key: install_action[key]
            for key in ("id", "label", "command", "mutation_risk", "claim_boundary")
            if key in install_action
        }
    elif (
        isinstance(review_action, dict)
        and isinstance(refresh_action, dict)
        and foreground_action_is_read_only(refresh_action)
    ):
        review_action["follow_up_action"] = {
            key: refresh_action[key]
            for key in ("id", "label", "command", "mutation_risk", "claim_boundary")
            if key in refresh_action
        }
    if useful:
        primary = _status_action(
            action_id="check_action_hint_status",
            label="Check action-hint hook status",
            command="aippocampus hooks action status --json",
        )
        primary["claim_boundary"] = claim_boundary
        primary["why"] = (
            "Useful action-time hints are navigation setup, not source evidence; "
            "status stays read-only and ordinary recall remains the proof path."
        )
    elif not installed and isinstance(review_action, dict):
        primary = review_action
    elif installed and isinstance(refresh_action, dict):
        primary = refresh_action
    elif installed:
        probe_action = next(
            (action for action in mapped_steps if action.get("id") == "probe_action_hint_hot_path"),
            None,
        )
        primary = (
            dict(probe_action)
            if isinstance(probe_action, dict)
            else next(
                (
                    action
                    for action in mapped_steps
                    if action.get("id")
                    in {
                        "check_action_hint_status",
                        "review_action_hint_guidance",
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
        )
    else:
        primary = next(
            (
                action
                for action in mapped_steps
                if action.get("id")
                in {
                    "check_action_hint_status",
                    "review_action_hint_guidance",
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
    compact_steps = [action for action in mapped_steps if foreground_action_is_read_only(action)]
    card = _hook_card(
        surface="action_hint_hook_status",
        title="Action-time hints",
        status=status,
        installed=installed,
        primary=primary,
        safe_actions=[primary, *compact_steps],
        extra={
            "stage": str(frontstage_card.get("stage") or status),
            "stage_values": ["installed", "callable", "active", "useful"],
            "useful": useful,
            "cache_status": str(frontstage_card.get("cache_status") or status),
            "cache_path_label": str(frontstage_card.get("cache_path_label") or ""),
            "cache_scope": str(frontstage_card.get("cache_scope") or ""),
            "manage_command": (
                "aippocampus hooks action uninstall --json"
                if installed
                else "aippocampus hooks action install --json"
            ),
        },
    )
    card["claim_boundary"] = claim_boundary
    return contract_fields(card)


def compact_action_hint_status_result(
    result: Mapping[str, Any],
    *,
    event: str,
) -> dict[str, Any]:
    """Project action-hint status into the default foreground card.

    Full hook status keeps operator repair detail such as paths, commands,
    cache-line diagnostics, and provider counts. The compact card deliberately
    answers only whether action-time hints are usable and what the next safe
    foreground action is, so status checks do not become a duplicate hooks
    inventory.
    """

    raw_card = result.get("frontstage_card")
    frontstage_card = raw_card if isinstance(raw_card, Mapping) else {}
    public = action_hint_status_contract(frontstage_card)
    privacy = dict(public.get("privacy_boundary") or {})
    privacy.update(
        {
            "local_path_serialized": False,
            "hook_command_serialized": False,
            "cache_path_serialized": False,
            "raw_cache_diagnostics_omitted": True,
        }
    )
    public.update(
        {
            "kind": "aippocampus_action_hint_status_compact",
            "title": "Action-time hints",
            "stage": str(frontstage_card.get("stage") or public.get("status") or ""),
            "useful": bool(frontstage_card.get("useful")),
            "optional": bool(frontstage_card.get("optional")),
            "fail_open": bool(frontstage_card.get("fail_open")),
            "recall_blocking": bool(frontstage_card.get("recall_blocking")),
            "hot_path_active": bool(frontstage_card.get("hot_path_active")),
            "warning_state": str(frontstage_card.get("warning_state") or ""),
            "setup_role": str(frontstage_card.get("setup_role") or ""),
            "event": event,
            "support_status": str(result.get("support_status") or ""),
            "cache_status": str(frontstage_card.get("cache_status") or public.get("status") or ""),
            "cache_record_count": int(frontstage_card.get("cache_record_count") or 0),
            "fresh_record_count": int(frontstage_card.get("fresh_record_count") or 0),
            "cache_path_label": str(
                frontstage_card.get("cache_path_label") or DEFAULT_ACTION_HINT_CACHE_LABEL
            ),
            "cache_scope": str(frontstage_card.get("cache_scope") or "unknown"),
            "privacy_boundary": privacy,
        }
    )
    public.pop("owner_path", None)
    compact = strip_compact_policy_vocabulary(
        public,
        extra_denied_keys=frozenset({"authority", "diagnostic_fields_omitted"}),
    )
    return redact_sensitive_values(redact_private_paths(compact))


def redact_public_result(result: Mapping[str, Any], *, path: Path) -> dict[str, Any]:
    public = dict(result)
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
    public.pop("next_command", None)
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
                command="aippocampus hooks action probe --compact-json",
                why=(
                    "A fresh cache is installed; run a live PreToolUse-shaped probe "
                    "before calling action-time hints useful."
                ),
                mutation_risk="read_only",
                claim_boundary="action_hints_are_navigation_not_source_truth",
            )
        )
        if active
        else dict(
            foreground_shell_action(
                action_id="probe_action_hint_hot_path",
                label="Probe action-hint hot path",
                command="aippocampus hooks action probe --compact-json",
                why=(
                    "The hook is installed but the prepared cache is not useful yet; "
                    "the explicit probe may auto-refresh the local cache, then report "
                    "whether a source route can be followed."
                ),
                mutation_risk="low_risk_local_cache_write",
                claim_boundary=str(
                    public.get("claim_boundary") or "host_setup_not_memory_evidence"
                ),
            )
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
