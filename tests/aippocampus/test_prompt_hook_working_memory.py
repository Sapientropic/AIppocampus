from __future__ import annotations

from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    concept_graph,
    hook,
    json,
    recall_cues,
    thread_cache,
)


class PromptHookWorkingMemoryTests(AmbientRecallHookCase):
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

    def test_same_thread_continuation_can_lower_scent_threshold_for_weak_route(self) -> None:
        registry_path = self.root / "threshold-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:threshold",
                            "title": "Quiet support",
                            "summary": "qa",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "qa 现在怎么看，这个很重要",
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-123",
            topic_epoch="epoch-stable",
            use_thread_cache=False,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "scent")
        self.assertLess(
            result["scent_threshold_policy"]["effective_threshold"],
            result["scent_threshold_policy"]["base_threshold"],
        )
        self.assertEqual(
            result["scent_threshold_policy"]["adjustments"][0]["reason"],
            "same_thread_decision_continuation",
        )

    def test_topic_signal_accumulator_can_surface_later_weak_route(self) -> None:
        registry_path = self.root / "topic-signal-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:topic-signal",
                            "title": "Quiet support",
                            "summary": "qa",
                            "keywords": ["qa"],
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cache_path = self.root / "topic-signal-cache.json"
        prompt = "qa 现在怎么看"

        baseline = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-123",
            topic_epoch="epoch-signal",
            ambient_cache_path=cache_path,
            use_thread_cache=False,
            use_semantic_gate=False,
            search_budget=0,
        )
        signal_path = thread_cache.signal_accumulator_path_for_cache(cache_path)
        for _ in range(2):
            thread_cache.record_topic_signal(
                signal_path,
                thread_id="thread-123",
                workspace=str(self.workspace),
                topic_epoch="epoch-signal",
                terms=recall_cues.expand_query_terms(prompt),
                outcome="weak_signal",
                reason_codes=["below_threshold"],
            )

        later = hook.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-123",
            topic_epoch="epoch-signal",
            ambient_cache_path=cache_path,
            use_thread_cache=False,
            use_semantic_gate=False,
            search_budget=0,
        )
        raw = signal_path.read_text(encoding="utf-8")

        self.assertEqual(baseline["decision"], "skip")
        self.assertEqual(later["decision"], "scent")
        self.assertIn(
            "topic_signal_accumulator_eased",
            {
                item["reason"]
                for item in later["scent_threshold_policy"]["adjustments"]
            },
        )
        self.assertIn("same-topic recall signal crossed routing threshold", later["reasons"])
        self.assertGreaterEqual(
            later["scent_threshold_policy"]["topic_signal_accumulator"]["weak_signal_count"],
            3,
        )
        self.assertNotIn(prompt, raw)
        self.assertNotIn(str(self.workspace).replace("\\", "/"), raw.replace("\\", "/"))

    def test_broad_fresh_personal_prompt_uses_continuity_boundary(self) -> None:
        registry_path = self.root / "fresh-personal-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:threshold",
                            "title": "Quiet support",
                            "summary": "qa",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "我压力有点大，qa 很重要",
            cwd=self.workspace,
            registry_path=registry_path,
            search_budget=0,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertEqual(
            result["scent_threshold_policy"]["effective_threshold"],
            result["scent_threshold_policy"]["base_threshold"],
        )
        self.assertEqual(result["scent_threshold_policy"]["risk_boundary"], "personal_continuity")

    def test_dream_hypothesis_working_memory_renders_uncertainty_boundary(self) -> None:
        registry_path = self.root / "dream-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:dream",
                            "title": "Dream bridge",
                            "project_label": "AIppocampus",
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
                    "route": "use_with_source",
                    "ask_policy": "do_not_ask_unless_contradicted_or_action_depends_on_uncertain_scope",
                    "risk": "medium",
                    "candidate_type": "dream_hypothesis",
                    "title": "Continuity dream bridge",
                    "summary": "A dream hypothesis about continuity and source refs.",
                    "recommendation": "Use quietly; reopen source before strong claims.",
                    "confidence": 0.66,
                    "project_label": "AIppocampus",
                    "trigger_terms": ["continuity", "source refs"],
                    "source_refs": [
                        {
                            "thread_key": "session:dream",
                            "title": "Dream bridge",
                            "message_id": "msg-dream",
                            "line": 12,
                        }
                    ],
                    "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
                    "review_state": "agent_adjudicated",
                    "foreground_use": {
                        "default_action": "quiet_substrate",
                        "strong_claim_requires_source_reopen": True,
                    },
                    "sensitive_use_gate": {"state": "allowed"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = hook.assess_prompt(
            "AIppocampus continuity source refs 这条线索还在吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            search_budget=0,
        )

        context = hook.context_for_hook(result)
        self.assertIn("Dream hypothesis, not source fact", context)
        self.assertIn("reopen source", context)
        self.assertIn("Use quietly", context)

    def test_working_memory_question_scent_obeys_cap_and_stop_tracking(self) -> None:
        registry_path = self.root / "question-working-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:alignment",
                            "title": "Alignment thread",
                            "project_label": "AIppocampus",
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        working = registry_path.parent / "working_memory.jsonl"
        policy_path = registry_path.parent / "ambient_recall_policy.jsonl"
        cache_path = registry_path.parent / "ambient_cache.json"
        working.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "ask_policy": "do_not_ask_unless_contradicted_or_action_depends_on_uncertain_scope",
                    "risk": "medium",
                    "candidate_key": "wm_alignment_question",
                    "candidate_type": "question_link",
                    "title": "Agent alignment drift",
                    "summary": "Recurring question about agent output drifting from user intent.",
                    "recommendation": "Use as quiet question scent only when alignment drift is relevant.",
                    "confidence": 0.82,
                    "project_label": "AIppocampus",
                    "trigger_terms": ["alignment drift", "agent intent"],
                    "source_finding_ids": ["sf_a", "sf_b"],
                    "source_refs": [
                        {"thread_key": "session:alignment", "title": "Alignment thread", "line": 77}
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        first = hook.assess_prompt(
            "alignment drift 这条 recurring question 要怎么处理？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            ambient_policy_path=policy_path,
            ambient_cache_path=cache_path,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )
        second = hook.assess_prompt(
            "alignment drift 这条 recurring question 要怎么处理？",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            ambient_policy_path=policy_path,
            ambient_cache_path=cache_path,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )
        stop = hook.assess_prompt(
            "stop tracking this",
            cwd=self.workspace,
            registry_path=registry_path,
            working_memory_path=working,
            ambient_policy_path=policy_path,
            ambient_cache_path=cache_path,
            thread_id="thread-a",
            warm_background=False,
            search_budget=0,
        )

        self.assertEqual(first["decision"], "scent")
        self.assertTrue(first["ambient_recall"]["cards"][0]["ambient_policy"]["target_keys"])
        self.assertEqual(second["decision"], "skip")
        self.assertEqual(second["ambient_policy"]["frequency_capped"], 1)
        self.assertEqual(stop["ambient_policy_update"]["action"], "dismiss")
        self.assertEqual(stop["ambient_policy_update"]["target_count"], 1)

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

    def test_weak_deictic_reviewed_trigger_does_not_force_evidence(self) -> None:
        triggers_path = self.root / "weak_deictic_semantic_triggers.jsonl"
        triggers_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_semantic_trigger",
                    "status": "active",
                    "title": "External hippocampus recall continuity",
                    "aliases": ["外置海马体", "external hippocampus"],
                    "confidence": 0.9,
                    "when_to_use": "Use for AIppocampus external hippocampus continuation.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        result = hook.assess_prompt(
            "这个外置海马体还要再收一下",
            cwd=self.workspace,
            registry_path=self.registry,
            semantic_triggers_path=triggers_path,
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
        self.assertNotIn("final_answer", context)
        self.assertIn("bounded source-backed evidence", context)
        self.assertNotIn("search the source thread before relying on exact wording", context)
        self.assertFalse(result["ambient_recall"]["cards"][0]["source_reopen_required"])
        self.assertEqual(
            result["ambient_recall"]["cards"][0]["authority_state"],
            "bounded_evidence_ready",
        )
        ambient_summary = hook.ambient_debug_summary(result)
        self.assertEqual(ambient_summary["source_reopen_required_count"], 0)
        self.assertEqual(ambient_summary["authority_counts"]["bounded_evidence_ready"], 1)
        self.assertEqual(ambient_summary["reopen_required_before_claim_count"], 0)
        self.assertEqual(ambient_summary["reopen_recommended_for_exact_quote_count"], 1)

    def test_original_wording_prompt_uses_deep_archival_recall(self) -> None:
        result = hook.assess_prompt(
            "你还能找回之前那句生命还能变成什么的原话吗？",
            cwd=self.workspace,
            registry_path=self.registry,
            search_budget=3,
        )

        self.assertEqual(result["decision"], "evidence")
        self.assertTrue(result["deep_archival_requested"])
        self.assertEqual(result["ambient_recall"]["mode"], "deep_archival_recall")
        context = hook.context_for_hook(result)
        self.assertIsNotNone(context)
        self.assertIn("deep archival", context.casefold())
