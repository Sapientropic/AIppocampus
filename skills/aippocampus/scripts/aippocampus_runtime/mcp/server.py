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
from aippocampus_runtime.mcp.mutation_boundary import UNSUPPORTED_MUTATION_TOOLS
from aippocampus_runtime.mcp.provider_key_bridge import (
    maybe_apply_provider_key_bridge_for_semantic_diagnostic,
)
from aippocampus_runtime.mcp.public_projection import (
    compact_health_payload,
    compact_message,
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
from aippocampus_runtime.mcp.sync_status_projection import backend_selection_payload
from aippocampus_runtime.mcp.tool_catalog import TOOLS
from aippocampus_runtime.mcp.tool_readiness import (
    tool_names_summary,
    tool_readiness_summary,
)
from aippocampus_runtime.ops import telepathy_handoff_store
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    RouteLimitError,
    normalize_route_limit,
)
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


def call_search_memory(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return tool_error(
            "missing_query", "search_memory requires a non-empty query.", arguments=arguments
        )
    limit = int_range(arguments.get("max"), default=10, minimum=1, maximum=25)
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
        include_paths=bool(arguments.get("include_private_paths")),
        metadata_only=not include_source_snippets,
    )
    if not include_source_snippets:
        payload["agent_next_action"] = (
            "Use recall_context or recall_deepen before quoting source; "
            "set include_source_snippets=true only for local diagnostic work."
        )
    return text_result(public_payload(arguments, payload))


def registry_dir_arg(arguments: dict[str, Any]) -> Path | None:
    return Path(str(arguments["registry_dir"])).resolve() if arguments.get("registry_dir") else None


def continuity_domains_snapshot_arg(arguments: dict[str, Any]) -> Path | None:
    value = arguments.get("continuity_domains_snapshot")
    return Path(str(value)).resolve() if value else None


