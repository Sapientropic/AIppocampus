from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import prompt as hook  # noqa: E402


class PromptForegroundBudgetTests(unittest.TestCase):
    def test_direction_only_weak_scent_foreground_stays_compact_with_debug_metrics(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.72,
            "confidence": "medium",
            "query_terms": ["hook", "field", "budget"],
            "concept_expansions": [],
            "candidates": [
                {
                    "title": "AIppocampus hook field budget",
                    "anchors": ["prompt hook foreground projection"],
                    "matched_terms": ["hook", "field budget"],
                },
                {
                    "title": "Source court boundary",
                    "anchors": ["source court escalation"],
                    "matched_terms": ["source court"],
                },
                {
                    "title": "Bounded summary route",
                    "anchors": ["bounded-summary theme"],
                    "matched_terms": ["bounded summary"],
                },
            ],
            "evidence": [],
            "working_memory": [],
            "cognitive_map": [],
            "ambient_recall": {
                "mode": "scent",
                "confidence": "medium",
                "cache_status": {"status": "hit", "card_count": 3},
                "cards": [
                    {
                        "theme": "AIppocampus hook field budget",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cached_warm_card",
                        "suggested_use": "Use as route context only.",
                    },
                    {
                        "theme": "Source court boundary",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "warm_scout_proposal",
                        "suggested_use": "Reopen source for claims.",
                    },
                    {
                        "theme": "Bounded summary route",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cognitive_map_route",
                        "suggested_use": "Orient only.",
                    },
                ],
            },
            "route_delivery_diagnostic": {
                "foreground_profile": "ambient_hot_path",
                "hot_path_candidates_after_merge": 3,
                "final_candidate_count": 3,
                "cold_semantic_shadowed": False,
            },
            "reasons": [
                "current prompt is about AIppocampus hook field budget",
                "weak direction_only scent",
            ],
            "elapsed_ms": 12.3,
        }

        context = hook.context_for_hook(result) or ""
        public = hook.public_hook_debug_payload(result)

        self.assertLessEqual(len(context), 650)
        self.assertLessEqual(context.count("\n") + 1, 9)
        self.assertIn("action: direction_only", context)
        self.assertIn("routes:", context)
        self.assertIn("can_use: orientation only", context)
        self.assertIn(
            "must_reopen_for: exact quotes, source-backed claims, public issue/comment text",
            context,
        )
        self.assertNotIn("Ambient recall private context", context)
        self.assertNotIn("bounded_evidence within scope", context)
        self.assertNotIn("source_open", context)
        self.assertNotIn("source-generation", context)
        self.assertEqual(public["ambient_recall"]["action_grammar_counts"]["direction_only"], 3)
        self.assertEqual(public["foreground_context"]["foreground_context_chars"], len(context))
        self.assertEqual(public["foreground_context"]["foreground_context_line_count"], 8)
        self.assertEqual(public["foreground_context"]["direction_only_actionable_route_count"], 3)
        self.assertEqual(public["foreground_context"]["weak_scent_payload_budget_violation_count"], 0)
        self.assertEqual(public["foreground_context"]["debug_only_field_leak_count"], 0)
        self.assertTrue(public["foreground_context"]["observatory_debug_payload_available"])


if __name__ == "__main__":
    unittest.main()
