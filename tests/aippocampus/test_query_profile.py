from __future__ import annotations

import unittest

from aippocampus_runtime.recall.ambient_cards import ambient_recall_from_decision
from aippocampus_runtime.recall.query_profile import classify_query_profile


class QueryProfileTests(unittest.TestCase):
    def test_exact_phrase_prefers_source_text_lane(self) -> None:
        profile = classify_query_profile("你还能找回之前那句生命还能变成什么的原话吗？")

        self.assertEqual(profile["profile"], "exact_phrase")
        self.assertEqual(profile["lane"], "source_text")
        self.assertIn("exact_wording_request", profile["reason_codes"])

    def test_life_context_preserves_warm_ambient_lane(self) -> None:
        profile = classify_query_profile("最近让我很烦的那个点后来怎么处理来着？")

        self.assertEqual(profile["profile"], "affective_life_context")
        self.assertEqual(profile["lane"], "ambient_life_context")
        self.assertIn("affective_continuity_terms", profile["reason_codes"])

    def test_generic_source_issue_prompt_is_recall_meta_not_normal(self) -> None:
        profile = classify_query_profile(
            "候选 source refs 的中间层和过度保守这个问题，是不是已经有 issue 了？"
        )

        self.assertEqual(profile["profile"], "generic_recall_meta")
        self.assertEqual(profile["lane"], "recall_composer")
        self.assertEqual(profile["composer"], "suppress_generic_scent")
        self.assertIn("generic_recall_meta_terms", profile["reason_codes"])

    def test_generic_meta_prompt_backstages_cached_direction_only_card(self) -> None:
        ambient = ambient_recall_from_decision(
            {"decision": "scent", "confidence": "medium", "elapsed_ms": 1.0},
            cached_cards=[
                {
                    "card_id": "unrelated-alias-card",
                    "theme": "Garden planning notebook",
                    "support_level": "candidate",
                    "visibility": "active_gentle_nudge",
                    "matched_terms": ["detached alias"],
                }
            ],
            cached_cards_first=True,
            prompt="候选 source refs 的中间层和过度保守这个问题，是不是已经有 issue 了？",
        )

        self.assertEqual(ambient["cards"], [])
        self.assertEqual(ambient["mode"], "silent_tuning")
        self.assertEqual(
            ambient["brief_precision"]["foreground_route_profile"],
            "generic_recall_meta",
        )
        self.assertEqual(ambient["brief_precision"]["composer_backstage_count"], 1)
        self.assertIn(
            "generic_meta_terms_only",
            ambient["brief_precision"]["foreground_suppression_reasons"],
        )

if __name__ == "__main__":
    unittest.main()
