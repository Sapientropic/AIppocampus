from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import state as macro_state  # noqa: E402
from aippocampus_runtime.recall import agent_continuity  # noqa: E402


class AgentOptInContinuityTests(unittest.TestCase):
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

    def test_recall_returns_compact_packet_and_deepens_only_on_request(self) -> None:
        report = agent_continuity.recall(
            "agent-native recall opt-in SECRET_TOKEN=abc123",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=3,
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(report["mode"], "recall")
        self.assertTrue(report["opt_in_required"])
        self.assertEqual(report["status"], "ok")
        self.assertFalse(report["policy_boundary"]["default_hook_foreground"])
        self.assertTrue(report["policy_boundary"]["source_reopen_required_for_strong_claims"])
        self.assertEqual(report["metrics"]["foreground_forbidden_key_count"], 0)
        self.assertEqual(report["metrics"]["blind_deepen_required_count"], 0)
        self.assertGreaterEqual(report["metrics"]["top_route_selection_hint_present_count"], 1)
        self.assertGreaterEqual(report["metrics"]["topic_label_present_count"], 1)
        self.assertEqual(report["red_lines"]["foreground_source_dump_count"], 0)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("source_id", encoded)
        self.assertNotIn("msg_final", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)

        topic_packet = next(
            packet for packet in report["memory_packets"] if packet.get("route_topic")
        )
        self.assertTrue(topic_packet["route_label"])
        self.assertTrue(topic_packet["route_topic"])
        self.assertNotEqual(
            topic_packet["display_hint"],
            "A source route may matter; reopen it before using the detail.",
        )

        deepen_request = report["deepen_requests"][0]
        packet = next(
            packet
            for packet in report["memory_packets"]
            if packet["route_id"] == deepen_request["route_id"]
        )
        self.assertEqual(packet["kind"], "aippocampus_memory_packet")
        self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
        self.assertIn(packet["next_action"], {"reopen_source", "use_hint"})
        self.assertTrue(packet["deepen_route_id"].startswith("deepen:"))
        self.assertTrue(packet["route_label"])

        self.assertEqual(deepen_request["route_id"], packet["route_id"])
        self.assertTrue(deepen_request["deepen_route_id_display_only"])
        self.assertEqual(deepen_request["callable_handle"], deepen_request["handle"])
        self.assertEqual(deepen_request["callable_handle_field"], "deepen_requests[].handle")
        self.assertIn(deepen_request["handle"], deepen_request["copy_paste_command"])
        self.assertEqual(report["suggested_next_command"], deepen_request["copy_paste_command"])
        self.assertNotIn("source_refs", json.dumps(deepen_request, ensure_ascii=False))

        deepened = agent_continuity.deepen(
            deepen_request["handle"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(deepened["mode"], "deepen")
        self.assertEqual(deepened["surface"], "recall")
        self.assertEqual(deepened["result"]["evidence_level"], "source_backed")
        self.assertIn("compact MemoryPacket", json.dumps(deepened, ensure_ascii=False))

    def test_topic_labels_distinguish_routes_that_share_broad_scope_bucket(self) -> None:
        rows = [
            {
                "message_id": "msg_benchmark",
                "turn_id": "turn_benchmark",
                "source_line": 10,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 10,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": "Benchmark claim posture should use measured_result, supports, limits, and avoid over-conservative cannot_claim wording.",
            },
            {
                "message_id": "msg_issue",
                "turn_id": "turn_issue",
                "source_line": 11,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 11,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": "Issue backlog interpretation should separate roadmap seeds, active issues, milestone cleanup, and planning queue triage.",
            },
            {
                "message_id": "msg_eval",
                "turn_id": "turn_eval",
                "source_line": 12,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 12,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": "Developer assessment and second-user evaluation comments should be kept separate from benchmark proof.",
            },
        ]
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        report = agent_continuity.recall(
            "technical work route labels for benchmark, issue backlog, and developer evaluation",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=5,
        )
        packets = report["memory_packets"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        topics = {packet.get("route_topic") for packet in packets}

        self.assertIn("benchmark_claim_posture", topics)
        self.assertIn("issue_backlog_interpretation", topics)
        self.assertIn("developer_assessment", topics)
        self.assertGreaterEqual(report["metrics"]["topic_label_present_count"], 3)
        self.assertEqual(report["metrics"]["blind_deepen_required_count"], 0)
        self.assertGreaterEqual(report["metrics"]["packet_triage_distinctiveness"], 0.75)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("msg_benchmark", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_stale_and_malformed_deepen_cannot_verify(self) -> None:
        recall = agent_continuity.recall(
            "agent-native recall opt-in",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        handle = recall["deepen_requests"][0]["handle"]

        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "message_id": "msg_later",
                        "turn_id": "turn_2",
                        "source_line": 9,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 2,
                        "is_final": True,
                        "text": "Later source should stale the old agent-continuity handle.",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        stale = agent_continuity.deepen(handle, cwd=self.cwd, clean_source_dir=self.clean)
        encoded_stale = json.dumps(stale, ensure_ascii=False)
        self.assertEqual(stale["status"], "cannot_verify")
        self.assertEqual(stale["result"]["error"]["code"], "stale_recall_handle")
        self.assertNotIn("Later source", encoded_stale)

        malformed = agent_continuity.deepen(
            "not-a-navigation-handle",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(malformed["status"], "cannot_verify")
        self.assertEqual(malformed["result"]["error"]["code"], "malformed_recall_handle")
        self.assertIn("deepen_requests[].handle", malformed["result"]["error"]["message"])
        self.assertIn("source_backed_claim", malformed["cannot_claim"])

        route_id_misuse = agent_continuity.deepen(
            recall["memory_packets"][0]["deepen_route_id"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(route_id_misuse["status"], "cannot_verify")
        self.assertEqual(route_id_misuse["result"]["error"]["code"], "malformed_recall_handle")
        self.assertEqual(
            route_id_misuse["result"]["error"]["details"]["callable_handle_field"],
            "deepen_requests[].handle",
        )

    def test_explain_is_public_safe(self) -> None:
        recall = agent_continuity.recall(
            "agent-native recall opt-in",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        handle = recall["deepen_requests"][0]["handle"]

        explanation = agent_continuity.explain(handle)
        encoded = json.dumps(explanation, ensure_ascii=False, sort_keys=True)

        self.assertEqual(explanation["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(explanation["mode"], "explain")
        self.assertEqual(explanation["surface"], "recall")
        self.assertEqual(explanation["explanation"]["next_safe_action"], "reopen_source")
        self.assertIn("reopenable_route_available", explanation["explanation"]["reason_codes"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("msg_final", encoded)

    def test_aippo_activation_deepen_explain_and_feedback_stay_low_authority(self) -> None:
        activation = agent_continuity.activate_aippo(task="coding issue closeout")
        encoded_activation = json.dumps(activation, ensure_ascii=False, sort_keys=True)

        self.assertEqual(activation["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(activation["mode"], "aippo")
        self.assertEqual(activation["activation_packet"]["kind"], "aippocampus_aippo_activation_packet")
        self.assertIn("coding", activation["activation_packet"]["task_families"])
        self.assertTrue(activation["activation_packet"]["use_guidance"])
        self.assertEqual(activation["metrics"]["generic_safety_posture_only_count"], 0)
        self.assertGreaterEqual(
            activation["metrics"]["low_risk_guidance_allowed_without_reopen_count"],
            1,
        )
        self.assertTrue(activation["metrics"]["usefulness_gate_ok"])
        self.assertEqual(
            activation["activation_packet"]["claim_permission"],
            "working_contract_allowed_no_fact_claim",
        )
        self.assertNotIn("source_refs", encoded_activation)
        self.assertNotIn("candidate_provenance", encoded_activation)
        self.assertEqual(activation["red_lines"]["stale_clause_activated_as_current"], 0)

        deepened = agent_continuity.deepen(
            activation["activation_packet"]["deepen_route_id"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(deepened["surface"], "aippo")
        self.assertGreater(
            deepened["result"]["source_support_ledger"]["source_ref_count"],
            0,
        )
        self.assertFalse(deepened["result"]["candidate_provenance"]["candidate_inputs_are_truth"])

        explanation = agent_continuity.explain(activation["activation_packet"]["deepen_route_id"])
        self.assertEqual(explanation["surface"], "aippo")
        self.assertIn(
            "candidate_surfaces_are_navigation_not_truth",
            explanation["explanation"]["reason_codes"],
        )

        receipt = agent_continuity.capture_feedback(
            route_id=activation["activation_packet"]["aippo_id"],
            outcome="source_reopen_success",
            route_kind="active_path",
            reason="user accepted after source reopen",
        )
        self.assertEqual(receipt["mode"], "feedback")
        self.assertEqual(receipt["authority"], "low_authority_feedback_signal")
        self.assertEqual(receipt["red_lines"]["feedback_promoted_without_source"], 0)
        self.assertTrue(receipt["policy_boundary"]["source_reopen_required_for_claims"])

    def test_cli_agent_recall_outputs_json(self) -> None:
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
        self.assertEqual(payload["memory_packets"][0]["kind"], "aippocampus_memory_packet")
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_cli_agent_aippo_task_selects_useful_clause_family(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--task",
                "benchmark reporting issue closeout",
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
        packet = payload["activation_packet"]
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["mode"], "aippo")
        self.assertIn("benchmark_reporting", packet["task_families"])
        self.assertIn("measured results", " ".join(packet["use_guidance"]))
        self.assertTrue(payload["metrics"]["usefulness_gate_ok"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("candidate_provenance", encoded)

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
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "macro",
                "--project",
                "AIppocampus",
                "--macro-state-jsonl",
                str(macro_path),
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
        self.assertEqual(payload["mode"], "macro")
        self.assertEqual(
            payload["memory_packets"][0]["packet_kind"],
            "macro_orientation_packet",
        )
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("macro-cli-source", encoded)


if __name__ == "__main__":
    unittest.main()
