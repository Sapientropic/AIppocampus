from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.navigation import avatar_illumination  # noqa: E402


def fixture_card() -> dict[str, object]:
    return {
        "kind": "source_backed_familiarity_card",
        "domain": "repo",
        "card_id": "card-runtime-boundary",
        "landmark": "runtime owner and verification boundary",
        "category": "runtime_owner",
        "boundary": "Keep route hints source-backed and navigation-only.",
        "route_terms": ["runtime", "implementation", "test", "review", "source"],
        "source_refs": [
            {"path": "docs/architecture/source-backed-familiarity-map.md", "line": 20},
            {"path": "skills/aippocampus/scripts/aippocampus_runtime/navigation/repo_familiarity.py", "line": 1},
        ],
        "freshness": "current",
        "invalidation": {
            "commit": "abc123",
            "files": [
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/navigation/repo_familiarity.py",
                    "sha256": "hash-still-matches",
                }
            ],
        },
        "why_now": "Relevant before changing route packet posture.",
        "action_delta_required": "Reopen the runtime owner and focused tests before changing projection.",
        "first_source_to_reopen": "skills/aippocampus/scripts/aippocampus_runtime/navigation/repo_familiarity.py",
        "stop_after": "Stop after source refs and focused tests confirm the boundary.",
        "do_not_use_for": ["current repo facts without reopening source"],
        "decision_shadow": {
            "status": "rejected_route",
            "route_constraint": "do_not_repeat_old_global_warning_channel",
            "source_thickness": "strong",
        },
        "injection_policy": {
            "support_level": "navigation",
            "source_reopen_required": True,
            "repo_commit": "abc123",
        },
    }


