from __future__ import annotations

# aippocampus-instruction-surface: semantic-gate prompt-hook test fixtures; prompt strings are test contracts, not runtime instructions.
from aippocampus_runtime.recall.prompt_recall_result_tiers import result_hot_path_funnel
from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    cue_cache,
    fake_test_windows_path,
    hook,
    json,
    recall_cues,
)


class PromptHookSemanticGateTests(AmbientRecallHookCase):
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
                "model_route": {"provider": "test-provider", "model": "test-model"},
                "cache_diagnostics": {"lookup": "disabled"},
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

    def test_semantic_vague_cue_without_route_still_renders_agent_affordance(self) -> None:
        context = hook.context_for_hook(
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [],
                "evidence": [],
                "working_memory": [],
                "semantic_gate": {
                    "available": True,
                    "decision": "scent",
                    "confidence": 0.85,
                    "query_aliases": [],
                    "memory_scope": [],
                },
            }
        )

        self.assertIsNotNone(context)
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn("Next: call agent_recall", context)
        self.assertIn("No source route was opened", context)

    def test_semantic_positive_can_bridge_to_sqlite_when_registry_metadata_misses(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Unlabeled external project handoff",
            keywords=["handoff"],
            summary="A sparse registry row whose clean source has richer recall terms.",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.9,
                "intent": "recall",
                "query_aliases": ["raw history", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["semantic route found source terms absent from metadata"],
                "workers": [],
                "errors": [],
                "cached": False,
                "model_route": {"provider": "test-provider", "model": "test-model"},
                "cache_diagnostics": {"lookup": "disabled"},
            }

        result = hook.assess_prompt(
            "那个外部项目后来到底卡在哪里？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertTrue(result["candidates"])
        self.assertTrue(result["candidates"][0]["fallback"])
        self.assertGreater(result["candidates"][0]["probe_score"], 0)
        self.assertIn("semantic gate", " ".join(str(reason) for reason in result["reasons"]))

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

    def test_semantic_gate_alias_hits_are_recorded_as_reusable_cues(self) -> None:
        registry_path = self.root / "semantic-cue-registry" / "threads.json"
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
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa", "внешний гиппокамп"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "semantic_cues.jsonl"

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.9,
                "intent": "continuation",
                "query_aliases": ["memoria externa", "внешний гиппокамп"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["multilingual paraphrase of the memory-system thread"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Podemos continuar esa memoria externa para mantener la continuidad?",
        ):
            result = hook.assess_prompt(
                prompt,
                cwd=self.workspace,
                registry_path=registry_path,
                semantic_gate_fn=fake_semantic_gate,
                semantic_cues_path=cues_path,
                search_budget=0,
            )
            self.assertEqual(result["decision"], "scent")

        triggers = cue_cache.semantic_cue_triggers(cues_path)
        aliases = {alias for trigger in triggers for alias in trigger.get("aliases") or []}
        self.assertIn("memoria externa", aliases)
        self.assertIn("внешний гиппокамп", aliases)

    def test_background_only_semantic_alias_hits_can_warm_reusable_cues(self) -> None:
        registry_path = self.root / "semantic-background-cue-registry" / "threads.json"
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
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa", "внешний гиппокамп"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "background_semantic_cues.jsonl"

        def background_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "background_only",
                "confidence": 0.9,
                "intent": "continuation",
                "query_aliases": ["memoria externa", "внешний гиппокамп"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["high-confidence aliases, but scent not needed for this run"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        cue_reports = []
        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Puedes continuar esa memoria externa para mantener la continuidad?",
        ):
            result = hook.assess_prompt(
                prompt,
                cwd=self.workspace,
                registry_path=registry_path,
                semantic_gate_fn=background_semantic_gate,
                semantic_cues_path=cues_path,
                search_budget=0,
            )
            self.assertEqual(result["semantic_gate"]["decision"], "background_only")
            self.assertNotIn("semantic_cue_cache", result)
            cue_reports.append(cue_cache.semantic_cue_cache_report(cues_path))

        self.assertEqual(cue_reports[0]["active_count"], 0)
        self.assertGreater(cue_reports[1]["active_count"], 0)

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active background semantic cues should avoid live semantic spend")

        result = hook.assess_prompt(
            "¿Seguimos con esa memoria externa de continuidad?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fail_semantic_gate,
            semantic_cues_path=cues_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("memoria externa", result["query_terms"])
        self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_active_semantic_cue_cache_can_emit_scent_without_semantic_gate(self) -> None:
        registry_path = self.root / "active-semantic-cue-registry" / "threads.json"
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
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "active_semantic_cues.jsonl"
        semantic_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.9,
            "query_aliases": ["memoria externa"],
        }
        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Podemos continuar esa memoria externa para mantener la continuidad?",
        ):
            cue_cache.record_semantic_cue_hits(
                cues_path,
                prompt=prompt,
                semantic_result=semantic_result,
                source_refs=[{"thread_key": "session:aippocampus", "message_id": "m1"}],
                route="semantic_gate",
            )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active semantic cue cache should avoid live semantic spend")

        result = hook.assess_prompt(
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_cues_path=cues_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
            detail="detail",
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("memoria externa", result["query_terms"])
        self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_living_cue_cache_default_hook_emits_scent_without_leaking_private_cue(self) -> None:
        living_cues = self.registry.parent / "living_cue_cache.jsonl"
        living_cues.write_text(
            json.dumps(
                {
                    "cue": "private canonical tree bridge",
                    "aliases": ["tree problem"],
                    "source_refs": [
                        {
                            "source_id": "clean:tree:m7",
                            "thread_key": "session:test-old",
                            "message_id": "m7",
                            "line": 14,
                            "snippet": "raw private source text must not leak",
                            "path": fake_test_windows_path("private-tree-messages.jsonl"),
                        }
                    ],
                    "confidence": 0.94,
                    "sensitivity": "safe",
                    "freshness": "current",
                    "status": "current",
                    "last_helpful_count": 2,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "Can we continue that tree problem from before?",
            cwd=self.workspace,
            registry_path=self.registry,
            use_semantic_gate=False,
            search_budget=0,
            detail="trace",
        )
        public = hook.public_hook_debug_payload(result)
        encoded_public = json.dumps(public, ensure_ascii=False, sort_keys=True)
        context = hook.context_for_hook(result) or ""
        encoded_context = json.dumps(context, ensure_ascii=False)

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("living cue cache", " ".join(result["reasons"]))
        self.assertEqual(result["candidates"][0]["thread_key"], "session:test-old")
        hot_path = result_hot_path_funnel(result)
        self.assertEqual(
            hot_path["living_cue_cache"]["diagnostics"]["live_llm_call_count"],
            0,
        )
        self.assertEqual(
            public["hot_path_funnel"]["living_cue_cache"]["selected_count"],
            1,
        )
        self.assertIn("Ambient recall scent", context)
        self.assertNotIn("private canonical tree bridge", encoded_public + encoded_context)
        self.assertNotIn("raw private source text", encoded_public + encoded_context)
        self.assertNotIn("private-tree", encoded_public + encoded_context)

    def test_active_semantic_cue_hit_skips_cold_foreground_semantic_call(self) -> None:
        registry_path = self.root / "semantic-cue-skip-live-registry" / "threads.json"
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
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa", "conversation continuity"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.old), "sqlite": str(self.sqlite)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "semantic_cue_skip_live.jsonl"
        semantic_result = {
            "available": True,
            "decision": "background_only",
            "confidence": 0.9,
            "query_aliases": ["memoria externa"],
            "memory_scope": ["registered_threads"],
        }
        for prompt in (
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            "¿Puedes continuar esa memoria externa para mantener la continuidad?",
        ):
            cue_cache.record_semantic_cue_hits(
                cues_path,
                prompt=prompt,
                semantic_result=semantic_result,
                source_refs=[{"thread_key": "session:aippocampus", "message_id": "m1"}],
                route="semantic_gate",
            )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active semantic cue hit should avoid a cold foreground model call")

        result = hook.assess_prompt(
            "¿Seguimos con esa memoria externa de continuidad?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_cues_path=cues_path,
            semantic_gate_fn=fail_semantic_gate,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertEqual(result["semantic_gate_reuse"]["source"], "semantic_cue_cache")
        self.assertTrue(result["semantic_gate_reuse"]["semantic_cue_hit"])
        self.assertFalse(result["semantic_gate_reuse"]["cold_model_call"])
        self.assertIn("memoria externa", result["query_terms"])

    def test_active_non_latin_semantic_cues_emit_scent_without_live_semantic(self) -> None:
        registry_path = self.root / "nonlatin-semantic-cue-registry" / "threads.json"
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
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["external hippocampus", "conversation continuity"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cues_path = self.root / "nonlatin_semantic_cues.jsonl"
        semantic_result = {
            "available": True,
            "decision": "scent",
            "confidence": 0.9,
            "query_aliases": [
                "внешний гиппокамп",
                "الحُصين الخارجي",
                "外部海馬",
                "외부 해마",
                "ฮิปโปแคมปัสภายนอก",
            ],
        }
        for _ in range(2):
            cue_cache.record_semantic_cue_hits(
                cues_path,
                prompt="synthetic multilingual continuity cue",
                semantic_result=semantic_result,
                source_refs=[{"thread_key": "session:aippocampus", "message_id": "m1"}],
                route="semantic_gate",
            )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("active semantic cues should avoid live semantic spend")

        prompts = [
            "Как там мой внешний гиппокамп памяти и продолжение разговоров?",
            "كيف حال الحُصين الخارجي للذاكرة واستمرار المحادثات؟",
            "外部海馬みたいな記憶システムの進捗はどう？",
            "외부 해마 같은 기억 시스템은 지금 어떻게 되고 있어?",
            "ระบบความจำแบบฮิปโปแคมปัสภายนอกตอนนี้เป็นอย่างไรบ้าง",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = hook.assess_prompt(
                    prompt,
                    cwd=self.workspace,
                    registry_path=registry_path,
                    semantic_cues_path=cues_path,
                    semantic_gate_fn=fail_semantic_gate,
                    use_semantic_gate=False,
                    search_budget=0,
                )

                self.assertEqual(result["decision"], "scent")
                self.assertEqual(result["candidates"][0]["thread_key"], "session:aippocampus")
                self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_reviewed_semantic_trigger_can_emit_scent_without_hardcoded_cue(self) -> None:
        registry_path = self.root / "reviewed-semantic-trigger-registry" / "threads.json"
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
                            "anchor_titles": ["External hippocampus recall"],
                            "keywords": ["memoria externa"],
                            "summary": "Source-backed continuity work for external memory.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "reviewed_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "External memory continuation",
                    "aliases": ["memoria externa"],
                    "confidence": 0.91,
                    "when_to_use": "Use when the user asks in Spanish about the external memory thread.",
                    "source_refs": [{"thread_key": "session:aippocampus", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("reviewed semantic trigger should avoid live semantic spend")

        result = hook.assess_prompt(
            "¿Podemos seguir con la memoria externa de la que hablamos?",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
            detail="detail",
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIsNone(result["semantic_gate"])
        self.assertIn("memoria externa", result["query_terms"])
        self.assertIn("associative cue", " ".join(result["reasons"]))

    def test_reviewed_semantic_trigger_source_refs_wake_sparse_registry_candidate(self) -> None:
        registry_path = self.root / "source-ref-semantic-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:friction",
                            "title": "Recovered sidecar-backed source thread",
                            "project_label": "Life-wide continuity",
                            "anchor_titles": [],
                            "keywords": [],
                            "summary": "No lexical overlap with the natural prompt or trigger aliases.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "source_ref_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Subconscious friction recall route",
                    "aliases": [
                        "最近让我很烦",
                        "recent personal friction",
                        "что меня раздражало недавно",
                    ],
                    "confidence": 0.93,
                    "when_to_use": "Use when subconscious review linked a natural annoyance/friction prompt to this source thread.",
                    "source_refs": [
                        {
                            "thread_key": "session:friction",
                            "title": "Recovered sidecar-backed source thread",
                            "message_id": "m-friction",
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("reviewed source refs should provide a local sidecar route")

        result = hook.assess_prompt(
            "最近让我很烦的那个点后来怎么处理来着？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
            detail="detail",
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["thread_key"], "session:friction")
        self.assertTrue(result["candidates"][0]["semantic_trigger_source"])
        self.assertIn("最近让我很烦", result["query_terms"])

    def test_reviewed_semantic_trigger_ignores_generic_source_ref_issue_prompt_terms(self) -> None:
        registry_path = self.root / "generic-spillover-semantic-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:detached-alias",
                            "title": "Garden planning notebook",
                            "project_label": "Home planning",
                            "anchor_titles": [],
                            "keywords": ["balcony planting"],
                            "summary": "A sparse row for unrelated household planning notes.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "generic_spillover_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Source ref issue route",
                    "aliases": ["detached alias"],
                    "confidence": 0.9,
                    "when_to_use": (
                        "Use when the user asks about source refs, candidate issues, "
                        "or route context."
                    ),
                    "source_refs": [{"thread_key": "session:detached-alias", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("generic trigger prompt terms should not require live semantic spend")

        result = hook.assess_prompt(
            "候选 source refs 的中间层和过度保守这个问题，是不是已经有 issue 了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
            detail="detail",
        )

        self.assertEqual(result["decision"], "skip")
        self.assertIsNone(result["semantic_gate"])
        self.assertFalse(result["candidates"])
        self.assertIsNone(hook.context_for_hook(result))
        public = hook.public_hook_debug_payload(result)
        delivery = public["route_delivery_diagnostic"]
        self.assertEqual(delivery["foreground_route_profile"], "generic_recall_meta")
        self.assertGreater(delivery["generic_prompt_term_count"], 0)
        self.assertEqual(
            delivery["semantic_trigger_generic_term_suppressed_count"],
            delivery["generic_prompt_term_count"],
        )
        self.assertIn("generic_meta_terms_only", delivery["foreground_suppression_reasons"])

    def test_reviewed_semantic_trigger_does_not_turn_plain_code_task_into_recall(self) -> None:
        registry_path = self.root / "code-surface-semantic-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:dashboard",
                            "title": "Dashboard design memory",
                            "project_label": "Product UI",
                            "anchor_titles": ["Dashboard hover behavior"],
                            "keywords": ["dashboard", "hover"],
                            "summary": "Prior source-backed dashboard decisions.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "code_surface_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Dashboard memory",
                    "aliases": ["dashboard"],
                    "confidence": 0.91,
                    "when_to_use": "Use when the user asks to recall the dashboard decision.",
                    "source_refs": [{"thread_key": "session:dashboard", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("plain code-surface tasks should stay local and quiet")

        result = hook.assess_prompt(
            "Fix the dashboard hover test and update the CSS.",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["semantic_gate"], None)

    def test_reviewed_semantic_trigger_can_scent_code_surface_continuation(self) -> None:
        registry_path = self.root / "code-surface-continuation-trigger-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:atlas",
                            "title": "Atlas dashboard memory",
                            "project_label": "Atlas dashboard",
                            "anchor_titles": ["Atlas dashboard layout sprint"],
                            "keywords": ["Atlas dashboard", "layout", "sprint"],
                            "summary": "Prior source-backed dashboard layout context.",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        triggers_path = self.root / "code_surface_continuation_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "Atlas dashboard continuation",
                    "aliases": ["Atlas dashboard", "layout sprint"],
                    "confidence": 0.91,
                    "when_to_use": "Use when the user asks to continue the Atlas dashboard context.",
                    "when_not_to_use": "Do not use for plain implementation tasks.",
                    "source_refs": [{"thread_key": "session:atlas", "message_id": "m1"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_semantic_gate(*args, **kwargs) -> dict:
            raise AssertionError("reviewed trigger should provide local continuation scent")

        result = hook.assess_prompt(
            "Fix Atlas dashboard layout, but only continue that context; do not implement.",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_triggers_path=triggers_path,
            semantic_gate_fn=fail_semantic_gate,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertTrue(
            any(
                "atlas" in str(term).casefold() and "dashboard" in str(term).casefold()
                for term in result["query_terms"]
            )
        )
        self.assertIn("associative cue", " ".join(result["reasons"]))
