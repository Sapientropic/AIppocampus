from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.warm_ambient import scout_profiles  # noqa: E402
from aippocampus_runtime.warm_ambient.activation_policy import (  # noqa: E402
    activation_policy_report,
    fixture_magic_activation_policy_report,
)


class MagicActivationPolicyTests(unittest.TestCase):
    def test_over_narrow_deterministic_path_reserves_bounded_exploratory_wake(self) -> None:
        report = activation_policy_report(
            signals={
                "high_uncertainty": True,
                "multilingual_potential": True,
                "cross_thread_potential": True,
                "source_gap_pressure": True,
                "deterministic_only_false_skip_count": 2,
                "manual_search_rescue_count": 1,
                "raw_prompt": "SECRET_TOKEN=abc123 should never serialize",
            },
            route_candidates=[
                {
                    "route_id": "multilingual-cross-thread-route",
                    "surface_kind": "warm_ambient_candidate",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 600,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "source_refs": [{"thread_key": "session:old", "message_id": "msg-1"}],
                    "raw_snippet": "raw private source text must not leak",
                }
            ],
            spend_report={"kind": "aippocampus_spend_doctor", "warning_codes": []},
            now_unix=1_010,
        )

        self.assertEqual(report["activation_class"], "exploratory_wake")
        self.assertIn("multilingual_or_cross_thread_potential", report["reason_codes"])
        self.assertIn("source_gap_pressure", report["reason_codes"])
        self.assertIn("deterministic_only_false_skip", report["reason_codes"])
        self.assertEqual(report["scheduler"]["tier"], "tier2_background")
        self.assertGreater(report["scheduler"]["selected_lane_count"], 0)
        self.assertLess(
            report["scheduler"]["selected_lane_count"],
            report["scheduler"]["full_lane_count"],
        )
        self.assertLess(report["metrics"]["exploratory_wake_budget_share"], 1.0)
        self.assertEqual(report["metrics"]["deterministic_only_false_skip_count"], 2)
        self.assertEqual(report["metrics"]["manual_search_rescue_count"], 1)
        self.assertTrue(report["contract"]["reuses_route_readiness"])
        self.assertTrue(report["contract"]["source_reopen_required_before_claim"])
        self.assertEqual(report["contract"]["scout_output_authority"], "navigation_only")
        self.assertIn("scout_output_is_source_truth", report["cannot_claim"])

    def test_over_wide_activation_suppresses_privacy_and_low_yield_wakeups(self) -> None:
        report = activation_policy_report(
            signals={
                "privacy_blocked": True,
                "low_value_model_wake_count": 2,
                "raw_prompt": "token=super-secret-value should never serialize",
            },
            route_candidates=[
                {
                    "route_id": "privacy-route",
                    "surface_kind": "warm_ambient_candidate",
                    "freshness": "current",
                    "created_unix": 1_000,
                    "ttl_seconds": 600,
                    "expected_value": 5,
                    "estimated_cost": 1,
                    "privacy_state": "blocked",
                    "source_refs": [{"thread_key": "E:\\private\\thread.jsonl", "message_id": "msg-2"}],
                }
            ],
            spend_report={
                "kind": "aippocampus_spend_doctor",
                "warning_codes": ["low_yield_high_spend:warm_ambient"],
            },
            now_unix=1_010,
        )

        self.assertEqual(report["activation_class"], "cold_sleep")
        self.assertEqual(report["scheduler"]["selected_lane_count"], 0)
        self.assertIn("privacy_blocked", report["reason_codes"])
        self.assertIn("low_yield_high_spend", report["reason_codes"])
        self.assertEqual(report["metrics"]["low_value_model_wake_count"], 3)
        self.assertEqual(report["metrics"]["privacy_suppression_count"], 1)
        self.assertFalse(report["contract"]["normal_foreground_full_sweep_allowed"])

    def test_full_sweep_stays_diagnostic_and_report_is_public_safe(self) -> None:
        default_report = activation_policy_report(signals={})
        diagnostic_report = activation_policy_report(
            signals={"diagnostic_requested": True},
            scheduler_tier="tier3_diagnostic",
            task_profile="coding",
        )
        fixture = fixture_magic_activation_policy_report()
        encoded = json.dumps(fixture, ensure_ascii=False, sort_keys=True)

        self.assertNotEqual(default_report["activation_class"], "full_sweep")
        self.assertEqual(diagnostic_report["activation_class"], "full_sweep")
        self.assertIn("diagnostic_only_full_sweep", diagnostic_report["reason_codes"])
        self.assertEqual(
            diagnostic_report["scheduler"]["selected_lane_count"],
            len(scout_profiles.DEFAULT_SCOUTS),
        )
        self.assertEqual(diagnostic_report["metrics"]["exploratory_wake_count"], 0)
        self.assertGreater(fixture["metrics"]["exploratory_wake_count"], 0)
        self.assertGreater(fixture["metrics"]["over_conservative_skip_count"], 0)
        self.assertFalse(fixture["privacy_boundary"]["raw_prompt_serialized"])
        self.assertFalse(fixture["privacy_boundary"]["raw_source_text_serialized"])
        self.assertFalse(fixture["privacy_boundary"]["local_paths_serialized"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("raw private source text", encoded)
        self.assertNotIn("E:\\private", encoded)


if __name__ == "__main__":
    unittest.main()
