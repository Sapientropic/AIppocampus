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
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ambient_warm_scheduler as warm_scheduler  # noqa: E402
import warm_ambient_recall as warm  # noqa: E402


class WarmAmbientRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.cache_path = self.root / "ambient-thread-cache.json"
        self.residue_path = self.root / "ambient-residue.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_thread(self, thread_key: str, rows: list[dict]) -> Path:
        clean_dir = self.root / "clean" / thread_key.replace(":", "-")
        clean_dir.mkdir(parents=True)
        messages_path = clean_dir / "messages.jsonl"
        messages_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        return messages_path

    def _write_registry(self, entries: list[dict]) -> Path:
        registry_path = self.root / "registry" / "threads.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

    def test_default_scout_lanes_are_adjusted_10_families_times_5_variants(self) -> None:
        calls: list[str] = []

        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            calls.append(scout)
            return {"decision": "skip", "confidence": 0.1}

        result = warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            wait_all=True,
            no_write=True,
        )
        families = {lane.split(":", 1)[0] for lane in warm.DEFAULT_SCOUTS}
        variants = {lane.split(":", 1)[1] for lane in warm.DEFAULT_SCOUTS}
        expected_families = {
            "intent_mode_classifier",
            "privacy_boundary_guard",
            "deep_theme_matcher",
            "key_line_hunter",
            "evidence_gap_sentinel",
            "user_style_preference",
            "trajectory_matcher",
            "cross_domain_bridge",
            "nudge_writer",
            "semantic_expander",
        }

        self.assertEqual(len(warm.DEFAULT_SCOUTS), 50)
        self.assertEqual(families, expected_families)
        self.assertEqual(len(variants), 5)
        self.assertEqual(
            warm.DEFAULT_SCOUTS[:5],
            (
                "intent_mode_classifier:direct",
                "privacy_boundary_guard:direct",
                "deep_theme_matcher:direct",
                "key_line_hunter:direct",
                "evidence_gap_sentinel:direct",
            ),
        )
        self.assertEqual(result["scout_count"], 50)
        self.assertEqual(len(calls), 50)
        self.assertEqual(warm.SCOUT_PRIORITY["key_line_hunter"], "P0")
        self.assertEqual(warm.SCOUT_PRIORITY["semantic_expander"], "P1")

    def test_scout_prompt_marks_output_contract_as_schema_not_template(self) -> None:
        payload, _ = warm.build_payload("继续 ambient recall", cwd=self.workspace, registry={})

        prompt = warm.scout_prompt("intent_mode_classifier:direct", payload)

        self.assertIn("Do not copy or fill output_contract", prompt)
        self.assertIn("using only scout_task.output_profile fields", prompt)
        self.assertIn("max_query_aliases", prompt)
        self.assertIn("max_candidates", prompt)

    def test_parse_scout_output_preserves_two_generation_candidates(self) -> None:
        row = warm.parse_scout_output(
            {
                "decision": "candidate",
                "confidence": 0.8,
                "themes": ["theme one", "theme two"],
                "candidates": [
                    {"theme": "candidate one", "support_level": "candidate"},
                    {"theme": "candidate two", "support_level": "candidate"},
                    {"theme": "candidate three", "support_level": "candidate"},
                ],
            },
            "deep_theme_matcher:direct",
        )

        self.assertEqual(len(row["candidates"]), 2)
        self.assertEqual(row["candidates"][0]["theme"], "candidate one")
        self.assertEqual(row["candidates"][1]["theme"], "candidate two")

    def test_parse_scout_output_treats_theme_object_as_candidate(self) -> None:
        row = warm.parse_scout_output(
            {
                "decision": "candidate",
                "confidence": 0.8,
                "theme": {
                    "theme": "resource booking generalization",
                    "support_level": "evidence",
                    "key_line": "I need a general resources booking system",
                    "source_refs": [
                        {"thread_key": "session:old", "message_id": "msg-1", "line": 7}
                    ],
                },
            },
            "deep_theme_matcher:direct",
        )

        self.assertEqual(row["themes"], [])
        self.assertEqual(row["candidates"][0]["theme"], "resource booking generalization")
        self.assertEqual(row["candidates"][0]["source_refs"][0]["message_id"], "msg-1")

    def test_parse_scout_output_keeps_intent_classifier_candidate_free(self) -> None:
        row = warm.parse_scout_output(
            {
                "decision": "candidate",
                "confidence": 0.8,
                "themes": ["execution mode"],
                "candidates": [{"theme": "too broad", "support_level": "candidate"}],
            },
            "intent_mode_classifier:direct",
        )

        self.assertEqual(row["themes"], [])
        self.assertEqual(row["candidates"], [])

    def test_env_max_workers_becomes_default_concurrency_limit(self) -> None:
        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {"decision": "skip", "confidence": 0.1}

        with patch.dict(os.environ, {"AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS": "7"}):
            result = warm.run_warm_ambient_recall(
                "继续 ambient recall",
                cwd=self.workspace,
                thread_id="thread-a",
                cache_path=self.cache_path,
                api_key="test-key",
                scout_fn=scout_fn,
                wait_all=True,
                no_write=True,
            )

        self.assertEqual(result["max_workers"], 7)

    def test_warm_background_is_default_on_with_explicit_opt_outs(self) -> None:
        self.assertTrue(warm_scheduler.warm_background_enabled(env={}))
        self.assertTrue(
            warm_scheduler.warm_background_enabled(
                env={"AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "1"}
            )
        )
        self.assertFalse(
            warm_scheduler.warm_background_enabled(
                env={"AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "off"}
            )
        )
        self.assertFalse(
            warm_scheduler.warm_background_enabled(
                False, env={"AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "1"}
            )
        )
        self.assertTrue(
            warm_scheduler.warm_background_enabled(
                True, env={"AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "off"}
            )
        )

    def test_scheduler_queues_by_default_when_spawn_is_disabled(self) -> None:
        with patch.dict(os.environ, {"AIPPOCAMPUS_WARM_RECALL_BACKGROUND": ""}):
            result = warm_scheduler.schedule_warm_ambient_recall(
                "继续 ambient recall",
                cwd=self.workspace,
                thread_id="thread-a",
                cache_path=self.cache_path,
                topic_epoch="epoch-test",
                job_dir=self.root / "warm-jobs",
                spawn=False,
            )

        self.assertEqual(result["status"], "queued")
        self.assertTrue(Path(result["job_path"]).exists())
        job = json.loads(Path(result["job_path"]).read_text(encoding="utf-8"))
        self.assertEqual(job["timeout"], warm_scheduler.DEFAULT_DETACHED_WARM_TIMEOUT)

    def test_scheduler_env_opt_out_still_disables_default_warming(self) -> None:
        with patch.dict(os.environ, {"AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "0"}):
            result = warm_scheduler.schedule_warm_ambient_recall(
                "继续 ambient recall",
                cwd=self.workspace,
                thread_id="thread-a",
                cache_path=self.cache_path,
                topic_epoch="epoch-test",
                job_dir=self.root / "warm-jobs",
                spawn=False,
            )

        self.assertEqual(result["status"], "disabled")
        self.assertFalse((self.root / "warm-jobs").exists())

    def test_model_scout_uses_stable_sanitized_user_id_and_quality_first_thinking(self) -> None:
        seen_user_ids: list[str | None] = []
        seen_thinking: list[str | None] = []
        seen_temperatures: list[float] = []

        def chat_fn(
            messages,
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
            *,
            user_id=None,
            thinking=None,
        ):
            del messages, api_key, model, base_url, max_tokens, timeout
            seen_user_ids.append(user_id)
            seen_thinking.append(thinking)
            seen_temperatures.append(temperature)
            content = json.dumps({"decision": "skip", "confidence": 0.1})
            return {"choices": [{"message": {"content": content}}]}

        warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            chat_fn=chat_fn,
            scouts=("intent_mode_classifier", "key_line_hunter"),
            wait_all=True,
            no_write=True,
        )

        self.assertEqual(len(set(seen_user_ids)), 1)
        self.assertRegex(seen_user_ids[0] or "", r"^aip-warm-[a-f0-9]{32}$")
        self.assertNotIn(str(self.workspace), seen_user_ids[0] or "")
        self.assertEqual(set(seen_thinking), {"enabled"})
        self.assertEqual(set(seen_temperatures), {warm.DEFAULT_TEMPERATURE})

    def test_model_scout_can_disable_thinking_for_explicit_diagnostics(self) -> None:
        seen_thinking: list[str | None] = []
        seen_temperatures: list[float] = []

        def chat_fn(
            messages,
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
            *,
            user_id=None,
            thinking=None,
        ):
            del messages, api_key, model, base_url, max_tokens, timeout, user_id
            seen_thinking.append(thinking)
            seen_temperatures.append(temperature)
            content = json.dumps({"decision": "skip", "confidence": 0.1})
            return {"choices": [{"message": {"content": content}}]}

        with patch.dict(os.environ, {"AIPPOCAMPUS_WARM_RECALL_THINKING": "disabled"}):
            previous = warm.DEFAULT_THINKING
            warm.DEFAULT_THINKING = "disabled"
            try:
                warm.run_warm_ambient_recall(
                    "继续 ambient recall",
                    cwd=self.workspace,
                    thread_id="thread-a",
                    cache_path=self.cache_path,
                    api_key="test-key",
                    chat_fn=chat_fn,
                    scouts=("semantic_expander",),
                    wait_all=True,
                    no_write=True,
                    temperature=0.2,
                )
            finally:
                warm.DEFAULT_THINKING = previous

        self.assertEqual(seen_thinking, ["disabled"])
        self.assertEqual(seen_temperatures, [0.2])

    def test_openai_compatible_route_does_not_send_deepseek_extensions_by_default(self) -> None:
        seen_user_ids: list[str | None] = []
        seen_thinking: list[str | None] = []
        seen_models: list[str] = []
        seen_base_urls: list[str] = []

        def chat_fn(
            messages,
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
            *,
            user_id=None,
            thinking=None,
        ):
            del messages, api_key, max_tokens, timeout, temperature
            seen_user_ids.append(user_id)
            seen_thinking.append(thinking)
            seen_models.append(model)
            seen_base_urls.append(base_url)
            return {"choices": [{"message": {"content": json.dumps({"decision": "skip", "confidence": 0.1})}}]}

        with patch.dict(
            os.environ,
            {
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_warm",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-warm-model",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_WARM_KEY",
                "LOCAL_WARM_KEY": "present",
            },
            clear=False,
        ):
            result = warm.run_warm_ambient_recall(
                "继续 ambient recall",
                cwd=self.workspace,
                thread_id="thread-a",
                cache_path=self.cache_path,
                model_route="local_warm",
                chat_fn=chat_fn,
                scouts=("semantic_expander",),
                wait_all=True,
                no_write=True,
            )

        self.assertEqual(seen_user_ids, [None])
        self.assertEqual(seen_thinking, [None])
        self.assertEqual(seen_models, ["local-warm-model"])
        self.assertEqual(seen_base_urls, ["http://127.0.0.1:11434/v1"])
        self.assertIsNone(result["user_id"])
        self.assertEqual(result["model_route"]["provider"], "local-test")
        self.assertEqual(result["cache"], {"available": False, "kind": "none"})

    def test_legacy_explicit_base_url_uses_conservative_compatible_capabilities(self) -> None:
        seen_user_ids: list[str | None] = []
        seen_thinking: list[str | None] = []
        seen_models: list[str] = []
        seen_base_urls: list[str] = []

        def chat_fn(
            messages,
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
            *,
            user_id=None,
            thinking=None,
        ):
            del messages, api_key, max_tokens, timeout, temperature
            seen_user_ids.append(user_id)
            seen_thinking.append(thinking)
            seen_models.append(model)
            seen_base_urls.append(base_url)
            return {"choices": [{"message": {"content": json.dumps({"decision": "skip", "confidence": 0.1})}}]}

        with patch.dict(os.environ, {"LOCAL_EXPLICIT_KEY": "present"}, clear=False):
            result = warm.run_warm_ambient_recall(
                "继续 ambient recall",
                cwd=self.workspace,
                thread_id="thread-a",
                cache_path=self.cache_path,
                api_key_env="LOCAL_EXPLICIT_KEY",
                model="local-explicit-model",
                base_url="http://127.0.0.1:11434/v1",
                chat_fn=chat_fn,
                scouts=("semantic_expander",),
                wait_all=True,
                no_write=True,
            )

        self.assertEqual(seen_user_ids, [None])
        self.assertEqual(seen_thinking, [None])
        self.assertEqual(seen_models, ["local-explicit-model"])
        self.assertEqual(seen_base_urls, ["http://127.0.0.1:11434/v1"])
        self.assertEqual(result["model_route"]["route"], "explicit_openai_compatible")
        self.assertEqual(result["cache"], {"available": False, "kind": "none"})

    def test_unavailable_and_job_summary_keep_route_metadata(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_warm_missing",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-warm-model",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_WARM_MISSING_KEY",
            },
            clear=False,
        ):
            result = warm.run_warm_ambient_recall(
                "继续 ambient recall",
                cwd=self.workspace,
                thread_id="thread-a",
                cache_path=self.cache_path,
                model_route="local_warm_missing",
                no_write=True,
            )
        summary = warm.warm_job_result_summary({"job_id": "job", "prompt_sha1": "abc"}, result)

        self.assertFalse(result["available"])
        self.assertEqual(result["model_route"]["provider"], "local-test")
        self.assertEqual(result["cache"], {"available": False, "kind": "none"})
        self.assertEqual(summary["model_route"]["provider"], "local-test")
        self.assertEqual(summary["cache"], {"available": False, "kind": "none"})

    def test_quorum_returns_without_waiting_for_all_scouts(self) -> None:
        calls: list[str] = []

        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            calls.append(scout)
            if scout.startswith(("key_line_hunter:", "intent_mode_classifier:")):
                return {
                    "decision": "candidate",
                    "confidence": 0.72,
                    "themes": [f"{scout} theme"],
                    "candidates": [
                        {
                            "theme": f"{scout} theme",
                            "support_level": "candidate",
                            "matched_terms": ["ambient recall"],
                        }
                    ],
                }
            time.sleep(0.25)
            return {"decision": "skip", "confidence": 0.1}

        started = time.perf_counter()
        result = warm.run_warm_ambient_recall(
            "继续 ambient recall 这条线",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            quorum=2,
            timeout=0.12,
            no_write=True,
        )
        elapsed = time.perf_counter() - started

        self.assertTrue(result["available"])
        self.assertTrue(result["quorum_met"])
        self.assertLess(elapsed, 0.2)
        self.assertEqual(result["accepted_scout_count"], 2)
        self.assertEqual(len(warm.DEFAULT_SCOUTS), 50)
        self.assertTrue(any(call.startswith("key_line_hunter:") for call in calls))
        self.assertTrue(any(call.startswith("intent_mode_classifier:") for call in calls))

    def test_prefix_cache_warmup_runs_initial_scout_before_parallel_followups(self) -> None:
        calls: list[str] = []
        warmup_completed = False
        premature_followups: list[str] = []

        def scout_fn(scout, payload, **kwargs):
            nonlocal warmup_completed
            del payload, kwargs
            calls.append(scout)
            if len(calls) == 1:
                time.sleep(0.02)
                warmup_completed = True
            elif not warmup_completed:
                premature_followups.append(scout)
            return {"decision": "skip", "confidence": 0.1}

        result = warm.run_warm_ambient_recall(
            "继续 ambient recall prefix cache",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=(
                "intent_mode_classifier:direct",
                "key_line_hunter:direct",
                "deep_theme_matcher:direct",
            ),
            max_workers=3,
            prefix_cache_warmup_scouts=1,
            wait_all=True,
            no_write=True,
        )

        self.assertEqual(calls[0], "intent_mode_classifier:direct")
        self.assertEqual(premature_followups, [])
        self.assertEqual(result["prefix_cache_warmup_scout_count"], 1)

    def test_quorum_not_met_does_not_write_weak_single_scout_cache(self) -> None:
        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            if scout.startswith("key_line_hunter"):
                return {
                    "decision": "candidate",
                    "confidence": 0.72,
                    "candidates": [
                        {
                            "theme": "single scout should stay out of cache",
                            "support_level": "candidate",
                            "matched_terms": ["single", "scout"],
                        }
                    ],
                }
            time.sleep(0.2)
            return {"decision": "skip", "confidence": 0.1}

        result = warm.run_warm_ambient_recall(
            "继续 ambient recall 但 quorum 不足",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("key_line_hunter:direct", "semantic_expander:direct"),
            quorum=2,
            timeout=0.05,
        )

        self.assertFalse(result["quorum_met"])
        self.assertEqual(result["status"], "quorum_not_met")
        self.assertIsNone(result["cache_write"])
        self.assertFalse(self.cache_path.exists())

    def test_malformed_scout_is_isolated(self) -> None:
        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            if scout.startswith("semantic_expander:"):
                raise ValueError("not valid JSON")
            return {
                "decision": "candidate",
                "confidence": 0.8,
                "candidates": [{"theme": "warm cache", "support_level": "candidate"}],
            }

        result = warm.run_warm_ambient_recall(
            "继续 warm cache",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("semantic_expander", "deep_theme_matcher"),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["accepted_scout_count"], 1)
        self.assertEqual(result["failed_scout_count"], 1)
        self.assertEqual(result["scouts"][0]["ok"], False)
        self.assertEqual(result["scouts"][1]["ok"], True)
        self.assertEqual(result["cards"][0]["theme"], "warm cache")

    def test_prompt_trace_fallback_can_surface_supported_prior_context(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 1,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "Use docker-compose.yml with a host log volume and keep the original service layout.",
                },
                {
                    "message_id": "msg-2",
                    "source_line": 2,
                    "role": "user",
                    "text": "Please add logging without changing the compose file completely.",
                },
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Docker logging",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {"decision": "skip", "confidence": 0.1}

        result = warm.run_warm_ambient_recall(
            "Please use the old docker-compose.yml and add logging",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("deep_theme_matcher",),
            prompt_trace=[
                {
                    "thread_key": "session:old",
                    "role": "assistant",
                    "phase": "final_answer",
                    "text": "Use docker-compose.yml with a host log volume and keep the original service layout.",
                    "source_refs": [{"thread_key": "session:old", "message_id": "msg-1", "line": 1}],
                },
                {
                    "thread_key": "session:old",
                    "role": "user",
                    "phase": "current_prompt",
                    "text": "Please use the old docker-compose.yml and add logging",
                    "source_refs": [{"thread_key": "session:old", "message_id": "msg-2", "line": 2}],
                },
            ],
            quorum=1,
            timeout=0.5,
            wait_all=True,
            no_write=True,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["trace_fallback_card_count"], 1)
        self.assertEqual(result["cards"][0]["source_validation"]["status"], "supported")
        self.assertEqual(result["cards"][0]["support_level"], "evidence")
        self.assertNotIn("current_prompt", result["cards"][0]["key_line"])

    def test_prompt_trace_fallback_does_not_use_current_prompt_as_memory(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 1,
                    "role": "user",
                    "text": "What are some advanced use cases for Node.js?",
                }
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Node prompt",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {"decision": "skip", "confidence": 0.1}

        result = warm.run_warm_ambient_recall(
            "What are some advanced use cases for Node.js?",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("deep_theme_matcher",),
            prompt_trace=[
                {
                    "thread_key": "session:old",
                    "role": "user",
                    "phase": "current_prompt",
                    "text": "What are some advanced use cases for Node.js?",
                    "source_refs": [{"thread_key": "session:old", "message_id": "msg-1", "line": 1}],
                }
            ],
            quorum=1,
            timeout=0.5,
            wait_all=True,
            no_write=True,
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["trace_fallback_card_count"], 0)

    def test_prompt_trace_fallback_handles_strong_continuation_without_term_overlap(self) -> None:
        cards = warm.prompt_trace_fallback_cards(
            "Please continue exactly where you left off.",
            [
                {
                    "thread_key": "session:old",
                    "role": "assistant",
                    "phase": "final_answer",
                    "text": "Register the WordPress plugin block extension, enqueue the editor script, and keep the generated alt text in the image block attributes.",
                    "source_refs": [
                        {"thread_key": "session:old", "message_id": "msg-1", "line": 1}
                    ],
                },
                {
                    "thread_key": "session:old",
                    "role": "user",
                    "phase": "current_prompt",
                    "text": "Please continue exactly where you left off.",
                    "source_refs": [
                        {"thread_key": "session:old", "message_id": "msg-2", "line": 2}
                    ],
                },
            ],
        )

        self.assertEqual(len(cards), 1)
        self.assertIn("WordPress", cards[0]["key_line"])
        self.assertNotIn("continue exactly", cards[0]["key_line"])

    def test_prompt_trace_fallback_ignores_generic_error_overlap(self) -> None:
        cards = warm.prompt_trace_fallback_cards(
            "I am trying to use my trained model but get error \"config file is not valid JSON.\"",
            [
                {
                    "thread_key": "session:old",
                    "role": "assistant",
                    "phase": "final_answer",
                    "text": "The RuntimeError expected scalar type Long but found Int occurs when a tensor dtype is wrong during training.",
                    "source_refs": [
                        {"thread_key": "session:old", "message_id": "msg-1", "line": 1}
                    ],
                },
            ],
        )

        self.assertEqual(cards, [])

    def test_warm_merge_writes_thread_cache_and_residue_without_raw_inputs(self) -> None:
        local_path = "E:" + "\\private\\notes\\ambient.md"
        prompt = f"继续 {local_path} 里的 ambient recall 方案"

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.91,
                "negative_contexts": ["do not treat unsourced scent as fact"],
                "candidates": [
                    {
                        "theme": "ambient recall cache first",
                        "support_level": "evidence",
                        "resonance": "high",
                        "suggested_use": "Use as source-backed prior only when helpful.",
                        "key_line": "Card/cache first, then warm scouts.",
                        "matched_terms": ["ambient recall", "cache"],
                        "source_refs": [
                            {
                                "thread_key": "session:old",
                                "title": "Ambient design",
                                "line": 42,
                                "message_id": "msg-1",
                            }
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            prompt,
            cwd=self.workspace,
            thread_id="thread-a",
            topic_epoch="epoch-test",
            cache_path=self.cache_path,
            residue_path=self.residue_path,
            residue_reason="warm_scout_unused",
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("key_line_hunter",),
            quorum=1,
            timeout=0.5,
        )
        cache_raw = self.cache_path.read_text(encoding="utf-8")
        residue_rows = [
            json.loads(line)
            for line in self.residue_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        joined = cache_raw + "\n" + self.residue_path.read_text(encoding="utf-8")

        self.assertEqual(result["cache_write"]["status"], "written")
        self.assertEqual(result["cache_write"]["residue_export"]["status"], "written")
        self.assertEqual(residue_rows[0]["source"], "ambient_thread_cache")
        self.assertEqual(residue_rows[0]["reason"], "warm_scout_unused")
        self.assertNotIn(str(self.workspace), joined)
        self.assertNotIn("private", joined.casefold())
        self.assertNotIn("notes", joined.casefold())
        self.assertNotIn(prompt, joined)

    def test_missing_api_key_fails_open_without_writing(self) -> None:
        result = warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key=None,
            api_key_env="AIPPOCAMPUS_TEST_MISSING_KEY",
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "missing api key")
        self.assertFalse(self.cache_path.exists())

    def test_source_validation_drops_unsupported_evidence_ref(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "This source discusses unrelated registry maintenance only.",
                }
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Old ambient thread",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.9,
                "candidates": [
                    {
                        "theme": "ambient validation",
                        "support_level": "evidence",
                        "key_line": "Card/cache first, then warm scouts.",
                        "matched_terms": ["warm scouts"],
                        "source_refs": [
                            {"thread_key": "session:old", "message_id": "msg-1", "line": 42}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "继续 warm scouts",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("key_line_hunter",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["cards"], [])

    def test_source_validation_keeps_supported_evidence_ref(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "The design says: Card/cache first, then warm scouts. This validates ambient recall.",
                }
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Old ambient thread",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.9,
                "candidates": [
                    {
                        "theme": "ambient validation",
                        "support_level": "evidence",
                        "key_line": "Card/cache first, then warm scouts.",
                        "matched_terms": ["ambient recall"],
                        "source_refs": [
                            {"thread_key": "session:old", "message_id": "msg-1", "line": 42}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("key_line_hunter",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertEqual(result["cards"][0]["support_level"], "evidence")
        self.assertEqual(result["cards"][0]["source_validation"]["status"], "supported")

    def test_supported_deep_archival_visibility_survives_merge(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "The original wording was: continuity survives transformation.",
                }
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Old ambient thread",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.92,
                "candidates": [
                    {
                        "theme": "original wording",
                        "support_level": "evidence",
                        "visibility": "deep_archival_recall",
                        "key_line": "continuity survives transformation",
                        "matched_terms": ["continuity"],
                        "source_refs": [
                            {"thread_key": "session:old", "message_id": "msg-1", "line": 42}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "找回原话 continuity survives transformation",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("key_line_hunter",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertEqual(result["mode"], "deep_archival_recall")
        self.assertEqual(result["cards"][0]["support_level"], "evidence")
        self.assertEqual(result["cards"][0]["visibility"], "deep_archival_recall")

    def test_current_thread_echo_is_suppressed_by_default(self) -> None:
        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.9,
                "candidates": [
                    {
                        "theme": "current echo",
                        "support_level": "evidence",
                        "key_line": "This was just said in the current thread.",
                        "matched_terms": ["current thread"],
                        "source_refs": [
                            {"thread_key": "session:current", "message_id": "msg-current", "line": 7}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "继续当前话题",
            cwd=self.workspace,
            thread_id="thread-a",
            current_thread_key="session:current",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("key_line_hunter",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertEqual(result["cards"], [])
        self.assertEqual(result["current_thread_echo_count"], 1)

    def test_llm_topic_epoch_rotation_uses_scout_label_not_prompt_terms(self) -> None:
        label = "semantic scope sidecar calibration"

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "candidate",
                "confidence": 0.8,
                "topic_epoch_action": "rotate",
                "topic_epoch_label": label,
                "topic_epoch_reason": "The prompt trace moved to sidecar calibration.",
                "candidates": [{"theme": "epoch rotation", "support_level": "candidate"}],
            }

        result = warm.run_warm_ambient_recall(
            "unrelated deterministic prompt terms should not define the epoch",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("deep_theme_matcher",),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )
        prompt_terms_epoch = warm.topic_epoch_from_terms(
            ["unrelated deterministic prompt terms should not define the epoch"]
        )

        self.assertEqual(result["topic_epoch"], warm.topic_epoch_from_terms([label]))
        self.assertNotEqual(result["topic_epoch"], prompt_terms_epoch)
        self.assertEqual(result["topic_epoch_decision"]["action"], "rotate")

    def test_prompt_trace_is_sanitized_before_scout_payload(self) -> None:
        local_path = "C:" + "\\private\\trace\\memory.md"
        seen_payloads: list[dict] = []

        def scout_fn(scout, payload, **kwargs):
            del scout, kwargs
            seen_payloads.append(payload)
            return {"decision": "skip", "confidence": 0.1}

        warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            prompt_trace=[
                {
                    "thread_key": "session:current",
                    "role": "user",
                    "text": f"trace mentions {local_path}",
                }
            ],
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("semantic_expander",),
            quorum=1,
            timeout=0.5,
            wait_all=True,
            no_write=True,
        )
        raw_payload = json.dumps(seen_payloads[0], ensure_ascii=False)

        self.assertIn("prompt_trace", seen_payloads[0])
        self.assertIn("<redacted:local-path>", raw_payload)
        self.assertNotIn(local_path.casefold(), raw_payload.casefold())
        self.assertNotIn("memory.md", raw_payload.casefold())

    def test_build_payload_keeps_stable_contract_before_prompt_specific_fields(self) -> None:
        payload, _ = warm.build_payload("继续 ambient recall", cwd=self.workspace, registry={})
        keys = list(payload.keys())

        self.assertLess(keys.index("output_contract"), keys.index("prompt"))
        self.assertLess(keys.index("memory_catalog"), keys.index("prompt"))

    def test_scout_prompt_uses_cache_friendly_prefix_and_family_lens_detail(self) -> None:
        payload = {
            "prompt_version": warm.PROMPT_VERSION,
            "task": "propose_warm_ambient_recall_hints",
            "prompt": "那个脑内续接器现在怎么样了？",
            "prompt_terms": ["脑内续接器"],
            "memory_catalog": [{"thread_key": "session:old", "summary": "ambient recall design"}],
            "prompt_trace": [{"text": "之前聊过 ambient recall。"}],
        }

        rendered = warm.scout_prompt("semantic_expander:registry_window", payload)
        parsed = json.loads(rendered)
        keys = list(parsed.keys())

        self.assertLess(keys.index("output_budget"), keys.index("shared_context"))
        self.assertLess(keys.index("shared_context"), keys.index("prompt_context"))
        self.assertLess(keys.index("prompt_context"), keys.index("scout_task"))
        self.assertLess(keys.index("prompt_context"), keys.index("variant_context"))
        self.assertNotIn("prompt", parsed["shared_context"])
        self.assertNotIn("prompt_trace", parsed["shared_context"])
        self.assertEqual(parsed["prompt_context"]["prompt"], payload["prompt"])
        self.assertIn("memory_catalog", parsed["shared_context"])
        self.assertIn("prompt_trace", parsed["prompt_context"])
        self.assertNotIn("prompt_trace", parsed["variant_context"])
        self.assertEqual(parsed["scout_task"]["scout_family"], "semantic_expander")
        self.assertEqual(parsed["scout_task"]["scout_variant"], "registry_window")
        semantic_profile = parsed["scout_task"]["output_profile"]
        lens = parsed["scout_task"]["lens_task"]
        self.assertIn("allowed_fields", semantic_profile)
        self.assertIn("query", lens.casefold())
        self.assertIn("registry", lens.casefold())

    def test_scout_prompt_keeps_case_context_before_lane_split(self) -> None:
        payload_a = {
            "prompt_version": warm.PROMPT_VERSION,
            "task": "propose_warm_ambient_recall_hints",
            "prompt": "case A prompt",
            "prompt_terms": ["case", "a"],
            "memory_catalog": [],
            "prompt_trace": [{"text": "case A trace"}],
        }
        payload_b = {
            "prompt_version": warm.PROMPT_VERSION,
            "task": "propose_warm_ambient_recall_hints",
            "prompt": "case B prompt",
            "prompt_terms": ["case", "b"],
            "memory_catalog": [],
            "prompt_trace": [{"text": "case B trace"}],
        }

        prompt_a = warm.scout_prompt("semantic_expander:direct", payload_a)
        prompt_b = warm.scout_prompt("key_line_hunter:direct", payload_a)
        prompt_c = warm.scout_prompt("semantic_expander:direct", payload_b)
        same_case_prefix_a = prompt_a.split('  "scout_task"', 1)[0]
        same_case_prefix_b = prompt_b.split('  "scout_task"', 1)[0]
        cross_case_prefix_a = prompt_a.split('  "prompt_context"', 1)[0]
        cross_case_prefix_c = prompt_c.split('  "prompt_context"', 1)[0]

        self.assertEqual(same_case_prefix_a, same_case_prefix_b)
        self.assertEqual(cross_case_prefix_a, cross_case_prefix_c)
        self.assertIn("case A prompt", same_case_prefix_a)
        self.assertNotIn('"scout":', same_case_prefix_a)
        self.assertNotIn("case A prompt", cross_case_prefix_a)
        self.assertNotIn("case B prompt", cross_case_prefix_c)

    def test_scout_prompt_shares_prompt_trace_before_lane_split(self) -> None:
        payload = {
            "prompt_version": warm.PROMPT_VERSION,
            "task": "propose_warm_ambient_recall_hints",
            "prompt": "继续",
            "prompt_terms": ["继续"],
            "memory_catalog": [{"thread_key": "session:old", "summary": "heavy registry"}],
            "prompt_trace": [{"text": "heavy trace"}],
        }

        direct = json.loads(warm.scout_prompt("semantic_expander:direct", payload))
        trace = json.loads(warm.scout_prompt("evidence_gap_sentinel:current_trace_window", payload))

        self.assertIn("prompt_trace", direct["prompt_context"])
        self.assertIn("prompt_trace", trace["prompt_context"])
        self.assertIn("memory_catalog", direct["shared_context"])
        self.assertIn("memory_catalog", trace["shared_context"])
        self.assertEqual(direct["variant_context"], {})
        self.assertIn("prompt_trace_policy", trace["variant_context"])

    def test_family_output_profile_omits_unused_fields(self) -> None:
        privacy = json.loads(
            warm.scout_prompt("privacy_boundary_guard:direct", {"prompt": "继续"})
        )["scout_task"]["output_profile"]
        semantic = json.loads(
            warm.scout_prompt("semantic_expander:direct", {"prompt": "继续"})
        )["scout_task"]["output_profile"]
        key_line = json.loads(
            warm.scout_prompt("key_line_hunter:direct", {"prompt": "继续"})
        )["scout_task"]["output_profile"]

        self.assertNotIn("candidates", privacy["allowed_fields"])
        self.assertIn("query_aliases", semantic["allowed_fields"])
        self.assertNotIn("topic_epoch_action", semantic["allowed_fields"])
        self.assertIn("candidates", key_line["allowed_fields"])
        self.assertIn("key_line", key_line["candidate_fields"])

    def test_p0_lens_tasks_are_family_specific(self) -> None:
        privacy = json.loads(
            warm.scout_prompt(
                "privacy_boundary_guard:current_trace_window",
                {"prompt": "继续", "memory_catalog": [], "prompt_trace": []},
            )
        )["scout_task"]["lens_task"].casefold()
        privacy_skeptic = json.loads(
            warm.scout_prompt(
                "privacy_boundary_guard:skeptic_window",
                {"prompt": "继续", "memory_catalog": [], "prompt_trace": []},
            )
        )["scout_task"]["lens_task"].casefold()
        theme = json.loads(
            warm.scout_prompt(
                "deep_theme_matcher:direct",
                {"prompt": "继续", "memory_catalog": [], "prompt_trace": []},
            )
        )["scout_task"]["lens_task"].casefold()
        key_line = json.loads(
            warm.scout_prompt(
                "key_line_hunter:direct",
                {"prompt": "继续", "memory_catalog": [], "prompt_trace": []},
            )
        )["scout_task"]["lens_task"].casefold()

        self.assertIn("relationship", privacy)
        self.assertIn("professional secret", privacy_skeptic)
        self.assertIn("philosophical", theme)
        self.assertIn("visual", key_line)

    def test_merge_dedupes_similar_themes_and_keeps_diverse_cards(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "candidate",
                    "confidence": 0.9,
                    "candidates": [
                        {
                            "theme": "ambient recall cache validation",
                            "support_level": "candidate",
                            "matched_terms": ["ambient recall", "cache"],
                        }
                    ],
                },
                "trajectory_matcher:direct",
            ),
            warm.parse_scout_output(
                {
                    "decision": "candidate",
                    "confidence": 0.85,
                    "candidates": [
                        {
                            "theme": "cache validation for ambient recall",
                            "support_level": "candidate",
                            "matched_terms": ["cache", "validation"],
                        }
                    ],
                },
                "deep_theme_matcher:registry_window",
            ),
            warm.parse_scout_output(
                {
                    "decision": "candidate",
                    "confidence": 0.8,
                    "candidates": [
                        {
                            "theme": "dream residue handoff",
                            "support_level": "candidate",
                            "matched_terms": ["dream", "residue"],
                        }
                    ],
                },
                "key_line_hunter:direct",
            ),
        ]

        result = warm.merge_scouts(rows, max_cards=3)
        themes = [card["theme"] for card in result["cards"]]

        self.assertEqual(len(result["cards"]), 2)
        self.assertIn("ambient recall cache validation", themes)
        self.assertIn("dream residue handoff", themes)
        ambient_card = next(card for card in result["cards"] if card["theme"].startswith("ambient"))
        self.assertIn("validation", ambient_card["matched_terms"])

    def test_guard_family_blocks_even_when_lane_has_variant_suffix(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "skip",
                    "confidence": 0.95,
                    "block": True,
                    "reason": "private unrelated association",
                },
                "privacy_scope_guard:direct",
            )
        ]

        result = warm.merge_scouts(rows)

        self.assertEqual(result["cards"], [])
        self.assertEqual(result["mode"], warm.SILENT_TUNING)
        self.assertEqual(result["blocked_by"], ["privacy_boundary_guard:direct"])

    def test_privacy_blocker_still_counts_suppressed_current_thread_fallback(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "skip",
                    "confidence": 0.95,
                    "block": True,
                    "reason": "private unrelated association",
                },
                "privacy_boundary_guard:direct",
            )
        ]
        fallback = [
            {
                "theme": "current-thread fallback",
                "support_level": warm.EVIDENCE,
                "visibility": warm.SOURCE_BACKED_RECALL_CARD,
                "key_line": "This was just said in the current thread.",
                "matched_terms": ["current thread"],
                "source_refs": [
                    {"thread_key": "session:current", "message_id": "msg-1", "line": 1}
                ],
            }
        ]

        result = warm.merge_scouts(
            rows,
            fallback_cards=fallback,
            current_thread_key="session:current",
        )

        self.assertEqual(result["cards"], [])
        self.assertEqual(result["blocked_by"], ["privacy_boundary_guard:direct"])
        self.assertEqual(result["current_thread_echo_count"], 1)

    def test_evidence_blocker_preserves_supported_prompt_trace_fallback(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "skip",
                    "confidence": 0.91,
                    "block": True,
                    "reason": "model candidate lacks source support",
                    "candidates": [
                        {
                            "theme": "unsupported model-only card",
                            "support_level": "evidence",
                            "matched_terms": ["phantom"],
                            "source_refs": [
                                {"thread_key": "session:old", "message_id": "missing"}
                            ],
                        }
                    ],
                },
                "evidence_gap_sentinel:direct",
            )
        ]
        fallback = [
            {
                "theme": "prior trace: booking system",
                "support_level": warm.EVIDENCE,
                "visibility": warm.SOURCE_BACKED_RECALL_CARD,
                "key_line": "Use a generic resource booking model.",
                "matched_terms": ["booking", "resource"],
                "source_refs": [
                    {"thread_key": "session:old", "message_id": "msg-1", "line": 1}
                ],
            }
        ]
        source_index = {
            "session:old": {
                "by_id": {
                    "msg-1": {
                        "id": "msg-1",
                        "line": 1,
                        "text": "Use a generic resource booking model.",
                    }
                },
                "by_line": {
                    "1": {
                        "id": "msg-1",
                        "line": 1,
                        "text": "Use a generic resource booking model.",
                    }
                },
            }
        }

        result = warm.merge_scouts(
            rows,
            fallback_cards=fallback,
            source_index=source_index,
        )

        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(result["cards"][0]["theme"], "prior trace: booking system")
        self.assertEqual(result["cards"][0]["source_validation"]["status"], "supported")
        self.assertEqual(result["blocked_by"], ["evidence_gap_sentinel:direct"])

    def test_evidence_blocker_still_silences_when_no_supported_fallback_exists(self) -> None:
        rows = [
            warm.parse_scout_output(
                {
                    "decision": "skip",
                    "confidence": 0.91,
                    "block": True,
                    "reason": "missing source support",
                },
                "evidence_gap_sentinel:direct",
            )
        ]

        result = warm.merge_scouts(rows, fallback_cards=[], source_index={})

        self.assertEqual(result["cards"], [])
        self.assertEqual(result["mode"], warm.SILENT_TUNING)
        self.assertEqual(result["blocked_by"], ["evidence_gap_sentinel:direct"])

    def test_legacy_scout_family_names_expand_to_canonical_taxonomy(self) -> None:
        self.assertEqual(warm.expand_scout_lanes(("query_expansion",)), ("semantic_expander:direct",))
        self.assertEqual(warm.expand_scout_lanes(("evidence_judge:skeptic_window",)), ("evidence_gap_sentinel:skeptic_window",))

    def test_scheduler_writes_sanitized_detached_job_without_raw_prompt(self) -> None:
        local_path = "E:" + "\\private\\notes\\ambient.md"
        result = warm_scheduler.schedule_warm_ambient_recall(
            f"继续 {local_path} 里的 ambient recall 方案",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=self.root / "registry" / "threads.json",
            cache_path=self.cache_path,
            topic_epoch="epoch-test",
            job_dir=self.root / "warm-jobs",
            spawn=False,
            enabled=True,
            api_key_env="DEEPSEEK_API_KEY",
            scouts=("intent_mode_classifier:direct",),
        )
        job = json.loads(Path(result["job_path"]).read_text(encoding="utf-8"))
        raw_job = json.dumps(job, ensure_ascii=False)

        self.assertEqual(result["status"], "queued")
        self.assertEqual(job["thread_id"], "thread-a")
        self.assertEqual(job["topic_epoch"], "epoch-test")
        self.assertTrue(job["wait_all"])
        self.assertFalse(job["no_write"])
        self.assertGreaterEqual(job["prefix_cache_warmup_scouts"], 1)
        self.assertGreater(job["prefix_cache_warmup_delay"], 0)
        self.assertIn("<redacted:local-path>", job["prompt"])
        self.assertNotIn(local_path, raw_job)
        self.assertNotIn("private", job["prompt"].casefold())
        self.assertNotIn("ambient.md", job["prompt"].casefold())

    def test_detached_job_waits_all_and_writes_late_scout_results_to_cache(self) -> None:
        job_result = warm_scheduler.schedule_warm_ambient_recall(
            "继续 ambient recall late cache",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            topic_epoch="epoch-test",
            job_dir=self.root / "warm-jobs",
            spawn=False,
            enabled=True,
            api_key_env="DEEPSEEK_API_KEY",
            scouts=("deep_theme_matcher:direct", "key_line_hunter:direct"),
            quorum=1,
        )

        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            if scout.startswith("key_line_hunter"):
                time.sleep(0.03)
                return {
                    "decision": "candidate",
                    "confidence": 0.82,
                    "candidates": [
                        {
                            "theme": "metaphor key-line resonance",
                            "support_level": "candidate",
                            "matched_terms": ["metaphor", "key-line"],
                        }
                    ],
                }
            return {
                "decision": "candidate",
                "confidence": 0.72,
                "candidates": [
                        {
                            "theme": "intent mode continuity",
                            "support_level": "candidate",
                            "matched_terms": ["intent", "mode"],
                        }
                ],
            }

        summary = warm.run_warm_job_file(
            Path(job_result["job_path"]),
            api_key="test-key",
            scout_fn=scout_fn,
        )
        cache_payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        cache_cards = next(iter(cache_payload["entries"].values()))["cards"]
        themes = [card["theme"] for card in cache_cards]

        self.assertEqual(summary["status"], "written")
        self.assertEqual(summary["observed_scout_result_count"], 2)
        self.assertEqual(summary["accepted_scout_count"], 2)
        self.assertNotIn("cards", summary)
        self.assertIn("intent mode continuity", themes)
        self.assertIn("metaphor key-line resonance", themes)


if __name__ == "__main__":
    unittest.main()
