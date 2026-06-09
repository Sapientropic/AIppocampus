from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import ambient_cards, authority, evidence_drawer  # noqa: E402
from aippocampus_runtime.recall.active_path_packet import build_active_path_packet  # noqa: E402


class MemoryEvidenceDrawerTests(unittest.TestCase):
    def test_projects_recall_route_and_bounded_evidence_into_drawer(self) -> None:
        default_packet = build_active_path_packet(
            ambient_recall={
                "kind": "aippocampus_ambient_recall",
                "confidence": "high",
                "cards": [
                    {
                        "card_id": "route-card",
                        "theme": "Prior launch constraint",
                        "support_level": "source_required",
                        "route": "reopen",
                        "suggested_use": "Reopen this before repeating the launch constraint.",
                        "source_refs": [
                            {
                                "thread_key": "session:launch",
                                "message_id": "msg-launch",
                                "line": 12,
                            }
                        ],
                    }
                ],
            }
        )
        packet = build_active_path_packet(
            ambient_recall={
                "kind": "aippocampus_ambient_recall",
                "confidence": "high",
                "cards": [
                    {
                        "card_id": "route-card",
                        "theme": "Prior launch constraint",
                        "support_level": "source_required",
                        "route": "reopen",
                        "suggested_use": "Reopen this before repeating the launch constraint.",
                        "source_refs": [
                            {
                                "thread_key": "session:launch",
                                "message_id": "msg-launch",
                                "line": 12,
                            }
                        ],
                    }
                ],
            },
            include_drawer=True,
        )
        bounded = ambient_cards.bounded_evidence_context_from_source_reopen(
            {
                "status": "ok",
                "support_level": "evidence",
                "evidence_level": "source_backed",
                "source_refs": [
                    {
                        "thread_key": "session:launch",
                        "message_id": "msg-launch",
                        "line": 12,
                    }
                ],
                "source_window": {
                    "messages": [
                        {
                            "message_id": "msg-launch",
                            "turn_id": "turn-launch",
                            "source_line": 12,
                            "phase": "final_answer",
                            "text": "bounded clean-source wording, not raw window payload",
                        }
                    ]
                },
                "source_boundary": {"clean_source_reopened": True},
            }
        )

        self.assertNotIn("evidence_drawer", default_packet)
        self.assertIn("evidence_drawer", packet)
        self.assertEqual(packet["evidence_drawer"]["kind"], "aippocampus_memory_evidence_drawer")
        self.assertGreaterEqual(packet["evidence_drawer"]["item_count"], 1)
        drawer = evidence_drawer.build_memory_evidence_drawer(
            active_path_packet=packet,
            bounded_evidence_context=bounded,
        )

        self.assertEqual(drawer["kind"], "aippocampus_memory_evidence_drawer")
        self.assertEqual(drawer["schema_version"], 1)
        self.assertTrue(drawer["source_boundary"]["drawer_is_not_source_truth"])
        self.assertTrue(
            drawer["source_boundary"]["navigation_only_items_cannot_support_factual_claims"]
        )
        route_item = next(
            item for item in drawer["items"] if item["action_grammar"] == "reopenable_route"
        )
        self.assertEqual(route_item["authority_label"], "reopen_source")
        self.assertEqual(route_item["reopen_plan"]["status"], "ready")
        self.assertEqual(route_item["reopen_plan"]["recommended_tool"], "recall_deepen")
        self.assertFalse(route_item["reopen_plan"]["manual_query_invention_expected"])
        self.assertTrue(route_item["navigation_only"])
        self.assertFalse(route_item["can_support_factual_claim"])
        self.assertIn("navigation_only_surface_supports_factual_claim", route_item["cannot_claim"])
        evidence_item = next(
            item for item in drawer["items"] if item["action_grammar"] == "bounded_evidence"
        )
        self.assertEqual(evidence_item["authority_label"], "use_bounded_evidence_within_scope")
        self.assertFalse(evidence_item["navigation_only"])
        self.assertTrue(evidence_item["can_support_factual_claim"])
        self.assertTrue(evidence_item["exact_claim_requires_source_reopen"])
        self.assertTrue(evidence_item["affordances"]["deepen"])

        serialized = json.dumps(drawer, ensure_ascii=False, sort_keys=True)
        self.assertNotIn('"source_window"', serialized)
        self.assertNotIn("bounded clean-source wording", serialized)
        self.assertNotIn("E:\\", serialized)

    def test_navigation_only_cue_cannot_masquerade_as_factual_evidence(self) -> None:
        drawer = evidence_drawer.build_memory_evidence_drawer(
            surfaces=[
                authority.with_trust_fields(
                    {
                        "card_id": "semantic-scent",
                        "theme": "Possible old preference",
                        "support_level": "scent",
                        "provenance_class": "cognitive_map_route",
                        "confidence": "high",
                        "suggested_use": "High-confidence scent, still not evidence.",
                    }
                )
            ]
        )

        item = drawer["items"][0]
        self.assertEqual(item["action_grammar"], "direction_only")
        self.assertEqual(item["authority_label"], "navigation_only")
        self.assertEqual(item["route_strength"], "high")
        self.assertTrue(item["navigation_only"])
        self.assertFalse(item["can_support_factual_claim"])
        self.assertTrue(item["source_boundary"]["confidence_is_not_authority"])
        self.assertIn("navigation_only_surface_supports_factual_claim", item["cannot_claim"])
        self.assertIn("confidence_score_is_authority", drawer["cannot_claim"])

    def test_blocked_or_insufficient_evidence_drawer_abstains(self) -> None:
        drawer = evidence_drawer.build_memory_evidence_drawer(
            surfaces=[
                {
                    "card_id": "blocked-route",
                    "theme": "Conflicted source route",
                    "support_level": "source_required",
                    "visibility": "blocked",
                    "source_refs": [{"thread_key": "session:blocked", "message_id": "msg-1"}],
                    "reopen_plan": {
                        "status": "blocked",
                        "failure_reason_codes": ["source_conflict_uncleared"],
                    },
                }
            ]
        )

        item = drawer["items"][0]
        self.assertEqual(item["action_grammar"], "ignore_or_blocked")
        self.assertEqual(item["authority_label"], "blocked_or_abstain")
        self.assertEqual(item["reopen_plan"]["status"], "blocked")
        self.assertEqual(item["abstention_reason"], "blocked_or_insufficient_evidence")
        self.assertFalse(item["can_support_factual_claim"])
        self.assertFalse(item["affordances"]["pin"])
        self.assertIn("blocked_or_insufficient_evidence_shapes_answer", item["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
