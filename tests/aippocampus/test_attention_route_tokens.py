from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.navigation import attention_route_tokens as tokens  # noqa: E402


class AttentionRouteTokenTests(unittest.TestCase):
    def test_long_event_projects_tight_source_span_tokens(self) -> None:
        report = tokens.build_route_token_fixture_report()
        by_id = {row["token_id"]: row for row in report["tokens"]}
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        event = by_id["event_public_long_turn"]
        span = by_id["span_public_long_turn_code_block"]

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(event["route_token_level"], "event_token")
        self.assertEqual(span["route_token_level"], "source_span_token")
        self.assertEqual(span["parent_event_token_id"], event["token_id"])
        self.assertEqual(span["span_kind"], "code_block")
        self.assertEqual(span["source_handles"][0]["char_range"], [128, 220])
        self.assertEqual(span["source_handles"][0]["line_range"], [45, 53])
        self.assertEqual(span["route_metadata"]["salience"], "high")
        self.assertEqual(span["route_metadata"]["privacy"], "public")
        self.assertIn(span["token_id"], event["span_token_ids"])
        self.assertNotIn("PRIVATE_SPAN_TEXT_SENTINEL", encoded)
        self.assertNotIn('"text"', encoded)
        self.assertNotIn('"raw_text"', encoded)

    def test_episode_question_tokens_navigate_without_claim_permission(self) -> None:
        report = tokens.build_route_token_fixture_report()
        by_id = {row["token_id"]: row for row in report["tokens"]}

        episode = by_id["episode_question_frontier"]

        self.assertEqual(episode["route_token_level"], "episode_or_question_token")
        self.assertEqual(episode["group_kind"], "question_frontier")
        self.assertEqual(episode["action_grammar"], "direction_only")
        self.assertEqual(episode["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(episode["token_contract"]["route_token_is_not_evidence"])
        self.assertEqual(episode["member_event_token_ids"], ["event_public_long_turn"])
        self.assertEqual(
            episode["member_source_span_token_ids"],
            ["span_public_long_turn_code_block"],
        )
        self.assertEqual(report["metrics"]["token_claim_ready_without_reopen_count"], 0)
        self.assertEqual(report["metrics"]["source_span_token_count"], 1)
        self.assertEqual(report["metrics"]["event_token_count"], 1)
        self.assertEqual(report["metrics"]["episode_or_question_token_count"], 1)

    def test_allowed_route_hints_are_sanitized_and_navigation_only(self) -> None:
        report = tokens.project_hierarchical_route_tokens(
            [
                {
                    "event_id": "event_hint_route",
                    "source_id": "clean:public-hints",
                    "segment_id": "msg-hints",
                    "turn_id": "turn-hints",
                    "route_hints": {
                        "semantic_warming": {
                            "semantic_score": 0.81,
                            "semantic_aliases": ["route packet hint integration"],
                            "raw_model_reasoning": "PRIVATE_REASONING_SENTINEL",
                        },
                        "familiarity_map": {
                            "first_source_to_reopen": "docs/architecture/source-backed-attention-router.md",
                            "route_terms": ["route-packet", "hint"],
                            "local_path": "C:\\Users\\Example\\private.txt",
                        },
                        "topology_explain_only": {
                            "topology_shape": "route_cycle",
                            "risk_reason_codes": ["blind_deepen_risk"],
                            "ranking_weight_changes": ["forbidden"],
                        },
                        "unknown_hint": {"leak": "PRIVATE_UNKNOWN_SENTINEL"},
                    },
                }
            ]
        )
        event = {row["token_id"]: row for row in report["tokens"]}["event_hint_route"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(event["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(event["token_contract"]["route_token_is_not_evidence"])
        self.assertEqual(
            set(event["route_hints"]),
            {"semantic_warming", "familiarity_map", "topology_explain_only"},
        )
        self.assertEqual(
            event["route_hints"]["semantic_warming"]["semantic_aliases"],
            ["route packet hint integration"],
        )
        self.assertEqual(
            event["route_hints"]["familiarity_map"]["route_terms"],
            ["route-packet", "hint"],
        )
        self.assertTrue(event["route_hints"]["topology_explain_only"]["explain_only"])
        self.assertNotIn("PRIVATE_REASONING_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_UNKNOWN_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("ranking_weight_changes", encoded)


if __name__ == "__main__":
    unittest.main()
