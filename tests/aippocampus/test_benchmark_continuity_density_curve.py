from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_continuity_density_curve as density_curve  # noqa: E402
from shared.benchmark_report_contract import benchmark_report_contract_lint  # noqa: E402


class ContinuityDensityCurveBenchmarkTests(unittest.TestCase):
    def test_density_curve_has_three_tiers_and_noisy_control(self) -> None:
        report = density_curve.build_density_curve_report()
        tiers = {row["tier"]: row for row in report["tiers"]}

        self.assertEqual(report["kind"], "aippocampus_continuity_density_curve_benchmark")
        self.assertIn("cold", tiers)
        self.assertIn("light", tiers)
        self.assertIn("medium", tiers)
        self.assertIn("noisy_saturated_control", tiers)
        self.assertGreater(
            report["measured_result"]["medium_vs_cold_source_reopen_lift"],
            0,
        )
        self.assertGreater(
            report["measured_result"]["medium_vs_cold_manual_search_step_reduction"],
            0,
        )
        self.assertGreater(
            tiers["noisy_saturated_control"]["wrong_route_drag_rate"],
            tiers["medium"]["wrong_route_drag_rate"],
        )
        self.assertFalse(report["observed_agent_behavior"])
        self.assertFalse(report["privacy_boundary"]["private_history_used"])

    def test_density_curve_report_satisfies_contract_linter_shape(self) -> None:
        report = density_curve.build_density_curve_report()
        lint = benchmark_report_contract_lint(report)

        self.assertTrue(lint["ok"], lint)
        self.assertFalse(lint["boundary_only_projection"])
        self.assertIn("supports", report)
        self.assertIn("private_real_history_density_curve", report["cannot_claim"])
        self.assertEqual(
            report["review_next_actions"][0]["id"],
            "review_continuity_density_synthetic_report",
        )

    def test_replay_measurement_computes_density_tiers_from_counts(self) -> None:
        report = density_curve.build_replay_backed_density_report()
        tiers = {row["tier"]: row for row in report["tiers"]}

        self.assertEqual(
            report["kind"],
            "aippocampus_continuity_density_replay_measurement",
        )
        self.assertEqual(report["measurement_origin"], "aggregate_replay_fixture")
        self.assertTrue(report["contract_gate_ok"])
        self.assertFalse(report["public_quality_gate_ok"])
        self.assertFalse(report["quality_gate_ok"])
        self.assertTrue(report["measured_result"]["density_tiers_computed_from_counts"])
        self.assertEqual(
            set(tiers),
            {"cold", "light", "medium", "heavy", "noisy_saturated_control"},
        )
        self.assertGreater(
            tiers["medium"]["source_reopen_success_rate"],
            tiers["cold"]["source_reopen_success_rate"],
        )
        self.assertLess(
            tiers["medium"]["manual_search_step_count"],
            tiers["cold"]["manual_search_step_count"],
        )
        self.assertGreater(
            tiers["noisy_saturated_control"]["wrong_route_drag_rate"],
            tiers["medium"]["wrong_route_drag_rate"],
        )
        self.assertGreater(
            tiers["noisy_saturated_control"]["context_pressure"],
            tiers["heavy"]["context_pressure"],
        )
        self.assertIn("public_quality_lift", report["cannot_claim"])

    def test_replay_measurement_sanitizes_private_identifiers(self) -> None:
        local_path = "X:" + "/synthetic-private/project/source.jsonl"
        rows = [
            {
                "case_id": "public-no-sensitive-id",
                "thread_id": "thread-secret-123",
                "source_refs": ["private://rollout/source-secret"],
                "private_source_refs": ["turn-very-private"],
                "local_path": local_path,
                "raw_text": "the private prompt should never serialize",
                "source_ref_count": 1,
                "registry_route_count": 1,
                "route_handle_count": 1,
                "source_reopen_attempted_count": 1,
                "source_reopen_success_count": 1,
                "manual_search_step_count": 3,
                "route_candidate_count": 3,
                "wrong_route_count": 0,
                "noisy_route_count": 0,
                "context_token_count": 1200,
                "context_budget_token_count": 4000,
            }
        ]
        report = density_curve.build_replay_backed_density_report(rows)
        serialized = json.dumps(report, ensure_ascii=False)

        self.assertNotIn("thread-secret-123", serialized)
        self.assertNotIn("source-secret", serialized)
        self.assertNotIn("turn-very-private", serialized)
        self.assertNotIn(local_path, serialized)
        self.assertNotIn("private prompt", serialized)
        self.assertFalse(report["privacy_boundary"]["raw_text_serialized"])
        self.assertFalse(report["privacy_boundary"]["thread_ids_serialized"])
        self.assertFalse(report["privacy_boundary"]["source_refs_serialized"])
        dropped = report["tiers"][0]["input_fields_dropped_to_preserve_public_boundary"]
        self.assertIn("thread_id", dropped)
        self.assertIn("raw_text", dropped)

    def test_heldout_behavior_report_separates_policy_candidate_from_runtime_adoption(self) -> None:
        report = density_curve.build_heldout_density_behavior_report()
        lint = benchmark_report_contract_lint(report)

        self.assertTrue(lint["ok"], lint)
        self.assertEqual(
            report["kind"],
            "aippocampus_continuity_density_heldout_behavior_report",
        )
        self.assertTrue(report["heldout_replay_behavior"])
        self.assertFalse(report["observed_agent_behavior"])
        self.assertTrue(report["public_quality_gate_ok"])
        self.assertFalse(report["runtime_policy_adoption_gate_ok"])
        self.assertGreater(report["metrics"]["correct_source_reopen_lift"], 0)
        self.assertLess(report["metrics"]["manual_search_step_delta"], 0)
        self.assertLess(report["metrics"]["wrong_route_drag_delta"], 0)
        self.assertEqual(report["metrics"]["noisy_saturation_regression_count"], 0)
        self.assertGreaterEqual(report["metrics"]["no_help_correctly_ignored_count"], 1)
        self.assertIn("runtime_policy_adoption", report["cannot_claim"])
        self.assertEqual(
            report["review_next_actions"][0]["id"],
            "review_continuity_density_heldout_report",
        )


if __name__ == "__main__":
    unittest.main()
