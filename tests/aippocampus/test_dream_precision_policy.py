from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.dream import precision_policy as policy  # noqa: E402


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def dream_finding(**overrides: object) -> dict[str, object]:
    refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
    base: dict[str, object] = {
        "finding_kind": "dream_synthesized",
        "dream_function": "prospective",
        "fingerprint": "dream_pf",
        "title": "Continuity may become a source-review need",
        "summary": "Treat this as a possible next concern, not a prediction.",
        "review_state": "agent_adjudicated",
        "foreground_eligible": False,
        "formal_memory_eligible": False,
        "confidence": 0.97,
        "counter_evidence": ["no explicit request yet"],
        "activation_cues": ["continuity source review", "source-review wording"],
        "source_refs": refs,
        "bridge_claims": [
            {
                "claim": "The hint cites both source anchors.",
                "source_refs": refs,
            }
        ],
        "expires_at": "2026-06-30T00:00:00Z",
        "truth_boundary": "dream_synthesized_candidate_not_fact",
    }
    base.update(overrides)
    return base


def working_memory_row(**overrides: object) -> dict[str, object]:
    refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
    base: dict[str, object] = {
        "candidate_type": "dream_hypothesis",
        "status": "active",
        "route": "use_with_source",
        "review_state": "agent_adjudicated",
        "title": "Continuity source review",
        "summary": "Use quietly as a dream hypothesis.",
        "trigger_terms": ["continuity source review"],
        "concepts": ["continuity", "source"],
        "source_refs": refs,
        "foreground_use": {"strong_claim_requires_source_reopen": True},
        "sensitive_use_gate": {"state": "allowed"},
        "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
    }
    base.update(overrides)
    return base


