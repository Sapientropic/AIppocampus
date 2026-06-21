from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.coding import agency_affordance as agency


def source_ref(line: int = 10, *, message_id: str | None = None) -> dict[str, object]:
    return {
        "thread_key": "session:agency-test",
        "message_id": message_id or f"msg-{line}",
        "source_line": line,
        "timestamp": "2026-05-30T00:00:00Z",
    }

class AgencyAffordanceTests(unittest.TestCase):
    def test_should_stay_silent_for_weak_visible_or_repeated_cues(self) -> None:
        weak_map = agency.build_agency_affordance_map(
            ambient_recall_cards=[
                {
                    "summary": "Similar words matched, but no action changes.",
                    "intervention_level": "light_nudge",
                    "source_refs": [source_ref(1)],
                    "matched_terms_only": True,
                }
            ],
            topic_epoch="epoch-1",
        )
        weak_selection = agency.select_agency_tickets(
            weak_map,
            trigger="compaction_loss",
            topic_epoch="epoch-1",
        )

        visible_ref = source_ref(2)
        visible_map = agency.build_agency_affordance_map(
            ambient_recall_cards=[
                {
                    "summary": "The user can already see this source-backed reminder.",
                    "intervention_level": "light_nudge",
                    "source_refs": [visible_ref],
                }
            ],
            topic_epoch="epoch-1",
        )
        visible_selection = agency.select_agency_tickets(
            visible_map,
            trigger="compaction_loss",
            topic_epoch="epoch-1",
            visible_context_refs=[visible_ref],
        )

        affordance = visible_map["affordances"][0]
        repeated_selection = agency.select_agency_tickets(
            visible_map,
            trigger="compaction_loss",
            topic_epoch="epoch-1",
            surface_history=[
                {
                    "topic_epoch": "epoch-1",
                    "affordance_id": affordance["affordance_id"],
                }
            ],
        )

        self.assertEqual(weak_selection["foreground_tickets"], [])
        self.assertEqual(visible_selection["foreground_tickets"], [])
        self.assertEqual(repeated_selection["foreground_tickets"], [])

    def test_should_remind_after_compaction_with_source_backed_nudge(self) -> None:
        affordance_map = agency.build_agency_affordance_map(
            ambient_recall_cards=[
                {
                    "summary": "Keep the anti-nag boundary visible after compaction.",
                    "intervention_level": "light_nudge",
                    "source_refs": [source_ref(10)],
                    "annoyance_risk": "medium",
                }
            ],
            topic_epoch="epoch-remind",
        )

        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="compaction_loss",
            topic_epoch="epoch-remind",
        )
        ticket = selection["foreground_tickets"][0]

        self.assertEqual(len(selection["foreground_tickets"]), 1)
        self.assertEqual(ticket["kind"], agency.TICKET_KIND)
        self.assertEqual(ticket["intervention_level"], "light_nudge")
        self.assertEqual(ticket["why_now"]["trigger"], "compaction_loss")
        self.assertEqual(ticket["source_thickness"], "usable")
        self.assertTrue(ticket["host_boundary"]["aippocampus_proposes_only"])
        self.assertIn("requires_user_confirmation", ticket)

    def test_should_warn_for_user_correction_without_push_forward(self) -> None:
        affordance_map = agency.build_agency_affordance_map(
            correction_windows=[
                {
                    "kind": "correction_active_task_anchor",
                    "summary": "Do not repeat the ignored registry import route.",
                    "instruction": "Warn before repeating the ignored correction.",
                    "adjudication_status": "valid_ignored",
                    "source_refs": [source_ref(20), source_ref(21)],
                }
            ],
            topic_epoch="epoch-warning",
        )

        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="user_correction",
            topic_epoch="epoch-warning",
        )
        ticket = selection["foreground_tickets"][0]

        self.assertEqual(ticket["intervention_level"], "warning")
        self.assertEqual(ticket["proposed_action"]["verb"], "warn_route")
        self.assertNotEqual(ticket["intervention_level"], "push_forward")
        self.assertTrue(ticket["requires_user_confirmation"])
        self.assertEqual(ticket["host_boundary"]["host_decides_permission"], True)

    def test_should_offer_next_step_for_scheduled_revisit(self) -> None:
        affordance_map = agency.build_agency_affordance_map(
            scheduled_revisits=[
                {
                    "summary": "Review the Track E benchmark sketch now that the revisit window opened.",
                    "source_refs": [source_ref(30)],
                    "preconditions": ["user is still on the same research track"],
                }
            ],
            topic_epoch="epoch-revisit",
        )

        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="scheduled_revisit",
            topic_epoch="epoch-revisit",
        )
        ticket = selection["foreground_tickets"][0]

        self.assertEqual(ticket["intervention_level"], "offer_next_step")
        self.assertEqual(ticket["why_now"]["trigger"], "scheduled_revisit")
        self.assertEqual(ticket["proposed_action"]["verb"], "ask_checkin")
        self.assertIn("user is still on the same research track", ticket["preconditions"])
        self.assertTrue(ticket["requires_user_confirmation"])

    def test_thin_source_cannot_foreground_except_state_check(self) -> None:
        thin_offer_map = agency.build_agency_affordance_map(
            scheduled_revisits=[
                {
                    "summary": "Offer a next step without source refs should stay out of foreground.",
                }
            ],
            topic_epoch="epoch-thin",
        )
        thin_offer = agency.select_agency_tickets(
            thin_offer_map,
            trigger="scheduled_revisit",
            topic_epoch="epoch-thin",
        )

        state_check_map = agency.build_agency_affordance_map(
            unfinished_tasks=[
                {
                    "summary": "Ask whether to resume the old task.",
                }
            ],
            topic_epoch="epoch-thin",
        )
        state_check = agency.select_agency_tickets(
            state_check_map,
            trigger="unfinished_task_reentry",
            topic_epoch="epoch-thin",
        )

        self.assertEqual(thin_offer["foreground_tickets"], [])
        self.assertEqual(len(state_check["foreground_tickets"]), 1)
        self.assertEqual(state_check["foreground_tickets"][0]["intervention_level"], "state_check")
        self.assertEqual(state_check["foreground_tickets"][0]["source_thickness"], "thin")

    def test_selector_limits_foreground_and_backstage_tickets_per_epoch(self) -> None:
        affordance_map = agency.build_agency_affordance_map(
            ambient_recall_cards=[
                {
                    "summary": "First useful nudge.",
                    "intervention_level": "light_nudge",
                    "source_refs": [source_ref(40)],
                },
                {
                    "summary": "Second useful nudge should wait.",
                    "intervention_level": "light_nudge",
                    "source_refs": [source_ref(41)],
                },
                {
                    "summary": "Backstage refresh one.",
                    "intervention_level": "backstage_only",
                    "source_refs": [source_ref(42)],
                },
                {
                    "summary": "Backstage refresh two.",
                    "intervention_level": "backstage_only",
                    "source_refs": [source_ref(43)],
                },
            ],
            topic_epoch="epoch-limit",
        )

        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="compaction_loss",
            topic_epoch="epoch-limit",
            foreground_limit=1,
            backstage_limit=1,
        )

        self.assertEqual(len(selection["foreground_tickets"]), 1)
        self.assertEqual(len(selection["backstage_tickets"]), 1)
        self.assertGreaterEqual(selection["suppressed_count"], 1)

    def test_dream_hypotheses_remain_backstage_and_respect_sensitive_gate(self) -> None:
        allowed = {
            "candidate_type": "dream_hypothesis",
            "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
            "title": "Continuity dream bridge",
            "summary": "Use this hypothesis only as route context.",
            "intervention_level": "warning",
            "source_refs": [source_ref(45)],
            "sensitive_use_gate": {"state": "allowed"},
        }
        blocked = {
            **allowed,
            "title": "Sensitive dream bridge",
            "source_refs": [source_ref(46)],
            "sensitive_use_gate": {"state": "blocked"},
        }
        affordance_map = agency.build_agency_affordance_map(
            dream_outputs=[allowed, blocked],
            topic_epoch="epoch-dream-agency",
        )

        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="compaction_loss",
            topic_epoch="epoch-dream-agency",
        )

        self.assertEqual(len(affordance_map["affordances"]), 1)
        self.assertEqual(selection["foreground_tickets"], [])
        self.assertEqual(len(selection["backstage_tickets"]), 1)
        self.assertEqual(selection["backstage_tickets"][0]["intervention_level"], "backstage_only")
        self.assertFalse(selection["backstage_tickets"][0]["foreground"])

    def test_journey_resonance_remains_backstage_source_refresh_without_raw_refs(self) -> None:
        resonance = {
            "kind": "aippocampus_content_light_journey_resonance",
            "status": "hypotheses_available",
            "intervention_level": "warning",
            "source_refs": [source_ref(47, message_id="msg-raw-journey-resonance")],
            "matches": [
                {
                    "resonance_id": "jr_res_fixture",
                    "suggested_use": "source_refresh_cue",
                    "hypothesis": (
                        "A source-free Journey shape resembles another project. "
                        "Reopen sources inside that project before treating any route as evidence."
                    ),
                    "shared_structure": {
                        "arc_sequence": ["屯", "蒙", "需"],
                        "dynamics_labels": ["dynamics:stalled-start"],
                    },
                    "candidate_patterns": ["stale_generated_artifact", "rejected_route"],
                    "claim_boundary": {
                        "hypothesis_not_fact": True,
                        "not_evidence": True,
                        "requires_source_reopen_before_use": True,
                    },
                    "privacy_boundary": {
                        "content_light_only": True,
                        "raw_source_refs_shared": False,
                        "raw_source_text_shared": False,
                    },
                }
            ],
        }

        affordance_map = agency.build_agency_affordance_map(
            journey_resonance_inputs=[resonance],
            topic_epoch="epoch-journey-resonance",
        )
        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="compaction_loss",
            topic_epoch="epoch-journey-resonance",
        )

        self.assertEqual(len(affordance_map["affordances"]), 1)
        affordance = affordance_map["affordances"][0]
        self.assertEqual(affordance["source_kind"], "journey_resonance")
        self.assertEqual(affordance["intervention_level"], "backstage_only")
        self.assertEqual(affordance["proposed_action"]["verb"], "refresh_sources")
        self.assertEqual(affordance["source_thickness"], "thin")
        self.assertEqual(affordance["evidence_refs"], [])
        self.assertTrue(affordance["matched_terms_only"])
        self.assertEqual(selection["foreground_tickets"], [])
        self.assertEqual(len(selection["backstage_tickets"]), 1)
        self.assertFalse(selection["backstage_tickets"][0]["foreground"])

        dumped = json.dumps({"map": affordance_map, "selection": selection}, ensure_ascii=False, sort_keys=True)
        self.assertIn("source-free Journey shape", dumped)
        self.assertNotIn("msg-raw-journey-resonance", dumped)

    def test_feedback_events_cover_expected_outcomes(self) -> None:
        affordance_map = agency.build_agency_affordance_map(
            ambient_recall_cards=[
                {
                    "summary": "Keep a source-backed reminder available.",
                    "intervention_level": "light_nudge",
                    "source_refs": [source_ref(50)],
                }
            ],
            topic_epoch="epoch-feedback",
        )
        ticket = agency.select_agency_tickets(
            affordance_map,
            trigger="compaction_loss",
            topic_epoch="epoch-feedback",
        )["foreground_tickets"][0]

        outcomes = {
            outcome: agency.record_ticket_feedback(ticket, outcome=outcome, tool_status=outcome)
            for outcome in agency.OUTCOME_FEEDBACK
        }

        self.assertEqual(set(outcomes), set(agency.OUTCOME_FEEDBACK))
        self.assertEqual(outcomes["accepted"]["kind"], agency.FEEDBACK_KIND)
        self.assertEqual(outcomes["tool_failure"]["tool_status"], "tool_failure")
        self.assertEqual(outcomes["corrected"]["ticket_id"], ticket["ticket_id"])
        with self.assertRaises(ValueError):
            agency.record_ticket_feedback(ticket, outcome="maybe")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agency-feedback.jsonl"
            self.assertEqual(agency.append_feedback_events(path, [outcomes["accepted"]]), 1)
            first_snapshot = path.read_text(encoding="utf-8")
            self.assertEqual(agency.append_feedback_events(path, [outcomes["ignored"]]), 1)
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(first_snapshot.splitlines()[0], lines[0])

if __name__ == "__main__":
    unittest.main()
