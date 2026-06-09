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

import benchmark_provider_conformance as benchmark  # noqa: E402


class ProviderConformanceBenchmarkTests(unittest.TestCase):
    def assert_fixture_blocker(self, fixture: dict, expected_code: str) -> None:
        validation = benchmark.validate_fixture(fixture)

        self.assertFalse(validation["ok"], validation)
        self.assertIn(expected_code, validation["blocker_codes"])

    def test_fixture_contract_covers_cross_provider_acceptance_slice(self) -> None:
        fixture = benchmark.load_fixture()
        validation = benchmark.validate_fixture(fixture)

        self.assertTrue(validation["ok"], validation)
        self.assertGreaterEqual(validation["provider_count"], 3)
        self.assertEqual(validation["case_count"], 5)
        self.assertLessEqual(
            {
                "provider_session_identity",
                "cross_provider_correction",
                "copied_summary_boundary",
                "injected_content_pollution",
                "mcp_drop_in_boundary",
            },
            set(validation["case_families"]),
        )

    def test_validator_rejects_missing_source_issue(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["source"]["issue"] = "https://github.com/Sapientropic/AIppocampus/issues/981"

        self.assert_fixture_blocker(fixture, "missing_source_issue")

    def test_validator_rejects_missing_parent_issue(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["source"]["parent_issue"] = (
            "https://github.com/Sapientropic/AIppocampus/issues/988"
        )

        self.assert_fixture_blocker(fixture, "missing_parent_issue")

    def test_validator_rejects_insufficient_provider_surface(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["providers"] = fixture["providers"][:2]

        self.assert_fixture_blocker(fixture, "insufficient_provider_surface")

    def test_validator_rejects_missing_required_case_family(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["cases"] = [
            case
            for case in fixture["cases"]
            if case["case_family"] != "mcp_drop_in_boundary"
        ]

        self.assert_fixture_blocker(fixture, "missing_required_case_family")

    def test_validator_rejects_duplicate_case_ids(self) -> None:
        fixture = copy.deepcopy(benchmark.load_fixture())
        fixture["cases"][1]["case_id"] = fixture["cases"][0]["case_id"]

        self.assert_fixture_blocker(fixture, "duplicate_case_id")

    def test_benchmark_reports_claim_bounded_provider_conformance_metrics(self) -> None:
        payload = benchmark.run_benchmark()
        metrics = payload["metrics"]

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_provider_conformance_benchmark")
        self.assertEqual(metrics["case_count"], 5)
        self.assertGreaterEqual(metrics["provider_count"], 5)
        self.assertGreaterEqual(metrics["source_reopen_route_count"], 3)
        self.assertGreaterEqual(metrics["navigation_only_artifact_count"], 3)
        self.assertGreaterEqual(metrics["injected_content_demoted_count"], 2)
        self.assertGreaterEqual(metrics["mcp_evidence_drawer_ready_count"], 1)
        self.assertEqual(metrics["same_name_conflation_failure_count"], 0)
        self.assertEqual(metrics["unexpected_provider_conformance_failure_count"], 0)
        self.assertEqual(metrics["missing_expected_failure_count"], 0)
        self.assertEqual(
            metrics["failure_code_counts"],
            {"provider_conformance.mcp_missing_source_ref_affordance": 1},
        )
        self.assertIn("all_client_drop_in_support", payload["cannot_claim"])
        self.assertNotIn("full_provider_conformance_kit", payload["cannot_claim"])
        self.assertIn("Provider conformance kit v1", payload["claim_boundary"])
        self.assertFalse(payload["config"]["uses_live_provider"])

    def test_provider_suites_run_generic_jsonl_and_claude_code_normalizers(self) -> None:
        payload = benchmark.run_benchmark()
        metrics = payload["metrics"]
        suites = {row["provider"]: row for row in payload["provider_suites"]}

        self.assertEqual(metrics["provider_suite_count"], 2)
        self.assertEqual(metrics["provider_suite_pass_count"], 2)
        self.assertEqual(set(suites), {"generic-jsonl", "claude-code"})
        for provider, suite in suites.items():
            self.assertTrue(suite["passed"], provider)
            self.assertEqual(suite["surface_statuses"]["ingestion"], "supported")
            self.assertIn("mcp", suite["surface_statuses"])
            self.assertIn("hooks", suite["surface_statuses"])
            self.assertIn("settings_mutation", suite["surface_statuses"])
            self.assertEqual(suite["message_count"], 2)
            self.assertEqual(suite["turn_count"], 1)
            self.assertEqual(suite["source_ref_missing_count"], 0)
            self.assertEqual(suite["forbidden_text_leak_count"], 0)
            self.assertTrue(suite["thread_key_stable"])

    def test_provider_failure_examples_cover_contract_risks(self) -> None:
        payload = benchmark.run_benchmark()
        examples = {row["risk"]: row for row in payload["provider_failure_examples"]}

        self.assertLessEqual(
            {
                "orphan_assistant",
                "unstable_session_id",
                "injected_content_pollution",
                "missing_source_reopen",
                "secret_path_leakage",
            },
            set(examples),
        )
        self.assertEqual(examples["orphan_assistant"]["stable_error_code"], "orphan_assistant")
        self.assertEqual(
            examples["unstable_session_id"]["stable_error_code"],
            "session_id_changed",
        )
        self.assertTrue(all(row["public_safe"] for row in examples.values()))

    def test_same_name_provider_sessions_do_not_conflate_route_identity(self) -> None:
        payload = benchmark.run_benchmark()
        case = {
            row["case_id"]: row for row in payload["cases"]
        }["same_repo_same_entity_name_distinct_provider_sessions"]

        self.assertTrue(case["passed"], case)
        self.assertEqual(case["detected_failure_codes"], [])
        by_entity = {row["entity_key"]: row for row in case["artifacts"]}
        self.assertEqual(set(by_entity), {"atlas-runtime", "atlas-dashboard"})
        self.assertTrue(all(row["route_identity_stable"] for row in case["artifacts"]))
        self.assertTrue(all(row["source_ref_present"] for row in case["artifacts"]))

    def test_cross_provider_routes_require_reopenable_source_or_navigation_only(self) -> None:
        payload = benchmark.run_benchmark()
        by_case = {row["case_id"]: row for row in payload["cases"]}

        correction = by_case["cross_provider_correction_reopenable_route"]
        copied = by_case["provider_a_source_ref_provider_b_copied_summary"]

        self.assertEqual(correction["source_reopen_route_count"], 1)
        self.assertEqual(correction["detected_failure_codes"], [])
        copied_summary = [
            row for row in copied["artifacts"] if row["artifact_kind"] == "copied_summary"
        ][0]
        self.assertEqual(copied_summary["action_grammar"], "direction_only")
        self.assertFalse(copied_summary["source_ref_present"])
        self.assertFalse(copied_summary["durable_user_memory"])

    def test_injected_system_and_tool_content_are_demoted(self) -> None:
        payload = benchmark.run_benchmark()
        case = {
            row["case_id"]: row for row in payload["cases"]
        }["host_injected_system_tool_content_demoted"]

        self.assertTrue(case["passed"], case)
        self.assertEqual(case["navigation_only_artifact_count"], 2)
        for artifact in case["artifacts"]:
            self.assertIn(artifact["content_origin"], {"system", "tool"})
            self.assertEqual(artifact["action_grammar"], "ignore_or_blocked")
            self.assertFalse(artifact["durable_user_memory"])

    def test_mcp_blob_only_output_is_reported_as_provider_conformance_failure(self) -> None:
        payload = benchmark.run_benchmark()
        case = {
            row["case_id"]: row for row in payload["cases"]
        }["universal_mcp_blob_requires_source_ref_affordance"]

        self.assertTrue(case["passed"], case)
        self.assertEqual(
            case["detected_failure_codes"],
            ["provider_conformance.mcp_missing_source_ref_affordance"],
        )
        good = [row for row in case["artifacts"] if row["artifact_id"] == "mcp-source-ref-payload"][0]
        bad = [row for row in case["artifacts"] if row["artifact_id"] == "mcp-blob-only-payload"][0]
        self.assertTrue(good["mcp_evidence_drawer_ready"])
        self.assertFalse(bad["mcp_evidence_drawer_ready"])
        self.assertFalse(bad["source_ref_present"])

    def test_report_is_sanitized(self) -> None:
        payload = benchmark.run_benchmark()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertFalse(payload["privacy_boundary"]["raw_provider_logs_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_memory_blob_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["source_ref_values_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertNotIn("codex:session:codex-alpha-1:turn:1", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)
        self.assertNotIn("sk-live-provider-suite", serialized)
        self.assertNotIn("private-transcript", serialized)


if __name__ == "__main__":
    unittest.main()
