from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from tests.aippocampus.import_path_helpers import import_benchmark_module

benchmark = import_benchmark_module("benchmark_default_hook_recall_usefulness")


class DefaultHookRecallUsefulnessBenchmarkTests(unittest.TestCase):
    def test_same_budget_four_arm_cohort_reports_required_axes(self) -> None:
        report = benchmark.build_default_hook_recall_usefulness_report()

        self.assertEqual(report["kind"], benchmark.REPORT_KIND)
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["comparison_contract"]["arms"],
            [
                "default_no_packet_baseline",
                "explicit_recall_same_budget",
                "default_hook_foreground_candidate",
                "default_hook_tiny_agent_recall_affordance",
            ],
        )
        self.assertTrue(report["comparison_contract"]["same_packet_budget"])
        self.assertTrue(report["comparison_contract"]["same_source_reopen_budget"])
        self.assertGreaterEqual(report["metrics"]["case_count"], 10)

        family_counts = report["cohort_coverage"]["family_counts"]
        for family in [
            "deictic_prompt",
            "multilingual_prompt",
            "already_good_noop",
            "stale_or_conflict_control",
            "question_resurfacing",
            "theme_user_review",
            "cognitive_load_drag",
            "attention_route_specificity",
            "self_referential_continuity",
            "explicit_route_hook_skip_gap",
        ]:
            self.assertGreaterEqual(family_counts[family], 1, family)

        arm_metrics = report["arm_metrics"]
        self.assertGreater(
            arm_metrics["explicit_recall_same_budget"]["helpful_next_action_rate"],
            arm_metrics["default_no_packet_baseline"]["helpful_next_action_rate"],
        )
        self.assertGreater(
            arm_metrics["explicit_recall_same_budget"]["manual_search_reduction_vs_baseline"],
            0,
        )
        self.assertGreater(
            arm_metrics["default_hook_foreground_candidate"]["activation_rate"],
            0,
        )
        self.assertGreater(
            arm_metrics["default_hook_tiny_agent_recall_affordance"]["affordance_emission_rate"],
            0,
        )

    def test_question_and_theme_gap_controls_block_default_foreground_adoption(self) -> None:
        report = benchmark.build_default_hook_recall_usefulness_report()
        question = report["question_theme_readout"]
        decision = report["decision"]

        self.assertGreaterEqual(question["question_resurfacing_count"], 1)
        self.assertGreaterEqual(question["theme_user_review_lift_count"], 1)
        self.assertGreaterEqual(question["stale_theme_carryover_count"], 1)
        self.assertGreaterEqual(question["wrong_route_drag_count"], 1)
        self.assertGreaterEqual(question["source_truth_overclaim_blocked_count"], 1)
        self.assertEqual(question["source_truth_overclaim_count"], 0)

        self.assertEqual(
            decision["default_foreground_decision"],
            "keep_default_hook_diagnostic_only",
        )
        self.assertFalse(decision["default_foreground_adoption_recommended"])
        self.assertEqual(decision["eligible_default_foreground_surfaces"], [])
        self.assertIn(
            "default_hook_foreground_candidate",
            decision["opt_in_or_diagnostic_surfaces"],
        )
        self.assertTrue(report["issue_readouts"]["github_1439"]["closeout_eligible"])

    def test_prompt_hook_gap_from_comment_is_measured_separately(self) -> None:
        report = benchmark.build_default_hook_recall_usefulness_report()
        hook_gap = report["prompt_hook_gap_readout"]

        self.assertGreaterEqual(
            hook_gap["explicit_recall_reopenable_route_count"],
            1,
        )
        self.assertGreaterEqual(hook_gap["default_hook_skip_no_memory_count"], 1)
        self.assertGreaterEqual(
            hook_gap["explicit_route_hook_skip_gap_count"],
            1,
        )
        self.assertGreaterEqual(
            hook_gap["tiny_agent_recall_affordance_candidate_count"],
            1,
        )
        self.assertTrue(
            report["issue_readouts"]["github_1439"]["explicit_route_hook_skip_gap_covered"]
        )

    def test_tiny_hook_to_agent_affordance_has_separate_readiness_gate(self) -> None:
        report = benchmark.build_default_hook_recall_usefulness_report()
        tiny = report["tiny_agent_recall_affordance_readout"]
        replay = report["tiny_agent_recall_host_faithful_replay"]
        decision = report["decision"]
        integration = report["hook_integration_status"]
        issue = report["issue_readouts"]["github_1449"]

        self.assertTrue(issue["tiny_affordance_eval_separated"])
        self.assertTrue(issue["fixture_gate_passed"])
        self.assertTrue(issue["host_faithful_replay_measured"])
        self.assertTrue(issue["agent_recall_follow_through_measured"])
        self.assertTrue(issue["manual_search_reduction_measured"])
        self.assertTrue(issue["runtime_policy_adoption_gate_ok"])
        self.assertTrue(issue["not_foreground_context"])
        self.assertGreaterEqual(tiny["affordance_emitted_count"], 1)
        self.assertEqual(
            tiny["affordance_emitted_count"],
            tiny["agent_followed_suggested_action_count"],
        )
        self.assertGreaterEqual(tiny["recall_after_hint_success_count"], 1)
        self.assertGreater(tiny["manual_search_reduction_vs_baseline"], 0)
        self.assertEqual(tiny["wrong_route_drag_count"], 0)
        self.assertEqual(tiny["irrelevant_memory_drag_count"], 0)
        self.assertEqual(tiny["source_truth_overclaim_count"], 0)
        self.assertGreaterEqual(tiny["quiet_for_reason_count"], 1)
        self.assertEqual(
            decision["tiny_agent_recall_affordance_decision"],
            "default_tiny_agent_recall_affordance_host_replay_ready_action_only",
        )
        self.assertEqual(
            integration["ambient_tiny_agent_recall_affordance"],
            "wired_secondary_action",
        )
        self.assertTrue(integration["foreground_callable"])
        self.assertTrue(integration["action_only"])
        self.assertTrue(integration["not_source_evidence"])
        self.assertEqual(
            integration["default_foreground_evidence_adoption"],
            "diagnostic_only",
        )
        self.assertEqual(integration["blockers_still_reported"], decision["adoption_blockers"])
        self.assertEqual(
            decision["eligible_tiny_agent_recall_affordance_surfaces"],
            ["default_hook_tiny_agent_recall_affordance"],
        )
        self.assertEqual(decision["diagnostic_tiny_agent_recall_affordance_surfaces"], [])
        self.assertIn(
            "default_hook_tiny_agent_recall_affordance",
            decision["eligible_tiny_agent_recall_affordance_surfaces"],
        )
        self.assertEqual(tiny["measurement_origin"], "host_faithful_replay")
        self.assertEqual(tiny["proxy_measurement_origin"], "derived_from_arm")
        self.assertTrue(tiny["observed_agent_behavior"])
        self.assertFalse(tiny["live_host_behavior"])
        self.assertTrue(tiny["host_faithful_replay_gate_passed"])
        self.assertTrue(tiny["eligible_for_runtime_policy_adoption"])
        self.assertFalse(tiny["eligible_for_public_quality_claim"])
        self.assertEqual(
            tiny["host_followed_action_count"],
            replay["metrics"]["host_followed_action_count"],
        )
        self.assertEqual(
            tiny["agent_recall_call_count"],
            replay["metrics"]["agent_recall_call_count"],
        )
        self.assertEqual(
            replay["red_lines"],
            {
                "source_truth_from_affordance_count": 0,
                "raw_handle_or_provenance_dump_count": 0,
                "broad_manual_search_before_recall_count": 0,
                "wrong_route_drag_count": 0,
                "irrelevant_memory_drag_count": 0,
            },
        )
        self.assertEqual(
            tiny["proxy_assumed_agent_followed_suggested_action_count"],
            tiny["agent_followed_suggested_action_count"],
        )
        self.assertEqual(
            tiny["proxy_recall_success_if_agent_follows_hint_rate"],
            tiny["recall_after_hint_success_rate"],
        )

    def test_report_is_public_safe_and_not_a_live_default_claim(self) -> None:
        report = benchmark.build_default_hook_recall_usefulness_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        for forbidden in [
            "raw_prompt",
            "raw_source_text",
            "source_refs",
            "thread_id",
            "message_id",
            "provider_payload",
            "SECRET_TOKEN",
            "E:\\",
            str(REPO_ROOT),
        ]:
            self.assertNotIn(forbidden, encoded)
        self.assertIn("live_default_hook_quality", report["cannot_claim"])
        self.assertIn("default_foreground_adoption_ready", report["cannot_claim"])
        self.assertIn(
            "live_tiny_agent_recall_affordance_quality",
            report["cannot_claim"],
        )
        self.assertIn(
            "tiny_agent_recall_affordance_host_faithful_replay_passed",
            report["can_claim"],
        )
        self.assertNotIn(
            "tiny_agent_recall_affordance_ready_for_default",
            report["cannot_claim"],
        )

    def test_cli_writes_public_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "default-hook-recall-usefulness.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        REPO_ROOT
                        / "benchmarks"
                        / "aippocampus"
                        / "benchmark_default_hook_recall_usefulness.py"
                    ),
                    "--json",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            written = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["kind"], benchmark.REPORT_KIND)
        self.assertEqual(written["kind"], benchmark.REPORT_KIND)
        self.assertFalse(
            written["issue_readouts"]["github_1439"]["default_foreground_adoption_recommended"]
        )
        self.assertTrue(written["issue_readouts"]["github_1449"]["fixture_gate_passed"])

if __name__ == "__main__":
    unittest.main()
