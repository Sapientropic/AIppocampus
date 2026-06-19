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
    foreground_template_action,
    normalize_foreground_action,
    shell_quote,
)
from aippocampus_runtime.first_recall_readiness import compact_health_first_recall_fields
from aippocampus_runtime.mcp import agent_recall_compact_choices as recall_choices
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


def public_payload(arguments: dict[str, Any], payload: Any) -> Any:
    if arguments.get("include_private_paths"):
        return payload
    return redact_sensitive_values(redact_private_paths(payload))


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
        action_id = str(item.get("id") or item.get("name") or item.get("action") or "")
        command_fields = _compact_command_fields(
            item.get("facade_command") or item.get("command"),
            action_id=action_id,
        )
        pairs = {
            "id": action_id,
            "severity": item.get("severity") or item.get("level"),
            "reason": core.compact_text(str(item.get("reason") or item.get("message") or ""), 220),
            **command_fields,
            "scope": item.get("scope"),
            "retryable": item.get("retryable"),
        }
        return {key: value for key, value in pairs.items() if value not in (None, "", [])}
    text = core.compact_text(str(item or ""), 220)
    return {"id": "recommended_action", "reason": text} if text else {}


def _action_command_projection(action: dict[str, Any]) -> dict[str, Any]:
    if action.get("command"):
        return {"kind": "shell_command", "command": action["command"]}
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
        return {"kind": "shell_command", "command": summary_command}
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
    return {"kind": "shell_command", "command": summary}


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
    freshness_summary = _without_empty(
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
    storage_summary = _without_empty(
        {
            "cleanup_recommended": True if storage_cleanup_recommended else None,
            "pressure": storage_pressure.get("pressure") if storage_pressure.get("pressure") else None,
            "bounded_audit_available": True if storage_cleanup_recommended else None,
        }
    )
    host_state_summary = _without_empty(
        {
            "confounds_detected": True if host_confounds.get("confounds_detected") else None,
            "available": host_confounds.get("available") if host_confounds.get("available") else None,
            "artifact_scope": host_confounds.get("artifact_scope") if host_confounds else None,
        }
    )
    # This card is the default foreground JSON surface. Keep only decision fields
    # here; freshness/storage/host-state objects are operator diagnostics and
    # belong behind the full detail command below.
    maintenance_summary = _without_empty(
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
        agent_next_action: dict[str, Any] = {
            "id": "continue_with_nonblocking_maintenance",
            "label": "Continue recall", "why": "Recall is usable; maintenance is advisory.",
            "mutation_risk": "read_only", "claim_boundary": "health_not_source", "continue_without_command": True,
            "primary": {
                "ordinary_first_recall_usable": True,
                "message": "ordinary source-backed recall/search can continue",
            },
        }
        if freshness_degraded and exact_latest_action:
            agent_next_action["before_exact_latest_claims"] = _action_command_projection(
                exact_latest_action
            )
        if storage_cleanup_action:
            agent_next_action["when_idle"] = _storage_summary_projection(
                storage_cleanup_action,
                storage_pressure,
            ) | {"id": "review_storage_gc_summary", "mutation_risk": "read_only"}
    else:
        agent_next_action = (
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
    foreground_action = dict(agent_next_action)
    readiness_card = foreground_readiness_card(
        subject="memory_health",
        scope="current_workspace",
        state=str(ready_status or ("ok" if ordinary_usable else "attention_needed")),
        usable_now=ordinary_usable,
        blocks_first_recall=not ordinary_usable,
        blocks_exact_latest=freshness_degraded,
        recommended=recommended_action_ids,
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
        "operator_detail_command": "aippocampus health --detail full --json",
        "output_boundary": "compact_foreground_no_operator_diagnostic_objects",
    }
    foreground_fields = canonical_foreground_action_fields(foreground_action)
    # Health compact JSON already carries the canonical foreground action and
    # the legacy agent_next_action alias. A one-item safe_next_actions list is a
    # byte-for-byte mirror, not an alternate path, and it is the easiest way for
    # operator health diagnostics to crowd out the foreground budget.
    if foreground_fields.get("safe_next_actions") == [foreground_fields.get("foreground_action")]:
        foreground_fields.pop("safe_next_actions", None)
    card.update(foreground_fields)
    return _without_empty(card)


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
        "agent_next_action": (
            "Use recall_context or search_memory for task-specific routes; request diagnostic output only for local audit."
        ),
    }
    if not entry and "status" in payload:
        result["status"] = payload["status"]
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def _without_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _without_empty(item)) not in (None, "", [])
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _without_empty(item)) not in (None, "", [])]
    return value


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


