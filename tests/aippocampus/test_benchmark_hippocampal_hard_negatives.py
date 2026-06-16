from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_hippocampal_hard_negatives as benchmark  # noqa: E402


class HippocampalHardNegativeBenchmarkTests(unittest.TestCase):
    def _write_locomo_smoke_dataset(self, directory: Path) -> Path:
        dataset_path = directory / "locomo-smoke.json"
        payload = [
            {
                "sample_id": "conv-public-smoke",
                "conversation": {
                    "session_1_date_time": "2026-01-01",
                    "session_1": [
                        {
                            "dia_id": "D1:1",
                            "speaker": "speaker_a",
                            "text": "The user chose the source-backed route after checking the audit packet.",
                        },
                        {
                            "dia_id": "D1:2",
                            "speaker": "speaker_b",
                            "text": "A nearby note mentions the same audit packet but does not choose it.",
                        },
                        {
                            "dia_id": "D1:3",
                            "speaker": "speaker_a",
                            "text": "The source-backed route phrase appears again as a distracting paraphrase.",
                        },
                    ],
                },
                "qa": [
                    {
                        "question": "Which route did the user choose after checking the audit packet?",
                        "answer": "The source-backed route.",
                        "category": "1",
                        "evidence": ["D1:1"],
                    }
                ],
            }
        ]
        dataset_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return dataset_path

    def test_fixture_contract_covers_all_hard_negative_families(self) -> None:
        fixture = benchmark.load_fixture()
        validation = benchmark.validate_fixture(fixture)

        self.assertTrue(validation["ok"], validation)
        self.assertEqual(
            validation["families_present"],
            {
                "near_neighbor_lure",
                "said_but_unsupported",
                "superseded_currentness_trap",
                "surface_paraphrase_lure",
            },
        )
        self.assertEqual(validation["missing_required_fields"], {})
        self.assertEqual(validation["case_count"], 12)
        self.assertEqual(
            validation["family_counts"],
            {
                "near_neighbor_lure": 3,
                "said_but_unsupported": 3,
                "superseded_currentness_trap": 3,
                "surface_paraphrase_lure": 3,
            },
        )
        self.assertTrue(validation["truth_source_independent"])
        self.assertTrue(validation["currentness_schema_present"])

    def test_scoring_rewards_honest_abstention_over_confident_wrong_evidence(self) -> None:
        fixture = benchmark.load_fixture()
        cases = benchmark.cases_by_id(fixture)

        honest = benchmark.score_response(
            cases["near_neighbor_lure__d2_i2"],
            {
                "decision": "skip",
                "confidence": 0.2,
                "evidence_refs": [],
                "scent_refs": [],
                "claims": [],
            },
        )
        wrong = benchmark.score_response(
            cases["near_neighbor_lure__d2_i2"],
            {
                "decision": "evidence",
                "confidence": 0.91,
                "evidence_refs": ["source:near_neighbor:frequent_distractor"],
                "scent_refs": [],
                "claims": ["The frequent distractor is the target memory."],
            },
        )

        self.assertEqual(honest["outcome"], "honest_skip")
        self.assertEqual(wrong["outcome"], "wrong_source_evidence")
        self.assertGreater(honest["score"], wrong["score"])
        self.assertLess(wrong["score"], 0)

    def test_scoring_catches_stale_currentness_and_unsupported_fact_failures(self) -> None:
        cases = benchmark.cases_by_id(benchmark.load_fixture())

        stale = benchmark.score_response(
            cases["superseded_currentness_trap__d1_i5"],
            {
                "decision": "evidence",
                "confidence": 0.88,
                "evidence_refs": ["source:superseded:old_decision"],
                "scent_refs": [],
                "claims": ["The old answer is the current decision."],
            },
        )
        unsupported = benchmark.score_response(
            cases["said_but_unsupported__d2_i1"],
            {
                "decision": "evidence",
                "confidence": 0.86,
                "evidence_refs": ["source:unsupported:hypothesis_only"],
                "scent_refs": [],
                "claims": ["The hypothesis became an accepted fact."],
            },
        )

        self.assertEqual(stale["outcome"], "stale_as_current")
        self.assertEqual(unsupported["outcome"], "unsupported_as_fact")
        self.assertLessEqual(stale["score"], benchmark.OUTCOME_WEIGHTS["honest_skip"])
        self.assertLessEqual(unsupported["score"], benchmark.OUTCOME_WEIGHTS["honest_skip"])

    def test_runner_reports_seven_outcomes_and_sanitized_claim_boundaries(self) -> None:
        payload = benchmark.run_benchmark()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_hippocampal_hard_negative_benchmark")
        self.assertEqual(payload["status"], "production_like_public_synthetic_slice")
        self.assertTrue(payload["contract_gate_ok"])
        self.assertTrue(payload["production_slice_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertFalse(payload["public_quality_gate_ok"])
        self.assertEqual(payload["benchmark_maturity_level"], "diagnostic_proxy")
        self.assertEqual(payload["measurement_origin"], "deterministic_fixture")
        self.assertFalse(payload["observed_agent_behavior"])
        self.assertEqual(
            set(payload["outcome_counts"]),
            {
                "correct_evidence",
                "honest_scent",
                "honest_skip",
                "wrong_source_evidence",
                "stale_as_current",
                "unsupported_as_fact",
                "confabulation",
            },
        )
        self.assertGreater(
            payload["outcome_weights"]["honest_skip"],
            payload["outcome_weights"]["wrong_source_evidence"],
        )
        self.assertGreater(
            payload["outcome_weights"]["honest_scent"],
            payload["outcome_weights"]["unsupported_as_fact"],
        )
        self.assertEqual(payload["metrics"]["case_count"], 12)
        self.assertEqual(payload["metrics"]["major_failure_count"], 7)
        self.assertEqual(payload["metrics"]["wrong_source_evidence_count"], 2)
        self.assertEqual(payload["metrics"]["stale_as_current_count"], 2)
        self.assertEqual(payload["metrics"]["unsupported_as_fact_count"], 2)
        self.assertEqual(payload["metrics"]["confabulation_count"], 1)
        self.assertEqual(payload["metrics"]["honest_uncertainty_count"], 5)
        self.assertEqual(payload["metrics"]["source_reopen_count"], 11)
        self.assertEqual(payload["metrics"]["evidence_source_reopen_rate"], 1.0)
        taxonomy = payload["contract_taxonomy_slice"]
        self.assertTrue(taxonomy["ok"])
        self.assertTrue(taxonomy["failures_expected_for_taxonomy_coverage"])
        self.assertEqual(taxonomy["metrics"]["major_failure_count"], 7)
        self.assertEqual(
            payload["metrics"]["family_counts"],
            {
                "near_neighbor_lure": 3,
                "said_but_unsupported": 3,
                "superseded_currentness_trap": 3,
                "surface_paraphrase_lure": 3,
            },
        )
        self.assertTrue(payload["quality_gates"]["production_like_family_floor_met"])
        production = payload["production_slice"]["metrics"]
        self.assertEqual(production["scored_example_count"], 12)
        self.assertEqual(production["major_failure_count"], 0)
        self.assertEqual(production["wrong_source_evidence_count"], 0)
        self.assertEqual(production["stale_as_current_count"], 0)
        self.assertEqual(production["unsupported_as_fact_count"], 0)
        self.assertEqual(production["confabulation_count"], 0)
        self.assertEqual(production["honest_uncertainty_count"], 4)
        self.assertEqual(production["source_reopen_count"], 8)
        self.assertEqual(production["evidence_source_reopen_rate"], 1.0)
        self.assertEqual(
            payload["production_slice"]["claim_level"],
            "public_production_like_synthetic_diagnostic",
        )
        self.assertFalse(payload["config"]["uses_model_judge"])
        self.assertFalse(payload["config"]["uses_private_history"])
        self.assertEqual(
            payload["config"]["claim_surface"],
            "production_like_public_synthetic_slice",
        )
        self.assertFalse(payload["privacy_boundary"]["raw_query_text_emitted"])
        self.assertIn("production-like synthetic", serialized)
        self.assertIn("cannot claim real-history H1/H2 quality", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)

    def test_public_dialogue_cohort_derives_source_safe_cases_from_locomo_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_path = self._write_locomo_smoke_dataset(Path(tmp))

            payload = benchmark.run_benchmark(
                cohort="public-dialogue-derived",
                public_dialogue_dataset_path=dataset_path,
                public_dialogue_max_samples=1,
                public_dialogue_max_cases=10,
            )

        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "public_dialogue_derived_cohort")
        self.assertEqual(payload["config"]["cohort"], "public_dialogue_derived")
        self.assertEqual(payload["dataset"]["source_family"], "LoCoMo")
        self.assertEqual(payload["metrics"]["case_count"], 3)
        self.assertEqual(payload["metrics"]["major_failure_count"], 0)
        self.assertEqual(payload["metrics"]["wrong_source_evidence_count"], 0)
        self.assertEqual(payload["metrics"]["unsupported_as_fact_count"], 0)
        self.assertEqual(
            payload["metrics"]["family_counts"],
            {
                "near_neighbor_lure": 1,
                "said_but_unsupported": 1,
                "superseded_currentness_trap": 0,
                "surface_paraphrase_lure": 1,
            },
        )
        self.assertEqual(
            payload["unsupported_families"]["superseded_currentness_trap"]["reason"],
            "locomo_has_dialogue_order_but_no_reliable_supersession_labels",
        )
        self.assertEqual(
            payload["external_prediction_template"]["fields"],
            ["case_id", "decision", "evidence_refs", "scent_refs", "source_reopened"],
        )
        self.assertFalse(payload["privacy_boundary"]["raw_dialogue_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_question_text_emitted"])
        self.assertIn("public_dialogue_derived", serialized)
        self.assertIn("source_ref_hashes_only", serialized)
        self.assertNotIn("source-backed route", serialized)
        self.assertNotIn("audit packet", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)

    def test_public_currentness_cohort_reports_supersession_metrics_separately(self) -> None:
        payload = benchmark.run_benchmark(cohort="public-currentness")
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        metrics = payload["metrics"]

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "public_currentness_cohort")
        self.assertEqual(payload["config"]["cohort"], "public_currentness")
        self.assertEqual(payload["dataset"]["source_family"], "public_vcs_issue_pr_fixture")
        self.assertEqual(metrics["public_currentness_case_count"], 4)
        self.assertEqual(metrics["public_dialogue_case_count"], 0)
        self.assertEqual(metrics["synthetic_contract_case_count"], 0)
        self.assertEqual(metrics["superseded_currentness_case_count"], 3)
        self.assertEqual(metrics["current_source_selected_count"], 2)
        self.assertEqual(metrics["stale_as_current_count"], 1)
        self.assertEqual(metrics["wrong_source_evidence_count"], 1)
        self.assertEqual(metrics["unsupported_as_fact_count"], 1)
        self.assertEqual(metrics["confabulation_count"], 0)
        self.assertEqual(metrics["honest_scent_or_skip_count"], 1)
        self.assertEqual(metrics["source_reopen_before_evidence_rate"], 1.0)
        self.assertTrue(metrics["public_quality_gate_ok"])
        self.assertFalse(metrics["full_p1_matrix_claimed"])
        self.assertEqual(
            metrics["per_family_case_counts"],
            {
                "near_neighbor_lure": 1,
                "said_but_unsupported": 1,
                "superseded_currentness_trap": 2,
                "surface_paraphrase_lure": 0,
            },
        )
        self.assertEqual(metrics["unsupported_family_count"], 1)
        self.assertEqual(
            payload["unsupported_families"]["surface_paraphrase_lure"]["reason"],
            "not_part_of_public_currentness_supersession_slice",
        )
        stale_case = next(
            case
            for case in payload["cases"]
            if case["case_id"] == "public_currentness:issue-1024:stale_plan_as_current"
        )
        self.assertEqual(stale_case["outcome"], "stale_as_current")
        self.assertEqual(stale_case["actual_decision"], "evidence")
        self.assertFalse(payload["quality_gates"]["full_p1_matrix_claimed"])
        self.assertTrue(payload["quality_gates"]["public_quality_gate_ok"])
        self.assertIn("historical_terrain_not_current_evidence", serialized)
        self.assertIn("public_currentness", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)

    def test_all_cohort_keeps_public_currentness_and_locomo_boundaries_separate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset_path = self._write_locomo_smoke_dataset(Path(tmp))

            payload = benchmark.run_benchmark(
                cohort="all",
                public_dialogue_dataset_path=dataset_path,
                public_dialogue_max_samples=1,
                public_dialogue_max_cases=10,
            )

        self.assertIn("synthetic_cohort", payload)
        self.assertIn("public_dialogue_cohort", payload)
        self.assertIn("public_currentness_cohort", payload)
        self.assertEqual(
            payload["public_dialogue_cohort"]["unsupported_families"][
                "superseded_currentness_trap"
            ]["reason"],
            "locomo_has_dialogue_order_but_no_reliable_supersession_labels",
        )
        self.assertEqual(
            payload["public_currentness_cohort"]["metrics"]["public_currentness_case_count"],
            4,
        )
        self.assertFalse(payload["public_currentness_cohort"]["metrics"]["full_p1_matrix_claimed"])

    def test_public_currentness_cli_outputs_json(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS / "benchmark_hippocampal_hard_negatives.py"),
                "--cohort",
                "public-currentness",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["config"]["cohort"], "public_currentness")
        self.assertEqual(payload["metrics"]["public_currentness_case_count"], 4)
        self.assertFalse(payload["metrics"]["full_p1_matrix_claimed"])


if __name__ == "__main__":
    unittest.main()
