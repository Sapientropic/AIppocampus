from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from aippocampus_runtime.ops import (
    coordination_topology,
    telepathy_coordination_packet,
)


class TelepathyCoordinationPacketTests(unittest.TestCase):
    def test_fixture_defines_soft_locks_and_handoffs_without_bureaucracy(self) -> None:
        report = telepathy_coordination_packet.build_telepathy_coordination_report()
        by_id = {item["case_id"]: item for item in report["packets"]}

        self.assertEqual(report["kind"], "aippocampus_telepathy_coordination_packet_report")
        self.assertTrue(report["contract_gate_ok"], json.dumps(report, indent=2))
        self.assertTrue(report["safety_gate_ok"], json.dumps(report, indent=2))
        self.assertEqual(report["authority_level"], "navigation_only")
        self.assertEqual(report["runtime_boundary"], "post_packet_explain_or_campus_first")
        self.assertFalse(report["every_turn_scan"])
        self.assertFalse(report["default_foreground_hook"])
        self.assertFalse(report["central_planner"])
        self.assertFalse(report["hard_locking"])
        self.assertEqual(report["metrics"]["packet_count"], 6)
        self.assertEqual(report["metrics"]["active_soft_lock_count"], 1)
        self.assertEqual(report["metrics"]["clean_handoff_count"], 1)
        self.assertEqual(report["metrics"]["candidate_only_handoff_count"], 1)
        self.assertEqual(report["metrics"]["privacy_blocked_packet_count"], 1)
        self.assertEqual(report["metrics"]["stale_or_released_lock_count"], 1)
        self.assertEqual(report["metrics"]["human_needed_count"], 1)

        self.assertEqual(by_id["active_soft_lock"]["coordination_mode"], "soft_lock")
        self.assertEqual(by_id["active_soft_lock"]["status"], "active")
        self.assertTrue(by_id["active_soft_lock"]["soft_lock_active"])
        self.assertFalse(by_id["active_soft_lock"]["hard_lock_created"])

        self.assertEqual(by_id["clean_reopenable_handoff"]["coordination_mode"], "handoff")
        self.assertEqual(by_id["clean_reopenable_handoff"]["handoff_readiness"], "route_ready")
        self.assertEqual(by_id["clean_reopenable_handoff"]["source_support"], "reopenable_route")

        self.assertEqual(by_id["candidate_only_handoff"]["source_support"], "candidate_only")
        self.assertTrue(by_id["candidate_only_handoff"]["source_reopen_required_before_claim"])
        self.assertEqual(
            by_id["candidate_only_handoff"]["claim_permission"],
            "navigation_only_not_fact",
        )

        self.assertIn("no_private_source", by_id["privacy_blocked_packet"]["boundary_flags"])
        self.assertEqual(by_id["privacy_blocked_packet"]["status"], "blocked")
        self.assertEqual(by_id["released_soft_lock"]["status"], "released")
        self.assertFalse(by_id["released_soft_lock"]["soft_lock_active"])
        self.assertEqual(by_id["human_needed_handoff"]["handoff_readiness"], "needs_human")

        for packet in report["packets"]:
            self.assertEqual(packet["kind"], "telepathy_coordination_packet")
            self.assertEqual(packet["claim_permission"], "navigation_only_not_fact")
            self.assertFalse(packet["assignment_created"])
            self.assertFalse(packet["shared_chain_of_thought"])
            self.assertEqual(packet["full_packet_surface"], "explain_debug_or_campus")
            self.assertLess(
                len(json.dumps(packet["foreground_projection"], sort_keys=True)),
                len(json.dumps(packet, sort_keys=True)),
            )

    def test_cross_agent_and_sheaf_boundaries_are_contract_fields(self) -> None:
        report = telepathy_coordination_packet.build_telepathy_coordination_report()

        self.assertTrue(report["contract"]["cross_agent_isolation_applies_before_output"])
        self.assertTrue(report["contract"]["packet_projects_to_coordination_topology_rows"])
        self.assertTrue(report["contract"]["soft_locks_are_advisory_not_transactional"])
        self.assertTrue(report["contract"]["handoff_cards_are_source_routes_not_truth"])
        self.assertTrue(report["contract"]["failed_glue_is_obstruction_not_assignment"])
        self.assertTrue(report["contract"]["no_shared_chain_of_thought"])
        self.assertTrue(report["contract"]["source_reopen_required_before_claim"])
        self.assertIn("shared_chain_of_thought", report["cannot_claim"])
        self.assertIn("central_planner_assignments", report["cannot_claim"])
        self.assertIn("distributed_lock_correctness", report["cannot_claim"])

    def test_packets_project_to_existing_coordination_topology_rows(self) -> None:
        report = telepathy_coordination_packet.build_telepathy_coordination_report()
        packets = {packet["case_id"]: packet for packet in report["packets"]}

        clean_row = telepathy_coordination_packet.topology_row_from_coordination_packet(
            packets["clean_reopenable_handoff"]
        )
        candidate_row = telepathy_coordination_packet.topology_row_from_coordination_packet(
            packets["candidate_only_handoff"]
        )
        private_row = telepathy_coordination_packet.topology_row_from_coordination_packet(
            packets["privacy_blocked_packet"]
        )

        self.assertEqual(
            coordination_topology.evaluate_coordination_case(clean_row)["diagnostic"],
            "healthy_handoff",
        )
        self.assertEqual(
            coordination_topology.evaluate_coordination_case(candidate_row)["diagnostic"],
            "handoff_knot",
        )
        self.assertEqual(
            coordination_topology.evaluate_coordination_case(private_row)["diagnostic"],
            "boundary_crossing",
        )

    def test_cli_sanitizes_private_coordination_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "telepathy-private.json"
            rows = [
                {
                    "case_id": "private_packet",
                    "scope": str(root / "private-rollout.jsonl"),
                    "coordination_mode": "handoff",
                    "status": "blocked",
                    "source_support": "candidate_only",
                    "owner": "codex-a",
                    "boundary_flags": ["no_private_source", "no_shared_cot"],
                    "handoff_readiness": "needs_human",
                    "raw_source_text": "PRIVATE_TELEPATHY_TEXT must not leave diagnostics",
                    "private_reasoning": "CHAIN_OF_THOUGHT_SENTINEL",
                    "source_handle": "source://private/raw-handle",
                }
            ]
            input_path.write_text(json.dumps(rows), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.ops.telepathy_coordination_packet",
                    "--input",
                    str(input_path),
                    "--json",
                ],
                check=False,
                text=True,
                capture_output=True,
                cwd=REPO_ROOT,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["safety_gate_ok"])
        self.assertEqual(payload["privacy_boundary"]["forbidden_marker_count"], 0)
        self.assertNotIn("PRIVATE_TELEPATHY_TEXT", encoded)
        self.assertNotIn("CHAIN_OF_THOUGHT_SENTINEL", encoded)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("source://private/raw-handle", encoded)

if __name__ == "__main__":
    unittest.main()
