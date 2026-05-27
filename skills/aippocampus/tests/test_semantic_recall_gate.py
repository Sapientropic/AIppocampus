from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

import semantic_recall_gate as gate  # noqa: E402
from redaction_fixtures import FAKE_TEST_OPENAI_API_KEY, FAKE_TEST_SECRET_VALUE  # noqa: E402


def fake_response(payload: dict, usage: dict | None = None) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(payload, ensure_ascii=False),
                }
            }
        ],
        "usage": usage or {"total_tokens": 12},
    }


class SemanticRecallGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.registry_path = self.root / "registry" / "threads.json"
        self.registry_path.parent.mkdir()
        self.registry = {
            "schema_version": 1,
            "threads": [
                {
                    "thread_key": "session:aippocampus",
                    "title": "AIppocampus thread",
                    "project_label": "AIppocampus",
                    "anchor_titles": ["AIppocampus ambient recall continuity"],
                    "keywords": ["AIppocampus", "海马体记忆", "ambient recall", "working memory"],
                    "summary": "Hook-assisted semantic recall continuity work.",
                    "paths": {"workspace": str(self.workspace)},
                }
            ],
        }
        self.registry_path.write_text(json.dumps(self.registry, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parallel_workers_merge_multilingual_aliases(self) -> None:
        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            content = messages[-1]["content"]
            if "Decide whether" in content:
                return fake_response(
                    {
                        "decision": "scent",
                        "intent": "continuation",
                        "confidence": 0.86,
                        "query_aliases": ["AIppocampus", "external hippocampus"],
                        "memory_scope": ["registered_threads"],
                        "anti_personalization_risk": "low",
                        "reason": "The prompt paraphrases the memory-system thread.",
                    }
                )
            if "multilingual" in content or "paraphrase" in content:
                return fake_response(
                    {
                        "decision": "background_only",
                        "confidence": 0.7,
                        "query_aliases": ["海马体记忆", "ambient recall", "working memory"],
                        "anti_personalization_risk": "low",
                        "reason": "Generated cross-lingual aliases.",
                    }
                )
            return fake_response(
                {
                    "decision": "background_only",
                    "confidence": 0.65,
                    "memory_scope": ["current_project", "working_memory"],
                    "anti_personalization_risk": "low",
                    "reason": "Current project memory may be relevant.",
                }
            )

        result = gate.run_semantic_gate(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["decision"], "scent")
        self.assertIn("AIppocampus", result["query_aliases"])
        self.assertIn("海马体记忆", result["query_aliases"])
        self.assertIn("registered_threads", result["memory_scope"])
        self.assertEqual(result["anti_personalization_risk"], "low")

    def test_semantic_gate_payload_keeps_stable_catalog_before_variable_prompt(self) -> None:
        payload = gate.catalog_payload(
            prompt="这次继续之前的海马体记忆工作。",
            cwd=self.workspace,
            registry=self.registry,
            associations={"terms": {}},
            working_memory=[],
            semantic_triggers_path=None,
        )
        payload_keys = list(payload.keys())

        self.assertLess(payload_keys.index("memory_catalog"), payload_keys.index("prompt"))
        self.assertLess(payload_keys.index("trigger_catalog"), payload_keys.index("prompt"))

        worker_payload = json.loads(gate.worker_prompt("gate", payload))
        worker_keys = list(worker_payload.keys())
        self.assertLess(worker_keys.index("input"), worker_keys.index("task"))
        self.assertLess(worker_keys.index("input"), worker_keys.index("output_schema"))
        self.assertLess(worker_keys.index("output_schema"), worker_keys.index("task"))

    def test_semantic_gate_reports_aggregate_deepseek_cache_metrics(self) -> None:
        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            del messages, api_key, model, base_url, max_tokens, timeout, temperature
            return fake_response(
                {
                    "decision": "background_only",
                    "confidence": 0.7,
                    "anti_personalization_risk": "low",
                    "reason": "cache telemetry",
                },
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 1,
                    "total_tokens": 11,
                    "prompt_cache_hit_tokens": 8,
                    "prompt_cache_miss_tokens": 2,
                },
            )

        result = gate.run_semantic_gate(
            "那个海马体继续一下",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertEqual(result["usage"]["prompt_cache_hit_tokens"], 24)
        self.assertEqual(result["usage"]["prompt_cache_miss_tokens"], 6)
        self.assertEqual(result["cache"]["hit_rate"], 0.8)

    def test_secret_like_prompt_skips_without_calling_model(self) -> None:
        def chat_fn(*args, **kwargs):
            raise AssertionError("model should not be called for secret-like prompts")

        result = gate.run_semantic_gate(
            f"api_key={FAKE_TEST_OPENAI_API_KEY}",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["decision"], "skip")
        self.assertIn("secret", " ".join(result["reasons"]))

    def test_secret_assignment_is_redacted_when_prompt_has_semantic_content(self) -> None:
        seen_prompts: list[str] = []

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            seen_prompts.append(messages[-1]["content"])
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.75,
                    "query_aliases": ["海马体记忆"],
                    "anti_personalization_risk": "low",
                    "reason": "redaction test",
                }
            )

        result = gate.run_semantic_gate(
            f"用这个 token={FAKE_TEST_SECRET_VALUE} 继续海马体记忆配置吗？",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertTrue(result["available"])
        self.assertTrue(result["secret_policy"]["redacted"])
        self.assertFalse(result["secret_policy"]["hard_block"])
        self.assertTrue(seen_prompts)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, "\n".join(seen_prompts))
        self.assertIn("<redacted:secret>", "\n".join(seen_prompts))

    def test_private_key_block_still_hard_blocks(self) -> None:
        def chat_fn(*args, **kwargs):
            raise AssertionError("model should not be called for private keys")

        private_key_block = "\n".join([
            "看看这个",
            "-----" + "BEGIN PRIVATE KEY" + "-----",
            "abc",
            "-----" + "END PRIVATE KEY" + "-----",
        ])

        result = gate.run_semantic_gate(
            private_key_block,
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["decision"], "skip")
        self.assertTrue(result["secret_policy"]["hard_block"])

    def test_cache_reuses_prior_semantic_decision(self) -> None:
        calls = {"count": 0}

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            calls["count"] += 1
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.8,
                    "query_aliases": ["AIppocampus"],
                    "anti_personalization_risk": "low",
                    "reason": "cached test",
                }
            )

        cache = self.root / "semantic_recall_cache.json"
        first = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            cache_path=cache,
            api_key="test-key",
            chat_fn=chat_fn,
        )
        second = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            cache_path=cache,
            api_key="test-key",
            chat_fn=chat_fn,
        )

        self.assertEqual(first["decision"], "scent")
        self.assertEqual(second["decision"], "scent")
        self.assertTrue(second["cached"])
        self.assertEqual(calls["count"], 3)

    def test_cache_write_error_is_reported_without_blocking_gate(self) -> None:
        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.8,
                    "query_aliases": ["AIppocampus"],
                    "anti_personalization_risk": "low",
                    "reason": "cache write warning test",
                }
            )

        with patch.object(gate, "write_cache", side_effect=OSError("readonly cache")):
            result = gate.run_semantic_gate(
                "脑内续接器",
                cwd=self.workspace,
                registry=self.registry,
                registry_path=self.registry_path,
                cache_path=self.root / "semantic_recall_cache.json",
                api_key="test-key",
                chat_fn=chat_fn,
            )

        self.assertTrue(result["available"])
        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["warnings"][0]["stage"], "cache_write")
        self.assertIn("readonly cache", result["warnings"][0]["message"])


if __name__ == "__main__":
    unittest.main()
