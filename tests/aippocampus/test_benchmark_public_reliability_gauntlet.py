from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]

gauntlet = import_benchmark_module("benchmark_public_reliability_gauntlet")
from shared.benchmark_report_contract import benchmark_report_contract_lint


class PublicReliabilityGauntletTests(unittest.TestCase):
    def test_report_keeps_runtime_mis_recall_and_pollution_axes_separate(self) -> None:
        payload = gauntlet.run_public_reliability_gauntlet(
            run_segment_soak=False,
            run_question_tracking=False,
        )

        self.assertEqual(payload["kind"], "aippocampus_public_reliability_gauntlet")
        self.assertTrue(payload["ok"], payload)
        self.assertNotIn("score", payload)
        self.assertNotIn("aggregate_score", payload)

        axes = payload["axes"]
        self.assertEqual(
            set(axes),
            {"runtime_stability", "mis_recall_quality", "pollution_hygiene"},
        )
        for axis_name, axis in axes.items():
            with self.subTest(axis=axis_name):
                self.assertIn("status", axis)
                self.assertIn("claim_boundary", axis)
                self.assertIn("metrics", axis)
                self.assertIn("cannot_claim", axis)

        runtime = axes["runtime_stability"]
        self.assertIn("synthetic_scale_capacity", runtime["components"])
        self.assertIn("longmemeval_s_500_reference", runtime["components"])
        self.assertEqual(
            runtime["components"]["longmemeval_s_500_reference"]["status"],
            "referenced_published_aggregate",
        )
        self.assertEqual(
            runtime["components"]["longmemeval_s_500_reference"]["metrics"][
                "question_count"
            ],
            500,
        )

        mis_recall = axes["mis_recall_quality"]
        self.assertIn("hard_negative_suppression", mis_recall["metrics"])
        self.assertIn("longmemeval_s_500_reference", mis_recall["components"])
        self.assertIn("exact_line_miss_taxonomy", mis_recall["metrics"])

        pollution = axes["pollution_hygiene"]
        self.assertIn("knowledge_pollution", pollution["components"])
        self.assertIn("auto_hook_pollution", pollution["components"])
        families = set(pollution["metrics"]["auto_hook_pollution_family_counts"])
        self.assertTrue(
            {
                "tool_trace_user_like_text",
                "recalled_context_feedback_loop",
                "empty_message_run_id",
                "transient_task_state",
                "agent_or_host_metadata",
            }.issubset(families)
        )

    def test_default_report_is_sanitized_and_names_cannot_claim_boundaries(self) -> None:
        payload = gauntlet.run_public_reliability_gauntlet(
            run_segment_soak=False,
            run_question_tracking=False,
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(payload["privacy_boundary"]["raw_private_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_longmemeval_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertNotIn(str(REPO_ROOT), rendered)
        self.assertNotIn("IGNORE_PREVIOUS_INSTRUCTIONS", rendered)
        self.assertNotIn("SYSTEM BOOT", rendered)
        self.assertNotIn("longmemeval_s_cleaned.json", rendered)

        cannot_claim = set(payload["cannot_claim"])
        self.assertIn("longmemeval_qa_score", cannot_claim)
        self.assertIn("real_gb_registry_runtime", cannot_claim)
        self.assertIn("private_history_quality", cannot_claim)
        self.assertIn("exact_line_citation_quality_solved", cannot_claim)
        self.assertIn("live_hook_write_path_quality", cannot_claim)
        self.assertIn("single_aggregate_reliability_score", cannot_claim)

    def test_default_report_has_closed_owner_no_open_followup_and_passes_contract_lint(self) -> None:
        payload = gauntlet.run_public_reliability_gauntlet(
            run_segment_soak=False,
            run_question_tracking=False,
        )

        self.assertEqual(
            payload["historical_source_issue"],
            "https://github.com/Sapientropic/AIppocampus/issues/1102",
        )
        self.assertEqual(payload["owner_issue_state"], "closed_historical")
        self.assertEqual(
            payload["historical_owner_issue_url"],
            "https://github.com/Sapientropic/AIppocampus/issues/2101",
        )
        self.assertIn("#2101 closed", payload["no_open_followup_reason"])
        self.assertEqual(
            payload["owner_path"],
            "benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py",
        )
        self.assertTrue(payload["review_next_actions"])
        self.assertTrue(payload["issue_actions"])
        for action in payload["review_next_actions"] + payload["issue_actions"]:
            self.assertEqual(action["issue_state"], "closed_historical")
            self.assertIn("#2101 closed", action["no_open_followup_reason"])

        lint = benchmark_report_contract_lint(payload)

        self.assertTrue(lint["ok"], lint)
        self.assertGreaterEqual(lint["explicit_no_open_followup_route_count"], 1)
        self.assertGreaterEqual(lint["no_action_reason_count"], 1)
        self.assertGreaterEqual(lint["owner_route_count"], 1)

if __name__ == "__main__":
    unittest.main()
