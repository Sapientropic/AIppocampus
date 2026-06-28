#!/usr/bin/env python3
"""Local MCP server for read-mostly AIppocampus memory access."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.cli.human_io import exit_code_for_payload
from aippocampus_runtime.mcp import runtime_hot_reload
from aippocampus_runtime.mcp.mutation_boundary import UNSUPPORTED_MUTATION_TOOLS
from aippocampus_runtime.mcp.protocol import initialize_result
from aippocampus_runtime.mcp.result_profile import render_profiled_result
from aippocampus_runtime.mcp.runtime_recovery import (
    foreground_mcp_runtime_recovery_payload,
    looks_like_stale_runtime_signature_mismatch,
)
from aippocampus_runtime.mcp.tool_catalog import TOOLS
from aippocampus_runtime.mcp.tool_handlers import (
    TOOL_CALLS,
    MCPArgumentError,
    tool_error,
)
from aippocampus_runtime.mcp.tool_readiness import (
    tool_names_summary,
    tool_readiness_summary,
)

__all__ = [
    "handle_payload",
    "handle_request",
    "main",
]


def jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

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
            } and (
                isinstance(exc, (ImportError, AttributeError, RuntimeError))
                or looks_like_stale_runtime_signature_mismatch(exc)
            ):
                payload = foreground_mcp_runtime_recovery_payload(name, exc)
                return jsonrpc_result(
                    request_id,
                    render_profiled_result(
                        arguments,
                        payload,
                        is_error=True,
                        full_output_boundary="foreground_mcp_runtime_recovery",
                    ),
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


@dataclass(frozen=True)
class StdioDispatch:
    output: str
    reexec_after_response: bool = False


def _request_id_from_raw(raw_message: str) -> Any:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload.get("id")
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0].get("id")
    return None


def _arguments_from_raw(raw_message: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError:
        return {}
    request = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(request, dict):
        return {}
    params = request.get("params")
    if not isinstance(params, dict):
        return {}
    arguments = params.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def _runtime_hot_reload_failed_response(raw_message: str, summary: str) -> StdioDispatch:
    request_id = _request_id_from_raw(raw_message)
    arguments = _arguments_from_raw(raw_message)
    payload = foreground_mcp_runtime_recovery_payload(
        "mcp_transport",
        RuntimeError(summary),
    )
    result = render_profiled_result(
        arguments,
        payload,
        is_error=True,
        full_output_boundary="foreground_mcp_runtime_hot_reload_recovery",
    )
    return StdioDispatch(
        json.dumps(jsonrpc_result(request_id, result), ensure_ascii=False, separators=(",", ":"))
        + "\n",
        reexec_after_response=False,
    )


def dispatch_stdio_message(raw_message: str) -> StdioDispatch:
    if runtime_hot_reload.runtime_generation_changed():
        try:
            proxied = runtime_hot_reload.proxy_request_through_fresh_runtime(raw_message)
        except Exception as exc:
            return _runtime_hot_reload_failed_response(
                raw_message,
                f"hot reload proxy failed: {type(exc).__name__}: {exc}",
            )
        if proxied.returncode == 0 and proxied.stdout.strip():
            output = proxied.stdout
            if not output.endswith("\n"):
                output += "\n"
            return StdioDispatch(output, reexec_after_response=True)
        return _runtime_hot_reload_failed_response(
            raw_message,
            (
                "hot reload proxy failed: "
                f"exit={proxied.returncode}; stderr={proxied.stderr[-400:]}"
            ),
        )

    try:
        payload = json.loads(raw_message)
        responses = handle_payload(payload)
    except json.JSONDecodeError as exc:
        responses = [jsonrpc_error(None, -32700, f"Parse error: {exc}")]
    output = "".join(
        json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
        for response in responses
    )
    return StdioDispatch(output)


def serve_stdio() -> int:
    seen_request = False
    for raw_message in sys.stdin:
        raw_message = raw_message.strip()
        if not raw_message:
            continue
        seen_request = True
        dispatch = dispatch_stdio_message(raw_message)
        if dispatch.output:
            print(dispatch.output, end="", flush=True)
        if dispatch.reexec_after_response:
            runtime_hot_reload.reexec_current_process()
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
            "  mcp status --detail full  Operator readiness detail, including explicit write fallbacks.\n"
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
    parser.add_argument(
        "--detail",
        choices=["compact", "full"],
        default="compact",
        help="For status, choose compact foreground readiness or full operator detail.",
    )
    args = parser.parse_args(raw_argv)
    if args.names and args.command is None:
        payload = tool_names_summary()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return exit_code_for_payload(payload)
    if args.list_tools or args.command in {"list-tools", "status"}:
        if args.summary_json or args.command == "status":
            payload = tool_readiness_summary(detail=args.detail)
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
