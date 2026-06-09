from __future__ import annotations

import copy
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
    def assert_fixture_blocker(self, fixture: dict, expected_code: str) -> None:
        validation = benchmark.validate_fixture(fixture)

        self.assertFalse(validation["ok"], validation)
        self.assertIn(expected_code, validation["blocker_codes"])

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
        self.assertTrue(
            {
                "active_recall_or_source_reopen",
                "fts_only",
                "semantic_only",
                "summary_first",
            }.issubset(set(validation["arms"]))
        )

    def test_validator_rejects_unsupported_fixture_schema_version(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["schema_version"] = "aippocampus.field_continuity_fixture.v0"

        self.assert_fixture_blocker(fixture, "unsupported_fixture_schema_version")

    def test_validator_rejects_missing_required_top_level_arm(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["arms"].remove(benchmark.ACTIVE_ARM)

        self.assert_fixture_blocker(fixture, "missing_required_arm")

    def test_validator_rejects_missing_field_report_discussion_link(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["source"]["discussion"] = "https://github.com/Sapientropic/AIppocampus/issues/454"

        self.assert_fixture_blocker(fixture, "missing_field_report_link")

    def test_validator_rejects_duplicate_case_ids(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["cases"][1]["case_id"] = fixture["cases"][0]["case_id"]

        self.assert_fixture_blocker(fixture, "duplicate_case_id")

    def test_validator_rejects_unknown_case_scenario_family(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["cases"][0]["scenario_family"] = "undeclared_magic_moment_family"

        self.assert_fixture_blocker(fixture, "case_unknown_scenario_family")

    def test_validator_rejects_case_missing_required_arm(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        del fixture["cases"][0]["arms"][benchmark.ACTIVE_ARM]

        self.assert_fixture_blocker(fixture, "case_missing_required_arm")

    def test_validator_rejects_insufficient_public_synthetic_family_coverage(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        for case in fixture["cases"]:
            case["scenario_family"] = "fresh_projectless_familiarity"

        self.assert_fixture_blocker(fixture, "insufficient_public_synthetic_families")

    def test_validator_rejects_missing_required_negative_control(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        for case in fixture["cases"]:
            case["negative_control_tags"] = [
                tag for tag in case["negative_control_tags"] if tag != "overclaiming"
            ]

        self.assert_fixture_blocker(fixture, "missing_required_negative_control")

    def test_validator_rejects_invalid_private_seed_reporting_contract(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["private_seed_reporting_contract"]["forbidden_fields"].remove("raw_prompt")

        self.assert_fixture_blocker(fixture, "invalid_private_seed_reporting_contract")

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
        self.assertIn("/issues/982", payload["source"]["design_issue"])
        metrics = payload["metrics"]
        self.assertEqual(metrics["case_count"], 5)
        self.assertEqual(metrics["scenario_family_count"], 5)
        self.assertEqual(metrics["active_recall_or_source_reopen_boundary_failures"], 0)
        self.assertEqual(metrics["source_reopen_success_rate"], 1.0)
        self.assertEqual(metrics["progressive_route_recovery_rate"], 1.0)
        self.assertEqual(metrics["external_state_overclaim_rate"], 0.0)
        self.assertEqual(metrics["uncertainty_boundary_preserved_rate"], 1.0)
        self.assertEqual(metrics["abstains_when_evidence_insufficient_rate"], 1.0)
        self.assertEqual(metrics["exact_prompt_or_tool_failure_recovery_rate"], 1.0)
        self.assertEqual(metrics["completion_nuance_preserved_rate"], 1.0)
        self.assertEqual(metrics["wrong_family_persistence_rate"], 0.0)
        self.assertEqual(metrics["irrelevant_memory_drag_rate"], 0.0)
        self.assertEqual(metrics["report_leakage_rate"], 0.0)
        self.assertEqual(metrics["latency_budget_overrun_rate"], 0.0)
        self.assertEqual(metrics["prompt_budget_overrun_rate"], 0.0)
        self.assertEqual(
            metrics["by_arm"]["fts_only"]["source_reopen_success_rate"],
            0.0,
        )
        self.assertEqual(
            metrics["by_arm"]["summary_first"]["prompt_budget_overrun_rate"],
            1.0,
        )
        self.assertEqual(
            metrics["by_arm"]["semantic_only"]["latency_budget_overrun_rate"],
            1.0,
        )
        self.assertEqual(
            metrics["by_arm"]["summary_first"]["report_leakage_rate"],
            0.2,
        )

        gates = payload["quality_gates"]
        self.assertTrue(gates["field_report_linked"])
        self.assertTrue(gates["private_seed_contract_present"])
        self.assertTrue(gates["negative_controls_present"])
        self.assertFalse(payload["config"]["uses_live_model"])
        self.assertFalse(payload["config"]["uses_private_history"])

    def test_issue_281_readout_exposes_field_continuity_quality_proxy(self) -> None:
        payload = benchmark.run_benchmark()
        readout = payload["issue_readouts"]["github_281"]

        self.assertTrue(readout["field_continuity_quality_proxy_measured"])
        self.assertEqual(readout["claim_level"], "public_safe_fixture_quality_proxy")
        self.assertEqual(readout["fresh_projectless_familiarity_status"], "covered")
        self.assertEqual(readout["source_reopen_success_rate"], 1.0)
        self.assertEqual(readout["progressive_route_recovery_rate"], 1.0)
        self.assertEqual(readout["wrong_family_persistence_rate"], 0.0)
        self.assertEqual(readout["irrelevant_memory_drag_rate"], 0.0)
        self.assertEqual(readout["live_fresh_thread_quality"], "not_measured")
        self.assertEqual(readout["private_real_history_quality"], "not_measured")
        self.assertEqual(readout["private_seed_review"], "contract_only")
        self.assertFalse(readout["closeout_eligible"])
        self.assertIn("GitHub #281 live fresh-thread quality", payload["cannot_claim"])
        self.assertIn("GitHub #281 private real-history quality", payload["cannot_claim"])

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
