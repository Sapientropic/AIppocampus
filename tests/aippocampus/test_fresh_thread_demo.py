from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_fresh_thread_recall_demo as benchmark  # noqa: E402
from aippocampus_runtime.recall import fresh_thread_demo as demo  # noqa: E402


class FreshThreadDemoTests(unittest.TestCase):
    def test_public_fixture_covers_issue_285_flows_and_negative_controls(self) -> None:
        flows = demo.fresh_thread_demo_flows()
        by_id = {flow.flow_id: flow for flow in flows}

        self.assertTrue(
            {
                "stress_cue",
                "website_cue",
                "gift_cue",
                "fresh_coding_cue",
                "negative_broad_stress",
                "negative_irrelevant_website",
                "negative_sensitive_gift",
                "negative_project_fact_bleed",
            }.issubset(by_id)
        )
        self.assertEqual(
            {flow.kind for flow in flows},
            {"positive_demo", "negative_control"},
        )
        self.assertTrue(all(flow.public_safe for flow in flows))

    def test_demo_report_runs_three_arms_without_claiming_benchmark_proof(self) -> None:
        report = demo.run_fresh_thread_demo()

        self.assertEqual(report["kind"], "aippocampus_fresh_thread_demo_report")
        self.assertEqual(report["arms"], ["no_memory", "hook_only", "active_recall"])
        self.assertFalse(report["claim_boundary"]["benchmark_proof"])
        self.assertTrue(report["claim_boundary"]["demo_proof"])
        self.assertIn("#285", report["claim_boundary"]["issue"])
        self.assertEqual(report["metrics"]["flow_count"], 8)
        self.assertEqual(report["metrics"]["positive_flow_count"], 4)
        self.assertEqual(report["metrics"]["negative_control_count"], 4)

    def test_active_recall_arm_shows_progression_and_source_reopen(self) -> None:
        report = demo.run_fresh_thread_demo()
        flows = {flow["flow_id"]: flow for flow in report["flows"]}

        stress_turns = flows["stress_cue"]["arms"]["active_recall"]["turns"]
        self.assertEqual(stress_turns[0]["packet_support_level"], "soft_hypothesis")
        self.assertEqual(stress_turns[0]["agent_action"], "use_silently")
        self.assertEqual(stress_turns[0]["activation_state"], "scent_emitted")
        self.assertEqual(stress_turns[1]["agent_action"], "active_recall")
        self.assertEqual(stress_turns[1]["lock_handling"], "use_ready_lock")
        self.assertEqual(stress_turns[1]["activation_state"], "confirmed")

        gift_turns = flows["gift_cue"]["arms"]["active_recall"]["turns"]
        self.assertTrue(any(turn["agent_action"] == "source_reopen" for turn in gift_turns))
        self.assertTrue(any(turn["requires_source_reopen"] for turn in gift_turns))

    def test_negative_controls_are_first_class_and_do_not_call_active_recall(self) -> None:
        report = demo.run_fresh_thread_demo()
        negative_flows = [flow for flow in report["flows"] if flow["kind"] == "negative_control"]

        self.assertEqual(len(negative_flows), 4)
        for flow in negative_flows:
            with self.subTest(flow=flow["flow_id"]):
                active = flow["arms"]["active_recall"]
                self.assertTrue(active["negative_control"])
                self.assertTrue(all(not turn["should_call_active_recall"] for turn in active["turns"]))
                self.assertTrue(all(not turn["source_refs_allowed"] for turn in active["turns"]))
                self.assertIn(
                    active["expected_outcome"],
                    {
                        "stay_generic",
                        "ask_normal_scoping_question",
                        "suppress_sensitive_detail",
                        "read_current_repo_first",
                    },
                )

    def test_expected_arm_outputs_are_explicit_for_no_memory_hook_and_active_recall(self) -> None:
        report = demo.run_fresh_thread_demo()

        for flow in report["flows"]:
            with self.subTest(flow=flow["flow_id"]):
                arms = flow["arms"]
                self.assertEqual(set(arms), {"no_memory", "hook_only", "active_recall"})
                for arm, payload in arms.items():
                    self.assertEqual(payload["arm"], arm)
                    self.assertTrue(payload["expected_outcome"])
                    self.assertTrue(payload["proof_boundary"])
                    self.assertGreaterEqual(len(payload["turns"]), 1)

    def test_report_is_public_safe_and_has_no_unsupported_evidence(self) -> None:
        report = demo.run_fresh_thread_demo()
        audit = demo.validate_fresh_thread_demo_report(report)
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(audit["privacy_failure_count"], 0)
        self.assertEqual(audit["unsupported_evidence_count"], 0)
        self.assertEqual(audit["negative_control_active_recall_count"], 0)
        self.assertNotIn("raw private", serialized)
        self.assertNotIn("private source", serialized)
        self.assertNotIn("sk_test", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)

    def test_text_runner_mentions_progression_without_dumping_candidate_refs(self) -> None:
        report = demo.run_fresh_thread_demo(flow_ids=["website_cue"], arms=["active_recall"])
        text = demo.render_fresh_thread_demo_report(report)

        self.assertIn("website_cue", text)
        self.assertIn("active_recall", text)
        self.assertIn("scent", text)
        self.assertIn("source_reopen", text)
        self.assertNotIn("candidate_refs", text)

    def test_benchmark_wrapper_uses_sanitized_public_envelope(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_fresh_thread_recall_demo_benchmark")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "passed")
        self.assertTrue(payload["quality_gates"]["privacy_safe"])
        self.assertTrue(payload["quality_gates"]["no_unsupported_evidence"])
        self.assertTrue(payload["quality_gates"]["negative_controls_pass"])
        self.assertFalse(payload["config"]["uses_live_model"])
        self.assertFalse(payload["config"]["uses_private_history"])
        self.assertIn("real-history fresh-thread recall quality", payload["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
