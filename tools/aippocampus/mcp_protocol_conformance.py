#!/usr/bin/env python3
"""Deterministic MCP protocol conformance smoke for AIppocampus."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from repo_paths import ensure_repo_imports
except ModuleNotFoundError:  # pragma: no cover - exercised by package imports.
    from tools.aippocampus.repo_paths import ensure_repo_imports

ensure_repo_imports(Path(__file__))

def _request(method: str, *, request_id: int, params: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def _tool_call(tool_name: str, arguments: Any, *, request_id: int) -> dict[str, Any]:
    return _request(
        "tools/call",
        request_id=request_id,
        params={"name": tool_name, "arguments": arguments},
    )


def _tool_payload(response: Mapping[str, Any]) -> dict[str, Any]:
    from aippocampus_runtime.mcp.compact_profile import mcp_tool_result_payload

    result = response.get("result")
    return mcp_tool_result_payload(result) if isinstance(result, Mapping) else {}


def _case(
    name: str,
    request: Mapping[str, Any],
    *,
    expect_error_code: str | None = None,
    expect_result_key: str | None = None,
) -> dict[str, Any]:
    from aippocampus_runtime.mcp import server

    response = server.handle_request(dict(request))
    ok = isinstance(response, Mapping) and "result" in response
    payload = _tool_payload(response or {})
    error = payload.get("error") if isinstance(payload.get("error"), Mapping) else {}
    if expect_error_code is not None:
        ok = ok and bool(response["result"].get("isError")) and error.get("code") == expect_error_code
    if expect_result_key is not None:
        result = response.get("result") if isinstance(response, Mapping) else {}
        ok = ok and isinstance(result, Mapping) and expect_result_key in result
    return {
        "name": name,
        "ok": bool(ok),
        "expected_error_code": expect_error_code,
        "actual_error_code": error.get("code"),
        "is_error": bool(
            isinstance(response, Mapping)
            and isinstance(response.get("result"), Mapping)
            and response["result"].get("isError")
        ),
    }


def _write_recall_fixture(cwd: Path) -> Path:
    from aippocampus_runtime.core import default_thread_clean_source_dir
    from aippocampus_runtime.source.io_kernel import write_jsonl_dict_rows

    clean = default_thread_clean_source_dir(cwd)
    clean.mkdir(parents=True, exist_ok=True)
    write_jsonl_dict_rows(
        clean / "messages.jsonl",
        [
            {
                "message_id": "msg-mcp-protocol",
                "turn_id": "turn-mcp-protocol",
                "turn_index": 1,
                "source_id": "src-mcp-protocol",
                "source_line": 1,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "MCP protocol conformance anchor for recall and deepen smoke.",
            }
        ],
    )
    return clean


def _successful_recall_deepen_cases(cwd: Path) -> list[dict[str, Any]]:
    from aippocampus_runtime.mcp import server

    clean = _write_recall_fixture(cwd)
    cache = cwd / "last-recall.json"
    recall_response = server.handle_request(
        _tool_call(
            "agent_recall",
            {
                "query": "MCP protocol conformance anchor",
                "cwd": str(cwd),
                "clean_source_dir": str(clean),
                "registry_dir": str(cwd / "registry"),
                "last_recall_path": str(cache),
                "detail": "compact",
            },
            request_id=700,
        )
    )
    recall_payload = _tool_payload(recall_response or {})
    recall_action = recall_payload.get("foreground_action")
    recall_action = recall_action if isinstance(recall_action, Mapping) else {}
    recall_arguments = recall_action.get("arguments")
    recall_arguments = dict(recall_arguments) if isinstance(recall_arguments, Mapping) else {}
    recall_ok = (
        isinstance(recall_response, Mapping)
        and isinstance(recall_response.get("result"), Mapping)
        and not recall_response["result"].get("isError")
        and recall_action.get("tool_name") == "agent_deepen"
        and bool(recall_arguments.get("request_index"))
    )

    deepen_response = server.handle_request(
        _tool_call(
            "agent_deepen",
            {
                **recall_arguments,
                "last_recall_path": str(cache),
                "cwd": str(cwd),
                "clean_source_dir": str(clean),
                "registry_dir": str(cwd / "registry"),
                "detail": "compact",
            },
            request_id=701,
        )
    )
    deepen_payload = _tool_payload(deepen_response or {})
    deepen_anchor_hit = "MCP protocol conformance anchor" in json.dumps(
        deepen_payload,
        ensure_ascii=False,
    )
    deepen_ok = (
        isinstance(deepen_response, Mapping)
        and isinstance(deepen_response.get("result"), Mapping)
        and not deepen_response["result"].get("isError")
        and deepen_payload.get("status") == "ok"
        and deepen_anchor_hit
        and deepen_payload.get("source_open_posture") in {
            "target_evidence_opened",
            "opened_diagnostic_only",
        }
    )
    return [
        {
            "name": "tools_call_agent_recall_success",
            "ok": bool(recall_ok),
            "is_error": bool(
                isinstance(recall_response, Mapping)
                and isinstance(recall_response.get("result"), Mapping)
                and recall_response["result"].get("isError")
            ),
            "foreground_tool": recall_action.get("tool_name"),
        },
        {
            "name": "tools_call_agent_deepen_success",
            "ok": bool(deepen_ok),
            "is_error": bool(
                isinstance(deepen_response, Mapping)
                and isinstance(deepen_response.get("result"), Mapping)
                and deepen_response["result"].get("isError")
            ),
            "status": deepen_payload.get("status"),
            "source_open_posture": deepen_payload.get("source_open_posture"),
            "anchor_hit": deepen_anchor_hit,
        },
    ]


def build_mcp_protocol_conformance_report() -> dict[str, Any]:
    from aippocampus_runtime.mcp.protocol import protocol_policy_payload

    cases = [
        _case(
            "initialize",
            _request(
                "initialize",
                request_id=1,
                params={"protocolVersion": "2025-11-25"},
            ),
            expect_result_key="protocolVersion",
        ),
        _case("tools_list", _request("tools/list", request_id=2), expect_result_key="tools"),
        _case(
            "tools_call_malformed_params",
            _request("tools/call", request_id=3, params=["not", "an", "object"]),
            expect_error_code="malformed_params",
        ),
        _case(
            "tools_call_malformed_arguments",
            _tool_call("agent_recall", ["not", "an", "object"], request_id=4),
            expect_error_code="malformed_arguments",
        ),
        _case(
            "tools_call_unknown_tool",
            _tool_call("unknown_memory_tool", {}, request_id=5),
            expect_error_code="unknown_tool",
        ),
        _case(
            "tools_call_unsupported_mutation",
            _tool_call("delete_memory", {}, request_id=6),
            expect_error_code="unsupported_mutation",
        ),
    ]
    with tempfile.TemporaryDirectory() as raw_tmp:
        cases.extend(_successful_recall_deepen_cases(Path(raw_tmp)))
    failed = [case for case in cases if not case["ok"]]
    return {
        "kind": "aippocampus_mcp_protocol_conformance",
        "ok": not failed,
        "case_count": len(cases),
        "failed_case_count": len(failed),
        "cases": cases,
        "protocol_policy": protocol_policy_payload(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.parse_args(argv)
    payload = build_mcp_protocol_conformance_report()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
