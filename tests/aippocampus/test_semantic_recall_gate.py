from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import semantic_cue_cache as cues  # noqa: E402
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
        self.registry_path.write_text(
            json.dumps(self.registry, ensure_ascii=False), encoding="utf-8"
        )
        self.old_route_env = {
            name: os.environ.get(name)
            for name in [
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV",
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON",
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID",
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING",
                "AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND",
                "LOCAL_SEMANTIC_TEST_KEY",
            ]
        }
        for name in self.old_route_env:
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        for name, value in self.old_route_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
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

    def test_semantic_gate_payload_adds_prompt_relevant_catalog_after_prompt(self) -> None:
        registry = {"schema_version": 1, "threads": []}
        for idx in range(35):
            registry["threads"].append(
                {
                    "thread_key": f"session:filler-{idx}",
                    "project_label": "AIppocampus",
                    "anchor_titles": [f"filler topic {idx}"],
                    "keywords": [f"filler-{idx}"],
                    "summary": f"Filler memory surface {idx}.",
                    "paths": {"workspace": str(self.workspace)},
                }
            )
        registry["threads"].append(
            {
                "thread_key": "session:target",
                "project_label": "AIppocampus",
                "anchor_titles": ["rare semantic marker continuation"],
                "keywords": ["raresemanticmarker", "continuation target"],
                "summary": "The target memory that should survive catalog truncation.",
                "paths": {"workspace": str(self.workspace)},
            }
        )

        payload = gate.catalog_payload(
            prompt="继续 raresemanticmarker 这条线索",
            cwd=self.workspace,
            registry=registry,
            associations={"terms": {}},
            working_memory=[],
            semantic_triggers_path=None,
        )

        payload_keys = list(payload.keys())
        self.assertLess(payload_keys.index("memory_catalog"), payload_keys.index("prompt"))
        self.assertLess(payload_keys.index("trigger_catalog"), payload_keys.index("prompt"))
        self.assertGreater(payload_keys.index("prompt_relevant_catalog"), payload_keys.index("prompt"))
        self.assertEqual(len(payload["memory_catalog"]), 36)
        self.assertIn(
            "session:target",
            [item["thread_key"] for item in payload["memory_catalog"]],
        )
        self.assertLessEqual(
            len(payload["prompt_relevant_catalog"]),
            gate.DEFAULT_MAX_PROMPT_RELEVANT_CATALOG_ITEMS,
        )
        self.assertIn(
            "session:target",
            [item["thread_key"] for item in payload["prompt_relevant_catalog"]],
        )

    def test_semantic_gate_payload_adds_prompt_relevant_triggers_after_prompt(self) -> None:
        triggers_path = self.root / "semantic_triggers.jsonl"
        rows = []
        for idx in range(90):
            rows.append(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "title": f"filler trigger {idx}",
                    "aliases": [f"filler-trigger-{idx}"],
                    "status": "active",
                    "confidence": 0.9,
                }
            )
        rows.append(
            {
                "kind": "aippocampus_semantic_trigger",
                "title": "rare trigger target",
                "aliases": ["raresidecartrigger"],
                "status": "active",
                "confidence": 0.9,
            }
        )
        triggers_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

        payload = gate.catalog_payload(
            prompt="继续 raresidecartrigger 这条线索",
            cwd=self.workspace,
            registry=self.registry,
            associations={"terms": {}},
            working_memory=[],
            semantic_triggers_path=triggers_path,
        )

        payload_keys = list(payload.keys())
        self.assertGreater(payload_keys.index("prompt_relevant_triggers"), payload_keys.index("prompt"))
        self.assertEqual(len(payload["trigger_catalog"]), 91)
        self.assertIn(
            "rare trigger target",
            [item["title"] for item in payload["trigger_catalog"]],
        )
        self.assertLessEqual(
            len(payload["prompt_relevant_triggers"]),
            gate.DEFAULT_MAX_PROMPT_RELEVANT_TRIGGER_ITEMS,
        )
        self.assertIn(
            "rare trigger target",
            [item["title"] for item in payload["prompt_relevant_triggers"]],
        )

    def test_prompt_relevant_triggers_ignore_short_single_entity_overlap(self) -> None:
        triggers_path = self.root / "short_entity_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "title": "AIppocampus Atlas recall gate",
                    "aliases": ["AIppocampus Atlas", "Atlas recall gate"],
                    "status": "active",
                    "confidence": 0.9,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(
            gate.prompt_relevant_triggers(
                prompt="把 Atlas 这个模块接一下",
                semantic_triggers_path=triggers_path,
            ),
            [],
        )
        self.assertTrue(
            gate.prompt_relevant_triggers(
                prompt="AIppocampus Atlas recall gate 这条线继续",
                semantic_triggers_path=triggers_path,
            )
        )

    def test_reviewed_trigger_keeps_late_domain_aliases_prompt_relevant(self) -> None:
        triggers_path = self.root / "semantic_triggers.jsonl"
        aliases = [f"filler alias {index}" for index in range(18)]
        aliases.extend(["self-continuity", "生命还能变成什么"])
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "title": "AIppocampus continuity trigger",
                    "aliases": aliases,
                    "status": "active",
                    "confidence": 0.9,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        relevant = gate.prompt_relevant_triggers(
            prompt="self-continuity quote 那个方向找回。",
            semantic_triggers_path=triggers_path,
        )

        self.assertTrue(relevant)
        self.assertIn("self-continuity", relevant[0]["aliases"])

    def test_semantic_gate_payload_includes_active_multilingual_cue_cache(self) -> None:
        cues_path = self.root / "semantic_cues.jsonl"
        semantic_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.88,
            "query_aliases": ["memoria externa", "外置海马体", "внешний гиппокамп"],
        }
        source_refs = [{"thread_key": "session:aippocampus", "message_id": "m1"}]
        for _ in range(2):
            cues.record_semantic_cue_hits(
                cues_path,
                prompt="¿Seguimos con la memoria externa?",
                semantic_result=semantic_result,
                source_refs=source_refs,
                route="semantic_gate",
            )

        payload = gate.catalog_payload(
            prompt="¿Seguimos con la memoria externa?",
            cwd=self.workspace,
            registry=self.registry,
            associations={"terms": {}},
            working_memory=[],
            semantic_triggers_path=None,
            semantic_cues_path=cues_path,
        )

        trigger_aliases = {
            alias for trigger in payload["trigger_catalog"] for alias in trigger.get("aliases") or []
        }
        relevant_aliases = {
            alias
            for trigger in payload["prompt_relevant_triggers"]
            for alias in trigger.get("aliases") or []
        }
        self.assertIn("memoria externa", trigger_aliases)
        self.assertIn("外置海马体", trigger_aliases)
        self.assertIn("memoria externa", relevant_aliases)

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

        private_key_block = "\n".join(
            [
                "看看这个",
                "-----" + "BEGIN PRIVATE KEY" + "-----",
                "abc",
                "-----" + "END PRIVATE KEY" + "-----",
            ]
        )

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

    def test_prompt_relevant_triggers_do_not_match_when_not_to_use_only_terms(self) -> None:
        trigger_path = self.root / "semantic_triggers.jsonl"
        trigger_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Atlas dashboard same-name project context",
                    "aliases": ["Atlas dashboard", "same-name entity trap"],
                    "when_to_use": "Use when continuing the Atlas dashboard context.",
                    "when_not_to_use": "Do not use for ordinary fixture edits.",
                    "confidence": 0.9,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        matches = gate.prompt_relevant_triggers(
            prompt="Bearer header placeholder 的 fixture 名字太误导。",
            semantic_triggers_path=trigger_path,
        )

        self.assertEqual(matches, [])

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
        self.assertEqual(first["cache_diagnostics"]["lookup"], "miss")
        self.assertEqual(second["cache_diagnostics"]["lookup"], "hit")
        self.assertTrue(second["cache_diagnostics"]["semantic_cues_in_cache_key"])
        self.assertEqual(calls["count"], 3)

    def test_semantic_cue_cache_changes_invalidate_gate_result_cache(self) -> None:
        calls = {"count": 0}

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            calls["count"] += 1
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.8,
                    "query_aliases": ["AIppocampus"],
                    "anti_personalization_risk": "low",
                    "reason": "cue cache key test",
                }
            )

        cache = self.root / "semantic_recall_cache.json"
        cues_path = self.root / "semantic_cues.jsonl"
        first = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            semantic_cues_path=cues_path,
            cache_path=cache,
            api_key="test-key",
            chat_fn=chat_fn,
        )
        cues_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_semantic_cue",
                    "status": "active",
                    "cue_id": "sc_test",
                    "cue": "внешний гиппокамп",
                    "route": "semantic_gate",
                    "confidence": 0.9,
                    "hit_count": 2,
                    "false_positive_count": 0,
                    "source_refs": [{"thread_key": "session:aippocampus"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        second = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            semantic_cues_path=cues_path,
            cache_path=cache,
            api_key="test-key",
            chat_fn=chat_fn,
        )

        self.assertFalse(first["cached"])
        self.assertFalse(second["cached"])
        self.assertEqual(second["cache_diagnostics"]["lookup"], "miss")
        self.assertTrue(second["cache_diagnostics"]["semantic_cues_in_cache_key"])
        self.assertEqual(calls["count"], 6)

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

    def test_worker_errors_are_bucketed_for_live_diagnostics(self) -> None:
        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            del messages, api_key, model, base_url, max_tokens, timeout, temperature
            raise TimeoutError("The read operation timed out")

        result = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["error_buckets"], {"read_timeout": 3})

    def test_overall_deadline_returns_before_slow_workers_finish(self) -> None:
        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            del messages, api_key, model, base_url, max_tokens, timeout, temperature
            time.sleep(0.35)
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.8,
                    "query_aliases": ["AIppocampus"],
                    "anti_personalization_risk": "low",
                    "reason": "too slow for foreground",
                }
            )

        started = time.perf_counter()
        result = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            timeout=5,
            deadline_seconds=0.05,
            chat_fn=chat_fn,
        )
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.25)
        self.assertFalse(result["available"])
        self.assertEqual(result["availability_reason"], "semantic_worker_timeout")
        self.assertEqual(result["diagnostic"], "semantic_overall_deadline_exceeded")
        self.assertEqual(result["error_buckets"], {"overall_deadline": 3})

    def test_openai_compatible_route_metadata_and_cache_metrics_are_neutral(self) -> None:
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_ROUTE"] = "local_semantic"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER"] = "local-test"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_MODEL"] = "local-model"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL"] = "http://127.0.0.1:11434/v1"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV"] = "LOCAL_SEMANTIC_TEST_KEY"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON"] = "false"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND"] = "none"
        os.environ["LOCAL_SEMANTIC_TEST_KEY"] = "present"
        seen: dict[str, object] = {}

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature, **kwargs):
            del messages, max_tokens, timeout, temperature, kwargs
            seen["api_key"] = api_key
            seen["model"] = model
            seen["base_url"] = base_url
            return fake_response(
                {
                    "decision": "background_only",
                    "confidence": 0.7,
                    "anti_personalization_risk": "low",
                    "reason": "local provider route",
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
            model_route="local_semantic",
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertTrue(result["available"])
        self.assertEqual(seen["api_key"], "present")
        self.assertEqual(seen["model"], "local-model")
        self.assertEqual(seen["base_url"], "http://127.0.0.1:11434/v1")
        self.assertEqual(result["model_route"]["provider"], "local-test")
        self.assertFalse(result["model_route"]["capabilities"]["supports_json_response"])
        self.assertEqual(result["worker_count"], 1)
        self.assertEqual(len(result["workers"]), 1)
        self.assertEqual(result["cache"], {"available": False, "kind": "none"})
        self.assertEqual(result["cache_diagnostics"]["lookup"], "disabled")
        self.assertIn("cache_key", result["cache_diagnostics"])

    def test_missing_openai_compatible_key_still_reports_route_metadata(self) -> None:
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_ROUTE"] = "local_semantic_missing"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER"] = "local-test"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_MODEL"] = "local-model"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL"] = "http://127.0.0.1:11434/v1"
        os.environ["AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV"] = "LOCAL_SEMANTIC_MISSING_KEY"

        result = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            model_route="local_semantic_missing",
            mode="on",
            use_cache=False,
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["model_route"]["provider"], "local-test")
        self.assertEqual(result["cache"], {"available": False, "kind": "none"})
        self.assertEqual(result["cache_diagnostics"]["lookup"], "disabled")


if __name__ == "__main__":
    unittest.main()
