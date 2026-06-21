from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.dream import utility_telemetry as telemetry

RAW_PRIVATE_PROMPT = "PRIVATE DREAM PROMPT TEXT SHOULD NOT LEAK"
RAW_SOURCE_EXCERPT = "SECRET SOURCE EXCERPT SHOULD NOT LEAK"
RAW_MODEL_PAYLOAD = "MODEL PAYLOAD SHOULD NOT LEAK"

def retention_policy(
    *,
    decision: str,
    coefficient_version: str = "conservative_v1",
    source_anchor: float = 0.81,
    divergence: float = 0.22,
) -> dict[str, object]:
    return {
        "kind": "aippocampus_dream_retention_policy",
        "coefficient_version": coefficient_version,
        "decision": decision,
        "raw_components": {
            "source_anchor_strength": {
                "value": source_anchor,
                "raw": {"source_excerpt": RAW_SOURCE_EXCERPT},
            },
            "structural_divergence": {
                "value": divergence,
                "raw": {"model_payload": RAW_MODEL_PAYLOAD},
            },
        },
        "aggregate": {"retention_pressure": 0.56},
    }

class DreamUtilityTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.events = Path(self.tmp.name) / "dream-utility-events.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def record(
        self,
        *,
        outcome: str,
        decision: str,
        dream_function: str = "prospective",
        source_family: str = "public_e2e50_fixture",
        utility_fixture_bucket: str | None = None,
    ) -> dict[str, object]:
        return telemetry.record_dream_utility_event(
            self.events,
            dream_hypothesis_id=f"private-local-hypothesis::{RAW_PRIVATE_PROMPT}",
            dream_function=dream_function,
            candidate_kind="route_hypothesis",
            outcome=outcome,
            retention_policy=retention_policy(decision=decision),
            source_family=source_family,
            utility_fixture_bucket=utility_fixture_bucket,
        )

    def test_records_privacy_safe_event_and_groups_public_fixture_buckets(self) -> None:
        self.record(
            outcome="ignored",
            decision="retain_for_review",
            dream_function="compensatory",
            utility_fixture_bucket="retained_unused",
        )
        self.record(
            outcome="later_supported",
            decision="drop_low_pressure",
            dream_function="prospective",
            utility_fixture_bucket="dropped_later_useful",
        )
        self.record(
            outcome="later_refuted",
            decision="retain_for_review",
            dream_function="active_imagination",
            utility_fixture_bucket="retained_later_refuted",
        )
        self.record(
            outcome="expired_unused",
            decision="retain_for_review",
            dream_function="amplification",
            utility_fixture_bucket="expired_unused",
        )

        report = telemetry.build_dream_utility_report(self.events)
        encoded = self.events.read_text(encoding="utf-8") + json.dumps(
            report, ensure_ascii=False, sort_keys=True
        )

        self.assertNotIn(RAW_PRIVATE_PROMPT, encoded)
        self.assertNotIn(RAW_SOURCE_EXCERPT, encoded)
        self.assertNotIn(RAW_MODEL_PAYLOAD, encoded)
        self.assertEqual(report["event_count"], 4)
        self.assertEqual(report["by_dream_function"]["compensatory"]["event_count"], 1)
        self.assertEqual(report["by_retention_decision"]["retain_for_review"]["event_count"], 3)
        self.assertEqual(report["by_coefficient_version"]["conservative_v1"]["event_count"], 4)
        self.assertEqual(
            report["dream_function_decision_coefficient_buckets"]["prospective"][
                "drop_low_pressure"
            ]["conservative_v1"]["later_supported_count"],
            1,
        )
        self.assertEqual(report["calibration_signals"]["retained_unused"]["event_count"], 1)
        self.assertEqual(report["calibration_signals"]["dropped_later_useful"]["event_count"], 1)
        self.assertEqual(report["calibration_signals"]["retained_later_refuted"]["event_count"], 1)
        self.assertEqual(report["calibration_signals"]["expired_unused"]["event_count"], 1)
        self.assertEqual(
            set(report["public_fixture_bucket_coverage"]["covered_buckets"]),
            {
                "retained_unused",
                "dropped_later_useful",
                "retained_later_refuted",
                "expired_unused",
            },
        )
        self.assertEqual(report["public_fixture_bucket_coverage"]["missing_buckets"], [])
        self.assertFalse(report["policy"]["automatic_coefficient_update"])
        self.assertTrue(report["policy"]["evidence_for_later_calibration_only"])
        self.assertTrue(report["source_boundary"]["raw_prompt_text_serialized"] is False)

    def test_component_values_are_bucketed_without_copying_raw_components(self) -> None:
        event = telemetry.record_dream_utility_event(
            self.events,
            dream_hypothesis_id="hypothesis-private-id",
            dream_function="amplification",
            candidate_kind="cross_thread_resonance",
            outcome="source_reopened",
            retention_policy=retention_policy(
                decision="park_for_review",
                coefficient_version="conservative_v1",
                source_anchor=0.04,
                divergence=0.92,
            ),
            source_family="public_memoryagentbench_fixture",
            utility_fixture_bucket="dropped_later_useful",
        )
        report = telemetry.build_dream_utility_report(self.events)

        self.assertEqual(event["component_value_buckets"]["source_anchor_strength"], "very_low")
        self.assertEqual(event["component_value_buckets"]["structural_divergence"], "very_high")
        self.assertNotIn("raw_components", event)
        self.assertEqual(report["by_component_value_bucket"]["source_anchor_strength"]["very_low"], 1)
        self.assertEqual(report["by_component_value_bucket"]["structural_divergence"]["very_high"], 1)
        self.assertEqual(report["calibration_signals"]["dropped_later_useful"]["event_count"], 1)

    def test_private_dogfood_events_are_reported_separately_from_public_regressions(self) -> None:
        public_event = self.record(
            outcome="expired_unused",
            decision="retain_for_review",
            source_family="public_vcs_hard_event",
            utility_fixture_bucket="expired_unused",
        )
        private_event = self.record(
            outcome="used_quietly",
            decision="retain_for_review",
            source_family="private_dogfood",
            utility_fixture_bucket="dropped_later_useful",
        )
        report = telemetry.build_dream_utility_report(self.events)

        self.assertEqual(report["by_source_family"]["public_vcs_hard_event"]["event_count"], 1)
        self.assertEqual(report["by_source_family"]["private_dogfood"]["event_count"], 1)
        self.assertEqual(report["public_event_count"], 1)
        self.assertEqual(report["private_dogfood_event_count"], 1)
        self.assertEqual(report["public_fixture_bucket_coverage"]["covered_buckets"], ["expired_unused"])
        public_event_id = str(public_event["event_id"])
        private_event_id = str(private_event["event_id"])
        self.assertTrue(public_event_id.startswith("dut_"))
        self.assertTrue(private_event_id.startswith("dut_"))

    def test_unknown_candidate_and_source_family_are_hashed_not_serialized(self) -> None:
        raw_candidate_kind = r"private\candidate-kind.md"
        raw_source_family = "private source family label"

        event = telemetry.record_dream_utility_event(
            self.events,
            dream_hypothesis_id="hypothesis-private-id",
            dream_function="prospective",
            candidate_kind=raw_candidate_kind,
            outcome="matched",
            retention_policy=retention_policy(decision="retain_for_review"),
            source_family=raw_source_family,
        )
        report = telemetry.build_dream_utility_report(self.events)
        encoded = self.events.read_text(encoding="utf-8") + json.dumps(
            report, ensure_ascii=False, sort_keys=True
        )

        self.assertTrue(event["candidate_kind"].startswith("custom:sha256:"))
        self.assertTrue(event["source_family"].startswith("custom:sha256:"))
        self.assertNotIn("candidate-kind", encoded)
        self.assertNotIn("private source family", encoded)

if __name__ == "__main__":
    unittest.main()
