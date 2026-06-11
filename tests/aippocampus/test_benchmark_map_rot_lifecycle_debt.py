from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (BENCHMARKS, SCRIPTS):
    sys.path.insert(0, str(_path))

import benchmark_map_rot_lifecycle_debt as benchmark  # noqa: E402


class MapRotLifecycleDebtBenchmarkTests(unittest.TestCase):
    def test_fixture_reports_map_health_pressure_without_red_line_leaks(self) -> None:
        report = benchmark.build_report()

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["metrics"]["case_count"], 9)
        self.assertEqual(report["metrics"]["challenged_backlog_count"], 1)
        self.assertEqual(report["metrics"]["oldest_challenged_age_days"], 45)
        self.assertEqual(report["metrics"]["review_needed_count"], 2)
        self.assertEqual(report["metrics"]["missing_middle_warning_count"], 1)
        self.assertEqual(report["metrics"]["dead_letter_count"], 1)
        self.assertEqual(report["metrics"]["eligible_current_navigation_count"], 1)
        self.assertEqual(report["metrics"]["historically_preserved_count"], 8)
        self.assertEqual(
            report["maintenance_actions"]["metrics"]["action_counts"]["needs_review"],
            2,
        )
        self.assertEqual(
            report["maintenance_actions"]["metrics"]["hot_surface_removal_count"],
            8,
        )
        self.assertEqual(report["hard_red_lines"]["stale_as_current_count"], 0)
        self.assertEqual(report["hard_red_lines"]["masked_source_resurrection_count"], 0)
        self.assertEqual(report["hard_red_lines"]["quarantined_route_emit_count"], 0)
        self.assertEqual(report["hard_red_lines"]["wrong_route_revival_count"], 0)
        self.assertIn("cold_map_self_cleaning", report["cannot_claim"])

    def test_stale_quarantined_and_missing_middle_cases_do_not_emit_routes(self) -> None:
        by_id = {case["case_id"]: case for case in benchmark.build_report()["cases"]}

        self.assertEqual(by_id["stale_current_pointer_refresh"]["next_action"], "refresh_source")
        self.assertFalse(by_id["stale_current_pointer_refresh"]["emitted_route"])
        self.assertFalse(by_id["stale_current_pointer_refresh"]["eligible_for_current_navigation"])

        self.assertEqual(by_id["quarantined_masked_route_silent"]["next_action"], "silence")
        self.assertFalse(by_id["quarantined_masked_route_silent"]["emitted_route"])

        missing = by_id["pathlet_missing_middle_warning"]
        self.assertTrue(missing["missing_middle_warning"])
        self.assertEqual(missing["next_action"], "deepen_missing_middle_before_route")

    def test_intentional_leaky_cases_increment_red_lines(self) -> None:
        leaky = benchmark.evaluate_map_rot_cases(
            [
                {
                    **benchmark.fixture_map_rot_cases()[0],
                    "case_id": "bad_stale_emit",
                    "emitted_route": True,
                },
                {
                    **benchmark.fixture_map_rot_cases()[2],
                    "case_id": "bad_quarantine_emit",
                    "emitted_route": True,
                },
            ]
        )

        self.assertFalse(leaky["ok"])
        self.assertEqual(leaky["hard_red_lines"]["stale_as_current_count"], 1)
        self.assertEqual(leaky["hard_red_lines"]["masked_source_resurrection_count"], 1)
        self.assertEqual(leaky["hard_red_lines"]["quarantined_route_emit_count"], 1)

    def test_cli_json_report_is_public_safe_and_ok(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS / "benchmark_map_rot_lifecycle_debt.py"),
                "--json",
            ],
            check=False,
            text=True,
            capture_output=True,
            cwd=REPO_ROOT,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_map_rot_lifecycle_debt")
        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn("C:\\", encoded)


if __name__ == "__main__":
    unittest.main()
