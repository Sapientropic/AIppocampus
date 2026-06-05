from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.cli import facade  # noqa: E402
from aippocampus_runtime.ops import cognitive_observatory  # noqa: E402
from aippocampus_runtime.ops.route_readiness import route_readiness_report  # noqa: E402


class RouteReadinessObservatoryTests(unittest.TestCase):
    def test_route_readiness_keeps_ready_rows_navigation_only(self) -> None:
        report = route_readiness_report(
            [
                {
                    "route_id": "ready-route",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:1", "message_id": "m1"}],
                }
            ],
            active_lock_roi={
                "lock_pull_count": 1,
                "lock_reopen_attempt_count": 1,
                "source_backed_hit_count": 1,
            },
            now_unix=1_010,
        )

        self.assertEqual(report["kind"], "aippocampus_route_readiness_report")
        self.assertEqual(report["metrics"]["ready_count"], 1)
        row = report["rows"][0]
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["navigation_only"])
        self.assertTrue(row["source_reopen_required_before_claim"])
        self.assertIn("prewarm_route_is_source_backed_evidence", report["cannot_claim"])
        self.assertEqual(
            report["metrics"]["rates"]["source_reopen_after_prewarm_rate"],
            1.0,
        )

    def test_route_readiness_suppresses_stale_privacy_low_roi_and_missing_refs(self) -> None:
        report = route_readiness_report(
            [
                {
                    "route_id": "stale",
                    "freshness": "stale",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:stale"}],
                },
                {
                    "route_id": "privacy",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "privacy_state": "blocked",
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:private"}],
                },
                {
                    "route_id": "low-roi",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 0.2,
                    "estimated_cost": 1,
                    "source_refs": [{"source_id": "clean:weak"}],
                },
                {
                    "route_id": "no-refs",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 100,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [],
                },
            ],
            now_unix=1_010,
        )

        self.assertEqual(report["metrics"]["ready_count"], 0)
        self.assertEqual(report["metrics"]["suppressed_count"], 4)
        self.assertEqual(report["metrics"]["stale_suppression_count"], 1)
        self.assertEqual(report["metrics"]["privacy_suppression_count"], 1)
        self.assertEqual(report["metrics"]["low_value_suppression_count"], 1)
        self.assertEqual(report["metrics"]["no_source_refs_suppression_count"], 1)
        for row in report["rows"]:
            self.assertEqual(row["readiness_class"], "silent")
            self.assertTrue(row["navigation_only"])

    def test_observatory_fixture_is_public_safe_and_read_only(self) -> None:
        report = cognitive_observatory.fixture_cognitive_observatory_readout()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_cognitive_observatory_readout")
        self.assertTrue(report["ok"])
        self.assertTrue(report["no_write"])
        self.assertTrue(report["contract"]["read_only_report"])
        self.assertTrue(report["contract"]["not_control_plane"])
        self.assertTrue(report["contract"]["source_reopen_required_before_claim"])
        self.assertGreater(report["metrics"]["route_ready_count"], 0)
        self.assertGreater(report["metrics"]["route_suppressed_count"], 0)
        self.assertIn("route_readiness", report["surfaces"])
        self.assertIn("activation_authority", report["surfaces"])
        self.assertIn("recall_diagnostic", report["surfaces"])
        self.assertIn("sleep_cycle", report["surfaces"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("this field must never be serialized", encoded)
        self.assertNotIn("private\\thread", encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertIn("complete_cognitive_observatory_ui_exists", report["cannot_claim"])

    def test_observatory_keeps_pruning_as_activation_eligibility_not_truth(self) -> None:
        report = cognitive_observatory.fixture_cognitive_observatory_readout()
        authority = report["activation_authority"]

        self.assertTrue(authority["contract"]["pruning_changes_activation_eligibility_only"])
        self.assertTrue(
            report["contract"]["activation_pruning_changes_activation_eligibility_only"]
        )
        self.assertEqual(
            authority["metrics"]["activation_truth_status_mutation_attempt_count"],
            0,
        )
        self.assertEqual(
            authority["metrics"]["activation_clean_source_mutation_attempt_count"],
            0,
        )

    def test_cli_facade_exposes_observatory_fixture_json(self) -> None:
        result = facade.run_command(["observatory", "--fixture", "--json"], capture_output=True)

        self.assertTrue(result.ok, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], "aippocampus_cognitive_observatory_readout")
        self.assertTrue(payload["contract"]["read_only_report"])
        self.assertTrue(payload["route_readiness"]["navigation_only"])


if __name__ == "__main__":
    unittest.main()
