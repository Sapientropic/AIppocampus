from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

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

import aippocampus_prompt_hook as hook  # noqa: E402
import build_concept_graph as concept_graph  # noqa: E402
import prompt_cues as recall_cues  # noqa: E402


class AmbientRecallHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_semantic_gate = os.environ.get("AIPPOCAMPUS_SEMANTIC_GATE")
        os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = "off"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.old = self.root / "old-thread"
        self.index_dir = self.old / ".aippocampus"
        self.index_dir.mkdir(parents=True)
        self.sqlite = self.index_dir / "source_index.sqlite"
        self._write_sqlite()
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self._write_registry()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        if self.old_semantic_gate is None:
            os.environ.pop("AIPPOCAMPUS_SEMANTIC_GATE", None)
        else:
            os.environ["AIPPOCAMPUS_SEMANTIC_GATE"] = self.old_semantic_gate

    def test_prompt_hook_keeps_decision_and_rendering_in_split_modules(self) -> None:
        self.assertEqual(hook.assess_prompt.__module__, "prompt_recall_decision")
        self.assertEqual(hook.context_for_hook.__module__, "prompt_context_render")
        self.assertEqual(hook.hook_stdout_payload.__module__, "prompt_context_render")

    def test_hook_input_from_stdin_reads_codex_json_after_split(self) -> None:
        old_stdin = sys.stdin
        payload = {"prompt": "hook smoke 测试", "cwd": str(self.workspace)}
        try:
            sys.stdin = io.StringIO(json.dumps(payload, ensure_ascii=False))
            parsed = hook.hook_input_from_stdin()
        finally:
            sys.stdin = old_stdin

        self.assertEqual(parsed["prompt"], payload["prompt"])
        self.assertEqual(parsed["cwd"], payload["cwd"])

    def _write_sqlite(self) -> None:
        con = sqlite3.connect(self.sqlite)
        try:
            con.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    line INTEGER,
                    timestamp TEXT,
                    role TEXT,
                    kind TEXT,
                    phase TEXT,
                    turn_index INTEGER,
                    is_final INTEGER,
                    text TEXT
                )
                """
            )
            rows = [
                (
                    1,
                    190,
                    "2026-05-25T01:00:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    7,
                    1,
                    "生命还能变成什么，而我能不能在变化后仍然是我。",
                ),
                (
                    2,
                    999,
                    "2026-05-25T01:30:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    11,
                    1,
                    "这只是一个包含之前和还是的普通收尾，不应该被当成那句生命问题的证据。",
                ),
                (
                    3,
                    356,
                    "2026-05-25T02:00:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    19,
                    1,
                    "raw history 明明在本地，但压缩后的我不知道该找什么，所以需要外置海马体和触发式召回。",
                ),
            ]
            con.executemany(
                """
                INSERT INTO messages
                (id, line, timestamp, role, kind, phase, turn_index, is_final, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            con.commit()
        finally:
            con.close()

    def _write_registry(self) -> None:
        entry = {
            "thread_key": "session:test-old",
            "title": "old-thread",
            "workspace_name": "old-thread",
            "updated_at": "2026-05-25T19:00:00Z",
            "message_count": 2,
            "rollout_size": 1024,
            "anchor_count": 2,
            "anchor_titles": [
                "Active recall and retrieval optimization checkpoint",
                "LLM self-continuity and external hippocampus",
            ],
            "keywords": [
                "active recall",
                "ambient recall",
                "hook",
                "Codex",
                "联想",
                "触发式召回",
                "外置海马体",
                "self-continuity",
                "生命还能变成什么",
            ],
            "summary": "旧线程讨论过 UserPromptSubmit hook、联想式记忆、小海马体、以及自我连续性的原话。",
            "paths": {
                "workspace": str(self.old),
                "sqlite": str(self.sqlite),
                "anchors": None,
            },
        }
        self.registry.write_text(
            json.dumps(
                {"schema_version": 1, "updated_at": "2026-05-25T19:00:00Z", "threads": [entry]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_single_thread_registry(
        self,
        *,
        title: str,
        keywords: list[str],
        summary: str,
    ) -> Path:
        registry_path = self.root / f"{title.lower().replace(' ', '-')}-registry" / "threads.json"
        registry_path.parent.mkdir()
        entry = {
            "thread_key": "session:single-thread",
            "title": title,
            "workspace_name": "single-thread",
            "updated_at": "2026-05-25T19:00:00Z",
            "anchor_titles": [title],
            "keywords": keywords,
            "summary": summary,
            "paths": {"workspace": str(self.old), "sqlite": str(self.sqlite)},
        }
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": [entry]}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

    def _write_clean_thread(self, thread_key: str, timestamp: str, text: str) -> Path:
        clean_dir = self.root / thread_key.replace(":", "-") / "clean-source"
        clean_dir.mkdir(parents=True)
        messages = clean_dir / "messages.jsonl"
        message = {
            "message_id": f"msg-{thread_key}",
            "turn_id": f"turn-{thread_key}",
            "source_line": 42,
            "timestamp": timestamp,
            "role": "assistant",
            "phase": "final_answer",
            "turn_index": 3,
            "is_final": True,
            "text": text,
        }
        messages.write_text(json.dumps(message, ensure_ascii=False) + "\n", encoding="utf-8")
        return messages

    def test_code_only_prompt_stays_silent(self) -> None:
        result = hook.assess_prompt(
            "把 dashboard 的按钮 hover 样式改一下，顺手跑测试",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(hook.context_for_hook(result))

    def test_code_surface_prompt_does_not_call_semantic_gate_for_generic_association(self) -> None:
        associations = self.registry.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "dashboard": {
                            "term": "dashboard",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 5,
                            "threads": [{"thread_key": "session:test-old"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("semantic gate should not run for ordinary code surface prompts")

        result = hook.assess_prompt(
            "把 dashboard 的按钮 hover 样式改一下，顺手跑测试",
            cwd=self.workspace,
            registry_path=self.registry,
            associations_path=associations,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(result["semantic_gate"])

    def test_short_latin_accent_daily_question_does_not_call_semantic_gate(self) -> None:
        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("semantic gate should not run for short daily questions")

        result = hook.assess_prompt(
            "¿Qué tiempo hará mañana?",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(result["semantic_gate"])

    def test_explicit_recall_with_local_association_skips_foreground_semantic_gate(self) -> None:
        associations = self.root / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "terms": {
                        "外置海马体": {
                            "term": "外置海马体",
                            "status": "verified",
                            "confidence": 0.95,
                            "hit_count": 3,
                            "threads": [{"thread_key": "session:test-old"}],
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("local association should avoid foreground semantic spend")

        result = hook.assess_prompt(
            "还记得外置海马体这件事吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            associations_path=associations,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])

    def test_associative_prompt_emits_scent_without_evidence(self) -> None:
        result = hook.assess_prompt(
            "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertGreaterEqual(result["score"], hook.SCENT_THRESHOLD)
        self.assertTrue(result["candidates"])
        self.assertEqual(result["ambient_recall"]["mode"], "active_gentle_nudge")
        self.assertEqual(
            result["ambient_recall"]["cards"][0]["visibility"], "active_gentle_nudge"
        )
        context = hook.context_for_hook(result)
        self.assertIsNotNone(context)
        self.assertIn("Ambient recall scent", context)
        self.assertIn("Ambient recall private context", context)
        self.assertIn("Use only if it helps", context)
        self.assertNotIn("line 190", context)

    def test_chinese_hook_cue_emits_scent(self) -> None:
        result = hook.assess_prompt(
            "我重启了一下 Codex，你看看实测钩子效果如何",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIn(
            "associative cue",
            " ".join(str(reason) for reason in result["reasons"]),
        )

    def test_generic_codex_overlap_without_memory_cue_stays_silent(self) -> None:
        result = hook.assess_prompt(
            "我重启了一下 Codex，看看状态",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(hook.context_for_hook(result))

    def test_vague_continuation_without_semantic_stays_silent_despite_overlap(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Python list.sort None",
            keywords=["Python", "list.sort", "None", "missing keys"],
            summary="Prior coding conversation about list.sort returning None.",
        )

        result = hook.assess_prompt(
            "继续刚才这个编程问题，重点是 list.sort None",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertGreaterEqual(result["score"], hook.SCENT_THRESHOLD)
        self.assertFalse(result["evidence"])

    def test_weaker_vague_continuation_needs_semantic_positive_to_scent(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Python list.sort None",
            keywords=["Python", "list.sort", "None", "missing keys"],
            summary="Prior coding conversation about list.sort returning None.",
        )

        local_result = hook.assess_prompt(
            "这个问题后面怎么接，重点是 list.sort None",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(local_result["decision"], "skip")

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.86,
                "intent": "continuation",
                "query_aliases": ["list.sort", "None"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["vague continuation with source overlap"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        semantic_result = hook.assess_prompt(
            "这个问题后面怎么接，重点是 list.sort None",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(semantic_result["decision"], "scent")
        self.assertIn("semantic gate", " ".join(str(reason) for reason in semantic_result["reasons"]))

    def test_short_english_associative_cues_require_token_boundaries(self) -> None:
        matches = recall_cues.matched_terms(
            "Rewrite the paragraphs while leveraging the background examples.",
            recall_cues.ASSOCIATIVE_CUES,
        )

        self.assertNotIn("rag", matches)
        self.assertNotIn("hook", recall_cues.matched_terms("Handle this webhook payload.", {"hook"}))
        self.assertNotIn(
            "hook",
            recall_cues.matched_terms(
                "Write a Header Hook for this course.", recall_cues.ASSOCIATIVE_CUES
            ),
        )
        self.assertNotIn(
            "evidence",
            recall_cues.matched_terms(
                "Summarize the evidence in these articles.", recall_cues.ASSOCIATIVE_CUES
            ),
        )
        self.assertIn("rag", recall_cues.matched_terms("Use RAG-lite for recall.", {"rag"}))

    def test_dynamic_association_can_emit_scent_without_hardcoded_cue(self) -> None:
        associations = self.registry.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "associations.json": {
                            "term": "associations.json",
                            "status": "staging",
                            "confidence": 0.7,
                            "related_terms": ["小海马体", "ambient recall"],
                            "threads": [
                                {
                                    "thread_key": "session:test-old",
                                    "title": "old-thread",
                                    "line": 356,
                                    "phase": "final_answer",
                                    "turn_index": 19,
                                }
                            ],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "这个 associations.json 的动态联想层还要再收一下",
            cwd=self.workspace,
            registry_path=self.registry,
            associations_path=associations,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIn(
            "dynamic association",
            " ".join(str(reason) for reason in result["reasons"]),
        )
        self.assertNotIn("ambient recall", result["query_terms"])

    def test_cognitive_map_route_emits_scent_without_direct_registry_match(self) -> None:
        cognitive_map_path = self.registry.parent / "cognitive_map.json"
        cognitive_map_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_cognitive_map",
                    "status": "active",
                    "routes": [
                        {
                            "route_id": "cmr_test",
                            "kind": "cognitive_map_route",
                            "source": "deepseek_subconscious_jobs",
                            "landmark_ids": ["lm_aippocampus"],
                            "landmark_labels": ["AIppocampus", "外置海马体"],
                            "region_ids": ["region_architecture"],
                            "region_labels": ["memory architecture"],
                            "route_cues": ["心理地图", "位置细胞", "网格细胞"],
                            "query_terms": ["外置海马体", "触发式召回"],
                            "thread_keys": ["session:test-old"],
                            "confidence": 0.9,
                            "source_refs": [{"thread_key": "session:test-old", "line": 356}],
                        }
                    ],
                    "landmarks": [
                        {
                            "landmark_id": "lm_aippocampus",
                            "label": "AIppocampus",
                            "aliases": ["外置海马体", "认知地图"],
                            "thread_keys": ["session:test-old"],
                            "confidence": 0.9,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("cognitive map route should avoid foreground semantic spend")

        result = hook.assess_prompt(
            "咱们继续心理地图和位置细胞这条升级",
            cwd=self.workspace,
            registry_path=self.registry,
            cognitive_map_path=cognitive_map_path,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:test-old")
        self.assertIn("外置海马体", result["query_terms"])
        self.assertIn("cognitive map route", " ".join(result["reasons"]))

    def test_semantic_gate_alias_can_emit_scent_without_hardcoded_cue(self) -> None:
        registry_path = self.root / "semantic-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "海马体记忆", "working memory"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.88,
                "intent": "continuation",
                "query_aliases": ["AIppocampus", "海马体记忆", "working memory"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["paraphrase of the memory-system thread"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")
        self.assertIn("AIppocampus", result["query_terms"])
        self.assertIn("semantic gate", " ".join(result["reasons"]))

    def test_foreground_budget_caps_semantic_gate_timeout(self) -> None:
        registry_path = self.root / "semantic-budget-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        seen: dict[str, float] = {}

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            seen["timeout"] = float(kwargs["timeout"])
            return {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "memory_scope": [],
                "reasons": ["test"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            semantic_timeout=3,
            max_elapsed_ms=3000,
            search_budget=0,
        )

        self.assertIn("timeout", seen)
        self.assertLessEqual(seen["timeout"], 1.8)
        self.assertEqual(result["semantic_gate"]["available"], False)

    def test_tiny_foreground_budget_skips_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-budget-skip-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError(
                "semantic gate should be skipped when no foreground budget remains"
            )

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fail_semantic_gate,
            semantic_timeout=3,
            max_elapsed_ms=1,
            search_budget=0,
        )

        self.assertEqual(result["semantic_gate"]["available"], False)
        self.assertIn("foreground budget", " ".join(result["semantic_gate"]["reasons"]))

    def test_multilingual_natural_language_can_reach_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-registry-ru" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "海马体记忆", "working memory"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.87,
                "intent": "continuation",
                "query_aliases": ["AIppocampus", "海马体记忆", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["Russian paraphrase of external hippocampus memory"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "Как там мой внешний гиппокамп памяти и продолжение разговоров?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")
        self.assertIn("AIppocampus", result["query_terms"])

    def test_space_less_japanese_prompt_can_reach_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-registry-ja" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "海马体记忆", "working memory"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.87,
                "intent": "continuation",
                "query_aliases": ["AIppocampus", "海马体记忆"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["Japanese paraphrase"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "外部海馬みたいな記憶システムの進捗はどう？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")

    def test_latin_language_long_exact_question_can_reach_semantic_gate(self) -> None:
        registry_path = self.root / "semantic-registry-es" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:aippocampus",
                            "title": "AIppocampus work",
                            "project_label": "AIppocampus",
                            "anchor_titles": ["AIppocampus ambient recall continuity"],
                            "keywords": ["AIppocampus", "external hippocampus"],
                            "summary": "Hook-assisted recall continuity and semantic gate work.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.87,
                "intent": "recall",
                "query_aliases": ["AIppocampus", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["Spanish exact-recall paraphrase"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "¿Puedes recuperar la frase exacta que dijiste sobre el hipocampo externo?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")

    def test_semantic_gate_evidence_is_guarded_for_fuzzy_status_prompt(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model wants evidence"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])

    def test_association_boost_counts_each_thread_once(self) -> None:
        entry = {
            "thread_key": "session:dup",
            "title": "Duplicate source thread",
            "updated_at": "2026-05-25T01:00:00Z",
            "paths": {},
        }
        match = {
            "term": "T-Sense",
            "status": "staging",
            "confidence": 0.62,
            "hit_count": 3,
            "matched_terms": ["T-Sense"],
            "threads": [
                {"thread_key": "session:dup", "line": 1},
                {"thread_key": "session:dup", "line": 2},
                {"thread_key": "session:dup", "line": 3},
            ],
        }

        merged = hook.merge_association_candidates([], {"threads": [entry]}, [match], ["T-Sense"])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["score"], hook.association_boost(match, 1))

    def test_clean_source_probe_can_rerank_specific_thread_above_broad_project_scent(self) -> None:
        old_messages = self._write_clean_thread(
            "session:old-project",
            "2026-05-20T00:00:00Z",
            "这里讨论过 T-Sense 的普通项目背景，但没有具体的新搜索方案。",
        )
        exact_messages = self._write_clean_thread(
            "session:exact-search",
            "2026-05-25T00:00:00Z",
            "T-Sense 可以评估 WukongVector WukongVector WukongVector WukongVector WukongVector 搜索层，先做小范围 spike。",
        )
        registry_path = self.root / "probe-registry" / "threads.json"
        registry_path.parent.mkdir()
        entries = [
            {
                "thread_key": "session:old-project",
                "title": "T-Sense · 2026-05-20",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-20T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(old_messages)},
            },
            {
                "thread_key": "session:exact-search",
                "title": "T-Sense · 2026-05-25",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-25T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(exact_messages)},
            },
        ]
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        associations = registry_path.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "T-Sense": {
                            "term": "T-Sense",
                            "status": "staging",
                            "confidence": 0.62,
                            "hit_count": 40,
                            "related_terms": [],
                            "threads": [
                                {
                                    "thread_key": "session:old-project",
                                    "title": "T-Sense · 2026-05-20",
                                }
                            ],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "T-SENSE 现在是不是应该采用 WukongVector 搜索？",
            cwd=self.workspace,
            registry_path=registry_path,
            associations_path=associations,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:exact-search")
        self.assertTrue(result["evidence"])
        self.assertIn("evidence-lite", " ".join(result["reasons"]))

    def test_project_timeline_recency_cue_can_add_latest_project_thread(self) -> None:
        old_messages = self._write_clean_thread(
            "session:timeline-old",
            "2026-05-20T00:00:00Z",
            "T-Sense 的旧讨论。",
        )
        latest_messages = self._write_clean_thread(
            "session:timeline-latest",
            "2026-05-25T00:00:00Z",
            "T-Sense 最新关心的是 Go runtime spike。",
        )
        registry_path = self.root / "timeline-registry" / "threads.json"
        registry_path.parent.mkdir()
        entries = [
            {
                "thread_key": "session:timeline-old",
                "title": "T-Sense old",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-20T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(old_messages)},
            },
            {
                "thread_key": "session:timeline-latest",
                "title": "T-Sense latest",
                "project_label": "T-Sense",
                "session_meta": {"timestamp": "2026-05-25T00:00:00Z"},
                "paths": {"clean_source_messages_jsonl": str(latest_messages)},
            },
        ]
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        (registry_path.parent / "associations.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "T-Sense": {
                            "term": "T-Sense",
                            "status": "staging",
                            "confidence": 0.62,
                            "hit_count": 2,
                            "threads": [{"thread_key": "session:timeline-old"}],
                        },
                        "当前线程": {
                            "term": "当前线程",
                            "status": "staging",
                            "confidence": 0.9,
                            "hit_count": 20,
                            "threads": [{"thread_key": "session:timeline-old"}],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "projects": {
                        "project:t-sense": {
                            "project_key": "project:t-sense",
                            "project_label": "T-Sense",
                            "project_tags": ["T-Sense"],
                            "latest_turns": [{"thread_key": "session:timeline-latest"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "关于T-SENSE，我在当前线程之外最后关心的主题是什么？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:timeline-latest")
        self.assertIn("project timeline", " ".join(result["reasons"]))

    def test_life_wide_timeline_recency_cue_can_add_quiet_scent(self) -> None:
        registry_path = self.root / "life-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "session_meta": {"timestamp": "2026-05-24T00:00:00Z"},
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "scope_label": "personal_reflection",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "title": "Life continuity notes",
                                        "timestamp": "2026-05-24T00:00:00Z",
                                        "turn_id": "turn-life-1",
                                        "scope_labels": ["personal_reflection", "open_question"],
                                        "topic_terms": ["焦虑", "问题"],
                                        "source_refs": [
                                            {
                                                "thread_key": "session:life-wide",
                                                "message_id": "msg-life-1",
                                                "turn_id": "turn-life-1",
                                                "clean_ordinal": 4,
                                                "source_line": 77,
                                                "role": "user",
                                                "phase": "",
                                            }
                                        ],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近那个焦虑问题我后来有推进吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:life-wide")
        self.assertTrue(result["candidates"][0]["life_wide_timeline_source"])
        self.assertIn("personal_reflection", result["candidates"][0]["scope_labels"])
        self.assertNotIn("source_refs", result["candidates"][0])
        self.assertEqual(result["candidates"][0]["source_ref_count"], 1)
        self.assertIn("life-wide timeline", " ".join(result["reasons"]))

    def test_life_wide_timeline_does_not_trigger_for_ordinary_code_prompt(self) -> None:
        registry_path = self.root / "life-code-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "scope_label": "personal_reflection",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["焦虑"],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近帮我修 TypeScript build error，顺手跑测试",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_life_wide_timeline_does_not_trigger_for_generic_status_prompt(self) -> None:
        registry_path = self.root / "life-status-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "scope_label": "personal_reflection",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "scope_labels": ["personal_reflection", "open_question"],
                                        "topic_terms": ["焦虑", "问题"],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近这个问题的状态怎么样？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_life_wide_timeline_does_not_substring_match_lifecycle(self) -> None:
        registry_path = self.root / "life-english-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:life-wide",
                            "title": "Life continuity notes",
                            "project_label": "Journal",
                            "paths": {"workspace": str(self.root / "journal")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_path.parent / "project_timeline.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "life_wide": {
                        "labels": {
                            "life_context": {
                                "scope_label": "life_context",
                                "latest_turns": [
                                    {
                                        "thread_key": "session:life-wide",
                                        "scope_labels": ["life_context"],
                                        "topic_terms": ["life"],
                                    }
                                ],
                            }
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "latest lifecycle hook status",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_working_memory_can_emit_soft_scent_without_manual_review_queue(self) -> None:
        registry_path = self.root / "working-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:app",
                            "title": "T-Sense-App",
                            "project_label": "T-Sense",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        working = registry_path.parent / "working_memory.jsonl"
        working.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "confirm_when_relevant",
                    "ask_policy": "ask_only_when_current_action_would_depend_on_this_or_sources_conflict",
                    "risk": "high",
                    "candidate_type": "contradiction_review",
                    "title": "Jackie mutation consent gate",
                    "summary": "Jackie tool bridge mutations should require explicit user consent before Review card writes.",
                    "recommendation": "Ask only if implementing mutation behavior.",
                    "confidence": 0.7,
                    "project_label": "T-Sense",
                    "trigger_terms": ["Jackie", "mutation", "consent gate", "Review card"],
                    "source_refs": [
                        {"thread_key": "session:app", "title": "T-Sense-App", "line": 149}
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "Jackie mutation flow 现在怎么处理？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertTrue(result["working_memory"])
        context = hook.context_for_hook(result)
        self.assertIn("Soft working memory", context)
        self.assertIn("Ask the user only if", context)

    def test_concept_graph_expansion_can_surface_indirect_memory_scent(self) -> None:
        messages = self._write_clean_thread(
            "session:runtime-memory",
            "2026-05-25T00:00:00Z",
            "T-Sense 的 Go runtime spike 应该先验证 gotd，再决定是否迁移本地核心。",
        )
        registry_path = self.root / "concept-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:runtime-memory",
                            "title": "T-Sense Go runtime",
                            "project_label": "T-Sense",
                            "session_meta": {"timestamp": "2026-05-25T00:00:00Z"},
                            "paths": {"clean_source_messages_jsonl": str(messages)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        associations = registry_path.parent / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "本地底座": {
                            "term": "本地底座",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 100,
                            "related_terms": ["Go runtime"],
                            "threads": [],
                        },
                        "Go runtime": {
                            "term": "Go runtime",
                            "status": "staging",
                            "confidence": 1.0,
                            "hit_count": 100,
                            "related_terms": ["gotd"],
                            "threads": [],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        concept_graph_path = concept_graph.default_concept_graph_path(registry_path=registry_path)
        concept_graph.build_concept_graph(associations, concept_graph_path)

        without_graph = hook.assess_prompt(
            "本地底座换语言是不是更好？",
            cwd=self.workspace,
            registry_path=registry_path,
            associations_path=associations,
            use_concept_graph=False,
            search_budget=0,
        )
        with_graph = hook.assess_prompt(
            "本地底座换语言是不是更好？",
            cwd=self.workspace,
            registry_path=registry_path,
            associations_path=associations,
            concept_graph_path=concept_graph_path,
            search_budget=0,
        )

        self.assertEqual(without_graph["decision"], "skip")
        self.assertEqual(with_graph["decision"], "scent")
        self.assertEqual(with_graph["candidates"][0]["thread_key"], "session:runtime-memory")
        self.assertIn("Go runtime", with_graph["query_terms"])
        self.assertIn("concept graph expansion", " ".join(with_graph["reasons"]))

    def test_weak_deictic_cue_does_not_force_evidence(self) -> None:
        result = hook.assess_prompt(
            "这个外置海马体还要再收一下",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "scent")

    def test_goal_injection_prompt_stays_silent_even_with_registry_overlap(self) -> None:
        result = hook.assess_prompt(
            "Current goal for this thread: status ACTIVE, token budget remaining",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["candidates"])

    def test_explicit_memory_prompt_emits_evidence(self) -> None:
        result = hook.assess_prompt(
            "你还能找回之前那句生命还能变成什么，而我能不能还是我吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        context = hook.context_for_hook(result)
        self.assertIsNotNone(context)
        self.assertIn("Ambient recall evidence", context)
        self.assertIn("line 190", context)
        self.assertNotIn("line 999", context)
        self.assertIn("final_answer", context)

    def test_hook_json_uses_user_prompt_submit_additional_context(self) -> None:
        result = hook.assess_prompt(
            "你之前说过外置海马体为什么重要吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=2,
        )
        payload = hook.hook_stdout_payload(result)

        self.assertEqual(
            payload["hookSpecificOutput"]["hookEventName"],
            "UserPromptSubmit",
        )
        self.assertIn(
            "additionalContext",
            payload["hookSpecificOutput"],
        )


if __name__ == "__main__":
    unittest.main()
