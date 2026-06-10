from __future__ import annotations

from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    hook,
    json,
)


class PromptHookRoutingScentTests(AmbientRecallHookCase):
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
        self.assertIn("action: direction_only", context)
        self.assertIn("can_use: orientation only", context)
        self.assertIn("must_reopen_for: exact quotes", context)
        self.assertNotIn("Ambient recall private context", context)
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

    def test_profile_recall_uses_cross_lingual_aliases_without_semantic_gate(self) -> None:
        registry_path = self._write_single_thread_registry(
            title="Professional profile and job search history",
            keywords=["CV", "LinkedIn", "job search", "professional profile"],
            summary=(
                "Prior records discuss the user's resume, CV, LinkedIn profile, "
                "and job-search materials."
            ),
        )

        result = hook.assess_prompt(
            "你知道我的简历和领英资料吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertIn("resume", result["query_terms"])
        self.assertIn("LinkedIn", result["query_terms"])
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["candidates"][0]["title"], "Professional profile and job search history")

    def test_recent_work_friction_prompt_uses_life_wide_timeline_route(self) -> None:
        registry_dir = self.root / "life-wide-registry"
        registry_dir.mkdir()
        registry_path = registry_dir / "threads.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:work-friction",
                            "title": "Product workflow friction",
                            "workspace_name": "OtherProject",
                            "project_label": "OtherProject",
                            "updated_at": "2026-05-24T12:00:00Z",
                            "anchor_titles": ["Workflow friction and product pressure"],
                            "keywords": ["workflow friction", "product pressure"],
                            "summary": (
                                "Old English and Russian project notes about product "
                                "workflow friction and pressure."
                            ),
                            "paths": {"workspace": str(self.old)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_dir / "project_timeline.json").write_text(
            json.dumps(
                {
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "latest_turns": [
                                    {
                                        "thread_key": "session:work-friction",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["workflow friction", "product pressure"],
                                        "source_refs": [
                                            {"thread_key": "session:work-friction", "source_line": 91}
                                        ],
                                    }
                                ]
                            }
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近工作上那些摩擦和困扰，我们后来怎么处理比较好？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["candidates"][0]["title"], "Product workflow friction")
        self.assertTrue(result["candidates"][0]["life_wide_timeline_source"])
        self.assertEqual(result["evidence"], [])

    def test_vague_life_wide_prompt_returns_multiple_timeline_routes(self) -> None:
        registry_dir = self.root / "life-wide-multilingual-registry"
        registry_dir.mkdir()
        registry_path = registry_dir / "threads.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:english-friction",
                            "title": "English workflow friction",
                            "project_label": "Ops",
                            "updated_at": "2026-05-25T12:00:00Z",
                            "keywords": ["workflow friction", "product pressure"],
                            "summary": "English notes about product workflow friction.",
                            "paths": {"workspace": str(self.old)},
                        },
                        {
                            "thread_key": "session:russian-burnout",
                            "title": "Russian burnout notes",
                            "project_label": "Journal",
                            "updated_at": "2026-05-24T12:00:00Z",
                            "keywords": ["рабочее давление", "burnout"],
                            "summary": "Russian notes about work pressure and burnout.",
                            "paths": {"workspace": str(self.root / "journal")},
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (registry_dir / "project_timeline.json").write_text(
            json.dumps(
                {
                    "life_wide": {
                        "labels": {
                            "personal_reflection": {
                                "latest_turns": [
                                    {
                                        "thread_key": "session:english-friction",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["workflow friction", "product pressure"],
                                        "source_refs": [
                                            {
                                                "thread_key": "session:english-friction",
                                                "source_line": 91,
                                            }
                                        ],
                                    },
                                    {
                                        "thread_key": "session:russian-burnout",
                                        "scope_labels": ["personal_reflection"],
                                        "topic_terms": ["рабочее давление", "burnout"],
                                        "source_refs": [
                                            {
                                                "thread_key": "session:russian-burnout",
                                                "source_line": 52,
                                            }
                                        ],
                                    },
                                ]
                            }
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "最近工作上那些摩擦和压力，我们后来怎么处理比较好？",
            cwd=self.workspace,
            registry_path=registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        candidate_keys = [candidate["thread_key"] for candidate in result["candidates"]]
        self.assertIn("session:english-friction", candidate_keys)
        self.assertIn("session:russian-burnout", candidate_keys)
        self.assertTrue(all(candidate["life_wide_timeline_source"] for candidate in result["candidates"][:2]))
        self.assertEqual(result["evidence"], [])

    def test_explicit_continuation_with_exact_terms_can_scent_without_semantic(self) -> None:
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

        self.assertEqual(result["decision"], "scent")
        self.assertGreaterEqual(result["score"], hook.SCENT_THRESHOLD)
        self.assertEqual(result["candidates"][0]["thread_key"], "session:single-thread")
        self.assertFalse(result["evidence"])

