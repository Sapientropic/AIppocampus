from __future__ import annotations

import json
import unittest

from aippocampus_runtime.source.agent_trace_admission import (
    ADMISSION_LEVELS,
    TRAINING_ROLES,
    classify_trace_row,
    project_trace_admission,
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


if __name__ == "__main__":
    unittest.main()
