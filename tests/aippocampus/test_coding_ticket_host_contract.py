from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.coding import host_contract  # noqa: E402


def source_ref(line: int = 10) -> dict[str, object]:
    return {
        "thread_key": "session:coding-host-contract",
        "message_id": f"msg-{line}",
        "source_line": line,
        "timestamp": "2026-05-31T00:00:00Z",
    }


def coding_ticket(
    case_id: str,
    *,
    proposed_use: str,
    intervention_level: str,
    thickness: str = "usable",
    annoyance_risk: str = "low",
) -> dict[str, object]:
    refs = [source_ref(20)]
    return {
        "schema_version": 1,
        "kind": "aippocampus_coding_continuity_ticket",
        "ticket_id": f"coding-ticket-{case_id}",
        "trigger": "compaction_loss",
        "intervention_level": intervention_level,
        "relevant_decisions": [f"decision:{case_id}"],
        "do_not_repeat": ["legacy import route"],
        "proposed_use": proposed_use,
        "evidence_refs": refs,
        "basis_refs": refs,
        "source_thickness": thickness,
        "derived_assessment": {
            "still_rejected": "yes" if proposed_use == "warn" else "unknown",
            "freshness": "fresh",
            "basis_refs": refs,
            "truth_boundary": "derived_weather_not_source_fact",
        },
        "expires_at": "task_or_topic_epoch_end",
        "summary": f"{case_id} continuity ticket",
        "diagnostics": {"decision": proposed_use},
        "annoyance_risk": annoyance_risk,
        "preconditions": ["host confirms the source is not already visible"],
        "outcome_feedback_expected": ["accepted", "ignored", "dismissed", "corrected"],
    }


