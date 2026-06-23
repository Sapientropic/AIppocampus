from __future__ import annotations

import json
import os
import unittest
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.mcp.compact_profile import mcp_tool_result_payload
from aippocampus_runtime.source.io_kernel import write_jsonl_dict_rows
from tests.aippocampus.cli_fixtures import run_aippocampus_cli


@dataclass(frozen=True)
class SourceOpenExpectation:
    recall_matched_cue_family: str | None = None
    recall_source_chain_role: str | None = None
    deepen_source_chain_role: str | None = None
    target_source_matched: bool | None = None
    thread_key: str | None = None
    message_id: str | None = None
    window_terms: tuple[str, ...] = ()


def write_clean_source_thread(clean_dir: Path, rows: Sequence[Mapping[str, object]]) -> None:
    """Write a minimal clean-source fixture with matching message and turn rows."""

    clean_dir.mkdir(parents=True, exist_ok=True)
    message_rows = [dict(row) for row in rows]
    write_jsonl_dict_rows(clean_dir / "messages.jsonl", message_rows)
    write_jsonl_dict_rows(
        clean_dir / "turns.jsonl",
        (
            {
                "turn_id": row["turn_id"],
                "turn_index": row["turn_index"],
                "message_ids": [row["message_id"]],
                "assistant_phase": row.get("phase") or row.get("role"),
            }
            for row in message_rows
        ),
    )


def run_cli_json(
    test: unittest.TestCase,
    *args: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    merged_env = {**os.environ, **dict(env or {})}
    proc = run_aippocampus_cli(*args, env=merged_env)
    test.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        test.fail(f"CLI did not return JSON: {exc}: {proc.stdout}")
    test.assertIsInstance(payload, dict)
    return payload


def call_mcp_tool_payload(name: str, arguments: Mapping[str, object]) -> dict[str, Any]:
    response = mcp.handle_request(
        {
            "jsonrpc": "2.0",
            "id": f"call-{name}",
            "method": "tools/call",
            "params": {"name": name, "arguments": dict(arguments)},
        }
    )
    return mcp_tool_result_payload(response["result"])


def assert_deepen_opened_expected_source(
    test: unittest.TestCase,
    deepen: Mapping[str, Any],
    expectation: SourceOpenExpectation,
) -> str:
    """Assert a deepen result opened the expected source and anchor text.

    This is the product probe #2632 needs: it fails when recall emits a route
    shape that cannot actually reopen the intended source window.
    """

    test.assertEqual(deepen["status"], "ok")
    if expectation.deepen_source_chain_role is not None:
        test.assertEqual(deepen.get("source_chain_role"), expectation.deepen_source_chain_role)
    if expectation.target_source_matched is not None:
        test.assertEqual(deepen.get("target_source_matched"), expectation.target_source_matched)
    result = deepen.get("result")
    test.assertIsInstance(result, Mapping)
    source_refs = result.get("source_refs") if isinstance(result, Mapping) else None
    test.assertIsInstance(source_refs, list)
    test.assertGreater(len(source_refs), 0)
    first_ref = source_refs[0]
    test.assertIsInstance(first_ref, Mapping)
    if expectation.thread_key is not None:
        test.assertEqual(first_ref.get("thread_key"), expectation.thread_key)
    if expectation.message_id is not None:
        test.assertEqual(first_ref.get("message_id"), expectation.message_id)
    window_text = json.dumps(result.get("source_window"), ensure_ascii=False)
    for term in expectation.window_terms:
        test.assertIn(term, window_text)
    return window_text


def _assert_recall_matched_expected_route(
    test: unittest.TestCase,
    recall: Mapping[str, Any],
    expectation: SourceOpenExpectation,
) -> None:
    test.assertEqual(recall["status"], "ok")
    if expectation.recall_matched_cue_family is not None:
        test.assertEqual(
            recall["memory_packets"][0]["matched_cue_family"],
            expectation.recall_matched_cue_family,
        )
    if expectation.recall_source_chain_role is not None:
        test.assertEqual(
            recall["memory_packets"][0]["source_chain_role"],
            expectation.recall_source_chain_role,
        )
    test.assertTrue(recall["recall_selector_available"])


def assert_cli_recall_deepens_to_source(
    test: unittest.TestCase,
    *,
    cue: str,
    cwd: Path,
    clean_source_dir: Path,
    registry_dir: Path,
    last_recall_path: Path,
    expectation: SourceOpenExpectation,
) -> tuple[dict[str, Any], dict[str, Any]]:
    recall = run_cli_json(
        test,
        "agent",
        "recall",
        cue,
        "--cwd",
        str(cwd),
        "--clean-source-dir",
        str(clean_source_dir),
        "--registry-dir",
        str(registry_dir),
        "--last-recall-path",
        str(last_recall_path),
        "--detail",
        "full",
        "--json",
    )
    _assert_recall_matched_expected_route(test, recall, expectation)
    deepen = run_cli_json(
        test,
        "agent",
        "deepen",
        "--request",
        "1",
        "--recall-selector",
        recall["recall_selector_id"],
        "--last-recall-path",
        str(last_recall_path),
        "--cwd",
        str(cwd),
        "--clean-source-dir",
        str(clean_source_dir),
        "--registry-dir",
        str(registry_dir),
        "--detail",
        "full",
        "--json",
    )
    assert_deepen_opened_expected_source(test, deepen, expectation)
    return recall, deepen


def assert_mcp_recall_deepens_to_source(
    test: unittest.TestCase,
    *,
    cue: str,
    cwd: Path,
    clean_source_dir: Path,
    registry_dir: Path,
    last_recall_path: Path,
    expectation: SourceOpenExpectation,
) -> tuple[dict[str, Any], dict[str, Any]]:
    recall = call_mcp_tool_payload(
        "agent_recall",
        {
            "query": cue,
            "cwd": str(cwd),
            "clean_source_dir": str(clean_source_dir),
            "registry_dir": str(registry_dir),
            "last_recall_path": str(last_recall_path),
            "detail": "full",
        },
    )
    _assert_recall_matched_expected_route(test, recall, expectation)
    deepen = call_mcp_tool_payload(
        "agent_deepen",
        {
            "request_index": 1,
            "recall_selector": recall["recall_selector_id"],
            "last_recall_path": str(last_recall_path),
            "cwd": str(cwd),
            "clean_source_dir": str(clean_source_dir),
            "registry_dir": str(registry_dir),
            "detail": "full",
        },
    )
    assert_deepen_opened_expected_source(test, deepen, expectation)
    return recall, deepen
