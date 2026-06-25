"""Foreground recovery card helpers for MCP tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.mcp.result_profile import render_profiled_result


def _action_map(action: Any) -> dict[str, Any]:
    return dict(action) if isinstance(action, Mapping) else {}


def compact_missing_input_recovery_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project missing-input recovery into an action-sized MCP card.

    Missing-argument errors are part of the foreground UX: a model sees them
    when it needs to recover from an invalid call. Keep the operator/source
    boundary detail in the full profile and give compact only the state, the
    primary template action, and a tiny list of safe follow-up actions.
    """

    error = _action_map(payload.get("error"))
    primary_action = _action_map(payload.get("foreground_action"))
    required_any = error.get("required_any") or primary_action.get("requires")
    compact_error = core.strip_empty(
        {
            "code": error.get("code"),
            "message": error.get("message"),
            "tool_name": error.get("tool_name") or primary_action.get("tool_name"),
            "required_any": required_any,
        }
    )
    safe_next_actions = [
        _action_map(action)
        for action in payload.get("safe_next_actions") or []
        if _action_map(action)
    ][:3]
    foreground_fields = (
        canonical_foreground_action_fields(
            primary_action,
            safe_next_actions=safe_next_actions,
        )
        if primary_action
        else {}
    )
    staged_followup = [
        _action_map(action)
        for action in payload.get("staged_followup") or []
        if _action_map(action)
    ][:3]
    return core.strip_empty(
        {
            "detail": "compact",
            "kind": payload.get("kind"),
            "surface": "mcp_missing_input_recovery_compact",
            "ok": False,
            "status": payload.get("status"),
            "surface_class": payload.get("surface_class"),
            "summary": compact_error.get("message"),
            "error": compact_error,
            "required_any": compact_error.get("required_any"),
            **foreground_fields,
            "staged_followup": staged_followup,
        }
    )


def missing_input_recovery_card(
    *,
    code: str,
    message: str,
    tool_name: str,
    arguments: dict[str, Any],
    required_any: list[str],
    safe_next_actions: list[dict[str, Any]],
    staged_followup: list[dict[str, Any]] | None = None,
    legacy_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "required_any": required_any,
        "next_step_hint": (
            f"Call {safe_next_actions[0]['tool_name']} with the suggested arguments."
            if safe_next_actions
            else None
        ),
        "arguments_template": safe_next_actions[0].get("arguments_template") if safe_next_actions else {},
    }
    if legacy_details:
        details.update(legacy_details)
    if safe_next_actions:
        details["foreground_action"] = dict(safe_next_actions[0])
    payload: dict[str, Any] = {
        "kind": "aippocampus_mcp_missing_input_recovery",
        "ok": False,
        "status": "needs_input",
        "surface_class": "foreground_recovery_card",
        "error": {
            "code": code,
            "message": message,
            "tool_name": tool_name,
            "required_any": required_any,
            "details": details,
        },
        **canonical_foreground_action_fields(
            safe_next_actions[0] if safe_next_actions else {},
            safe_next_actions=safe_next_actions,
        ),
        "source_boundary": {
            "claim_authority": "none_until_source_reopened",
            "navigation_only": True,
            "source_reopen_required_before_claim": True,
        },
        "related_issue": "https://github.com/Sapientropic/AIppocampus/issues/2057",
    }
    if staged_followup:
        payload["staged_followup"] = staged_followup
    return render_profiled_result(
        arguments,
        payload,
        is_error=True,
        compact_projector=compact_missing_input_recovery_payload,
        full_output_boundary="local_private_recovery_detail",
    )


def template_tool_action(
    tool_name: str,
    arguments_template: dict[str, Any],
    requires: list[str],
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "arguments_template": arguments_template,
        "requires": requires,
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
    }


def register_thread_recovery(arguments: dict[str, Any], message: str) -> dict[str, Any]:
    actions = [
        template_tool_action(
            "list_threads",
            {"cwd": "{project_cwd}", "detail": "compact"},
            ["cwd"],
        ),
        template_tool_action(
            "register_thread",
            {
                "cwd": "{project_cwd}",
                "provider": "{provider}",
                "confirm_write": True,
            },
            ["cwd", "provider", "confirm_write"],
        )
        | {
            "mutation_risk": "explicit_local_registry_write",
            "claim_boundary": "registry_write_not_source_claim",
            "why": "Only write after the user has chosen the provider and confirmed local registry registration.",
        },
        template_tool_action(
            "memory_health",
            {"cwd": "{project_cwd}", "detail": "compact"},
            ["cwd"],
        ),
    ]
    return missing_input_recovery_card(
        code="explicit_write_required",
        message=message,
        tool_name="register_thread",
        arguments=arguments,
        required_any=["cwd", "provider", "confirm_write"],
        safe_next_actions=actions,
        staged_followup=[
            actions[0],
            actions[1],
        ],
        legacy_details={
            "write_effect": "register_current_thread",
            "explicit_write_required": True,
        },
    )
