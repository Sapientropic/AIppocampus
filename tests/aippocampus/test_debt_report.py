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
        )
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