class AvatarIlluminationTests(unittest.TestCase):
    def test_valid_card_produces_source_backed_avatar_state_and_compact_packet(self) -> None:
        state = avatar_illumination.build_source_backed_avatar_state(
            fixture_card(),
            task="Implement the runtime route projection and add focused tests",
        )

        self.assertEqual(state["kind"], "source_backed_avatar_state")
        self.assertIn(state["lifecycle_state"], {"active", "weak"})
        self.assertTrue(state["activation"]["active"])
        self.assertGreater(state["activation"]["source_density"], 0)
        self.assertGreater(state["activation"]["source_diversity"], 0)
        self.assertEqual(state["activation"]["authority_floor"], "navigation")
        self.assertEqual(state["claim_permission"], "none")
        self.assertFalse(state["fact_claim_allowed"])
        self.assertIn("earth", state["facet_illumination"])
        self.assertIn("human", state["facet_illumination"])
        self.assertIn("heaven", state["facet_illumination"])
        self.assertTrue(any(item["facet"] == "builder" for item in state["active_facets"]))
        self.assertTrue(any(item["facet"] == "reviewer" for item in state["active_facets"]))
        self.assertTrue(state["posture_tensions"])

        packet = avatar_illumination.project_avatar_state_for_foreground(state, max_packet_bytes=700)

        self.assertTrue(packet["emitted"])
        self.assertEqual(packet["claim_permission"], "none")
        self.assertTrue(packet["source_reopen_required_before_claim"])
        self.assertNotIn("source_refs", packet)
        self.assertLessEqual(packet["packet_bytes"], 700)

    def test_unrelated_task_does_not_receive_positive_avatar_posture(self) -> None:
        state = avatar_illumination.build_source_backed_avatar_state(
            fixture_card(),
            task="casual chat about weather",
        )

        packet = avatar_illumination.project_avatar_state_for_foreground(state)

        self.assertEqual(state["task_relevance"]["status"], "irrelevant_to_task")
        self.assertFalse(state["selected_for_task"])
        self.assertFalse(packet["emitted"])
        self.assertEqual(packet["reason"], "irrelevant_to_task")
        self.assertEqual(packet["recommended_next"], "continue_without_avatar")
        self.assertEqual(packet["claim_permission"], "none")

    def test_partial_invalidation_narrows_posture_and_retains_shadow_record(self) -> None:
        state = avatar_illumination.build_source_backed_avatar_state(
            fixture_card(),
            task="Review the changed source boundary",
            semantic_invalidation_events=[
                {
                    "reason_code": "topic_epoch_changed",
                    "partial_invalidation": True,
                    "narrow_to_facets": ["archivist"],
                    "first_source_to_reopen": "docs/architecture/source-backed-familiarity-map.md",
                    "source_refs": [{"path": "docs/architecture/source-backed-familiarity-map.md", "line": 70}],
                }
            ],
        )

        self.assertEqual(state["lifecycle_state"], "narrowed")
        self.assertEqual(state["card_state"], "partial_invalidation")
        self.assertEqual([item["facet"] for item in state["active_facets"]], ["archivist"])
        self.assertEqual(state["shadow_record"]["status"], "shadow_candidate")
        self.assertEqual(state["shadow_record"]["broader_scope_status"], "suspect_until_reopened")
        self.assertFalse(state["fact_claim_allowed"])
        self.assertEqual(state["semantic_invalidation"]["reason_codes"], ["topic_epoch_changed"])

    def test_semantic_invalidation_suppresses_card_even_when_file_hashes_can_match(self) -> None:
        state = avatar_illumination.build_source_backed_avatar_state(
            fixture_card(),
            task="Change runtime projection",
            semantic_invalidation_events=[
                {
                    "reason_code": "user_correction",
                    "source_refs": [{"path": "docs/architecture/source-backed-familiarity-map.md", "line": 44}],
                    "first_source_to_reopen": "docs/architecture/source-backed-familiarity-map.md",
                    "file_fingerprints_still_match": True,
                }
            ],
        )

        self.assertEqual(state["lifecycle_state"], "shadowed")
        self.assertEqual(state["card_state"], "suspect")
        self.assertFalse(state["activation"]["active"])
        self.assertEqual(state["action_grammar"], "direction_with_ref")
        self.assertEqual(state["semantic_invalidation"]["reason_codes"], ["user_correction"])

        packet = avatar_illumination.project_avatar_state_for_foreground(state)

        self.assertFalse(packet["emitted"])
        self.assertEqual(packet["recommended_next"], "reopen_source")
        self.assertEqual(packet["claim_permission"], "none")

    def test_semantic_reason_allowlist_is_stable_and_rejects_vocabulary_drift(self) -> None:
        invalidation = avatar_illumination.semantic_invalidation_state(
            [
                {
                    "reason_code": "superseding_decision",
                    "source_refs": [{"path": "docs/architecture/source-backed-familiarity-map.md"}],
                },
                {
                    "reason_code": "review_due",
                    "first_source_to_reopen": "docs/architecture/source-backed-familiarity-map.md",
                },
                {
                    "reason_code": "macro_recheck_required",
                    "source_refs": [{"path": "docs/architecture/runtime-recheck-events.md"}],
                },
                {
                    "reason_code": "vocabulary_drift",
                    "source_refs": [{"path": "docs/architecture/source-backed-familiarity-map.md"}],
                },
            ]
        )

        self.assertEqual(
            invalidation["reason_codes"],
            ["superseding_decision", "review_due", "macro_recheck_required"],
        )
        self.assertEqual(invalidation["rejected_events"][0]["reason"], "unsupported_reason_code")
        self.assertTrue(invalidation["source_reopen_required_before_use"])

    def test_blocked_boundary_is_absent_and_cannot_emit_foreground(self) -> None:
        card = fixture_card()
        card["privacy_state"] = "blocked"

        state = avatar_illumination.build_source_backed_avatar_state(card, task="Review runtime source")

        self.assertEqual(state["lifecycle_state"], "absent")
        self.assertEqual(state["card_state"], "blocked_boundary")
        self.assertFalse(state["activation"]["active"])
        self.assertEqual(state["action_grammar"], "ignore_or_blocked")

        packet = avatar_illumination.project_avatar_state_for_foreground(state)

        self.assertFalse(packet["emitted"])
        self.assertEqual(packet["action_grammar"], "ignore_or_blocked")

    def test_fresh_decision_shadow_projects_negative_attention_when_task_relevant(self) -> None:
        guidance = avatar_illumination.decision_shadow_negative_attention(
            fixture_card(),
            task="Runtime rejected route projection",
        )

        self.assertTrue(guidance["emitted"])
        self.assertEqual(guidance["guidance_action"], "avoid")
        self.assertEqual(guidance["status"], "active_negative_attention")
        self.assertFalse(guidance["still_rejected_claim_allowed"])
        self.assertEqual(guidance["authority_level"], "direction_only")
        self.assertEqual(guidance["claim_permission"], "none")
        self.assertTrue(guidance["source_refs"])

    def test_invalidated_decision_shadow_becomes_reopen_candidate_not_blacklist(self) -> None:
        guidance = avatar_illumination.decision_shadow_negative_attention(
            fixture_card(),
            task="Runtime rejected route projection",
            semantic_invalidation_events=[
                {
                    "reason_code": "superseding_decision",
                    "source_refs": [{"path": "docs/architecture/source-backed-familiarity-map.md", "line": 80}],
                }
            ],
        )

        self.assertTrue(guidance["emitted"])
        self.assertEqual(guidance["guidance_action"], "reopen_first")
        self.assertEqual(guidance["status"], "shadow_candidate")
        self.assertTrue(guidance["old_rejection_reason_invalidated"])
        self.assertFalse(guidance["still_rejected_claim_allowed"])
        self.assertFalse(guidance["permanent_blacklist"])

    def test_non_coding_irrelevant_task_does_not_receive_repo_shadow(self) -> None:
        guidance = avatar_illumination.decision_shadow_negative_attention(
            fixture_card(),
            task="Polish README public positioning copy",
        )

        self.assertFalse(guidance["emitted"])
        self.assertEqual(guidance["reason"], "irrelevant_to_task")
        self.assertEqual(guidance["claim_permission"], "none")


if __name__ == "__main__":
    unittest.main()
