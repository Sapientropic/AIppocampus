from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

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
        self.assertEqual(payload["metrics"]["semantic_error_case_count"], 0)
        self.assertEqual(payload["metrics"]["semantic_decision_counts"], {})
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
                case_workers=2,
            )

        self.assertEqual(payload["status"], "sufficient")
        self.assertTrue(payload["quality_gate_ok"])
        self.assertEqual(payload["config"]["case_workers"], 2)
        self.assertFalse(payload["config"]["semantic_result_cache_enabled"])
        self.assertEqual(payload["metrics"]["total_cases"], 4)
        self.assertEqual(payload["metrics"]["semantic_model_call_count"], 3)
        self.assertEqual(payload["metrics"]["semantic_available_count"], 3)
        self.assertEqual(payload["metrics"]["semantic_error_case_count"], 0)
        self.assertEqual(payload["metrics"]["semantic_decision_counts"]["scent"], 2)
        self.assertEqual(payload["metrics"]["semantic_decision_counts"]["evidence"], 1)
        self.assertEqual(payload["metrics"]["semantic_evidence_allowed_count"], 1)
        self.assertEqual(payload["metrics"]["semantic_evidence_guarded_to_scent_count"], 0)
        self.assertEqual(payload["metrics"]["semantic_usage"]["total_tokens"], 360)
        self.assertEqual(payload["metrics"]["semantic_usage"]["cache_hit_rate"], 0.3)
        self.assertEqual(payload["metrics"]["semantic_latency_ms"]["count"], 3)
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
