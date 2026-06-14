from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

from benchmarks.aippocampus import (
    benchmark_default_hook_recall_usefulness as benchmark,  # noqa: E402
)


class DefaultHookRecallUsefulnessBenchmarkTests(unittest.TestCase):
    def test_same_budget_three_arm_cohort_reports_required_axes(self) -> None:
        report = benchmark.build_default_hook_recall_usefulness_report()

        self.assertEqual(report["kind"], benchmark.REPORT_KIND)
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["comparison_contract"]["arms"],
            [
                "default_no_packet_baseline",
                "explicit_recall_same_budget",
                "default_hook_foreground_candidate",
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
        self.assertEqual(
            report["decision"]["tiny_agent_recall_affordance_decision"],
            "review_opt_in_affordance_only_not_default_foreground",
        )
        self.assertTrue(
            report["issue_readouts"]["github_1439"][
                "explicit_route_hook_skip_gap_covered"
            ]
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
            written["issue_readouts"]["github_1439"][
                "default_foreground_adoption_recommended"
            ]
        )


if __name__ == "__main__":
    unittest.main()
