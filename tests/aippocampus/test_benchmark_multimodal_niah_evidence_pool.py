from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
):
    sys.path.insert(0, str(_path))

import benchmark_multimodal_niah_evidence_pool as benchmark  # noqa: E402


class MultimodalNiahEvidencePoolBenchmarkTests(unittest.TestCase):
    def test_fixture_declares_fixed_pools_with_ground_truth_and_distractors(self) -> None:
        fixture = benchmark.load_fixture()
        source_fixture = benchmark.load_source_fixture(fixture)
        report = benchmark.validate_fixture(fixture, source_fixture)

        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["schema_version"],
            "aippocampus.multimodal_niah_evidence_pool_fixture.v1",
        )
        self.assertEqual(report["case_count"], 4)
        self.assertEqual(report["source_fixture_id"], "public_multimodal_corpus_v1")
        self.assertEqual(set(report["pool_sizes"]), {3, 4, 5})
        self.assertEqual(report["expected_failure_case_count"], 0)

        for case in report["cases"]:
            self.assertTrue(set(case["ground_truth_evidence_ids"]) <= set(case["pool_evidence_ids"]))
            self.assertGreater(len(case["distractor_evidence_ids"]), 0)

    def test_pool_construction_is_deterministic_and_reproducible(self) -> None:
        fixture = benchmark.load_fixture()
        source_fixture = benchmark.load_source_fixture(fixture)

        first = benchmark.build_pools(fixture, source_fixture)
        second = benchmark.build_pools(fixture, source_fixture)

        self.assertEqual(first, second)
        self.assertEqual(
            first["niah-conflict-final-bill-stale-failure"]["pool_evidence_ids"],
            [
                "msrc-calendar-001",
                "msrc-bill-001",
                "msrc-email-001",
                "msrc-receipt-001",
            ],
        )

    def test_report_scores_answer_synthesis_under_supplied_pool_not_retrieval(self) -> None:
        payload = benchmark.run_benchmark(source_reopen_mode="disabled")

        self.assertEqual(payload["kind"], "aippocampus_multimodal_niah_evidence_pool_benchmark")
        self.assertEqual(payload["schema_version"], 2)
        self.assertTrue(payload["ok"], payload)
        self.assertTrue(payload["claim_boundary"]["retrieval_not_scored"])
        self.assertEqual(payload["tracks"]["source_reopen"]["status"], "skipped_provider_not_configured")

        metrics = payload["metrics"]
        for key in {
            "niah_observed_answerer_case_count",
            "deterministic_fixture_only_case_count",
            "pool_ground_truth_coverage_rate",
            "answer_correctness",
            "source_selection_accuracy",
            "source_anchor_citation_accuracy",
            "unsupported_claim_rate",
            "abstention_accuracy",
            "stale_or_conflicting_distractor_selection_rate",
            "ambiguous_currentness_reopen_or_abstain_rate",
            "prompt_ground_truth_leak_count",
            "retrieval_quality_claimed",
            "provider_unavailable_blocker_count",
            "raw_media_bytes_public_reported_count",
            "absolute_path_leak_count",
        }:
            self.assertIn(key, metrics)
        for key in {
            "pool_ground_truth_coverage_rate",
            "answer_correctness",
            "source_selection_accuracy",
            "source_anchor_citation_accuracy",
            "unsupported_claim_rate",
            "abstention_accuracy",
            "stale_or_conflicting_distractor_selection_rate",
            "ambiguous_currentness_reopen_or_abstain_rate",
        }:
            self.assertIn(key, payload["rate_estimates"])

        self.assertEqual(metrics["niah_observed_answerer_case_count"], 0)
        self.assertEqual(metrics["deterministic_fixture_only_case_count"], 4)
        self.assertEqual(metrics["pool_ground_truth_coverage_rate"], 1.0)
        self.assertEqual(metrics["answer_correctness"], 1.0)
        self.assertEqual(metrics["source_selection_accuracy"], 1.0)
        self.assertEqual(metrics["source_anchor_citation_accuracy"], 1.0)
        self.assertEqual(metrics["unsupported_claim_rate"], 0.0)
        self.assertEqual(metrics["abstention_accuracy"], 1.0)
        self.assertEqual(metrics["stale_or_conflicting_distractor_selection_rate"], 0.0)
        self.assertEqual(metrics["ambiguous_currentness_reopen_or_abstain_rate"], 0.0)
        self.assertEqual(metrics["prompt_ground_truth_leak_count"], 0)
        self.assertFalse(metrics["retrieval_quality_claimed"])
        self.assertEqual(metrics["provider_unavailable_blocker_count"], 0)
        self.assertEqual(metrics["raw_media_bytes_public_reported_count"], 0)
        self.assertEqual(metrics["absolute_path_leak_count"], 0)
        self.assertEqual(payload["conflict_decisions"]["current_source_selected_count"], 1)
        self.assertEqual(payload["conflict_decisions"]["needs_source_reopen_count"], 0)
        self.assertEqual(
            payload["conflict_decisions"]["stale_or_conflicting_distractor_selection_count"],
            0,
        )

        by_id = {case["case_id"]: case for case in payload["cases"]}
        failure = by_id["niah-conflict-final-bill-stale-failure"]
        self.assertTrue(failure["ground_truth_present"])
        self.assertTrue(failure["input_stale_or_conflicting_distractor_selected"])
        self.assertFalse(failure["stale_or_conflicting_distractor_selected"])
        self.assertTrue(failure["source_selection_correct"])
        self.assertEqual(failure["input_selected_evidence_ids"], ["msrc-email-001"])
        self.assertEqual(failure["selected_evidence_ids"], ["msrc-bill-001"])
        self.assertEqual(failure["cited_source_anchor_ids"], ["bill-001:total"])
        self.assertEqual(failure["selection_decision"], "prefer_current_source")
        self.assertEqual(
            failure["currentness_decision"],
            "unique_current_source_from_metadata",
        )
        self.assertIn("source_metadata_currentness_supported", failure["selection_reason_codes"])
        self.assertIsNone(failure["failure_mode"])

    def test_ambiguous_conflict_currentness_requires_reopen_instead_of_guessing(self) -> None:
        fixture = benchmark.load_fixture()
        source_fixture = benchmark.load_source_fixture(fixture)
        sources = benchmark._source_index(copy.deepcopy(source_fixture))
        qa_by_id = benchmark._qa_index(source_fixture)
        for source_id in ("msrc-email-001", "msrc-bill-001"):
            sources[source_id] = dict(sources[source_id])
            sources[source_id]["captured_at"] = "2026-05-01T08:30:00Z"
            sources[source_id]["authority_level"] = "user_message_source"
        ambiguous = {
            "case_id": "niah-conflict-currentness-ambiguous",
            "corpus_case_id": "mmc-conflict-final-bill",
            "query_shape": "conflict_resolution",
            "pool_size": 2,
            "ground_truth_evidence_ids": ["msrc-bill-001"],
            "distractor_evidence_ids": ["msrc-email-001"],
            "pool_evidence_ids": ["msrc-email-001", "msrc-bill-001"],
            "input_selected_evidence_ids": ["msrc-email-001"],
            "selected_evidence_ids": [],
            "cited_source_anchor_ids": [],
            "stale_or_conflicting_distractor_ids": ["msrc-email-001"],
            "expected_answer_state": "needs_source_reopen",
            "selected_answer_state": "needs_source_reopen",
            "answer_correct": True,
        }

        row = benchmark._evaluate_case(
            ambiguous,
            corpus_case=qa_by_id["mmc-conflict-final-bill"],
            sources=sources,
        )
        metrics, _ = benchmark._metrics([row])

        self.assertEqual(row["selection_decision"], "needs_source_reopen")
        self.assertEqual(row["currentness_decision"], "ambiguous_currentness")
        self.assertTrue(row["needs_source_reopen"])
        self.assertEqual(row["selected_evidence_ids"], [])
        self.assertFalse(row["stale_or_conflicting_distractor_selected"])
        self.assertEqual(metrics["needs_source_reopen_rate"], 1.0)
        self.assertEqual(metrics["stale_or_conflicting_distractor_selection_rate"], 0.0)

    def test_later_weaker_conflict_source_requires_reopen_instead_of_winning(self) -> None:
        fixture = benchmark.load_fixture()
        source_fixture = benchmark.load_source_fixture(fixture)
        sources = benchmark._source_index(copy.deepcopy(source_fixture))
        qa_by_id = benchmark._qa_index(source_fixture)
        sources["msrc-email-001"] = dict(sources["msrc-email-001"])
        sources["msrc-email-001"]["captured_at"] = "2026-05-03T08:30:00Z"

        conflict = {
            "case_id": "niah-conflict-later-weaker-source",
            "corpus_case_id": "mmc-conflict-final-bill",
            "query_shape": "conflict_resolution",
            "pool_size": 2,
            "ground_truth_evidence_ids": ["msrc-bill-001"],
            "distractor_evidence_ids": ["msrc-email-001"],
            "pool_evidence_ids": ["msrc-email-001", "msrc-bill-001"],
            "input_selected_evidence_ids": ["msrc-email-001"],
            "selected_evidence_ids": [],
            "cited_source_anchor_ids": [],
            "stale_or_conflicting_distractor_ids": ["msrc-email-001"],
            "expected_answer_state": "needs_source_reopen",
            "selected_answer_state": "needs_source_reopen",
            "answer_correct": True,
        }

        row = benchmark._evaluate_case(
            conflict,
            corpus_case=qa_by_id["mmc-conflict-final-bill"],
            sources=sources,
        )

        self.assertEqual(row["selection_decision"], "needs_source_reopen")
        self.assertEqual(row["currentness_decision"], "authority_time_conflict")
        self.assertTrue(row["needs_source_reopen"])
        self.assertEqual(row["selected_evidence_ids"], [])
        self.assertFalse(row["stale_or_conflicting_distractor_selected"])

    def test_answerer_replay_scores_observed_fixed_reader_without_scoring_retrieval(self) -> None:
        payload = benchmark.run_benchmark(answerer_replay=True)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["config"]["answerer_replay"], True)
        answerer_replay = payload["tracks"]["observed_answerer_replay"]
        derived_text_pool = payload["tracks"]["derived_text_pool"]
        self.assertEqual(answerer_replay["status"], "scored")
        self.assertEqual(answerer_replay["provider_route"], "fixed_reader_replay")
        self.assertEqual(derived_text_pool["metrics"]["niah_observed_answerer_case_count"], 0)
        self.assertEqual(derived_text_pool["metrics"]["deterministic_fixture_only_case_count"], 4)
        self.assertEqual(
            answerer_replay["claim_boundary"]["measures"],
            "observed_answerer_source_selection_citation_conflict_and_abstention",
        )
        self.assertTrue(answerer_replay["claim_boundary"]["retrieval_not_scored"])
        self.assertIn("retrieval_quality", answerer_replay["claim_boundary"]["cannot_claim"])

        metrics = payload["metrics"]
        self.assertEqual(metrics["niah_observed_answerer_case_count"], 6)
        self.assertEqual(metrics["deterministic_fixture_only_case_count"], 4)
        self.assertEqual(metrics["answer_correctness"], 1.0)
        self.assertEqual(metrics["source_selection_accuracy"], 1.0)
        self.assertEqual(metrics["source_anchor_citation_accuracy"], 1.0)
        self.assertEqual(metrics["stale_or_conflicting_distractor_selection_rate"], 0.0)
        self.assertEqual(metrics["ambiguous_currentness_reopen_or_abstain_rate"], 1.0)
        self.assertEqual(metrics["unsupported_claim_rate"], 0.0)
        self.assertEqual(metrics["abstention_accuracy"], 1.0)
        self.assertEqual(metrics["prompt_ground_truth_leak_count"], 0)
        self.assertFalse(metrics["retrieval_quality_claimed"])
        self.assertEqual(metrics["provider_unavailable_blocker_count"], 0)
        self.assertEqual(metrics["raw_media_bytes_public_reported_count"], 0)
        self.assertEqual(metrics["absolute_path_leak_count"], 0)

        by_id = {case["case_id"]: case for case in answerer_replay["cases"]}
        self.assertEqual(
            set(by_id),
            {
                "ground_truth_present_selection",
                "stale_conflict_repair",
                "ambiguous_currentness_reopen",
                "unsupported_visual_detail",
                "prompt_leakage_guard",
                "retrieval_not_scored_guard",
            },
        )
        self.assertEqual(by_id["stale_conflict_repair"]["selected_evidence_ids"], ["msrc-bill-001"])
        self.assertTrue(by_id["stale_conflict_repair"]["input_stale_or_conflicting_distractor_selected"])
        self.assertFalse(by_id["stale_conflict_repair"]["stale_or_conflicting_distractor_selected"])
        self.assertEqual(
            by_id["ambiguous_currentness_reopen"]["selected_answer_state"],
            "needs_source_reopen",
        )
        self.assertTrue(by_id["ambiguous_currentness_reopen"]["needs_source_reopen"])
        self.assertTrue(by_id["unsupported_visual_detail"]["abstention_correct"])
        self.assertFalse(by_id["retrieval_not_scored_guard"]["retrieval_quality_scored"])

        serialized_prompt_inputs = json.dumps(
            [case["agent_visible_prompt"] for case in answerer_replay["cases"]],
            ensure_ascii=False,
        )
        forbidden_fragments = [
            "ground_truth_evidence_ids",
            "expected_answer",
            "answer_correct",
            "failure_mode",
            "hidden_scoring_metadata",
            "msrc-bill-001",
            "Marigold Gallery",
        ]
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, serialized_prompt_inputs)

    def test_answerer_replay_prompt_leakage_guard_counts_scoring_metadata(self) -> None:
        fixture = benchmark.load_fixture()
        fixture["observed_answerer_replay_cases"][0]["agent_visible_prompt"] = (
            "ground_truth_evidence_ids msrc-img-001 answer_correct hidden_scoring_metadata"
        )
        source_fixture = benchmark.load_source_fixture(fixture)

        payload = benchmark.run_benchmark(
            fixture_payload=fixture,
            source_fixture_payload=source_fixture,
            answerer_replay=True,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["metrics"]["prompt_ground_truth_leak_count"], 1)
        self.assertIn(
            "answerer_prompt_ground_truth_leak",
            payload["tracks"]["observed_answerer_replay"]["blocker_codes"],
        )

    def test_validation_rejects_input_selection_outside_supplied_pool(self) -> None:
        fixture = benchmark.load_fixture()
        source_fixture = benchmark.load_source_fixture(fixture)
        fixture["cases"][1]["input_selected_evidence_ids"] = ["not-a-source"]

        report = benchmark.validate_fixture(fixture, source_fixture)

        self.assertFalse(report["ok"])
        self.assertIn("input_selection_outside_supplied_pool", report["blocker_codes"])

    def test_empty_selected_sources_are_not_reopenable(self) -> None:
        self.assertFalse(benchmark._has_reopenable_sources([], {}))

    def test_source_reopen_mode_checks_original_anchors_without_claiming_live_model_quality(self) -> None:
        payload = benchmark.run_benchmark(source_reopen_mode="deterministic_fixture")

        source_reopen = payload["tracks"]["source_reopen"]
        self.assertEqual(source_reopen["status"], "scored")
        self.assertEqual(source_reopen["provider_route"], "deterministic_fixture")
        self.assertEqual(source_reopen["metrics"]["ground_truth_source_reopen_rate"], 1.0)
        self.assertIn("live_vision_model_quality", payload["cannot_claim"])
        self.assertIn("atm_bench_hard_score", payload["cannot_claim"])

    def test_default_report_sanitizes_fixture_text_answers_and_local_paths(self) -> None:
        payload = benchmark.run_benchmark(source_reopen_mode="deterministic_fixture")

        self.assertFalse(payload["privacy_boundary"]["raw_questions_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_answers_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_fixture_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Grace", serialized)
        self.assertNotIn("Marigold Gallery", serialized)
        self.assertNotIn("512", serialized)
        self.assertNotIn(str(REPO_ROOT), serialized)

    def test_fixture_validation_rejects_pool_without_ground_truth_evidence(self) -> None:
        fixture = benchmark.load_fixture()
        source_fixture = benchmark.load_source_fixture(fixture)
        fixture["cases"][0]["pool_evidence_ids"] = ["msrc-email-001", "msrc-receipt-001", "msrc-bill-001"]

        report = benchmark.validate_fixture(fixture, source_fixture)

        self.assertFalse(report["ok"])
        self.assertIn("pool_missing_ground_truth_evidence", report["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
