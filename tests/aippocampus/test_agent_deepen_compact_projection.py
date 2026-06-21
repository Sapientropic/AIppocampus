from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"

from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.recall import agent_continuity
from tests.aippocampus.frontstage_assertions import (
    assert_compact_frontstage_payload,
)


class AgentDeepenCompactProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        messages = [
            {
                "message_id": "msg_user",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 2,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "小海马体需要 source-backed continuity。",
            },
            {
                "message_id": "msg_final",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 3,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": "AIppocampus 使用 clean source，而不是摘要替代事实。",
            },
        ]
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in messages:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": "turn_1",
                        "turn_index": 1,
                        "message_ids": ["msg_user", "msg_final"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run_agent(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", "agent", *args],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            env=env,
        )

    def _run_agent_module(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.recall.agent_continuity", *args],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def _tool_payload(self, response: dict) -> dict:
        return json.loads(response["result"]["content"][0]["text"])

    def _call_tool_payload(self, name: str, arguments: dict[str, object]) -> dict:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": f"call-{name}",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        return self._tool_payload(response)

    def test_cli_agent_deepen_json_defaults_to_compact_source_court_card(self) -> None:
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.cwd / "last-recall-json.json"),
        }
        recall_proc = self._run_agent(
            "recall",
            "source-backed continuity",
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--json",
            env=env,
        )
        compact_proc = self._run_agent("deepen", "--request", "1", "--last-recall", "--json", env=env)
        full_proc = self._run_agent(
            "deepen",
            "--request",
            "1",
            "--last-recall",
            "--json",
            "--detail",
            "full",
            env=env,
        )

        self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
        self.assertEqual(compact_proc.returncode, 0, compact_proc.stderr)
        self.assertEqual(full_proc.returncode, 0, full_proc.stderr)
        compact_payload = json.loads(compact_proc.stdout)
        full_payload = json.loads(full_proc.stdout)
        compact_encoded = json.dumps(compact_payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(compact_payload["detail"], "compact")
        self.assertEqual(compact_payload["surface"], "agent_cli_source_court_compact")
        self.assertEqual(compact_payload["source_window_summary"]["message_count"], 2)
        assert_compact_frontstage_payload(self, compact_payload, max_top_level_diagnostics=1)
        self.assertNotIn("result", compact_payload)
        self.assertNotIn("source_window", compact_payload)
        self.assertNotIn('"messages"', compact_encoded)
        self.assertNotIn("macro_navigation_diagnostics", compact_encoded)
        self.assertNotIn("cannot_claim", compact_payload)
        self.assertEqual(
            compact_payload["primary_source_snippet"]["text"],
            "小海马体需要 source-backed continuity。",
        )
        self.assertEqual(
            compact_payload["primary_source_snippet"]["claim_boundary"],
            "exact_wording_inside_this_snippet_only",
        )
        action_ids = [action["id"] for action in compact_payload["safe_next_actions"]]
        self.assertIn("choose_export_for_next_thread", action_ids)
        self.assertIn("choose_sync_for_next_device", action_ids)
        self.assertNotIn("AIppocampus 使用 clean source", compact_encoded)
        self.assertNotIn(str(self.cwd), compact_encoded)

        self.assertEqual(full_payload["detail"], "full")
        self.assertIn("source_window", full_payload["result"])
        self.assertIn("messages", full_payload["result"]["source_window"])
        self.assertIn("AIppocampus 使用 clean source", json.dumps(full_payload, ensure_ascii=False))

    def test_cli_agent_explain_json_defaults_to_compact_route_card(self) -> None:
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.cwd / "last-recall-explain.json"),
        }
        recall_proc = self._run_agent(
            "recall",
            "source-backed continuity",
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--json",
            env=env,
        )
        compact_proc = self._run_agent("explain", "--request", "1", "--last-recall", "--json", env=env)
        full_proc = self._run_agent(
            "explain",
            "--request",
            "1",
            "--last-recall",
            "--json",
            "--detail",
            "full",
            env=env,
        )

        self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
        self.assertEqual(compact_proc.returncode, 0, compact_proc.stderr)
        self.assertEqual(full_proc.returncode, 0, full_proc.stderr)
        compact_payload = json.loads(compact_proc.stdout)
        full_payload = json.loads(full_proc.stdout)
        compact_encoded = json.dumps(compact_payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(compact_payload["detail"], "compact")
        self.assertEqual(compact_payload["kind"], "aippocampus_route_explain_card")
        self.assertEqual(compact_payload["surface"], "agent_cli_route_explain_compact")
        self.assertEqual(compact_payload["decision"], "reopenable_route_available")
        self.assertNotIn("macro_", compact_payload["route_reason"])
        self.assertNotIn("projection_status_", compact_payload["route_reason"])
        self.assertEqual(compact_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn(compact_payload["foreground_action"], compact_payload.get("safe_next_actions", []))
        self.assertEqual(compact_payload["foreground_action"]["tool_name"], "agent_deepen")
        self.assertEqual(compact_payload["foreground_action"]["arguments"]["request_index"], 1)
        self.assertIn(
            "--recall-selector {recall_selector}",
            compact_payload["foreground_action"]["command_template"],
        )
        self.assertEqual(
            compact_payload["foreground_action"]["requires"],
            ["request_index", "recall_selector"],
        )
        self.assertIn(
            "agent deepen --request 1 --last-recall --json",
            compact_payload["foreground_action"]["last_recall_fallback_command"],
        )
        self.assertNotIn("command", compact_payload["foreground_action"])
        self.assertNotIn("cli_command", compact_payload["foreground_action"])
        self.assertEqual(
            compact_payload["claim_boundary"],
            "navigation_only_until_source_reopened",
        )
        self.assertIn("--detail full", compact_payload["detail_command"])
        self.assertNotIn("macro_navigation_diagnostics", compact_payload)
        self.assertNotIn("cannot_claim", compact_encoded)
        self.assertNotIn("source_refs", compact_encoded)
        self.assertNotIn(str(self.cwd), compact_encoded)

        self.assertEqual(full_payload["detail"], "full")
        self.assertIn("explanation", full_payload)
        self.assertIn("macro_navigation_diagnostics", full_payload)
        self.assertIn("cannot_claim", full_payload["explanation"])

    def test_cli_agent_explain_last_recall_error_is_compact_recovery_card(self) -> None:
        proc = self._run_agent(
            "explain",
            "--request",
            "1",
            "--last-recall",
            "--last-recall-path",
            str(self.cwd / "missing-last-recall.json"),
            "--json",
        )

        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["kind"], "aippocampus_route_explain_card")
        self.assertEqual(payload["status"], "cannot_verify")
        self.assertEqual(payload["surface"], "agent_cli_route_explain_compact")
        self.assertEqual(payload["error"]["code"], "last_recall_unavailable")
        self.assertEqual(payload["foreground_action"]["id"], "recall_with_cue_full_detail")
        self.assertIn("agent recall", payload["foreground_action"]["command_template"])
        self.assertNotIn("macro_navigation_diagnostics", payload)
        self.assertNotIn("cannot_claim", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_cli_agent_explain_last_recall_text_redacts_path_and_shows_recovery(self) -> None:
        missing_path = self.cwd / "missing-last-recall.json"
        proc = self._run_agent(
            "explain",
            "--request",
            "1",
            "--last-recall",
            "--last-recall-path",
            str(missing_path),
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("last_recall_unavailable", proc.stdout)
        self.assertIn("Next:", proc.stdout)
        self.assertIn("aippocampus agent recall", proc.stdout)
        self.assertNotIn(str(self.cwd), proc.stdout)
        self.assertNotIn(str(missing_path), proc.stdout)

    def test_agent_continuity_module_deepen_handle_json_returns_recovery_card(self) -> None:
        proc = self._run_agent_module("deepen", "--handle", "not-a-real-handle", "--json")

        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(proc.stderr.strip(), "")
        self.assertEqual(payload["detail"], "compact")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "cannot_verify")
        self.assertEqual(payload["error"]["code"], "malformed_recall_handle")
        self.assertIn("safe_next_actions", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertNotIn("macro_navigation_diagnostics", payload)
        self.assertNotIn("cannot_claim", encoded)

    def test_mcp_recall_routes_expose_actions_and_deepen_detail_modes(self) -> None:
        old_last_recall = os.environ.get(agent_continuity.LAST_RECALL_CACHE_ENV)
        os.environ[agent_continuity.LAST_RECALL_CACHE_ENV] = str(self.cwd / "mcp-last-recall.json")
        self.addCleanup(
            lambda: os.environ.pop(agent_continuity.LAST_RECALL_CACHE_ENV, None)
            if old_last_recall is None
            else os.environ.__setitem__(agent_continuity.LAST_RECALL_CACHE_ENV, old_last_recall)
        )
        recall_payload = self._call_tool_payload(
            "agent_recall",
            {
                "query": "clean source continuity",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "max": 2,
            },
        )
        encoded_recall = json.dumps(recall_payload, ensure_ascii=False, sort_keys=True)
        route = recall_payload["routes"][0]
        route_action = recall_payload["routes"][0]["action"]
        self.assertEqual(route_action["id"], "deepen_this_route")
        self.assertEqual(route_action["tool_name"], "agent_deepen")
        self.assertEqual(route_action["arguments"]["request_index"], 1)
        self.assertIn("recall_selector", route_action["arguments"])
        self.assertIn("--request 1 --recall-selector", route_action["command"])
        self.assertEqual(route["callable_selector"]["kind"], "recall_selector_request_index")
        self.assertEqual(route["callable_selector"]["request_index"], 1)
        self.assertEqual(
            route["callable_selector"]["recall_selector"],
            route_action["arguments"]["recall_selector"],
        )
        self.assertNotIn("display_id", route)
        self.assertNotIn("feedback_id", route)
        self.assertEqual(
            route["private_handle_boundary"],
            "compact_output_redacts_local_private_handle_use_callable_selector",
        )
        self.assertNotIn('"handle":', encoded_recall)
        self.assertNotIn('"callable_handle":', encoded_recall)
        self.assertNotIn('"source_refs":', encoded_recall)

        explain_payload = self._call_tool_payload("agent_explain", route_action["arguments"])
        explain_encoded = json.dumps(explain_payload, ensure_ascii=False)
        self.assertEqual(explain_payload["detail"], "compact")
        self.assertEqual(explain_payload["kind"], "aippocampus_route_explain_card")
        self.assertEqual(explain_payload["surface"], "mcp_agent_explain_compact")
        self.assertEqual(explain_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn(explain_payload["foreground_action"], explain_payload.get("safe_next_actions", []))
        self.assertEqual(explain_payload["foreground_action"]["tool_name"], "agent_deepen")
        self.assertIn("agent deepen --request 1 --recall-selector", explain_payload["foreground_action"]["command"])
        self.assertNotIn("macro_navigation_diagnostics", explain_payload)
        self.assertNotIn("cannot_claim", explain_encoded)

        compact_payload = self._call_tool_payload("agent_deepen", route_action["arguments"])
        compact_encoded = json.dumps(compact_payload, ensure_ascii=False)
        self.assertEqual(compact_payload["detail"], "compact")
        self.assertEqual(compact_payload["surface"], "mcp_agent_deepen_compact")
        self.assertEqual(compact_payload["source_window_summary"]["message_count"], 2)
        self.assertEqual(compact_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(compact_payload["foreground_action"]["id"], "use_opened_source_window")
        self.assertNotIn(compact_payload["foreground_action"], compact_payload["safe_next_actions"])
        feedback_ids = [action["id"] for action in compact_payload["feedback_actions"]]
        self.assertEqual(
            feedback_ids,
            ["mark_route_helpful", "mark_route_wrong", "keep_route_quiet"],
        )
        for action in compact_payload["feedback_actions"]:
            self.assertEqual(action["mutation_risk"], "durable_low_authority_feedback_write")
            self.assertEqual(action["claim_boundary"], "feedback_is_not_source_truth")
            self.assertIn("aippocampus agent feedback", action["command"])
            self.assertNotIn("feedback_id", action["command"])
        self.assertNotIn("result", compact_payload)
        self.assertNotIn("source_window", compact_payload)
        self.assertNotIn('"messages"', compact_encoded)
        self.assertEqual(
            compact_payload["primary_source_snippet"]["text"],
            "小海马体需要 source-backed continuity。",
        )
        self.assertEqual(
            compact_payload["primary_source_snippet"]["source_scope"],
            "opened_window_primary_message",
        )
        carry_ids = [action["id"] for action in compact_payload["carry_next_actions"]]
        self.assertEqual(carry_ids, ["choose_export_for_next_thread", "choose_sync_for_next_device"])
        self.assertNotIn("AIppocampus 使用 clean source", compact_encoded)

        full_payload = self._call_tool_payload(
            "agent_deepen",
            {**route_action["arguments"], "detail": "full"},
        )
        full_encoded = json.dumps(full_payload, ensure_ascii=False)
        self.assertEqual(full_payload["detail"], "full")
        self.assertIn("source_window", full_payload["result"])
        self.assertIn("AIppocampus 使用 clean source", full_encoded)
        self.assertNotIn(str(self.cwd), full_encoded)

if __name__ == "__main__":
    unittest.main()