def _canonical_agent_action(card: Any) -> dict[str, Any]:
    card_map = card if isinstance(card, dict) else {}
    action = card_map.get("canonical_action") if isinstance(card_map.get("canonical_action"), dict) else {}
    if action:
        result = _without_empty(normalize_foreground_action(action))
        result.setdefault("label", "Open selected recall route")
        result.setdefault("mutation_risk", "read_only")
        result.setdefault(
            "why",
            "Recall surfaced route-shaped context; deepen before using it for source-backed claims.",
        )
        return result
    return {
        "action_id": "continue_normally",
        "arguments": {},
        "claim_boundary": "no_route_claim",
    }


def _recall_miss_recovery_card(status: Any) -> dict[str, Any]:
    miss_class = "no_route" if str(status or "") == "no_routes" else "weak_or_unavailable_route"
    return {
        "miss_class": miss_class,
        "summary": (
            "No compact source-backed route surfaced."
            if miss_class == "no_route"
            else "Recall did not produce a route that is safe to use directly."
        ),
        "primary_action": "refine_cue_or_run_exact_search",
        "recovery_actions": [
            'refine the cue with a project, object, person, or time clue',
            "run exact search after providing exact_phrase",
            "aippocampus onboard --provider auto --status --json",
        ],
        "safe_next_actions": [
            foreground_template_action(
                action_id="search_exact_phrase",
                label="Search exact clean-source wording",
                command_template='aippocampus search "{exact_phrase}" --json',
                requires=["exact_phrase"],
                why="Search only after the caller supplies real remembered wording.",
                mutation_risk="read_only",
                claim_boundary="search_result_requires_source_boundary",
            ),
            {
                "id": "check_onboarding_status",
                "label": "Check source registration",
                "command": "aippocampus onboard --provider auto --status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "setup_status_not_memory_evidence",
            },
        ],
        "do_not": [
            "do not claim from scent or route silence",
            "do not broaden into manual search before checking source/index readiness when continuity was expected",
        ],
        "claim_boundary": "no_route_claim",
    }


def _weak_route_recovery_card() -> dict[str, Any]:
    return {
        "miss_class": "weak_route",
        "summary": "Recall returned route-shaped context, but no safe deepen request was available.",
        "primary_action": "refine_cue_or_run_exact_search",
        "recovery_actions": [
            "refine cue before relying on the route",
            "run exact search for distinctive source wording",
            "request full diagnostics only if this route should have been reopenable",
        ],
        "do_not": [
            "do not treat direction-only context as evidence",
            "do not quote or decide from a route without reopened source",
        ],
        "claim_boundary": "no_claim_before_reopen",
    }


def route_deepen_action(request_index: int, *, low_confidence: bool = False) -> dict[str, Any]:
    action = {
        "id": "deepen_this_route",
        "tool_name": "agent_deepen",
        "arguments": {"request_index": request_index, "last_recall": True},
        "command": (
            f"aippocampus agent deepen --request {request_index} --last-recall --json"
        ),
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
    }
    if low_confidence:
        action["route_choice_posture"] = "labels_low_specificity"
        action["confidence"] = "low_confidence_navigation"
    return action


