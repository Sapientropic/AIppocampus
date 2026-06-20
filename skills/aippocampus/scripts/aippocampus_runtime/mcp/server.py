#!/usr/bin/env python3
"""Local MCP server for read-mostly AIppocampus memory access."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime import health as aippocampus_health
from aippocampus_runtime.cli.human_io import exit_code_for_payload
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.mcp import memory_health_recovery
from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.mcp.agent_explain_projection import compact_agent_explain_payload
from aippocampus_runtime.mcp.agent_recall_projection import compact_agent_recall_payload
from aippocampus_runtime.mcp.foreground_recovery import (
    missing_input_recovery_card,
)
from aippocampus_runtime.mcp.foreground_recovery import (
    register_thread_recovery as _register_thread_recovery,
)
from aippocampus_runtime.mcp.foreground_recovery import (
    template_tool_action as _template_tool_action,
)
from aippocampus_runtime.mcp.mutation_boundary import UNSUPPORTED_MUTATION_TOOLS
from aippocampus_runtime.mcp.provider_key_bridge import (
    maybe_apply_provider_key_bridge_for_semantic_diagnostic,
)
from aippocampus_runtime.mcp.public_projection import (
    compact_health_payload,
    compact_latest_reply_message,
    compact_recall_context_payload,
    compact_register_thread_payload,
    compact_thread,
    detail_arg,
    public_payload,
)
from aippocampus_runtime.mcp.recall_navigation import (
    RecallNavigationError,
    navigation_error_payload,
    recall_context_packet,
    recall_deepen_packet,
)
from aippocampus_runtime.mcp.runtime_recovery import foreground_mcp_runtime_recovery_payload
from aippocampus_runtime.mcp.sync_status_projection import backend_selection_payload
from aippocampus_runtime.mcp.tool_catalog import TOOLS
from aippocampus_runtime.mcp.tool_readiness import (
    tool_names_summary,
    tool_readiness_summary,
)
from aippocampus_runtime.ops import telepathy_handoff_store
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION
from aippocampus_runtime.recall import why_cli
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    RouteLimitError,
    agent_recall_missing_query_payload,
    compact_aippo_guidance_card,
    handle_from_last_recall_cache,
    last_recall_unavailable_payload,
    mark_last_recall_request_opened,
    missing_handle_payload,
    normalize_route_limit,
    opened_route_keys_from_last_recall_cache,
    query_from_last_recall_cache,
    recall_selector_cache_path,
    write_last_recall_cache,
    write_recall_selector_snapshot,
)
from aippocampus_runtime.recall.background_findings import background_findings_card
from aippocampus_runtime.recall.why_diagnostics import recall_diagnostic_report
from aippocampus_runtime.registry import api as registry
from aippocampus_runtime.registry.store import RegistryWriteBusyError
from aippocampus_runtime.source import latest_reply as latest_reply_module
from aippocampus_runtime.source.search import (
    iter_clean_messages,
    public_search_result,
    search_clean_source,
)
from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage
from conversation_sources import PROVIDER_CHOICES, create_conversation_provider

SCRIPT_DIR = Path(__file__).resolve().parents[2]
SERVER_NAME = "aippocampus"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-11-25"


def cwd_arg(arguments: dict[str, Any]) -> Path:
    return core.canonical_path(str(arguments.get("cwd") or os.getcwd()))


def int_range(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


class MCPArgumentError(ValueError):
    """Invalid MCP arguments that should become client-visible tool errors."""


def route_limit_arg(value: Any, *, default: int) -> int:
    try:
        return normalize_route_limit(value, default=default, field="max")
    except RouteLimitError as exc:
        raise MCPArgumentError(str(exc)) from exc


def agent_continuity_module() -> Any:
    return importlib.import_module("aippocampus_runtime.recall.agent_continuity")


def clean_source_dir_for(arguments: dict[str, Any]) -> Path:
    cwd = cwd_arg(arguments)
    explicit = arguments.get("clean_source_dir")
    if explicit:
        return core.resolve_artifact_path(str(explicit), cwd, core.default_thread_clean_source_dir(cwd))
    global_dir = core.default_thread_clean_source_dir(cwd)
    legacy_dir = cwd / ".aippocampus" / "clean-source"
    if (global_dir / "messages.jsonl").exists() or not (legacy_dir / "messages.jsonl").exists():
        return global_dir
    return legacy_dir


def missing_files(root: Path, required: list[str]) -> list[str]:
    return [name for name in required if not (root / name).exists()]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def text_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "isError": is_error,
    }


def tool_error(
    code: str,
    message: str,
    *,
    arguments: dict[str, Any] | None = None,
    retryable: bool | None = None,
    **details: Any,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if retryable is not None:
        error["retryable"] = retryable
    if details:
        error["details"] = details
    payload: Any = {"ok": False, "error": error}
    if arguments is not None:
        payload = public_payload(arguments, payload)
    return text_result(payload, is_error=True)


def clean_source_unavailable(
    source_dir: Path, required: list[str], arguments: dict[str, Any]
) -> dict[str, Any]:
    return tool_error(
        "clean_source_unavailable",
        "Clean-source artifacts are unavailable for the requested workspace or clean_source_dir.",
        arguments=arguments,
        clean_source_dir=str(source_dir),
        missing_files=missing_files(source_dir, required),
        required_files=required,
    )


def _mcp_template_action(
    *,
    action_id: str,
    tool_name: str,
    arguments_template: dict[str, Any],
    requires: list[str],
    label: str,
    why: str,
    mutation_risk: str = "read_only",
    claim_boundary: str = "no_claim_before_reopen",
) -> dict[str, Any]:
    return {
        "id": action_id,
        "tool_name": tool_name,
        "arguments_template": arguments_template,
        "requires": list(requires),
        "template_only": True,
        "label": label,
        "why": why,
        "mutation_risk": mutation_risk,
        "claim_boundary": claim_boundary,
    }


def _list_threads_missing_registry_actions() -> list[dict[str, Any]]:
    register = _mcp_template_action(
        action_id="register_thread_before_listing",
        tool_name="register_thread",
        arguments_template={"cwd": "{project_cwd}", "provider": "{provider}", "confirm_write": True},
        requires=["cwd", "provider", "confirm_write"],
        label="Register a thread before listing routes",
        why="The registry does not exist yet; choose an explicit provider and confirm the local write before listing.",
        mutation_risk="explicit_local_registry_write",
        claim_boundary="registry_write_not_source_claim",
    )
    status = _mcp_template_action(
        action_id="inspect_thread_registration_status",
        tool_name="memory_health",
        arguments_template={"cwd": "{project_cwd}", "detail": "compact"},
        requires=["cwd"],
        label="Inspect thread registration health",
        why="Use a read-only health check if registration status is unclear.",
        claim_boundary="health_status_not_source_evidence",
    )
    return [register, status]


def _list_threads_ok_actions() -> list[dict[str, Any]]:
    recall_context = _mcp_template_action(
        action_id="recall_context_from_thread_list",
        tool_name="recall_context",
        arguments_template={"intent": "{task_or_memory_cue}"},
        requires=["intent"],
        label="Use recall_context for a task-specific route",
        why="Thread lists orient the registry; use recall_context with a concrete cue before relying on source.",
    )
    full_detail = _mcp_template_action(
        action_id="inspect_list_threads_full_detail",
        tool_name="list_threads",
        arguments_template={"detail": "full"},
        requires=["operator_diagnostic_need"],
        label="Inspect full registry detail only for diagnostics",
        why="Full detail may expose private identifiers; keep it behind an explicit diagnostic need.",
        claim_boundary="operator_detail_not_source_evidence",
    )
    return [recall_context, full_detail]


def clean_source_message_sort_key(item: dict[str, Any]) -> int:
    ordinal = item.get("clean_ordinal")
    if ordinal is not None:
        try:
            return int(ordinal)
        except (TypeError, ValueError):
            pass
    try:
        return int(item.get("source_line") or 0)
    except (TypeError, ValueError):
        return 0


def call_search_memory(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return missing_input_recovery_card(
            code="missing_query",
            message="search_memory requires a non-empty query.",
            tool_name="search_memory",
            arguments=arguments,
            required_any=["query"],
            safe_next_actions=[
                _template_tool_action(
                    "search_memory",
                    {"query": "{specific_cue_or_phrase}", "max": 10},
                    ["query"],
                ),
                _template_tool_action("recall_context", {"intent": "{task_or_memory_cue}"}, ["intent"]),
            ],
        )
    limit = int_range(arguments.get("max"), default=10, minimum=1, maximum=25)
    scope = str(arguments.get("scope") or "current").strip()
    if arguments.get("all") or arguments.get("all_registered_sources"):
        scope = "all_registered_sources"
    if arguments.get("from_last_recall"):
        scope = "last_recall_candidates"
    include_paths = bool(arguments.get("include_private_paths"))
    if scope == "all_registered_sources":
        from aippocampus_runtime.source.registry_search import search_registry_sources

        payload = search_registry_sources(
            [query],
            registry_dir=arguments.get("registry_dir"),
            limit=limit,
            include_paths=include_paths,
            search_budget=str(arguments.get("search_budget") or "default"),
            record_last_search=False,
        )
        payload["limit"] = limit
        payload["mcp_search_scope"] = scope
        return text_result(public_payload(arguments, payload))
    if scope == "last_recall_candidates":
        from aippocampus_runtime.source.last_recall_search import search_last_recall_sources

        request_index = (
            int_range(arguments.get("request_index"), default=0, minimum=0, maximum=25)
            if arguments.get("request_index") is not None
            else None
        )
        payload = search_last_recall_sources(
            [query],
            cwd=cwd_arg(arguments),
            last_recall_path=arguments.get("last_recall_path"),
            recall_selector=arguments.get("recall_selector"),
            request_index=request_index or None,
            limit=limit,
            include_paths=include_paths,
        )
        payload["limit"] = limit
        payload["mcp_search_scope"] = scope
        return text_result(public_payload(arguments, payload), is_error=not bool(payload.get("ok")))
    if scope != "current":
        return missing_input_recovery_card(
            code="unsupported_search_scope",
            message="search_memory scope must be current, all_registered_sources, or last_recall_candidates.",
            tool_name="search_memory",
            arguments=arguments,
            required_any=["scope"],
            safe_next_actions=[
                _template_tool_action(
                    "search_memory",
                    {"query": "{specific_cue_or_phrase}", "scope": "current"},
                    ["query"],
                )
            ],
        )
    source_dir = clean_source_dir_for(arguments)
    required = ["messages.jsonl"]
    if missing_files(source_dir, required):
        return clean_source_unavailable(source_dir, required, arguments)
    result = search_clean_source(
        cwd_arg(arguments),
        [query],
        clean_source_dir=source_dir,
        limit=limit,
    )
    result["limit"] = limit
    include_source_snippets = bool(
        arguments.get("include_source_snippets") or arguments.get("include_snippets")
    )
    payload = public_search_result(
        result,
        include_paths=include_paths,
        metadata_only=not include_source_snippets,
        query_text=query,
    )
    payload["mcp_search_scope"] = "current"
    return text_result(public_payload(arguments, payload))


def registry_dir_arg(arguments: dict[str, Any]) -> Path | None:
    return Path(str(arguments["registry_dir"])).resolve() if arguments.get("registry_dir") else None


def continuity_domains_snapshot_arg(arguments: dict[str, Any]) -> Path | None:
    value = arguments.get("continuity_domains_snapshot")
    return Path(str(value)).resolve() if value else None


def call_recall_context(arguments: dict[str, Any]) -> dict[str, Any]:
    intent = str(arguments.get("intent") or arguments.get("query") or "").strip()
    if not intent:
        return missing_input_recovery_card(
            code="missing_intent",
            message="recall_context requires a non-empty intent or query.",
            tool_name="recall_context",
            arguments=arguments,
            required_any=["intent", "query"],
            safe_next_actions=[
                _template_tool_action(
                    "recall_context",
                    {"intent": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["intent_or_query"],
                ),
                _template_tool_action(
                    "agent_recall",
                    {"query": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["query"],
                ),
                _template_tool_action(
                    "search_memory",
                    {"query": "{exact_phrase_or_cue}", "max": 10},
                    ["query"],
                ),
            ],
        )
    source_dir = clean_source_dir_for(arguments)
    required = ["messages.jsonl"]
    if missing_files(source_dir, required):
        return clean_source_unavailable(source_dir, required, arguments)
    try:
        payload = recall_context_packet(
            intent=intent,
            cwd=cwd_arg(arguments),
            clean_source_dir=source_dir,
            registry_dir=registry_dir_arg(arguments),
            continuity_domains_snapshot_path=continuity_domains_snapshot_arg(arguments),
            max_routes=route_limit_arg(arguments.get("max"), default=5),
        )
    except RecallNavigationError as exc:
        return text_result(public_payload(arguments, navigation_error_payload(exc)), is_error=True)
    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload = compact_recall_context_payload(payload)
    else:
        payload = {"detail": "full", **payload}
    return text_result(public_payload(arguments, payload))


def call_recall_deepen(arguments: dict[str, Any]) -> dict[str, Any]:
    if "handle" not in arguments:
        return missing_input_recovery_card(
            code="missing_recall_handle",
            message="recall_deepen requires a recall_context handle or navigation seed.",
            tool_name="recall_deepen",
            arguments=arguments,
            required_any=["handle"],
            safe_next_actions=[
                _template_tool_action(
                    "recall_context",
                    {"intent": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["intent_or_query"],
                ),
                _template_tool_action(
                    "agent_recall",
                    {"query": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["query"],
                ),
            ],
            staged_followup=[
                _template_tool_action(
                    "recall_context",
                    {"intent": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["intent_or_query"],
                ),
                _template_tool_action(
                    "recall_deepen",
                    {"handle": "{handle_from_recall_context_routes}", "cwd": "{project_cwd}"},
                    ["handle"],
                ),
            ],
            legacy_details={
                "required": ["handle"],
                "next_step_hint": (
                    "Call recall_context with intent/query, then pass a selected route handle "
                    "to recall_deepen."
                ),
                "arguments_template": {
                    "intent": "continue the issue-work context",
                    "cwd": "{project_cwd}",
                },
                "followup_arguments_template": {
                    "handle": "{handle_from_recall_context_routes}",
                    "cwd": "{project_cwd}",
                },
            },
        )
    source_dir = clean_source_dir_for(arguments)
    required = ["messages.jsonl"]
    if missing_files(source_dir, required):
        return clean_source_unavailable(source_dir, required, arguments)
    registry_dir = registry_dir_arg(arguments)
    registry_path = registry.registry_paths(registry_dir)[0]
    lock_path = Path(str(arguments["lock_path"])).resolve() if arguments.get("lock_path") else None
    try:
        payload = recall_deepen_packet(
            handle=arguments.get("handle"),
            clean_source_dir=source_dir,
            registry_path=registry_path if registry_path.exists() else None,
            registry_dir=registry_dir,
            lock_path=lock_path,
            continuity_domains_snapshot_path=continuity_domains_snapshot_arg(arguments),
            max_matches=route_limit_arg(arguments.get("max"), default=5),
        )
    except RecallNavigationError as exc:
        return text_result(public_payload(arguments, navigation_error_payload(exc)), is_error=True)
    return text_result(public_payload(arguments, payload))


def call_agent_recall(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or arguments.get("intent") or "").strip()
    if not query:
        payload = agent_recall_missing_query_payload(
            schema_version=str(getattr(agent_continuity_module(), "SCHEMA_VERSION", "agent-continuity-path-v1")),
            kind="aippocampus_agent_continuity_path",
        )
        return text_result(public_payload(arguments, payload), is_error=True)
    agent = agent_continuity_module()
    provider_bridge_report = maybe_apply_provider_key_bridge_for_semantic_diagnostic(arguments)
    payload = agent.recall(
        query,
        cwd=arguments.get("cwd"),
        clean_source_dir=arguments.get("clean_source_dir"),
        registry_dir=arguments.get("registry_dir"),
        macro_state_path=arguments.get("macro_state_jsonl"),
        project=str(arguments.get("project") or "AIppocampus"),
        max_routes=route_limit_arg(arguments.get("max"), default=agent.MAX_ROUTES),
        attention_router=arguments.get("attention_router_mode")
        or bool(arguments.get("attention_router")),
        run_semantic_gate=bool(arguments.get("run_semantic_gate")),
        semantic_gate_mode=str(
            arguments.get("semantic")
            or arguments.get("semantic_gate_mode")
            or "off"
        ),
        semantic_timeout=int_range(
            arguments.get("semantic_timeout"), default=12, minimum=1, maximum=60
        ),
        opened_route_keys=opened_route_keys_from_last_recall_cache(arguments.get("last_recall_path")),
    )
    if provider_bridge_report is not None:
        payload["provider_key_bridge"] = provider_bridge_report
    cache_written = write_last_recall_cache(
        payload.get("deepen_requests") or [],
        query=query,
        cwd=arguments.get("cwd"),
        clean_source_dir=arguments.get("clean_source_dir"),
        registry_dir=arguments.get("registry_dir"),
        macro_state_path=arguments.get("macro_state_jsonl"),
        project=str(arguments.get("project") or "AIppocampus"),
        max_matches=route_limit_arg(arguments.get("max"), default=agent.MAX_ROUTES),
        schema_version=str(getattr(agent, "SCHEMA_VERSION", "agent-continuity-path-v1")),
        path=arguments.get("last_recall_path"),
    )
    selector_id = write_recall_selector_snapshot(arguments.get("last_recall_path")) if cache_written else None
    payload["last_recall_cache_available"] = cache_written
    payload["recall_selector_available"] = bool(selector_id)
    payload["recall_selector_id"] = selector_id
    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload["query"] = query
        payload = compact_agent_recall_payload(payload)
    else:
        payload = {"detail": "full", **payload}
    return text_result(public_payload(arguments, payload))


def call_agent_aippo(arguments: dict[str, Any]) -> dict[str, Any]:
    agent = agent_continuity_module()
    task = str(arguments.get("task") or "")
    payload = agent.activate_aippo(task=task)
    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload = compact_aippo_guidance_card(payload, task=task)
    else:
        payload = {"detail": "full", "output_boundary": "local_private_diagnostic_full", **payload}
    is_error = payload.get("ok") is False or payload.get("status") == "needs_input"
    return text_result(public_payload(arguments, payload), is_error=is_error)


def call_agent_background(arguments: dict[str, Any]) -> dict[str, Any]:
    cue = str(arguments.get("cue") or arguments.get("query") or arguments.get("task") or "").strip()
    payload = background_findings_card(
        cue,
        registry_dir=arguments.get("registry_dir"),
        working_memory_path=arguments.get("working_memory_path"),
        project=str(arguments.get("project") or "AIppocampus"),
        limit=int_range(arguments.get("limit"), default=4, minimum=1, maximum=12),
        detail=str(arguments.get("detail") or "compact"),
    )
    is_error = payload.get("ok") is False or payload.get("status") == "needs_input"
    return text_result(public_payload(arguments, payload), is_error=is_error)


def call_agent_deepen(arguments: dict[str, Any]) -> dict[str, Any]:
    handle = arguments.get("handle")
    cached_context: dict[str, Any] = {}
    request_index_arg: int | None = None
    selector_cache_path: str | Path | None = arguments.get("last_recall_path")
    if handle is None and (
        arguments.get("recall_selector") or arguments.get("last_recall") or "request_index" in arguments
    ):
        request_index = int_range(arguments.get("request_index"), default=1, minimum=1, maximum=25)
        request_index_arg = request_index
        try:
            if arguments.get("recall_selector"):
                selector_cache_path = recall_selector_cache_path(
                    str(arguments.get("recall_selector") or ""),
                    last_recall_path_value=arguments.get("last_recall_path"),
                )
            handle, cached_context = handle_from_last_recall_cache(
                request_index=request_index,
                path=selector_cache_path,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            payload = last_recall_unavailable_payload(
                mode="deepen",
                exc=exc,
                schema_version=str(getattr(agent_continuity_module(), "SCHEMA_VERSION", "agent-continuity-path-v1")),
                kind="aippocampus_agent_continuity_path",
                cue=query_from_last_recall_cache(selector_cache_path),
            )
            return text_result(public_payload(arguments, payload), is_error=True)
    if handle is None:
        payload = missing_handle_payload(
            mode="deepen",
            schema_version=str(getattr(agent_continuity_module(), "SCHEMA_VERSION", "agent-continuity-path-v1")),
            kind="aippocampus_agent_continuity_path",
        )
        return text_result(public_payload(arguments, payload), is_error=True)
    agent = agent_continuity_module()
    payload = agent.deepen(
        handle,
        cwd=arguments.get("cwd") or cached_context.get("cwd"),
        clean_source_dir=arguments.get("clean_source_dir") or cached_context.get("clean_source_dir"),
        registry_dir=arguments.get("registry_dir") or cached_context.get("registry_dir"),
        macro_state_path=arguments.get("macro_state_jsonl") or cached_context.get("macro_state_jsonl"),
        project=str(arguments.get("project") or cached_context.get("project") or "AIppocampus"),
        max_matches=route_limit_arg(
            arguments["max"] if "max" in arguments else cached_context.get("max"),
            default=agent.MAX_ROUTES,
        ),
    )
    if request_index_arg is not None and payload.get("status") == "ok":
        try:
            mark_last_recall_request_opened(
                request_index_arg,
                path=selector_cache_path,
                outcome="source_open",
            )
        except Exception:
            pass
    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload = compact_agent_deepen_payload(
            payload,
            request_index=request_index_arg,
            last_recall=bool(arguments.get("last_recall") or request_index_arg is not None),
            recall_selector=str(arguments.get("recall_selector") or ""),
            surface="mcp_agent_deepen_compact",
        )
    else:
        payload = {"detail": "full", "output_boundary": "local_private_diagnostic_full", **payload}
    is_error = payload.get("status") == "cannot_verify" or payload.get("ok") is False
    return text_result(public_payload(arguments, payload), is_error=is_error)


def call_agent_explain(arguments: dict[str, Any]) -> dict[str, Any]:
    handle = arguments.get("handle")
    cached_context: dict[str, Any] = {}
    request_index_arg: int | None = None
    selector_cache_path: str | Path | None = arguments.get("last_recall_path")
    if handle is None and (
        arguments.get("recall_selector") or arguments.get("last_recall") or "request_index" in arguments
    ):
        request_index = int_range(arguments.get("request_index"), default=1, minimum=1, maximum=25)
        request_index_arg = request_index
        try:
            if arguments.get("recall_selector"):
                selector_cache_path = recall_selector_cache_path(
                    str(arguments.get("recall_selector") or ""),
                    last_recall_path_value=arguments.get("last_recall_path"),
                )
            handle, cached_context = handle_from_last_recall_cache(
                request_index=request_index,
                path=selector_cache_path,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            payload = last_recall_unavailable_payload(
                mode="explain",
                exc=exc,
                schema_version=str(getattr(agent_continuity_module(), "SCHEMA_VERSION", "agent-continuity-path-v1")),
                kind="aippocampus_agent_continuity_path",
                cue=query_from_last_recall_cache(selector_cache_path),
            )
            payload = compact_agent_explain_payload(
                payload,
                request_index=request_index_arg,
                last_recall=True,
                recall_selector=str(arguments.get("recall_selector") or ""),
                surface="mcp_agent_explain_compact",
            )
            return text_result(public_payload(arguments, payload), is_error=True)
    if handle is None:
        payload = missing_handle_payload(
            mode="explain",
            schema_version=str(getattr(agent_continuity_module(), "SCHEMA_VERSION", "agent-continuity-path-v1")),
            kind="aippocampus_agent_continuity_path",
        )
        payload = compact_agent_explain_payload(payload, surface="mcp_agent_explain_compact")
        return text_result(public_payload(arguments, payload), is_error=True)
    agent = agent_continuity_module()
    payload = agent.explain(
        handle,
        macro_state_path=arguments.get("macro_state_jsonl") or cached_context.get("macro_state_jsonl"),
        project=str(arguments.get("project") or cached_context.get("project") or "AIppocampus"),
    )
    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload = compact_agent_explain_payload(
            payload,
            request_index=request_index_arg,
            last_recall=bool(arguments.get("last_recall") or request_index_arg is not None),
            recall_selector=str(arguments.get("recall_selector") or ""),
            surface="mcp_agent_explain_compact",
        )
    else:
        payload = {"detail": "full", "output_boundary": "local_private_diagnostic_full", **payload}
    is_error = payload.get("status") == "cannot_verify" or payload.get("ok") is False
    return text_result(public_payload(arguments, payload), is_error=is_error)


def call_recall_diagnostic(arguments: dict[str, Any]) -> dict[str, Any]:
    cue = str(arguments.get("cue") or arguments.get("intent") or arguments.get("query") or "").strip()
    if not cue:
        return missing_input_recovery_card(
            code="missing_cue",
            message="recall_diagnostic requires a non-empty cue, intent, or query.",
            tool_name="recall_diagnostic",
            arguments=arguments,
            required_any=["cue", "intent", "query"],
            safe_next_actions=[
                _template_tool_action(
                    "recall_diagnostic",
                    {"cue": "{memory_cue_or_route_question}", "mode": "why-recall"},
                    ["cue"],
                ),
                _template_tool_action("agent_recall", {"query": "{memory_cue_or_route_question}"}, ["query"]),
            ],
        )
    provider_bridge_report = maybe_apply_provider_key_bridge_for_semantic_diagnostic(arguments)
    payload = recall_diagnostic_report(
        cue=cue,
        mode=str(arguments.get("mode") or "why-recall"),
        cwd=cwd_arg(arguments),
        clean_source_dir=arguments.get("clean_source_dir"),
        registry_dir=arguments.get("registry_dir"),
        max_routes=route_limit_arg(arguments.get("max"), default=5),
        handle=arguments.get("handle"),
        thread_id=arguments.get("thread_id"),
        topic_epoch=arguments.get("topic_epoch"),
        lock_id=arguments.get("lock_id"),
        lock_path=arguments.get("lock_path"),
        cache_path=arguments.get("cache_path"),
        run_live_semantic_gate=bool(arguments.get("run_semantic_gate")),
        semantic_gate_mode=str(arguments.get("semantic_gate_mode") or "off"),
        semantic_timeout=int_range(
            arguments.get("semantic_timeout"), default=12, minimum=1, maximum=60
        ),
        include_associative_path_diagnostics=bool(
            arguments.get("include_associative_path_diagnostics")
            or arguments.get("apw_diagnostics")
        ),
        associative_path_sidecar_dir=arguments.get("apw_sidecar_dir"),
        associative_path_bridge_path=arguments.get("apw_semantic_bridge_path"),
        associative_path_navigation_path=arguments.get("apw_navigation_path"),
        associative_path_active_lock_path=arguments.get("apw_active_lock_path"),
        associative_path_feedback_path=arguments.get("apw_feedback_path"),
    )
    if provider_bridge_report is not None:
        payload["provider_key_bridge"] = provider_bridge_report
    payload = why_cli.attach_foreground_actions(payload, cue=cue)
    return text_result(public_payload(arguments, payload))


def call_latest_reply(arguments: dict[str, Any]) -> dict[str, Any]:
    cwd = cwd_arg(arguments)
    source_dir = clean_source_dir_for(arguments)
    detail = detail_arg(arguments)
    messages = iter_clean_messages(source_dir / "messages.jsonl")
    final_messages = [
        item
        for item in messages
        if item.get("role") == "assistant"
        and (item.get("is_final") or item.get("phase") == "final_answer")
    ]
    if final_messages and not arguments.get("rollout"):
        raw_message = final_messages[-1]
        message = raw_message if detail == "full" else compact_latest_reply_message(raw_message)
        selector = {
            key: raw_message.get(key)
            for key in ("message_id", "turn_id", "turn_index")
            if raw_message.get(key) not in (None, "")
        }
        full_latest_reply_action = latest_reply_module.latest_reply_tool_action()
        source_reopen_action = {
            "id": "reopen_latest_final_answer_context",
            "tool_name": "get_turn_context",
            "arguments": selector,
            "claim_boundary": "source_open_required_before_quoting",
            "mutation_risk": "read_only",
            "authority_after_running": "source_open_within_clean_source_turn_scope",
            "why": "Use the clean-source selector before quoting exact wording from the compact latest-reply card.",
        }
        return text_result(
            public_payload(
                arguments,
                {
                    "status": "clean_source_final_answer",
                    "detail": detail,
                    "source": str(source_dir / "messages.jsonl"),
                    "message": message,
                    "message_count": len(messages),
                    "source_reopen_action": source_reopen_action,
                    **canonical_foreground_action_fields(
                        full_latest_reply_action,
                        safe_next_actions=[full_latest_reply_action, source_reopen_action],
                    ),
                },
            )
        )
    try:
        rollout = Path(str(arguments["rollout"])) if arguments.get("rollout") else core.locate_rollout(cwd)
        payload = latest_reply_module.latest_reply(rollout)
    except (FileNotFoundError, OSError, ValueError) as exc:
        payload = latest_reply_module.latest_reply_unavailable_payload(exc, detail=detail)
        return text_result(public_payload(arguments, payload), is_error=True)
    if isinstance(payload, dict):
        payload = latest_reply_module.public_latest_reply_result(payload, detail=detail)
    return text_result(public_payload(arguments, payload))


def call_get_turn_context(arguments: dict[str, Any]) -> dict[str, Any]:
    source_dir = clean_source_dir_for(arguments)
    turn_id = arguments.get("turn_id")
    message_id = arguments.get("message_id")
    turn_index = arguments.get("turn_index")
    if not turn_id and not message_id and turn_index is None:
        return missing_input_recovery_card(
            code="missing_turn_selector",
            message="get_turn_context requires turn_id, message_id, or turn_index.",
            tool_name="get_turn_context",
            arguments=arguments,
            required_any=["turn_id", "message_id", "turn_index"],
            safe_next_actions=[
                _template_tool_action(
                    "agent_recall",
                    {"query": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["query"],
                ),
                _template_tool_action(
                    "recall_context",
                    {"intent": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["intent_or_query"],
                ),
            ],
            staged_followup=[
                _template_tool_action(
                    "agent_recall",
                    {"query": "{task_or_memory_cue}", "cwd": "{project_cwd}"},
                    ["query"],
                ),
                _template_tool_action(
                    "get_turn_context",
                    {"message_id": "{message_id_from_selected_route}"},
                    ["message_id"],
                ),
            ],
        )

    required = ["messages.jsonl", "turns.jsonl"]
    if missing_files(source_dir, required):
        return clean_source_unavailable(source_dir, required, arguments)

    messages = iter_clean_messages(source_dir / "messages.jsonl")
    turns = read_jsonl(source_dir / "turns.jsonl")

    if not turn_id and message_id:
        matched = next(
            (
                item
                for item in messages
                if item.get("message_id") == message_id or item.get("id") == message_id
            ),
            None,
        )
        if matched:
            turn_id = matched.get("turn_id")
            turn_index = matched.get("turn_index")
        else:
            return tool_error(
                "message_not_found",
                "No clean-source message matched the requested message_id.",
                arguments=arguments,
                message_id=str(message_id),
                source=str(source_dir / "messages.jsonl"),
            )

    selected_turn = None
    for turn in turns:
        if turn_id and turn.get("turn_id") == turn_id:
            selected_turn = turn
            break
        if turn_index is not None and turn.get("turn_index") == turn_index:
            selected_turn = turn
            break
    if selected_turn is None:
        return tool_error(
            "turn_not_found",
            "No clean-source turn matched the requested identifier.",
            arguments=arguments,
            turn_id=str(turn_id) if turn_id is not None else None,
            turn_index=turn_index,
        )

    message_ids = set(selected_turn.get("message_ids") or [])
    selected_messages = [
        item
        for item in messages
        if item.get("message_id") in message_ids
        or item.get("id") in message_ids
        or item.get("turn_id") == selected_turn.get("turn_id")
    ]
    selected_messages.sort(key=clean_source_message_sort_key)
    return text_result(
        public_payload(
            arguments,
            {
                "source": str(source_dir),
                "turn": selected_turn,
                "messages": selected_messages,
            },
        )
    )

def call_list_threads(arguments: dict[str, Any]) -> dict[str, Any]:
    registry_dir = (
        Path(str(arguments["registry_dir"])).resolve() if arguments.get("registry_dir") else None
    )
    json_path, _ = registry.registry_paths(registry_dir)
    detail = detail_arg(arguments)
    if not json_path.exists():
        actions = _list_threads_missing_registry_actions()
        return text_result(
            {
                "status": "registry_missing",
                "detail": detail,
                "registry": str(json_path)
                if arguments.get("include_private_paths")
                else LOCAL_PATH_REDACTION,
                "threads": [],
                "count": 0,
                **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
            }
        )
    payload = registry.load_registry(json_path)
    default_limit = 5 if detail == "compact" else len(payload.get("threads") or []) or 0
    limit = int_range(arguments.get("max"), default=default_limit, minimum=1, maximum=100)
    raw_threads = list(payload.get("threads") or [])[:limit]
    include_private_identifiers = bool(
        arguments.get("include_private_identifiers") or arguments.get("include_private_paths")
    )
    threads = (
        [
            compact_thread(
                item,
                include_private_identifiers=include_private_identifiers,
            )
            for item in raw_threads
        ]
        if detail == "compact"
        else raw_threads
    )
    actions = _list_threads_ok_actions()
    return text_result(
        public_payload(
            arguments,
            {
                "status": "ok",
                "detail": detail,
                "registry": str(json_path),
                "threads": threads,
                "count": len(threads),
                "total_count": len(payload.get("threads") or []),
                "identifier_boundary": (
                    "private_identifiers_included"
                    if include_private_identifiers
                    else "compact_thread_handles_are_stable_local_fingerprints"
                ),
                **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
            },
        )
    )


def call_register_thread(arguments: dict[str, Any]) -> dict[str, Any]:
    if not arguments.get("confirm_write") and not arguments.get("write"):
        return _register_thread_recovery(
            arguments,
            "register_thread writes to the local AIppocampus registry and requires cwd, provider, and confirm_write=true.",
        )
    if not str(arguments.get("cwd") or "").strip() or not str(arguments.get("provider") or "").strip():
        return _register_thread_recovery(
            arguments,
            "register_thread requires explicit cwd and provider before writing the local registry.",
        )
    registry_dir = (
        Path(str(arguments["registry_dir"])).resolve() if arguments.get("registry_dir") else None
    )
    provider_name = str(arguments.get("provider") or "")
    try:
        provider = create_conversation_provider(provider_name, codex_home_dir=core.codex_home())
    except ValueError:
        return tool_error(
            "provider_not_available",
            "The requested conversation provider is not available for register_thread.",
            arguments=arguments,
            provider=provider_name,
            supported=list(PROVIDER_CHOICES),
        )
    try:
        result = registry.register_current_thread(
            cwd_arg(arguments),
            registry_dir=registry_dir,
            build_index=bool(arguments.get("build_index")),
            provider=provider,
        )
    except RegistryWriteBusyError as exc:
        return tool_error(
            "registry_writer_busy",
            "Another local agent is updating the AIppocampus registry. Retry after it finishes.",
            arguments=arguments,
            retryable=True,
            wait_timeout_seconds=exc.wait_timeout_seconds,
            registry=str(exc.registry_path),
        )
    if not arguments.get("include_private_paths"):
        result = compact_register_thread_payload(result)
    return text_result(public_payload(arguments, result))


def call_sync_status(arguments: dict[str, Any]) -> dict[str, Any]:
    cwd = cwd_arg(arguments)
    if arguments.get("object_store_url"):
        token_env = str(arguments.get("token_env") or "AIPPOCAMPUS_OBJECT_STORE_TOKEN")
        return text_result(
            public_payload(
                arguments,
                sync_object_storage.status_object_storage_bundle(
                    str(arguments["object_store_url"]),
                    prefix=str(arguments.get("object_prefix") or sync_object_storage.DEFAULT_PREFIX),
                    token=os.environ.get(token_env),
                ),
            )
        )
    if arguments.get("sync_dir"):
        return text_result(
            public_payload(arguments, sync_bundle.status_sync_bundle(str(arguments["sync_dir"])))
        )

    return text_result(
        public_payload(
            arguments,
            backend_selection_payload(cwd, diagnostic=bool(arguments.get("diagnostic"))),
        )
    )


def call_memory_health(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = aippocampus_health.health_report(cwd_arg(arguments))
    except Exception as exc:
        del exc
        payload = memory_health_recovery.payload_for_health_exception(arguments)
        return text_result(public_payload(arguments, payload), is_error=False)

    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload = compact_health_payload(payload)
    elif isinstance(payload, dict):
        payload = {"detail": "full", **payload}
    if isinstance(payload, dict):
        payload = memory_health_recovery.recall_first_health_payload(arguments, payload)
    return text_result(public_payload(arguments, payload))


def call_list_telepathy_handoffs(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = telepathy_handoff_store.list_handoffs_payload(
        cwd=cwd_arg(arguments),
        store_path=arguments.get("store_path"),
        scope=arguments.get("scope"),
        status=str(arguments.get("status") or "active"),
        limit=int_range(arguments.get("max"), default=20, minimum=1, maximum=100),
    )
    return text_result(public_payload(arguments, payload))


def call_deepen_telepathy_handoff(arguments: dict[str, Any]) -> dict[str, Any]:
    card_id = str(arguments.get("card_id") or "").strip()
    if not card_id:
        return missing_input_recovery_card(
            code="missing_telepathy_handoff_card_id",
            message="deepen_telepathy_handoff requires a card_id.",
            tool_name="deepen_telepathy_handoff",
            arguments=arguments,
            required_any=["card_id"],
            safe_next_actions=[
                {
                    "tool_name": "list_telepathy_handoffs",
                    "arguments": {"status": "active", "max": 20},
                },
                _template_tool_action(
                    "deepen_telepathy_handoff",
                    {"card_id": "{card_id_from_list_telepathy_handoffs_cards}"},
                    ["card_id"],
                ),
            ],
        )
    payload = telepathy_handoff_store.deepen_handoff_payload(
        card_id=card_id,
        cwd=cwd_arg(arguments),
        store_path=arguments.get("store_path"),
    )
    return text_result(public_payload(arguments, payload), is_error=not bool(payload.get("ok")))


TOOL_CALLS = {
    "agent_recall": call_agent_recall,
    "agent_aippo": call_agent_aippo,
    "agent_background": call_agent_background,
    "agent_deepen": call_agent_deepen,
    "agent_explain": call_agent_explain,
    "search_memory": call_search_memory,
    "recall_context": call_recall_context,
    "recall_deepen": call_recall_deepen,
    "recall_diagnostic": call_recall_diagnostic,
    "latest_reply": call_latest_reply,
    "get_turn_context": call_get_turn_context,
    "list_threads": call_list_threads,
    "register_thread": call_register_thread,
    "sync_status": call_sync_status,
    "memory_health": call_memory_health,
    "list_telepathy_handoffs": call_list_telepathy_handoffs,
    "deepen_telepathy_handoff": call_deepen_telepathy_handoff,
}


def jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    protocol = str(params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION)
    return {
        "protocolVersion": protocol,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    raw_params = request.get("params")
    params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}

    if request_id is None:
        return None
    if method == "initialize":
        return jsonrpc_result(request_id, initialize_result(params))
    if method in {"tools/list", "resources/list", "resources/templates/list"}:
        result = {"tools": TOOLS} if method == "tools/list" else {"resources": []} if method == "resources/list" else {"resourceTemplates": []}
        return jsonrpc_result(request_id, result)
    if method == "tools/call":
        if raw_params is not None and not isinstance(raw_params, dict):
            return jsonrpc_result(
                request_id,
                tool_error(
                    "malformed_params",
                    "tools/call params must be an object.",
                    expected="object",
                    actual=type(raw_params).__name__,
                ),
            )
        name = str(params.get("name") or "")
        if not name:
            return jsonrpc_result(
                request_id,
                tool_error(
                    "missing_tool_name",
                    "tools/call requires a tool name.",
                    required=["name"],
                ),
            )
        raw_arguments = params.get("arguments")
        if raw_arguments is None:
            arguments: dict[str, Any] = {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            return jsonrpc_result(
                request_id,
                tool_error(
                    "malformed_arguments",
                    "tools/call arguments must be an object when provided.",
                    expected="object",
                    actual=type(raw_arguments).__name__,
                ),
            )
        handler = TOOL_CALLS.get(name)
        if handler is None:
            if name in UNSUPPORTED_MUTATION_TOOLS:
                return jsonrpc_result(
                    request_id,
                    tool_error(
                        "unsupported_mutation",
                        "This MCP server is read-mostly; the requested mutating tool is not exposed.",
                        arguments=arguments,
                        requested_tool=name,
                    ),
                )
            return jsonrpc_result(
                request_id,
                tool_error("unknown_tool", f"Unknown tool: {name}", arguments=arguments),
            )
        try:
            return jsonrpc_result(request_id, handler(arguments))
        except MCPArgumentError as exc:
            return jsonrpc_result(
                request_id,
                tool_error("invalid_argument", str(exc), arguments=arguments),
            )
        except Exception as exc:
            if name in {
                "agent_recall",
                "agent_aippo",
                "agent_background",
                "agent_deepen",
                "agent_explain",
            } and isinstance(exc, (ImportError, AttributeError, RuntimeError)):
                payload = foreground_mcp_runtime_recovery_payload(name, exc)
                return jsonrpc_result(
                    request_id,
                    text_result(public_payload(arguments, payload), is_error=True),
                )
            return jsonrpc_result(
                request_id,
                tool_error("tool_failed", f"{type(exc).__name__}: {exc}", arguments=arguments),
            )
    if method in {"notifications/initialized", "ping"}:
        return jsonrpc_result(request_id, {})
    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def handle_payload(payload: Any) -> list[dict[str, Any]]:
    requests = payload if isinstance(payload, list) else [payload]
    responses: list[dict[str, Any]] = []
    for request in requests:
        if not isinstance(request, dict):
            responses.append(jsonrpc_error(None, -32600, "Invalid request"))
            continue
        response = handle_request(request)
        if response is not None:
            responses.append(response)
    return responses


def serve_stdio() -> int:
    seen_request = False
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        seen_request = True
        try:
            payload = json.loads(line)
            responses = handle_payload(payload)
        except json.JSONDecodeError as exc:
            responses = [jsonrpc_error(None, -32700, f"Parse error: {exc}")]
        for response in responses:
            print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    if not seen_request:
        print(json.dumps(tool_readiness_summary(), ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="aippocampus mcp",
        description=(
            "MCP foreground/server entry.\n\n"
            "Action card:\n"
            "  mcp status              Compact readiness card for foreground agents.\n"
            "  mcp list-tools          Full MCP schema catalog for host wiring.\n"
            "  mcp list-tools --json   Full MCP schema catalog for host wiring.\n"
            "  mcp list-tools --compact  Compact readiness card; no schema wall.\n"
            "  mcp --names             Tool names only.\n\n"
            "Bare `aippocampus mcp` remains the stdio server when launched by an MCP host."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", choices=["list-tools", "status"])
    parser.add_argument(
        "--list-tools", action="store_true", help="Print the tool catalog as JSON and exit."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Compatibility no-op for list-tools; MCP catalog output is JSON.",
    )
    parser.add_argument(
        "--compact",
        "--summary-json",
        action="store_true",
        dest="summary_json",
        help="For list-tools, emit a compact tool-readiness summary instead of full schemas.",
    )
    parser.add_argument(
        "--names",
        action="store_true",
        help="For list-tools, emit only visible tool names as JSON.",
    )
    args = parser.parse_args(raw_argv)
    if args.names and args.command is None:
        payload = tool_names_summary()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return exit_code_for_payload(payload)
    if args.list_tools or args.command in {"list-tools", "status"}:
        if args.summary_json or args.command == "status":
            payload = tool_readiness_summary()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return exit_code_for_payload(payload)
        if args.names:
            payload = tool_names_summary()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return exit_code_for_payload(payload)
        payload = {"ok": True, "tools": TOOLS}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return exit_code_for_payload(payload)
    if not raw_argv and sys.stdin.isatty():
        payload = tool_readiness_summary()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return exit_code_for_payload(payload)
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
