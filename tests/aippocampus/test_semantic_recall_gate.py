from __future__ import annotations

import concurrent.futures
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.recall import semantic_cue_cache as cues
from aippocampus_runtime.recall import semantic_gate_response as response_stage
from aippocampus_runtime.recall import semantic_recall_gate as gate
from tests.aippocampus.redaction_fixtures import FAKE_TEST_OPENAI_API_KEY, FAKE_TEST_SECRET_VALUE
from tests.aippocampus.timing_fixtures import host_timeout_sleep


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
                "LOCAL_SEMANTIC_MISSING_KEY",
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

    def test_semantic_gate_cache_fingerprint_uses_stable_namespace(self) -> None:
        key = gate.cache_fingerprint(
            prompt="继续 #144",
            cwd=self.workspace,
            registry_path=self.registry_path,
            mode="auto",
            model="deepseek-test",
            base_url="https://api.example.invalid/v1",
            workers=("contextualist",),
            temperature=0.1,
        )
        stat = self.registry_path.stat()
        parts = [
            gate.PROMPT_VERSION,
            gate.semantic_gate_mode("auto"),
            "deepseek-test",
            "https://api.example.invalid/v1",
            "contextualist",
            "0.1",
            "继续 #144",
            str(self.workspace.resolve()).casefold(),
            f"{self.registry_path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}",
        ]

        self.assertEqual(
            key,
            gate.stable_text_fingerprint(
                "\n".join(parts),
                namespace="semantic-gate-cache",
                prefix="sg",
                length=24,
            ),
        )

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

    def test_worker_alias_runs_and_invalid_worker_fails_closed(self) -> None:
        calls: list[str] = []

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            del api_key, model, base_url, max_tokens, timeout, temperature
            content = "\n".join(str(message.get("content") or "") for message in messages)
            calls.append(content)
            return fake_response(
                {
                    "decision": "scent",
                    "intent": "continuation",
                    "confidence": 0.82,
                    "query_aliases": ["AIppocampus"],
                    "memory_scope": ["registered_threads"],
                    "anti_personalization_risk": "low",
                    "reason": "The prompt asks to continue prior memory work.",
                }
            )

        result = gate.run_semantic_gate(
            "继续之前 AIppocampus recall gate 那段",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            workers=("default",),
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["worker_count"], 3)
        self.assertEqual(len(calls), 3)

        invalid = gate.run_semantic_gate(
            "继续之前 AIppocampus recall gate 那段",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            workers=("unknown",),
            use_cache=False,
            chat_fn=chat_fn,
        )

        self.assertFalse(invalid["available"])
        self.assertEqual(invalid["decision"], "skip")
        self.assertEqual(invalid["worker_count"], 0)
        self.assertIn("invalid semantic worker", " ".join(invalid["errors"]))

    def test_merge_workers_caps_evidence_when_scope_worker_reports_high_risk(self) -> None:
        merged = gate.merge_workers(
            [
                {
                    "worker": "gate",
                    "decision": "evidence",
                    "intent": "recall",
                    "confidence": 0.91,
                    "query_aliases": ["exact wording"],
                    "memory_scope": ["registered_threads"],
                    "negative_contexts": [],
                    "anti_personalization_risk": "low",
                    "reason": "The prompt asks for exact prior wording.",
                },
                {
                    "worker": "scope",
                    "decision": "scent",
                    "intent": "recall",
                    "confidence": 0.88,
                    "query_aliases": [],
                    "memory_scope": ["cross_project"],
                    "negative_contexts": ["generic product work should not become personal memory"],
                    "anti_personalization_risk": "high",
                    "reason": "Cross-project scope is ambiguous and high risk.",
                },
            ],
            [],
        )

        self.assertEqual(merged["decision"], "scent")
        self.assertEqual(merged["anti_personalization_risk"], "high")
        self.assertTrue(merged["decision_capped"])
        self.assertEqual(merged["decision_before_risk_cap"], "evidence")
        self.assertEqual(merged["decision_cap_reason"], "high_anti_personalization_risk")
        self.assertEqual(merged["winning_worker"], "gate")
        self.assertEqual(merged["risk_worker"], "scope")
        self.assertIn("capped", " ".join(merged["reasons"]))

    def test_issue_580_response_stage_fixtures_cover_major_gate_outputs(self) -> None:
        disabled = gate.run_semantic_gate(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key_env="LOCAL_SEMANTIC_MISSING_KEY",
            mode="on",
            use_cache=False,
        )

        self.assertFalse(disabled["available"])
        self.assertEqual(disabled["decision"], "skip")
        self.assertEqual(disabled["availability_reason"], "semantic_unavailable")
        self.assertEqual(disabled["diagnostic"], "semantic_disabled_or_auth_unavailable")

        def evidence_chat(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            del messages, api_key, model, base_url, max_tokens, timeout, temperature
            return fake_response(
                {
                    "decision": "evidence",
                    "intent": "recall",
                    "confidence": 0.91,
                    "query_aliases": ["old source-backed wording"],
                    "memory_scope": ["registered_threads"],
                    "anti_personalization_risk": "low",
                    "reason": "The prompt asks for exact old source wording.",
                }
            )

        evidence = gate.run_semantic_gate(
            "找回之前那段原话和来源",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=evidence_chat,
        )

        self.assertTrue(evidence["available"])
        self.assertEqual(evidence["decision"], "evidence")
        self.assertEqual(evidence["anti_personalization_risk"], "low")
        self.assertIn("old source-backed wording", evidence["query_aliases"])

        def low_confidence_chat(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            del messages, api_key, model, base_url, max_tokens, timeout, temperature
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.31,
                    "query_aliases": ["weak ambient association"],
                    "memory_scope": ["registered_threads"],
                    "anti_personalization_risk": "low",
                    "reason": "Only a weak association.",
                }
            )

        low_confidence = gate.run_semantic_gate(
            "这个可能和以前哪条线有点像？",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=low_confidence_chat,
        )

        self.assertTrue(low_confidence["available"])
        self.assertEqual(low_confidence["decision"], "background_only")
        self.assertIn("downgraded low-confidence scent", low_confidence["reasons"])

    def test_issue_580_response_stage_owns_worker_response_parsing(self) -> None:
        parsed = response_stage.parse_worker_response(
            fake_response(
                {
                    "decision": "evidence",
                    "intent": "recall",
                    "confidence": 0.92,
                    "query_aliases": ["外置海马体", "external hippocampus"],
                    "memory_scope": ["registered_threads"],
                    "anti_personalization_risk": "low",
                    "reason": "source-backed recall request",
                }
            ),
            "gate",
        )

        self.assertIs(gate.parse_worker_response, response_stage.parse_worker_response)
        self.assertEqual(parsed["worker"], "gate")
        self.assertEqual(parsed["decision"], "evidence")
        self.assertEqual(parsed["intent"], "recall")
        self.assertEqual(parsed["confidence"], 0.92)
        self.assertIn("外置海马体", parsed["query_aliases"])
        self.assertEqual(parsed["anti_personalization_risk"], "low")

    def test_public_cli_payload_omits_aliases_workers_and_raw_errors(self) -> None:
        private_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.82,
            "cached": False,
            "query_aliases": ["private alias", FAKE_TEST_OPENAI_API_KEY],
            "memory_scope": ["registered_threads"],
            "reasons": ["private reason with E:\\private\\notes.md"],
            "workers": [{"raw": "private worker output"}],
            "errors": ["private error with token=secret"],
            "error_buckets": {"semantic_worker_error": 1},
            "cache": {"available": True, "hit_tokens": 1},
            "model_route": {
                "provider": "deepseek",
                "base_url": "https://private-model.example/v1",
                "api_key_env": "PRIVATE_MODEL_KEY_ENV",
            },
        }

        public = gate.public_semantic_gate_payload(private_result)

        encoded = json.dumps(public, ensure_ascii=False)
        self.assertEqual(public["decision"], "scent")
        self.assertEqual(public["worker_count"], 1)
        self.assertNotIn("query_aliases", public)
        self.assertNotIn("workers", public)
        self.assertNotIn("reasons", public)
        self.assertNotIn("errors", public)
        self.assertNotIn("private alias", encoded)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, encoded)
        self.assertNotIn("private-model.example", encoded)

    def test_public_payload_includes_safe_cache_diagnostics(self) -> None:
        private_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.82,
            "cached": True,
            "cache_diagnostics": {
                "lookup": "hit",
                "cache_key": "sg_" + "a" * 24,
                "semantic_cues_in_cache_key": True,
                "path": str(self.root / "private" / "semantic_recall_cache.json"),
                "prompt": "private prompt text",
                "telemetry": {"hits": 2, "misses": 1},
            },
        }

        public = gate.public_semantic_gate_payload(private_result)
        encoded = json.dumps(public, ensure_ascii=False)

        self.assertEqual(public["cache_diagnostics"]["lookup"], "hit")
        self.assertEqual(public["cache_diagnostics"]["cache_key"], "sg_" + "a" * 24)
        self.assertTrue(public["cache_diagnostics"]["semantic_cues_in_cache_key"])
        self.assertEqual(public["cache_diagnostics"]["telemetry"], {"hits": 2, "misses": 1})
        self.assertNotIn("private prompt text", encoded)
        self.assertNotIn(str(self.root), encoded)

    def test_main_json_uses_public_semantic_gate_payload(self) -> None:
        private_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.82,
            "cached": False,
            "query_aliases": ["private alias"],
            "workers": [{"raw": "private worker output"}],
            "errors": ["private error"],
        }
        stdout = io.StringIO()
        with (
            patch.object(gate, "run_semantic_gate", return_value=private_result),
            patch.object(
                sys,
                "argv",
                [
                    "semantic_recall_gate.py",
                    "--prompt",
                    "private prompt",
                    "--cwd",
                    str(self.workspace),
                    "--json",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = gate.main()

        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn('"decision": "scent"', rendered)
        self.assertNotIn("private alias", rendered)
        self.assertNotIn("private worker output", rendered)
        self.assertNotIn("private error", rendered)

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

    def test_mixed_private_key_prompt_preserves_safe_context_after_redaction(self) -> None:
        seen_prompts: list[str] = []

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            seen_prompts.append(messages[-1]["content"])
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.78,
                    "query_aliases": ["path anchor redaction"],
                    "anti_personalization_risk": "low",
                    "reason": "safe surrounding context remains useful.",
                }
            )

        private_key_block = "\n".join(
            [
                "-----" + "BEGIN PRIVATE KEY" + "-----",
                "abc",
                "-----" + "END PRIVATE KEY" + "-----",
            ]
        )
        prompt = (
            "Continue the AIppocampus external-model redaction design and "
            "project-safe path anchor work.\n"
            f"{private_key_block}\n"
            "Keep source-backed recall useful without leaking credential material."
        )

        result = gate.run_semantic_gate(
            prompt,
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        encoded_prompts = "\n".join(seen_prompts)
        self.assertTrue(result["available"])
        self.assertTrue(result["secret_policy"]["redacted"])
        self.assertFalse(result["secret_policy"]["hard_block"])
        self.assertIn("<redacted:private-key-block>", encoded_prompts)
        self.assertIn("project-safe path anchor", encoded_prompts)
        self.assertNotIn("BEGIN PRIVATE KEY", encoded_prompts)
        self.assertNotIn("abc", encoded_prompts)

    def test_model_payload_uses_project_safe_path_anchors_for_prompt_and_catalog(self) -> None:
        seen_prompts: list[str] = []

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            seen_prompts.append(messages[-1]["content"])
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.74,
                    "query_aliases": ["project path anchor"],
                    "anti_personalization_risk": "low",
                    "reason": "path anchors preserve safe structure.",
                }
            )

        project_file = self.workspace / "src" / "memory_gate.py"
        registry = {
            **self.registry,
            "threads": [
                {
                    **self.registry["threads"][0],
                    "summary": f"Related implementation lives near {project_file}",
                }
            ],
        }

        result = gate.run_semantic_gate(
            f"Continue the redaction work around {project_file}",
            cwd=self.workspace,
            registry=registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            chat_fn=chat_fn,
        )

        encoded_prompts = "\n".join(seen_prompts)
        self.assertTrue(result["available"])
        self.assertIn("<redacted:local-path>", encoded_prompts)
        self.assertIn("<path-anchor", encoded_prompts)
        self.assertIn("scope=project", encoded_prompts)
        self.assertIn("class=python", encoded_prompts)
        self.assertIn("hash=sha256:", encoded_prompts)
        self.assertNotIn(str(self.workspace), encoded_prompts)
        self.assertNotIn("memory_gate.py", encoded_prompts)

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

    def test_expired_cache_entry_reports_expiration_and_telemetry_without_prompt_text(self) -> None:
        cache = self.root / "semantic_recall_cache.json"
        route = gate.resolve_model_route(None)
        key = gate.cache_fingerprint(
            prompt="脑内续接器",
            cwd=self.workspace,
            registry_path=self.registry_path,
            semantic_triggers_path=gate.default_semantic_triggers_path(
                registry_path=self.registry_path
            ),
            semantic_cues_path=gate.default_semantic_cues_path(registry_path=self.registry_path),
            mode="auto",
            model=route.model,
            base_url=route.base_url,
            temperature=gate.DEFAULT_TEMPERATURE,
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "entries": {
                        key: {
                            "created_at": "2026-01-01T00:00:00Z",
                            "created_unix": time.time() - gate.DEFAULT_CACHE_TTL_SECONDS - 10,
                            "result": {
                                "available": True,
                                "decision": "scent",
                                "confidence": 0.8,
                                "query_aliases": ["private exact alias"],
                            },
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            return fake_response(
                {
                    "decision": "scent",
                    "confidence": 0.8,
                    "query_aliases": ["AIppocampus"],
                    "anti_personalization_risk": "low",
                    "reason": "expired cache rerun",
                }
            )

        result = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            cache_path=cache,
            api_key="test-key",
            chat_fn=chat_fn,
        )
        report = gate.semantic_cache_report(cache)
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertFalse(result["cached"])
        self.assertEqual(result["cache_diagnostics"]["lookup"], "expired")
        self.assertEqual(report["telemetry"]["expired"], 1)
        self.assertEqual(report["telemetry"]["misses"], 1)
        self.assertNotIn("private exact alias", encoded)
        self.assertNotIn("脑内续接器", encoded)

    def test_cache_eviction_keeps_high_value_semantic_cue_result_over_new_churn(self) -> None:
        cache = self.root / "semantic_recall_cache.json"
        high_value = {
            "available": True,
            "decision": "scent",
            "confidence": 0.93,
            "query_aliases": ["source-backed cue alias"],
            "cache_diagnostics": {"semantic_cues_in_cache_key": True},
        }
        low_value = {
            "available": True,
            "decision": "background_only",
            "confidence": 0.2,
            "query_aliases": [],
            "cache_diagnostics": {"semantic_cues_in_cache_key": False},
        }

        gate.write_cache(cache, "sg_high_value_cue", high_value, max_entries=2)
        gate.write_cache(cache, "sg_low_churn_1", low_value, max_entries=2)
        gate.write_cache(cache, "sg_low_churn_2", low_value, max_entries=2)
        payload = json.loads(cache.read_text(encoding="utf-8"))

        self.assertIn("sg_high_value_cue", payload["entries"])
        self.assertIn("sg_low_churn_2", payload["entries"])
        self.assertNotIn("sg_low_churn_1", payload["entries"])
        self.assertEqual(payload["telemetry"]["evictions"], 1)
        self.assertEqual(payload["telemetry"]["eviction_reasons"], {"low_value_churn": 1})

    def test_concurrent_cache_writers_do_not_share_fixed_tmp_path(self) -> None:
        cache = self.root / "semantic_recall_cache.json"

        def write_one(index: int) -> None:
            gate.write_cache(
                cache,
                f"sg_concurrent_{index}",
                {
                    "available": True,
                    "decision": "scent",
                    "confidence": 0.7,
                    "query_aliases": [f"alias-{index}"],
                },
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(write_one, index) for index in range(12)]
            for future in futures:
                future.result()

        payload = json.loads(cache.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["entries"]), 12)
        self.assertEqual(payload["telemetry"]["writes"], 12)
        self.assertFalse(list(cache.parent.glob("*.tmp")))
        self.assertFalse(list(cache.parent.glob("*.lock")))

    def test_cache_report_separates_partial_timeout_skip_from_valid_skip(self) -> None:
        cache = self.root / "semantic_recall_cache.json"
        gate.write_cache(
            cache,
            "sg_valid_skip",
            {
                "available": True,
                "decision": "skip",
                "confidence": 0.2,
                "partial_success": False,
                "partial_failure_reasons": [],
                "error_buckets": {},
            },
        )
        gate.write_cache(
            cache,
            "sg_partial_timeout_skip",
            {
                "available": True,
                "decision": "skip",
                "confidence": 0.2,
                "partial_success": True,
                "partial_failure_reasons": ["read_timeout"],
                "error_buckets": {"read_timeout": 1},
            },
        )

        report = gate.semantic_cache_report(cache)

        self.assertEqual(report["value_classes"]["skip"], 1)
        self.assertEqual(report["value_classes"]["partial_timeout_skip"], 1)
        self.assertEqual(report["active_partial_failure_count"], 1)
        self.assertEqual(report["active_timeout_count"], 1)
        self.assertEqual(report["degraded_cached_decision_count"], 1)

    def test_main_cache_report_json_omits_prompt_and_alias_text(self) -> None:
        cache = self.root / "semantic_recall_cache.json"
        gate.write_cache(
            cache,
            "sg_report",
            {
                "available": True,
                "decision": "scent",
                "confidence": 0.8,
                "query_aliases": ["private alias should not render"],
                "cache_diagnostics": {"semantic_cues_in_cache_key": True},
            },
        )
        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "semantic_recall_gate.py",
                    "--cache-report",
                    "--cache",
                    str(cache),
                    "--json",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = gate.main()

        rendered = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn('"entry_count"', rendered)
        self.assertIn('"telemetry"', rendered)
        self.assertNotIn("private alias should not render", rendered)

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

    def test_foreground_gate_requires_explicit_deadline_before_calling_model(self) -> None:
        calls = {"count": 0}

        def chat_fn(*args, **kwargs):
            calls["count"] += 1
            raise AssertionError("foreground gate without a deadline must fail open")

        result = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            foreground=True,
            chat_fn=chat_fn,
        )

        self.assertEqual(calls["count"], 0)
        self.assertFalse(result["available"])
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["availability_reason"], "foreground_budget_skipped")
        self.assertEqual(result["diagnostic"], "semantic_foreground_deadline_required")
        self.assertEqual(result["error_buckets"], {"foreground_budget": 1})
        self.assertEqual(result["deadline"]["seconds"], None)
        self.assertEqual(result["deadline"]["exceeded"], True)

    def test_foreground_gate_requires_worker_timeout_within_deadline(self) -> None:
        calls = {"count": 0}

        def chat_fn(*args, **kwargs):
            calls["count"] += 1
            raise AssertionError("foreground worker timeout must be bounded before model call")

        result = gate.run_semantic_gate(
            "脑内续接器",
            cwd=self.workspace,
            registry=self.registry,
            registry_path=self.registry_path,
            api_key="test-key",
            use_cache=False,
            foreground=True,
            timeout=3.0,
            deadline_seconds=1.0,
            chat_fn=chat_fn,
        )

        self.assertEqual(calls["count"], 0)
        self.assertFalse(result["available"])
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["availability_reason"], "foreground_budget_skipped")
        self.assertEqual(result["diagnostic"], "semantic_foreground_timeout_exceeds_deadline")
        self.assertEqual(result["error_buckets"], {"foreground_budget": 1})
        self.assertEqual(result["deadline"]["seconds"], 1.0)
        self.assertEqual(result["deadline"]["exceeded"], True)

    def test_overall_deadline_returns_before_slow_workers_finish(self) -> None:
        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):
            del messages, api_key, model, base_url, max_tokens, timeout, temperature
            host_timeout_sleep(
                0.35,
                reason="simulate workers that exceed the semantic gate overall deadline",
            )
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
