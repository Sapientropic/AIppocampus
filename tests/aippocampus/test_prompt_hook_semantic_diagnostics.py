from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.hooks import prompt as hook
from tests.aippocampus.redaction_fixtures import FAKE_TEST_OPENAI_API_KEY


class PromptHookSemanticDiagnosticsTests(unittest.TestCase):
    def test_low_value_casual_prompt_skips_semantic_and_registry_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fail_if_called(prompt: str, **kwargs) -> dict:
                raise AssertionError("low-value casual prompt should not call semantic gate")

            result = hook.assess_prompt(
                "今天天气怎么样",
                cwd=root,
                semantic_gate_fn=fail_if_called,
                semantic_timeout=5,
                max_elapsed_ms=20000,
                detail="detail",
            )

        public = hook.public_hook_debug_payload(result)
        delivery = public["route_delivery_diagnostic"]
        affordance = public["agent_recall_affordance"]

        self.assertEqual(result["decision"], "skip")
        self.assertLess(result["elapsed_ms"], 250)
        self.assertEqual(delivery["foreground_route_profile"], "low_value_casual")
        self.assertEqual(delivery["foreground_lane"], "stay_silent")
        self.assertFalse(delivery["semantic_waited"])
        self.assertIn(
            "low_value_casual_no_memory_route_intent",
            delivery["foreground_suppression_reasons"],
        )
        self.assertFalse(affordance["usable_continuity_lead"])
        self.assertEqual(affordance["suggested_agent_action"], "stay_silent")

    def test_explicit_aippo_prompt_delivers_agent_native_affordance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = hook.assess_prompt(
                "用 AIppo working contract 帮我 review 这个 issue 的反馈口径",
                cwd=Path(tmp),
                semantic_gate_fn=lambda *_, **__: {
                    "available": False,
                    "decision": "skip",
                    "confidence": 0.0,
                    "query_aliases": [],
                },
                max_elapsed_ms=1200,
            )

        public = hook.public_hook_debug_payload(result)
        payload = hook.hook_stdout_payload(result)
        context = payload["hookSpecificOutput"]["additionalContext"] if payload else ""
        affordance = public["agent_recall_affordance"]

        self.assertTrue(affordance["usable_continuity_lead"])
        self.assertEqual(affordance["suggested_agent_action"], "agent_aippo")
        self.assertIn("aippo_working_contract", affordance["lead_kinds"])
        self.assertIn("explicit_agent_native_surface_intent", affordance["reason_codes"])
        self.assertIn("Next: call agent_aippo", context)
        self.assertNotIn("source_refs", context)
        self.assertNotIn(str(tmp), json.dumps(public, ensure_ascii=False))

    def test_explicit_avatar_episode_prompt_exposes_surface_specific_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = hook.assess_prompt(
                "用 avatar 和 Episode-Arc / project experience 看看这个插件体验问题以前是不是反复出现过",
                cwd=Path(tmp),
                semantic_gate_fn=lambda *_, **__: {
                    "available": False,
                    "decision": "skip",
                    "confidence": 0.0,
                    "query_aliases": [],
                },
                max_elapsed_ms=1200,
            )

        public = hook.public_hook_debug_payload(result)
        affordance = public["agent_recall_affordance"]
        context = (hook.hook_stdout_payload(result) or {})["hookSpecificOutput"][
            "additionalContext"
        ]

        self.assertTrue(affordance["usable_continuity_lead"])
        self.assertEqual(affordance["suggested_agent_action"], "agent_recall")
        self.assertIn("avatar_posture", affordance["lead_kinds"])
        self.assertIn("episode_arc", affordance["lead_kinds"])
        self.assertIn("project_experience", affordance["lead_kinds"])
        self.assertIn("avatar_posture_candidate", affordance["reason_codes"])
        self.assertIn("episode_arc_candidate", affordance["reason_codes"])
        self.assertIn("project_experience_candidate", affordance["reason_codes"])
        self.assertIn("Next: call agent_recall", context)

    def test_explicit_architecture_prompt_exposes_quiet_navigation_affordance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = hook.assess_prompt(
                "验一下 topology、attention router、macro orientation、sheaf/local-global 是否让前台少走弯路",
                cwd=Path(tmp),
                semantic_gate_fn=lambda *_, **__: {
                    "available": False,
                    "decision": "skip",
                    "confidence": 0.0,
                    "query_aliases": [],
                },
                max_elapsed_ms=1200,
            )

        public = hook.public_hook_debug_payload(result)
        payload = hook.hook_stdout_payload(result)
        context = payload["hookSpecificOutput"]["additionalContext"] if payload else ""
        affordance = public["agent_recall_affordance"]

        self.assertTrue(affordance["usable_continuity_lead"])
        self.assertEqual(affordance["suggested_agent_action"], "agent_recall")
        self.assertIn("architecture_navigation", affordance["lead_kinds"])
        self.assertIn("architecture_navigation_requested", affordance["reason_codes"])
        self.assertEqual(
            affordance["suggested_query_seed"],
            "architecture navigation / route diagnostics",
        )
        self.assertIn("agent_explain or deepen", context)
        self.assertTrue(affordance["not_enough_for_claim"])
        self.assertNotIn("source_refs", context)

    def test_explicit_architecture_prompt_suppresses_unrelated_warm_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry" / "threads.json"
            registry_path.parent.mkdir()
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "threads": [
                            {
                                "thread_key": "session:old-plugin-debugging",
                                "title": "Old unrelated plugin debugging",
                                "project_label": "OtherProject",
                                "anchor_titles": ["attention router incident"],
                                "keywords": ["attention router", "macro orientation", "plugin"],
                                "summary": "An old unrelated project route.",
                                "paths": {"workspace": str(root / "old")},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = hook.assess_prompt(
                "验一下 topology、attention router、macro orientation、sheaf/local-global 是否让前台少走弯路",
                cwd=root,
                registry_path=registry_path,
                use_semantic_gate=False,
                search_budget=0,
                max_elapsed_ms=1200,
            )

        context = (hook.hook_stdout_payload(result) or {})["hookSpecificOutput"][
            "additionalContext"
        ]
        public = hook.public_hook_debug_payload(result)
        affordance = public["agent_recall_affordance"]

        self.assertIn("architecture_navigation", affordance["lead_kinds"])
        self.assertIn("Architecture navigation available", context)
        self.assertIn("Ambient memory routes are suppressed", context)
        self.assertNotIn("Old unrelated plugin debugging", context)
        self.assertNotIn("session:old-plugin-debugging", context)

    def test_public_payload_explains_partial_semantic_success_without_raw_worker_details(
        self,
    ) -> None:
        private_result = {
            "decision": "scent",
            "score": 0.88,
            "confidence": "medium",
            "query_terms": [FAKE_TEST_OPENAI_API_KEY],
            "candidates": [{"title": "private title", "thread_key": "session:private"}],
            "evidence": [{"snippet": "private source wording"}],
            "semantic_gate": {
                "available": True,
                "decision": "scent",
                "confidence": 0.82,
                "cached": False,
                "query_aliases": [f"alias {FAKE_TEST_OPENAI_API_KEY}"],
                "workers": [{"raw": "private worker output"}],
                "errors": ["private semantic error"],
                "error_buckets": {"read_timeout": 1, "private_raw_failure": 1},
                "worker_count": 2,
                "successful_worker_count": 1,
                "failed_worker_count": 1,
                "partial_success": True,
                "partial_failure_reasons": ["read_timeout", "private raw failure"],
                "budget": {
                    "requested_timeout": 4.0,
                    "effective_timeout": 2.0,
                    "overall_deadline_seconds": 4.0,
                    "effective_timeout_policy": "worker_socket_timeout_half_of_overall_deadline",
                    "budget_clip_reason": "worker_socket_timeout_policy",
                    "private_budget_note": "do not print",
                },
            },
            "route_delivery_diagnostic": {
                "foreground_profile": "ambient_hot_path",
                "semantic_reuse_source": "semantic_provider_timeout",
                "semantic_waited": True,
                "semantic_partial_failure": True,
                "raw_prompt": "private prompt text",
                "candidate_ids": ["session:private"],
            },
        }

        public = hook.public_hook_debug_payload(private_result)
        encoded = json.dumps(public, ensure_ascii=False)
        semantic = public["semantic_gate"]

        self.assertTrue(semantic["available"])
        self.assertTrue(semantic["partial_success"])
        self.assertEqual(semantic["successful_worker_count"], 1)
        self.assertEqual(semantic["failed_worker_count"], 1)
        self.assertEqual(semantic["partial_failure_reasons"], ["read_timeout"])
        self.assertEqual(semantic["error_buckets"], {"read_timeout": 1})
        self.assertEqual(
            semantic["budget"]["effective_timeout_policy"],
            "worker_socket_timeout_half_of_overall_deadline",
        )
        self.assertEqual(semantic["budget"]["budget_clip_reason"], "worker_socket_timeout_policy")
        self.assertTrue(public["route_delivery_diagnostic"]["semantic_partial_failure"])
        self.assertNotIn("private worker output", encoded)
        self.assertNotIn("private semantic error", encoded)
        self.assertNotIn("private_raw_failure", encoded)
        self.assertNotIn("private_budget_note", encoded)
        self.assertNotIn("private prompt text", encoded)

    def test_foreground_semantic_budget_exposes_timeout_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            registry_path = root / "registry" / "threads.json"
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
                }

            result = hook.assess_prompt(
                "那个脑内续接器现在怎么样了？",
                cwd=workspace,
                registry_path=registry_path,
                semantic_gate_fn=fake_semantic_gate,
                semantic_timeout=3,
                max_elapsed_ms=3000,
                search_budget=0,
            )

        budget = result["semantic_gate"]["budget"]
        self.assertIn("timeout", seen)
        self.assertTrue(seen["foreground"])
        self.assertEqual(seen["deadline_seconds"], budget["overall_deadline_seconds"])
        self.assertEqual(budget["effective_timeout"], seen["timeout"])
        self.assertEqual(
            budget["effective_timeout_policy"],
            "worker_socket_timeout_half_of_overall_deadline",
        )
        self.assertEqual(budget["budget_clip_reason"], "foreground_post_semantic_reserve")

if __name__ == "__main__":
    unittest.main()
