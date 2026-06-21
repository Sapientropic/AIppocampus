from __future__ import annotations

import unittest

from aippocampus_runtime.knowledge import capability_conflicts


class KnowledgeCapabilityConflictResolverTests(unittest.TestCase):
    def test_safety_gate_suppresses_warm_communication_style(self) -> None:
        report = capability_conflicts.resolve_capability_conflicts(
            [
                {
                    "action_id": "warm_support_reply",
                    "capability_id": "communication.supportive_style.low.v1",
                    "precedence_class": "communication_style",
                    "output_state": "answer_directly",
                    "reason_codes": ["warm_style_requested"],
                },
                {
                    "action_id": "crisis_boundary_redirect",
                    "capability_id": "safety.crisis_boundary.high.v1",
                    "precedence_class": "safety_high_risk",
                    "output_state": "refuse_or_redirect",
                    "reason_codes": ["urgent_harm_boundary"],
                },
            ]
        )

        self.assertEqual(report["selected"]["action_id"], "crisis_boundary_redirect")
        self.assertEqual(report["output_state"], "refuse_or_redirect")
        self.assertIn("safety_high_risk_overrides_communication_style", report["reason_codes"])
        self.assertIn("warm_support_reply", {item["action_id"] for item in report["suppressed"]})

    def test_high_risk_gate_turns_direct_answer_into_question_state(self) -> None:
        report = capability_conflicts.resolve_capability_conflicts(
            [
                {
                    "action_id": "direct_contract_answer",
                    "capability_id": "task.contract_answer.low.v1",
                    "precedence_class": "task_domain",
                    "output_state": "answer_directly",
                },
                {
                    "action_id": "legal_context_gate",
                    "capability_id": "knowledge.contract_review.risk_flag.high.v1",
                    "precedence_class": "safety_high_risk",
                    "output_state": "missing_context_question",
                    "questions": [
                        {
                            "code": "missing_jurisdiction",
                            "field": "jurisdiction",
                        }
                    ],
                },
            ]
        )

        self.assertEqual(report["output_state"], "missing_context_question")
        self.assertEqual(report["questions"][0]["code"], "missing_jurisdiction")
        self.assertIn("safety_high_risk_overrides_task_domain", report["reason_codes"])

    def test_privacy_partition_blocks_external_payload_or_side_effect(self) -> None:
        report = capability_conflicts.resolve_capability_conflicts(
            [
                {
                    "action_id": "send_raw_relationship_memory_to_tool",
                    "capability_id": "tool.external_payload.medium.v1",
                    "precedence_class": "task_domain",
                    "output_state": "call_tool",
                    "tool_id": "external.crm.write",
                },
                {
                    "action_id": "block_external_private_payload",
                    "capability_id": "privacy.external_payload.high.v1",
                    "precedence_class": "privacy_boundary",
                    "output_state": "cannot_proceed",
                    "reason_codes": ["external_payload_blocked"],
                },
            ]
        )

        self.assertEqual(report["selected"]["action_id"], "block_external_private_payload")
        self.assertEqual(report["suppressed"][0]["tool_id"], "external.crm.write")
        self.assertIn("privacy_boundary_overrides_task_domain", report["reason_codes"])

    def test_same_user_cross_domain_memory_can_project_local_route_handle(self) -> None:
        report = capability_conflicts.resolve_capability_conflicts(
            [
                {
                    "action_id": "use_relationship_memory_as_local_route",
                    "capability_id": "memory.cross_domain_context.medium.v1",
                    "precedence_class": "task_domain",
                    "output_state": "local_route_handle",
                    "reason_codes": ["local_route_handle_only"],
                }
            ]
        )

        self.assertEqual(report["selected"]["action_id"], "use_relationship_memory_as_local_route")
        self.assertEqual(report["output_state"], "local_route_handle")
        self.assertIn("local_route_handle_only", report["reason_codes"])

    def test_source_truth_gate_suppresses_stale_task_operation(self) -> None:
        report = capability_conflicts.resolve_capability_conflicts(
            [
                {
                    "action_id": "run_storage_cleanup",
                    "capability_id": "operation.storage_cleanup.medium.v1",
                    "precedence_class": "operation_side_effect",
                    "output_state": "perform_operation",
                },
                {
                    "action_id": "block_stale_source_operation",
                    "capability_id": "source_truth.stale_conflict.high.v1",
                    "precedence_class": "source_truth",
                    "output_state": "human_review_required",
                    "reason_codes": ["source_conflict_uncleared"],
                },
            ]
        )

        self.assertEqual(report["output_state"], "human_review_required")
        self.assertIn("source_truth_overrides_operation_side_effect", report["reason_codes"])
        self.assertIn("source_conflict_uncleared", report["reason_codes"])

    def test_required_uncertainty_beats_brevity_or_style_preference(self) -> None:
        report = capability_conflicts.resolve_capability_conflicts(
            [
                {
                    "action_id": "keep_answer_short",
                    "capability_id": "style.brevity.low.v1",
                    "precedence_class": "communication_style",
                    "output_state": "answer_directly",
                },
                {
                    "action_id": "require_uncertainty_and_source_reopen",
                    "capability_id": "source_truth.uncertainty_gate.high.v1",
                    "precedence_class": "source_truth",
                    "output_state": "source_reopen_required",
                    "cannot_claim": ["style_preference_removes_uncertainty"],
                },
            ]
        )

        self.assertEqual(report["selected"]["action_id"], "require_uncertainty_and_source_reopen")
        self.assertEqual(report["output_state"], "source_reopen_required")
        self.assertIn("source_truth_overrides_communication_style", report["reason_codes"])
        self.assertIn("style_preference_removes_uncertainty", report["cannot_claim"])
        self.assertIn("capability_text_is_not_fact_source", report["cannot_claim"])

if __name__ == "__main__":
    unittest.main()
