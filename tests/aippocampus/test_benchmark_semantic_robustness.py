from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

benchmark = import_benchmark_module("benchmark_semantic_robustness")
from shared.benchmark_report_contract import benchmark_report_contract_lint


class SemanticRobustnessBenchmarkTests(unittest.TestCase):
    def test_track_s_runner_reports_s1_s3_without_live_llm_judges(self) -> None:
        payload = benchmark.run_semantic_robustness_benchmark()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["ok"], payload)
        self.assertTrue(payload["quality_gate_ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_semantic_robustness_benchmark")
        self.assertEqual(payload["track"], "Track S")
        self.assertEqual(payload["status"], "diagnostic_only")
        self.assertEqual(payload["benchmark_maturity_level"], "diagnostic_contract")
        self.assertEqual(payload["measurement_origin"], "deterministic_contract")
        self.assertFalse(payload["observed_agent_behavior"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertEqual(payload["quality_gate_kind"], "diagnostic_track_s_not_public_quality")
        self.assertFalse(payload["public_quality_gate_ok"])
        self.assertEqual(payload["decision_impact"], "diagnostic_only")
        self.assertGreater(payload["case_count"], 0)
        self.assertIn("supports", payload)
        self.assertTrue(benchmark_report_contract_lint(payload)["ok"])
        self.assertGreaterEqual(len(payload["gap_next_actions"]), 4)
        self.assertEqual(
            {action["track"] for action in payload["gap_next_actions"]},
            {"s4_offline_proxy_alignment", "s5_representation_space_health"},
        )
        self.assertFalse(payload["config"]["uses_live_llm_judge"])
        self.assertFalse(payload["config"]["requires_provider_keys"])
        self.assertFalse(payload["privacy_boundary"]["raw_prompt_or_query_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])

        tracks = payload["tracks"]
        self.assertEqual(
            set(tracks),
            {
                "s1_gate_robustness",
                "s2_retrieval_invariance",
                "s3_hard_negative_suppression",
                "s4_offline_proxy_alignment",
                "s5_representation_space_health",
            },
        )

        s1 = tracks["s1_gate_robustness"]["metrics"]
        self.assertGreaterEqual(s1["bundle_count"], 3)
        self.assertIn("decision_stability_rate", s1)
        self.assertIn("false_evidence_escalation_rate", s1)
        self.assertIn("missed_scent_or_evidence_rate", s1)
        self.assertIn("route_flip_taxonomy", s1)
        self.assertEqual(s1["false_evidence_escalation_count"], 0)

        s2 = tracks["s2_retrieval_invariance"]["metrics"]
        self.assertGreaterEqual(s2["bundle_count"], 2)
        self.assertIn("target_source_rank_variance_avg", s2)
        self.assertIn("score_variance_avg", s2)
        self.assertIn("top_k_survival_rate", s2)
        self.assertIn("rank_drop_rate", s2)

        s3 = tracks["s3_hard_negative_suppression"]["metrics"]
        self.assertGreaterEqual(s3["case_count"], 2)
        self.assertIn("hard_negative_suppression_rate", s3)
        self.assertIn("stale_as_current_rate", s3)
        self.assertIn("explicit_negation_violation_rate", s3)
        self.assertIn("source_evidence_over_escalation_rate", s3)
        self.assertIn("surface_lingering_scent_count", s3)
        self.assertEqual(s3["explicit_negation_violation_count"], 0)
        self.assertEqual(s3["stale_as_current_count"], 0)
        self.assertEqual(s3["source_evidence_over_escalation_count"], 0)
        for row in tracks["s3_hard_negative_suppression"]["cases"]:
            self.assertEqual(row["actual"], "skip", row)

        self.assertEqual(tracks["s4_offline_proxy_alignment"]["status"], "disabled_by_default")
        self.assertEqual(tracks["s4_offline_proxy_alignment"]["claim_boundary"], "proxy_not_truth")
        s4_actions = {
            action["id"]: action
            for action in tracks["s4_offline_proxy_alignment"]["next_actions"]
        }
        self.assertIn("check_local_proxy_model_availability", s4_actions)
        self.assertIn("complete_proxy_model_license_review", s4_actions)
        self.assertIn("required_artifact", s4_actions["check_local_proxy_model_availability"])
        self.assertIn("owner_path", s4_actions["complete_proxy_model_license_review"])
        self.assertEqual(
            tracks["s5_representation_space_health"]["claim_boundary"],
            "health_check_not_quality_claim",
        )
        s5_actions = {
            action["id"]: action
            for action in tracks["s5_representation_space_health"]["next_actions"]
        }
        self.assertIn("provide_local_embedding_index", s5_actions)
        self.assertIn("add_representation_health_runner", s5_actions)
        self.assertIn("required_artifact", s5_actions["provide_local_embedding_index"])
        self.assertIn("owner_path", s5_actions["add_representation_health_runner"])
        self.assertEqual(
            {
                action["id"]
                for action in payload["gap_next_actions"]
                if action["track"] == "s5_representation_space_health"
            },
            set(s5_actions),
        )
        self.assertIn("human_level_semantic_understanding", payload["cannot_claim"])
        self.assertIn("track_a_b_product_quality_replacement", payload["cannot_claim"])
        self.assertIn("live_llm_judge_quality", payload["cannot_claim"])
        self.assertIn("proxy_model_agreement_as_source_truth", payload["cannot_claim"])
        self.assertNotIn("E:\\", serialized)
        self.assertNotIn("C:\\", serialized)

    def test_private_debug_text_is_opt_in_and_proxy_alignment_can_skip_cleanly(self) -> None:
        private_payload = benchmark.run_semantic_robustness_benchmark(
            include_private_text=True,
            include_proxy_alignment=True,
        )

        self.assertTrue(private_payload["privacy_boundary"]["raw_prompt_or_query_text_emitted"])
        self.assertIn("private_debug", private_payload)
        self.assertEqual(
            private_payload["tracks"]["s4_offline_proxy_alignment"]["status"],
            "skipped_missing_local_model",
        )

if __name__ == "__main__":
    unittest.main()
