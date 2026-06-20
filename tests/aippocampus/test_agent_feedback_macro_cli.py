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
        self.assertLess(
            proc.stdout.index('aippocampus agent recall "old cue" --json'),
            proc.stdout.index("aippocampus agent deepen --request 1 --last-recall --json"),
        )
        self.assertLess(
            proc.stdout.index("aippocampus agent deepen --request 1 --last-recall --json"),
            proc.stdout.index('aippocampus agent background "task cue" --json'),
        )
        self.assertIn("aippocampus agent feedback <route_id>", proc.stdout)

    def test_cli_agent_recall_missing_cue_returns_recovery_card(self) -> None:
        proc = self.run_agent("recall", "--json")

        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["error"]["code"], "agent_recall_cue_required")
        self.assertEqual(payload["foreground_action"]["id"], "recall_vague_cue")
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["foreground_action"]["command_template"], 'aippocampus agent recall "{cue}" --json')
        templates = [item["command_template"] for item in payload["safe_next_actions"] if item.get("command_template")]
        commands = [item["command"] for item in payload["safe_next_actions"] if item.get("command")]
        self.assertIn('aippocampus search "{exact_phrase}" --json', templates)
        self.assertIn("aippocampus onboard --provider auto --status --json", commands)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("old decision or handoff cue", encoded)
        self.assertNotIn("distinctive exact phrase", encoded)

    def test_cli_agent_feedback_default_json_is_durable_scoped_lane(self) -> None:
        registry = self.cwd / "registry"
        env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(registry)}
        empty_env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(self.cwd / "empty-registry")}
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
        missing = self.run_agent("feedback", "--json", env=empty_env)
        help_proc = self.run_agent("feedback", "--help")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["mode"], "feedback")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
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
        self.assertEqual(missing_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", missing_payload)
        self.assertNotIn(missing_payload["foreground_action"], missing_payload["safe_next_actions"])
        self.assertEqual(missing_payload["status"], "needs_route_id")
        self.assertIn("agent recall", missing_payload["foreground_action"]["command_template"])
        self.assertEqual(missing_payload["foreground_action"]["requires"], ["cue"])
        self.assertEqual(missing_payload["foreground_action"]["id"], "recall_before_feedback")
        self.assertEqual(missing_payload["safe_next_actions"][1]["requires"], ["route_id", "feedback_outcome"])
        self.assertIn("durable low-authority route calibration", help_proc.stdout)
        self.assertIn("Default durable example:", help_proc.stdout)
        self.assertIn("--feedback-jsonl <local-feedback.jsonl>", help_proc.stdout)
        self.assertIn("helped/useful", help_proc.stdout)

    def test_cli_agent_feedback_prefers_last_recall_route_choices(self) -> None:
        registry = self.cwd / "registry"
        cache = registry / "agent" / "last-recall.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_agent_last_recall",
                    "schema_version": "agent-continuity-path-v1",
                    "requests": [
                        {"request_index": 1, "route_id": "route_cached_feedback"},
                        {"request_index": 2, "route_id": "route_second_feedback"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        proc = self.run_agent(
            "feedback",
            "--json",
            env={**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(registry)},
        )

        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "needs_route_id")
        self.assertEqual(payload["last_recall_route_choice_count"], 2)
        self.assertEqual(payload["foreground_action"]["source"], "last_recall_cache")
        self.assertEqual(payload["foreground_action"]["route_id"], "route_cached_feedback")
        self.assertIn("route_cached_feedback", payload["foreground_action"]["command_template"])
        self.assertIn("{feedback_outcome}", payload["foreground_action"]["command_template"])
        self.assertEqual(payload["foreground_action"]["requires"], ["feedback_outcome"])
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(
            "source_reopen_success",
            json.dumps(payload["safe_next_actions"], ensure_ascii=False),
        )
        self.assertNotIn("old cue", json.dumps(payload, ensure_ascii=False))

    def test_cli_agent_explain_json_errors_return_foreground_recovery_cards(self) -> None:
        deepen_missing = self.run_agent("deepen", "--json")
        missing = self.run_agent("explain", "--json")
        malformed = self.run_agent("explain", "not-a-valid-handle", "--json")

        self.assertEqual(deepen_missing.returncode, 2)
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(malformed.returncode, 2)
        deepen_payload = json.loads(deepen_missing.stdout)
        missing_payload = json.loads(missing.stdout)
        malformed_payload = json.loads(malformed.stdout)
        self.assertEqual(deepen_payload["error"]["code"], "missing_recall_handle")
        self.assertNotIn("operator_detail", deepen_payload)
        self.assertNotIn("boundary_detail", deepen_payload)
        self.assertIn("operator_detail_command", deepen_payload)
        self.assertEqual(missing_payload["error"]["code"], "missing_recall_handle")
        self.assertEqual(malformed_payload["error"]["code"], "malformed_recall_handle")
        for payload, mode, error_container, has_nested_error in (
            (deepen_payload, "deepen", deepen_payload, True),
            (missing_payload, "explain", missing_payload, False),
            (malformed_payload, "explain", malformed_payload, False),
        ):
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("agent_next_action", payload)
            self.assertIsInstance(payload["foreground_action"], dict)
            self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
            self.assertEqual(payload["foreground_action"]["id"], "recall_with_cue")
            self.assertIn("command_template", payload["foreground_action"])
            self.assertNotIn("command", payload["foreground_action"])
            self.assertEqual(payload["foreground_action"]["requires"], ["cue"])
            self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
            self.assertEqual(payload["foreground_action"]["claim_boundary"], "no_claim_before_reopen")
            self.assertIsInstance(payload["foreground_action"], dict)
            self.assertNotIn("next_safe_action", payload)
            self.assertNotIn("next_safe_action_id", payload)
            if has_nested_error and error_container["error"]["code"] == "missing_recall_handle":
                self.assertNotIn("next_safe_action_id", error_container)
                self.assertNotIn("next_safe_action", error_container)
            self.assertNotIn("recovery_actions", payload)
            self.assertNotIn('agent recall "old decision or handoff cue"', encoded)
            follow_up = payload["safe_next_actions"][0]
            self.assertEqual(follow_up["id"], f"{mode}_last_recall_request")
            self.assertEqual(follow_up["requires"], ["last_recall_cache", "request_index"])
            self.assertIn(f"agent {mode} --request {{request_index}} --last-recall", follow_up["command_template"])

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
        json_proc = self.run_agent("macro", "--cwd", str(self.cwd), "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        self.assertIn("AIppocampus agent macro: missing_macro_state_path", proc.stdout)
        self.assertIn('aippocampus agent recall "{cue}" --json', proc.stdout)
        self.assertIn("aippocampus agent macro --explain-schema", proc.stdout)
        self.assertIn("aippocampus agent macro --init-template --json", proc.stdout)
        self.assertNotIn('"memory_packets"', proc.stdout)
        payload = json.loads(json_proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["fallback_available"])
        self.assertEqual(payload["producer_status"]["state_producer"], "available_as_staged_review_path")
        self.assertFalse(payload["producer_status"]["hot_path_write_allowed"])
        self.assertEqual(
            payload["producer_status"]["total_hexagram_status"],
            "not_produced_by_minimal_producer",
        )
        self.assertNotIn("agent_next_action", payload)
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertEqual(payload["detail"], "compact")
        self.assertNotIn("cannot_claim", payload)
        self.assertNotIn("diagnostics", payload)
        self.assertNotIn("metrics", payload)
        self.assertNotIn("policy_boundary", payload)
        self.assertNotIn("red_lines", payload)
        self.assertIn("operator_detail_command", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["foreground_action"]["id"], "recall_project_macro_orientation")
        self.assertIn("command_template", payload["foreground_action"])
        self.assertNotIn("command", payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["requires"], ["cue"])
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
        self.assertEqual(payload["foreground_action"]["claim_boundary"], "no_claim_before_reopen")
        self.assertNotIn("recovery_actions", payload)
        self.assertNotIn('agent recall "project macro orientation cue"', encoded)
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertEqual(
            action_ids,
            [
                "explain_macro_schema",
                "init_macro_state_template",
            ],
        )
        self.assertIn("command", payload["safe_next_actions"][0])
        self.assertIn("command", payload["safe_next_actions"][1])

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
