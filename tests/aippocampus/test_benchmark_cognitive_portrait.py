from __future__ import annotations

import sys
import unittest
from pathlib import Path

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

import benchmark_cognitive_portrait as benchmark  # noqa: E402


class CognitivePortraitBenchmarkTests(unittest.TestCase):
    def test_benchmark_compares_structured_portrait_to_full_source_context(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_cognitive_portrait_benchmark")
        self.assertTrue(payload["quality_gate_ok"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "contract_smoke")
        self.assertEqual(payload["claim_level"], "contract_smoke")
        self.assertEqual(payload["sample_case_count"], 3)
        self.assertGreater(payload["minimum_empirical_case_count"], payload["sample_case_count"])
        self.assertEqual(
            payload["sample_size_warning"]["sample_case_count"],
            payload["sample_case_count"],
        )
        self.assertIn(
            "statistically_meaningful_cognitive_portrait_quality",
            payload["sample_size_warning"]["cannot_claim"],
        )
        self.assertLess(
            payload["metrics"]["portrait_context_approx_tokens"],
            payload["metrics"]["full_context_approx_tokens"],
        )
        self.assertLess(payload["metrics"]["portrait_to_full_token_ratio"], 1.0)
        self.assertEqual(payload["metrics"]["source_fidelity_rate"], 1.0)
        self.assertEqual(payload["metrics"]["structured_over_personalization_risk_count"], 0)
        self.assertGreater(
            payload["metrics"]["naive_summary_over_personalization_risk_count"],
            0,
        )
        self.assertFalse(payload["privacy_boundary"]["raw_context_emitted"])
        self.assertTrue(payload["privacy_boundary"]["case_selection_filters_active"])
        self.assertEqual(
            payload["privacy_boundary"]["case_selection_filter_policy"],
            "aippocampus_runtime.safety.benchmark_sensitive_text_policy",
        )
        self.assertIn("live_model_behavioral_equivalence", payload["cannot_claim"])
        self.assertIn(
            "statistically_meaningful_cognitive_portrait_quality",
            payload["cannot_claim"],
        )

    def test_portrait_artifact_keeps_source_refs_and_back_pointers(self) -> None:
        payload = benchmark.run_benchmark()
        portrait = payload["portrait"]

        self.assertEqual(
            portrait["source_surface"],
            "question_candidate_frontier_marker_question_link_theme_candidate",
        )
        self.assertGreaterEqual(len(portrait["recurring_questions"]), 1)
        for item in portrait["recurring_questions"]:
            self.assertTrue(item["source_finding_ids"])
            self.assertTrue(item["source_ref_tokens"])
        for item in portrait["frontiers"]:
            self.assertTrue(item["source_finding_id"])
            self.assertTrue(item["source_ref_tokens"])
            self.assertTrue(item["dimensions"])

    def test_frontier_and_theme_dimensions_are_rendered(self) -> None:
        ref = {
            "thread_key": "session:diagnostic",
            "message_id": "msg-diagnostic",
            "source_line": 12,
        }
        portrait = benchmark.build_cognitive_portrait(
            [
                {
                    "finding_kind": "frontier_marker",
                    "fingerprint": "sf_frontier",
                    "frontier_type": "blocked",
                    "linked_question_short": "context continuity",
                    "boundary_reason": "Source refs must survive handoff.",
                    "concepts": ["handoff calibration", "source refs"],
                    "source_refs": [ref],
                },
                {
                    "finding_kind": "theme_candidate",
                    "theme_cluster_id": "th_frontier",
                    "theme_short": "handoff calibration",
                    "shared_concepts": ["handoff calibration", "source refs"],
                    "source_refs": [ref],
                },
            ]
        )
        rendered = benchmark.render_structured_portrait(portrait)

        self.assertIn("handoff calibration", rendered)
        self.assertIn("source refs", rendered)
        self.assertTrue(portrait["themes"])
        self.assertEqual(portrait["diagnostics"]["theme_candidate_count"], 1)

    def test_linked_pack_keeps_unlinked_question_candidates_as_single_observations(self) -> None:
        ref_1 = {
            "thread_key": "session:linked",
            "message_id": "msg-linked",
            "source_line": 10,
        }
        ref_2 = {
            "thread_key": "session:unlinked",
            "message_id": "msg-unlinked",
            "source_line": 20,
        }
        portrait = benchmark.build_cognitive_portrait(
            [
                {
                    "finding_kind": "question_candidate",
                    "fingerprint": "sf_linked_question",
                    "question_short": "context after compaction",
                    "question_text": "How should context survive compaction?",
                    "what_features": ["context continuity", "compaction"],
                    "source_refs": [ref_1],
                },
                {
                    "finding_kind": "question_candidate",
                    "fingerprint": "sf_unlinked_question",
                    "question_short": "threshold calibration",
                    "question_text": "How should threshold calibration be validated?",
                    "what_features": ["threshold calibration", "quality evidence"],
                    "source_refs": [ref_2],
                },
                {
                    "finding_kind": "question_link",
                    "question_cluster_id": "ql_context",
                    "linked_question_short": "context after compaction",
                    "question_count": 2,
                    "link_type": "recurring",
                    "concepts": ["context continuity"],
                    "source_refs": [ref_1],
                    "linked_questions": [
                        {
                            "source_finding_id": "sf_linked_question",
                            "question_short": "context after compaction",
                            "what_features": ["context continuity", "compaction"],
                        }
                    ],
                },
            ]
        )
        rendered = benchmark.render_structured_portrait(portrait)
        labels = [item["label"] for item in portrait["recurring_questions"]]

        self.assertIn("context after compaction", labels)
        self.assertIn("threshold calibration", labels)
        self.assertIn("threshold calibration", rendered)
        self.assertEqual(
            benchmark.source_fidelity_metrics(portrait)["portrait_item_count"],
            2,
        )

    def test_report_states_help_loss_and_over_personalization_boundary(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertTrue(payload["report"]["helps"])
        self.assertIn(
            "Exact quote recovery still needs fuller clean-source injection.",
            payload["report"]["loses_fidelity"],
        )
        actions = payload["fidelity_gap_actions"]
        self.assertEqual(actions[0]["gap_id"], "exact_quote_recovery")
        self.assertIn("aippocampus search", actions[0]["command"])
        self.assertIn("recall_navigation.py", actions[0]["owner_path"])
        self.assertEqual(actions[0]["claim_boundary"], "diagnostic_action_not_source_evidence")
        self.assertTrue(payload["report"]["over_personalization"])
        cases = {case["case_id"]: case for case in payload["cases"]}
        self.assertTrue(cases["resume_after_compaction"]["portrait_equivalent_by_fixture"])
        self.assertTrue(cases["profile_boundary"]["portrait_equivalent_by_fixture"])
        self.assertTrue(cases["exact_quote_recovery"]["portrait_equivalent_by_fixture"])
        self.assertIn(
            "Do not claim continuity unless source refs survive",
            cases["exact_quote_recovery"]["portrait_missing_terms"],
        )

    def test_unbacked_existing_finding_shapes_are_skipped(self) -> None:
        fixture = benchmark.build_fixture()
        rows = list(fixture.findings) + [
            {
                "finding_kind": "question_candidate",
                "fingerprint": "sf_unbacked",
                "question_short": "unsupported profile shortcut",
                "question_text": "Can this unsupported profile be used?",
                "source_refs": [],
            }
        ]

        portrait = benchmark.build_cognitive_portrait(rows)

        self.assertIn(
            "sf_unbacked",
            portrait["diagnostics"]["skipped_unbacked_finding_ids"],
        )
        self.assertEqual(
            benchmark.source_fidelity_metrics(portrait)["source_fidelity_rate"],
            1.0,
        )

    def test_private_text_is_explicit_debug_output_only(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=True)

        self.assertTrue(payload["privacy_boundary"]["raw_context_emitted"])
        self.assertIn("debug_contexts", payload)
        self.assertIn("structured_portrait", payload["debug_contexts"])
        self.assertIn("full_source_context", payload["debug_contexts"])


if __name__ == "__main__":
    unittest.main()
