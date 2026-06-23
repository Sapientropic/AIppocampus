#!/usr/bin/env python3
"""Tool-family handlers for the AIppocampus MCP server.

aippocampus-stage-map: handlers collect raw tool payloads and route them
through render_profiled_result/text_result; compact/detail redaction belongs in
the shared MCP profile layer, not in per-tool JSON assembly.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime import health as aippocampus_health
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.mcp import memory_health_recovery
from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.mcp.agent_explain_projection import compact_agent_explain_payload
from aippocampus_runtime.mcp.agent_recall_projection import compact_agent_recall_payload
from aippocampus_runtime.mcp.clean_source_resolution import resolve_mcp_clean_source_dir
from aippocampus_runtime.mcp.compact_profile import (
    compact_mcp_tool_result,
    compact_search_memory_payload,
)
from aippocampus_runtime.mcp.foreground_recovery import (
    missing_input_recovery_card,
)
from aippocampus_runtime.mcp.foreground_recovery import (
    register_thread_recovery as _register_thread_recovery,
)
from aippocampus_runtime.mcp.foreground_recovery import (
    template_tool_action as _template_tool_action,
)
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
    normalize_handle,
    recall_context_packet,
    recall_deepen_packet,
)
from aippocampus_runtime.mcp.result_profile import (
    RuntimeProvenanceContext,
    render_profiled_result,
)
from aippocampus_runtime.mcp.selector_cache import (
    handle_from_selector_or_last_recall,
    recall_cache_path_for_mcp_recall,
)
from aippocampus_runtime.mcp.sync_status_projection import backend_selection_payload
from aippocampus_runtime.mcp.thread_list_projection import (
    list_threads_missing_registry_actions,
    list_threads_ok_actions,
)
from aippocampus_runtime.ops import telepathy_handoff_store
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION
from aippocampus_runtime.recall import agent_deepen_requests, why_cli
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    RouteLimitError,
    agent_recall_missing_query_payload,
    attach_recall_gate_context_to_payload,
    compact_aippo_guidance_card,
    last_recall_unavailable_payload,
    mark_last_recall_request_opened,
    missing_handle_payload,
    normalize_route_limit,
    opened_route_keys_from_last_recall_cache,
    query_from_last_recall_cache,
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
    return resolve_mcp_clean_source_dir(
        cwd=cwd_arg(arguments),
        clean_source_dir=arguments.get("clean_source_dir"),
    )


def recall_clean_source_dir_for(arguments: dict[str, Any]) -> Path:
    return resolve_mcp_clean_source_dir(
        cwd=cwd_arg(arguments),
        clean_source_dir=arguments.get("clean_source_dir"),
        continuity_domains_snapshot=arguments.get("continuity_domains_snapshot"),
    )


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
    return compact_mcp_tool_result(payload, is_error=is_error)


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
            registry_dir=registry_dir_arg(arguments),
            limit=limit,
            include_paths=include_paths,
            search_budget=str(arguments.get("search_budget") or "default"),
            record_last_search=False,
            cwd=cwd_arg(arguments),
        )
        payload["limit"] = limit
        payload["mcp_search_scope"] = scope
        payload["detail"] = "compact"
        payload["surface"] = "mcp_search_memory_compact"
        return render_profiled_result(
            arguments,
            payload,
            compact_projector=lambda raw: compact_search_memory_payload(
                raw,
                include_source_snippets=bool(
                    arguments.get("include_source_snippets") or arguments.get("include_snippets")
                ),
            ),
            runtime_provenance_context=RuntimeProvenanceContext(
                clean_source_dir=clean_source_dir_for(arguments),
                registry_dir=registry_dir_arg(arguments),
            ),
        )
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
        payload["detail"] = "compact"
        payload["surface"] = "mcp_search_memory_compact"
        return render_profiled_result(
            arguments,
            payload,
            is_error=not bool(payload.get("ok")),
            compact_projector=lambda raw: compact_search_memory_payload(
                raw,
                include_source_snippets=bool(
                    arguments.get("include_source_snippets") or arguments.get("include_snippets")
                ),
            ),
            runtime_provenance_context=RuntimeProvenanceContext(
                clean_source_dir=clean_source_dir_for(arguments),
                registry_dir=registry_dir_arg(arguments),
            ),
        )
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
    source_dir = recall_clean_source_dir_for(arguments)
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
    payload["detail"] = "compact"
    payload["surface"] = "mcp_search_memory_compact"
    return render_profiled_result(
        arguments,
        payload,
        compact_projector=lambda raw: compact_search_memory_payload(
            raw,
            include_source_snippets=include_source_snippets,
        ),
        runtime_provenance_context=RuntimeProvenanceContext(
            clean_source_dir=source_dir,
            registry_dir=registry_dir_arg(arguments),
        ),
    )


def registry_dir_arg(arguments: dict[str, Any]) -> Path | None:
    if arguments.get("registry_dir"):
        return Path(str(arguments["registry_dir"])).resolve()
    return core.aippocampus_registry_dir().resolve()


def continuity_domains_snapshot_arg(arguments: dict[str, Any]) -> Path | None:
    value = arguments.get("continuity_domains_snapshot")
    return Path(str(value)).resolve() if value else None


def call_recall_context(arguments: dict[str, Any]) -> dict[str, Any]:
    intent = str(arguments.get("intent") or arguments.get("query") or arguments.get("cue") or "").strip()
    if not intent:
        return missing_input_recovery_card(
            code="missing_intent",
            message="recall_context requires a non-empty intent or query.",
            tool_name="recall_context",
            arguments=arguments,
            required_any=["intent", "query", "cue"],
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
    source_dir = recall_clean_source_dir_for(arguments)
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
    try:
        normalized_handle = normalize_handle(arguments.get("handle"))
    except RecallNavigationError as exc:
        return text_result(public_payload(arguments, navigation_error_payload(exc)), is_error=True)
    source_dir = recall_clean_source_dir_for(arguments)
    required = ["messages.jsonl"]
    if str(normalized_handle.get("kind") or "") != "active_recall_lock" and missing_files(
        source_dir, required
    ):
        return clean_source_unavailable(source_dir, required, arguments)
    registry_dir = registry_dir_arg(arguments)
    registry_path = registry.registry_paths(registry_dir)[0]
    lock_path = Path(str(arguments["lock_path"])).resolve() if arguments.get("lock_path") else None
    try:
        payload = recall_deepen_packet(
            handle=normalized_handle,
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
    query = str(arguments.get("query") or arguments.get("intent") or arguments.get("cue") or "").strip()
    if not query:
        payload = agent_recall_missing_query_payload(
            schema_version=str(getattr(agent_continuity_module(), "SCHEMA_VERSION", "agent-continuity-path-v1")),
            kind="aippocampus_agent_continuity_path",
        )
        return text_result(public_payload(arguments, payload), is_error=True)
    agent = agent_continuity_module()
    cwd_path = cwd_arg(arguments)
    source_dir = clean_source_dir_for(arguments)
    registry_dir = registry_dir_arg(arguments)
    cache_path = recall_cache_path_for_mcp_recall(arguments, registry_dir=registry_dir)
    provider_bridge_report = maybe_apply_provider_key_bridge_for_semantic_diagnostic(arguments)
    payload = agent.recall(
        query,
        cwd=cwd_path,
        clean_source_dir=source_dir,
        registry_dir=registry_dir,
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
        include_associative_fallback=bool(
            arguments.get("include_associative_fallback") or arguments.get("apw_fallback")
        ),
        associative_path_sidecar_dir=arguments.get("apw_sidecar_dir"),
        associative_path_bridge_path=arguments.get("apw_semantic_bridge_path"),
        associative_path_navigation_path=arguments.get("apw_navigation_path"),
        associative_path_active_lock_path=arguments.get("apw_active_lock_path"),
        associative_path_feedback_path=arguments.get("apw_feedback_path"),
    )
    if provider_bridge_report is not None:
        payload["provider_key_bridge"] = provider_bridge_report
    cache_written = write_last_recall_cache(
        payload.get("deepen_requests") or [],
        query=query,
        cwd=cwd_path,
        clean_source_dir=source_dir,
        registry_dir=registry_dir,
        macro_state_path=arguments.get("macro_state_jsonl"),
        project=str(arguments.get("project") or "AIppocampus"),
        max_matches=route_limit_arg(arguments.get("max"), default=agent.MAX_ROUTES),
        schema_version=str(getattr(agent, "SCHEMA_VERSION", "agent-continuity-path-v1")),
        path=cache_path,
    )
    selector_id = write_recall_selector_snapshot(cache_path) if cache_written else None
    if selector_id:
        agent_deepen_requests.attach_recall_selector_to_payload(payload, selector_id)
    payload["last_recall_cache_available"] = cache_written
    payload["recall_selector_available"] = bool(selector_id)
    payload["recall_selector_id"] = selector_id

    def _compact_recall(raw: dict[str, Any]) -> dict[str, Any]:
        raw["query"] = query
        return compact_agent_recall_payload(raw)

    return render_profiled_result(
        arguments,
        payload,
        compact_projector=_compact_recall,
        runtime_provenance_context=RuntimeProvenanceContext(
            clean_source_dir=source_dir,
            registry_dir=registry_dir,
        ),
    )


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
        registry_dir=registry_dir_arg(arguments),
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
            handle, cached_context, selector_cache_path = handle_from_selector_or_last_recall(
                arguments,
                request_index=request_index,
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
        registry_dir=arguments.get("registry_dir")
        or cached_context.get("registry_dir")
        or registry_dir_arg(arguments),
        macro_state_path=arguments.get("macro_state_jsonl") or cached_context.get("macro_state_jsonl"),
        project=str(arguments.get("project") or cached_context.get("project") or "AIppocampus"),
        max_matches=route_limit_arg(
            arguments["max"] if "max" in arguments else cached_context.get("max"),
            default=agent.MAX_ROUTES,
        ),
    )
    apw_identity = cached_context.get("apw_route_identity")
    if isinstance(apw_identity, dict):
        payload["apw_route_identity"] = dict(apw_identity)
        result = payload.get("result")
        if isinstance(result, dict):
            result["apw_route_identity"] = dict(apw_identity)
    attach_recall_gate_context_to_payload(payload, cached_context)
    if request_index_arg is not None and payload.get("status") == "ok":
        try:
            mark_last_recall_request_opened(
                request_index_arg,
                path=selector_cache_path,
                outcome="source_open",
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            # aippocampus-debt-ok: broad-exception-boundary
            # Best-effort selector-cache receipt writes must not break a
            # successful source-open payload or force cache diagnostics into
            # compact MCP output. The reopen result above remains authoritative.
            payload.setdefault("detail_warnings", []).append(
                {
                    "code": "last_recall_open_receipt_not_marked",
                    "message": "source opened, but the local selector cache receipt was not updated",
                    "error_type": type(exc).__name__,
                }
            )
    def _compact_deepen(raw: dict[str, Any]) -> dict[str, Any]:
        return compact_agent_deepen_payload(
            raw,
            request_index=request_index_arg,
            last_recall=bool(arguments.get("last_recall") or request_index_arg is not None),
            recall_selector=str(arguments.get("recall_selector") or ""),
            surface="mcp_agent_deepen_compact",
        )

    is_error = payload.get("status") == "cannot_verify" or payload.get("ok") is False
    return render_profiled_result(
        arguments,
        payload,
        is_error=is_error,
        compact_projector=_compact_deepen,
        full_output_boundary="local_private_diagnostic_full",
    )


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
            handle, cached_context, selector_cache_path = handle_from_selector_or_last_recall(
                arguments,
                request_index=request_index,
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
    def _compact_explain(raw: dict[str, Any]) -> dict[str, Any]:
        return compact_agent_explain_payload(
            raw,
            request_index=request_index_arg,
            last_recall=bool(arguments.get("last_recall") or request_index_arg is not None),
            recall_selector=str(arguments.get("recall_selector") or ""),
            surface="mcp_agent_explain_compact",
        )

    is_error = payload.get("status") == "cannot_verify" or payload.get("ok") is False
    return render_profiled_result(
        arguments,
        payload,
        is_error=is_error,
        compact_projector=_compact_explain,
        full_output_boundary="local_private_diagnostic_full",
    )


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
    cwd_path = cwd_arg(arguments)
    source_dir = clean_source_dir_for(arguments)
    payload = recall_diagnostic_report(
        cue=cue,
        mode=str(arguments.get("mode") or "why-recall"),
        cwd=cwd_path,
        clean_source_dir=source_dir,
        registry_dir=registry_dir_arg(arguments),
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
    return render_profiled_result(
        arguments,
        payload,
        full_output_boundary="local_private_diagnostic_full",
        runtime_provenance_context=RuntimeProvenanceContext(
            clean_source_dir=source_dir,
            registry_dir=registry_dir_arg(arguments),
        ),
    )


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
        actions = list_threads_missing_registry_actions()
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
    actions = list_threads_ok_actions()
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
    except Exception:
        payload = memory_health_recovery.payload_for_health_exception(arguments)
        return render_profiled_result(
            arguments,
            payload,
            is_error=False,
            runtime_provenance_context=RuntimeProvenanceContext(
                clean_source_dir=clean_source_dir_for(arguments),
                registry_dir=registry_dir_arg(arguments),
            ),
        )

    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload = compact_health_payload(payload)
    if isinstance(payload, dict):
        payload = memory_health_recovery.recall_first_health_payload(arguments, payload)
    return render_profiled_result(
        arguments,
        payload,
        runtime_provenance_context=RuntimeProvenanceContext(
            clean_source_dir=clean_source_dir_for(arguments),
            registry_dir=registry_dir_arg(arguments),
        ),
    )


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
