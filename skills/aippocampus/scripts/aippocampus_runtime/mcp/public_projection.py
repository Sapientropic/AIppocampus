#!/usr/bin/env python3
"""Public-safe MCP payload projections."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from aippocampus_runtime import core
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


def compact_action(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        pairs = {
            "id": item.get("id") or item.get("name") or item.get("action"),
            "severity": item.get("severity") or item.get("level"),
            "reason": core.compact_text(str(item.get("reason") or item.get("message") or ""), 220),
            "command": item.get("facade_command") or item.get("command"),
            "scope": item.get("scope"),
            "retryable": item.get("retryable"),
        }
        return {key: value for key, value in pairs.items() if value not in (None, "", [])}
    text = core.compact_text(str(item or ""), 220)
    return {"id": "recommended_action", "reason": text} if text else {}


def compact_health_payload(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("product_readiness") or {}
    all_recommended = [
        action
        for item in payload.get("recommended_actions") or []
        if (action := compact_action(item))
    ]
    storage_action = next(
        (
            item
            for item in all_recommended
            if item.get("id") == "storage_gc_rebuildable_cache"
            and str(item.get("severity") or "").casefold() in {"critical", "warning"}
        ),
        None,
    )
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
            and item.get("command")
        ),
        None,
    )
    storage_cleanup_action = next(
        (
            item
            for item in all_recommended
            if item.get("id") == "storage_gc_rebuildable_cache" and item.get("command")
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
            "dry_run_command": storage_cleanup_action.get("command")
            if storage_cleanup_action
            else storage_pressure.get("dry_run_command")
            if storage_cleanup_recommended
            else None,
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
            "freshness": freshness_summary,
            "storage": storage_summary,
            "host_state": host_state_summary,
        }
    )
    if ordinary_usable and all_recommended:
        agent_next_action: dict[str, Any] = {
            "id": "continue_with_nonblocking_maintenance",
            "primary": {
                "kind": "recall_policy",
                "ordinary_first_recall_usable": True,
                "message": "ordinary source-backed recall/search can continue",
            },
            "recommended_action_ids": [
                str(item.get("id") or "")
                for item in all_recommended
                if str(item.get("id") or "")
            ][:5],
        }
        if (
            freshness_degraded and exact_latest_action
        ):
            agent_next_action["before_exact_latest_claims"] = {
                "kind": "shell_command",
                "command": exact_latest_action["command"],
                "reason": "refresh source/index artifacts before exact latest current-thread claims",
            }
        if storage_cleanup_action:
            agent_next_action["when_idle"] = {
                "kind": "shell_command",
                "command": storage_cleanup_action["command"],
                "reason": "bounded storage cleanup audit; non-blocking for ordinary recall",
            }
    else:
        agent_next_action = (
            promotable_blocking[0]
            if not ordinary_usable and promotable_blocking
            else all_recommended[0]
            if all_recommended and not ordinary_usable
            else {
                "id": "no_action",
                "reason": (
                    "Memory health is ready; advisory actions can wait unless you are doing local diagnostics."
                ),
            }
        )
    foreground_action = dict(agent_next_action)
    card = {
        "kind": "aippocampus_health_card",
        "detail": "compact",
        "ok": ordinary_usable,
        "status": ready_status or ("ok" if ordinary_usable else "attention_needed"),
        "ordinary_first_recall_usable": ordinary_usable,
        "blocks_first_recall": not ordinary_usable,
        "blocks_exact_latest_claims": freshness_degraded,
        "foreground_action": foreground_action,
        "agent_next_action": foreground_action,
        "maintenance_summary": maintenance_summary,
        "operator_detail_command": "aippocampus health --detail full --json",
        "output_boundary": "compact_foreground_no_operator_diagnostic_objects",
    }
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
        return _without_empty(action)
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
            'aippocampus search "distinctive exact phrase" --json',
            "aippocampus onboard --provider auto --status --json",
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


def compact_agent_recall_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project agent_recall into one foreground action plus compact route receipts."""

    memory_packets = [
        packet for packet in payload.get("memory_packets") or [] if isinstance(packet, dict)
    ]
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    labels_low_specificity = recall_choices.low_specificity_route_choices(
        metrics, len(memory_packets)
    )
    route_receipts: list[dict[str, Any]] = []
    for index, packet in enumerate(memory_packets[:3], start=1):
        route_receipts.append(
            _without_empty(
                {
                    "route_index": index,
                    "route_id": packet.get("route_id"),
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
                    "choice_reason": recall_choices.route_choice_reason(
                        packet,
                        index=index,
                        route_count=len(memory_packets),
                        labels_low_specificity=labels_low_specificity,
                    )
                    if len(memory_packets) > 1
                    else None,
                    "claim_permission": packet.get("claim_permission"),
                    "next_action_boundary": "reopen_required_before_claim",
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
            "tool_name": "search_memory",
            "arguments": {
                "query": "distinctive exact phrase",
                "max": 5,
            },
            "cli_command": 'aippocampus search "distinctive exact phrase" --json',
            "why": "No route surfaced; try exact source-backed search or check onboarding/index freshness.",
            "claim_boundary": "no_route_claim",
        }
    elif foreground_action.get("action_id") == "continue_normally":
        weak_route_recovery_card = _weak_route_recovery_card()
        foreground_action = {
            "action_id": "recover_weak_route",
            "tool_name": "search_memory",
            "arguments": {
                "query": "more specific cue or exact phrase",
                "max": 5,
            },
            "cli_command": 'aippocampus search "distinctive exact phrase" --json',
            "why": "A route surfaced without a safe deepen action; refine or exact-search before relying on it.",
            "claim_boundary": "no_claim_before_reopen",
        }
    elif labels_low_specificity and foreground_action.get("tool_name") == "agent_deepen":
        foreground_action = recall_choices.with_low_specificity_foreground_action(
            foreground_action,
            metrics=metrics,
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
        "metrics": _without_empty(
            {
                "requested_max_routes": (payload.get("metrics") or {}).get("requested_max_routes"),
                "effective_max_routes": (payload.get("metrics") or {}).get("effective_max_routes"),
                "memory_packet_count": (payload.get("metrics") or {}).get("memory_packet_count"),
                "deepen_request_count": (payload.get("metrics") or {}).get("deepen_request_count"),
                "route_label_specificity_floor": metrics.get("route_label_specificity_floor"),
                "topic_label_present_count": metrics.get("topic_label_present_count"),
            }
        ),
        "audit_available": bool(payload.get("audit_available")),
        "semantic_gate_diagnostics": semantic_compact,
        "provider_key_bridge": payload.get("provider_key_bridge"),
        "policy_boundary": payload.get("policy_boundary"),
        "output_boundary": "compact_foreground_no_local_private_handles",
        "action_boundary": {
            "primary_action_field": "foreground_action",
            "diagnostics_available_with_detail_full": True,
            "source_reopen_required_for_claims": True,
        },
    }
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
        "source_boundary": payload.get("source_boundary"),
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
