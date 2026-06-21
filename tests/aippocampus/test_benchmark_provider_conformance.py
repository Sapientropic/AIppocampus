from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"

benchmark = import_benchmark_module("benchmark_provider_conformance")

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

    def test_sanitized_replay_separates_synthetic_kit_from_multi_client_route(self) -> None:
        payload = benchmark.build_provider_conformance_replay_report()
        metrics = payload["metrics"]

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_provider_conformance_replay_report")
        self.assertEqual(payload["status"], "sanitized_multi_client_replay_completed")
        self.assertTrue(payload["config"]["synthetic_kit_kept_separate"])
        self.assertTrue(payload["synthetic_conformance_kit"]["ok"])
        self.assertGreaterEqual(metrics["real_or_dogfood_provider_count"], 2)
        self.assertGreaterEqual(metrics["synthetic_provider_count"], 5)
        self.assertGreaterEqual(metrics["live_or_sanitized_replay_case_count"], 6)
        self.assertGreaterEqual(metrics["cross_provider_route_success_count"], 3)
        self.assertGreaterEqual(metrics["cross_provider_source_reopen_success_count"], 3)
        self.assertGreaterEqual(metrics["foreground_action_helpful_count"], 1)
        self.assertEqual(metrics["provider_identity_conflation_count"], 0)
        self.assertEqual(metrics["wrong_route_drag_count"], 0)
        self.assertIn("all_client_drop_in_support", payload["cannot_claim"])
        self.assertIn("live_provider_adapter_quality", payload["cannot_claim"])

    def test_sanitized_replay_keeps_copied_summary_and_mcp_blob_as_controls(self) -> None:
        payload = benchmark.build_provider_conformance_replay_report()
        metrics = payload["metrics"]
        cases = {
            row["case_id"]: row
            for row in payload["sanitized_provider_replay"]["cases"]
        }

        self.assertEqual(metrics["copied_summary_promoted_to_source_count"], 0)
        self.assertEqual(metrics["mcp_blob_source_truth_violation_count"], 0)
        self.assertEqual(metrics["injected_content_durable_memory_count"], 0)
        self.assertGreaterEqual(metrics["missing_source_ref_affordance_count"], 1)
        self.assertEqual(metrics["manual_search_fallback_count"], 1)
        copied = cases["copied_summary_control_requires_source_ref"]
        self.assertEqual(copied["foreground_action"]["decision"], "ask_for_source_ref_before_using_summary")
        self.assertTrue(copied["foreground_action"]["helpful"])
        self.assertTrue(copied["foreground_action"]["manual_search_fallback"])
        mcp = cases["mcp_blob_only_control_stays_direction_only"]
        self.assertEqual(
            mcp["detected_failure_codes"],
            ["provider_conformance.mcp_missing_source_ref_affordance"],
        )
        blob = [
            row for row in mcp["artifacts"] if row["artifact_id"] == "mcp-blob-only-control"
        ][0]
        self.assertEqual(blob["action_grammar"], "direction_only")
        self.assertFalse(blob["source_ref_present"])
        self.assertFalse(blob["source_reopenable"])

    def test_sanitized_replay_report_has_no_raw_provider_or_path_leaks(self) -> None:
        payload = benchmark.build_provider_conformance_replay_report()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        metrics = payload["metrics"]

        self.assertEqual(metrics["raw_provider_log_leak_count"], 0)
        self.assertEqual(metrics["local_path_or_settings_path_leak_count"], 0)
        self.assertEqual(metrics["secret_leak_count"], 0)
        self.assertFalse(payload["privacy_boundary"]["raw_provider_logs_emitted"])
        self.assertFalse(payload["privacy_boundary"]["source_ref_values_emitted"])
        self.assertNotIn("codex:session:codex-public-route-1:turn:4", serialized)
        self.assertNotIn("claude-code:session:claude-public-route-1:turn:6", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)
        self.assertNotIn("sk-live-provider-suite", serialized)

    def test_replay_cohort_cli_outputs_json_report(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS / "benchmark_provider_conformance.py"),
                "--replay-cohort",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        payload = json.loads(result.stdout)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_provider_conformance_replay_report")
        self.assertEqual(
            payload["metrics"]["live_or_sanitized_replay_case_count"],
            6,
        )

if __name__ == "__main__":
    unittest.main()
