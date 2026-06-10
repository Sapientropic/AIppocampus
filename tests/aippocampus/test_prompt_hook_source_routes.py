from __future__ import annotations

from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    hook,
    json,
    recall_cues,
)


class PromptHookSourceRouteTests(AmbientRecallHookCase):
    def test_current_checkout_fact_prompt_does_not_use_old_project_source_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:old-project-test-command",
            [
                {
                    "source_line": 58,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "OldProject 的测试命令是 pytest -q；这只适用于旧仓库。",
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:old-project-test-command",
            title="OldProject test command",
            keywords=["source-backed evidence", "测试命令", "pytest"],
            summary="OldProject used pytest -q as its test command.",
            messages_path=messages,
            project_label="OldProject",
        )

        result = hook.assess_prompt(
            "请给这个 repo 的 source-backed evidence：测试命令是什么？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertFalse(result["evidence"])
        self.assertIn("current checkout required", " ".join(result["reasons"]))
        self.assertIsNone(hook.context_for_hook(result))

    def test_russian_natural_recall_can_recover_source_evidence_without_semantic_gate(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:russian-natural-evidence",
            [
                {
                    "source_line": 73,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Мы описали внешний гиппокамп как trigger recall: "
                        "память всплывает только когда текущий вопрос дает устойчивый якорь."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:russian-natural-evidence",
            title="Внешний гиппокамп trigger recall",
            keywords=["внешний гиппокамп", "trigger recall", "устойчивый якорь"],
            summary="Русская формулировка про внешний гиппокамп и trigger recall.",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "Найди, как мы раньше формулировали внешний гиппокамп и trigger recall.",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("внешний гиппокамп", result["evidence"][0]["snippet"])

    def test_russian_prior_wording_recall_can_recover_source_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:russian-prior-wording",
            [
                {
                    "source_line": 91,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "Прежняя формулировка про raw history после сжатия: "
                        "история уже локальна, но после сжатия агент не знает, что искать."
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:russian-prior-wording",
            title="Прежняя формулировка raw history",
            keywords=["raw history", "прежняя формулировка", "сжатия"],
            summary="Русская формулировка про raw history после сжатия.",
            messages_path=messages,
        )
        prompt = "Найди прежнюю формулировку про raw history после сжатия."

        result = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertTrue(recall_cues.natural_evidence_intent(prompt))
        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("raw history", result["evidence"][0]["snippet"])

    def test_explicit_personal_pressure_recall_uses_source_evidence_boundary(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:pressure-prior-wording",
            [
                {
                    "source_line": 97,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "之前压力那段的结论：开源发布前先收窄验收口径，"
                        "保留一个可执行的下一步，不要把所有焦虑都变成待办。"
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:pressure-prior-wording",
            title="压力那段怎么说",
            keywords=["压力", "开源发布", "验收口径"],
            summary="之前压力那段说要收窄验收口径并保留可执行下一步。",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "我之前压力那段到底怎么说的？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertEqual(result["scent_threshold_policy"]["risk_boundary"], "personal_continuity")
        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertIn("开源发布前先收窄验收口径", result["evidence"][0]["snippet"])

    def test_scent_only_topic_can_be_explicitly_retrieved(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:scent-boundary",
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
            thread_key="session:scent-boundary",
            title="AIppocampus Atlas recall gate",
            keywords=["recall gate", "scent-only", "project-scoped"],
            summary="Prior work discussed the recall gate scent-only boundary.",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "recall gate 的 scent-only 边界找回。",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertFalse(recall_cues.negative_evidence_intent("recall gate 的 scent-only 边界找回。"))

    def test_natural_evidence_intent_upgrades_strong_scent_to_evidence(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:life-evidence",
            [
                {
                    "source_line": 88,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "结论：life-wide evidence 当前不够，应该写成 honest readiness gate，"
                        "不能把 semantic sidecar 命中当成已经证实。"
                    ),
                }
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:life-evidence",
            title="AIppocampus life-wide evidence",
            keywords=["life-wide evidence", "honest readiness gate", "semantic sidecar"],
            summary="Stage 2 life-wide evidence 不够，需要 honest readiness gate。",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "上次关于 life-wide evidence 不够的结论是什么？",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=2,
            use_semantic_gate=False,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertEqual(result["evidence"][0]["phase"], "final_answer")
        self.assertIn("honest readiness gate", result["evidence"][0]["snippet"])
        self.assertIn("natural evidence intent", " ".join(result["reasons"]))

    def test_evidence_quality_prefers_final_answer_over_subagent_process_noise(self) -> None:
        messages = self._write_clean_thread_rows(
            "session:ambient-loop",
            [
                {
                    "source_line": 41,
                    "role": "user",
                    "phase": "",
                    "is_final": False,
                    "text": (
                        "<subagent_notification> ambient recall ambient recall ambient recall "
                        "闭环 闭环 hook cache evidence process details only </subagent_notification>"
                    ),
                },
                {
                    "source_line": 120,
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "ambient recall 闭环是 UserPromptSubmit hook 到 cache 再到 evidence 的运行链路。",
                },
            ],
        )
        registry_path = self._write_clean_registry(
            thread_key="session:ambient-loop",
            title="Ambient recall loop",
            keywords=["ambient recall", "闭环", "hook", "cache", "evidence"],
            summary="讨论 ambient recall hook/cache/evidence 闭环。",
            messages_path=messages,
        )

        result = hook.assess_prompt(
            "找一下之前说 ambient recall 闭环的那段",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=1,
            use_semantic_gate=False,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["evidence"])
        self.assertEqual(result["evidence"][0]["line"], 120)
        self.assertNotIn("<subagent_notification>", result["evidence"][0]["snippet"])

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

