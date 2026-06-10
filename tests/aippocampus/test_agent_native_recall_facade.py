from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import agent_facade_contract as facade  # noqa: E402


class AgentNativeRecallFacadeTests(unittest.TestCase):
    def test_recall_packets_are_tiny_and_do_not_emit_source_refs(self) -> None:
        report = facade.build_facade_fixture_report()
        foreground = [record["memory_packet"] for record in report["records"]]
        encoded = json.dumps(foreground, ensure_ascii=False, sort_keys=True)
        by_id = {packet["route_id"]: packet for packet in foreground}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["metrics"]["foreground_packet_count"], 5)
        self.assertLessEqual(
            report["metrics"]["foreground_packet_max_bytes"],
            facade.FOREGROUND_PACKET_BYTE_BUDGET,
        )
        self.assertEqual(report["metrics"]["foreground_forbidden_key_count"], 0)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("source_id", encoded)
        self.assertNotIn("segment_id", encoded)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_SUMMARY_SENTINEL", encoded)

        summary = by_id["route_project_workflow_summary"]
        self.assertEqual(summary["output_mode"], "bounded_summary_as_route")
        self.assertEqual(summary["claim_permission"], "no_claim_before_reopen")
        self.assertEqual(summary["next_action"], "use_hint")
        self.assertTrue(summary["deepen_route_id"].startswith("deepen:"))

    def test_deepen_exposes_routes_or_refuses_without_overclaiming(self) -> None:
        report = facade.build_facade_fixture_report()
        by_id = {record["route_id"]: record for record in report["records"]}

        summary_deepen = by_id["route_project_workflow_summary"]["deepen"]
        reopen_deepen = by_id["route_old_decision_reopen"]["deepen"]
        blocked_deepen = by_id["route_private_blocked"]["deepen"]
        cannot_verify = by_id["route_direction_only"]["deepen"]
        source_open = by_id["route_source_open_bounded"]["deepen"]

        self.assertEqual(summary_deepen["status"], "source_route")
        self.assertEqual(summary_deepen["claim_permission"], "no_claim_before_reopen")
        self.assertGreaterEqual(summary_deepen["source_handle_count"], 1)
        self.assertEqual(summary_deepen["claim_boundary"], "reopen_source_before_claim")
        self.assertEqual(reopen_deepen["status"], "source_route")

        self.assertEqual(blocked_deepen["status"], "blocked")
        self.assertEqual(blocked_deepen["source_handles"], [])
        self.assertIn("privacy_domain", blocked_deepen["blocked_reason_codes"])

        self.assertEqual(cannot_verify["status"], "cannot_verify")
        self.assertEqual(cannot_verify["source_handles"], [])
        self.assertIn("source_backed_claim", cannot_verify["cannot_claim"])

        self.assertEqual(source_open["status"], "source_backed_evidence")
        self.assertEqual(source_open["claim_permission"], "bounded_claim_allowed")
        self.assertEqual(source_open["claim_boundary"], "bounded_to_already_open_scope")
        self.assertEqual(report["red_lines"]["source_backed_claim_without_reopen"], 0)

    def test_explain_maps_facade_modes_to_safe_next_actions(self) -> None:
        report = facade.build_facade_fixture_report()
        by_id = {record["route_id"]: record for record in report["records"]}

        summary = by_id["route_project_workflow_summary"]["explain"]
        reopen = by_id["route_old_decision_reopen"]["explain"]
        blocked = by_id["route_private_blocked"]["explain"]
        direction = by_id["route_direction_only"]["explain"]

        self.assertEqual(summary["decision"], "why_recall")
        self.assertEqual(summary["next_safe_action"], "use_hint")
        self.assertIn("summary_is_not_evidence", summary["reason_codes"])

        self.assertEqual(reopen["next_safe_action"], "reopen_source")
        self.assertIn("reopenable_route_available", reopen["reason_codes"])

        self.assertEqual(blocked["decision"], "why_not_recall")
        self.assertEqual(blocked["next_safe_action"], "stay_silent")
        self.assertIn("mask:privacy_domain", blocked["reason_codes"])

        self.assertEqual(direction["output_mode"], "direction_only")
        self.assertIn("direction_only_navigation", direction["reason_codes"])
        self.assertIn("public_sdk_stability", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
