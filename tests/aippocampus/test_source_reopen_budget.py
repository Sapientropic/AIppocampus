from __future__ import annotations

import json
import unittest

from aippocampus_runtime.recall import source_reopen_budget as budget


class SourceReopenBudgetTests(unittest.TestCase):
    def test_fixture_report_separates_hot_warm_cold_and_sanitizes(self) -> None:
        report = budget.build_source_reopen_budget_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["metrics"]["case_count"], 7)
        self.assertEqual(report["metrics"]["hot_path_case_count"], 3)
        self.assertEqual(report["metrics"]["warm_path_case_count"], 1)
        self.assertEqual(report["metrics"]["cold_path_case_count"], 3)
        self.assertEqual(report["metrics"]["source_reopen_required_count"], 3)
        self.assertEqual(report["metrics"]["bounded_summary_allowed_count"], 1)
        self.assertEqual(report["metrics"]["timeout_fail_open_count"], 1)
        self.assertEqual(report["red_lines"]["unnecessary_reopen_count"], 0)
        self.assertEqual(report["red_lines"]["source_backed_claim_without_reopen"], 0)
        self.assertEqual(report["privacy_boundary"]["forbidden_marker_count"], 0)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("raw_source_text", encoded)
        self.assertIn("summary_as_evidence", report["cannot_claim"])

    def test_mandatory_reopen_claim_without_reopen_counts_violation(self) -> None:
        decision = budget.classify_source_reopen_case(
            {
                "case_id": "bad_public_claim_without_reopen",
                "triggers": ["public_claim"],
                "attempted_claim": True,
                "source_reopened": False,
            }
        )

        self.assertEqual(decision["path"], "cold")
        self.assertTrue(decision["source_reopen_required"])
        self.assertEqual(decision["next_action"], "reopen_source")
        self.assertEqual(decision["claim_permission"], "no_claim_before_reopen")
        self.assertEqual(decision["source_backed_claim_without_reopen"], 1)

    def test_bounded_summary_and_timeout_paths_do_not_force_bad_claims(self) -> None:
        bounded = budget.classify_source_reopen_case(
            {
                "case_id": "bounded_summary_low_risk",
                "path": "hot",
                "output_mode": "bounded_summary_as_route",
            }
        )
        timeout = budget.classify_source_reopen_case(
            {
                "case_id": "foreground_timeout",
                "path": "hot",
                "foreground_hook": True,
                "estimated_latency_ms_proxy": 200,
                "fail_open_on_timeout": True,
            }
        )

        self.assertTrue(bounded["bounded_summary_allowed"])
        self.assertEqual(bounded["next_action"], "use_bounded_route")
        self.assertFalse(bounded["source_reopen_required"])
        self.assertEqual(bounded["unnecessary_reopen_count"], 0)

        self.assertTrue(timeout["timeout_fail_open"])
        self.assertEqual(timeout["next_action"], "fail_open_no_claim")
        self.assertEqual(timeout["source_backed_claim_without_reopen"], 0)

if __name__ == "__main__":
    unittest.main()
