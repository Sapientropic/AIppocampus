from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEBT_REPORT = REPO_ROOT / "tools" / "aippocampus" / "docs" / "debt_report.py"

spec = importlib.util.spec_from_file_location("debt_report", DEBT_REPORT)
assert spec is not None and spec.loader is not None
debt_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(debt_report)


class DebtReportTests(unittest.TestCase):
    def test_headroom_summary_counts_exact_near_and_over_budget_runtime(self) -> None:
        system_weight = debt_report.build_system_weight(
            [
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/exact.py",
                    "current_count": 100,
                    "guard_budget": 100,
                    "margin": 0,
                    "over_budget": False,
                },
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/near.py",
                    "current_count": 99,
                    "guard_budget": 100,
                    "margin": 1,
                    "over_budget": False,
                },
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/over.py",
                    "current_count": 101,
                    "guard_budget": 100,
                    "margin": -1,
                    "over_budget": True,
                },
            ],
            split_boundaries={},
        )

        summary = system_weight["guard_headroom_summary"]
        self.assertEqual(summary["runtime_exact_zero_count"], 1)
        self.assertEqual(summary["runtime_near_zero_count"], 1)
        self.assertEqual(summary["runtime_over_budget_count"], 1)
        warnings = debt_report.report_warnings(
            headroom_summary=summary,
            count_drifts=[
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/exact.py",
                    "registered_current_count": 99,
                    "current_count": 100,
                    "drift": 1,
                }
            ],
            stale_allowances=[],
        )
        self.assertEqual(
            [warning["code"] for warning in warnings],
            [
                "runtime_exact_zero_headroom",
                "runtime_near_zero_headroom",
                "architecture_debt_register_count_drift",
            ],
        )

    def test_clean_headroom_does_not_emit_nonfatal_warnings(self) -> None:
        system_weight = debt_report.build_system_weight(
            [
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/healthy.py",
                    "current_count": 80,
                    "guard_budget": 120,
                    "margin": 40,
                    "over_budget": False,
                }
            ],
            split_boundaries={},
        )

        warnings = debt_report.report_warnings(
            headroom_summary=system_weight["guard_headroom_summary"],
            count_drifts=[],
            stale_allowances=[],
        )
        self.assertEqual(warnings, [])

    def test_count_drift_classifies_small_positive_and_stale_allowance(self) -> None:
        self.assertEqual(
            debt_report.drift_class(
                registered_count=100,
                current_count=103,
                guard_budget=140,
            ),
            "harmless_small_drift",
        )
        self.assertEqual(
            debt_report.drift_class(
                registered_count=100,
                current_count=130,
                guard_budget=140,
            ),
            "positive_drift",
        )
        self.assertEqual(
            debt_report.drift_class(
                registered_count=2400,
                current_count=120,
                guard_budget=2500,
            ),
            "large_stale_allowance_after_shrink",
        )

    def test_stale_allowance_rows_are_actionable(self) -> None:
        rows = [
            {
                "path": "tests/aippocampus/test_split_owner.py",
                "current_count": 32,
                "guard_budget": 4300,
                "margin": 4268,
                "over_budget": False,
            },
            {
                "path": "tests/aippocampus/test_normal_owner.py",
                "current_count": 1200,
                "guard_budget": 1500,
                "margin": 300,
                "over_budget": False,
            },
        ]

        stale = debt_report.stale_allowance_entries(rows)

        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["path"], "tests/aippocampus/test_split_owner.py")
        self.assertEqual(
            stale[0]["drift_class"],
            "large_stale_allowance_after_shrink",
        )
        self.assertEqual(
            stale[0]["recommended_action"],
            "lower_guard_budget_or_archive_row_with_dated_owner_rationale",
        )
        warnings = debt_report.report_warnings(
            headroom_summary={
                "runtime_exact_zero_count": 0,
                "runtime_near_zero_count": 0,
            },
            count_drifts=[],
            stale_allowances=stale,
        )
        self.assertIn(
            "architecture_debt_stale_allowance",
            [warning["code"] for warning in warnings],
        )


if __name__ == "__main__":
    unittest.main()
