from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
EVIDENCE_MAP = REPO_ROOT / "docs" / "evidence" / "benchmark-evidence-map.md"
BENCHMARK_PLAN = (
    REPO_ROOT / "docs" / "evidence" / "benchmarks" / "memory-decision-benchmark-plan.md"
)
sys.path.insert(0, str(BENCHMARKS))

import benchmark_continuous_memory_arms as benchmark  # noqa: E402


class ContinuousMemoryArmsBenchmarkTests(unittest.TestCase):
    def test_report_has_public_safe_memory_attribution_arms(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_continuous_memory_arms_benchmark")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "diagnostic_attribution_controls")
        self.assertEqual(
            set(payload["arms"]),
            {
                "no_memory",
                "true_aippocampus_memory",
                "sham_unrelated_memory",
                "stale_wrong_memory",
                "oracle_memory",
            },
        )
        self.assertEqual(payload["config"]["uses_live_model"], False)
        self.assertEqual(payload["config"]["uses_private_history"], False)
        self.assertIn("author_written_synthetic", payload["config"]["scenario_provenance"])
        self.assertIn("full #378 continuous-memory superiority", payload["cannot_claim"])
        self.assertIn("exact dollar accounting for every local operation", payload["cannot_claim"])
        self.assertNotIn("complete #410 cost and harm ledger", payload["cannot_claim"])

    def test_attribution_metrics_separate_presence_correctness_stale_and_oracle(self) -> None:
        payload = benchmark.run_benchmark()
        metrics = payload["metrics"]
        by_arm = metrics["by_arm"]

        self.assertEqual(metrics["case_count"], 6)
        self.assertEqual(metrics["arm_count"], 5)
        self.assertEqual(metrics["memory_presence_effect"], 0.0)
        self.assertGreater(metrics["memory_correctness_effect"], 0.0)
        self.assertGreater(metrics["stale_memory_harm"], 0.0)
        self.assertGreater(metrics["oracle_headroom"], 0.0)
        self.assertEqual(by_arm["sham_unrelated_memory"]["success_rate"], by_arm["no_memory"]["success_rate"])
        self.assertGreater(
            by_arm["true_aippocampus_memory"]["success_rate"],
            by_arm["sham_unrelated_memory"]["success_rate"],
        )
        self.assertGreater(
            by_arm["oracle_memory"]["success_rate"],
            by_arm["true_aippocampus_memory"]["success_rate"],
        )
        self.assertEqual(
            metrics["source_reopen_obedience_by_arm"]["true_aippocampus_memory"],
            1.0,
        )
        self.assertEqual(metrics["source_reopen_obedience_by_arm"]["oracle_memory"], 1.0)
        self.assertEqual(metrics["source_reopen_obedience_by_arm"]["stale_wrong_memory"], 0.0)

    def test_cases_and_rows_are_sanitized_by_default(self) -> None:
        payload = benchmark.run_benchmark()
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["privacy_boundary"]["public_safe_synthetic_fixtures"], True)
        self.assertEqual(payload["privacy_boundary"]["raw_source_snippets_in_report"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_in_report"], False)
        self.assertEqual(payload["privacy_boundary"]["case_ids_are_hashed"], True)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("Bearer ", encoded)
        self.assertNotIn("api_key", encoded.lower())
        for row in payload["rows"]:
            self.assertIn("case_id_sha1", row)
            self.assertNotIn("case_id", row)
            self.assertNotIn("correct_memory_text", row)
            self.assertNotIn("source_ref", row)
            self.assertIn("memory_packet_shape", row)

    def test_stale_wrong_arm_is_a_diagnostic_stressor_not_product_claim(self) -> None:
        payload = benchmark.run_benchmark()
        stale_rows = [row for row in payload["rows"] if row["arm"] == "stale_wrong_memory"]

        self.assertGreater(len(stale_rows), 0)
        self.assertTrue(any(row["harm_score"] >= 3 for row in stale_rows))
        self.assertTrue(all(not row["source_backed_hit"] for row in stale_rows))
        self.assertIn(
            "stale wrong arm is an adversarial diagnostic stressor, not a product mode",
            payload["interpretation_notes"],
        )

    def test_report_includes_public_safe_full_cost_ledger(self) -> None:
        payload = benchmark.run_benchmark()
        ledger = payload["cost_harm_ledger"]
        cost = ledger["cost"]
        by_arm = cost["by_arm"]
        baselines = cost["comparison_baselines"]

        self.assertEqual(ledger["schema_version"], 1)
        self.assertEqual(cost["accounting_basis"], "public_synthetic_cost_units")
        self.assertEqual(cost["background_jobs_counted"], True)
        self.assertEqual(cost["unavailable_required_components"], [])
        for component in (
            "foreground_tokens",
            "background_tokens",
            "background_api_calls",
            "wall_clock_latency_ms",
            "indexing_maintenance_ms",
            "storage_growth_bytes",
            "source_reopen_count",
            "retry_recovery_count",
            "human_correction_count",
            "human_correction_minutes",
        ):
            self.assertIn(component, cost["component_status"])

        true_cost = by_arm["true_aippocampus_memory"]
        no_memory_cost = by_arm["no_memory"]
        self.assertGreater(true_cost["background_cost_units"], 0)
        self.assertGreater(true_cost["source_reopen_count"], 0)
        self.assertGreater(true_cost["storage_growth_bytes"], 0)
        self.assertGreater(
            true_cost["amortized_cost_per_successful_slice"],
            true_cost["foreground_cost_per_successful_slice"],
        )
        self.assertEqual(no_memory_cost["background_cost_units"], 0)
        self.assertIn("fresh_context_spec_loop", baselines)
        self.assertLess(
            baselines["fresh_context_spec_loop"]["amortized_cost_per_successful_slice"],
            true_cost["amortized_cost_per_successful_slice"],
        )

    def test_harm_ledger_weights_severe_false_positives_over_event_rate(self) -> None:
        payload = benchmark.run_benchmark()
        harm = payload["cost_harm_ledger"]["harm"]
        by_arm = harm["by_arm"]

        self.assertLessEqual(harm["overall_false_positive_rate"], 0.25)
        self.assertGreater(by_arm["stale_wrong_memory"]["harm_weighted_false_positive_cost"], 0)
        self.assertGreater(
            by_arm["stale_wrong_memory"]["harm_weighted_false_positive_cost"],
            by_arm["no_memory"]["harm_weighted_false_positive_cost"]
            + by_arm["sham_unrelated_memory"]["harm_weighted_false_positive_cost"],
        )
        self.assertTrue(harm["severe_false_positive_dominates_score"])
        self.assertGreater(
            harm["max_single_false_positive_cost"],
            harm["average_false_positive_cost"],
        )
        self.assertGreater(
            by_arm["stale_wrong_memory"]["max_downstream_turns_affected"],
            by_arm["true_aippocampus_memory"]["max_downstream_turns_affected"],
        )

    def test_net_value_allows_cost_or_safety_to_beat_memory_lift(self) -> None:
        payload = benchmark.run_benchmark()
        ledger = payload["cost_harm_ledger"]
        net = ledger["net_value_under_equalized_cost"]
        by_arm = net["by_arm"]

        self.assertEqual(net["decision_rule"]["forces_memory_arm_win"], False)
        self.assertEqual(net["decision_rule"]["allows_fresh_context_cost_win"], True)
        self.assertEqual(net["decision_rule"]["excludes_oracle_from_fair_cost_winner"], True)
        self.assertEqual(
            net["lowest_amortized_cost_per_successful_slice_fair_strategy"],
            "fresh_context_spec_loop",
        )
        self.assertEqual(net["highest_net_value_fair_strategy"], "fresh_context_spec_loop")
        self.assertLess(
            by_arm["stale_wrong_memory"]["net_value_units"],
            by_arm["no_memory"]["net_value_units"],
        )
        self.assertGreater(
            by_arm["true_aippocampus_memory"]["success_value_units"],
            by_arm["no_memory"]["success_value_units"],
        )

    def test_fresh_context_spec_loop_is_realistic_baseline_not_oracle_upper_bound(self) -> None:
        payload = benchmark.run_benchmark()
        framing = payload["benchmark_framing"]
        baselines = payload["cost_harm_ledger"]["cost"]["comparison_baselines"]
        fresh_context = baselines["fresh_context_spec_loop"]
        primary = payload["preregistration"]["primary_endpoint"]

        self.assertEqual(
            framing["baseline_arms"]["fresh_context_spec_loop"]["normalized_role"],
            "realistic_fresh_context_handoff_loop",
        )
        self.assertEqual(
            framing["baseline_arms"]["oracle_fresh_context_spec_loop"]["role"],
            "upper_bound_no_harm_control",
        )
        self.assertFalse(framing["baseline_arms"]["oracle_fresh_context_spec_loop"]["primary_opponent"])
        self.assertEqual(fresh_context["framing_role"], "realistic_fresh_context_handoff_loop")
        self.assertFalse(fresh_context["complete_spec_upper_bound"])
        self.assertEqual(primary["scope"], "context_loss_or_instability")
        self.assertIn(
            "complete_spec_short_task_current_prompt_sufficient",
            primary["does_not_apply_when"],
        )
        self.assertIn(
            "memory_useful_when_current_prompt_contains_full_correct_context",
            payload["cannot_claim"],
        )

    def test_report_pre_registers_primary_endpoint_and_decision_rule(self) -> None:
        payload = benchmark.run_benchmark()
        preregistration = payload["preregistration"]
        primary = preregistration["primary_endpoint"]
        seed_strategy = preregistration["seed_repeat_strategy"]
        decision = preregistration["current_report_decision"]

        self.assertEqual(preregistration["status"], "pre_registered_design_contract")
        self.assertEqual(
            primary["name"],
            "source_grounded_task_success_under_equalized_cost",
        )
        self.assertIn("source support", primary["why_chosen"])
        self.assertIn("severe false positives", primary["why_chosen"])
        self.assertEqual(seed_strategy["same_task_seed_pairs_across_arms"], True)
        self.assertGreaterEqual(
            seed_strategy["public_quality_min_repeats_per_scenario_arm"],
            5,
        )
        self.assertGreaterEqual(
            preregistration["public_quality_minimums"]["scenario_families"],
            3,
        )
        self.assertIn("lower_bound", preregistration["confidence_rule"]["primary_rule"])
        self.assertEqual(
            preregistration["secondary_metrics_policy"],
            "exploratory_unless_named_in_primary_decision_rule",
        )
        self.assertEqual(decision["continuous_memory_advantage_claim_allowed"], False)
        self.assertEqual(decision["primary_endpoint_winner"], "fresh_context_spec_loop")
        self.assertIn("no demonstrated memory advantage", decision["decision_label"])

    def test_report_tracks_scenario_provenance_holdouts_and_negative_controls(self) -> None:
        payload = benchmark.run_benchmark()
        controls = payload["scenario_controls"]
        categories = controls["provenance_categories"]

        self.assertIn("public_log_or_vcs_derived", payload["config"]["scenario_provenance"])
        self.assertIn("holdout_blind", payload["config"]["scenario_provenance"])
        self.assertEqual(categories["external_written_synthetic"]["case_count"], 0)
        self.assertGreaterEqual(
            controls["external_or_holdout_case_share"],
            controls["public_quality_min_external_or_holdout_share"],
        )
        self.assertTrue(controls["public_quality_external_or_holdout_share_gate_passed"])
        self.assertEqual(
            controls["holdout_used_for_prompt_or_threshold_tuning_count"],
            0,
        )
        self.assertGreaterEqual(controls["negative_control_case_count"], 2)
        self.assertGreater(
            controls["negative_control_unnecessary_intervention_by_arm"][
                "stale_wrong_memory"
            ],
            0,
        )
        self.assertEqual(
            controls["negative_control_unnecessary_intervention_by_arm"][
                "true_aippocampus_memory"
            ],
            0,
        )
        self.assertEqual(
            controls["negative_control_memory_intervention_by_arm"]["no_memory"],
            0,
        )
        self.assertEqual(
            controls["negative_control_memory_intervention_by_arm"][
                "sham_unrelated_memory"
            ],
            0,
        )
        self.assertGreater(
            controls["negative_control_memory_intervention_by_arm"][
                "true_aippocampus_memory"
            ],
            0,
        )
        self.assertIn(
            "only author_written_synthetic",
            " ".join(payload["cannot_claim"]),
        )

    def test_prompt_threshold_tuning_selection_excludes_holdouts(self) -> None:
        payload = benchmark.run_benchmark(
            scenario_selection_role="prompt_threshold_tuning"
        )
        controls = payload["scenario_controls"]

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["config"]["scenario_selection_role"], "prompt_threshold_tuning")
        self.assertEqual(payload["metrics"]["case_count"], 4)
        self.assertNotIn("holdout_blind", payload["config"]["scenario_provenance"])
        self.assertEqual(controls["available_case_count"], 6)
        self.assertEqual(controls["selected_case_count"], 4)
        self.assertEqual(controls["holdout_excluded_from_selection_count"], 2)
        self.assertEqual(
            controls["holdout_used_for_prompt_or_threshold_tuning_count"],
            0,
        )

    def test_scenario_metadata_public_label_guard_rejects_paths_and_secrets(self) -> None:
        for value in (
            "C:" + "/" + "Us" + "ers/sdy/private-case.jsonl",
            "/" + "home/sdy/private-case.jsonl",
            "/" + "Us" + "ers/sdy/private-case.jsonl",
            "Bear" + "er sk-" + "test",
            "raw_" + "private_log_export",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    benchmark.public_metadata_label(value, field="scenario_source_material")

    def test_rows_record_scenario_generation_and_tuning_visibility(self) -> None:
        payload = benchmark.run_benchmark()
        rows = payload["rows"]
        holdout_rows = [
            row for row in rows if "holdout_blind" in row["scenario_provenance"]
        ]

        self.assertGreater(len(holdout_rows), 0)
        for row in rows:
            self.assertIn("scenario_generated_by", row)
            self.assertIn("scenario_source_material", row)
            self.assertIn("aippocampus_internals_visible", row)
            self.assertIn("prompt_threshold_tuning_role", row)
            self.assertNotIn("\\", row["scenario_source_material"])
        self.assertTrue(
            all(
                row["prompt_threshold_tuning_role"] == "holdout_excluded"
                for row in holdout_rows
            )
        )

    def test_docs_register_runner_and_claim_boundary(self) -> None:
        evidence_map = EVIDENCE_MAP.read_text(encoding="utf-8")
        benchmark_plan = BENCHMARK_PLAN.read_text(encoding="utf-8")

        self.assertIn("benchmarks/aippocampus/benchmark_continuous_memory_arms.py", evidence_map)
        self.assertIn("Continuous-memory attribution arms", evidence_map)
        self.assertIn("true_aippocampus_memory", benchmark_plan)
        self.assertIn("sham_unrelated_memory", benchmark_plan)
        self.assertIn("stale_wrong_memory", benchmark_plan)
        self.assertIn("oracle_memory", benchmark_plan)
        self.assertIn("memory_presence_effect", benchmark_plan)
        self.assertIn("memory_correctness_effect", benchmark_plan)
        self.assertIn("amortized_cost_per_successful_slice", benchmark_plan)
        self.assertIn("harm_weighted_false_positive_cost", benchmark_plan)
        self.assertIn("net_value_under_equalized_cost", benchmark_plan)
        self.assertIn("#410 cost and harm ledger", benchmark_plan)
        self.assertIn("#407 pre-registration", benchmark_plan)
        self.assertIn("#409 scenario provenance and holdout controls", benchmark_plan)
        self.assertIn("public_log_or_vcs_derived", benchmark_plan)
        self.assertIn("holdout_blind", benchmark_plan)
        self.assertIn("holdout_excluded", benchmark_plan)
        self.assertIn("source_grounded_task_success_under_equalized_cost", benchmark_plan)
        self.assertIn("no demonstrated memory advantage", benchmark_plan)
        self.assertIn("not a public superiority claim", benchmark_plan)

    def test_cli_emits_json_and_can_write_report(self) -> None:
        output = REPO_ROOT / ".tmp" / "test-continuous-memory-arms.json"
        if output.exists():
            output.unlink()

        result = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS / "benchmark_continuous_memory_arms.py"),
                "--json",
                "--output",
                str(output),
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        stdout_payload = json.loads(result.stdout)
        file_payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(stdout_payload["kind"], "aippocampus_continuous_memory_arms_benchmark")
        self.assertEqual(file_payload["metrics"], stdout_payload["metrics"])


if __name__ == "__main__":
    unittest.main()
