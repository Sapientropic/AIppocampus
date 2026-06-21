from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.dream import delivery_policy
from aippocampus_runtime.hooks import prompt as hook
from aippocampus_runtime.recall import prompt_recall_context


class DreamDeliveryEligibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self.registry.write_text(json.dumps({"threads": []}), encoding="utf-8")
        self.working_memory = self.root / "working-memory.jsonl"
        self.working_memory.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "candidate_key": "wm_dream_continuity",
                    "title": "Continuity route bridge",
                    "summary": "Use only as a route hint.",
                    "trigger_terms": ["continuity"],
                    "source_finding_ids": ["dreamfinding_continuity"],
                    "confidence": 0.7,
                    "project_label": "AIppocampus",
                    "review_state": "agent_adjudicated",
                    "sensitive_use_gate": {"state": "allowed"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _append_working_memory_row(self, row: dict[str, object]) -> None:
        with self.working_memory.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _delivery_args(self, mode: str = "delivered") -> argparse.Namespace:
        return argparse.Namespace(
            dream_delivery_mode=mode,
            dream_rollout_rate=1.0,
            dream_shadow_ab=False,
            dream_shadow_log=None,
            dream_shadow_salt="unit-test-salt",
            registry=str(self.registry),
            registry_dir=None,
            working_memory=str(self.working_memory),
            session_id="session-test",
            topic_epoch="epoch-test",
            dream_assignment_unit=None,
        )

    def test_zero_dream_limit_prefilters_dream_rows_before_matching(self) -> None:
        with patch.object(
            prompt_recall_context,
            "match_working_memory",
            wraps=prompt_recall_context.match_working_memory,
        ) as matcher:
            result = hook.assess_prompt(
                "把当前 repo 的 TypeScript hover 样式修一下",
                cwd=self.workspace,
                registry_path=self.registry,
                working_memory_path=self.working_memory,
                use_semantic_gate=False,
                search_budget=0,
                dream_hypothesis_limit=0,
                dream_delivery_prefilter_reason="ineligible_task_mode",
            )

        self.assertEqual(result["working_memory"], [])
        self.assertEqual(matcher.call_count, 0)
        self.assertEqual(
            result["dream_delivery_prefilter"]["reason"],
            "ineligible_task_mode",
        )
        self.assertEqual(result["dream_delivery_prefilter"]["prefiltered_dream_count"], 1)
        public = hook.public_hook_debug_payload(result)
        debug = public["dream_delivery_prefilter"]
        self.assertEqual(debug["reason"], "ineligible_task_mode")
        self.assertEqual(debug["task_mode"], "unknown")
        encoded = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("wm_dream_continuity", encoded)
        self.assertNotIn("hover 样式", encoded)

    def test_zero_dream_limit_keeps_non_dream_working_memory_match(self) -> None:
        self._append_working_memory_row(
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "question_link",
                "candidate_key": "wm_question_continuity",
                "title": "Continuity question follow-up",
                "summary": "A source-backed question link about continuity.",
                "trigger_terms": ["continuity"],
                "source_refs": [{"thread_key": "session:continuity", "line": 12}],
                "confidence": 0.7,
                "project_label": "AIppocampus",
            }
        )

        result = hook.assess_prompt(
            "AIppocampus continuity 这条线下一步怎么收？",
            cwd=self.workspace,
            registry_path=self.registry,
            working_memory_path=self.working_memory,
            use_semantic_gate=False,
            search_budget=0,
            dream_hypothesis_limit=0,
            dream_delivery_prefilter_reason="budget_zero",
        )

        self.assertEqual(len(result["working_memory"]), 1)
        self.assertEqual(result["working_memory"][0]["candidate_type"], "question_link")
        self.assertEqual(result["dream_delivery_prefilter"]["prefiltered_dream_count"], 1)

    def test_positive_dream_limit_preserves_explicit_dream_selection(self) -> None:
        result = hook.assess_prompt(
            "AIppocampus continuity 这条线下一步怎么收？",
            cwd=self.workspace,
            registry_path=self.registry,
            working_memory_path=self.working_memory,
            use_semantic_gate=False,
            search_budget=0,
            dream_hypothesis_limit=1,
            dream_delivery_prefilter_reason="eligible_task_mode",
        )

        self.assertEqual(len(result["working_memory"]), 1)
        self.assertEqual(result["working_memory"][0]["candidate_type"], "dream_hypothesis")
        self.assertEqual(result["dream_delivery_prefilter"]["reason"], "eligible_task_mode")
        self.assertEqual(result["dream_delivery_prefilter"]["effective_limit"], 1)

    def test_delivery_policy_blocks_coding_prompt_before_shadow_matching(self) -> None:
        with patch(
            "aippocampus_runtime.dream.live_shadow_ab.record_prompt_shadow_from_hook_args",
            side_effect=AssertionError("dream shadow matching should be skipped"),
        ):
            delivery = delivery_policy.prepare_dream_delivery(
                prompt="把当前 repo 的 TypeScript hover 样式修一下",
                hook_input={},
                args=self._delivery_args(),
            )

        self.assertFalse(delivery["allow_dream"])
        self.assertEqual(delivery["dream_hypothesis_limit"], 0)
        self.assertEqual(delivery["prefilter_reason"], "ineligible_task_mode")
        self.assertEqual(delivery["task_mode"], "coding_current_repo")

    def test_delivery_policy_preserves_life_prompt_for_dream_arm(self) -> None:
        with patch(
            "aippocampus_runtime.dream.live_shadow_ab.record_prompt_shadow_from_hook_args",
            return_value={
                "delivered_arm": "dream",
                "delivery_decision": "delivered_dream_treatment",
            },
        ) as recorder:
            delivery = delivery_policy.prepare_dream_delivery(
                prompt="最近 continuity 这条线让我有点卡住，能不能从梦的角度看下一步？",
                hook_input={},
                args=self._delivery_args(),
            )

        self.assertEqual(recorder.call_count, 1)
        self.assertTrue(delivery["allow_dream"])
        self.assertEqual(delivery["dream_hypothesis_limit"], 1)
        self.assertEqual(delivery["prefilter_reason"], "eligible_task_mode")
        self.assertIn(delivery["task_mode"], {"life_wide_reflection", "explicit_dream"})

if __name__ == "__main__":
    unittest.main()
