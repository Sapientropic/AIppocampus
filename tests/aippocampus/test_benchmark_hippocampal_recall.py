from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_hippocampal_recall as benchmark  # noqa: E402
import build_hippocampal_fixture as builder  # noqa: E402
import hippocampal_fixture_schema as schema  # noqa: E402


def _by_case(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["case_id"]): row for row in rows}


class HippocampalRecallP1BenchmarkTests(unittest.TestCase):
    def test_builder_produces_public_safe_diagnostic_seed(self) -> None:
        rows = builder.build_fixture_rows()
        validation = schema.validate_fixture(rows)
        serialized = "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows
        )

        self.assertTrue(validation["ok"], validation)
        self.assertEqual(validation["dataset_id"], schema.DATASET_ID)
        self.assertGreaterEqual(validation["case_count"], 10)
        self.assertTrue(validation["public_safety"]["synthetic_public_safe"])
        self.assertFalse(validation["public_safety"]["uses_private_history"])
        self.assertFalse(validation["coverage"]["full_p1_matrix_claim"])
        self.assertGreater(validation["coverage"]["diagnostic_only_cell_count"], 0)
        self.assertIn("D0/I0", validation["cell_density"])
        self.assertIn("D3/I3", validation["cell_density"])
        self.assertIn("D6/I5", validation["cell_density"])
        self.assertNotIn("internal_cue_list", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)
        self.assertNotIn(".aippocampus", serialized)

    def test_schema_rejects_missing_source_refs_invalid_levels_and_untrusted_truth(self) -> None:
        row = builder.build_fixture_rows()[0]
        cases: list[dict[str, object]] = []
        for code, mutation in {
            "missing_source_refs": lambda item: item.update({"expected_source_refs": []}),
            "invalid_degradation_level": lambda item: item.update(
                {"degradation_level": "D9"}
            ),
            "invalid_interference_level": lambda item: item.update(
                {"interference_level": "I9"}
            ),
            "missing_ambiguity_policy": lambda item: item.pop(
                "ambiguity_policy",
                None,
            ),
            "unsupported_truth_source": lambda item: item.update(
                {"truth_source": "model_generated_label"}
            ),
            "unsupported_scorer_input": lambda item: item.update(
                {
                    "scorer_allowed_inputs": [
                        "query",
                        "candidate_refs",
                        "source_reopen_result",
                        "internal_cue_list",
                    ]
                }
            ),
        }.items():
            mutated = copy.deepcopy(row)
            mutated["case_id"] = f"{row['case_id']}__{code}"
            mutation(mutated)
            cases.append(mutated)

        validation = schema.validate_fixture(cases)

        self.assertFalse(validation["ok"], validation)
        self.assertTrue(
            {
                "missing_source_refs",
                "invalid_degradation_level",
                "invalid_interference_level",
                "missing_ambiguity_policy",
                "unsupported_truth_source",
                "unsupported_scorer_input",
            }.issubset(set(validation["blocker_codes"]))
        )

    def test_jsonl_roundtrip_keeps_report_safe_rows(self) -> None:
        rows = builder.build_fixture_rows()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hippocampal_synthetic_v1.jsonl"
            write_report = builder.write_fixture(path, rows=rows)
            loaded = schema.load_fixture(path)

        self.assertTrue(write_report["ok"], write_report)
        self.assertEqual(len(loaded), len(rows))
        self.assertEqual(
            [row["case_id"] for row in loaded],
            [row["case_id"] for row in rows],
        )
        for row in loaded:
            sanitized = schema.sanitized_case(row)
            serialized = json.dumps(sanitized, ensure_ascii=False, sort_keys=True)
            self.assertIn("query_sha1", sanitized)
            self.assertNotIn(str(row["query"]), serialized)
            self.assertNotIn("raw_source_text", serialized)

    def test_runner_reports_d_i_views_gates_and_claim_boundaries(self) -> None:
        payload = benchmark.run_benchmark()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_hippocampal_recall_benchmark")
        self.assertFalse(payload["quality_gates"]["full_p1_coverage_sufficient"])
        self.assertTrue(payload["quality_gates"]["must_pass_gates_represented"])
        self.assertIn("D0", payload["views"]["by_degradation"])
        self.assertIn("I5", payload["views"]["by_interference"])
        self.assertIn("D0/I0", payload["views"]["matrix"])
        self.assertIn("D6/I5", payload["views"]["matrix"])
        self.assertEqual(
            payload["views"]["matrix"]["D6/I5"]["coverage_status"],
            "diagnostic_only",
        )
        self.assertEqual(
            payload["report_schema_version"],
            "aippocampus.hippocampal_recall_report.v1",
        )
        self.assertEqual(payload["config"]["fixture_dataset_id"], schema.DATASET_ID)
        self.assertEqual(
            payload["config"]["fixture_schema_version"],
            schema.FIXTURE_SCHEMA_VERSION,
        )
        self.assertEqual(payload["config"]["fixture_version"], schema.FIXTURE_VERSION)
        self.assertEqual(payload["config"]["fixture_seed"], schema.FIXTURE_SEED)
        self.assertEqual(
            payload["reproducibility"]["clean_clone_command"],
            "python benchmarks/aippocampus/benchmark_hippocampal_recall.py --json",
        )
        self.assertFalse(payload["reproducibility"]["requires_private_registry"])
        self.assertIn("scent_precision", payload["views"]["aggregate"])
        self.assertIn("calibration", payload["views"])
        self.assertFalse(payload["config"]["uses_private_history"])
        self.assertFalse(payload["privacy_boundary"]["raw_query_text_emitted"])
        self.assertIn("full_50_scene_350_case_p1_quality", payload["cannot_claim"])
        self.assertNotIn("internal_cue_list", serialized)
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)

    def test_adapter_contract_reports_local_arms_and_external_diagnostics(self) -> None:
        payload = benchmark.run_benchmark()
        contract = payload["adapter_contract"]
        views_by_arm = payload["views_by_arm"]

        for arm in (
            "keyword_only",
            "baseline_rag",
            "closed_book",
            "overactive_all_evidence",
            "random_retrieval",
        ):
            self.assertIn(arm, contract["local_arms"])
            self.assertIn(arm, views_by_arm)
            self.assertIn("D0/I0", views_by_arm[arm]["matrix"])
            self.assertIn("calibration", views_by_arm[arm])
            self.assertIn("source_reopen_success", views_by_arm[arm]["aggregate"])
            self.assertIn("cost", views_by_arm[arm]["aggregate"])

        self.assertEqual(contract["arm_count"], len(contract["local_arms"]))
        self.assertFalse(contract["requires_external_credentials"])
        self.assertEqual(
            contract["external_adapters"]["mem0"]["status"],
            "diagnostic_missing_configuration",
        )
        self.assertEqual(
            contract["external_adapters"]["zep_graphiti"]["status"],
            "diagnostic_missing_configuration",
        )
        self.assertIn(
            "expected_source_refs",
            contract["truth_label_fields_hidden_from_adapters"],
        )

    def test_adapter_case_input_hides_truth_labels(self) -> None:
        row = builder.build_fixture_rows()[0]
        adapter_case = benchmark.adapter_case_for_row(row)
        serialized = json.dumps(adapter_case, ensure_ascii=False, sort_keys=True)

        self.assertEqual(adapter_case["case_id"], row["case_id"])
        self.assertIn("query", adapter_case)
        self.assertIn("candidate_source_refs", adapter_case)
        for field in (
            "expected_decision",
            "expected_source_refs",
            "acceptable_scent_refs",
            "distractor_source_refs",
            "forbidden_claims",
            "truth_source",
            "ambiguity_policy",
        ):
            self.assertNotIn(field, adapter_case)
            self.assertNotIn(field, serialized)

    def test_h5_consolidation_report_uses_frozen_h1_h2_labels_and_controls(self) -> None:
        payload = benchmark.run_benchmark()
        h5 = payload["h5_consolidation"]

        self.assertEqual(
            h5["version"],
            "aippocampus.h5_consolidation_delta_report.v1",
        )
        self.assertEqual(h5["before_arm"], "keyword_only")
        self.assertEqual(
            h5["arms"],
            [
                "no_consolidation",
                "aippocampus_dream_consolidation",
                "random_consolidation",
                "simple_summary_consolidation",
            ],
        )
        self.assertTrue(h5["truth_boundary"]["labels_frozen_before_after"])
        self.assertTrue(h5["truth_boundary"]["reruns_same_case_ids"])
        self.assertFalse(h5["truth_boundary"]["allows_relabeling_after_consolidation"])
        self.assertFalse(h5["truth_boundary"]["uses_live_dream_worker"])
        self.assertIn(
            "user_visible_dream_benefit",
            h5["cannot_claim"],
        )

        no_consolidation = h5["views_by_arm"]["no_consolidation"]["aggregate"]
        self.assertEqual(no_consolidation["score_delta_total"], 0.0)
        self.assertEqual(no_consolidation["false_forgetting_count"], 0)
        self.assertEqual(no_consolidation["overgeneralization_count"], 0)

        dream = h5["views_by_arm"]["aippocampus_dream_consolidation"]["aggregate"]
        self.assertGreater(dream["improvement_count"], 0)
        self.assertIn("stale_as_current_delta", dream)
        self.assertIn("wrong_twin_delta", dream)
        self.assertIn("cost_per_improvement", dream)
        self.assertGreaterEqual(dream["new_association_discovery_count"], 1)

    def test_h5_case_deltas_keep_same_cases_and_report_regressions(self) -> None:
        payload = benchmark.run_benchmark()
        h5 = payload["h5_consolidation"]
        case_deltas = h5["case_deltas"]

        self.assertTrue(case_deltas)
        for delta in case_deltas:
            self.assertTrue(delta["same_case_id_after_rerun"])
            self.assertFalse(delta["truth_relabeling_allowed"])
            self.assertIn("frozen_expected_decision", delta)
            self.assertIn("frozen_label_sha1", delta)
            self.assertNotIn("query", delta)

        random_view = h5["views_by_arm"]["random_consolidation"]["aggregate"]
        summary_view = h5["views_by_arm"]["simple_summary_consolidation"]["aggregate"]
        self.assertGreater(random_view["false_forgetting_count"], 0)
        self.assertGreater(summary_view["overgeneralization_count"], 0)

    def test_cross_system_comparison_table_reports_claim_levels_and_missing_adapters(self) -> None:
        payload = benchmark.run_benchmark()
        comparison = payload["cross_system_comparison"]
        rows = {row["row_id"]: row for row in comparison["rows"]}

        self.assertEqual(
            comparison["version"],
            "aippocampus.hippocampal_cross_system_comparison.v1",
        )
        self.assertEqual(
            comparison["dated_report_path"],
            "docs/evidence/benchmarks/hippocampal-cross-system-comparison-2026-06-04.md",
        )
        for row_id in (
            "aippocampus_diagnostic",
            "baseline_rag",
            "keyword_only",
            "closed_book",
            "overactive_all_evidence",
            "random_retrieval",
            "semantic_only",
            "mem0",
            "zep_graphiti",
            "letta",
            "langmem",
        ):
            self.assertIn(row_id, rows)

        keyword = rows["keyword_only"]
        self.assertTrue(keyword["comparable"])
        self.assertEqual(keyword["claim_level"], "synthetic_public_result")
        self.assertGreater(keyword["h1_h2_sample_size"], 0)
        self.assertGreater(keyword["d5_d6_sample_size"], 0)
        self.assertIn("h1_degraded_drop_from_d0", keyword)
        self.assertIn("h2_separation_accuracy", keyword)
        self.assertIn("source_reopen_success", keyword)

        aippocampus = rows["aippocampus_diagnostic"]
        self.assertEqual(aippocampus["h5_arm"], "aippocampus_dream_consolidation")
        self.assertGreater(aippocampus["h5_score_delta_total"], 0)
        self.assertIn("user_visible_dream_benefit", comparison["cannot_claim"])

        mem0 = rows["mem0"]
        self.assertFalse(mem0["comparable"])
        self.assertEqual(mem0["claim_level"], "diagnostic_missing_configuration")
        self.assertIsNone(mem0["h1_degraded_accuracy"])

        semantic = rows["semantic_only"]
        self.assertFalse(semantic["comparable"])
        self.assertEqual(semantic["availability"], "adapter_not_implemented")

    def test_scoring_catches_source_reopen_wrong_twin_overactive_and_skip_failures(self) -> None:
        rows = _by_case(builder.build_fixture_rows())

        source_reopen = benchmark.score_response(
            rows["keyword_contract__d0_i0"],
            {
                "decision": "evidence",
                "confidence": 0.91,
                "evidence_refs": ["source:keyword_contract:target"],
                "scent_refs": [],
                "source_reopened": False,
                "claims": [],
            },
        )
        wrong_twin = benchmark.score_response(
            rows["superseded_route__d1_i5"],
            {
                "decision": "evidence",
                "confidence": 0.9,
                "evidence_refs": ["source:superseded_route:old"],
                "scent_refs": [],
                "source_reopened": True,
                "claims": [],
            },
        )
        overactive = benchmark.score_response(
            rows["ambiguous_hook__d3_i3"],
            {
                "decision": "evidence",
                "confidence": 0.87,
                "evidence_refs": ["source:ambiguous_hook:alpha"],
                "scent_refs": [],
                "source_reopened": True,
                "claims": [],
            },
        )
        unsupported_skip = benchmark.score_response(
            rows["keyword_contract__d0_i0"],
            {
                "decision": "skip",
                "confidence": 0.15,
                "evidence_refs": [],
                "scent_refs": [],
                "source_reopened": False,
                "claims": [],
            },
        )
        wrong_evidence = benchmark.score_response(
            rows["keyword_contract__d0_i0"],
            {
                "decision": "evidence",
                "confidence": 0.74,
                "evidence_refs": ["source:keyword_contract:unrelated"],
                "scent_refs": [],
                "source_reopened": True,
                "claims": [],
            },
        )

        self.assertEqual(source_reopen["outcome"], "source_reopen_failure")
        self.assertEqual(wrong_twin["outcome"], "wrong_twin_selection")
        self.assertEqual(overactive["outcome"], "overconfident_evidence")
        self.assertEqual(unsupported_skip["outcome"], "unsupported_skip")
        self.assertEqual(wrong_evidence["outcome"], "wrong_evidence")
        self.assertLess(source_reopen["score"], 0)
        self.assertLess(wrong_twin["score"], 0)
        self.assertLess(overactive["score"], 0)
        self.assertLess(wrong_evidence["score"], 0)

    def test_scoring_distinguishes_scent_layers_and_calibration_categories(self) -> None:
        rows = _by_case(builder.build_fixture_rows())

        target_only = benchmark.score_response(
            rows["ambiguous_hook__d3_i3"],
            {
                "decision": "scent",
                "confidence": 0.56,
                "evidence_refs": [],
                "scent_refs": ["source:ambiguous_hook:alpha"],
                "source_reopened": False,
                "claims": [],
            },
        )
        both = benchmark.score_response(
            rows["ambiguous_hook__d3_i3"],
            {
                "decision": "scent",
                "confidence": 0.55,
                "evidence_refs": [],
                "scent_refs": [
                    "source:ambiguous_hook:alpha",
                    "source:ambiguous_hook:beta",
                ],
                "source_reopened": False,
                "claims": [],
            },
        )
        distractor_only = benchmark.score_response(
            rows["ambiguous_hook__d3_i3"],
            {
                "decision": "scent",
                "confidence": 0.52,
                "evidence_refs": [],
                "scent_refs": ["source:ambiguous_hook:beta"],
                "source_reopened": False,
                "claims": [],
            },
        )
        underconfident = benchmark.score_response(
            rows["metaphor_cache__d2_i1"],
            {
                "decision": "scent",
                "confidence": 0.48,
                "evidence_refs": [],
                "scent_refs": ["source:metaphor_cache:target"],
                "source_reopened": False,
                "claims": [],
            },
        )

        self.assertEqual(target_only["outcome"], "correct_scent")
        self.assertEqual(target_only["scent_layer"], "scent_hit")
        self.assertTrue(target_only["scent_precision_contributes"])
        self.assertEqual(both["outcome"], "correct_scent")
        self.assertEqual(both["scent_layer"], "scent_both")
        self.assertTrue(both["low_separation"])
        self.assertFalse(both["scent_precision_contributes"])
        self.assertEqual(distractor_only["outcome"], "partial_miss")
        self.assertEqual(distractor_only["scent_layer"], "scent_distractor")
        self.assertEqual(underconfident["outcome"], "underconfident_scent")
        self.assertEqual(underconfident["calibration_category"], "underconfident_scent")


if __name__ == "__main__":
    unittest.main()
