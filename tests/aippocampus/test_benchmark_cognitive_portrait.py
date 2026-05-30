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
        self.assertIn("live_model_behavioral_equivalence", payload["cannot_claim"])

    def test_portrait_artifact_keeps_source_refs_and_back_pointers(self) -> None:
        payload = benchmark.run_benchmark()
        portrait = payload["portrait"]

        self.assertEqual(portrait["source_surface"], "question_candidate_frontier_marker_question_link")
        self.assertGreaterEqual(len(portrait["recurring_questions"]), 1)
        for item in portrait["recurring_questions"]:
            self.assertTrue(item["source_finding_ids"])
            self.assertTrue(item["source_ref_tokens"])
        for item in portrait["frontiers"]:
            self.assertTrue(item["source_finding_id"])
            self.assertTrue(item["source_ref_tokens"])

    def test_report_states_help_loss_and_over_personalization_boundary(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertTrue(payload["report"]["helps"])
        self.assertIn(
            "Exact quote recovery still needs fuller clean-source injection.",
            payload["report"]["loses_fidelity"],
        )
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
