from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_longmemeval_v2_context as benchmark  # noqa: E402


class LongMemEvalV2ContextMappingTests(unittest.TestCase):
    def test_missing_files_return_skipped_payload_with_claim_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = benchmark.run_longmemeval_v2_context_mapping(
                questions_file=root / "missing_questions.jsonl",
                trajectories_file=root / "missing_trajectories.jsonl",
                case_limit=3,
            )

        self.assertEqual(payload["kind"], "aippocampus_longmemeval_v2_context_mapping")
        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["metrics"]["question_count"], 0)
        self.assertIn("longmemeval_v2_source_evidence_hit_rate", payload["cannot_claim"])
        self.assertIn("longmemeval_v2_answer_accuracy", payload["cannot_claim"])
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])

    def test_mapping_pilot_reports_sanitized_aggregate_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            questions = root / "questions.jsonl"
            trajectories = root / "trajectories.jsonl"
            self._write_jsonl(
                questions,
                [
                    {
                        "id": "traj-1",
                        "domain": "enterprise",
                        "environment": "workarena",
                        "question_type": "procedure",
                        "question": "RAW QUESTION TEXT",
                        "answer": "RAW ANSWER TEXT",
                        "eval_function": "exact_match",
                    },
                    {
                        "id": "question-web",
                        "domain": "web",
                        "environment": "webarena-reddit",
                        "question_type": "dynamic-environment",
                        "question": "ANOTHER RAW QUESTION",
                        "answer": "hidden",
                        "eval_function": "llm_judge",
                    },
                    {
                        "id": "question-missing",
                        "domain": "unknown",
                        "environment": "unmapped",
                        "question_type": "static-environment",
                        "question": "DO NOT LEAK",
                        "answer": "hidden",
                        "eval_function": "exact_match",
                    },
                ],
            )
            self._write_jsonl(
                trajectories,
                [
                    {
                        "id": "traj-1",
                        "domain": "enterprise",
                        "environment": "workarena",
                        "goal": "RAW TRAJECTORY GOAL",
                        "states": [
                            {
                                "state_index": 0,
                                "accessibility_tree": "RAW TREE",
                                "screenshot": "LOCAL_SCREENSHOT_SENTINEL/shot.png",
                                "action": "click raw",
                                "thought": "raw thought",
                            }
                        ],
                    },
                    {
                        "id": "web-a",
                        "domain": "web",
                        "environment": "webarena",
                        "goal": "WEB RAW A",
                        "states": [{"state_index": 0, "url": "https://example.invalid/a"}],
                    },
                    {
                        "id": "web-b",
                        "domain": "web",
                        "environment": "webarena",
                        "goal": "WEB RAW B",
                        "states": [{"state_index": 0, "url": "https://example.invalid/b"}],
                    },
                ],
            )

            payload = benchmark.run_longmemeval_v2_context_mapping(
                questions_file=questions,
                trajectories_file=trajectories,
                case_limit=5,
            )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "mapping_pilot_diagnostic")
        self.assertEqual(payload["metrics"]["question_count"], 3)
        self.assertEqual(payload["metrics"]["trajectory_count"], 3)
        self.assertEqual(payload["metrics"]["exact_id_match_count"], 1)
        self.assertEqual(payload["metrics"]["environment_candidate_coverage_count"], 2)
        self.assertEqual(payload["metrics"]["ambiguous_candidate_count"], 1)
        self.assertEqual(payload["metrics"]["missing_mapping_count"], 1)
        self.assertEqual(payload["metrics"]["aippocampus_continuity_context_pack_count"], 2)
        self.assertEqual(payload["metrics"]["aippocampus_non_lexical_guidance_changed_context_count"], 1)
        continuity_arm = payload["arms"]["aippocampus_continuity_context"]
        self.assertEqual(continuity_arm["mode"], "routing_only_continuity_guidance")
        self.assertEqual(continuity_arm["claim_permission"], "none")
        self.assertFalse(continuity_arm["activation_packet_is_fact_evidence"])
        self.assertIn("aippo_ficus_activation_packet", continuity_arm["input_layers"])
        self.assertEqual(payload["decision"]["source_evidence_scoring"], "not_supported_missing_gold_evidence_refs")
        self.assertEqual(payload["decision"]["answer_generation"], "not_run_requires_official_reader_harness")
        self.assertTrue(payload["decision"]["can_build_context_candidate_packs"])
        self.assertFalse(payload["decision"]["can_score_source_evidence_retrieval"])
        self.assertFalse(payload["decision"]["can_score_benchmark_grade_context_gathering"])
        self.assertEqual(
            [case["mapping_status"] for case in payload["cases"]],
            ["exact_id_match", "environment_pool_only", "missing_candidate_pool"],
        )

        dumped = json.dumps(payload, ensure_ascii=False)
        for forbidden in (
            "RAW QUESTION",
            "RAW ANSWER",
            "RAW TRAJECTORY",
            "RAW TREE",
            "LOCAL_SCREENSHOT_SENTINEL",
            "shot.png",
            "raw thought",
            "click raw",
        ):
            self.assertNotIn(forbidden, dumped)

    def test_runner_does_not_emit_fake_source_evidence_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            questions = root / "questions.jsonl"
            trajectories = root / "trajectories.jsonl"
            self._write_jsonl(
                questions,
                [
                    {
                        "id": "q1",
                        "domain": "web",
                        "environment": "webarena-cms",
                        "question_type": "static-environment",
                        "question": "Hidden question",
                        "answer": "Hidden answer",
                    }
                ],
            )
            self._write_jsonl(
                trajectories,
                [
                    {
                        "id": "t1",
                        "domain": "web",
                        "environment": "webarena",
                        "goal": "Hidden goal",
                        "states": [{"state_index": 0, "accessibility_tree": "Hidden tree"}],
                    }
                ],
            )

            payload = benchmark.run_longmemeval_v2_context_mapping(
                questions_file=questions,
                trajectories_file=trajectories,
            )

        metric_keys = set(payload["metrics"])
        self.assertNotIn("source_evidence_hit_rate_top5", metric_keys)
        self.assertNotIn("evidence_hit_rate_top5", metric_keys)
        self.assertNotIn("mrr", metric_keys)
        self.assertEqual(payload["metrics"]["question_evidence_ref_count"], 0)
        self.assertIn("benchmark_grade_context_gathering_score", payload["cannot_claim"])

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
