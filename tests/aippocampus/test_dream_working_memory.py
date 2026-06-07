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

    def test_constructive_artifact_projects_as_optional_probe_not_evidence(self) -> None:
        refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
        row = wm.adjudicated_dream_findings_to_working_memory(
            [
                adjudicated_finding(
                    dream_function="active_imagination",
                    candidate_kind="question_not_yet_asked",
                    activation_cues=["compaction loss probe"],
                    constructive_artifact={
                        "artifact_kind": "draft_question",
                        "draft_text": "If compaction lost the last crucial turn, what source handle would show it?",
                        "draft_origin": "active_imagination over source-ref continuity",
                        "intended_use": "foreground_probe",
                        "status": "dream_draft_not_source",
                        "truth_boundary": "dream_draft_not_source",
                        "source_refs": refs,
                        "counter_evidence": ["not an extractive quote"],
                        "when_not_to_use": ["exact source claim"],
                        "requires_source_reopen_before_claim": True,
                    },
                )
            ]
        )[0]

        self.assertIn("constructive_artifact", row)
        if "constructive_artifact" not in row:
            return
        self.assertEqual(row["constructive_artifact"]["status"], "dream_draft_not_source")
        self.assertIn("crucial turn", row["constructive_artifact"]["draft_text"])
        self.assertEqual(row["foreground_use"]["draft_artifact_action"], "optional_probe")
        self.assertEqual(row["constructive_artifact"]["foreground_use"], "optional_probe_not_evidence")
        self.assertTrue(row["constructive_artifact"]["requires_source_reopen_before_claim"])
        preview = wm.render_dream_hypothesis_preview(row)
        self.assertIn("Dream draft", preview)
        self.assertIn("optional probe", preview)
        self.assertIn("not source fact", preview)

    def test_journey_bridge_projects_as_optional_unblock_probe_not_evidence(self) -> None:
        refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
        row = wm.adjudicated_dream_findings_to_working_memory(
            [
                adjudicated_finding(
                    dream_function="amplification",
                    candidate_kind="journey_pattern_resonance",
                    activation_cues=["rollback boundary before rebuild"],
                    journey_bridge_hypothesis={
                        "bridge_kind": "shared_unblock_condition",
                        "source_journey_refs": ["journey:docs-ia", "journey:dream-routing"],
                        "shared_pattern": "both routes camp before replacing an old structure",
                        "possible_reason": "each journey may be waiting for a reversible boundary before the next move is safe",
                        "unblock_condition": "define the rollback, snapshot, or recovery boundary before rebuilding",
                        "falsification_cues": ["source shows one blockage was only missing time"],
                        "status": "dream_bridge_not_source_fact",
                        "truth_boundary": "dream_bridge_not_source_fact",
                        "source_refs": refs,
                        "foreground_use": "journey_unblock_probe_not_evidence",
                        "requires_source_reopen_before_claim": True,
                    },
                )
            ]
        )[0]

        self.assertIn("journey_bridge_hypothesis", row)
        bridge = row["journey_bridge_hypothesis"]
        self.assertEqual(bridge["status"], "dream_bridge_not_source_fact")
        self.assertEqual(bridge["foreground_use"], "journey_unblock_probe_not_evidence")
        self.assertIn("rollback", bridge["unblock_condition"])
        self.assertIn("rollback boundary before rebuild", row["trigger_terms"])
        self.assertTrue(any("define the rollback" in term for term in row["trigger_terms"]))
        self.assertEqual(row["foreground_use"]["journey_bridge_action"], "optional_unblock_probe_on_trigger")

        plan = wm.plan_dream_hypothesis_use(
            row,
            prompt="这条 journey 下一步是不是要先定义 rollback boundary？",
            now="2026-06-01T00:00:00Z",
        )
        preview = wm.render_dream_hypothesis_preview(row)

        self.assertEqual(plan["action"], "deliver_as_optional_unblock_probe")
        self.assertEqual(plan["reason"], "journey_bridge_trigger_matched")
        self.assertEqual(plan["journey_bridge_diagnostic"], "delivered_as_optional_unblock_probe")
        self.assertIn("rollback", plan["unblock_condition"])
        self.assertIn("Journey bridge Dream hypothesis", preview)
        self.assertIn("optional unblock probe", preview)
        self.assertIn("not source fact", preview)

    def test_prospective_invitation_surfaces_only_on_trigger_and_not_when_annoying_or_expired(self) -> None:
        low_risk = wm.adjudicated_dream_findings_to_working_memory(
            [
                adjudicated_finding(
                    dream_function="prospective",
                    activation_cues=["AGI blank starting point"],
                    review_after="2026-06-20T00:00:00Z",
                    expires_at="2026-07-01T00:00:00Z",
                    prospective_invitation={
                        "emerging_theme": "AI as subconscious layer and blank starting point",
                        "trigger_condition": "user mentions AGI, selfhood, or blankness",
                        "suggested_opening": "Is the blank starting point question live here?",
                        "invitation_type": "light_question",
                        "expires_after": "14d",
                        "expires_at": "2026-07-01T00:00:00Z",
                        "annoyance_risk": "low",
                        "status": "dream_invitation_not_source_fact",
                        "truth_boundary": "dream_invitation_not_source_fact",
                        "requires_source_reopen_before_claim": True,
                    },
                )
            ]
        )[0]
        self.assertIn("prospective_invitation", low_risk)
        if "prospective_invitation" not in low_risk:
            return
        invitation = dict(low_risk.get("prospective_invitation") or {})

        delivered = wm.plan_dream_hypothesis_use(
            low_risk,
            prompt="AGI 里的 blank starting point 要怎么理解？",
            now="2026-06-01T00:00:00Z",
        )
        unrelated = wm.plan_dream_hypothesis_use(
            low_risk,
            prompt="帮我看一个 Rust borrow checker 报错",
            now="2026-06-01T00:00:00Z",
        )
        high_annoyance = wm.plan_dream_hypothesis_use(
            {
                **low_risk,
                "prospective_invitation": {
                    **invitation,
                    "annoyance_risk": "high",
                },
            },
            prompt="AGI 里的 blank starting point 要怎么理解？",
            now="2026-06-01T00:00:00Z",
        )
        expired = wm.plan_dream_hypothesis_use(
            {
                **low_risk,
                "expires_at": "2026-05-01T00:00:00Z",
                "prospective_invitation": {
                    **invitation,
                    "expires_at": "2026-05-01T00:00:00Z",
                },
            },
            prompt="AGI 里的 blank starting point 要怎么理解？",
            now="2026-06-01T00:00:00Z",
        )

        self.assertEqual(low_risk["foreground_use"]["prospective_invitation_action"], "optional_question_on_trigger")
        self.assertEqual(delivered["action"], "deliver_as_optional_question")
        self.assertEqual(delivered["reason"], "prospective_invitation_trigger_matched")
        self.assertEqual(delivered["invitation_diagnostic"], "delivered_as_optional_question")
        self.assertIn("blank starting point", delivered["suggested_opening"])
        self.assertEqual(unrelated["action"], "stay_silent")
        self.assertEqual(unrelated["reason"], "trigger_not_matched")
        self.assertEqual(unrelated["invitation_diagnostic"], "trigger_not_matched")
        self.assertEqual(high_annoyance["action"], "stay_silent")
        self.assertEqual(high_annoyance["reason"], "prospective_invitation_annoyance_high")
        self.assertEqual(high_annoyance["invitation_diagnostic"], "annoyance_suppressed")
        self.assertEqual(expired["reason"], "dream_hypothesis_expired")
        self.assertEqual(expired["invitation_diagnostic"], "delivery_gate_blocked")

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
