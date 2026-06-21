"""Public projections for provider doctor reports."""

from __future__ import annotations

import json
from typing import Any

from aippocampus_runtime.cognitive_worker_mode import BACKGROUND_MODEL_CONSENT_ENV
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)
from aippocampus_runtime.model.routing import DEFAULT_DEEPSEEK_API_KEY_ENV

SCHEMA_VERSION = 1
DEFAULT_PROVIDER_ENV_VAR = DEFAULT_DEEPSEEK_API_KEY_ENV


def _public_token(value: Any, *, fallback: str = "unknown", limit: int = 96) -> str:
    text = str(value or "").strip()
    clean = "".join(char for char in text[:limit] if char.isalnum() or char in {"_", "-", "."})
    return clean or fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalized_recommended_action(action: dict[str, Any]) -> dict[str, Any]:
    command = str(action.get("command") or "").strip()
    normalized: dict[str, Any] = {
        "id": _public_token(action.get("id"), fallback="provider_doctor_action"),
        "kind": "shell_command" if command else "guidance",
        "message": str(action.get("message") or "").strip(),
        "has_command": bool(command),
    }
    if command:
        normalized["command"] = command
        normalized["mutation_risk"] = str(action.get("mutation_risk") or "read_only")
        normalized["claim_boundary"] = str(
            action.get("claim_boundary") or "provider_visibility_not_memory_evidence"
        )
    if action.get("follow_up_command"):
        normalized["follow_up_command"] = str(action["follow_up_command"])
    return {key: value for key, value in normalized.items() if value not in (None, "", [])}


def _provider_doctor_primary_action(
    report: dict[str, Any],
    normalized_actions: list[dict[str, Any]],
) -> dict[str, object]:
    command_action = next((action for action in normalized_actions if action.get("command")), None)
    if command_action:
        return foreground_shell_action(
            action_id=str(command_action.get("id") or "inspect_provider_doctor"),
            command=str(command_action["command"]),
            label="Check hook/provider visibility",
            why=str(command_action.get("message") or "Verify provider readiness in the host environment."),
            mutation_risk=str(command_action.get("mutation_risk") or "read_only"),
            claim_boundary=str(
                command_action.get("claim_boundary") or "provider_visibility_not_memory_evidence"
            ),
        )
    status = str(report.get("status") or "")
    if status == "missing_provider_env_var":
        return foreground_shell_action(
            action_id="set_provider_env_in_hook_environment",
            command="aippocampus onboard provider-key --plan --json",
            label="Plan provider-key bridge setup",
            why="The provider key is not visible to this process; plan the hook environment bridge before applying any write.",
            mutation_risk="read_only_plan",
            claim_boundary="provider_key_setup_not_memory_evidence",
        )
    if status == "route_config_error":
        return foreground_shell_action(
            action_id="inspect_model_route_config",
            command="aippocampus doctor config --detail full --json",
            label="Inspect route configuration",
            why="The configured model route is incomplete; inspect registered config without printing values.",
            mutation_risk="read_only",
            claim_boundary="config_presence_not_provider_connectivity",
        )
    return foreground_shell_action(
        action_id="inspect_provider_doctor_detail",
        command="aippocampus doctor provider --detail full --json",
        label="Inspect provider detail",
        why="Provider readiness needs operator detail before changing the hook environment.",
        mutation_risk="read_only",
        claim_boundary="provider_visibility_not_memory_evidence",
    )


def compact_provider_doctor_card(report: dict[str, Any]) -> dict[str, Any]:
    """Project provider doctor into the compact foreground decision-card shape."""

    route = _as_dict(report.get("route"))
    normalized_actions = [
        _normalized_recommended_action(action)
        for action in report.get("recommended_actions") or []
        if isinstance(action, dict)
    ]
    primary = _provider_doctor_primary_action(report, normalized_actions)
    detail_action = foreground_shell_action(
        action_id="inspect_provider_doctor_detail",
        command="aippocampus doctor provider --detail full --json",
        label="Open full provider doctor report",
        why="Use full detail only for local operator diagnosis; it includes route/env presence objects.",
        mutation_risk="read_only",
        claim_boundary="operator_detail_not_memory_evidence",
    )
    safe_actions = [primary]
    if primary.get("id") != detail_action["id"]:
        safe_actions.append(detail_action)
    action_fields = canonical_foreground_action_fields(primary, safe_next_actions=safe_actions)
    card: dict[str, Any] = {
        "schema_version": report.get("schema_version") or SCHEMA_VERSION,
        "kind": "aippocampus_provider_doctor_card",
        "detail": "compact",
        "surface": "foreground_decision_card",
        "ok": bool(report.get("ok")),
        "status": report.get("status"),
        **action_fields,
        "route_summary": {
            "requested_route": route.get("requested_route"),
            "provider": route.get("provider"),
            "model": route.get("model"),
            "provider_env_var": route.get("provider_env_var"),
            "base_url_configured": route.get("base_url_configured"),
        },
        "recommended_action_count": len(normalized_actions),
        "recommended_action_ids": [
            str(action.get("id") or "")
            for action in normalized_actions
            if str(action.get("id") or "")
        ][:5],
        "recommended_actions_deferred_to_operator_detail": bool(normalized_actions),
        "operator_detail_command": "aippocampus doctor provider --detail full --json",
        "full_audit_command": "aippocampus doctor provider --detail full --json",
        "audit_json_available": True,
        "privacy": {
            "values_printed": False,
            "local_paths_included": False,
            "base_url_value_printed": False,
            "operator_env_objects_omitted": True,
        },
        "boundary_summary": {
            "full_detail_owns_diagnostics": True,
            "detail_available_with": "aippocampus doctor provider --detail full --json",
            "frontstage_rule": "readiness and next check first; diagnostics stay in full detail",
        },
    }
    return {
        key: value
        for key, value in card.items()
        if value not in (None, "", [], {})
    }


