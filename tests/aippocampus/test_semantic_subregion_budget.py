from __future__ import annotations

import unittest

from aippocampus_runtime.subconscious import semantic_subregion_budget as budget


class SemanticSubregionBudgetTests(unittest.TestCase):
    def test_classifies_semantic_subregion_vs_job_circuit(self) -> None:
        report = budget.build_semantic_subregion_budget_report(
            [
                {
                    "worker": "semantic_scope_labeling",
                    "model_call_count": 1,
                    "strict_schema": True,
                    "timeout_ms": 5000,
                    "foreground": True,
                },
                {
                    "worker": "theme_emergence_pipeline",
                    "model_call_count": 2,
                    "tool_loop": True,
                    "staging_writes": True,
                    "strict_schema": True,
                },
                {
                    "worker": "foreground_no_timeout",
                    "model_call_count": 1,
                    "strict_schema": True,
                    "foreground": True,
                },
            ]
        )
        rows = {row["worker"]: row for row in report["rows"]}

        self.assertEqual(rows["semantic_scope_labeling"]["layer"], "semantic_subregion")
        self.assertEqual(rows["theme_emergence_pipeline"]["layer"], "job_circuit")
        self.assertIn("multiple_model_calls", rows["theme_emergence_pipeline"]["violations"])
        self.assertIn("writes_or_scheduler_effects", rows["theme_emergence_pipeline"]["violations"])
        self.assertEqual(rows["foreground_no_timeout"]["layer"], "job_circuit")
        self.assertIn(
            "foreground_missing_fail_open_timeout",
            rows["foreground_no_timeout"]["violations"],
        )
        self.assertTrue(report["contract"]["output_is_routing_scent_until_source_reopen"])

if __name__ == "__main__":
    unittest.main()
