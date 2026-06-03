from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_field_continuity as benchmark  # noqa: E402


class FieldContinuityBenchmarkTests(unittest.TestCase):
    def test_fixture_contract_covers_field_continuity_acceptance_slice(self) -> None:
        fixture = benchmark.load_fixture()
        validation = benchmark.validate_fixture(fixture)

        self.assertTrue(validation["ok"], validation)
        self.assertGreaterEqual(validation["scenario_family_count"], 2)
        self.assertGreaterEqual(validation["public_synthetic_case_count"], 2)
        self.assertEqual(
            validation["required_negative_controls"],
            {
                "overclaiming",
                "wrong_family_persistence",
                "stale_route_dominance",
            },
        )
        self.assertIn("fresh_projectless_familiarity", validation["scenario_families"])
        self.assertIn("external_state_restraint", validation["scenario_families"])
        self.assertIn("cross_thread_exact_prompt_tool_failure", validation["scenario_families"])

    def test_private_seed_reporting_contract_is_hash_and_aggregate_only(self) -> None:
        fixture = benchmark.load_fixture()
        validation = benchmark.validate_fixture(fixture)
        contract = validation["private_seed_reporting_contract"]

        self.assertTrue(contract["hash_only"])
        self.assertTrue(contract["aggregate_only"])
        self.assertIn("seed_hash_sha256", contract["allowed_fields"])
        self.assertIn("case_family", contract["allowed_fields"])
        for forbidden in {
            "raw_prompt",
            "raw_source_text",
            "local_path",
            "rollout_id",
            "thread_id",
            "credential",
        }:
            self.assertIn(forbidden, contract["forbidden_fields"])

    def test_benchmark_reports_claim_bounded_metrics_and_quality_gates(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_field_continuity_benchmark")
        metrics = payload["metrics"]
        self.assertEqual(metrics["case_count"], 5)
        self.assertEqual(metrics["scenario_family_count"], 5)
        self.assertEqual(metrics["active_recall_or_source_reopen_boundary_failures"], 0)
        self.assertEqual(metrics["source_reopen_success_rate"], 1.0)
        self.assertEqual(metrics["progressive_route_recovery_rate"], 1.0)
        self.assertEqual(metrics["external_state_overclaim_rate"], 0.0)
        self.assertEqual(metrics["uncertainty_boundary_preserved_rate"], 1.0)
        self.assertEqual(metrics["exact_prompt_or_tool_failure_recovery_rate"], 1.0)
        self.assertEqual(metrics["completion_nuance_preserved_rate"], 1.0)
        self.assertEqual(metrics["wrong_family_persistence_rate"], 0.0)
        self.assertEqual(metrics["irrelevant_memory_drag_rate"], 0.0)

        gates = payload["quality_gates"]
        self.assertTrue(gates["field_report_linked"])
        self.assertTrue(gates["private_seed_contract_present"])
        self.assertTrue(gates["negative_controls_present"])
        self.assertFalse(payload["config"]["uses_live_model"])
        self.assertFalse(payload["config"]["uses_private_history"])

    def test_report_is_sanitized_and_does_not_overclaim(self) -> None:
        payload = benchmark.run_benchmark()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertFalse(payload["privacy_boundary"]["raw_prompt_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertIn("field reports are benchmark seeds", serialized)
        self.assertIn("foreground-hook-only sufficiency", serialized)
        self.assertNotIn("example_files={,.join(examples)}", serialized)
        self.assertNotIn("SyntaxError: f-string", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)


if __name__ == "__main__":
    unittest.main()
