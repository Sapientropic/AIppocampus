#!/usr/bin/env python3
"""Local MCP server for read-mostly AIppocampus memory access."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime import health as aippocampus_health
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION, redact_private_paths
from aippocampus_runtime.registry import api as registry
from aippocampus_runtime.source import latest_reply as latest_reply_module
from aippocampus_runtime.source.search import iter_clean_messages, search_clean_source
from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage
from conversation_sources import PROVIDER_CHOICES, create_conversation_provider

SCRIPT_DIR = Path(__file__).resolve().parents[2]
SERVER_NAME = "aippocampus"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-11-25"


def tool_schema(
    name: str, description: str, properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


TOOLS: list[dict[str, Any]] = [
    tool_schema(
        "search_memory",
        "Search clean-source AIppocampus memory for the current or supplied workspace.",
        {
            "query": {"type": "string"},
            "cwd": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 25},
            "clean_source_dir": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
        ["query"],
    ),
    tool_schema(
        "latest_reply",
        "Return the latest assistant final answer for a workspace rollout.",
        {
            "cwd": {"type": "string"},
            "rollout": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "get_turn_context",
        "Return clean-source messages for a turn, message id, or turn index.",
        {
            "cwd": {"type": "string"},
            "turn_id": {"type": "string"},
            "message_id": {"type": "string"},
            "turn_index": {"type": "integer"},
            "clean_source_dir": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "list_threads",
        "List machine-wide registered AIppocampus threads.",
        {
            "registry_dir": {"type": "string"},
            "max": {"type": "integer", "minimum": 1, "maximum": 100},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "register_thread",
        "Explicitly register the current workspace thread in the machine-wide registry.",
        {
            "cwd": {"type": "string"},
            "registry_dir": {"type": "string"},
            "build_index": {"type": "boolean"},
            "provider": {"type": "string", "enum": list(PROVIDER_CHOICES)},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "sync_status",
        "Report current local bundle/sync capability without pushing or pulling data.",
        {
            "cwd": {"type": "string"},
            "sync_dir": {"type": "string"},
            "object_store_url": {"type": "string"},
            "object_prefix": {"type": "string"},
            "token_env": {"type": "string"},
            "include_private_paths": {"type": "boolean"},
        },
    ),
    tool_schema(
        "memory_health",
        "Run the local AIppocampus health check for a workspace.",
        {"cwd": {"type": "string"}, "include_private_paths": {"type": "boolean"}},
    ),
]

UNSUPPORTED_MUTATION_TOOLS = {
    "delete_memory",
    "enable_hook",
    "forget_memory",
    "install_hook",
    "pull_sync",
    "push_sync",
    "repair_sync",
    "store_memory",
    "sync_pull",
    "sync_push",
    "sync_repair",
    "uninstall_hook",
    "update_memory",
    "write_memory",
}


def cwd_arg(arguments: dict[str, Any]) -> Path:
    return Path(str(arguments.get("cwd") or os.getcwd())).resolve()


def int_range(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


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


def public_payload(arguments: dict[str, Any], payload: Any) -> Any:
    if arguments.get("include_private_paths"):
        return payload
    return redact_private_paths(payload)


def tool_error(
    code: str,
    message: str,
    *,
    arguments: dict[str, Any] | None = None,
    **details: Any,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
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
    return text_result(public_payload(arguments, result))


def call_latest_reply(arguments: dict[str, Any]) -> dict[str, Any]:
    cwd = cwd_arg(arguments)
    source_dir = clean_source_dir_for(arguments)
    messages = iter_clean_messages(source_dir / "messages.jsonl")
    final_messages = [
        item
        for item in messages
        if item.get("role") == "assistant"
        and (item.get("is_final") or item.get("phase") == "final_answer")
    ]
    if final_messages and not arguments.get("rollout"):
        return text_result(
            public_payload(
                arguments,
                {
                    "status": "clean_source_final_answer",
                    "source": str(source_dir / "messages.jsonl"),
                    "message": final_messages[-1],
                    "message_count": len(messages),
                },
            )
        )
    rollout = Path(str(arguments["rollout"])) if arguments.get("rollout") else core.locate_rollout(cwd)
    return text_result(public_payload(arguments, latest_reply_module.latest_reply(rollout)))


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
    if not json_path.exists():
        return text_result(
            {
                "status": "registry_missing",
                "registry": str(json_path)
                if arguments.get("include_private_paths")
                else LOCAL_PATH_REDACTION,
                "threads": [],
                "count": 0,
            }
        )
    payload = registry.load_registry(json_path)
    limit = int(arguments.get("max") or len(payload.get("threads") or []) or 0)
    threads = list(payload.get("threads") or [])[:limit]
    return text_result(
        public_payload(
            arguments,
            {
                "status": "ok",
                "registry": str(json_path),
                "threads": threads,
                "count": len(threads),
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
    result = registry.register_current_thread(
        cwd_arg(arguments),
        registry_dir=registry_dir,
        build_index=bool(arguments.get("build_index")),
        provider=provider,
    )
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

    # Without a selected backend, report capability truth rather than claiming
    # a global sync state. This keeps plugin users from assuming cross-device
    # sync is active merely because the MCP server is installed.
    return text_result(
        public_payload(
            arguments,
            {
                "cwd": str(cwd),
                "status": "available_requires_sync_dir",
                "backend": "local_folder",
                "backends": ["local_folder", "http_object_store"],
                "commands": ["status", "push", "pull", "repair"],
                "script": str(SCRIPT_DIR / "sync_bundle.py"),
                "object_storage_script": str(SCRIPT_DIR / "sync_object_storage.py"),
                "sync_flows": {
                    "status": "implemented",
                    "push": "implemented",
                    "pull": "implemented",
                    "repair": "implemented",
                },
                "object_storage": {
                    "backend": "http_object_store",
                    "status": "implemented_requires_object_store_url",
                    "transport": "HTTP PUT/GET object keys",
                },
                "raw_rollout_sync": "explicit_only",
            },
        )
    )


def call_memory_health(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = aippocampus_health.health_report(cwd_arg(arguments))
    except Exception as exc:
        return tool_error("health_check_failed", str(exc), arguments=arguments)

    return text_result(public_payload(arguments, payload))


TOOL_CALLS = {
    "search_memory": call_search_memory,
    "latest_reply": call_latest_reply,
    "get_turn_context": call_get_turn_context,
    "list_threads": call_list_threads,
    "register_thread": call_register_thread,
    "sync_status": call_sync_status,
    "memory_health": call_memory_health,
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
    if method == "tools/list":
        return jsonrpc_result(request_id, {"tools": TOOLS})
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list-tools", action="store_true", help="Print the tool catalog as JSON and exit."
    )
    args = parser.parse_args()
    if args.list_tools:
        print(json.dumps({"tools": TOOLS}, ensure_ascii=False, indent=2))
        return 0
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
