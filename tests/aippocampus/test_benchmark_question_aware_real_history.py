from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

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

import benchmark_question_aware_real_history as benchmark  # noqa: E402


def source_ref(suffix: str) -> dict[str, Any]:
    return {
        "thread_key": f"session:private-{suffix}",
        "message_id": f"msg-private-{suffix}",
        "turn_id": f"turn-private-{suffix}",
        "source_line": int(suffix) * 10,
    }


def fixture_rows() -> list[dict[str, Any]]:
    ref_1 = source_ref("1")
    ref_2 = source_ref("2")
    ref_3 = source_ref("3")
    return [
        {
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-05-01T00:00:00Z",
            "finding_kind": "question_candidate",
            "fingerprint": "sf_private_question_1",
            "question_text": "How do I keep context after compaction?",
            "question_short": "context after compaction",
            "summary": "Private raw summary should not be emitted by default.",
            "confidence": 0.87,
            "source_refs": [ref_1],
            "what_features": ["context continuity", "compaction"],
            "phase_context": "post_compaction",
            "intent_orientation": "implementation",
            "concepts": ["context continuity", "source refs"],
        },
        {
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-05-02T00:00:00Z",
            "finding_kind": "frontier_marker",
            "fingerprint": "sf_private_frontier_1",
            "frontier_type": "blocked",
            "linked_question_short": "context after compaction",
            "boundary_reason": "Resume only after source refs survive.",
            "confidence": 0.8,
            "source_refs": [ref_2],
            "concepts": ["source refs", "handoff"],
        },
        {
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-05-03T00:00:00Z",
            "finding_kind": "question_link",
            "question_cluster_id": "ql_private_context",
            "linked_question_short": "context after compaction",
            "question_count": 2,
            "source_thread_count": 2,
            "link_type": "recurring",
            "summary": "Private recurring link summary should not be emitted by default.",
            "confidence": 0.88,
            "source_refs": [ref_1, ref_2],
            "concepts": ["context continuity", "source refs"],
            "linked_questions": [
                {
                    "source_finding_id": "sf_private_question_1",
                    "question_short": "context after compaction",
                    "phase_context": "post_compaction",
                    "intent_orientation": "implementation",
                }
            ],
        },
        {
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-05-04T00:00:00Z",
            "finding_kind": "theme_candidate",
            "theme_cluster_id": "th_private_context",
            "theme_label": "Recurring question theme: context continuity",
            "theme_short": "context continuity",
            "cluster_method": "deterministic_shared_concept_neighbors_v1",
            "shared_concepts": ["context continuity", "source refs"],
            "confidence": 0.82,
            "source_refs": [ref_1, ref_2, ref_3],
        },
        {
            "kind": "aippocampus_subconscious_job_finding",
            "finding_kind": "question_candidate",
            "fingerprint": "sf_unbacked",
            "question_short": "unsupported private question",
            "question_text": "This unsupported private question should be skipped.",
            "source_refs": [],
        },
    ]


class QuestionAwareRealHistoryBenchmarkTests(unittest.TestCase):
    def test_benchmark_builds_sanitized_structural_pack(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["kind"], "aippocampus_question_aware_real_history_benchmark")
        self.assertTrue(payload["status"].startswith("structural_proxy_ready"))
        self.assertFalse(payload["private_text_emitted"])
        self.assertEqual(payload["metrics"]["pack_count"], 1)
        self.assertEqual(payload["metrics"]["source_ref_fidelity_rate"], 1.0)
        self.assertEqual(payload["metrics"]["source_seed_kind_counts"]["theme_candidate"], 1)
        self.assertGreater(payload["metrics"]["quote_required_case_count"], 0)
        self.assertEqual(
            payload["pack_selection"]["strategy"],
            "chronological_source_backed_question_rows",
        )
        self.assertEqual(payload["pack_selection"]["skipped_unbacked_row_count"], 1)
        self.assertEqual(payload["pack_selection"]["selected_source_seed_kind_counts"]["question_link"], 1)
        self.assertEqual(payload["pack_selection"]["selected_source_seed_kind_counts"]["theme_candidate"], 1)
        self.assertFalse(payload["pack_selection"]["selected_lacks_link_or_theme_context"])
        self.assertFalse(
            payload["scaffold_vs_evidence"]["answer_usefulness_evidence"][
                "live_model_answer_quality_measured"
            ]
        )
        self.assertIn(
            "final factual claims",
            payload["scaffold_vs_evidence"]["requires_clean_source_lookup"],
        )
        self.assertNotIn("How do I keep context after compaction?", rendered)
        self.assertNotIn("msg-private", rendered)
        self.assertNotIn("session:private", rendered)
        self.assertNotIn(str(REPO_ROOT), rendered)

    def test_benchmark_records_claim_boundaries(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
        )

        self.assertIn(
            "selected_question_rows_can_form_sanitized_source_backed_structural_packs",
            payload["can_claim"],
        )
        self.assertIn("known_failure_modes_are_reported_without_private_text", payload["can_claim"])
        self.assertIn("private_real_history_answer_quality", payload["cannot_claim"])
        self.assertIn("quote_fidelity_without_clean_source_reopen", payload["cannot_claim"])
        self.assertIn("user_visible_recall_improvement", payload["cannot_claim"])
        self.assertIn("answer_usefulness_beyond_structural_proxy", payload["cannot_claim"])

    def test_benchmark_records_known_failure_modes(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
        )
        codes = {item["code"] for item in payload["known_failure_modes"]}

        self.assertIn("structural_proxy_not_answer_quality", codes)
        self.assertIn("clean_source_required_for_evidence", codes)
        self.assertIn("quote_fidelity_requires_clean_source_reopen", codes)
        self.assertIn("selected_slice_not_full_history", codes)

    def test_status_marks_scaffold_regression_as_lookup_required(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
        )

        if payload["metrics"]["term_coverage_delta"] < 0:
            self.assertEqual(payload["status"], "structural_proxy_ready_but_scaffold_regressed")
            self.assertIn(
                "question_aware_term_coverage_regressed",
                {item["code"] for item in payload["known_failure_modes"]},
            )

    def test_selection_reports_missing_link_or_theme_context(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=[
                {
                    "finding_kind": "question_candidate",
                    "fingerprint": "sf_question_only",
                    "question_short": "context continuity",
                    "source_refs": [source_ref("1")],
                    "concepts": ["context continuity"],
                }
            ],
        )
        codes = {item["code"] for item in payload["known_failure_modes"]}

        self.assertTrue(payload["status"].startswith("structural_proxy_ready"))
        self.assertTrue(payload["pack_selection"]["selected_lacks_link_or_theme_context"])
        self.assertIn("selected_rows_lack_link_or_theme_context", codes)

    def test_unbacked_rows_are_skipped(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=[
                {
                    "finding_kind": "question_candidate",
                    "fingerprint": "sf_unbacked",
                    "question_short": "unsupported",
                    "source_refs": [],
                }
            ],
        )

        self.assertEqual(payload["status"], "insufficient_real_history_packs")
        self.assertEqual(payload["eligible_row_count"], 0)
        self.assertEqual(payload["metrics"]["pack_count"], 0)
        self.assertIn(
            "insufficient_real_history_packs",
            {item["code"] for item in payload["known_failure_modes"]},
        )

    def test_private_text_is_debug_only(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
            include_private_text=True,
        )

        self.assertTrue(payload["private_text_emitted"])
        self.assertIn("debug_contexts", payload["packs"][0])


if __name__ == "__main__":
    unittest.main()
