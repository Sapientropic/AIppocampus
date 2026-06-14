from __future__ import annotations

import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import benchmark_compaction_continuity as benchmark  # noqa: E402


class CompactionContinuityBenchmarkTests(unittest.TestCase):
    def test_track_d_runner_reports_coverage_without_private_text(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)

        self.assertEqual(payload["kind"], "aippocampus_compaction_continuity_benchmark")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["config"]["live_llm"], False)
        self.assertGreaterEqual(payload["metrics"]["total_cases"], 45)
        self.assertEqual(payload["privacy_boundary"]["raw_correction_text_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_emitted"], False)
        self.assertTrue(payload["privacy_boundary"]["case_selection_filters_active"])
        self.assertEqual(
            payload["privacy_boundary"]["case_selection_filter_policy"],
            "aippocampus_runtime.safety.benchmark_sensitive_text_policy",
        )
        self.assertIn("live_codex_host_behavior", payload["cannot_claim"])
        self.assertIn("live_hook_capture", payload["cannot_claim"])
        case_types = {row["case_type"] for row in payload["cases"]}
        self.assertIn("rejected_route_after_compaction_warning", case_types)
        self.assertIn("rejected_route_visible_silent", case_types)

        required_stages = {
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "SubagentStart",
            "SubagentStop",
            "Stop",
            "PreCompact",
            "PostCompact",
        }
        self.assertLessEqual(required_stages, set(payload["coverage"]["hook_stages"]))
        self.assertLessEqual(
            {"visible", "post_compaction", "horizon_lost"},
            set(payload["coverage"]["compaction_states"]),
        )
        self.assertLessEqual(
            {"valid_adopted", "valid_ignored", "refuted", "superseded", "local_only", "uncertain"},
            set(payload["coverage"]["adjudication_statuses"]),
        )
        for row in payload["cases"]:
            self.assertIn("case_id_sha1", row)
            self.assertIn("thread_id_sha1", row)
            self.assertIn("correction_event_id_sha1", row)
            self.assertIn("source_event_id_sha1", row)
            self.assertIn("fixture_events", row)
            self.assertGreaterEqual(row["fixture_event_count"], 2)
            self.assertTrue(row["source_event_chain_valid"])
            self.assertNotIn("case_id", row)
            self.assertNotIn("thread_id", row)
            self.assertNotIn("correction_text", row)
            self.assertNotIn("source_ref", row)
            for event in row["fixture_events"]:
                self.assertNotIn("text", event)
                self.assertNotIn("source_ref", event)

    def test_track_d_runner_catches_required_failure_modes(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)
        metrics = payload["metrics"]

        self.assertEqual(metrics["event_chain_valid_rate"], 1.0)
        self.assertEqual(
            metrics["rate_estimates"]["correction_anchor_recall"]["confidence_interval"][
                "method"
            ],
            "wilson_score",
        )
        self.assertEqual(
            metrics["rate_estimates"]["anti_nag_precision"]["denominator"],
            sum(1 for row in payload["cases"] if not row["expected_emit"]),
        )
        self.assertGreater(metrics["visible_context_echo_expected_silent_count"], 0)
        self.assertEqual(metrics["visible_context_echo_noise_count"], 0)
        self.assertGreater(metrics["stale_anchor_guard_case_count"], 0)
        self.assertEqual(metrics["stale_route_retry_count"], 0)
        rejected_warning = [
            row
            for row in payload["cases"]
            if row["case_type"] == "rejected_route_after_compaction_warning"
        ][0]
        rejected_visible = [
            row
            for row in payload["cases"]
            if row["case_type"] == "rejected_route_visible_silent"
        ][0]
        self.assertTrue(rejected_warning["anchor_surface_actual"])
        self.assertFalse(rejected_visible["anchor_surface_actual"])
        self.assertGreater(metrics["unrelated_pre_tool_use_case_count"], 0)
        self.assertEqual(metrics["false_anchor_count"], 0)
        self.assertGreater(metrics["repeated_anchor_case_count"], 0)
        self.assertEqual(metrics["repeated_anchor_count"], 0)
        self.assertEqual(metrics["repeated_anchor_suppression_rate"], 1.0)
        self.assertGreater(metrics["expected_anchor_recall_count"], 0)
        self.assertEqual(metrics["lost_post_compaction_corrections"], 0)
        self.assertEqual(metrics["correction_anchor_recall"], 1.0)
        self.assertEqual(metrics["source_fidelity"], 1.0)
        self.assertEqual(metrics["anti_nag_precision"], 1.0)

    def test_complete_spec_fresh_context_is_no_harm_upper_bound_not_primary_opponent(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)
        framing = payload["benchmark_framing"]
        oracle_arm = framing["baseline_arms"]["oracle_fresh_context_spec_loop"]
        realistic_arm = framing["baseline_arms"]["realistic_fresh_context_handoff_loop"]
        no_harm = payload["metrics"]["no_harm_when_spec_complete"]

        self.assertEqual(framing["primary_endpoint"]["name"], "context_loss_or_instability")
        self.assertEqual(oracle_arm["role"], "upper_bound_no_harm_control")
        self.assertFalse(oracle_arm["primary_opponent"])
        self.assertEqual(
            oracle_arm["expected_short_task_winner"],
            "fresh_context_or_memory_silence",
        )
        self.assertEqual(realistic_arm["role"], "primary_reset_baseline")
        self.assertIn(
            "complete_spec_fresh_context_is_not_primary_opponent",
            payload["cannot_claim"],
        )
        self.assertIn(
            "memory_useful_when_current_prompt_contains_full_correct_context",
            payload["cannot_claim"],
        )
        self.assertTrue(no_harm["ok"])
        self.assertGreater(no_harm["case_count"], 0)
        self.assertEqual(no_harm["unwanted_memory_injection_count"], 0)
        self.assertIn(
            "spec_complete_short_task_no_harm",
            {row["case_type"] for row in payload["cases"]},
        )

    def test_source_fidelity_requires_bound_event_chain(self) -> None:
        case = next(
            item
            for item in benchmark.fixture_cases()
            if item.case_type == "post_compaction_anchor_recall"
        )
        broken_case = replace(case, source_event_id="missing-source-event")

        row = benchmark.evaluate_case(broken_case, include_private_text=False)

        self.assertFalse(row["source_event_bound"])
        self.assertFalse(row["source_event_chain_valid"])
        self.assertFalse(row["source_fidelity"])
        self.assertFalse(row["correct"])

    def test_case_limit_is_diagnostic_subset_not_capture_failure(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False, case_limit=4)

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["status"], "diagnostic_subset")
        self.assertFalse(payload["config"]["complete_case_set"])
        self.assertTrue(payload["diagnostic"]["is_subset"])
        self.assertFalse(payload["diagnostic"]["sufficient_quality_evidence"])

    def test_full_suite_ok_requires_every_case_correct(self) -> None:
        original_evaluate_case = benchmark.evaluate_case

        def hidden_case_failure(*args, **kwargs):
            row = original_evaluate_case(*args, **kwargs)
            if row["case_type"] == "post_compaction_anchor_recall":
                row["correct"] = False
            return row

        with patch.object(benchmark, "evaluate_case", side_effect=hidden_case_failure):
            payload = benchmark.run_benchmark(include_private_text=False)

        self.assertEqual(
            payload["metrics"]["correct_count"],
            payload["metrics"]["total_cases"] - 1,
        )
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["status"], "track_d_regression")

    def test_report_includes_hook_state_status_density_diagnostics(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)
        density = payload["coverage_density"]

        self.assertEqual(
            density["axes"],
            ["hook_stage", "compaction_state", "adjudication_status"],
        )
        self.assertEqual(
            density["possible_cell_count"],
            len(benchmark.HOOK_STAGES)
            * len(benchmark.COMPACTION_STATES)
            * len(benchmark.ADJUDICATION_STATUSES),
        )
        self.assertEqual(density["observed_cell_count"], len(density["observed_cells"]))
        self.assertLess(density["observed_cell_count"], density["possible_cell_count"])
        self.assertGreater(density["missing_cell_count"], 0)
        self.assertGreater(density["singleton_cell_count"], 0)
        self.assertEqual(density["missing_high_risk_cells"], [])
        self.assertEqual(density["high_risk_sparse_cells"], [])
        self.assertGreaterEqual(density["min_high_risk_cell_count"], 2)
        self.assertTrue(
            any(
                cell["hook_stage"] == "PostCompact"
                and cell["compaction_state"] == "horizon_lost"
                and cell["adjudication_status"] == "superseded"
                for cell in density["observed_cells"]
            )
        )

    def test_track_d_issue_1352_to_1360_target_cells_are_covered(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)
        cell_counts: dict[tuple[str, str, str], int] = {}
        for row in payload["cases"]:
            key = (
                row["hook_stage"],
                row["compaction_state"],
                row["adjudication_status"],
            )
            cell_counts[key] = cell_counts.get(key, 0) + 1

        required_cells = {
            ("UserPromptSubmit", "post_compaction", "valid_adopted"),
            ("UserPromptSubmit", "horizon_lost", "valid_adopted"),
            ("UserPromptSubmit", "post_compaction", "uncertain"),
            ("UserPromptSubmit", "post_compaction", "local_only"),
            ("PreToolUse", "visible", "valid_ignored"),
            ("PreToolUse", "visible", "valid_adopted"),
            ("PreToolUse", "post_compaction", "valid_adopted"),
            ("PreToolUse", "post_compaction", "refuted"),
            ("PreToolUse", "horizon_lost", "refuted"),
            ("PreToolUse", "horizon_lost", "superseded"),
            ("PostToolUse", "post_compaction", "valid_adopted"),
            ("PostToolUse", "horizon_lost", "valid_adopted"),
            ("PostToolUse", "post_compaction", "refuted"),
            ("PostToolUse", "horizon_lost", "refuted"),
            ("PostToolUse", "post_compaction", "uncertain"),
            ("SubagentStart", "visible", "valid_adopted"),
            ("SubagentStart", "horizon_lost", "refuted"),
            ("SubagentStart", "horizon_lost", "superseded"),
            ("PreCompact", "post_compaction", "refuted"),
            ("PreCompact", "post_compaction", "superseded"),
            ("Stop", "post_compaction", "valid_adopted"),
            ("Stop", "post_compaction", "valid_ignored"),
            ("Stop", "post_compaction", "refuted"),
            ("Stop", "post_compaction", "superseded"),
            ("PostCompact", "horizon_lost", "local_only"),
        }
        missing = sorted(cell for cell in required_cells if cell_counts.get(cell, 0) == 0)
        self.assertEqual(missing, [])

        post_tool_positive = [
            row
            for row in payload["cases"]
            if row["hook_stage"] == "PostToolUse"
            and row["compaction_state"] in {"post_compaction", "horizon_lost"}
            and row["adjudication_status"] == "valid_adopted"
        ]
        self.assertGreaterEqual(len(post_tool_positive), 2)
        for row in post_tool_positive:
            self.assertTrue(row["source_event_chain_valid"])
            self.assertTrue(row["source_fidelity"])
            self.assertIsNotNone(row["emitted_source_event_id_sha1"])

        silent_stages = {"PreCompact", "Stop"}
        for row in payload["cases"]:
            if row["hook_stage"] in silent_stages:
                self.assertFalse(row["expected_emit"])
                self.assertFalse(row["emitted_anchor"])

    def test_subagent_sequence_coverage_validates_cross_stage_links(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)
        sequence_coverage = payload["sequence_coverage"]

        self.assertEqual(sequence_coverage["sequence_count"], 2)
        self.assertEqual(sequence_coverage["invalid_sequence_count"], 0)
        self.assertEqual(sequence_coverage["adopted_rehydration_count"], 1)
        self.assertEqual(sequence_coverage["refuted_suppression_count"], 1)
        self.assertLessEqual(
            {
                "UserPromptSubmit",
                "SubagentStart",
                "SubagentStop",
                "PostCompact",
            },
            set(sequence_coverage["covered_stages"]),
        )
        for sequence in payload["sequences"]:
            self.assertTrue(sequence["event_link_chain_valid"])
            self.assertEqual(len(sequence["steps"]), 4)
            self.assertNotIn("sequence_id", sequence)
            self.assertNotIn("thread_id", sequence)
            for step in sequence["steps"]:
                self.assertNotIn("correction_text", step)
                self.assertNotIn("source_ref", step)

    def test_private_debug_text_requires_explicit_opt_in(self) -> None:
        public_payload = benchmark.run_benchmark(include_private_text=False)
        private_payload = benchmark.run_benchmark(include_private_text=True)

        self.assertFalse(any("correction_text" in row for row in public_payload["cases"]))
        self.assertTrue(any("correction_text" in row for row in private_payload["cases"]))
        self.assertEqual(
            private_payload["privacy_boundary"]["raw_correction_text_emitted"],
            True,
        )

    def test_sensitive_debug_policy_catches_database_and_private_host_material(self) -> None:
        self.assertTrue(
            benchmark.looks_sensitive(
                "Server=db.internal;Database=prod;User ID=app_user"
            )
        )
        self.assertTrue(benchmark.looks_sensitive("http://10.0.0.8:8080/debug"))
        self.assertFalse(
            benchmark.looks_sensitive(
                "ordinary source-backed correction text without credentials"
            )
        )

    def test_cli_writes_sanitized_json_report(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("FAKE_TEST_PRIVATE", encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("Bearer ", encoded)
        self.assertNotIn("thread:track-d-demo", encoded)


if __name__ == "__main__":
    unittest.main()
