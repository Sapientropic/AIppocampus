from __future__ import annotations

from tests.aippocampus.prompt_hook_fixtures import AmbientRecallHookCase, hook, json


class PromptHookAntiNagBehaviorTests(AmbientRecallHookCase):
    def test_question_scent_frequency_cap_and_stop_tracking_are_pr_critical(self) -> None:
        registry_path = self.root / "anti-nag-registry" / "threads.json"
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

        kwargs = {
            "cwd": self.workspace,
            "registry_path": registry_path,
            "working_memory_path": working,
            "ambient_policy_path": policy_path,
            "ambient_cache_path": cache_path,
            "thread_id": "thread-a",
            "warm_background": False,
            "search_budget": 0,
        }
        first = hook.assess_prompt("alignment drift 这条 recurring question 要怎么处理？", **kwargs)
        second = hook.assess_prompt("alignment drift 这条 recurring question 要怎么处理？", **kwargs)
        stop = hook.assess_prompt("stop tracking this", **kwargs)

        self.assertEqual(first["decision"], "scent")
        self.assertEqual(second["decision"], "skip")
        self.assertEqual(second["ambient_policy"]["frequency_capped"], 1)
        self.assertEqual(stop["ambient_policy_update"]["action"], "dismiss")
        self.assertEqual(stop["ambient_policy_update"]["target_count"], 1)
        self.assertEqual(set(stop["result_tiers"]), {"decision"})
        self.assertNotIn("semantic_bridge_diagnostic", stop)
        self.assertNotIn("semantic_cue_cache", stop)
