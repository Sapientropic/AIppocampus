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

import dream_working_memory as wm  # noqa: E402


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

    def test_sensitive_dream_hypothesis_is_parked_before_working_memory_projection(self) -> None:
        sensitive = adjudicated_finding(
            title="Durable personality preference",
            summary="The user's personality means they secretly prefer this route.",
            confidence=0.72,
        )

        adjudicated = wm.background_adjudicate_dream_finding(sensitive)

        self.assertEqual(adjudicated["adjudication_result"]["status"], "parked")
        self.assertIn("sensitive_use_gate", adjudicated["adjudication_result"]["failed_checks"])
        self.assertEqual(wm.adjudicated_dream_findings_to_working_memory([adjudicated]), [])


if __name__ == "__main__":
    unittest.main()
