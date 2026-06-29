from __future__ import annotations

import json
import unittest

from aippocampus_runtime.recall.feedback.suppression_lifecycle import feedback_trace_family
from aippocampus_runtime.recall.rollout_search import rollout_payload_class
from aippocampus_runtime.source import agent_trace_families
from aippocampus_runtime.source.agent_trace_admission import (
    ACCEPTED_RECEIPT_FIELDS,
    ADMISSION_LEVELS,
    RECEIPT_FIELD_CONTRACT,
    TRAINING_ROLES,
    TRAINING_SIGNAL_KIND,
    adapt_trace_rows_with_receipts,
    behavior_training_signal_from_trace,
    classify_trace_row,
    draft_navigation_candidate_from_signal,
    project_behavior_training_ledger,
    project_candidate_funnel,
    project_trace_admission,
    verify_navigation_candidate,
)


class AgentTraceAdmissionTests(unittest.TestCase):
    def _mixed_rows(self) -> list[dict]:
        return [
            {
                "trace_id": "closeout-1",
                "trace_family": "final_answer_closeout",
                "source_refs": [{"message_id": "msg-final", "line": 10}],
                "receipt_refs": [{"event_id": "evt-test"}],
                "summary": "Verified focused checks and left next step.",
            },
            {
                "trace_id": "check-1",
                "trace_family": "successful_test_check_event",
                "status": "passed",
                "exit_code": 0,
                "source_refs": [{"message_id": "msg-check", "line": 12}],
                "command_family": "pytest",
            },
            {
                "trace_id": "raw-1",
                "trace_family": "raw_stdout",
                "stdout": "full tool output C:\\private\\trace api_key=sk-private",
                "full_command_args": ["pytest", "tests/aippocampus/test_secret.py"],
            },
            {
                "trace_id": "commentary-1",
                "trace_family": "routine_commentary",
                "text": "I am thinking through the next tool call.",
            },
            {
                "trace_id": "repo-1",
                "trace_family": "repo_breadcrumb",
                "safe_repo_relative": True,
                "repo_path": "skills/aippocampus/scripts/aippocampus_runtime/source/behavior_events.py",
            },
        ]

    def test_contract_vocabularies_are_small_and_stable(self) -> None:
        self.assertEqual(
            ADMISSION_LEVELS,
            (
                "ignore",
                "operator_only",
                "navigation_candidate",
                "reopenable_route",
                "bounded_evidence_after_open",
            ),
        )
        self.assertEqual(
            TRAINING_ROLES,
            (
                "none",
                "positive_demo",
                "hard_negative",
                "process_supervision",
                "replay_sample",
                "hindsight_relabel",
            ),
        )

    def test_mixed_trace_packet_admits_only_bounded_navigation_rows(self) -> None:
        rows = self._mixed_rows()
        classified = {row["trace_id"]: classify_trace_row(row) for row in rows}

        self.assertEqual(classified["closeout-1"]["admission_level"], "reopenable_route")
        self.assertEqual(
            classified["closeout-1"]["authority_join"],
            "reported_and_receipted_navigation",
        )
        self.assertEqual(classified["check-1"]["admission_level"], "reopenable_route")
        self.assertEqual(
            classified["check-1"]["authority_join"],
            "behavior_receipt_navigation",
        )
        self.assertEqual(classified["raw-1"]["admission_level"], "operator_only")
        self.assertEqual(classified["commentary-1"]["admission_level"], "ignore")
        self.assertEqual(classified["repo-1"]["admission_level"], "navigation_candidate")
        self.assertEqual(
            classified["repo-1"]["candidate_lifecycle_state"],
            "draft_candidate_staging",
        )
        self.assertEqual(
            classified["check-1"]["graph_projection"],
            "typed_graph_contribution_after_owner_gate",
        )

    def test_family_aliases_admit_final_answer_closeout_without_silent_downgrade(self) -> None:
        payload_family = rollout_payload_class({"role": "assistant", "is_final": True})
        classified = classify_trace_row(
            {
                "trace_id": "final-1",
                "family": payload_family,
                "source_refs": [{"message_id": "msg-1", "line": 1}],
                "receipt_refs": [{"event_id": "evt-1"}],
            }
        )

        self.assertEqual(payload_family, "assistant_final")
        self.assertEqual(classified["producer_trace_family"], "assistant_final")
        self.assertEqual(classified["trace_family"], "final_answer_closeout")
        self.assertTrue(classified["family_alias_applied"])
        self.assertEqual(classified["admission_level"], "reopenable_route")
        self.assertEqual(classified["reason"], "closeout_joined_to_receipt")

    def test_trace_family_producer_values_are_known_or_declared_aliases(self) -> None:
        producer_values = agent_trace_families.declared_trace_family_producer_values()
        known_or_alias = agent_trace_families.KNOWN_TRACE_FAMILIES | set(
            agent_trace_families.FAMILY_ALIASES
        )

        self.assertIn(rollout_payload_class({"role": "assistant", "is_final": True}), producer_values)
        self.assertIn(
            agent_trace_families.TOOL_CALL_SUCCEEDED_PRODUCER_FAMILY,
            producer_values,
        )
        self.assertNotIn("fixture_only_family", producer_values)
        self.assertEqual(
            agent_trace_families.raw_family({"trace_family_under_test": "fixture_only_family"}),
            "",
        )
        self.assertLessEqual(producer_values, known_or_alias)
        self.assertLessEqual(
            set(agent_trace_families.FAMILY_ALIASES.values()),
            agent_trace_families.KNOWN_TRACE_FAMILIES,
        )

    def test_project_admission_joins_closeout_to_matching_behavior_receipt(self) -> None:
        closeout = {
            "trace_id": "final-joined",
            "family": "assistant_final",
            "source_refs": [{"message_id": "msg-joined", "line": 7}],
        }
        receipt = {
            "trace_id": "source-open-joined",
            "trace_family": "successful_recall_deepen_source_open",
            "source_refs": [{"message_id": "msg-joined", "line": 7}],
        }
        source_only = classify_trace_row(closeout)
        adapted = adapt_trace_rows_with_receipts([closeout, receipt])
        adapted_closeout = next(row for row in adapted if row["trace_id"] == "final-joined")
        joined_closeout = classify_trace_row(adapted_closeout)
        detail = project_trace_admission([closeout, receipt], detail="operator")
        ledger = project_behavior_training_ledger([closeout, receipt], detail="operator")

        self.assertEqual(source_only["admission_level"], "navigation_candidate")
        self.assertEqual(source_only["authority_join"], "agent_reported_navigation_only")
        self.assertEqual(adapted_closeout["receipt_state"], "matched")
        self.assertEqual(joined_closeout["admission_level"], "reopenable_route")
        self.assertEqual(
            joined_closeout["authority_join"],
            "reported_and_receipted_navigation",
        )
        self.assertEqual(detail["admission_counts"]["reopenable_route"], 1)
        self.assertEqual(detail["admission_counts"]["bounded_evidence_after_open"], 1)
        self.assertEqual(ledger["training_role_counts"]["process_supervision"], 1)
        self.assertEqual(ledger["training_role_counts"]["positive_demo"], 1)

    def test_receipt_field_contract_is_adapter_owned_not_test_fixture_only(self) -> None:
        self.assertEqual(set(ACCEPTED_RECEIPT_FIELDS), set(RECEIPT_FIELD_CONTRACT))
        self.assertEqual(
            {row["status"] for row in RECEIPT_FIELD_CONTRACT.values()},
            {"adapter_produced"},
        )
        self.assertEqual(
            {row["adapter"] for row in RECEIPT_FIELD_CONTRACT.values()},
            {"adapt_trace_rows_with_receipts"},
        )

        test_only_field = classify_trace_row(
            {
                "trace_id": "final-test-only",
                "family": "assistant_final",
                "source_refs": [{"message_id": "msg-test-only", "line": 2}],
                "test_receipt_refs": [{"event_id": "fixture-only"}],
            }
        )

        self.assertEqual(test_only_field["admission_level"], "navigation_candidate")
        self.assertEqual(test_only_field["reason"], "closeout_self_report_only")

    def test_operator_detail_reports_unknown_family_without_compact_inventory(self) -> None:
        rows = [{"trace_id": "unknown-1", "family": "brand_new_family"}]
        detail = project_trace_admission(rows, detail="operator")
        compact = project_trace_admission(rows, detail="compact")

        self.assertEqual(detail["unknown_family_count"], 1)
        self.assertEqual(detail["unknown_trace_families"][0]["family"], "brand_new_family")
        self.assertEqual(compact["status"], "diagnostic_only")
        self.assertNotIn("unknown_trace_families", compact)

    def test_unknown_family_with_source_and_receipt_refs_reports_registration_drift(self) -> None:
        row = {
            "trace_id": "unknown-with-refs",
            "family": "brand_new_family",
            "source_refs": [{"message_id": "msg-new", "line": 3}],
            "receipt_refs": [{"event_id": "evt-new"}],
        }

        classified = classify_trace_row(row)
        detail = project_trace_admission([row], detail="operator")
        compact = project_trace_admission([row], detail="compact")

        self.assertEqual(classified["admission_level"], "operator_only")
        self.assertEqual(
            classified["reason"],
            "unknown_trace_family_requires_registration",
        )
        self.assertEqual(classified["source_state"], "unknown_family_source_refs_and_receipts")
        self.assertNotEqual(classified["source_state"], "missing_source_or_receipt")
        self.assertEqual(detail["unknown_family_count"], 1)
        self.assertNotIn("unknown_trace_families", compact)

    def test_behavior_source_ref_adapter_preserves_feedback_and_clean_receipt_refs(self) -> None:
        feedback_row = {
            "trace_id": "feedback-1",
            "trace_family": feedback_trace_family("source_reopen_success"),
            "outcome": "source_reopen_success",
            "source_refs": [{"thread_key": "thread-a", "message_id": "msg-a", "line": 4}],
        }
        clean_receipt = {
            "trace_id": "clean-1",
            "event_kind": "tool_call_observed",
            "hard_event_kind": "tool_call_succeeded",
            "status": "succeeded",
            "source_ref": "provider:session:line-8",
            "source_line": 8,
        }
        malformed = {
            "trace_id": "malformed-1",
            "event_kind": "tool_call_succeeded",
            "status": "succeeded",
            "source_ref": "provider:session:line-only",
        }

        feedback_classified = classify_trace_row(feedback_row)
        clean_classified = classify_trace_row(clean_receipt)
        malformed_classified = classify_trace_row(malformed)
        feedback_signal = behavior_training_signal_from_trace(feedback_row)
        malformed_signal = behavior_training_signal_from_trace(
            {**malformed, "outcome": "source_reopen_success"}
        )

        self.assertEqual(feedback_classified["admission_level"], "bounded_evidence_after_open")
        self.assertEqual(feedback_classified["source_ref_count"], 1)
        self.assertEqual(feedback_signal["training_role"], "positive_demo")
        self.assertEqual(clean_classified["trace_family"], "successful_tool_check_receipt")
        self.assertEqual(clean_classified["admission_level"], "reopenable_route")
        self.assertEqual(clean_classified["source_ref_count"], 1)
        self.assertEqual(malformed_classified["source_ref_count"], 0)
        self.assertEqual(malformed_classified["admission_level"], "operator_only")
        self.assertEqual(malformed_signal["training_role"], "none")

    def test_compact_projection_is_action_boundary_not_trace_inventory(self) -> None:
        compact = project_trace_admission(self._mixed_rows(), detail="compact")

        self.assertEqual(compact["status"], "route_available")
        self.assertEqual(compact["foreground_action"]["id"], "open_trace_route_source")
        self.assertEqual(
            compact["primary_route"]["admission_level"],
            "reopenable_route",
        )
        encoded = json.dumps(compact, ensure_ascii=False)
        for forbidden in (
            "receipt_refs",
            "source_refs",
            "stdout",
            "full_command_args",
            "routine_commentary",
            "C:\\private",
            "sk-private",
            "api_key",
            "policy_gate_matrix",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_detail_projection_is_count_based(self) -> None:
        detail = project_trace_admission(self._mixed_rows(), detail="operator")

        self.assertEqual(detail["operator_only_count"], 1)
        self.assertEqual(detail["ignored_count"], 1)
        self.assertEqual(detail["admission_counts"]["reopenable_route"], 2)
        self.assertEqual(detail["admission_counts"]["navigation_candidate"], 1)
        self.assertEqual(detail["training_role_counts"]["process_supervision"], 2)
        self.assertEqual(
            detail["graph_projection_counts"]["operator_report_only"],
            1,
        )
        encoded = json.dumps(detail, ensure_ascii=False)
        self.assertNotIn("stdout", encoded)
        self.assertNotIn("C:\\private", encoded)

    def test_behavior_training_ledger_covers_five_signal_roles_without_raw_leak(self) -> None:
        rows = [
            {
                "trace_id": "positive",
                "trace_family": "successful_recall_deepen_source_open",
                "outcome": "source_reopen_success",
                "cue": "private fuzzy cue",
                "source_refs": [{"message_id": "msg-positive", "line": 1}],
                "opened_anchor_hits": 3,
                "low_confidence_before": True,
                "multilingual": True,
                "cue_frequency": 1,
            },
            {
                "trace_id": "negative",
                "trace_family": "repo_breadcrumb",
                "outcome": "wrong_route_drag",
                "safe_repo_relative": True,
                "route_id": "route:bad",
                "preferred_route_id": "route:good",
                "rejected_route_ids": ["route:bad"],
            },
            {
                "trace_id": "process",
                "trace_family": "joined_route_note",
                "source_refs": [{"message_id": "msg-route", "line": 2}],
                "joined_evidence_refs": [{"message_id": "msg-final", "line": 3}],
            },
            {
                "trace_id": "replay",
                "trace_family": "repo_breadcrumb",
                "outcome": "missed_opportunity",
                "safe_repo_relative": True,
            },
            {
                "trace_id": "relabel",
                "trace_family": "repo_breadcrumb",
                "outcome": "hindsight_relabel",
                "safe_repo_relative": True,
            },
        ]

        signals = [behavior_training_signal_from_trace(row) for row in rows]
        by_trace = {row["trace_id"]: row for row in signals}
        self.assertEqual({row["kind"] for row in signals}, {TRAINING_SIGNAL_KIND})
        self.assertEqual(by_trace["positive"]["training_role"], "positive_demo")
        self.assertEqual(by_trace["negative"]["training_role"], "hard_negative")
        self.assertEqual(by_trace["process"]["training_role"], "process_supervision")
        self.assertEqual(by_trace["replay"]["training_role"], "replay_sample")
        self.assertEqual(by_trace["relabel"]["training_role"], "hindsight_relabel")
        self.assertEqual(
            by_trace["positive"]["learning_priority"]["bucket"],
            "high_information",
        )
        self.assertTrue(by_trace["negative"]["contrastive_pair"])

        compact = project_behavior_training_ledger(signals, detail="compact")
        detail = project_behavior_training_ledger(signals, detail="operator")
        encoded = json.dumps({"compact": compact, "detail": detail}, ensure_ascii=False)

        self.assertEqual(compact["decision"], "use_training_signals_as_navigation_calibration_only")
        self.assertEqual(detail["training_role_counts"]["positive_demo"], 1)
        self.assertEqual(detail["training_role_counts"]["hard_negative"], 1)
        self.assertEqual(detail["training_role_counts"]["process_supervision"], 1)
        self.assertEqual(detail["training_role_counts"]["replay_sample"], 1)
        self.assertEqual(detail["training_role_counts"]["hindsight_relabel"], 1)
        self.assertEqual(detail["contrastive_pair_count"], 1)
        self.assertNotIn("private fuzzy cue", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_candidate_funnel_verifier_outcomes_drive_foreground_exposure(self) -> None:
        positive_signal = behavior_training_signal_from_trace(
            {
                "trace_id": "positive",
                "trace_family": "successful_recall_deepen_source_open",
                "outcome": "source_reopen_success",
                "cue_hash": "cue-positive",
                "route_id": "route:positive",
                "source_refs": [{"message_id": "msg-positive"}],
                "opened_anchor_hits": 2,
            }
        )
        negative_signal = behavior_training_signal_from_trace(
            {
                "trace_id": "negative",
                "trace_family": "repo_breadcrumb",
                "outcome": "wrong_route_drag",
                "safe_repo_relative": True,
                "cue_hash": "cue-positive",
                "route_id": "route:negative",
            }
        )

        good_candidate = draft_navigation_candidate_from_signal(
            positive_signal,
            producer_family="semantic_cue_alias",
        )
        bad_candidate = draft_navigation_candidate_from_signal(
            negative_signal,
            producer_family="semantic_cue_alias",
        )
        verified_good = verify_navigation_candidate(
            good_candidate,
            outcome="source_open_hit",
        )
        verified_bad = verify_navigation_candidate(
            bad_candidate,
            outcome="wrong_route",
        )

        compact = project_candidate_funnel([verified_bad, verified_good], detail="compact")
        detail = project_candidate_funnel([verified_bad, verified_good], detail="operator")
        encoded = json.dumps({"compact": compact, "detail": detail}, ensure_ascii=False)

        self.assertEqual(compact["status"], "foreground_route_available")
        self.assertEqual(
            compact["primary_candidate"]["lifecycle_state"],
            "source_open_claim_ready",
        )
        self.assertEqual(detail["foreground_exposed_count"], 1)
        self.assertEqual(detail["lifecycle_counts"]["rejected_hard_negative"], 1)
        self.assertEqual(detail["training_role_counts"]["hard_negative"], 1)
        self.assertNotIn("route:positive", encoded)
        self.assertNotIn("route:negative", encoded)


if __name__ == "__main__":
    unittest.main()
