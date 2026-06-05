from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.warm_ambient.prewarm_planner import (  # noqa: E402
    fixture_prewarm_planner_report,
    prewarm_planner_report,
)


class PrewarmPlannerTests(unittest.TestCase):
    def test_planner_reuses_route_readiness_without_turning_routes_into_truth(self) -> None:
        local_path = "E:" + "\\private\\prewarm\\notes.md"
        report = prewarm_planner_report(
            [
                {
                    "domain_id": "issue-574-active-path-followup",
                    "title": "Active path packet follow-up",
                    "owner_surface": "warm_ambient",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 600,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "latency_saved_ms_estimate": 180,
                    "query_aliases": ["active path packet", "prewarm route"],
                    "invalidation_triggers": ["registry_fingerprint_changed"],
                    "source_refs": [
                        {
                            "thread_key": "session:current",
                            "message_id": "msg-1",
                            "line": 12,
                        }
                    ],
                    "raw_snippet": f"raw source text at {local_path} must not leak",
                },
                {
                    "domain_id": "stale-route",
                    "title": "Stale dream residue",
                    "owner_surface": "dream",
                    "freshness": "stale",
                    "created_unix": 1_000,
                    "ttl_seconds": 600,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"thread_key": "session:old", "message_id": "msg-2"}],
                },
                {
                    "domain_id": "low-value-route",
                    "title": "Low ROI route",
                    "owner_surface": "semantic_trigger",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 600,
                    "expected_value": 0.2,
                    "estimated_cost": 1,
                    "source_refs": [{"thread_key": "session:weak", "message_id": "msg-3"}],
                },
                {
                    "domain_id": "privacy-route",
                    "title": "Privacy blocked route",
                    "owner_surface": "warm_ambient",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 600,
                    "privacy_state": "blocked",
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [
                        {
                            "thread_key": local_path,
                            "message_id": "msg-4",
                        }
                    ],
                },
            ],
            active_lock_roi={
                "lock_pull_count": 1,
                "lock_reopen_attempt_count": 1,
                "source_backed_hit_count": 1,
                "expired_before_consumption_count": 1,
                "never_read_count": 1,
            },
            now_unix=1_010,
        )

        self.assertEqual(report["kind"], "aippocampus_prewarm_planner_report")
        self.assertTrue(report["no_write"])
        self.assertTrue(report["navigation_only"])
        self.assertTrue(report["contract"]["reuses_route_readiness"])
        self.assertTrue(report["contract"]["foreground_hook_mutation_allowed"] is False)
        self.assertIn("prewarm_candidate_is_source_truth", report["cannot_claim"])
        self.assertIn("full_sleep_cycle_planner_is_live", report["cannot_claim"])

        metrics = report["metrics"]
        self.assertEqual(metrics["prewarm_candidate_count"], 4)
        self.assertEqual(metrics["prewarm_ready_count"], 1)
        self.assertEqual(metrics["prewarm_suppressed_count"], 3)
        self.assertEqual(metrics["stale_prewarm_suppression_count"], 1)
        self.assertEqual(metrics["privacy_suppression_count"], 1)
        self.assertEqual(metrics["low_value_suppression_count"], 1)
        self.assertEqual(metrics["foreground_latency_saved_ms_estimate"], 180)
        self.assertEqual(metrics["model_visible_claim_from_prewarm_violation_count"], 0)
        self.assertEqual(metrics["source_reopen_after_prewarm_rate"], 1.0)
        self.assertGreater(metrics["wasted_prewarm_rate"], 0)

        ready = next(row for row in report["predicted_domains"] if row["status"] == "ready")
        self.assertEqual(ready["next_action"], "source_reopen")
        self.assertEqual(ready["readiness_class"], "source_reopen_ready")
        self.assertEqual(ready["source_refs"][0]["message_id"], "msg-1")
        self.assertEqual(ready["query_aliases"], ["active path packet", "prewarm route"])
        self.assertEqual(ready["invalidation_triggers"], ["registry_fingerprint_changed"])

        suppressed = [row for row in report["predicted_domains"] if row["status"] == "suppressed"]
        self.assertEqual(len(suppressed), 3)
        self.assertTrue(all(row["next_action"] == "stay_silent" for row in suppressed))
        self.assertTrue(all(row["navigation_only"] for row in suppressed))

        route_readiness = report["route_readiness"]
        self.assertEqual(route_readiness["metrics"]["ready_count"], 1)
        self.assertEqual(route_readiness["metrics"]["suppressed_count"], 3)
        self.assertTrue(route_readiness["contract"]["source_reopen_required_before_claim"])

        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw source text", encoded)
        self.assertNotIn("prewarm\\notes", encoded)
        self.assertNotIn("E:\\", encoded)
        self.assertNotIn("answer text", encoded)

    def test_fixture_is_public_safe_and_has_negative_controls(self) -> None:
        report = fixture_prewarm_planner_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_prewarm_planner_report")
        self.assertGreater(report["metrics"]["prewarm_ready_count"], 0)
        self.assertGreater(report["metrics"]["prewarm_suppressed_count"], 0)
        self.assertIn("roi_gated_prewarm_planner_fixture_exists", report["can_claim"])
        self.assertFalse(report["privacy_boundary"]["raw_source_text_serialized"])
        self.assertFalse(report["privacy_boundary"]["local_paths_serialized"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("private\\thread", encoded)


if __name__ == "__main__":
    unittest.main()