def compact_agent_recall_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project agent_recall into one foreground action plus compact route receipts."""

    recovery_cue = str(
        redact_sensitive_values(
            redact_private_paths(str(payload.get("query") or payload.get("intent") or payload.get("cue") or "").strip())
        )
        or ""
    ).strip()
    if command_value_needs_input(recovery_cue):
        recovery_cue = ""
    search_fields = (
        {
            "arguments": {"query": recovery_cue, "max": 5},
            "cli_command": f"aippocampus search {shell_quote(recovery_cue)} --json",
        }
        if recovery_cue
        else {
            "arguments_template": {"query": "{exact_phrase}", "max": 5},
            "requires": ["exact_phrase"],
            "template_only": True,
            "cli_command_template": 'aippocampus search "{exact_phrase}" --json',
        }
    )
    memory_packets = [
        packet for packet in payload.get("memory_packets") or [] if isinstance(packet, dict)
    ]
    raw_metrics = payload.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    labels_low_specificity = recall_choices.low_specificity_route_choices(
        metrics, len(memory_packets)
    ) or recall_choices.distinctive_cue_anchor_gap(
        recovery_cue,
        memory_packets,
    )
    cache_available = bool(payload.get("last_recall_cache_available"))
    route_receipts: list[dict[str, Any]] = []
    for index, packet in enumerate(memory_packets[:3], start=1):
        route_id = str(packet.get("route_id") or f"route:{index}").strip()
        already_opened = bool(packet.get("already_opened"))
        route_is_callable = (
            cache_available
            and not already_opened
            and str(packet.get("output_mode") or "") == "reopenable_route"
        )
        callable_selector = (
            {
                "kind": "last_recall_request_index",
                "request_index": index,
                "last_recall": True,
            }
            if route_is_callable
            else {
                "kind": "not_callable_from_compact_card",
                "reason": (
                    "route_already_opened_in_this_session"
                    if already_opened
                    else "route_not_reopenable_or_last_recall_cache_missing"
                ),
            }
        )
        route_receipts.append(
            _without_empty(
                {
                    "route_index": index,
                    "route_id": route_id,
                    "display_id": route_id,
                    "feedback_id": route_id,
                    "callable_selector": callable_selector,
                    "private_handle_boundary": (
                        "compact_output_redacts_local_private_handle_use_callable_selector"
                    ),
                    "route_label": core.compact_text(
                        str(
                            packet.get("route_topic")
                            or packet.get("route_label")
                            or packet.get("display_hint")
                            or "memory route"
                        ),
                        120,
                    ),
                    "route_family": packet.get("route_kind") or packet.get("output_mode"),
                    "already_opened": already_opened or None,
                    "choice_reason": recall_choices.route_choice_reason(
                        packet,
                        index=index,
                        route_count=len(memory_packets),
                        labels_low_specificity=labels_low_specificity,
                    )
                    if len(memory_packets) > 1 or labels_low_specificity
                    else None,
                    "claim_permission": packet.get("claim_permission"),
                    "next_action_boundary": "reopen_required_before_claim",
                    "action": route_deepen_action(index, low_confidence=labels_low_specificity)
                    if route_is_callable
                    else None,
                }
            )
        )
    semantic = payload.get("semantic_gate_diagnostics")
    semantic_compact = None
    if isinstance(semantic, dict):
        semantic_compact = _without_empty(
            {
                "requested": semantic.get("requested"),
                "mode": semantic.get("mode"),
                "overall_recall_diagnostic": semantic.get("overall_recall_diagnostic"),
                "semantic_sidecar": semantic.get("semantic_sidecar"),
                "agent_next_action": semantic.get("agent_next_action"),
                "boundary": semantic.get("boundary"),
            }
        )
    status = payload.get("status")
    miss_recovery_card = None if memory_packets else _recall_miss_recovery_card(status)
    weak_route_recovery_card = None
    foreground_action = _canonical_agent_action(payload.get("foreground_action_card"))
    if miss_recovery_card is not None:
        foreground_action = {
            "action_id": "recover_recall_miss",
            "label": "Recover recall miss",
            "tool_name": "search_memory",
            "why": "No route surfaced; try exact source-backed search or check onboarding/index freshness.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_route_claim",
        } | search_fields
    elif foreground_action.get("action_id") == "continue_normally" or foreground_action.get("id") == "continue_normally":
        weak_route_recovery_card = _weak_route_recovery_card()
        foreground_action = {
            "action_id": "recover_weak_route",
            "label": "Recover weak route",
            "tool_name": "search_memory",
            "why": "A route surfaced without a safe deepen action; refine or exact-search before relying on it.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        } | search_fields
    elif labels_low_specificity and foreground_action.get("tool_name") == "agent_deepen":
        foreground_action = recall_choices.with_low_specificity_foreground_action(
            foreground_action,
            metrics=metrics,
            cue=recovery_cue,
        )
    result = {
        "detail": "compact",
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "mode": payload.get("mode"),
        "surface": "mcp_agent_recall_compact",
        "status": status,
        "opt_in_required": payload.get("opt_in_required"),
        "foreground_action": foreground_action,
        "miss_recovery_card": miss_recovery_card,
        "weak_route_recovery_card": weak_route_recovery_card,
        "routes": route_receipts,
        "route_count": len(memory_packets),
        "semantic_gate_diagnostics": semantic_compact,
        "provider_key_bridge": payload.get("provider_key_bridge"),
        "claim_boundary": _compact_claim_boundary(
            can_use_for=["route_selection", "next_action_choice"],
            must_reopen_for=["source_backed_claims", "exact_wording", "sensitive_or_stale_facts"],
            detail_command='aippocampus agent recall "old decision or handoff cue" --json --detail full',
        ),
        "operator_detail_command": 'aippocampus agent recall "old decision or handoff cue" --json --detail full',
    }
    result.update(canonical_foreground_action_fields(foreground_action))
    return _without_empty(result)


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


def compact_recall_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    routes = [route for route in payload.get("routes") or [] if isinstance(route, dict)]
    compact_routes: list[dict[str, Any]] = []
    for index, route in enumerate(routes[:5], start=1):
        compact_routes.append(
            _without_empty(
                {
                    "route_index": index,
                    "route_id": route.get("route_id"),
                    "kind": route.get("kind"),
                    "route_label": core.compact_text(
                        str(route.get("route_label") or route.get("title") or "memory route"),
                        120,
                    ),
                    "summary": core.compact_text(str(route.get("summary") or ""), 180),
                    "evidence_level": route.get("evidence_level"),
                    "support_level": route.get("support_level"),
                    "source_ref_count": len(
                        [ref for ref in route.get("source_refs") or [] if isinstance(ref, dict)]
                    ),
                    "handle_sha256_12": _handle_digest(route.get("handle")),
                    "foreground_action": _recall_context_foreground_action(route, index),
                }
            )
        )
    result = {
        "detail": "compact",
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "support_level": payload.get("support_level"),
        "status": payload.get("status"),
        "routes": compact_routes,
        "route_count": len(routes),
        "suggested_next": "follow_route_foreground_action" if routes else payload.get("suggested_next"),
        "continuity_route_status": payload.get("continuity_route_status"),
        "claim_boundary": _compact_claim_boundary(
            can_use_for=["route_selection", "recall_deepen_target_choice"],
            must_reopen_for=["source_backed_claims", "exact_wording", "sensitive_or_stale_facts"],
            detail_command='recall_context with {"detail":"full"}',
        ),
        "metrics": {
            "funnel_stage": (payload.get("metrics") or {}).get("funnel_stage"),
            "route_count": len(routes),
        },
        "output_boundary": "compact_foreground_no_local_private_handles",
        "agent_next_action": (
            "Use routes[].foreground_action; request detail=full only for opaque handle diagnostics."
        ),
        "warnings": payload.get("warnings"),
    }
    return _without_empty(result)
