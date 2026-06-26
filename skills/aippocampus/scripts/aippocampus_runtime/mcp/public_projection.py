#!/usr/bin/env python3
"""Public-safe MCP payload projections."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, cast

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    command_value_needs_input,
    foreground_readiness_card,
    strip_foreground_action_legacy_aliases,
)
from aippocampus_runtime.first_recall_readiness import compact_health_first_recall_fields
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.source.latest_reply import MAX_COMPACT_FINAL_ANSWER_CHARS


def public_payload(arguments: dict[str, Any], payload: Any) -> Any:
    projected = payload if arguments.get("include_private_paths") else redact_sensitive_values(redact_private_paths(payload))
    return strip_foreground_action_legacy_aliases(projected)


def detail_arg(arguments: dict[str, Any]) -> str:
    value = str(arguments.get("detail") or "").strip().casefold()
    if value in {"full", "diagnostic", "debug"} or arguments.get("diagnostic"):
        return "full"
    return "compact"


def compact_message(item: dict[str, Any]) -> dict[str, Any]:
    preview = core.compact_text(str(item.get("text") or ""), 360)
    pairs = {
        "message_id": item.get("message_id") or item.get("id"),
        "turn_id": item.get("turn_id"),
        "turn_index": item.get("turn_index"),
        "role": item.get("role"),
        "phase": item.get("phase"),
        "is_final": item.get("is_final"),
        "timestamp": item.get("timestamp"),
        "text_preview": preview,
    }
    return {key: value for key, value in pairs.items() if value not in (None, "")}


def compact_latest_reply_message(item: dict[str, Any]) -> dict[str, Any]:
    message = compact_message(item)
    raw_text = str(item.get("text") or "")
    message["text"] = core.compact_text(raw_text, MAX_COMPACT_FINAL_ANSWER_CHARS)
    message["text_char_limit"] = MAX_COMPACT_FINAL_ANSWER_CHARS
    message["text_bounded"] = len(raw_text) > MAX_COMPACT_FINAL_ANSWER_CHARS
    return message


def compact_thread(
    item: dict[str, Any],
    *,
    include_private_identifiers: bool = False,
) -> dict[str, Any]:
    paths_obj = item.get("paths")
    paths = cast(dict[str, Any], paths_obj) if isinstance(paths_obj, dict) else {}
    raw_thread_key = str(item.get("thread_key") or "").strip()
    thread_handle = (
        raw_thread_key
        if include_private_identifiers
        else core.stable_text_fingerprint(
            raw_thread_key or str(item.get("title") or item.get("workspace_name") or "unknown"),
            namespace="mcp-thread-handle",
            length=12,
            prefix="thread",
        )
    )
    pairs = {
        "thread_handle": thread_handle,
        "thread_handle_authority": (
            "private_registry_key" if include_private_identifiers else "diagnostic_local_fingerprint"
        ),
        "thread_handle_usable_as_source_selector": bool(include_private_identifiers),
        "title": core.compact_text(
            str(
                item.get("title")
                or item.get("workspace_name")
                or ("private thread" if raw_thread_key else "")
            ),
            120,
        ),
        "project_label": item.get("project_label"),
        "workspace_name": item.get("workspace_name"),
        "updated_at": item.get("updated_at"),
        "message_count": item.get("message_count"),
        "anchor_count": item.get("anchor_count"),
        "scope_labels": item.get("scope_labels") if isinstance(item.get("scope_labels"), list) else None,
        "has_clean_source": bool(paths.get("clean_source_messages_jsonl")),
    }
    if include_private_identifiers and raw_thread_key:
        pairs["thread_key"] = raw_thread_key
    elif raw_thread_key:
        pairs["thread_key_redacted"] = True
    return {key: value for key, value in pairs.items() if value not in (None, "", [])}


def public_thread_detail_without_private_identifiers(item: dict[str, Any]) -> dict[str, Any]:
    session_meta_obj = item.get("session_meta")
    session_meta = cast(dict[str, Any], session_meta_obj) if isinstance(session_meta_obj, dict) else {}
    paths_obj = item.get("paths")
    paths = cast(dict[str, Any], paths_obj) if isinstance(paths_obj, dict) else {}
    base_instructions = session_meta.get("base_instructions")
    dynamic_tools = session_meta.get("dynamic_tools")
    result = {
        **compact_thread(item, include_private_identifiers=False),
        "detail_profile": "full_without_private_identifiers",
        "private_identifier_fields_omitted": [
            "thread_key",
            "project_key",
            "session_meta.id",
        ],
        "raw_session_metadata_omitted": bool(session_meta),
        "session_meta_summary": {
            "available": bool(session_meta),
            "timestamp": session_meta.get("timestamp"),
            "source": session_meta.get("source"),
            "cwd_redacted": bool(session_meta.get("cwd")),
            "base_instructions_text_omitted": bool(base_instructions),
            "dynamic_tools_omitted": bool(dynamic_tools),
        },
        "paths_summary": {
            "workspace_registered": bool(paths.get("workspace")),
            "rollout_registered": bool(paths.get("rollout")),
            "clean_source_registered": bool(
                paths.get("clean_source_messages_jsonl") or paths.get("clean_source_dir")
            ),
            "local_paths_omitted": bool(paths),
        },
    }
    return core.strip_empty(result)


def _command_with_cwd_template(command: str) -> str:
    return re.sub(r'--cwd\s+(?:"[^"]+"|\S+)', '--cwd "{cwd}"', command, count=1)


def _uses_current_directory_cwd(command: str) -> bool:
    return bool(re.search(r'--cwd\s+(?:"\."|\.)($|\s)', command))


_MAINTENANCE_ACTION_IDS = {
    "build_clean_source",
    "build_index",
    "build_segments",
    "checkpoint",
    "prepare_graphify_corpus",
}


def _looks_like_python_script_path_command(command: str) -> bool:
    return bool(
        re.match(r'(?i)^\s*(?:python(?:\.exe)?|python3(?:\.\d+)?(?:\.exe)?|py(?:\.exe)?)\s+', command)
        and re.search(r'(?i)(?:[A-Za-z]:\\|/|\\\\).+\.py\b', command)
    )


def _compact_command_fields(command: Any, *, action_id: str = "") -> dict[str, Any]:
    raw = str(command or "").strip()
    if not raw:
        return {}
    if action_id in _MAINTENANCE_ACTION_IDS and _looks_like_python_script_path_command(raw):
        return {
            "command_template": 'aippocampus maintenance --cwd "{cwd}"',
            "requires": ["cwd"],
            "template_only": True,
        }
    if " --cwd " in raw and not _uses_current_directory_cwd(raw):
        return {
            "command_template": _command_with_cwd_template(raw),
            "requires": ["cwd"],
            "template_only": True,
        }
    if command_value_needs_input(raw):
        return {
            "command_template": raw,
            "requires": ["operator_input"],
            "template_only": True,
        }
    return {"command": raw}


def compact_action(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        action_id = str(
            item.get("id") or item.get("kind") or item.get("name") or item.get("action") or ""
        )
        reason = core.compact_text(str(item.get("reason") or item.get("message") or ""), 220)
        command_fields = _compact_command_fields(
            item.get("facade_command") or item.get("command"),
            action_id=action_id,
        )
        mutates = action_id in _MAINTENANCE_ACTION_IDS and bool(command_fields)
        pairs = {
            "id": action_id,
            "label": item.get("label")
            or (action_id.replace("_", " ").strip().capitalize() if action_id else "Recommended action"),
            "severity": item.get("severity") or item.get("level"),
            "reason": reason,
            "why": item.get("why") or reason or "Follow this compact health recommendation before relying on readiness.",
            "mutation_risk": item.get("mutation_risk")
            or ("explicit_generated_artifact_write" if mutates else "read_only"),
            "claim_boundary": item.get("claim_boundary") or "health_readiness_not_source_evidence",
            **command_fields,
            "scope": item.get("scope"),
            "retryable": item.get("retryable"),
        }
        if not command_fields:
            pairs["no_command_needed"] = True
        return {key: value for key, value in pairs.items() if value not in (None, "", [])}
    text = core.compact_text(str(item or ""), 220)
    return {"id": "recommended_action", "reason": text} if text else {}


def _action_command_projection(action: dict[str, Any]) -> dict[str, Any]:
    if action.get("command"):
        return {"command": action["command"]}
    if action.get("command_template"):
        result = {
            "kind": "shell_command_template",
            "command_template": action["command_template"],
            "template_only": True,
        }
        if action.get("requires"):
            result["requires"] = action["requires"]
        return result
    return {"kind": "manual_action"}


def _storage_summary_projection(
    storage_cleanup_action: dict[str, Any] | None,
    storage_pressure: dict[str, Any],
) -> dict[str, Any]:
    summary_command = str(storage_pressure.get("summary_command") or "").strip()
    if summary_command:
        return {"command": summary_command}
    raw_command = ""
    command_field = "command"
    if storage_cleanup_action:
        raw_command = str(
            storage_cleanup_action.get("command")
            or storage_cleanup_action.get("command_template")
            or ""
        ).strip()
        command_field = (
            "command_template"
            if storage_cleanup_action.get("command_template")
            else "command"
        )
    summary = re.sub(r"\s+--json\s+--top\s+\d+\b", " --summary-json", raw_command, count=1)
    if not summary or summary == raw_command:
        summary = "aippocampus storage gc --dry-run --summary-json --cwd ."
        command_field = "command"
    if command_field == "command_template":
        result: dict[str, Any] = {
            "kind": "shell_command_template",
            "command_template": summary,
            "template_only": True,
        }
        if storage_cleanup_action and storage_cleanup_action.get("requires"):
            result["requires"] = storage_cleanup_action["requires"]
        return result
    return {"command": summary}


def _maintenance_plan_action(*, reason: str) -> dict[str, Any]:
    return {
        "id": "review_maintenance_plan",
        "label": "Review maintenance plan",
        "command": "aippocampus maintenance plan --summary-json",
        "mutation_risk": "read_only",
        "claim_boundary": "maintenance_plan_not_source_evidence",
        "why": reason,
    }


def _maintenance_apply_action(*, reason: str) -> dict[str, Any]:
    return {
        "id": "apply_after_user_consent",
        "label": "Apply maintenance after consent",
        "command": "aippocampus maintenance apply --summary-json",
        "mutation_risk": "writes_generated_source_artifacts",
        "claim_boundary": "explicit_maintenance_write_not_source_claim",
        "why": reason,
        "write_boundary": {
            "explicit_user_consent_required": True,
            "no_write_happens_until_command_runs": True,
        },
    }


def _health_followup_actions(
    *,
    freshness_degraded: bool,
    exact_latest_action: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not (freshness_degraded and exact_latest_action):
        return []
    reason = (
        "Latest clean-source or index artifacts may be stale; review the bounded maintenance "
        "plan before exact-latest claims."
    )
    return [
        _maintenance_plan_action(reason=reason),
        _maintenance_apply_action(
            reason=(
                "Run only after reviewing the maintenance plan and deciding to refresh generated "
                "source/index artifacts."
            )
        ),
    ]


def compact_health_payload(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("product_readiness") or {}
    all_recommended = [
        action
        for item in payload.get("recommended_actions") or []
        if (action := compact_action(item))
    ]
    blocking = [
        item
        for item in all_recommended
        if str(item.get("severity") or "").casefold() in {"critical", "warning"}
    ]
    promotable_blocking = [] if payload.get("ok") else blocking
    ordinary_usable = (
        bool(readiness.get("ordinary_first_recall_usable"))
        if isinstance(readiness, dict) and "ordinary_first_recall_usable" in readiness
        else bool(payload.get("ok"))
    )
    ready_status = (
        readiness.get("status")
        if isinstance(readiness, dict) and readiness.get("status")
        else payload.get("status")
    )
    exact_latest_action = next(
        (
            item
            for item in all_recommended
            if item.get("id") in {"build_clean_source", "build_index", "build_segments"}
            and (item.get("command") or item.get("command_template"))
        ),
        None,
    )
    storage_cleanup_action = next(
        (
            item
            for item in all_recommended
            if item.get("id") == "storage_gc_rebuildable_cache"
            and (item.get("command") or item.get("command_template"))
        ),
        None,
    )
    freshness_obj = payload.get("freshness")
    freshness = cast(dict[str, Any], freshness_obj) if isinstance(freshness_obj, dict) else {}
    freshness_degraded = bool(
        isinstance(readiness, dict)
        and (
            readiness.get("freshness_degraded")
            or readiness.get("latest_current_thread_may_be_missing")
        )
    ) or bool(
        freshness.get("latest_visible_gap")
        or any(
            item.get("id") in {"build_clean_source", "build_index", "build_segments"}
            for item in all_recommended
        )
    )
    first_recall_fields = compact_health_first_recall_fields(
        readiness if isinstance(readiness, dict) else None,
        ordinary_usable=ordinary_usable,
        freshness_degraded=freshness_degraded,
    )
    storage_pressure_obj = payload.get("storage_pressure")
    storage_pressure = (
        cast(dict[str, Any], storage_pressure_obj) if isinstance(storage_pressure_obj, dict) else {}
    )
    host_confounds_obj = payload.get("host_state_confounds")
    host_confounds = cast(dict[str, Any], host_confounds_obj) if isinstance(host_confounds_obj, dict) else {}
    recommended_action_ids = [
        str(item.get("id") or "")
        for item in all_recommended
        if str(item.get("id") or "")
    ][:5]
    storage_cleanup_recommended = bool(
        isinstance(readiness, dict)
        and readiness.get("storage_pressure_cleanup_recommended")
    ) or bool(storage_pressure.get("pressure"))
    freshness_summary = core.strip_empty(
        {
            "degraded": True if freshness_degraded else None,
            "latest_current_thread_may_be_missing": True
            if (
                bool(
                    isinstance(readiness, dict)
                    and readiness.get("latest_current_thread_may_be_missing")
                )
                or bool(freshness.get("latest_visible_gap"))
            )
            else None,
            "index_message_delta": freshness.get("index_message_delta"),
            "clean_source_message_delta": freshness.get("clean_source_message_delta"),
            "clean_source_turn_delta": freshness.get("clean_source_turn_delta"),
        }
    )
    storage_summary = core.strip_empty(
        {
            "cleanup_recommended": True if storage_cleanup_recommended else None,
            "pressure": storage_pressure.get("pressure") if storage_pressure.get("pressure") else None,
            "bounded_audit_available": True if storage_cleanup_recommended else None,
        }
    )
    host_state_summary = core.strip_empty(
        {
            "confounds_detected": True if host_confounds.get("confounds_detected") else None,
            "available": host_confounds.get("available") if host_confounds.get("available") else None,
            "artifact_scope": host_confounds.get("artifact_scope") if host_confounds else None,
        }
    )
    # This card is the default foreground JSON surface. Keep only decision fields
    # here; freshness/storage/host-state objects are operator diagnostics and
    # belong behind the full detail command below.
    maintenance_summary = core.strip_empty(
        {
            "recommended_action_count": len(all_recommended),
            "blocking_action_count": (
                readiness.get("blocking_action_count") if isinstance(readiness, dict) else None
            ),
            "high_severity_action_count": (
                readiness.get("high_severity_action_count") if isinstance(readiness, dict) else None
            ),
            "recommended_action_ids": recommended_action_ids,
            "freshness_degraded": True if freshness_summary else None,
            "storage": storage_summary or None,
            "storage_cleanup_recommended": True if storage_summary else None,
            "host_state_confounds_detected": True if host_state_summary else None,
        }
    )
    if ordinary_usable and all_recommended:
        primary_action: dict[str, Any] = {
            "id": "continue_with_nonblocking_maintenance",
            "label": "Continue recall", "why": "Recall is usable; maintenance is advisory.",
            "mutation_risk": "read_only", "claim_boundary": "health_not_source", "continue_without_command": True,
            "primary": {"ordinary_first_recall_usable": True},
        }
        if storage_cleanup_action:
            primary_action["when_idle"] = _storage_summary_projection(
                storage_cleanup_action,
                storage_pressure,
            ) | {"id": "review_storage_gc_summary", "mutation_risk": "read_only"}
    else:
        primary_action = (
            promotable_blocking[0]
            if not ordinary_usable and promotable_blocking
            else all_recommended[0]
            if all_recommended and not ordinary_usable
            else {
                "id": "no_action",
                "label": "Continue", "why": "Health is ready; no action is needed.",
                "mutation_risk": "read_only", "claim_boundary": "health_not_source", "continue_without_command": True,
                "reason": "Memory health is ready; advisory actions can wait unless you are doing local diagnostics.",
            }
        )
    foreground_action = dict(primary_action)
    readiness_card = foreground_readiness_card(
        subject="memory_health",
        scope="current_workspace",
        state=str(ready_status or ("ok" if ordinary_usable else "attention_needed")),
        usable_now=ordinary_usable,
        blocks_first_recall=not ordinary_usable,
        blocks_exact_latest=freshness_degraded,
        recommended=[],
        claim_boundary="health_readiness_not_source_evidence",
    )
    workspace_maintenance = None
    continuity_available = None
    if isinstance(readiness, dict):
        workspace_maintenance = readiness.get("workspace_source_maintenance_required")
        continuity_available = readiness.get("continuity_recall_available")
    card = {
        "kind": "aippocampus_health_card",
        "detail": "compact",
        "ok": ordinary_usable,
        "status": ready_status or ("ok" if ordinary_usable else "attention_needed"),
        "ordinary_first_recall_usable": ordinary_usable,
        "blocks_first_recall": not ordinary_usable,
        "blocks_exact_latest_claims": freshness_degraded,
        "workspace_source_maintenance_required": None if workspace_maintenance is None else bool(workspace_maintenance),
        "continuity_recall_available": None if continuity_available is None else bool(continuity_available),
        **first_recall_fields,
        "readiness_card": readiness_card,
        "maintenance_summary": maintenance_summary,
        "operator_detail_command": "aippocampus health --detail full --json --operator-timeout-ms 5000",
    }
    followup_actions = _health_followup_actions(
        freshness_degraded=freshness_degraded,
        exact_latest_action=exact_latest_action,
    )
    foreground_fields = canonical_foreground_action_fields(
        foreground_action,
        safe_next_actions=[foreground_action, *followup_actions],
    )
    card.update(foreground_fields)
    return core.strip_empty(card)


def compact_register_thread_payload(payload: dict[str, Any]) -> dict[str, Any]:
    entry_obj = payload.get("entry")
    entry = cast(dict[str, Any], entry_obj) if isinstance(entry_obj, dict) else {}
    paths_obj = entry.get("paths")
    paths = cast(dict[str, Any], paths_obj) if isinstance(paths_obj, dict) else {}
    status = payload.get("status") or "registered"
    raw_thread_key = str(entry.get("thread_key") or payload.get("thread_key") or "").strip()
    thread_handle = core.stable_text_fingerprint(
        raw_thread_key or str(entry.get("title") or entry.get("workspace_name") or "unknown"),
        namespace="mcp-thread-handle",
        length=12,
        prefix="thread",
    )
    foreground_action = {
        "id": "recall_from_registered_thread",
        "label": "Recall from registered thread",
        "tool_name": "recall_context",
        "arguments_template": {"intent": "{task_or_memory_cue}"},
        "requires": ["task_or_memory_cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "registered_thread_status_is_not_memory_evidence",
        "why": "Registration only makes source reachable; recall or search with a concrete cue before using it as continuity.",
    }
    search_action = {
        "id": "search_registered_thread",
        "label": "Search registered source",
        "tool_name": "search_memory",
        "arguments_template": {"query": "{exact_phrase}"},
        "requires": ["exact_phrase"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "source_reopen_required_before_claim",
        "why": "Use when you have distinctive wording to find the registered clean source.",
    }
    result = {
        "detail": "compact",
        "status": status,
        "thread_handle": thread_handle,
        "thread_key_redacted": bool(raw_thread_key),
        "title": core.compact_text(
            str(entry.get("title") or entry.get("workspace_name") or entry.get("thread_key") or ""),
            160,
        ),
        "project_label": entry.get("project_label"),
        "message_count": entry.get("message_count"),
        "has_clean_source": bool(paths.get("clean_source_messages_jsonl") or paths.get("clean_source_dir")),
        "index_built": bool(payload.get("index_report") or payload.get("index_built")),
        "next_step_hint": (
            "Use recall_context or search_memory for task-specific routes; request diagnostic output only for local audit."
        ),
        **canonical_foreground_action_fields(
            foreground_action,
            safe_next_actions=[foreground_action, search_action],
        ),
    }
    if not entry and "status" in payload:
        result["status"] = payload["status"]
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def _compact_claim_boundary(
    *,
    can_use_for: list[str],
    must_reopen_for: list[str],
    detail_command: str,
) -> dict[str, Any]:
    return {
        "can_use_for": can_use_for,
        "must_reopen_for": must_reopen_for,
        "detail_available_with": detail_command,
    }


def _handle_digest(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _recall_context_foreground_action(route: dict[str, Any], index: int) -> dict[str, Any]:
    reopen_obj = route.get("source_reopen_path")
    reopen = cast(dict[str, Any], reopen_obj) if isinstance(reopen_obj, dict) else {}
    arguments_obj = reopen.get("arguments")
    arguments = cast(dict[str, Any], arguments_obj) if isinstance(arguments_obj, dict) else {}
    if arguments:
        return {
            "action_id": "recall_deepen_selected_route",
            "tool_name": "recall_deepen",
            "arguments": dict(arguments),
            "claim_boundary": "source_reopen_required_before_strong_claim",
        }
    return {
        "action_id": "recall_deepen_requires_full_detail",
        "tool_name": "recall_deepen",
        "arguments": {"request_index": index, "detail": "full"},
        "claim_boundary": "source_reopen_required_before_strong_claim",
    }


def _agent_recall_redirect_action() -> dict[str, Any]:
    return {
        "id": "use_agent_recall_for_foreground_continuity",
        "label": "Use agent_recall for foreground continuity",
        "tool_name": "agent_recall",
        "command_template": 'aippocampus agent recall "{same_continuity_cue}" --json',
        "arguments_template": {"query": "{same_continuity_cue}"},
        "requires": ["same_continuity_cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "why": (
            "recall_context is a legacy/detail route-handle tool; use agent_recall "
            "for ordinary foreground continuity, then agent_deepen before claims."
        ),
    }


def compact_recall_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    routes = [route for route in payload.get("routes") or [] if isinstance(route, dict)]
    compact_routes: list[dict[str, Any]] = []
    for index, route in enumerate(routes[:2], start=1):
        compact_routes.append(
            core.strip_empty(
                {
                    "index": index,
                    "label": core.compact_text(str(route.get("route_label") or "legacy route"), 120),
                    "route_label": core.compact_text(
                        str(route.get("route_label") or route.get("title") or "memory route"),
                        120,
                    ),
                    "summary": core.compact_text(str(route.get("summary") or ""), 180),
                    "evidence_level": route.get("evidence_level"),
                    "claim_boundary": "source_reopen_required_before_claim",
                    "action": _recall_context_foreground_action(route, index),
                }
            )
        )
    redirect_action = _agent_recall_redirect_action()
    route_actions = [
        route["action"]
        for route in compact_routes
        if isinstance(route, dict) and isinstance(route.get("action"), dict)
    ]
    result = {
        "detail": "compact",
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "surface": "mcp_recall_context_legacy_compact",
        "status": payload.get("status"),
        "summary": (
            "recall_context is legacy/detail-only for route handles; prefer agent_recall "
            "for ordinary foreground continuity."
        ),
        # Compatibility metadata: owner #2753. Removal condition: delete this
        # field when recall_context leaves the MCP catalog. Default exposure:
        # compact only redirects to agent_recall; route-handle detail remains
        # behind explicit full/detail calls.
        "legacy_tool_state": "legacy_detail_only",
        "routes": compact_routes,
        "claim_boundary": _compact_claim_boundary(
            can_use_for=["legacy_route_receipts", "next_action_choice"],
            must_reopen_for=["source_backed_claims", "exact_wording", "sensitive_or_stale_facts"],
            detail_command='recall_context with {"detail":"full"}',
        ),
        **canonical_foreground_action_fields(
            redirect_action,
            safe_next_actions=route_actions,
        ),
        "warnings": payload.get("warnings"),
    }
    return core.strip_empty(result)
