from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_agent_continuity_loop as benchmark  # noqa: E402


class AgentContinuityLoopBenchmarkTests(unittest.TestCase):
    def test_public_safe_loop_composes_router_facade_aippo_and_budgets(self) -> None:
        report = benchmark.run_agent_continuity_loop()
        rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_agent_continuity_loop_fixture")
        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))

        by_id = {case["case_id"]: case for case in report["cases"]}
        self.assertTrue(
            {
                "positive_bounded_summary_route",
                "positive_reopenable_route",
                "aippo_low_risk_workflow",
                "blocked_privacy_route",
                "stale_conflict_reopen_route",
                "anti_nag_recently_dismissed",
            }.issubset(by_id)
        )

        summary = by_id["positive_bounded_summary_route"]["stages"]
        self.assertEqual(
            summary["semantic_warm_route"]["kind"],
            "aippocampus_attention_route_token",
        )
        self.assertEqual(summary["hot_router_packet"]["output_mode"], "bounded_summary_as_route")
        self.assertEqual(summary["facade_packet"]["next_action"], "use_hint")
        self.assertEqual(summary["deepen_result"]["status"], "source_route")
        self.assertEqual(summary["source_reopen_budget"]["next_action"], "use_bounded_route")

        reopen = by_id["positive_reopenable_route"]["stages"]
        self.assertEqual(reopen["hot_router_packet"]["output_mode"], "reopenable_route")
        self.assertEqual(reopen["facade_packet"]["next_action"], "reopen_source")
        self.assertEqual(reopen["deepen_result"]["claim_boundary"], "reopen_source_before_claim")

        aippo = by_id["aippo_low_risk_workflow"]["stages"]
        self.assertEqual(aippo["aippo_packet"]["output_mode"], "working_contract")
        self.assertEqual(aippo["aippo_packet"]["next_action"], "use_hint")
        self.assertGreaterEqual(aippo["aippo_deepen"]["source_support_ledger"]["source_ref_count"], 1)

        blocked = by_id["blocked_privacy_route"]["stages"]
        self.assertEqual(blocked["hot_router_packet"]["output_mode"], "silence")
        self.assertEqual(blocked["facade_packet"]["output_mode"], "ignore_or_blocked")
        self.assertEqual(blocked["deepen_result"]["status"], "blocked")
        self.assertEqual(blocked["facade_packet"]["next_action"], "stay_silent")

        stale = by_id["stale_conflict_reopen_route"]["stages"]
        self.assertEqual(stale["hot_router_packet"]["claim_permission"], "no_claim_before_reopen")
        self.assertEqual(stale["source_reopen_budget"]["next_action"], "reopen_source")

        anti_nag = by_id["anti_nag_recently_dismissed"]["stages"]
        self.assertEqual(anti_nag["foreground_budget"]["metrics"]["anti_nag_suppressed_count"], 1)
        self.assertFalse(anti_nag["foreground_budget"]["foreground_packets"])

        metrics = report["metrics"]
        self.assertEqual(metrics["integrated_loop_case_count"], 6)
        self.assertEqual(metrics["integrated_loop_success_count"], 6)
        self.assertGreaterEqual(metrics["deepen_required_follow_through_count"], 3)
        self.assertEqual(metrics["agent_packet_budget_violation_count"], 0)
        self.assertEqual(metrics["foreground_forbidden_key_count"], 0)
        self.assertEqual(metrics["semantic_route_used_as_truth_count"], 0)
        self.assertEqual(metrics["source_backed_claim_without_reopen"], 0)
        self.assertEqual(metrics["aippo_low_risk_guidance_success_count"], 1)

        for name, value in report["red_lines"].items():
            with self.subTest(red_line=name):
                self.assertEqual(value, 0)

        foreground = json.dumps(report["foreground_packets"], ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "source_handles",
            "source_id",
            "source_refs",
            "support_ledger",
            "head_votes",
            "masks_applied",
            "PRIVATE_",
            "C:\\",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, foreground)

        self.assertFalse(report["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["local_paths_emitted"])
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", rendered)
        self.assertIn("live_host_behavior_lift", report["cannot_claim"])
        self.assertIn("private_history_quality", report["cannot_claim"])
        self.assertIn("answer_generation_quality", report["cannot_claim"])
        self.assertIn("default_foreground_adoption", report["cannot_claim"])

    def test_red_line_violation_fails_without_hiding_behind_success_counts(self) -> None:
        cases = benchmark.fixture_agent_continuity_loop_cases()
        bad = [dict(case) for case in cases]
        bad[0] = dict(bad[0], attempted_claim=True, source_reopened=False)

        report = benchmark.evaluate_agent_continuity_loop_cases(bad)

        self.assertFalse(report["ok"])
        self.assertGreater(report["red_lines"]["source_backed_claim_without_reopen"], 0)
        self.assertGreaterEqual(report["metrics"]["integrated_loop_success_count"], 5)


if __name__ == "__main__":
    unittest.main()
