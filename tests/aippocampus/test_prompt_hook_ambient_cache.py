from __future__ import annotations

from aippocampus_runtime.recall import feedback_events
from tests.aippocampus.prompt_hook_fixtures import (
    AmbientRecallHookCase,
    hook,
    json,
    os,
    patch,
    thread_cache,
)


class PromptHookAmbientCacheTests(AmbientRecallHookCase):
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

    def test_prompt_hook_can_enqueue_background_warm_job_on_cache_miss(self) -> None:
        scheduled: list[dict] = []

        def fake_schedule(prompt: str, **kwargs):
            scheduled.append({"prompt": prompt, **kwargs})
            return {"status": "queued", "job_id": "job-test", "spawned": False}

        with patch(
            "aippocampus_runtime.recall.prompt_recall_ambient.schedule_warm_ambient_recall",
            fake_schedule,
        ):
            result = hook.assess_prompt(
                "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
                cwd=self.workspace,
                registry_path=self.registry,
                thread_id="thread-a",
                topic_epoch="epoch-test",
                warm_background=True,
                search_budget=0,
            )

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0]["thread_id"], "thread-a")
        self.assertEqual(scheduled[0]["current_thread_key"], "session:thread-a")
        self.assertEqual(scheduled[0]["prompt_trace"][0]["thread_key"], "session:thread-a")
        self.assertEqual(scheduled[0]["prompt_trace"][0]["phase"], "current_prompt")
        self.assertEqual(scheduled[0]["topic_epoch"], "epoch-test")
        self.assertFalse(scheduled[0]["wait_all_foreground"])
        self.assertEqual(result["ambient_recall"]["warm_background"]["status"], "queued")
        self.assertEqual(result["ambient_recall"]["warm_background"]["job_id"], "job-test")
        self.assertTrue(result["route_delivery_diagnostic"]["background_scheduled"])

    def test_prompt_hook_creates_navigation_only_active_recall_lock(self) -> None:
        cache_path = self.root / "ambient-cache-lock.json"
        raw_prompt = "hook 机制就像人类的触发式联想，DO NOT STORE THIS PROMPT"

        result = hook.assess_prompt(
            raw_prompt,
            cwd=self.workspace,
            registry_path=self.registry,
            thread_id="thread-a",
            topic_epoch="epoch-lock",
            ambient_cache_path=cache_path,
            warm_background=False,
            search_budget=0,
        )
        lock_path = cache_path.parent / "active_recall_locks.json"
        raw_lock = lock_path.read_text(encoding="utf-8")
        lock = result["ambient_recall"]["active_recall_lock"]

        self.assertEqual(result["decision"], "scent")
        self.assertIn(lock["state"], {"pending", "ready"})
        self.assertEqual(lock["support_level"], "scent")
        self.assertTrue(lock["source_reopen_required"])
        self.assertNotIn("DO NOT STORE THIS PROMPT", raw_lock)
        self.assertNotIn(str(self.workspace).replace("\\", "/"), raw_lock.replace("\\", "/"))
        self.assertNotIn("snippet", raw_lock.casefold())

    def test_prompt_hook_prioritizes_warm_thread_cache_and_exposes_metadata(self) -> None:
        cache_path = self.root / "ambient-cache.json"
        thread_cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(self.workspace),
            topic_epoch="epoch-cache",
            cards=[
                {
                    "card_id": "cached-card",
                    "theme": "cached warm context",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "matched_terms": ["ambient recall"],
                }
            ],
            mode="active_gentle_nudge",
            confidence="medium",
            query_aliases=["cached alias"],
            topic_epoch_decision={"action": "reuse", "label": "ambient", "confidence": 0.7},
            visibility_bias="active_gentle_nudge",
        )

        result = hook.assess_prompt(
            "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
            cwd=self.workspace,
            registry_path=self.registry,
            thread_id="thread-a",
            topic_epoch="epoch-cache",
            ambient_cache_path=cache_path,
            search_budget=0,
        )

        ambient = result["ambient_recall"]
        self.assertEqual(ambient["cache_status"]["status"], "hit")
        self.assertEqual(ambient["cache_status"]["query_aliases"], ["cached alias"])
        self.assertEqual(ambient["cache_status"]["topic_epoch_decision"]["action"], "reuse")
        self.assertEqual(ambient["cache_status"]["visibility_bias"], "active_gentle_nudge")
        self.assertEqual(ambient["cards"][0]["card_id"], "cached-card")
        self.assertEqual(ambient["cards"][0]["provenance_class"], "cached_warm_card")
        self.assertEqual(ambient["cards"][0]["cached_origin"], "unknown")
        context = hook.context_for_hook(result)
        self.assertIn("cached warm candidate", context.casefold())

    def test_prompt_hook_uses_related_cache_after_paraphrase_epoch_miss(self) -> None:
        cache_path = self.root / "ambient-cache-related.json"
        registry_path = self._write_single_thread_registry(
            title="Ambient recall design",
            keywords=["ambient recall", "associative cache"],
            summary="Prior notes about warm ambient recall cards and associative cache behavior.",
        )
        thread_cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(self.workspace),
            topic_epoch="epoch-first-phrasing",
            cards=[
                {
                    "card_id": "cached-related-card",
                    "theme": "Ambient recall design: ambient recall",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "matched_terms": ["ambient recall"],
                }
            ],
            mode="active_gentle_nudge",
            confidence="medium",
            related_fingerprints=thread_cache.related_signal_fingerprints(
                candidates=[{"thread_key": "session:single-thread"}],
            ),
            topic_epoch_decision={
                "action": "reuse",
                "label": "ambient recall cache continuity",
            },
        )

        result = hook.assess_prompt(
            "ambient associative cache 这个暖启动还能再顺一点吗？",
            cwd=self.workspace,
            registry_path=registry_path,
            thread_id="thread-a",
            ambient_cache_path=cache_path,
            warm_background=True,
            search_budget=0,
        )

        ambient = result["ambient_recall"]
        self.assertEqual(ambient["cache_status"]["status"], "related_hit")
        self.assertEqual(ambient["cache_status"]["matched_topic_epoch"], "epoch-first-phrasing")
        self.assertEqual(ambient["cards"][0]["card_id"], "cached-related-card")
        self.assertNotIn("warm_background", ambient)

    def test_prompt_hook_next_turn_reads_detached_warm_cache_without_rescheduling(self) -> None:
        cache_path = self.root / "ambient-cache-next-turn.json"
        scheduled: list[dict] = []

        def fake_schedule(prompt: str, **kwargs):
            scheduled.append({"prompt": prompt, **kwargs})
            thread_cache.write_thread_cache(
                kwargs["cache_path"],
                thread_id=kwargs["thread_id"],
                workspace=str(kwargs["cwd"]),
                topic_epoch=kwargs["topic_epoch"],
                cards=[
                    {
                        "card_id": "detached-card",
                        "theme": "detached warm result",
                        "support_level": "candidate",
                        "visibility": "active_gentle_nudge",
                        "matched_terms": ["ambient recall"],
                    }
                ],
                mode="active_gentle_nudge",
                confidence="medium",
                query_aliases=["detached alias"],
                topic_epoch_decision={"action": "reuse", "label": "ambient", "confidence": 0.8},
            )
            return {"status": "scheduled", "job_id": "job-detached", "spawned": False}

        with patch(
            "aippocampus_runtime.recall.prompt_recall_ambient.schedule_warm_ambient_recall",
            fake_schedule,
        ):
            first = hook.assess_prompt(
                "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
                cwd=self.workspace,
                registry_path=self.registry,
                thread_id="thread-a",
                topic_epoch="epoch-next",
                ambient_cache_path=cache_path,
                warm_background=True,
                search_budget=0,
            )
            second = hook.assess_prompt(
                "继续这个 ambient recall 方向",
                cwd=self.workspace,
                registry_path=self.registry,
                thread_id="thread-a",
                topic_epoch="epoch-next",
                ambient_cache_path=cache_path,
                warm_background=True,
                search_budget=0,
            )

        self.assertEqual(first["ambient_recall"]["warm_background"]["status"], "scheduled")
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(second["ambient_recall"]["cache_status"]["status"], "hit")
        self.assertEqual(second["ambient_recall"]["cards"][0]["card_id"], "detached-card")
        self.assertEqual(second["ambient_recall"]["cards"][0]["provenance_class"], "cached_warm_card")
        self.assertEqual(second["ambient_recall"]["cards"][0]["cached_origin"], "unknown")
        self.assertNotIn("warm_background", second["ambient_recall"])

    def test_prompt_hook_frequency_caps_cached_warm_card_without_policy_key(self) -> None:
        cache_path = self.root / "ambient-cache-fallback-policy.json"
        thread_cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(self.workspace),
            topic_epoch="epoch-fallback-policy",
            cards=[
                {
                    "card_id": "fallback-policy-card",
                    "theme": "cached warm context",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "matched_terms": ["ambient recall"],
                }
            ],
            mode="active_gentle_nudge",
            confidence="medium",
            query_aliases=["cached alias"],
        )

        first = hook.assess_prompt(
            "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
            cwd=self.workspace,
            registry_path=self.registry,
            thread_id="thread-a",
            topic_epoch="epoch-fallback-policy",
            ambient_cache_path=cache_path,
            warm_background=False,
            search_budget=0,
        )
        second = hook.assess_prompt(
            "hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
            cwd=self.workspace,
            registry_path=self.registry,
            thread_id="thread-a",
            topic_epoch="epoch-fallback-policy",
            ambient_cache_path=cache_path,
            warm_background=False,
            search_budget=0,
        )

        self.assertEqual(first["ambient_recall"]["cards"][0]["card_id"], "fallback-policy-card")
        self.assertGreaterEqual(second["ambient_recall"]["policy_filter"]["frequency_capped"], 1)
        self.assertNotIn(
            "fallback-policy-card",
            [card.get("card_id") for card in second["ambient_recall"]["cards"]],
        )

    def test_prompt_hook_filters_cached_warm_card_from_feedback_lane(self) -> None:
        cache_path = self.root / "ambient-cache-feedback.json"
        feedback_path = self.root / "route-feedback.jsonl"
        event = feedback_events.active_flow_event(
            route_id="cached-card-to-quiet",
            route_kind="active_path",
            signal="wrong_route_drag",
        )
        feedback_path.write_text(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        thread_cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace=str(self.workspace),
            topic_epoch="epoch-feedback",
            cards=[
                {
                    "card_id": "cached-card-to-quiet",
                    "theme": "cached warm context",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "matched_terms": ["ambient recall"],
                }
            ],
            mode="active_gentle_nudge",
            confidence="medium",
        )

        with patch.dict(os.environ, {"AIPPOCAMPUS_FEEDBACK_JSONL": str(feedback_path)}):
            result = hook.assess_prompt(
                "please recall a zephyr calibration route",
                cwd=self.workspace,
                registry_path=self.registry,
                thread_id="thread-a",
                topic_epoch="epoch-feedback",
                ambient_cache_path=cache_path,
                warm_background=False,
                search_budget=0,
            )

        ambient = result["ambient_recall"]
        self.assertNotIn(
            "cached-card-to-quiet",
            [card.get("card_id") for card in ambient["cards"]],
        )
        self.assertEqual(ambient["feedback_filter"]["load_status"], "loaded")
        self.assertEqual(ambient["feedback_filter"]["quieted_card_count"], 1)

    def test_prompt_hook_debug_log_summarizes_ambient_cache_without_raw_prompt(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.7,
            "confidence": "medium",
            "query_terms": ["ambient"],
            "concept_expansions": [],
            "cognitive_map": [],
            "candidates": [],
            "working_memory": [],
            "semantic_gate": None,
            "evidence": [],
            "elapsed_ms": 12.0,
            "ambient_recall": {
                "mode": "active_gentle_nudge",
                "confidence": "medium",
                "cards": [
                    {
                        "card_id": "card-a",
                        "theme": "ambient",
                        "visibility": "active_gentle_nudge",
                        "support_level": "candidate",
                        "provenance_class": "cached_warm_card",
                        "source_validation": {"status": "supported"},
                    }
                ],
                "cache_status": {
                    "status": "hit",
                    "topic_epoch": "epoch-debug",
                    "card_count": 1,
                },
                "warm_background": {"status": "queued", "spawned": False},
            },
        }
        log_path = self.root / "debug.jsonl"

        hook.write_debug_log(
            result,
            hook_input={"prompt": "DO NOT LOG THIS PROMPT", "session_id": "thread-a"},
            log_path=log_path,
        )
        event = json.loads(log_path.read_text(encoding="utf-8"))
        raw = log_path.read_text(encoding="utf-8")

        self.assertNotIn("DO NOT LOG THIS PROMPT", raw)
        self.assertEqual(event["ambient_recall"]["cache"]["status"], "hit")
        self.assertEqual(event["ambient_recall"]["warm_background"]["status"], "queued")
        self.assertEqual(event["ambient_recall"]["source_validation_statuses"]["supported"], 1)
        self.assertEqual(event["ambient_recall"]["provenance_counts"]["cached_warm_card"], 1)
        self.assertEqual(event["ambient_recall"]["support_level_counts"]["candidate"], 1)
