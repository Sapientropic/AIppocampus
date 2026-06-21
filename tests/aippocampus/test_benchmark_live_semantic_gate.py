from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.aippocampus.import_path_helpers import import_benchmark_module

live_benchmark = import_benchmark_module("benchmark_live_semantic_gate")

class LiveSemanticGateBenchmarkTests(unittest.TestCase):
    def _write_corpus(self, corpus: Path) -> None:
        corpus.mkdir()
        messages = [
            {
                "message_id": "m1",
                "turn_id": "t1",
                "source_id": "src_demo",
                "source_line": 1,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "How do I debug list.sort returning None?",
                "_meta": {"category": "program and code"},
            },
            {
                "message_id": "m2",
                "turn_id": "t1",
                "source_id": "src_demo",
                "source_line": 2,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": "Use sorted(items) or remember that list.sort mutates in place.",
                "_meta": {"category": "program and code"},
            },
            {
                "message_id": "m3",
                "turn_id": "t2",
                "source_id": "src_demo",
                "source_line": 3,
                "role": "user",
                "phase": "",
                "turn_index": 2,
                "is_final": False,
                "text": "How should I handle missing dictionary keys?",
                "_meta": {"category": "program and code"},
            },
            {
                "message_id": "m4",
                "turn_id": "t2",
                "source_id": "src_demo",
                "source_line": 4,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 2,
                "is_final": True,
                "text": "Use dict.get(key, default) when missing keys are expected.",
                "_meta": {"category": "program and code"},
            },
        ]
        (corpus / "messages.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in messages),
            encoding="utf-8",
        )
        (corpus / "turns.jsonl").write_text(
            json.dumps({"source_id": "src_demo", "turn_count": 2}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

    def test_live_eval_skips_cleanly_without_semantic_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "sharegpt"
            self._write_corpus(corpus)
            with patch.object(live_benchmark.semantic, "semantic_gate_enabled", return_value=False):
                payload = live_benchmark.run_live_semantic_eval(
                    sharegpt_corpus_dir=corpus,
                    sharegpt_conversations=1,
                )

        self.assertEqual(payload["status"], "skipped_missing_semantic_backend")
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["metrics"]["total_cases"], 0)
        self.assertEqual(payload["metrics"]["semantic_available_count"], 0)
        self.assertEqual(payload["metrics"]["semantic_availability_rate"], 0.0)
        self.assertEqual(payload["metrics"]["semantic_error_case_count"], 0)
        self.assertEqual(payload["metrics"]["semantic_decision_counts"], {})
        self.assertEqual(payload["metrics"]["semantic_availability_reason_counts"], {})
        self.assertEqual(payload["metrics"]["semantic_usage"]["total_tokens"], 0)
        self.assertFalse(
            payload["issue_readouts"]["github_786"][
                "live_semantic_reopen_quality_measured"
            ]
        )
        self.assertEqual(
            payload["metrics"]["continuation_language_metrics"]["zh"]["total_cases"],
            0,
        )
        self.assertIn("live_semantic_model_quality", payload["cannot_claim"])

    def test_live_eval_reports_missing_sharegpt_corpus_as_not_ready(self) -> None:
        def fake_live_semantic(prompt: str, **kwargs) -> dict:
            self.fail("missing corpus should be diagnosed before semantic calls")

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-sharegpt"
            payload = live_benchmark.run_live_semantic_eval(
                sharegpt_corpus_dir=missing,
                sharegpt_conversations=1,
                semantic_gate_fn=fake_live_semantic,
            )

        raw = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertFalse(payload["quality_claim_attempted"])
        self.assertEqual(payload["status"], "missing_sharegpt_corpus")
        self.assertEqual(payload["diagnostic"]["reason_code"], "sharegpt_corpus_missing")
        self.assertIn("convert_to_aippocampus.py", payload["diagnostic"]["preparation_command"])
        self.assertIn("benchmark_corpus/output/sharegpt_coding_multiturn", raw)
        self.assertNotIn(str(missing), raw)
        self.assertIn("live_semantic_model_quality", payload["cannot_claim"])

    def test_live_eval_uses_prompt_hook_with_sanitized_report(self) -> None:
        seen_prompts: list[str] = []

        def fake_live_semantic(prompt: str, **kwargs) -> dict:
            seen_prompts.append(prompt)
            wants_evidence = "原始建议" in prompt
            return {
                "kind": "aippocampus_semantic_recall_gate",
                "available": True,
                "decision": "evidence" if wants_evidence else "scent",
                "confidence": 0.93 if wants_evidence else 0.88,
                "intent": "recall" if wants_evidence else "continuation",
                "query_aliases": ["list.sort", "dict.get"],
                "memory_scope": ["registered_threads"],
                "negative_contexts": [],
                "anti_personalization_risk": "low",
                "reasons": ["fake live semantic continuation"],
                "workers": [{"worker": "gate", "decision": "scent"}],
                "errors": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "prompt_cache_hit_tokens": 30,
                    "prompt_cache_miss_tokens": 70,
                },
                "cache": {"hit_rate": 0.3},
                "cached": False,
                "elapsed_ms": 42.0,
            }

        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "sharegpt"
            self._write_corpus(corpus)
            payload = live_benchmark.run_live_semantic_eval(
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=1,
                min_cases=4,
                semantic_gate_fn=fake_live_semantic,
                case_workers=1,
            )

        self.assertEqual(payload["status"], "sufficient")
        self.assertTrue(payload["quality_gate_ok"])
        self.assertEqual(payload["config"]["case_workers"], 1)
        self.assertFalse(payload["config"]["semantic_result_cache_enabled"])
        self.assertEqual(payload["metrics"]["total_cases"], 4)
        semantic_calls = payload["metrics"]["semantic_model_call_count"]
        self.assertGreater(semantic_calls, 0)
        self.assertEqual(payload["metrics"]["semantic_available_count"], semantic_calls)
        self.assertEqual(payload["metrics"]["semantic_availability_rate"], 1.0)
        self.assertEqual(payload["metrics"]["semantic_error_case_count"], 0)
        self.assertEqual(sum(payload["metrics"]["semantic_decision_counts"].values()), semantic_calls)
        self.assertLessEqual(payload["metrics"]["semantic_evidence_allowed_count"], semantic_calls)
        self.assertEqual(payload["metrics"]["semantic_evidence_guarded_to_scent_count"], 0)
        self.assertEqual(payload["metrics"]["semantic_usage"]["total_tokens"], 120 * semantic_calls)
        self.assertEqual(payload["metrics"]["semantic_usage"]["cache_hit_rate"], 0.3)
        self.assertEqual(payload["metrics"]["semantic_latency_ms"]["count"], semantic_calls)
        self.assertEqual(
            payload["metrics"]["continuation_language_metrics"]["zh"]["total_cases"],
            1,
        )
        self.assertEqual(
            payload["metrics"]["continuation_language_metrics"]["en"]["total_cases"],
            1,
        )
        self.assertEqual(payload["privacy_boundary"]["raw_prompt_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["semantic_aliases_emitted"], False)
        self.assertIn("semantic_error_kinds", payload["cases"][1])
        self.assertIn("semantic_availability_reason", payload["cases"][1])
        self.assertTrue(any("能接着我们之前关于" in prompt for prompt in seen_prompts))
        evidence_cases = [
            row
            for row in payload["cases"]
            if row["case_type"] == "sharegpt_coding_live_semantic_evidence_should_evidence"
        ]
        self.assertEqual(len(evidence_cases), 1)
        self.assertEqual(evidence_cases[0]["actual"], "evidence")
        self.assertGreater(evidence_cases[0]["evidence_count"], 0)
        self.assertNotIn("How do I debug", json.dumps(payload))
        self.assertNotIn("list.sort", json.dumps(payload))

    def test_live_eval_counts_semantic_evidence_to_source_required_route(self) -> None:
        def fake_live_semantic(prompt: str, **kwargs) -> dict:
            continuation = "能接着" in prompt or "continue" in prompt.casefold()
            wants_evidence = "原始建议" in prompt
            return {
                "kind": "aippocampus_semantic_recall_gate",
                "available": True,
                "decision": "evidence" if continuation or wants_evidence else "skip",
                "confidence": 0.93,
                "intent": (
                    "continuation"
                    if continuation
                    else "source_recall"
                    if wants_evidence
                    else "none"
                ),
                "query_aliases": ["list.sort", "dict.get"] if continuation or wants_evidence else [],
                "memory_scope": ["registered_threads"] if continuation or wants_evidence else [],
                "negative_contexts": [],
                "anti_personalization_risk": "low",
                "reasons": ["fake live semantic source route"],
                "workers": [{"worker": "gate", "decision": "evidence"}],
                "errors": [],
                "usage": {},
                "cache": {},
                "cached": False,
                "elapsed_ms": 42.0,
            }

        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "sharegpt"
            self._write_corpus(corpus)
            payload = live_benchmark.run_live_semantic_eval(
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=1,
                min_cases=4,
                semantic_gate_fn=fake_live_semantic,
                case_workers=1,
            )

        continuation_cases = [
            row
            for row in payload["cases"]
            if "live_semantic" in row["case_type"] and row["expected"] == "should_scent"
        ]
        self.assertEqual(len(continuation_cases), 2)
        self.assertTrue(all(row["actual"] == "scent" for row in continuation_cases))
        self.assertTrue(
            all(row["source_required_reopen_plan_ready"] for row in continuation_cases)
        )
        self.assertEqual(payload["metrics"]["semantic_evidence_guarded_to_scent_count"], 2)
        self.assertEqual(
            payload["metrics"]["semantic_evidence_to_source_required_route_count"], 2
        )
        self.assertEqual(
            payload["metrics"]["semantic_evidence_guarded_to_plain_scent_count"], 0
        )
        self.assertEqual(payload["metrics"]["paid_semantic_hit_count"], 2)
        self.assertEqual(payload["metrics"]["high_confidence_paid_semantic_hit_count"], 2)
        self.assertEqual(payload["metrics"]["paid_semantic_hit_to_source_reopen_rate"], 1.0)
        self.assertEqual(payload["metrics"]["source_reopen_after_semantic_hit_rate"], 1.0)
        self.assertEqual(payload["metrics"]["semantic_hit_user_visible_lift_rate"], 1.0)
        self.assertEqual(
            payload["metrics"]["paid_semantic_hit_guarded_to_plain_scent_count"], 0
        )
        self.assertEqual(
            payload["metrics"]["manual_query_invention_after_paid_semantic_hit_count"],
            0,
        )
        self.assertEqual(payload["metrics"]["useful_route_suppressed_count"], 0)
        self.assertEqual(payload["metrics"]["all_scent_collapse_rate"], 0.0)
        self.assertEqual(payload["metrics"]["overconservative_suppression_reason_counts"], {})
        self.assertFalse(
            payload["metrics"]["bounded_evidence_after_semantic_reopen_rate_measured"]
        )
        self.assertIsNone(
            payload["metrics"]["bounded_evidence_after_semantic_reopen_rate"]
        )
        readout = payload["issue_readouts"]["github_786"]
        self.assertTrue(readout["live_semantic_reopen_quality_measured"])
        self.assertEqual(readout["live_semantic_reopen_quality"], "source_required_reopen_route")
        self.assertEqual(readout["semantic_evidence_guarded_to_plain_scent_count"], 0)
        self.assertTrue(readout["live_semantic_reopen_closeout_eligible"])
        readout_201 = payload["issue_readouts"]["github_201"]
        self.assertTrue(readout_201["live_paid_semantic_route_actionability_measured"])
        self.assertEqual(readout_201["paid_semantic_hit_count"], 2)
        self.assertEqual(readout_201["paid_semantic_hit_to_source_reopen_rate"], 1.0)
        self.assertEqual(
            readout_201["manual_query_invention_after_paid_semantic_hit_count"],
            0,
        )
        self.assertEqual(
            readout_201["paid_semantic_hit_guarded_to_plain_scent_count"],
            0,
        )
        self.assertEqual(readout_201["semantic_hit_user_visible_lift_rate"], 1.0)
        self.assertEqual(readout_201["all_scent_collapse_rate"], 0.0)
        self.assertFalse(
            readout_201["bounded_evidence_after_semantic_reopen_rate_measured"]
        )
        self.assertTrue(readout_201["source_boundary_preserved"])
        self.assertTrue(
            readout_201["live_semantic_route_actionability_closeout_eligible"]
        )
        self.assertEqual(
            payload["metrics"]["continuation_language_metrics"]["zh"][
                "semantic_evidence_to_source_required_route_count"
            ],
            1,
        )
        self.assertEqual(
            payload["metrics"]["continuation_language_metrics"]["en"][
                "semantic_evidence_guarded_to_plain_scent_count"
            ],
            0,
        )

    def test_paid_semantic_metrics_count_manual_search_delegation(self) -> None:
        rows = [
            {
                "semantic_gate_called": True,
                "semantic_available": True,
                "semantic_decision": "evidence",
                "semantic_confidence": 0.94,
                "actual": "scent",
                "source_required_reopen_plan_ready": False,
                "source_reopen_manual_query_expected": None,
            },
            {
                "semantic_gate_called": True,
                "semantic_available": True,
                "semantic_decision": "evidence",
                "semantic_confidence": 0.91,
                "actual": "scent",
                "source_required_reopen_plan_ready": True,
                "source_reopen_manual_query_expected": True,
            },
            {
                "semantic_gate_called": True,
                "semantic_available": True,
                "semantic_decision": "evidence",
                "semantic_confidence": 0.88,
                "actual": "evidence",
                "source_required_reopen_plan_ready": False,
                "source_reopen_manual_query_expected": False,
            },
        ]

        metrics = live_benchmark.summarize_live_semantic_results(rows)

        self.assertEqual(metrics["paid_semantic_hit_count"], 2)
        self.assertEqual(metrics["high_confidence_paid_semantic_hit_count"], 2)
        self.assertEqual(metrics["paid_semantic_hit_to_source_reopen_rate"], 0.5)
        self.assertEqual(metrics["source_reopen_after_semantic_hit_rate"], 0.5)
        self.assertEqual(metrics["paid_semantic_hit_guarded_to_plain_scent_count"], 1)
        self.assertEqual(metrics["manual_query_invention_after_paid_semantic_hit_count"], 2)
        self.assertEqual(metrics["useful_route_suppressed_count"], 2)
        self.assertEqual(metrics["all_scent_collapse_rate"], 0.5)
        self.assertEqual(metrics["semantic_hit_user_visible_lift_rate"], 0.5)
        self.assertEqual(
            metrics["overconservative_suppression_reason_counts"],
            {
                "manual_query_expected_after_reopen_route": 1,
                "plain_scent_without_reopen_plan": 1,
            },
        )

    def test_live_eval_fails_quality_gate_when_live_semantic_never_available(self) -> None:
        def unavailable_semantic(prompt: str, **kwargs) -> dict:
            del prompt, kwargs
            return {
                "kind": "aippocampus_semantic_recall_gate",
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "availability_reason": "semantic_unavailable",
                "diagnostic": "invalid_worker_or_backend_unavailable",
                "query_aliases": [],
                "memory_scope": [],
                "negative_contexts": [],
                "reasons": ["semantic worker did not run"],
                "workers": [],
                "errors": [],
                "usage": {},
                "cached": False,
                "elapsed_ms": 2.0,
            }

        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "sharegpt"
            self._write_corpus(corpus)
            payload = live_benchmark.run_live_semantic_eval(
                sharegpt_corpus_dir=corpus,
                sharegpt_conversations=1,
                min_cases=4,
                min_surface_recall=0.0,
                semantic_gate_fn=unavailable_semantic,
                case_workers=1,
            )

        self.assertEqual(payload["status"], "insufficient_live_semantic_availability")
        self.assertFalse(payload["quality_gate_ok"])
        semantic_calls = payload["metrics"]["semantic_model_call_count"]
        self.assertGreater(semantic_calls, 0)
        self.assertEqual(payload["metrics"]["semantic_available_count"], 0)
        self.assertEqual(
            payload["metrics"]["semantic_availability_reason_counts"],
            {"semantic_unavailable": semantic_calls},
        )
        self.assertIn("live_semantic_model_quality", payload["cannot_claim"])

    def test_parse_workers_accepts_default_alias_and_rejects_unknown(self) -> None:
        self.assertEqual(live_benchmark.parse_workers("default"), live_benchmark.DEFAULT_WORKERS)
        self.assertEqual(live_benchmark.parse_workers("gate,default"), live_benchmark.DEFAULT_WORKERS)
        with self.assertRaises(argparse.ArgumentTypeError):
            live_benchmark.parse_workers("default,unknown")

    def test_live_eval_auto_parallelism_scales_with_conversation_count(self) -> None:
        self.assertEqual(
            live_benchmark.resolve_case_workers(
                sharegpt_conversations=100,
                case_workers=live_benchmark.DEFAULT_CASE_WORKERS,
            ),
            50,
        )
        self.assertEqual(
            live_benchmark.resolve_case_workers(sharegpt_conversations=20, case_workers=0),
            10,
        )
        self.assertEqual(
            live_benchmark.resolve_case_workers(sharegpt_conversations=100, case_workers=7),
            7,
        )

    def test_bounded_evidence_after_semantic_reopen_companion_measures_next_step(self) -> None:
        payload = live_benchmark.bounded_evidence_after_semantic_reopen_report()
        metrics = payload["metrics"]

        self.assertEqual(
            payload["kind"],
            "aippocampus_bounded_evidence_after_semantic_reopen_report",
        )
        self.assertTrue(payload["quality_gate_ok"])
        self.assertTrue(payload["observed_agent_behavior"])
        self.assertFalse(payload["runtime_policy_adoption_gate_ok"])
        self.assertGreaterEqual(metrics["provider_backed_semantic_route_count"], 1)
        self.assertGreaterEqual(metrics["semantic_reopen_attempt_count"], 1)
        self.assertGreaterEqual(metrics["semantic_reopen_success_count"], 1)
        self.assertGreaterEqual(metrics["bounded_evidence_after_semantic_reopen_count"], 1)
        self.assertGreaterEqual(metrics["answer_or_action_used_bounded_evidence_count"], 1)
        self.assertEqual(metrics["manual_query_invention_after_semantic_hit_count"], 0)
        self.assertEqual(metrics["bounded_evidence_false_positive_count"], 0)
        self.assertGreaterEqual(metrics["source_missing_or_budget_block_count"], 1)
        self.assertGreaterEqual(metrics["stale_conflict_privacy_high_risk_block_count"], 1)
        self.assertIn("model_only_semantic_output_as_evidence", payload["cannot_claim"])

if __name__ == "__main__":
    unittest.main()
