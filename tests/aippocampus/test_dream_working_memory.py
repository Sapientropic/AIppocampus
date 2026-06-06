from __future__ import annotations

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

from aippocampus_runtime.dream import working_memory as wm  # noqa: E402


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def bridge_claim(refs: list[dict[str, object]]) -> dict[str, object]:
    return {"claim": "This is a hypothesis over selected source refs.", "source_refs": refs}


def adjudicated_finding(**overrides: object) -> dict[str, object]:
    refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
    finding: dict[str, object] = {
        "finding_kind": "dream_synthesized",
        "dream_function": "amplification",
        "review_state": "agent_adjudicated",
        "title": "Continuity source-ref bridge",
        "summary": "Use as a tentative bridge only when it changes the route.",
        "confidence": 0.66,
        "source_refs": refs,
        "bridge_claims": [bridge_claim(refs)],
        "downstream_use": ["working_memory", "ambient_recall_card", "reflection_space"],
    }
    finding.update(overrides)
    return finding


class DreamWorkingMemoryTests(unittest.TestCase):
    def test_adjudicated_dream_row_defaults_to_quiet_substrate_use(self) -> None:
        rows = wm.adjudicated_dream_findings_to_working_memory([adjudicated_finding()])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["candidate_type"], "dream_hypothesis")
        self.assertEqual(row["truth_boundary"], "adjudicated_dream_hypothesis_not_fact")
        self.assertEqual(row["foreground_use"]["default_action"], "quiet_substrate")
        self.assertTrue(row["foreground_use"]["strong_claim_requires_source_reopen"])

        plan = wm.plan_dream_hypothesis_use(row, prompt="continuity source refs", now="2026-05-30T00:00:00Z")
        self.assertEqual(plan["action"], "use_quietly")
        self.assertEqual(plan["route"], "working_memory")

        preview = wm.render_dream_hypothesis_preview(row)
        self.assertIn("Dream hypothesis", preview)
        self.assertIn("not source fact", preview)
        self.assertIn("reopen source", preview)

    def test_dream_hypothesis_stays_silent_when_source_visible_or_annoying_or_expired(self) -> None:
        row = wm.adjudicated_dream_findings_to_working_memory(
            [adjudicated_finding(expires_at="2026-05-01T00:00:00Z")]
        )[0]

        self.assertEqual(
            wm.plan_dream_hypothesis_use(row, source_visible=True, now="2026-04-01T00:00:00Z")["action"],
            "stay_silent",
        )
        self.assertEqual(
            wm.plan_dream_hypothesis_use(row, annoyance_risk="high", now="2026-04-01T00:00:00Z")["action"],
            "stay_silent",
        )
        expired = wm.plan_dream_hypothesis_use(row, now="2026-05-30T00:00:00Z")
        self.assertEqual(expired["action"], "stay_silent")
        self.assertEqual(expired["reason"], "dream_hypothesis_expired")

    def test_strong_user_facing_claim_requires_source_reopen(self) -> None:
        row = wm.adjudicated_dream_findings_to_working_memory([adjudicated_finding()])[0]

        plan = wm.plan_dream_hypothesis_use(
            row,
            strong_user_facing_claim=True,
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(plan["action"], "reopen_source")
        self.assertEqual(plan["reason"], "strong_claim_requires_source_reopen")
        self.assertTrue(plan["requires_source_reopen"])

    def test_adjudicated_dream_row_carries_trust_horizon_capsule_metadata(self) -> None:
        row = wm.adjudicated_dream_findings_to_working_memory(
            [
                adjudicated_finding(
                    created_at="2026-05-01T00:00:00Z",
                    validated_at="2026-05-03T00:00:00Z",
                    validated_by="source_guard",
                    review_after="2026-06-01T00:00:00Z",
                    expires_at="2026-07-01T00:00:00Z",
                    invalidation_triggers=["source_fingerprint_changed", "user_correction"],
                )
            ]
        )[0]

        horizon = row["trust_horizon"]

        self.assertEqual(horizon["validated_at"], "2026-05-03T00:00:00Z")
        self.assertEqual(horizon["validated_by"], "source_guard")
        self.assertEqual(horizon["review_after"], "2026-06-01T00:00:00Z")
        self.assertEqual(horizon["expires_at"], "2026-07-01T00:00:00Z")
        self.assertEqual(horizon["visibility_tier"], "quiet_substrate")
        self.assertIn("source_fingerprint_changed", horizon["invalidation_triggers"])
        self.assertIn("trust_horizon_review_due", horizon["invalidation_triggers"])
        self.assertTrue(horizon["source_fingerprint"].startswith("dreamsrc_"))
        self.assertEqual(row["source_fingerprint"], horizon["source_fingerprint"])
        self.assertEqual(row["validated_at"], horizon["validated_at"])
        self.assertEqual(row["validated_by"], horizon["validated_by"])
        self.assertEqual(row["review_after"], horizon["review_after"])
        self.assertEqual(row["invalidation_triggers"], horizon["invalidation_triggers"])
        self.assertEqual(row["visibility_tier"], horizon["visibility_tier"])

    def test_trust_horizon_allows_quiet_use_but_reopens_on_invalidation_boundaries(self) -> None:
        row = wm.adjudicated_dream_findings_to_working_memory(
            [
                adjudicated_finding(
                    expires_at="2026-07-01T00:00:00Z",
                    invalidation_triggers=["source_fingerprint_changed", "contradiction_visible"],
                )
            ]
        )[0]
        fingerprint = row["trust_horizon"]["source_fingerprint"]

        quiet = wm.plan_dream_hypothesis_use(
            row,
            prompt="continuity source refs",
            now="2026-06-01T00:00:00Z",
        )
        exact = wm.plan_dream_hypothesis_use(
            row,
            exact_or_quote_claim=True,
            now="2026-06-01T00:00:00Z",
        )
        contradicted = wm.plan_dream_hypothesis_use(
            row,
            contradiction_visible=True,
            now="2026-06-01T00:00:00Z",
        )
        requested = wm.plan_dream_hypothesis_use(
            row,
            user_requested_evidence=True,
            now="2026-06-01T00:00:00Z",
        )
        changed_source = wm.plan_dream_hypothesis_use(
            row,
            source_fingerprint_current=fingerprint + "_new",
            now="2026-06-01T00:00:00Z",
        )
        review_due = wm.plan_dream_hypothesis_use(
            wm.adjudicated_dream_findings_to_working_memory(
                [
                    adjudicated_finding(
                        review_after="2026-05-01T00:00:00Z",
                        expires_at="2026-07-01T00:00:00Z",
                    )
                ]
            )[0],
            prompt="continuity source refs",
            now="2026-06-01T00:00:00Z",
        )

        self.assertEqual(quiet["action"], "use_quietly")
        self.assertEqual(quiet["trust_horizon_status"], "valid")
        self.assertEqual(exact["action"], "reopen_source")
        self.assertEqual(exact["reason"], "exact_or_quote_claim_requires_source_reopen")
        self.assertEqual(contradicted["reason"], "contradiction_visible_requires_source_reopen")
        self.assertEqual(requested["reason"], "user_requested_evidence_requires_source_reopen")
        self.assertEqual(changed_source["reason"], "source_fingerprint_changed")
        self.assertEqual(review_due["reason"], "trust_horizon_review_due_requires_source_reopen")

    def test_source_fingerprint_uses_raw_ref_identity_before_working_memory_cleanup(self) -> None:
        refs_a = [
            {**source_ref("session:a", "msg-a", 10), "source_id": "source-a"},
            {**source_ref("session:a", "msg-a", 10), "source_id": "source-b"},
        ]
        refs_b = [
            {**source_ref("session:a", "msg-a", 10), "source_id": "source-a"},
            {**source_ref("session:a", "msg-a", 10), "source_id": "source-c"},
        ]

        row_a = wm.adjudicated_dream_findings_to_working_memory(
            [adjudicated_finding(source_refs=refs_a, bridge_claims=[bridge_claim(refs_a)])]
        )[0]
        row_b = wm.adjudicated_dream_findings_to_working_memory(
            [adjudicated_finding(source_refs=refs_b, bridge_claims=[bridge_claim(refs_b)])]
        )[0]

        self.assertEqual(row_a["source_refs"], row_b["source_refs"])
        self.assertNotEqual(row_a["source_fingerprint"], row_b["source_fingerprint"])

    def test_dream_hypothesis_requires_route_relevance_before_quiet_use(self) -> None:
        row = wm.adjudicated_dream_findings_to_working_memory([adjudicated_finding()])[0]

        plan = wm.plan_dream_hypothesis_use(
            row,
            prompt="unrelated deployment invoice question",
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(plan["action"], "stay_silent")
        self.assertEqual(plan["reason"], "no_route_relevance")

    def test_model_backed_dream_projection_uses_llm_activation_cues_not_summary_terms(self) -> None:
        row = wm.adjudicated_dream_findings_to_working_memory(
            [
                adjudicated_finding(
                    summary=(
                        "This summary mentions checklist, examples, state, and completeness, "
                        "but those words are explanatory background rather than activation cues."
                    ),
                    activation_cues=[
                        "continuity source review",
                        "source-ref continuity",
                    ],
                )
            ]
        )[0]

        self.assertEqual(row["trigger_terms"], ["continuity source review", "source-ref continuity"])
        self.assertNotIn("checklist", row["trigger_terms"])
        self.assertNotIn("examples", row["trigger_terms"])
        self.assertNotIn("completeness", row["trigger_terms"])

    def test_sensitive_gate_ignores_negative_profile_boundary_copy(self) -> None:
        adjudicated = wm.background_adjudicate_dream_finding(
            adjudicated_finding(
                summary=(
                    "Treat this as a dream-synthesized candidate for review, "
                    "not as a user-profile fact."
                )
            )
        )
        rows = wm.adjudicated_dream_findings_to_working_memory([adjudicated])

        self.assertEqual(adjudicated["adjudication_result"]["status"], "accepted")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sensitive_use_gate"]["state"], "allowed")

    def test_preference_relationship_and_high_confidence_are_not_sensitive_by_themselves(self) -> None:
        continuity = adjudicated_finding(
            title="Preference and relationship continuity",
            summary=(
                "A source-backed preference and relationship-context hypothesis "
                "may help quiet route selection without becoming a profile fact."
            ),
            confidence=0.94,
        )

        adjudicated = wm.background_adjudicate_dream_finding(continuity)
        rows = wm.adjudicated_dream_findings_to_working_memory([adjudicated])

        self.assertEqual(adjudicated["adjudication_result"]["status"], "accepted")
        self.assertNotIn("sensitive_use_gate", adjudicated["adjudication_result"]["failed_checks"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sensitive_use_gate"]["state"], "allowed")
        self.assertEqual(rows[0]["foreground_use"]["default_action"], "quiet_substrate")

    def test_profile_or_secret_dream_hypothesis_is_parked_before_working_memory_projection(self) -> None:
        sensitive = adjudicated_finding(
            title="Durable personality diagnosis",
            summary="The user's personality means they secretly prefer this route.",
            confidence=0.72,
        )

        adjudicated = wm.background_adjudicate_dream_finding(sensitive)

        self.assertEqual(adjudicated["adjudication_result"]["status"], "parked")
        self.assertIn("sensitive_use_gate", adjudicated["adjudication_result"]["failed_checks"])
        self.assertEqual(wm.adjudicated_dream_findings_to_working_memory([adjudicated]), [])


if __name__ == "__main__":
    unittest.main()
