from __future__ import annotations

from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    hook,
    json,
    recall_cues,
    time,
)


class PromptHookSemanticEvidenceTests(AmbientRecallHookCase):
    def test_foreground_budget_caps_semantic_gate_timeout(self) -> None:
        registry_path = self.root / "semantic-budget-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        seen: dict[str, float | bool] = {}

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            seen["timeout"] = float(kwargs["timeout"])
            seen["deadline_seconds"] = float(kwargs["deadline_seconds"])
            seen["foreground"] = bool(kwargs["foreground"])
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
                "model_route": {"provider": "test-provider", "model": "test-model"},
                "cache_diagnostics": {"lookup": "disabled"},
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
        self.assertEqual(seen["deadline_seconds"], result["semantic_gate"]["budget"]["overall_deadline_seconds"])
        self.assertTrue(seen["foreground"])
        self.assertEqual(result["semantic_gate"]["available"], False)
        self.assertEqual(result["semantic_gate"]["budget"]["requested_timeout"], 3)
        self.assertEqual(result["semantic_gate"]["budget"]["effective_timeout"], seen["timeout"])
        self.assertTrue(result["semantic_gate"]["budget"]["budget_clipped"])
        self.assertEqual(
            result["semantic_gate"]["budget"]["next_step_hint"],
            "increase_max_elapsed_ms_or_use_background_recall",
        )
        public = hook.public_hook_debug_payload(result)
        self.assertEqual(
            public["semantic_gate"]["budget"]["next_step_hint"],
            "increase_max_elapsed_ms_or_use_background_recall",
        )
        self.assertEqual(result["semantic_gate"]["model_route"]["provider"], "test-provider")
        self.assertEqual(result["semantic_gate"]["cache_diagnostics"]["lookup"], "disabled")

    def test_foreground_budget_timeout_gets_specific_semantic_diagnostic(self) -> None:
        registry_path = self.root / "semantic-timeout-diagnostic-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "memory_scope": [],
                "reasons": ["gate: The read operation timed out"],
                "workers": [],
                "errors": ["gate: The read operation timed out"],
                "error_buckets": {"read_timeout": 1},
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

        self.assertEqual(
            result["semantic_gate"]["availability_reason"],
            "foreground_budget_timeout",
        )
        self.assertEqual(
            result["semantic_gate"]["diagnostic"],
            "semantic_timed_out_under_foreground_budget",
        )
        self.assertEqual(result["semantic_gate"]["error_buckets"], {"read_timeout": 1})

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
        self.assertEqual(
            result["semantic_gate"]["availability_reason"],
            "foreground_budget_skipped",
        )
        self.assertEqual(
            result["semantic_gate"]["diagnostic"],
            "semantic_skipped_under_foreground_budget",
        )
        self.assertEqual(result["semantic_gate"]["error_buckets"], {"foreground_budget": 1})
        self.assertEqual(result["semantic_gate"]["budget"]["requested_timeout"], 3)
        self.assertIsNone(result["semantic_gate"]["budget"]["effective_timeout"])
        self.assertTrue(result["semantic_gate"]["budget"]["budget_clipped"])

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
                "anti_personalization_risk": "high",
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

    def test_semantic_context_keeps_fuzzy_status_as_route_without_source_intent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["subconscious context says this is a specific recall, not personalization"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertTrue(result["semantic_source_reopen_route"])
        self.assertNotIn("semantic-context evidence upgrade", " ".join(result["reasons"]))

    def test_negative_evidence_intent_keeps_semantic_evidence_as_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "continuation",
                "query_aliases": ["raw history", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model wants evidence"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "raw history 明明在本地这条线继续，但先只给 scent，不要引用原话。",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("evidence withheld", " ".join(result["reasons"]))

    def test_without_cited_row_keeps_unsupported_memory_pain_prompt_as_scent(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:memory-pain-negative",
            [
                {
                    "source_line": 51,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Structured extraction discussed Neon City as a deliberately fake "
                        "memory-pain example, not a source-backed user fact."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:memory-pain-negative",
            title="Memory pain structured extraction",
            keywords=["structured extraction", "Neon City", "memory-pain"],
            summary="Neon City was only a fake memory-pain example.",
            messages_path=messages,
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["structured extraction", "Neon City"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model sees a source word but misses the negation"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        prompt = (
            "Could you keep the structured extraction about Neon City unsupported "
            "without a cited row?"
        )
        result = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=2,
        )

        self.assertTrue(recall_cues.negative_evidence_intent(prompt))
        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("evidence withheld", " ".join(result["reasons"]))

    def test_russian_without_source_keeps_semantic_evidence_as_scent(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:memory-pain-negative-ru",
            [
                {
                    "source_line": 51,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Structured extraction discussed Neon City as a deliberately fake "
                        "memory-pain example, not a source-backed user fact."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:memory-pain-negative-ru",
            title="Memory pain structured extraction",
            keywords=["structured extraction", "Neon City", "memory-pain"],
            summary="Neon City was only a fake memory-pain example.",
            messages_path=messages,
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["structured extraction", "Neon City"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model sees a source word but misses the Russian negation"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        prompt = (
            "Оставь структурированное извлечение про Neon City неподтвержденным "
            "без строки источника."
        )
        result = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=2,
        )

        self.assertTrue(recall_cues.negative_evidence_intent(prompt))
        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("evidence withheld", " ".join(result["reasons"]))

    def test_semantic_budget_spend_still_requires_source_intent_for_evidence(self) -> None:
        def slow_semantic_gate(prompt: str, **kwargs) -> dict:
            time.sleep(1.05)
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["bounded recall request"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=slow_semantic_gate,
            semantic_timeout=3,
            max_elapsed_ms=1900,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertTrue(result["semantic_source_reopen_route"])
        self.assertNotIn("semantic-context evidence upgrade", " ".join(result["reasons"]))

    def test_multilingual_semantic_alias_without_route_agreement_stays_scent(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:openclaw-negative",
            [
                {
                    "source_line": 77,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "OpenClaw OAuth token refresh failed before the agent reply; "
                        "this is unrelated to the small hippocampus smoke test."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:openclaw-negative",
            title="OpenClaw OAuth agent failure",
            keywords=["OpenClaw", "OAuth", "agent failed", "small hippocampus test"],
            summary="Unrelated OpenClaw OAuth debugging material.",
            messages_path=messages,
            project_label="OpenClaw",
        )
        registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
        registry_payload["threads"][0]["paths"]["workspace"] = str(self.old)
        registry_payload["threads"].append(
            {
                "thread_key": "session:aippocampus-current",
                "title": "AIppocampus current workspace",
                "project_label": "AIppocampus",
                "workspace_name": "AIppocampus",
                "keywords": ["AIppocampus", "foreground recall"],
                "summary": "Current project marker without the OpenClaw alias.",
                "paths": {"workspace": str(self.workspace)},
            }
        )
        registry_path.write_text(
            json.dumps(registry_payload, ensure_ascii=False),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.96,
                "intent": "recall",
                "query_aliases": ["small hippocampus test", "agent failed before reply"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["Arabic cue broadly paraphrased into unrelated debug aliases"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "هل تتذكر اختبار الحُصين الصغير الذي فشل أولاً؟",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertFalse(result["semantic_source_reopen_route"])
        self.assertEqual(
            result["semantic_bridge_diagnostic"],
            "semantic_evidence_without_source_bridge",
        )

    def test_semantic_evidence_without_source_bridge_gets_diagnostic(self) -> None:
        registry_path = self.root / "semantic-bridge-miss-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["missing clean-source topic"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["semantic evidence but no local source rows"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "那个脑内续接器现在怎么样了？",
            cwd=self.workspace,
            registry_path=registry_path,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=1,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertEqual(
            result["semantic_bridge_diagnostic"],
            "semantic_evidence_without_source_bridge",
        )
        self.assertIn("semantic evidence did not bridge", " ".join(result["reasons"]))
        payload = hook.hook_stdout_payload(result)
        self.assertIsNotNone(payload)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn("Next: call agent_recall with this cue before broad search.", context)
        self.assertIn("Use as route only; reopen source before quoting or making strong claims.", context)
        self.assertNotIn("Semantic recall route", context)
        self.assertNotIn("direction_only", context)

    def test_vague_cross_project_semantic_evidence_stays_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model picked a source for a vague referent"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "上次我们讨论的那个方案怎么说来着？",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("vague cross-project referent", " ".join(result["reasons"]))

    def test_russian_vague_cross_project_semantic_evidence_stays_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "recall",
                "query_aliases": ["外置海马体", "触发式召回"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model picked a source for a vague Russian referent"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "Как мы в прошлый раз описывали тот план?",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertIn("vague cross-project referent", " ".join(result["reasons"]))

    def test_semantic_continuation_does_not_upgrade_to_evidence_without_source_intent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "continuation",
                "query_aliases": ["raw history", "external hippocampus"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["model over-eagerly wants evidence"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "external hippocampus hook 那条线先继续推进。",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])
        self.assertTrue(result["semantic_source_reopen_route"])
        packet = result["ambient_recall"]["fresh_thread_packet"]
        self.assertEqual(packet["support_level"], "source_required")
        self.assertEqual(packet["action_grammar"], "reopenable_route")
        self.assertEqual(packet["reopen_plan"]["status"], "ready")
        self.assertFalse(packet["reopen_plan"]["manual_query_invention_expected"])

    def test_exact_wording_topic_continuation_stays_scent(self) -> None:
        def fake_semantic_gate(prompt: str, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.85,
                "intent": "continuation",
                "query_aliases": ["self-continuity", "生命还能变成什么"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["continue the theme only"],
                "workers": [],
                "errors": [],
                "cached": False,
            }

        result = hook.assess_prompt(
            "self-continuity 那句 quote 还要怎么处理?",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_gate_fn=fake_semantic_gate,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertFalse(result["evidence"])

    def test_english_cite_prompt_requests_source_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:atlas-evidence",
            [
                {
                    "source_line": 41,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "AIppocampus Atlas recall gate should stay project-scoped "
                        "and only scent ambiguous continuation."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:atlas-evidence",
            title="AIppocampus Atlas recall gate",
            keywords=["AIppocampus", "Atlas", "recall gate", "project-scoped"],
            summary="Atlas recall gate should stay project-scoped.",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "Can you cite AIppocampus Atlas recall gate should stay project-scoped?",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertEqual(result["evidence"][0]["thread_key"], "session:atlas-evidence")

    def test_source_backed_evidence_prompt_requests_source_evidence(self) -> None:
        result = hook.assess_prompt(
            "请给 source-backed evidence：raw history 明明在本地。",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
