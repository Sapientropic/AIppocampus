from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.source.operation_claim_gate import evaluate_operation_claim
from aippocampus_runtime.source.operation_integrity import diagnose_clean_source


class OperationClaimGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.clean_source = Path(self.tmp.name) / "clean-source"
        self.clean_source.mkdir()
        (self.clean_source / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "source_provider": "codex",
                    "source_id": "src_gate",
                    "event_lane_policy": {
                        "status": "enabled_for_codex_rollouts",
                        "raw_payload_policy": "hash_only",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.clean_source / "events.jsonl").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_events(self, *rows: dict) -> None:
        (self.clean_source / "events.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def report(self) -> dict:
        return diagnose_clean_source(self.clean_source)

    def test_missing_partial_and_weak_families_cannot_support_strong_claims(self) -> None:
        missing_report = self.report()
        missing_gate = evaluate_operation_claim(
            missing_report,
            family="source_reopen_before_risky_action",
            event_id="evt_missing",
            intended_support_level="evidence",
        )
        self.assertEqual(missing_gate["decision"], "downgrade_to_candidate")
        self.assertEqual(missing_gate["support_level"], "candidate")
        self.assertTrue(missing_gate["source_reopen_required"])
        self.assertTrue(missing_gate["ordinary_recall_allowed"])

        self.write_events(
            {
                "event_id": "evt_partial",
                "source_ref": "codex:session:demo#L11",
                "source_line": 11,
                "critical_operation_family": "source_reopen_before_risky_action",
                "risk_family": "public_claim",
                "status": "succeeded",
            }
        )
        partial_gate = evaluate_operation_claim(
            self.report(),
            family="source_reopen_before_risky_action",
            event_id="evt_partial",
            intended_support_level="evidence",
        )
        self.assertEqual(partial_gate["decision"], "require_source_reopen")
        self.assertEqual(partial_gate["support_level"], "source_required")
        self.assertEqual(partial_gate["action_grammar"], "reopenable_route")

        self.write_events(
            {
                "event_id": "unknown",
                "source_ref": "codex:session:demo#L21",
                "source_line": 21,
                "critical_operation_family": "explicit_user_constraint",
                "constraint_kind": "do_not_touch_generated_files",
                "scope": "active_task",
                "expiry_or_supersession": "until_next_user_override",
                "status": "active",
            }
        )
        weak_gate = evaluate_operation_claim(
            self.report(),
            family="explicit_user_constraint",
            event_id="unknown",
            intended_support_level="evidence",
        )
        self.assertEqual(weak_gate["decision"], "require_source_reopen")
        self.assertIn("family_weak_covered", weak_gate["reason_codes"])

    def test_covered_fact_with_matching_join_key_allows_source_backed_claim(self) -> None:
        self.write_events(
            {
                "event_id": "evt_test_passed",
                "source_ref": "codex:session:demo#L31",
                "source_line": 31,
                "critical_operation_family": "test_check_command_result",
                "call_ref": "call_test_passed",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "exit_code": 0,
                "failure_family": "none",
                "status": "succeeded",
            }
        )

        gate = evaluate_operation_claim(
            self.report(),
            family="test_check_command_result",
            event_id="evt_test_passed",
            call_ref="call_test_passed",
            intended_support_level="evidence",
        )

        self.assertEqual(gate["decision"], "allow_source_backed_claim")
        self.assertEqual(gate["support_level"], "evidence")
        self.assertEqual(gate["trust_level"], "bounded_evidence")
        self.assertEqual(gate["action_grammar"], "bounded_evidence")
        self.assertTrue(gate["trust_contract"]["treat_as_fact"])
        self.assertFalse(gate["source_reopen_required"])

    def test_covered_family_without_matching_join_key_downgrades_to_candidate(self) -> None:
        self.write_events(
            {
                "event_id": "evt_test_passed",
                "source_ref": "codex:session:demo#L41",
                "source_line": 41,
                "critical_operation_family": "test_check_command_result",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "exit_code": 0,
                "failure_family": "none",
                "status": "succeeded",
            }
        )

        gate = evaluate_operation_claim(
            self.report(),
            family="test_check_command_result",
            event_id="evt_other",
            intended_support_level="evidence",
        )

        self.assertEqual(gate["decision"], "downgrade_to_candidate")
        self.assertEqual(gate["support_level"], "candidate")
        self.assertIn("claim_not_joined_to_fact", gate["reason_codes"])

    def test_all_provided_join_keys_must_match_the_same_fact(self) -> None:
        self.write_events(
            {
                "event_id": "evt_test_passed",
                "source_ref": "codex:session:demo#L45",
                "source_line": 45,
                "critical_operation_family": "test_check_command_result",
                "call_ref": "call_original",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "exit_code": 0,
                "failure_family": "none",
                "status": "succeeded",
            }
        )

        gate = evaluate_operation_claim(
            self.report(),
            family="test_check_command_result",
            event_id="evt_test_passed",
            call_ref="call_other",
            intended_support_level="evidence",
        )

        self.assertEqual(gate["decision"], "downgrade_to_candidate")
        self.assertEqual(gate["matched_fact_count"], 0)
        self.assertIn("claim_not_joined_to_fact", gate["reason_codes"])

    def test_privacy_issue_blocks_public_operation_claim(self) -> None:
        self.write_events(
            {
                "event_id": "evt_private_source",
                "source_ref": "C:\\Users\\Administrator\\secret\\thread.jsonl",
                "source_line": 51,
                "critical_operation_family": "test_check_command_result",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "exit_code": 0,
                "failure_family": "none",
                "status": "succeeded",
            }
        )

        gate = evaluate_operation_claim(
            self.report(),
            family="test_check_command_result",
            event_id="evt_private_source",
            intended_support_level="evidence",
            public_claim=True,
        )

        self.assertEqual(gate["decision"], "block_public_claim")
        self.assertEqual(gate["support_level"], "suppressed")
        self.assertEqual(gate["trust_level"], "ignore")
        self.assertIn("privacy_issue_affects_claim", gate["reason_codes"])
        self.assertTrue(gate["ordinary_recall_allowed"])

    def test_conflict_requires_review_before_strong_claim(self) -> None:
        self.write_events(
            {
                "event_id": "evt_conflicted",
                "source_ref": "codex:session:demo#L61",
                "source_line": 61,
                "critical_operation_family": "file_edit_write_attempt",
                "path_fingerprints": ["sha256:abc123def4567890"],
                "generated_file": False,
                "status": "succeeded",
            },
            {
                "event_id": "evt_conflicted",
                "source_ref": "codex:session:demo#L62",
                "source_line": 62,
                "critical_operation_family": "file_edit_write_attempt",
                "path_fingerprints": ["sha256:abc123def4567890"],
                "generated_file": False,
                "status": "failed",
            },
        )

        gate = evaluate_operation_claim(
            self.report(),
            family="file_edit_write_attempt",
            event_id="evt_conflicted",
            intended_support_level="evidence",
        )

        self.assertEqual(gate["decision"], "conflict_requires_review")
        self.assertEqual(gate["support_level"], "suppressed")
        self.assertEqual(gate["action_grammar"], "ignore_or_blocked")
        self.assertIn("conflict_affects_claim", gate["reason_codes"])

    def test_host_ticket_renderer_uses_gate_before_strong_operation_wording(self) -> None:
        def host_ticket_wording(report: dict) -> str:
            gate = evaluate_operation_claim(
                report,
                family="test_check_command_result",
                event_id="evt_unjoined",
                intended_support_level="evidence",
            )
            if gate["decision"] == "allow_source_backed_claim":
                return "source_backed_operation_fact"
            return f"operation_{gate['support_level']}"

        self.assertEqual(host_ticket_wording(self.report()), "operation_candidate")

if __name__ == "__main__":
    unittest.main()
