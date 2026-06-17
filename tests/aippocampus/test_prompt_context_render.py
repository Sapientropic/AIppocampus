from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import prompt_context_render as render  # noqa: E402


class PromptContextRenderTests(unittest.TestCase):
    def test_hook_debug_payload_includes_agent_affordance_for_aippo_lead(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.72,
            "confidence": "medium",
            "query_terms": ["continue", "issue"],
            "cognitive_map": [],
            "concept_expansions": [],
            "candidates": [{"title": "AIppo workflow route", "anchors": ["route packet"]}],
            "working_memory": [
                {
                    "candidate_type": "aippo_working_contract",
                    "route": "aippo_project_workflow_activation",
                    "matched_terms": ["issue"],
                }
            ],
            "evidence": [],
            "reasons": ["soft working memory: AIppo workflow route"],
        }

        public = render.public_hook_debug_payload(result)
        affordance = public["agent_recall_affordance"]
        payload = render.hook_stdout_payload(result)
        context = payload["hookSpecificOutput"]["additionalContext"] if payload else ""

        self.assertTrue(affordance["usable_continuity_lead"])
        self.assertEqual(affordance["suggested_agent_action"], "agent_aippo")
        self.assertIn("aippo_working_contract", affordance["lead_kinds"])
        self.assertEqual(affordance["not_enough_for_claim"], True)
        self.assertEqual(
            affordance["privacy_boundary"],
            "no raw source, no local paths, no source refs in hook",
        )
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn(
            "Next: call agent_aippo for the task contract before broad search.",
            context,
        )
        self.assertIn("Use as route only; reopen source before quoting or making strong claims.", context)
        self.assertNotIn("suggested_agent_action=agent_aippo", context)
        self.assertNotIn("not_enough_for_claim=true", context)
        self.assertNotIn("source_refs", context)
        self.assertNotIn("C:\\", context)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", context)

    def test_vague_old_route_affordance_suggests_deepen_without_manual_search(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.64,
            "confidence": "medium",
            "query_terms": ["old", "route"],
            "cognitive_map": [],
            "concept_expansions": [],
            "candidates": [{"title": "old route candidate", "anchors": ["source route"]}],
            "working_memory": [],
            "evidence": [],
            "semantic_source_reopen_route": True,
            "reasons": ["registry overlap: old route candidate"],
        }

        affordance = render.public_hook_debug_payload(result)["agent_recall_affordance"]
        context = render.context_for_hook(result) or ""

        self.assertTrue(affordance["usable_continuity_lead"])
        self.assertEqual(affordance["suggested_agent_action"], "agent_deepen")
        self.assertEqual(affordance["budget_hint"], "deepen_top_1")
        self.assertEqual(affordance["suggested_query_seed"], "source-required route")
        self.assertIn("source_required", affordance["lead_kinds"])
        self.assertIn("source_required_route_available", affordance["reason_codes"])
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn(
            "Next: call agent_deepen when a selected route is available; otherwise call agent_recall first.",
            context,
        )
        self.assertNotIn("suggested_agent_action=agent_deepen", context)
        self.assertNotIn("source_required_route_available", context)

    def test_current_code_question_affordance_reads_repo_first_without_context(self) -> None:
        result = {
            "decision": "skip",
            "score": 0.1,
            "confidence": "low",
            "query_terms": ["current", "code"],
            "cognitive_map": [],
            "concept_expansions": [],
            "candidates": [],
            "working_memory": [],
            "evidence": [],
            "reasons": ["current checkout required: read current repo first"],
        }

        public = render.public_hook_debug_payload(result)
        affordance = public["agent_recall_affordance"]

        self.assertFalse(affordance["usable_continuity_lead"])
        self.assertEqual(affordance["suggested_agent_action"], "read_current_repo_first")
        self.assertEqual(affordance["lead_count"], 0)
        self.assertEqual(affordance["budget_hint"], "current_repo_first")
        self.assertIsNone(render.context_for_hook(result))
        self.assertIsNone(render.hook_stdout_payload(result))

    def test_generic_meta_suppression_hides_legacy_candidate_summary(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.5,
            "confidence": "medium",
            "query_terms": ["source", "issue"],
            "cognitive_map": [],
            "concept_expansions": [],
            "candidates": [
                {
                    "thread_key": "session:cross-project",
                    "title": "Cross-project issue-shaped candidate",
                    "anchors": ["Checkpoint lines 6-67"],
                    "matched_terms": ["source", "issue"],
                    "support_level": "scent",
                    "action_grammar": "direction_only",
                }
            ],
            "working_memory": [],
            "evidence": [],
            "ambient_recall": {
                "mode": "silent_tuning",
                "card_count": 0,
                "cards": [],
                "brief_precision": {
                    "foreground_route_profile": "generic_recall_meta",
                    "foreground_lane": "recall_composer",
                    "foreground_card_count": 0,
                    "composer_backstage_count": 1,
                    "alias_spillover_suppressed_count": 1,
                    "cross_project_generic_scent_suppressed_count": 1,
                    "foreground_suppression_reasons": ["generic_meta_terms_only"],
                },
            },
            "route_delivery_diagnostic": {
                "foreground_route_profile": "generic_recall_meta",
                "foreground_lane": "recall_composer",
                "semantic_trigger_generic_term_suppressed_count": 2,
                "foreground_suppression_reasons": ["generic_meta_terms_only"],
                "hot_path_candidates_after_merge": 0,
                "evidence_count": 0,
            },
            "reasons": ["registry overlap: Cross-project issue-shaped candidate"],
        }

        self.assertIsNone(render.context_for_hook(result))
        self.assertIsNone(render.hook_stdout_payload(result))


if __name__ == "__main__":
    unittest.main()
