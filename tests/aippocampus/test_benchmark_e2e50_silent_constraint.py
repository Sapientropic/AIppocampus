from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_e2e50_silent_constraint as benchmark  # noqa: E402


class E2E50SilentConstraintBenchmarkTests(unittest.TestCase):
    def test_default_fixture_scores_behavior_metrics_without_private_payloads(self) -> None:
        payload = benchmark.run_benchmark()
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["kind"], "aippocampus_e2e50_silent_constraint_case_pack")
        self.assertEqual(payload["claim_level"], "public_synthetic_case_pack_scaffold_only")
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["raw_source_refs_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["private_thread_ids_emitted"], False)

        metrics = payload["metrics"]
        self.assertGreaterEqual(metrics["total_cases"], 7)
        self.assertEqual(metrics["silent_constraint_respected_rate"], 1.0)
        self.assertEqual(metrics["known_bad_route_avoided_rate"], 1.0)
        self.assertEqual(metrics["transient_concern_extinguished_rate"], 1.0)
        self.assertEqual(metrics["current_rule_selected_rate"], 1.0)
        self.assertEqual(metrics["source_reopen_before_risky_action_rate"], 1.0)
        self.assertEqual(metrics["unprompted_overhang_count"], 0)
        self.assertEqual(metrics["stale_revival_count"], 0)
        self.assertEqual(metrics["confabulation_count"], 0)

        self.assertLessEqual(
            {
                "binding_constraint_survival",
                "behavior_backed_rejected_route",
                "transient_concern_extinction",
                "superseded_currentness",
                "same_topic_drift_trap",
                "benign_non_action_cue",
                "source_reopen_before_risky_action",
            },
            set(payload["coverage"]["case_families"]),
        )
        self.assertIn("e2e50_behavior_benchmark_quality", payload["cannot_claim"])
        self.assertIn("private_real_history_behavior_lift", payload["cannot_claim"])
        self.assertIn("representative_e2e50_sample_quality", payload["cannot_claim"])
        self.assertIn("live_host_behavior_lift", payload["cannot_claim"])
        self.assertIn("semantic_judge_quality", payload["cannot_claim"])

        for row in payload["cases"]:
            self.assertIn("case_hash", row)
            self.assertNotIn("case_id", row)
            self.assertNotIn("source_refs", row)
            self.assertNotIn("behavior_trace", row)
            self.assertNotIn("prompt", row)

        self.assertNotIn("PRIVATE_SENTINEL_TEXT", encoded)
        self.assertNotIn("thread:e2e50-synthetic", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_unreviewed_pack_stays_diagnostic_and_sanitized(self) -> None:
        case_pack = {
            "schema_version": 1,
            "kind": "aippocampus_e2e50_annotated_case_pack",
            "cases": [
                {
                    "case_id": "PRIVATE_SENTINEL_CASE_ID",
                    "case_family": "binding_constraint_survival",
                    "source_review": {
                        "source_reviewed": False,
                        "compaction_boundary_observed": True,
                        "source_ref_hashes": ["sha256:abc123"],
                    },
                    "expected_behavior": {
                        "required_codes": ["safe_route_used"],
                        "forbidden_codes": ["forbidden_route_used"],
                    },
                    "behavior_trace": [{"code": "safe_route_used"}],
                }
            ],
        }

        payload = benchmark.run_benchmark(case_pack=case_pack)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["status"], "case_pack_incomplete")
        self.assertEqual(payload["metrics"]["source_reviewed_case_count"], 0)
        self.assertIn("manually_annotated_case_pack_ready", payload["cannot_claim"])
        self.assertNotIn("PRIVATE_SENTINEL_CASE_ID", encoded)
        self.assertNotIn("forbidden_route_used", encoded)


if __name__ == "__main__":
    unittest.main()