class CodingTicketHostContractTests(unittest.TestCase):
    def test_host_decisions_cover_the_visibility_ladder(self) -> None:
        decisions = {
            "silent": host_contract.host_decision_for_ticket(
                coding_ticket("silent", proposed_use="prepare_context", intervention_level="silent")
            ),
            "backstage": host_contract.host_decision_for_ticket(
                coding_ticket("backstage", proposed_use="prepare_context", intervention_level="backstage_only")
            ),
            "nudge": host_contract.host_decision_for_ticket(
                coding_ticket("nudge", proposed_use="remind", intervention_level="light_nudge")
            ),
            "warning": host_contract.host_decision_for_ticket(
                coding_ticket("warning", proposed_use="warn", intervention_level="warning")
            ),
            "ask": host_contract.host_decision_for_ticket(
                coding_ticket("ask", proposed_use="ask", intervention_level="state_check")
            ),
            "refresh": host_contract.host_decision_for_ticket(
                coding_ticket(
                    "refresh",
                    proposed_use="refresh_sources",
                    intervention_level="state_check",
                    thickness="thin",
                )
            ),
            "visible": host_contract.host_decision_for_ticket(
                coding_ticket("visible", proposed_use="remind", intervention_level="light_nudge"),
                source_visible=True,
            ),
        }

        self.assertEqual(decisions["silent"]["visibility"], "silent_tuning")
        self.assertEqual(decisions["backstage"]["visibility"], "backstage_prep")
        self.assertEqual(decisions["nudge"]["visibility"], "light_nudge")
        self.assertEqual(decisions["warning"]["visibility"], "warning")
        self.assertEqual(decisions["ask"]["visibility"], "light_nudge")
        self.assertEqual(decisions["refresh"]["visibility"], "backstage_prep")
        self.assertEqual(decisions["visible"]["visibility"], "stay_silent")
        self.assertEqual(decisions["ask"]["host_action"], "ask_user")
        self.assertEqual(decisions["refresh"]["host_action"], "refresh_sources")
        self.assertFalse(decisions["refresh"]["user_visible"])
        self.assertTrue(decisions["warning"]["requires_user_confirmation"])
        self.assertTrue(decisions["warning"]["host_boundary"]["host_decides_permission"])
        self.assertIn("source_already_visible", decisions["visible"]["suppression_reasons"])

    def test_contract_names_ai_emitted_fields_and_host_owned_inputs(self) -> None:
        ticket = coding_ticket("contract", proposed_use="warn", intervention_level="warning")
        contract = host_contract.describe_host_contract(ticket)

        self.assertEqual(contract["kind"], "aippocampus_coding_ticket_host_contract")
        self.assertEqual(contract["validation"]["missing_required_ai_fields"], [])
        self.assertIn("source_thickness", contract["ai_emits"]["required_fields"])
        self.assertIn("derived_assessment", contract["ai_emits"]["required_fields"])
        self.assertIn("source_visible", contract["host_supplies"]["runtime_inputs"])
        self.assertIn("visibility", contract["host_decides"]["fields"])
        self.assertEqual(contract["normalized_ticket"]["feedback_expectations"], ticket["outcome_feedback_expected"])
        self.assertEqual(
            contract["foreground_consumption"]["default_lane"],
            "host_mediated_foreground_or_backstage",
        )
        self.assertEqual(contract["foreground_consumption"]["card_kind"], "coding_continuity_lane_card")

    def test_compact_lane_card_answers_how_foreground_agent_consumes_ticket(self) -> None:
        ticket = coding_ticket("foreground", proposed_use="warn", intervention_level="warning")
        decision = host_contract.host_decision_for_ticket(ticket)

        card = host_contract.coding_continuity_lane_card(ticket, decision)

        self.assertEqual(card["kind"], "coding_continuity_lane_card")
        self.assertEqual(card["lane"], "foreground")
        self.assertEqual(card["foreground_visibility"], "warning")
        self.assertEqual(card["next_action"], "warn_route")
        self.assertEqual(card["source_boundary"], "source_backed_proposal_not_permission_or_execution")
        self.assertTrue(card["source_reopen_required_before_claim"])
        self.assertIn("do_not_repeat", card)
        encoded = json.dumps(card, ensure_ascii=False)
        self.assertNotIn("derived_assessment", encoded)
        self.assertNotIn("C:/", encoded)

    def test_backstage_lane_card_routes_quiet_ticket_without_dumping_diagnostics(self) -> None:
        ticket = coding_ticket(
            "backstage-lane",
            proposed_use="prepare_context",
            intervention_level="backstage_only",
        )
        decision = host_contract.host_decision_for_ticket(ticket)

        card = host_contract.coding_continuity_lane_card(ticket, decision)

        self.assertEqual(card["lane"], "backstage")
        self.assertEqual(card["next_action"], "prepare_context")
        self.assertFalse(card["user_visible"])
        self.assertEqual(card["agent_consumption"], "route_usable_guidance_through_action_hints_or_recall")

    def test_feedback_tunes_future_activation_without_rewriting_source_facts(self) -> None:
        ticket = coding_ticket("feedback", proposed_use="warn", intervention_level="warning")
        before = copy.deepcopy(ticket["derived_assessment"])
        tuning = host_contract.tune_activation_from_feedback(
            [ticket],
            [
                {
                    "kind": "aippocampus_agency_ticket_feedback",
                    "ticket_id": "coding-ticket-feedback",
                    "outcome": "dismissed",
                    "note": "too chatty for this phase",
                },
                {
                    "kind": "aippocampus_agency_ticket_feedback",
                    "ticket_id": "coding-ticket-feedback",
                    "outcome": "tool_failure",
                },
            ],
        )

        self.assertEqual(tuning["kind"], "aippocampus_coding_ticket_activation_tuning")
        self.assertFalse(tuning["source_fact_mutation_allowed"])
        self.assertEqual(ticket["derived_assessment"], before)
        self.assertEqual(tuning["adjustments"][0]["ticket_id"], "coding-ticket-feedback")
        self.assertEqual(tuning["adjustments"][0]["activation_tuning"], "quieter")
        self.assertIn("source_fact_rewrite", tuning["forbidden_mutations"])

    def test_recent_dismissal_suppresses_same_ticket_without_rewriting_source_facts(self) -> None:
        ticket = coding_ticket("dismissed", proposed_use="warn", intervention_level="warning")
        before = copy.deepcopy(ticket["derived_assessment"])

        decision = host_contract.host_decision_for_ticket(
            ticket,
            recent_feedback=[
                {
                    "kind": "aippocampus_agency_ticket_feedback",
                    "ticket_id": "coding-ticket-dismissed",
                    "outcome": "dismissed",
                    "topic_epoch": "task_or_topic_epoch_end",
                }
            ],
        )

        self.assertEqual(decision["visibility"], "stay_silent")
        self.assertIn("recent_feedback_suppressed", decision["suppression_reasons"])
        self.assertEqual(ticket["derived_assessment"], before)

    def test_recent_delivery_suppresses_duplicate_ticket_surface(self) -> None:
        ticket = coding_ticket("duplicate", proposed_use="ask", intervention_level="state_check")

        decision = host_contract.host_decision_for_ticket(
            ticket,
            recent_feedback=[
                {
                    "kind": "aippocampus_coding_ticket_delivery_event",
                    "ticket_id": "coding-ticket-duplicate",
                    "delivery_state": "delivered",
                    "topic_epoch": "task_or_topic_epoch_end",
                }
            ],
        )

        self.assertEqual(decision["visibility"], "stay_silent")
        self.assertIn("duplicate_ticket_suppressed", decision["suppression_reasons"])

    def test_simulation_passes_host_feedback_to_each_ticket_decision(self) -> None:
        ticket = coding_ticket("sim-feedback", proposed_use="ask", intervention_level="state_check")

        result = host_contract.simulate_host_consumption(
            [ticket],
            recent_feedback=[
                {
                    "ticket_id": "coding-ticket-sim-feedback",
                    "outcome": "ignored",
                    "topic_epoch": "task_or_topic_epoch_end",
                }
            ],
        )

        self.assertEqual(result["decisions"][0]["visibility"], "stay_silent")
        self.assertIn("recent_feedback_suppressed", result["decisions"][0]["suppression_reasons"])

    def test_no_host_degrades_to_silence(self) -> None:
        ticket = coding_ticket("no-host", proposed_use="warn", intervention_level="warning")
        decision = host_contract.host_decision_for_ticket(ticket, host_present=False)

        self.assertEqual(decision["visibility"], "stay_silent")
        self.assertEqual(decision["host_action"], "no_action")
        self.assertEqual(decision["safe_degradation"], "no_host")
        self.assertFalse(decision["user_visible"])


if __name__ == "__main__":
    unittest.main()