class DreamPrecisionPolicyTests(unittest.TestCase):
    def test_retention_policy_separates_hard_gates_from_soft_pressure(self) -> None:
        finding = dream_finding(source_refs=[], bridge_claims=[], confidence=0.99)

        payload = policy.retention_policy_for_probe(finding, now="2026-05-30T00:00:00Z")
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["kind"], "aippocampus_dream_retention_policy")
        self.assertFalse(payload["hard_gate"]["passed"])
        self.assertIn("source_refs_present", payload["hard_gate"]["failures"])
        self.assertIn("bridge_claims_source_refs", payload["hard_gate"]["failures"])
        self.assertEqual(payload["decision"], "park_for_review")
        self.assertEqual(payload["aggregate"]["meaning"], "attention_lifecycle_not_truth")
        self.assertNotIn('"confidence"', encoded)
        self.assertEqual(payload["ignored_model_self_rating"]["input_model_confidence"], 0.99)

    def test_retention_policy_allows_source_backed_preference_continuity(self) -> None:
        finding = dream_finding(
            title="Source-backed preference continuity",
            summary=(
                "A user preference and relationship context can be retained as "
                "quiet route material without becoming a profile claim."
            ),
            confidence=0.99,
        )

        payload = policy.retention_policy_for_probe(finding, now="2026-05-30T00:00:00Z")

        self.assertTrue(payload["hard_gate"]["passed"])
        self.assertNotIn("sensitive_profile_claim_parked", payload["hard_gate"]["failures"])
        self.assertNotEqual(payload["decision"], "park_for_review")
        self.assertEqual(payload["ignored_model_self_rating"]["input_model_confidence"], 0.99)

    def test_retention_policy_still_parks_profile_or_secret_claims(self) -> None:
        finding = dream_finding(
            title="Personality diagnosis",
            summary="The user's personality secretly proves the preferred route.",
            confidence=0.7,
        )

        payload = policy.retention_policy_for_probe(finding, now="2026-05-30T00:00:00Z")

        self.assertFalse(payload["hard_gate"]["passed"])
        self.assertIn("sensitive_profile_claim_parked", payload["hard_gate"]["failures"])
        self.assertEqual(payload["decision"], "park_for_review")

    def test_structural_divergence_outranks_model_self_rating(self) -> None:
        same_voice_high_rating = [
            {
                "voice_id": "model_self",
                "frontier_id": "frontier-a",
                "candidate_kind": "trajectory_hint",
                "title": "Same answer",
                "model_self_rating": 0.99,
                "source_refs": [source_ref("session:a", "msg-a", 10)],
            }
        ]
        divergent_voices_low_rating = [
            {
                "voice_id": "compensatory",
                "frontier_id": "frontier-a",
                "candidate_kind": "blind_spot",
                "title": "Check route bias",
                "model_self_rating": 0.1,
                "source_refs": [source_ref("session:a", "msg-a", 10)],
            },
            {
                "voice_id": "prospective",
                "frontier_id": "frontier-a",
                "candidate_kind": "emergence_signal",
                "title": "Watch source-review need",
                "model_self_rating": 0.1,
                "source_refs": [source_ref("session:b", "msg-b", 20)],
            },
            {
                "voice_id": "amplification",
                "frontier_id": "frontier-a",
                "candidate_kind": "cross_thread_resonance",
                "title": "Connect to prior continuity pattern",
                "model_self_rating": 0.1,
                "source_refs": [source_ref("session:c", "msg-c", 30)],
            },
        ]

        high_self = policy.structural_divergence_component(same_voice_high_rating)
        divergent = policy.structural_divergence_component(divergent_voices_low_rating)

        self.assertGreater(divergent["value"], high_self["value"])
        self.assertEqual(high_self["ignored_model_self_rating_max"], 0.99)
        self.assertEqual(divergent["ignored_model_self_rating_max"], 0.1)
        self.assertEqual(divergent["raw"]["distinct_voice_count"], 3)
        self.assertEqual(divergent["raw"]["distinct_candidate_count"], 3)

    def test_adaptive_coefficients_recompute_from_raw_components(self) -> None:
        voices = [
            {
                "voice_id": "compensatory",
                "candidate_kind": "blind_spot",
                "title": "Check route bias",
                "source_refs": [source_ref("session:a", "msg-a", 10)],
            },
            {
                "voice_id": "prospective",
                "candidate_kind": "emergence_signal",
                "title": "Watch source-review need",
                "source_refs": [source_ref("session:b", "msg-b", 20)],
            },
        ]
        conservative = policy.retention_policy_for_probe(
            dream_finding(),
            structural_voices=voices,
            coefficients={"source_anchor_strength": 0.7, "structural_divergence": 0.1},
            coefficient_version="conservative_test",
            now="2026-05-30T00:00:00Z",
        )
        divergence_heavy = policy.recompute_retention_from_components(
            conservative["raw_components"],
            coefficients={"source_anchor_strength": 0.1, "structural_divergence": 0.7},
            coefficient_version="divergence_test",
        )

        self.assertEqual(conservative["raw_components"], divergence_heavy["raw_components"])
        self.assertNotEqual(
            conservative["aggregate"]["retention_pressure"],
            divergence_heavy["aggregate"]["retention_pressure"],
        )
        self.assertEqual(divergence_heavy["coefficient_version"], "divergence_test")

    def test_activation_policy_maps_to_existing_visibility_modes(self) -> None:
        row = working_memory_row()

        silent = policy.activation_policy_for_row(
            row,
            prompt="continuity source review",
            route_relevance=True,
            visibility_budget=0.1,
            now="2026-05-30T00:00:00Z",
        )
        gentle = policy.activation_policy_for_row(
            row,
            prompt="continuity source review",
            route_relevance=True,
            visibility_budget=0.8,
            now="2026-05-30T00:00:00Z",
        )
        source_backed = policy.activation_policy_for_row(
            row,
            prompt="continuity source review",
            route_relevance=True,
            strong_user_facing_claim=True,
            now="2026-05-30T00:00:00Z",
        )
        blocked = policy.activation_policy_for_row(
            row,
            prompt="continuity source review",
            source_visible=True,
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(silent["activation_policy"]["visibility"], "silent_tuning")
        self.assertEqual(gentle["activation_policy"]["visibility"], "active_gentle_nudge")
        self.assertEqual(source_backed["activation_policy"]["visibility"], "source_backed_recall_card")
        self.assertTrue(source_backed["activation_policy"]["requires_source_reopen"])
        self.assertEqual(blocked["activation_policy"]["visibility"], "stay_silent")
        self.assertEqual(blocked["activation_policy"]["reason"], "source_already_visible")

    def test_activation_policy_reads_trust_horizon_boundaries(self) -> None:
        expired = working_memory_row(
            trust_horizon={
                "expires_at": "2026-05-01T00:00:00Z",
                "review_after": "2026-04-01T00:00:00Z",
            }
        )
        review_due = working_memory_row(
            trust_horizon={
                "expires_at": "2026-07-01T00:00:00Z",
                "review_after": "2026-05-01T00:00:00Z",
            }
        )

        self.assertIn(
            "dream_hypothesis_expired",
            policy.activation_hard_gate_failures(expired, now="2026-06-01T00:00:00Z"),
        )
        self.assertIn(
            "trust_horizon_review_due",
            policy.activation_hard_gate_failures(review_due, now="2026-06-01T00:00:00Z"),
        )

    def test_retrospective_policy_requires_explicit_target_not_term_overlap(self) -> None:
        probe = dream_finding(fingerprint="pf_supported")
        term_overlap_only = [
            {
                "kind": "aippocampus_working_memory",
                "title": "Continuity source review appeared later",
                "source_refs": [source_ref("session:later", "msg-later", 30)],
            }
        ]
        explicit_support = [
            *term_overlap_only,
            {
                "kind": "prospective_validation_event",
                "target_finding_id": "pf_supported",
                "validation_status": "supported",
                "source_refs": [source_ref("session:explicit", "msg-explicit", 40)],
            },
        ]

        unknown = policy.retrospective_policy_for_probe(
            probe,
            term_overlap_only,
            now="2026-05-30T00:00:00Z",
        )
        supported = policy.retrospective_policy_for_probe(
            probe,
            explicit_support,
            now="2026-05-30T00:00:00Z",
        )
        encoded = json.dumps(supported, ensure_ascii=False)

        self.assertEqual(unknown["retrospective_policy"]["status"], "unknown")
        self.assertEqual(supported["retrospective_policy"]["status"], "supported")
        self.assertEqual(supported["retrospective_policy"]["evidence_ref_count"], 1)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)


if __name__ == "__main__":
    unittest.main()
