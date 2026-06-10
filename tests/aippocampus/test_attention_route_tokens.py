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


if __name__ == "__main__":
    unittest.main()
