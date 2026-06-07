from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import prompt_context_render as render  # noqa: E402


class PromptContextRenderTests(unittest.TestCase):
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
