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
        self.assertIn("At most 3 query_aliases", prompt)
        self.assertIn("Candidate budget", prompt)
        self.assertIn("up to 2", prompt)

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

        self.assertEqual(row["themes"], ["execution mode"])
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

    def test_model_scout_uses_stable_sanitized_user_id(self) -> None:
        seen_user_ids: list[str | None] = []

        def chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature, *, user_id=None):
            del messages, api_key, model, base_url, max_tokens, timeout, temperature
            seen_user_ids.append(user_id)
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
            scouts=("evidence_gap_sentinel",),
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
            scouts=("evidence_gap_sentinel",),
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
            scouts=("evidence_judge",),
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
            "memory_catalog": [],
        }

        rendered = warm.scout_prompt("semantic_expander:registry_window", payload)
        parsed = json.loads(rendered)
        keys = list(parsed.keys())

        self.assertLess(keys.index("output_budget"), keys.index("shared_context"))
        self.assertLess(keys.index("shared_context"), keys.index("scout_task"))
        self.assertEqual(parsed["shared_context"], payload)
        self.assertEqual(parsed["scout_task"]["scout_family"], "semantic_expander")
        self.assertEqual(parsed["scout_task"]["scout_variant"], "registry_window")
        self.assertIn("query", parsed["scout_task"]["lens_task"].casefold())
        self.assertIn("registry", parsed["scout_task"]["lens_task"].casefold())

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
        self.assertNotIn("private", raw_job.casefold())
        self.assertNotIn("ambient.md", raw_job.casefold())

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