def call_recall_context(arguments: dict[str, Any]) -> dict[str, Any]:
    intent = str(arguments.get("intent") or arguments.get("query") or "").strip()
    if not intent:
        return tool_error(
            "missing_intent",
            "recall_context requires a non-empty intent or query.",
            arguments=arguments,
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
    return text_result(public_payload(arguments, payload))


def call_recall_deepen(arguments: dict[str, Any]) -> dict[str, Any]:
    if "handle" not in arguments:
        return tool_error(
            "missing_recall_handle",
            "recall_deepen requires a recall_context handle or navigation seed.",
            arguments=arguments,
            required=["handle"],
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
        return tool_error(
            "missing_query",
            "agent_recall requires a non-empty query or intent.",
            arguments=arguments,
        )
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
    )
    if provider_bridge_report is not None:
        payload["provider_key_bridge"] = provider_bridge_report
    return text_result(public_payload(arguments, payload))


def call_agent_aippo(arguments: dict[str, Any]) -> dict[str, Any]:
    agent = agent_continuity_module()
    payload = agent.activate_aippo(task=str(arguments.get("task") or ""))
    return text_result(public_payload(arguments, payload))


def call_agent_deepen(arguments: dict[str, Any]) -> dict[str, Any]:
    if "handle" not in arguments:
        return tool_error(
            "missing_agent_handle",
            "agent_deepen requires an opaque handle from agent_recall or an AIppo route id.",
            arguments=arguments,
            required=["handle"],
        )
    agent = agent_continuity_module()
    payload = agent.deepen(
        arguments.get("handle"),
        cwd=arguments.get("cwd"),
        clean_source_dir=arguments.get("clean_source_dir"),
        registry_dir=arguments.get("registry_dir"),
        macro_state_path=arguments.get("macro_state_jsonl"),
        project=str(arguments.get("project") or "AIppocampus"),
        max_matches=route_limit_arg(arguments.get("max"), default=agent.MAX_ROUTES),
    )
    is_error = payload.get("status") == "cannot_verify" or payload.get("ok") is False
    return text_result(public_payload(arguments, payload), is_error=is_error)


def call_agent_explain(arguments: dict[str, Any]) -> dict[str, Any]:
    if "handle" not in arguments:
        return tool_error(
            "missing_agent_handle",
            "agent_explain requires an opaque handle from agent_recall or an AIppo route id.",
            arguments=arguments,
            required=["handle"],
        )
    agent = agent_continuity_module()
    payload = agent.explain(
        arguments.get("handle"),
        macro_state_path=arguments.get("macro_state_jsonl"),
        project=str(arguments.get("project") or "AIppocampus"),
    )
    return text_result(public_payload(arguments, payload))


def call_recall_diagnostic(arguments: dict[str, Any]) -> dict[str, Any]:
    cue = str(arguments.get("cue") or arguments.get("intent") or arguments.get("query") or "").strip()
    if not cue:
        return tool_error(
            "missing_cue",
            "recall_diagnostic requires a non-empty cue, intent, or query.",
            arguments=arguments,
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
    )
    if provider_bridge_report is not None:
        payload["provider_key_bridge"] = provider_bridge_report
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
        message = final_messages[-1] if detail == "full" else compact_message(final_messages[-1])
        return text_result(
            public_payload(
                arguments,
                {
                    "status": "clean_source_final_answer",
                    "detail": detail,
                    "source": str(source_dir / "messages.jsonl"),
                    "message": message,
                    "message_count": len(messages),
                    "agent_next_action": (
                        "Use this compact final-answer preview for orientation; "
                        "call get_turn_context or recall_deepen before quoting exact wording."
                    ),
                },
            )
        )
    rollout = Path(str(arguments["rollout"])) if arguments.get("rollout") else core.locate_rollout(cwd)
    payload = latest_reply_module.latest_reply(rollout)
    if isinstance(payload, dict):
        payload = dict(payload)
        payload.setdefault("detail", detail)
    return text_result(public_payload(arguments, payload))


def call_get_turn_context(arguments: dict[str, Any]) -> dict[str, Any]:
    source_dir = clean_source_dir_for(arguments)
    turn_id = arguments.get("turn_id")
    message_id = arguments.get("message_id")
    turn_index = arguments.get("turn_index")
    if not turn_id and not message_id and turn_index is None:
        return tool_error(
            "missing_turn_selector",
            "get_turn_context requires turn_id, message_id, or turn_index.",
            arguments=arguments,
            required_any=["turn_id", "message_id", "turn_index"],
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
    selected_messages.sort(
        key=lambda item: int(item.get("clean_ordinal") or item.get("source_line") or 0)
    )
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
        return text_result(
            {
                "status": "registry_missing",
                "detail": detail,
                "registry": str(json_path)
                if arguments.get("include_private_paths")
                else LOCAL_PATH_REDACTION,
                "threads": [],
                "count": 0,
                "agent_next_action": "Register or sync a thread before listing memory routes.",
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
                "agent_next_action": (
                    "Use recall_context for task-specific routes; request detail=full only for diagnostics."
                ),
            },
        )
    )


def call_register_thread(arguments: dict[str, Any]) -> dict[str, Any]:
    registry_dir = (
        Path(str(arguments["registry_dir"])).resolve() if arguments.get("registry_dir") else None
    )
    provider_name = str(arguments.get("provider") or "codex")
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
        return tool_error("health_check_failed", str(exc), arguments=arguments)

    if detail_arg(arguments) == "compact" and not arguments.get("include_private_paths"):
        payload = compact_health_payload(payload)
    elif isinstance(payload, dict):
        payload = {"detail": "full", **payload}
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
        return tool_error(
            "missing_telepathy_handoff_card_id",
            "deepen_telepathy_handoff requires a card_id.",
            arguments=arguments,
            required=["card_id"],
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
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            responses = handle_payload(payload)
        except json.JSONDecodeError as exc:
            responses = [jsonrpc_error(None, -32700, f"Parse error: {exc}")]
        for response in responses:
            print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aippocampus mcp")
    parser.add_argument("command", nargs="?", choices=["list-tools"])
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
    args = parser.parse_args(argv)
    if args.list_tools or args.command == "list-tools":
        if args.summary_json:
            print(json.dumps(tool_readiness_summary(), ensure_ascii=False, indent=2))
            return 0
        if args.names:
            print(json.dumps(tool_names_summary(), ensure_ascii=False, indent=2))
            return 0
        print(json.dumps({"tools": TOOLS}, ensure_ascii=False, indent=2))
        return 0
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
