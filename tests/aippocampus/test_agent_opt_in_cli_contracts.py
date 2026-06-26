from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.contracts import (
    foreground_action_contract_violations,
)
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.recall import (
    agent_continuity,
)
from tests.aippocampus.frontstage_assertions import assert_semantic_human_output

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

class AgentOptInCliContractsTests(unittest.TestCase):
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
                "text": "继续 agent-native recall opt-in path，但不要把 SECRET_TOKEN=abc123 放进前台。",
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
                "text": "Opt-in continuity should return a compact MemoryPacket, then deepen source before claims.",
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

    def assertCanonicalForegroundAction(self, payload: dict[str, object]) -> None:
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn("next_safe_action", payload)
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        if "foreground_action_contract" in payload:
            self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
            self.assertEqual(foreground_action_contract_violations(payload), [])

    def _append_clean_rows(self, rows: list[dict[str, object]]) -> None:
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _macro_state_path(
        self,
        *,
        active_layer: str = "人",
        momentum: dict[str, object] | None = None,
    ) -> Path:
        macro_path = self.cwd / f"macro-{active_layer}.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=(1, 2, 3),
            source_refs=({"source_id": f"macro-live-{active_layer}"},),
            updated_at=macro_state.utc_now_iso(),
            active_layer=active_layer,
            momentum=momentum,
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        return macro_path

    def _append_default_macro_state(
        self,
        *,
        active_layer: str = "人",
        changing_lines: tuple[int, ...] = (1, 2, 3),
    ) -> Path:
        macro_path = self.cwd / ".aippocampus" / "macro-orientation.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=changing_lines,
            source_refs=({"source_id": f"default-macro-{active_layer}"},),
            updated_at=macro_state.utc_now_iso(),
            active_layer=active_layer,
            momentum={"basis": {"counter_evidence_delta": 0.2}},
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        return macro_path

    def test_cli_agent_feedback_default_lane_is_consumed_by_next_recall(self) -> None:
        registry = self.cwd / "registry"
        env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(registry)}
        base = [sys.executable, "-m", "aippocampus_runtime.cli.facade", "agent"]
        run_kwargs = {
            "cwd": SCRIPTS,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "capture_output": True,
            "check": False,
            "env": env,
        }
        recall_args = [
            *base,
            "recall",
            "agent-native recall opt-in",
            "--cwd",
            str(self.cwd),
            "--clean-source-dir",
            str(self.clean),
            "--json",
        ]
        recall_proc = subprocess.run(recall_args, **run_kwargs)
        self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
        recall_payload = json.loads(recall_proc.stdout)
        self.assertNotIn("route_id", recall_payload["routes"][0])

        detail_proc = subprocess.run([*recall_args, "--detail", "full"], **run_kwargs)
        self.assertEqual(detail_proc.returncode, 0, detail_proc.stderr)
        route_id = json.loads(detail_proc.stdout)["memory_packets"][0]["route_id"]

        feedback_proc = subprocess.run(
            [
                *base,
                "feedback",
                route_id,
                "--outcome",
                "wrong",
                "--cwd",
                str(self.cwd),
                "--json",
            ],
            **run_kwargs,
        )
        self.assertEqual(feedback_proc.returncode, 0, feedback_proc.stderr)
        feedback_payload = json.loads(feedback_proc.stdout)
        self.assertEqual(feedback_payload["write_boundary"]["storage"], "jsonl")
        self.assertEqual(feedback_payload["feedback_lane"]["path_source"], "default_registry")

        full_recall_proc = subprocess.run(
            [
                *base,
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--attention-router",
                "--json",
                "--detail",
                "full",
            ],
            **run_kwargs,
        )

        self.assertEqual(full_recall_proc.returncode, 0, full_recall_proc.stderr)
        full_payload = json.loads(full_recall_proc.stdout)
        calibration = full_payload["attention_router_navigation"]["feedback_calibration"]
        encoded = json.dumps(full_payload, ensure_ascii=False)
        self.assertEqual(calibration["load_status"], "loaded")
        self.assertGreaterEqual(calibration["event_count_loaded"], 1)
        self.assertNotIn(str(registry), encoded)

    def test_cli_agent_recall_default_compact_last_recall_round_trips(self) -> None:
        registry = self.cwd / "registry"
        env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(registry)}
        base = [sys.executable, "-m", "aippocampus_runtime.cli.facade", "agent"]
        run_kwargs = {
            "cwd": SCRIPTS,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "capture_output": True,
            "check": False,
            "env": env,
        }
        recall_proc = subprocess.run(
            [
                *base,
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
            ],
            **run_kwargs,
        )
        self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
        recall_payload = json.loads(recall_proc.stdout)
        recall_action = recall_payload["foreground_action"]
        self.assertIn("--recall-selector", recall_action["command"])
        self.assertRegex(recall_action["command"], r"--recall-selector sel_[0-9a-f]{16}")
        self.assertNotIn(str(registry), recall_proc.stdout)
        selector_id = str(recall_action["arguments"].get("recall_selector") or "")

        overwrite_proc = subprocess.run(
            [
                *base,
                "recall",
                "different intervening recall",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
            ],
            **run_kwargs,
        )
        self.assertEqual(overwrite_proc.returncode, 0, overwrite_proc.stderr)

        deepen_proc = subprocess.run(
            [
                *base,
                "deepen",
                "--request",
                "1",
                "--recall-selector",
                selector_id,
                "--json",
            ],
            **run_kwargs,
        )

        self.assertEqual(deepen_proc.returncode, 0, deepen_proc.stderr)
        deepen_payload = json.loads(deepen_proc.stdout)
        self.assertEqual(deepen_payload["mode"], "deepen")
        self.assertEqual(deepen_payload["status"], "ok")
        self.assertNotIn(str(registry), deepen_proc.stdout)

    def test_cli_agent_recall_default_json_is_compact_foreground(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["mode"], "recall")
        self.assertEqual(payload["surface"], "agent_cli_public_compact")
        self.assertCanonicalForegroundAction(payload)
        self.assertNotIn("action_id", payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_deepen")
        self.assertEqual(payload["foreground_action"]["arguments"]["request_index"], 1)
        self.assertNotIn("cannot_claim", payload)
        self.assertIn("reopen", payload["claim_boundary"])
        self.assertNotIn("output_boundary", payload)
        self.assertNotIn("action_boundary", payload)
        self.assertNotIn("metrics", payload)
        self.assertNotIn("audit_available", payload)
        self.assertNotIn("memory_packets", payload)
        self.assertNotIn("deepen_requests", payload)
        self.assertNotIn("foreground_action_card", payload)
        self.assertNotIn('"copy_paste_command":', encoded)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_cli_agent_recall_full_json_is_explicit_local_diagnostic(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
                "--detail",
                "full",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["detail"], "full")
        self.assertEqual(payload["output_boundary"], "local_private_diagnostic_full")
        self.assertIn("memory_packets", payload)
        self.assertIn("deepen_requests", payload)
        self.assertIn("foreground_action_card", payload)
        self.assertIn("cannot_claim", payload)
        self.assertIn("aippo-nav:", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_cli_agent_feedback_rejects_unknown_route_kind_as_structured_json(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "feedback",
                "route_test",
                "--outcome",
                "wrong_route",
                "--route-kind",
                "recall_context",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["error"]["field"], "route_kind")
        self.assertIn("continuity_domain", payload["error"]["valid_values"])
        self.assertEqual(payload["error"]["aliases"]["wrong_route"], "wrong_route_drag")

    def test_cli_agent_feedback_rejects_unknown_outcome_as_structured_json(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "feedback",
                "route_test",
                "--outcome",
                "maybe_bad",
                "--route-kind",
                "active_path",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(payload["error"]["field"], "outcome")
        self.assertIn("wrong_route_drag", payload["error"]["valid_values"])

    def test_cli_agent_recall_default_output_is_compact_human_frontstage(self) -> None:
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(self.cwd / "last-recall.json"),
        }
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            env=env,
        )
        deepen_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "deepen",
                "--request",
                "1",
                "--last-recall",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            env=env,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(deepen_proc.returncode, 0, deepen_proc.stderr)
        self.assertIn("AIppocampus agent recall: ok", proc.stdout)
        self.assertRegex(
            proc.stdout,
            r"Next: aippocampus agent deepen --request 1 --recall-selector sel_[0-9a-f]{16}\.",
        )
        self.assertIn("AIppocampus agent deepen: ok", deepen_proc.stdout)
        assert_semantic_human_output(self, proc.stdout, max_lines=8)
        self.assertNotIn('"memory_packets"', proc.stdout)
        self.assertNotIn("source_refs", proc.stdout)
        self.assertNotIn(str(self.cwd), proc.stdout)
        cache_text = Path(env[agent_continuity.LAST_RECALL_CACHE_ENV]).read_text()
        cache = json.loads(cache_text)
        cache_context = cache["context"]
        self.assertEqual(cache_context["path_scope"], "caller_supplied_cwd_only_not_persisted")
        self.assertNotIn("cwd", cache_context)
        self.assertNotIn(str(self.cwd), cache_text)
        self.assertNotIn("clean_source_dir", cache_context)
        self.assertNotIn("registry_dir", cache_context)
        self.assertNotIn("macro_state_jsonl", cache_context)
        self.assertTrue(cache["privacy_boundary"]["derived_local_source_paths_persisted"])
        self.assertFalse(cache["privacy_boundary"]["derived_local_source_paths_plaintext_persisted"])
        self.assertTrue(cache["privacy_boundary"]["local_reopen_context_token_persisted"])
        self.assertFalse(cache["privacy_boundary"]["opaque_handles_cleartext_persisted"])
        self.assertFalse(cache["privacy_boundary"]["local_reopen_token_encoding_is_encryption"])
        self.assertNotIn("aippo-nav:", cache_text)
        self.assertNotIn('"handle"', json.dumps(cache["requests"], ensure_ascii=False))
        self.assertIn("local_reopen_token", cache["requests"][0])

    def test_cli_agent_deepen_default_output_is_compact_human_frontstage(self) -> None:
        recall_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
                "--detail",
                "full",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        handle = json.loads(recall_proc.stdout)["deepen_requests"][0]["handle"]

        deepen_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "deepen",
                handle,
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
        self.assertEqual(deepen_proc.returncode, 0, deepen_proc.stderr)
        self.assertIn("AIppocampus agent deepen: ok", deepen_proc.stdout)
        self.assertIn("source windows opened:", deepen_proc.stdout)
        self.assertIn("Source:", deepen_proc.stdout)
        self.assertIn("agent-native recall opt-in path", deepen_proc.stdout)
        self.assertIn("whole opened window", deepen_proc.stdout)
        self.assertNotIn('"source_window"', deepen_proc.stdout)
        self.assertIn("<sensitive-value-redacted>", deepen_proc.stdout)
        self.assertNotIn("SECRET_TOKEN=abc123", deepen_proc.stdout)
        self.assertNotIn("SECRET_TOKEN", deepen_proc.stdout)
        self.assertNotIn("Opt-in continuity should return", deepen_proc.stdout)

    def test_cli_agent_recall_rejects_invalid_explicit_max(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--max",
                "0",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["error"]["code"], "usage_error")
        self.assertIn("max must be >= 1", payload["error"]["message"])

    def test_cli_agent_recall_public_json_writes_local_request_followup_cache(self) -> None:
        last_recall_path = self.cwd / "last-recall.json"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--last-recall-path",
                str(last_recall_path),
                "--json",
                "--public",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(last_recall_path.exists())
        cache_text = last_recall_path.read_text(encoding="utf-8")
        self.assertEqual(payload["surface"], "agent_cli_public_compact")
        self.assertNotIn("last_recall_cache_available", payload)
        self.assertNotIn("deepen_requests", payload)
        self.assertNotIn("foreground_action_card", payload)
        self.assertNotIn("memory_packets", payload)
        self.assertNotIn("macro_navigation", payload)
        self.assertNotIn("attention_router_navigation", payload)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_deepen")
        self.assertNotIn("action_boundary", payload)
        self.assertNotIn("output_boundary", payload)
        self.assertNotIn("metrics", payload)
        self.assertNotIn("audit_available", payload)
        self.assertNotIn("suggested_next_command", payload)
        self.assertCanonicalForegroundAction(payload)
        self.assertLess(len(encoded.encode("utf-8")), 4096)
        self.assertNotIn(str(last_recall_path), encoded)
        self.assertNotIn('"handle"', json.dumps(json.loads(cache_text)["requests"]))
        self.assertIn("local_reopen_token", cache_text)

    def test_cli_agent_deepen_can_use_public_stdout_cache_card(self) -> None:
        local_last_recall_path = self.cwd / "local-last-recall.json"
        public_cache_path = self.cwd / "public-cache.json"
        env = {
            **os.environ,
            agent_continuity.LAST_RECALL_CACHE_ENV: str(local_last_recall_path),
        }
        base = [sys.executable, "-m", "aippocampus_runtime.cli.facade", "agent"]
        run_kwargs = {
            "cwd": SCRIPTS,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "capture_output": True,
            "check": False,
            "env": env,
        }
        recall_proc = subprocess.run(
            [
                *base,
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
                "--public",
            ],
            **run_kwargs,
        )
        self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
        public_cache_path.write_text(recall_proc.stdout, encoding="utf-8", newline="\n")

        deepen_proc = subprocess.run(
            [
                *base,
                "deepen",
                "--request",
                "1",
                "--last-recall",
                "--last-recall-path",
                str(public_cache_path),
                "--json",
            ],
            **run_kwargs,
        )

        self.assertEqual(deepen_proc.returncode, 0, deepen_proc.stderr)
        payload = json.loads(deepen_proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["mode"], "deepen")
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("local_reopen_token", encoded)
        self.assertNotIn(str(local_last_recall_path), encoded)
        self.assertNotIn(str(public_cache_path), encoded)

    def test_cli_agent_explain_can_use_public_last_recall_request_index(self) -> None:
        last_recall_path = self.cwd / "last-recall.json"
        recall_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--last-recall-path",
                str(last_recall_path),
                "--json",
                "--public",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        explain_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "explain",
                "--request",
                "1",
                "--last-recall",
                "--last-recall-path",
                str(last_recall_path),
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
        self.assertEqual(explain_proc.returncode, 0, explain_proc.stderr)
        payload = json.loads(explain_proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["mode"], "explain")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["kind"], "aippocampus_route_explain_card")
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_deepen")
        self.assertEqual(payload["foreground_action"]["arguments"]["request_index"], 1)
        self.assertEqual(payload["claim_boundary"], "navigation_only_until_source_reopened")
        self.assertNotIn("macro_navigation_diagnostics", payload)
        self.assertNotIn("cannot_claim", encoded)
        self.assertNotIn(str(last_recall_path), encoded)
        self.assertNotIn("local_reopen_token", encoded)

    def test_cli_agent_recall_help_marks_full_json_as_local_diagnostic(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "--help",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--detail {compact,full}", proc.stdout)
        self.assertIn("--json", proc.stdout)

if __name__ == "__main__":
    unittest.main()
