from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"

from aippocampus_runtime.recall import agent_continuity
from aippocampus_runtime.recall.agent_recall_cache import (
    recall_selector_cache_path,
    write_last_recall_cache,
    write_recall_selector_snapshot,
)
from tests.aippocampus.frontstage_assertions import (
    assert_compact_frontstage_payload,
)
from tests.aippocampus.product_probe_helpers import (
    call_mcp_tool_payload,
    run_agent_cli,
    write_clean_source_thread,
)


class AgentDeepenCompactProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        write_clean_source_thread(
            self.clean,
            [
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
            ],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

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

    def test_cli_agent_deepen_json_defaults_to_compact_source_court_card(self) -> None:
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.cwd / "last-recall-json.json"),
        }
        recall_proc = run_agent_cli(
            "recall",
            "source-backed continuity",
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--json",
            env=env,
        )
        compact_proc = run_agent_cli("deepen", "--request", "1", "--last-recall", "--json", env=env)
        full_proc = run_agent_cli(
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
        self.assertNotIn("carry_next_actions", compact_payload)
        self.assertNotIn("choose_export_for_next_thread", compact_encoded)
        self.assertNotIn("choose_sync_for_next_device", compact_encoded)
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
        recall_proc = run_agent_cli(
            "recall",
            "source-backed continuity",
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--json",
            env=env,
        )
        compact_proc = run_agent_cli("explain", "--request", "1", "--last-recall", "--json", env=env)
        full_proc = run_agent_cli(
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
        proc = run_agent_cli(
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
        proc = run_agent_cli(
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
        recall_payload = call_mcp_tool_payload(
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
        self.assertNotIn("request_index", route)
        self.assertNotIn("recall_selector", route)
        self.assertNotIn("display_id", route)
        self.assertNotIn("feedback_id", route)
        self.assertNotIn("callable_selector", route)
        self.assertNotIn("private_handle_boundary", route)
        self.assertNotIn('"handle":', encoded_recall)
        self.assertNotIn('"callable_handle":', encoded_recall)
        self.assertNotIn('"source_refs":', encoded_recall)

        explain_payload = call_mcp_tool_payload("agent_explain", route_action["arguments"])
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

        compact_payload = call_mcp_tool_payload("agent_deepen", route_action["arguments"])
        compact_encoded = json.dumps(compact_payload, ensure_ascii=False)
        self.assertEqual(compact_payload["detail"], "compact")
        self.assertEqual(compact_payload["surface"], "mcp_agent_deepen_compact")
        self.assertEqual(compact_payload["source_open_posture"], "target_evidence_opened")
        self.assertNotIn("source_window_summary", compact_payload)
        self.assertEqual(compact_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(compact_payload["foreground_action"]["id"], "use_opened_source_window")
        self.assertNotIn("feedback_actions", compact_payload)
        self.assertNotIn("feedback_boundary", compact_payload)
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
        self.assertNotIn("carry_next_actions", compact_payload)
        self.assertNotIn("AIppocampus 使用 clean source", compact_encoded)

        full_payload = call_mcp_tool_payload(
            "agent_deepen",
            {**route_action["arguments"], "detail": "full"},
        )
        full_encoded = json.dumps(full_payload, ensure_ascii=False)
        self.assertEqual(full_payload["detail"], "full")
        self.assertIn("source_window", full_payload["result"])
        self.assertIn("AIppocampus 使用 clean source", full_encoded)
        self.assertNotIn(str(self.cwd), full_encoded)

    def test_mcp_deepen_translates_blocked_recall_gate_to_diagnostic_posture(self) -> None:
        cache_path = self.cwd / "blocked-gate-last-recall.json"
        self.assertTrue(
            write_last_recall_cache(
                [
                    {
                        "request_index": 1,
                        "route_id": "route_blocked",
                        "handle": {
                            "kind": "source_ref",
                            "route_id": "route_blocked",
                            "source_refs": [
                                {"source_id": "src_test", "message_id": "msg_final"}
                            ],
                        },
                        "source_anchor_gate": {
                            "status": "blocked",
                            "reason": "opened_source_validation_artifact",
                            "opened_anchor_hits": 0,
                            "target_source_matched": False,
                        },
                        "target_source_matched": False,
                        "recommended_evidence_route": False,
                        "route_choice_posture": "low_confidence_source_anchor_gap",
                    }
                ],
                query="黏菌 联想回忆 探索算法",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                registry_dir=self.cwd / "registry",
                macro_state_path=None,
                project="fixture",
                max_matches=5,
                schema_version="agent-continuity-path-v1",
                path=cache_path,
            )
        )
        selector = write_recall_selector_snapshot(cache_path)
        self.assertIsNotNone(selector)

        payload = call_mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": 1,
                "recall_selector": selector,
                "last_recall_path": str(cache_path),
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
            },
        )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["source_open_posture"], "opened_diagnostic_only")
        self.assertEqual(payload["evidence_level"], "not_target_evidence")
        self.assertNotIn("source_anchor_gate", payload)
        self.assertNotIn("recall_gate_context", payload)
        self.assertNotIn("target_source_matched", payload)
        self.assertNotIn("recommended_evidence_route", payload)
        self.assertNotIn("source_anchor_gate", encoded)
        self.assertEqual(payload["foreground_action"]["id"], "treat_opened_source_as_diagnostic")

    def test_selector_ids_do_not_collide_for_identical_fast_cache_writes(self) -> None:
        request = {
            "request_index": 1,
            "route_id": "route_same",
            "handle": {
                "kind": "source_ref",
                "route_id": "route_same",
                "source_refs": [{"source_id": "src_test", "message_id": "msg_user"}],
            },
        }
        cache_a = self.cwd / "cache-a" / "last-recall.json"
        cache_b = self.cwd / "cache-b" / "last-recall.json"

        with patch(
            "aippocampus_runtime.recall.agent_recall_cache.secrets.token_hex",
            side_effect=["nonce_a", "nonce_b"],
        ):
            self.assertTrue(
                write_last_recall_cache(
                    [request],
                    query="clean source continuity",
                    cwd=self.cwd,
                    clean_source_dir=self.clean,
                    registry_dir=self.cwd / "registry",
                    macro_state_path=None,
                    project="fixture",
                    max_matches=5,
                    schema_version="agent-continuity-path-v1",
                    path=cache_a,
                )
            )
            self.assertTrue(
                write_last_recall_cache(
                    [request],
                    query="clean source continuity",
                    cwd=self.cwd,
                    clean_source_dir=self.clean,
                    registry_dir=self.cwd / "registry",
                    macro_state_path=None,
                    project="fixture",
                    max_matches=5,
                    schema_version="agent-continuity-path-v1",
                    path=cache_b,
                )
            )

        selector_a = write_recall_selector_snapshot(cache_a)
        selector_b = write_recall_selector_snapshot(cache_b)
        self.assertIsNotNone(selector_a)
        self.assertIsNotNone(selector_b)
        self.assertNotEqual(selector_a, selector_b)

    def test_mcp_selector_survives_without_last_recall_env_path(self) -> None:
        old_registry = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
        old_last_recall = os.environ.get(agent_continuity.LAST_RECALL_CACHE_ENV)
        registry_dir = self.cwd / "registry"
        custom_last_recall = self.cwd / "custom-last-recall" / "last-recall.json"
        os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = str(registry_dir)
        os.environ[agent_continuity.LAST_RECALL_CACHE_ENV] = str(custom_last_recall)

        def restore_env() -> None:
            if old_registry is None:
                os.environ.pop("AIPPOCAMPUS_REGISTRY_DIR", None)
            else:
                os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = old_registry
            if old_last_recall is None:
                os.environ.pop(agent_continuity.LAST_RECALL_CACHE_ENV, None)
            else:
                os.environ[agent_continuity.LAST_RECALL_CACHE_ENV] = old_last_recall

        self.addCleanup(restore_env)

        recall_payload = call_mcp_tool_payload(
            "agent_recall",
            {
                "query": "clean source continuity",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "max": 2,
            },
        )
        action_args = recall_payload["foreground_action"]["arguments"]
        selector = str(action_args.get("recall_selector") or "")
        self.assertTrue(selector, recall_payload)
        self.assertTrue((custom_last_recall.parent / "recall-selectors" / f"{selector}.json").exists())
        self.assertTrue((registry_dir / "agent" / "recall-selectors" / f"{selector}.json").exists())

        os.environ.pop(agent_continuity.LAST_RECALL_CACHE_ENV, None)
        payload = call_mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": 1,
                "recall_selector": selector,
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
            },
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["surface"], "mcp_agent_deepen_compact")
        self.assertEqual(payload["source_open_posture"], "target_evidence_opened")
        self.assertIn("primary_source_snippet", payload)

    def test_mcp_selector_uses_explicit_registry_without_private_cache_path(self) -> None:
        old_registry = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
        old_last_recall = os.environ.get(agent_continuity.LAST_RECALL_CACHE_ENV)
        os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = str(self.cwd / "fallback-registry")
        os.environ.pop(agent_continuity.LAST_RECALL_CACHE_ENV, None)

        def restore_env() -> None:
            if old_registry is None:
                os.environ.pop("AIPPOCAMPUS_REGISTRY_DIR", None)
            else:
                os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = old_registry
            if old_last_recall is None:
                os.environ.pop(agent_continuity.LAST_RECALL_CACHE_ENV, None)
            else:
                os.environ[agent_continuity.LAST_RECALL_CACHE_ENV] = old_last_recall

        self.addCleanup(restore_env)
        registry_dir = self.cwd / "explicit-registry"

        recall_payload = call_mcp_tool_payload(
            "agent_recall",
            {
                "query": "clean source continuity",
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(registry_dir),
                "max": 2,
            },
        )
        action_args = recall_payload["foreground_action"]["arguments"]
        selector = str(action_args.get("recall_selector") or "")
        self.assertTrue(selector, recall_payload)
        explicit_selector = registry_dir / "agent" / "recall-selectors" / f"{selector}.json"
        default_selector = recall_selector_cache_path(selector)
        self.assertTrue(explicit_selector.exists())
        self.assertTrue(default_selector.exists())
        fallback_cache = json.loads(default_selector.read_text(encoding="utf-8"))
        fallback_cache["requests"][0]["local_reopen_token"] = {
            "encoding": "utf8_xor_v1_not_encryption",
            "bytes": [],
        }
        fallback_cache["requests"][0]["handle"] = {"kind": "source_ref"}
        default_selector.write_text(
            json.dumps(fallback_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        payload = call_mcp_tool_payload(
            "agent_deepen",
            {
                "request_index": 1,
                "recall_selector": selector,
                "cwd": str(self.cwd),
                "clean_source_dir": str(self.clean),
                "registry_dir": str(registry_dir),
            },
        )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["surface"], "mcp_agent_deepen_compact")
        self.assertEqual(payload["source_open_posture"], "target_evidence_opened")
        self.assertIn("primary_source_snippet", payload)

if __name__ == "__main__":
    unittest.main()