def render_text(report: dict[str, Any]) -> str:
    route = _as_dict(report.get("route"))
    provider_env = _as_dict(report.get("provider_env"))
    lines = [
        "AIppocampus provider doctor",
        f"- Status: {report.get('status')}",
        f"- Route: {route.get('provider', 'unknown')} / {route.get('model', 'unknown')}",
    ]
    if provider_env.get("checked"):
        lines.extend(
            [
                f"- Provider env: {provider_env.get('env_var')}",
                f"- Visible in current process: {str(provider_env.get('visible_in_current_process')).lower()}",
                f"- Visible in child process: {str(provider_env.get('visible_in_child_process')).lower()}",
                "- Privacy: key value not printed; base URL value not printed; local paths omitted",
            ]
        )
    else:
        lines.append("- Key env: not checked because route configuration failed")
    cognitive_worker = _as_dict(report.get("cognitive_worker"))
    if cognitive_worker:
        lines.append(f"- Cognitive worker mode: {cognitive_worker.get('status', 'unknown')}")
    background_consent = _as_dict(report.get("background_model_consent"))
    if background_consent:
        lines.append(
            "- Background model consent: "
            f"{background_consent.get('status', 'unknown')} "
            f"(env {background_consent.get('required_env', BACKGROUND_MODEL_CONSENT_ENV)})"
        )
    hook_relevance = _as_dict(report.get("hook_relevance"))
    if hook_relevance and not hook_relevance.get("actual_installed_hook_process_checked"):
        lines.extend(
            [
                "- Hook process caveat: current/child-process visibility does not prove an already-running hook process can see the key.",
                "- Hook bridge next: use `aippocampus onboard provider-key --plan --json`, apply only after choosing a private source, restart Codex/hook host, then run `aippocampus hooks prompt status --last` and `aippocampus doctor provider --json`.",
                "- No-key path: source-backed recall/search remains usable without the provider-key bridge.",
            ]
        )
    for action in report.get("recommended_actions") or []:
        if isinstance(action, dict) and action.get("message"):
            lines.append(f"- Next: {action['message']}")
    lines.append("")
    return "\n".join(lines)


def render_config_text(report: dict[str, Any], *, detail: str = "compact") -> str:
    data = _as_dict(report.get("data"))
    knobs = list(data.get("knobs") or [])
    configured = [
        item for item in knobs if isinstance(item, dict) and item.get("configured")
    ]
    configured_sensitive = [item for item in configured if item.get("sensitive")]
    cannot_claim = list(report.get("cannot_claim") or [])
    warnings = list(report.get("warnings") or [])
    lines = [
        "AIppocampus config doctor",
        f"- Status: {report.get('status')}",
        "- Privacy: values are not printed; configured values are presence-only",
        "- Boundary: config presence does not validate secret values or provider connectivity",
        "- Next: use `aippocampus doctor provider` when you need provider/key connectivity readiness.",
    ]
    if warnings:
        lines.insert(2, f"- Warnings: {len(warnings)}")
    if int(data.get("unknown_count", 0) or 0):
        lines.insert(2, f"- Unknown AIPPOCAMPUS_* env vars: {data.get('unknown_count', 0)}")
    if detail == "full":
        lines.extend(
            [
                f"- Registered knobs: {len(knobs)}",
                f"- Configured env vars: {len(configured)}",
                f"- Sensitive env vars present: {len(configured_sensitive)}",
                f"- Unknown AIPPOCAMPUS_* env vars: {data.get('unknown_count', 0)}",
                f"- Warnings: {len(warnings)}",
                "- Knob catalog:",
            ]
        )
        for item in knobs:
            if not isinstance(item, dict):
                continue
            note = str(item.get("notes") or "")
            note_part = f" note={note}" if note else ""
            lines.append(
                f"  - {item.get('name')} surface={item.get('surface')} "
                f"default={item.get('default')} source={item.get('source')}{note_part}"
            )
    else:
        lines.append("- Detail: use `aippocampus config --detail full` for the knob catalog.")
    lines.append("")
    if cannot_claim and detail == "full":
        lines.append("- Detail: " + ", ".join(str(item) for item in cannot_claim[:3]))
        lines.append("")
    return "\n".join(lines)


def public_json_text(report: dict[str, Any]) -> str:
    """Serialize the provider doctor public report without printing secrets."""

    return json.dumps(report, ensure_ascii=False, indent=2)
