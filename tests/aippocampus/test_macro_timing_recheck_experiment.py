from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import timing  # noqa: E402
from aippocampus_runtime.ops import macro_timing_recheck_experiment  # noqa: E402


class MacroTimingRecheckExperimentTests(unittest.TestCase):
    def test_active_axis_is_derived_from_source_deltas_without_currentness_upgrade(self) -> None:
        report = timing.build_macro_timing_report(
            [
                {
                    "event_id": "workflow-success",
                    "line": 4,
                    "route_success_delta": 0.7,
                    "support_delta": 0.2,
                    "source_epoch": 8,
                    "recency_rank": 1,
                    "currentness_status": "current",
                },
                {
                    "event_id": "substrate-stale",
                    "line": 2,
                    "staleness_delta": 0.5,
                    "counter_evidence_delta": 0.2,
                    "source_epoch": 7,
                    "recency_rank": 2,
                    "currentness_status": "stale",
                },
            ],
            quiet_source_event_count=3,
            project_activity_level="normal",
        )

        self.assertEqual(report["active_axis"]["line"], 4)
        self.assertEqual(report["active_axis"]["axis_id"], "human_workflow_coordination")
        self.assertEqual(report["active_axis"]["currentness_status"], "unchanged")
        self.assertEqual(report["authority_level"], "navigation_only")
        self.assertFalse(report["fact_claim_allowed"])
        self.assertTrue(report["boundary"]["does_not_replace_currentness_head"])
        self.assertTrue(report["boundary"]["does_not_replace_temporal_head"])

    def test_stale_pressure_marks_axis_for_recheck_without_deciding_freshness(self) -> None:
        report = timing.build_macro_timing_report(
            [
                {
                    "event_id": "claim-counter-evidence",
                    "line": 2,
                    "counter_evidence_delta": 0.4,
                    "staleness_delta": 0.3,
                    "source_epoch": 11,
                    "recency_rank": 1,
                    "currentness_status": "stale",
                }
            ],
            quiet_source_event_count=2,
            project_activity_level="normal",
        )

        axis = report["line_time_weights"][1]
        self.assertEqual(axis["line"], 2)
        self.assertIn("axis_currentness_recheck", axis["recheck_on"])
        self.assertEqual(axis["currentness_status"], "unchanged")
        self.assertIn("counter_evidence_pressure", axis["reason_codes"])

    def test_source_epoch_cadence_uses_activity_thresholds_not_calendar_cycles(self) -> None:
        active = timing.build_macro_timing_report(
            [{"event_id": "e1", "line": 4, "route_success_delta": 0.1, "source_epoch": 1}],
            quiet_source_event_count=5,
            project_activity_level="normal",
        )
        slow = timing.build_macro_timing_report(
            [{"event_id": "e1", "line": 4, "route_success_delta": 0.1, "source_epoch": 1}],
            quiet_source_event_count=5,
            project_activity_level="slow_quiet",
        )

        self.assertTrue(active["cadence"]["recheck_due"])
        self.assertFalse(slow["cadence"]["recheck_due"])
        self.assertEqual(active["cadence"]["timing_basis"], "source_epoch")
        self.assertTrue(active["cadence"]["calendar_cycle_used"] is False)

    def test_public_experiment_report_keeps_distinct_signal_as_candidate_only(self) -> None:
        report = macro_timing_recheck_experiment.build_macro_timing_recheck_experiment_report()

        self.assertEqual(report["kind"], "macro_timing_recheck_experiment")
        self.assertTrue(report["ok"])
        self.assertEqual(report["source_issue"], "#1314")
        self.assertEqual(report["case_count"], 4)
        self.assertGreaterEqual(report["distinct_signal_count"], 2)
        self.assertEqual(report["claim_without_source_reopen_count"], 0)
        self.assertEqual(report["currentness_mutation_count"], 0)
        self.assertFalse(report["default_adoption_allowed"])
        self.assertEqual(report["promotion_status"], "fixture_candidate_not_promoted")
        for case in report["cases"]:
            self.assertIn("existing_temporal_head_covers", case["comparison"])
            self.assertIn("existing_currentness_head_covers", case["comparison"])
            self.assertEqual(case["packet"]["authority_level"], "navigation_only")
            self.assertFalse(case["packet"]["fact_claim_allowed"])


if __name__ == "__main__":
    unittest.main()
