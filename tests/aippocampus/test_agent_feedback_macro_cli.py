from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import state as macro_state  # noqa: E402


class AgentFeedbackMacroCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_agent(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                *args,
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            env=env,
        )

    def test_cli_agent_top_help_teaches_recall_deepen_feedback_loop(self) -> None:
        proc = self.run_agent("--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("First useful loop:", proc.stdout)
        self.assertIn('aippocampus agent recall "old cue" --json', proc.stdout)
        self.assertIn("aippocampus agent deepen --request 1 --last-recall --json", proc.stdout)
        self.assertIn("aippocampus agent feedback <route_id>", proc.stdout)

    def test_cli_agent_feedback_default_json_is_durable_scoped_lane(self) -> None:
        registry = self.cwd / "registry"
        env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(registry)}
        proc = self.run_agent(
            "feedback",
            "route_test",
            "--outcome",
            "wrong_route",
            "--cwd",
            str(self.cwd),
            "--json",
            env=env,
        )
        missing = self.run_agent("feedback", "--json")
        help_proc = self.run_agent("feedback", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["mode"], "feedback")
        self.assertEqual(payload["write_boundary"]["storage"], "jsonl")
        self.assertTrue(payload["write_boundary"]["wrote_event"])
        self.assertTrue(payload["write_boundary"]["will_affect_future_routes"])
        self.assertEqual(payload["feedback_lane"]["path_source"], "default_registry")
        self.assertFalse(payload["feedback_lane"]["raw_path_emitted"])
        self.assertNotIn(str(registry), proc.stdout)
        feedback_rows = [
            json.loads(line)
            for path in registry.rglob("*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(feedback_rows[0]["route_id"], "route_test")
        self.assertFalse(feedback_rows[0].get("feedback_changes_source_truth", False))
        self.assertNotIn("feedback_report", payload)
        helped = self.run_agent(
            "feedback",
            "route_test",
            "--outcome",
            "helped",
            "--cwd",
            str(self.cwd),
            "--json",
            env=env,
        )
        self.assertEqual(helped.returncode, 0, helped.stderr)
        helped_payload = json.loads(helped.stdout)
        self.assertEqual(helped_payload["receipt"]["outcome"], "source_reopen_success")
        self.assertEqual(missing.returncode, 2)
        missing_payload = json.loads(missing.stdout)
        self.assertEqual(missing_payload["status"], "needs_route_id")
        self.assertIn("agent recall", missing_payload["agent_next_action"]["command"])
        self.assertEqual(missing_payload["safe_next_actions"][0]["id"], "recall_before_feedback")
        self.assertIn("durable low-authority route calibration", help_proc.stdout)
        self.assertIn("Default durable example:", help_proc.stdout)
        self.assertIn("--feedback-jsonl <local-feedback.jsonl>", help_proc.stdout)
        self.assertIn("helped/useful", help_proc.stdout)

    def test_cli_agent_explain_json_errors_return_foreground_recovery_cards(self) -> None:
        missing = self.run_agent("explain", "--json")
        malformed = self.run_agent("explain", "not-a-valid-handle", "--json")

        self.assertEqual(missing.returncode, 2)
        self.assertEqual(malformed.returncode, 2)
        missing_payload = json.loads(missing.stdout)
        malformed_payload = json.loads(malformed.stdout)
        self.assertEqual(missing_payload["explanation"]["error"]["code"], "missing_recall_handle")
        self.assertEqual(
            malformed_payload["explanation"]["error"]["code"],
            "malformed_recall_handle",
        )
        self.assertEqual(missing_payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertIn("agent recall", missing_payload["agent_next_action"])
        self.assertIn("agent explain --request 1 --last-recall", missing_payload["follow_up_action"]["cli_command"])
        self.assertEqual(malformed_payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertIn("agent recall", malformed_payload["agent_next_action"])
        self.assertIn("agent explain --request 1 --last-recall", malformed_payload["follow_up_action"]["cli_command"])
        self.assertEqual(
            missing_payload["next_safe_action"],
            "rerun_agent_recall_then_request_index",
        )

    def test_cli_agent_macro_help_is_task_first(self) -> None:
        proc = self.run_agent("macro", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Macro-orientation navigation card:", proc.stdout)
        self.assertIn("Do not use macro as source truth", proc.stdout)
        self.assertIn('aippocampus agent recall "old cue" --json', proc.stdout)
        self.assertIn("aippocampus agent macro --explain-schema", proc.stdout)
        self.assertIn("run recall/deepen", proc.stdout)

    def test_cli_agent_macro_missing_state_explains_schema_repair(self) -> None:
        proc = self.run_agent("macro", "--cwd", str(self.cwd))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("AIppocampus agent macro: missing_macro_state_path", proc.stdout)
        self.assertIn('aippocampus agent recall "project macro orientation cue" --json', proc.stdout)
        self.assertIn("aippocampus agent macro --explain-schema", proc.stdout)
        self.assertIn("aippocampus agent macro --init-template --json", proc.stdout)
        self.assertNotIn('"memory_packets"', proc.stdout)

    def test_cli_agent_macro_schema_and_template_are_available(self) -> None:
        schema_proc = self.run_agent("macro", "--explain-schema")
        template_proc = self.run_agent("macro", "--init-template", "--json")
        template = json.loads(template_proc.stdout)

        self.assertEqual(schema_proc.returncode, 0, schema_proc.stderr)
        self.assertEqual(template_proc.returncode, 0, template_proc.stderr)
        self.assertIn("AIppocampus agent macro schema", schema_proc.stdout)
        self.assertEqual(template["kind"], "macro_orientation_state")
        self.assertTrue(template["source_refs"])

    def test_cli_agent_macro_outputs_compact_packet(self) -> None:
        macro_path = self.cwd / "macro-orientation.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=(1,),
            source_refs=({"source_id": "macro-cli-source"},),
            updated_at="2026-06-11T10:00:00Z",
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        proc = self.run_agent(
            "macro",
            "--project",
            "AIppocampus",
            "--macro-state-jsonl",
            str(macro_path),
            "--json",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["mode"], "macro")
        self.assertEqual(
            payload["memory_packets"][0]["packet_kind"],
            "macro_orientation_packet",
        )
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("macro-cli-source", encoded)


if __name__ == "__main__":
    unittest.main()
