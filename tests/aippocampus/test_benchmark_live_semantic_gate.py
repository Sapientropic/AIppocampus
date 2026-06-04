from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

import benchmark_live_semantic_gate as live_benchmark  # noqa: E402


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
        self.assertEqual(
            payload["metrics"]["continuation_language_metrics"]["zh"]["total_cases"],
            0,
        )
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
        with self.assertRaises(Exception):
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


if __name__ == "__main__":
    unittest.main()
