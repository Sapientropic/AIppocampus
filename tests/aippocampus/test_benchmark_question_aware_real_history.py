from __future__ import annotations

import json
import sys
import tempfile
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


def answer_quality_review_rows() -> list[dict[str, Any]]:
    return [
        {
            "kind": "question_aware_answer_quality_review",
            "case_id": "private-case-1",
            "arm": "plain_baseline",
            "source_reopened": False,
            "answer_supported": False,
            "citation_correct": False,
            "answer_useful": False,
            "wrong_hint": True,
            "extra_verification_steps": 2,
            "answer_text": "PRIVATE ANSWER TEXT SHOULD NOT BE SERIALIZED",
            "source_text": "PRIVATE SOURCE TEXT SHOULD NOT BE SERIALIZED",
            "source_refs": [source_ref("1")],
            "local_path": str(REPO_ROOT / "private" / "source.md"),
        },
        {
            "kind": "question_aware_answer_quality_review",
            "case_id": "private-case-1",
            "arm": "question_aware_source_reopen",
            "source_reopened": True,
            "answer_supported": True,
            "citation_correct": True,
            "answer_useful": True,
            "wrong_hint": False,
            "extra_verification_steps": 0,
            "answer_text": "PRIVATE QUESTION AWARE ANSWER SHOULD NOT BE SERIALIZED",
            "source_text": "PRIVATE QUESTION AWARE SOURCE SHOULD NOT BE SERIALIZED",
            "source_refs": [source_ref("1")],
        },
        {
            "kind": "question_aware_answer_quality_review",
            "case_id": "private-case-2",
            "arm": "plain_baseline",
            "source_reopened": True,
            "answer_supported": True,
            "citation_correct": True,
            "answer_useful": True,
            "wrong_hint": False,
            "extra_verification_steps": 1,
        },
        {
            "kind": "question_aware_answer_quality_review",
            "case_id": "private-case-2",
            "arm": "question_aware_source_reopen",
            "source_reopened": True,
            "answer_supported": True,
            "citation_correct": True,
            "answer_useful": True,
            "wrong_hint": False,
            "extra_verification_steps": 1,
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
        self.assertIn("question_blind_term_coverage", payload["metrics"])
        self.assertGreater(
            payload["metrics"]["question_aware_over_question_blind_delta"],
            0.0,
        )
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
        self.assertTrue(payload["evaluation_design"]["same_selected_rows_for_plain_and_question_aware"])
        self.assertTrue(payload["evaluation_design"]["plain_baseline_receives_question_metadata"])
        self.assertTrue(payload["evaluation_design"]["question_blind_structural_baseline_measured"])
        self.assertFalse(payload["evaluation_design"]["question_blind_baseline_receives_question_metadata"])
        self.assertFalse(payload["evaluation_design"]["question_blind_is_true_retrieval_baseline"])
        self.assertFalse(payload["evaluation_design"]["selection_lift_measured"])
        self.assertFalse(payload["evaluation_design"]["answer_generation_measured_by_benchmark"])
        self.assertIn(
            "same_selected_rows_baseline",
            payload["evaluation_design"]["no_lift_reason_codes"],
        )
        self.assertIn(
            "final factual claims",
            payload["scaffold_vs_evidence"]["requires_clean_source_lookup"],
        )
        self.assertNotIn("How do I keep context after compaction?", rendered)
        self.assertNotIn("msg-private", rendered)
        self.assertNotIn("session:private", rendered)
        self.assertNotIn(str(REPO_ROOT), rendered)

    def test_question_blind_baseline_omits_question_and_theme_labels(self) -> None:
        context = benchmark.render_question_blind_source_terms(fixture_rows())

        self.assertIn("question_candidate", context)
        self.assertIn("source refs", context)
        self.assertNotIn("context after compaction", context)
        self.assertNotIn("Recurring question theme", context)
        self.assertNotIn("handoff calibration", context)

    def test_question_aware_terms_lift_over_question_blind_baseline(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=[
                {
                    "finding_kind": "question_candidate",
                    "fingerprint": "sf_unique_question",
                    "question_short": "activation boundary lift",
                    "question_text": "Where should activation boundary lift appear?",
                    "source_refs": [source_ref("1")],
                    "concepts": ["continuity"],
                }
            ],
        )

        self.assertLess(
            payload["metrics"]["question_blind_term_coverage"],
            payload["metrics"]["question_aware_term_coverage"],
        )
        self.assertGreater(
            payload["metrics"]["question_aware_over_question_blind_delta"],
            0.0,
        )
        self.assertIn(
            "question_aware_fields_add_structural_route_terms_over_question_blind_baseline",
            payload["can_claim"],
        )

    def test_frontier_concepts_counted_by_baseline_are_preserved_by_scaffold(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=[
                {
                    "finding_kind": "question_candidate",
                    "fingerprint": "sf_context_question",
                    "question_short": "context continuity",
                    "question_text": "How should continuity survive handoff?",
                    "source_refs": [source_ref("1")],
                    "concepts": ["context continuity"],
                },
                {
                    "finding_kind": "frontier_marker",
                    "fingerprint": "sf_context_frontier",
                    "frontier_type": "blocked",
                    "linked_question_short": "context continuity",
                    "boundary_reason": "Resume only after source refs survive.",
                    "source_refs": [source_ref("2")],
                    "concepts": [
                        "source refs",
                        "handoff",
                        "calibration",
                    ],
                },
            ],
        )

        self.assertEqual(payload["metrics"]["plain_term_coverage"], 1.0)
        self.assertEqual(payload["metrics"]["question_aware_term_coverage"], 1.0)
        self.assertEqual(payload["metrics"]["term_coverage_delta"], 0.0)
        self.assertNotIn(
            "question_aware_term_coverage_regressed",
            {item["code"] for item in payload["known_failure_modes"]},
        )

    def test_theme_terms_counted_by_baseline_are_preserved_by_scaffold(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=[
                {
                    "finding_kind": "theme_candidate",
                    "theme_cluster_id": "th_context_theme",
                    "theme_short": "handoff calibration",
                    "theme_label": "Recurring theme: handoff calibration",
                    "shared_concepts": [
                        "source refs",
                        "handoff calibration",
                    ],
                    "source_refs": [source_ref("1"), source_ref("2")],
                }
            ],
        )

        self.assertEqual(payload["metrics"]["plain_term_coverage"], 1.0)
        self.assertEqual(payload["metrics"]["question_aware_term_coverage"], 1.0)
        self.assertEqual(payload["metrics"]["term_coverage_delta"], 0.0)
        self.assertFalse(payload["pack_selection"]["selected_lacks_link_or_theme_context"])

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
        self.assertIn("true_no_question_aware_retrieval_baseline", payload["cannot_claim"])
        self.assertIn("answer_usefulness_beyond_structural_proxy", payload["cannot_claim"])

    def test_answer_quality_review_compares_paired_arms_without_overclaiming(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
            answer_quality_review_rows=answer_quality_review_rows(),
        )
        review = payload["answer_quality_review"]
        metrics = review["metrics"]

        self.assertEqual(
            review["status"],
            "selected_source_reopened_answer_quality_review_ready",
        )
        self.assertEqual(metrics["review_case_count"], 2)
        self.assertEqual(metrics["complete_comparison_case_count"], 2)
        self.assertEqual(metrics["plain_baseline_answer_useful_rate"], 0.5)
        self.assertEqual(metrics["question_aware_source_reopen_answer_useful_rate"], 1.0)
        self.assertEqual(metrics["answer_usefulness_delta"], 0.5)
        self.assertEqual(metrics["question_aware_source_reopened_rate"], 1.0)
        self.assertEqual(metrics["question_aware_wrong_hint_rate"], 0.0)
        self.assertEqual(metrics["mean_extra_verification_steps_delta"], -1.0)
        self.assertIn(
            "selected_source_reopened_answer_quality_review_recorded",
            payload["can_claim"],
        )
        self.assertIn("private_real_history_answer_quality", payload["cannot_claim"])
        self.assertIn("full_history_answer_quality", review["cannot_claim"])
        self.assertIn("case_hash", review["case_summaries"][0])
        self.assertNotIn("private-case-1", json.dumps(review, ensure_ascii=False))

    def test_answer_quality_review_output_is_public_safe(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
            answer_quality_review_rows=answer_quality_review_rows(),
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertFalse(payload["answer_quality_review"]["privacy"]["raw_answer_text_emitted"])
        self.assertFalse(payload["answer_quality_review"]["privacy"]["raw_source_text_emitted"])
        self.assertNotIn("PRIVATE ANSWER TEXT", rendered)
        self.assertNotIn("PRIVATE SOURCE TEXT", rendered)
        self.assertNotIn("session:private", rendered)
        self.assertNotIn(str(REPO_ROOT), rendered)

    def test_answer_quality_review_loads_jsonl_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "answer_quality_review.jsonl"
            review_path.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in answer_quality_review_rows()
                )
                + "\n",
                encoding="utf-8",
            )
            payload = benchmark.run_question_aware_real_history_benchmark(
                job_rows=fixture_rows(),
                answer_quality_review_path=review_path,
            )

        self.assertEqual(
            payload["answer_quality_review"]["status"],
            "selected_source_reopened_answer_quality_review_ready",
        )

    def test_answer_quality_review_reports_missing_pair_boundary(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
            answer_quality_review_rows=[
                {
                    "kind": "question_aware_answer_quality_review",
                    "case_id": "private-case-1",
                    "arm": "question_aware_source_reopen",
                    "source_reopened": True,
                    "answer_supported": True,
                    "citation_correct": True,
                    "answer_useful": True,
                }
            ],
        )
        review = payload["answer_quality_review"]

        self.assertEqual(review["status"], "answer_quality_review_incomplete")
        self.assertEqual(review["metrics"]["review_case_count"], 1)
        self.assertEqual(review["metrics"]["complete_comparison_case_count"], 0)
        self.assertIn("paired_answer_quality_review_missing", review["cannot_claim"])
        self.assertNotIn(
            "selected_source_reopened_answer_quality_review_recorded",
            payload["can_claim"],
        )

    def test_benchmark_records_known_failure_modes(self) -> None:
        payload = benchmark.run_question_aware_real_history_benchmark(
            job_rows=fixture_rows(),
        )
        codes = {item["code"] for item in payload["known_failure_modes"]}

        self.assertIn("structural_proxy_not_answer_quality", codes)
        self.assertIn("clean_source_required_for_evidence", codes)
        self.assertIn("quote_fidelity_requires_clean_source_reopen", codes)
        self.assertIn("selected_slice_not_full_history", codes)
        self.assertIn("plain_baseline_term_ceiling", codes)

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

    def test_public_shadow_fixture_compares_question_aware_source_reopen(self) -> None:
        payload = benchmark.run_question_aware_public_shadow_benchmark(
            fixture_path=REPO_ROOT
            / "benchmark_corpus"
            / "question_aware_public_shadow"
            / "fixture.json",
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(
            payload["kind"],
            "aippocampus_question_aware_public_shadow_benchmark",
        )
        self.assertEqual(payload["status"], "public_shadow_ready")
        self.assertEqual(payload["claim_level"], "public_replayable_shadow_fixture")
        self.assertGreaterEqual(payload["metrics"]["public_case_count"], 4)
        self.assertGreaterEqual(payload["metrics"]["negative_control_count"], 2)
        self.assertEqual(payload["metrics"]["negative_control_pass_count"], 2)
        self.assertEqual(
            {item["observed_skip_reason"] for item in payload["negative_controls"]},
            {"code_heavy", "noise"},
        )
        self.assertGreater(
            payload["metrics"]["question_aware_over_question_blind_delta"],
            0.0,
        )
        self.assertGreater(
            payload["metrics"]["answer_usefulness_delta"],
            0.0,
        )
        self.assertGreater(
            payload["metrics"]["manual_query_reduction_delta"],
            0.0,
        )
        self.assertEqual(
            payload["threshold_readout"]["dynamic_six_axis_threshold"]["false_merge_count"],
            0,
        )
        self.assertEqual(
            payload["threshold_readout"]["dynamic_six_axis_threshold"]["false_split_count"],
            0,
        )
        self.assertIn(
            "public_shadow_question_aware_source_reopen_comparison_recorded",
            payload["can_claim"],
        )
        self.assertIn(
            "public_shadow_selected_baseline_preregistered",
            payload["can_claim"],
        )
        self.assertIn(
            "public_shadow_materialization_review_evidence_recorded",
            payload["can_claim"],
        )
        prereg = payload["baseline_preregistration"]
        self.assertEqual(
            prereg["kind"],
            "question_aware_public_shadow_baseline_preregistration",
        )
        self.assertFalse(
            prereg["arms"]["question_blind_structural"]["true_retrieval_baseline"]
        )
        self.assertTrue(
            prereg["arms"]["no_question_retrieval_answer"]["true_retrieval_baseline"]
        )
        self.assertIn(
            "question_aware_over_question_blind_delta",
            prereg["primary_readouts"],
        )
        self.assertIn(
            "retrieval_recall_delta",
            prereg["primary_readouts"],
        )
        retrieval_baseline = payload["no_question_retrieval_answer_baseline"]
        self.assertEqual(
            retrieval_baseline["kind"],
            "question_aware_public_shadow_no_question_retrieval_answer_baseline",
        )
        self.assertEqual(retrieval_baseline["status"], "fair_baseline_shape_ready")
        self.assertFalse(
            retrieval_baseline["arms"]["no_question_retrieval_answer"][
                "question_metadata_visible"
            ]
        )
        self.assertTrue(
            retrieval_baseline["arms"]["question_aware_retrieval_answer"][
                "question_metadata_visible"
            ]
        )
        self.assertEqual(
            retrieval_baseline["retrieval_selection"]["no_question_retrieval_answer"][
                "forbidden_fields"
            ],
            [
                "question_text",
                "question_short",
                "linked_question_short",
                "linked_questions",
                "theme_short",
                "theme_label",
                "theme_cluster_id",
            ],
        )
        self.assertEqual(
            retrieval_baseline["metrics"]["no_question_retrieval_recall"],
            0.5,
        )
        self.assertEqual(
            retrieval_baseline["metrics"]["question_aware_retrieval_recall"],
            1.0,
        )
        self.assertEqual(
            retrieval_baseline["metrics"]["retrieval_recall_delta"],
            0.5,
        )
        self.assertEqual(
            payload["metrics"]["no_question_retrieval_recall"],
            0.5,
        )
        self.assertEqual(
            payload["metrics"]["retrieval_recall_delta"],
            0.5,
        )
        self.assertIn(
            "public_shadow_true_no_question_retrieval_baseline_shape_recorded",
            payload["can_claim"],
        )
        self.assertNotIn(
            "true_no_question_aware_retrieval_baseline",
            payload["cannot_claim"],
        )
        self.assertIn(
            "broad_no_question_aware_retrieval_baseline",
            payload["cannot_claim"],
        )
        review_evidence = payload["materialization_review_evidence"]
        self.assertEqual(
            review_evidence["status"],
            "public_shadow_review_evidence_ready",
        )
        self.assertEqual(
            review_evidence["reviewer_usefulness_categories"]["manual_search_reduction"][
                "status"
            ],
            "observed",
        )
        self.assertEqual(
            review_evidence["reviewer_usefulness_categories"]["wrong_route_drag"]["status"],
            "bounded",
        )
        self.assertEqual(
            review_evidence["reviewer_usefulness_categories"][
                "candidate_link_theme_materialization"
            ]["status"],
            "observed",
        )
        self.assertIn("private_real_history_answer_quality", payload["cannot_claim"])
        self.assertIn("broad_no_question_aware_retrieval_baseline", payload["cannot_claim"])
        self.assertIn("live_user_visible_recall_improvement", payload["cannot_claim"])
        self.assertIn(
            "private_history_materialization_quality",
            review_evidence["cannot_claim"],
        )
        calibration = payload["public_safe_calibration_readout"]
        self.assertEqual(
            calibration["kind"],
            "question_aware_public_safe_local_calibration_readout",
        )
        self.assertEqual(
            calibration["status"],
            "public_safe_local_calibration_ready",
        )
        self.assertEqual(
            calibration["metrics"][
                "missed_resurfacing_without_question_tracking_count"
            ],
            2,
        )
        self.assertEqual(calibration["metrics"]["stale_question_carryover_count"], 0)
        self.assertEqual(calibration["metrics"]["wrong_route_drag_count"], 0)
        self.assertEqual(calibration["metrics"]["noise_false_positive_count"], 0)
        github_248 = calibration["issue_readouts"]["github_248"]
        self.assertEqual(
            github_248["closeout_scope"],
            "public_safe_owner_closeout_only",
        )
        self.assertFalse(github_248["private_or_live_calibration_measured"])
        self.assertTrue(github_248["owner_closeout_eligible"])
        self.assertIn("issue_248_public_safe_owner_closeout", payload["can_claim"])
        self.assertIn("private_or_live_issue_248_closeout", payload["cannot_claim"])
        self.assertNotIn("issue_248_closeout", payload["cannot_claim"])
        self.assertIn(
            "stale_question_carryover",
            calibration["false_positive_classes"],
        )
        self.assertIn(
            "noise_or_code_promoted_to_question",
            calibration["false_positive_classes"],
        )
        self.assertIn(
            "missed_resurfacing_without_question_tracking",
            calibration["false_negative_classes"],
        )
        self.assertTrue(
            calibration["issue_readouts"]["github_1368"]["closeout_eligible"]
        )
        self.assertTrue(payload["issue_readouts"]["github_1368"]["closeout_eligible"])
        self.assertIn(
            "public_safe_question_tracking_calibration_classes_recorded",
            payload["can_claim"],
        )
        self.assertFalse(payload["privacy"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy"]["local_path_emitted"])
        self.assertNotIn("PUBLIC_SOURCE_TEXT_SENTINEL", rendered)
        self.assertNotIn(str(REPO_ROOT), rendered)


if __name__ == "__main__":
    unittest.main()
