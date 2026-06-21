from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from aippocampus_runtime.ops import coordination_topology


class CoordinationTopologyTests(unittest.TestCase):
    def test_fixture_detects_coordination_shapes_without_assigning_work(self) -> None:
        report = coordination_topology.build_coordination_topology_report()
        diagnostics = {item["case_id"]: item for item in report["diagnostics"]}

        self.assertEqual(report["kind"], "aippocampus_coordination_topology_diagnostic")
        self.assertTrue(report["contract_gate_ok"], json.dumps(report, indent=2))
        self.assertTrue(report["safety_gate_ok"], json.dumps(report, indent=2))
        self.assertFalse(report["usefulness_gate_ok"])
        self.assertEqual(report["authority_level"], "navigation_explain_only")
        self.assertEqual(report["runtime_position"], "post_packet_explain_side")
        self.assertFalse(report["every_turn_scan"])
        self.assertFalse(report["ranking_weight_changes"])
        self.assertFalse(report["foreground_hook_mutation"])
        self.assertEqual(report["metrics"]["case_count"], 8)
        self.assertEqual(report["metrics"]["agent_collision_count"], 1)
        self.assertEqual(report["metrics"]["overlap_without_coordination_count"], 1)
        self.assertEqual(report["metrics"]["orphaned_handoff_count"], 1)
        self.assertEqual(report["metrics"]["cut_point_count"], 1)
        self.assertEqual(report["metrics"]["boundary_crossing_count"], 1)
        self.assertEqual(report["metrics"]["repeated_stale_route_loop_count"], 1)
        self.assertEqual(report["metrics"]["handoff_knot_count"], 1)
        self.assertEqual(report["metrics"]["healthy_handoff_count"], 1)
        self.assertEqual(report["metrics"]["privacy_clean_but_coordination_useless_count"], 1)

        self.assertEqual(diagnostics["healthy_handoff"]["diagnostic"], "healthy_handoff")
        self.assertEqual(diagnostics["collision_without_handoff"]["diagnostic"], "collision")
        self.assertEqual(
            diagnostics["overlap_privacy_clean_but_useless"]["diagnostic"],
            "overlap_without_coordination",
        )
        self.assertEqual(diagnostics["orphaned_route_packet"]["diagnostic"], "orphan")
        self.assertEqual(diagnostics["single_bridge_cut_point"]["diagnostic"], "cut_point")
        self.assertEqual(diagnostics["private_boundary_crossing"]["diagnostic"], "boundary_crossing")
        self.assertEqual(diagnostics["stale_route_loop"]["diagnostic"], "loop")
        self.assertEqual(diagnostics["handoff_source_knot"]["diagnostic"], "handoff_knot")

        for item in report["diagnostics"]:
            self.assertTrue(item["navigation_only"])
            self.assertFalse(item["assignment_created"])
            self.assertEqual(item["claim_permission"], "no_claim_before_source_reopen")

    def test_topology_shapes_project_to_maintenance_action_hints(self) -> None:
        report = coordination_topology.build_coordination_topology_report()
        by_id = {item["case_id"]: item for item in report["diagnostics"]}

        self.assertEqual(
            by_id["stale_route_loop"]["topology_shape"],
            "repeated_failed_route_cycle",
        )
        self.assertEqual(
            by_id["stale_route_loop"]["maintenance_action_hint"],
            "suppress_until_source_changes",
        )
        self.assertEqual(
            by_id["orphaned_route_packet"]["topology_shape"],
            "orphaned_handoff",
        )
        self.assertEqual(by_id["orphaned_route_packet"]["maintenance_action_hint"], "needs_review")

    def test_private_material_is_sanitized_from_report_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "coordination-private.json"
            rows = [
                {
                    "case_id": "private_crossing",
                    "scenario": "boundary_crossing",
                    "agents": ["codex-a", "codex-b"],
                    "scope_ids": ["fragile.source"],
                    "private_payload": "PRIVATE_COORDINATION_TEXT must not leave diagnostics",
                    "local_path": str(root / "private-rollout.jsonl"),
                    "source_handle": "source://private/raw-handle",
                    "privacy_material_crossed": True,
                    "visible_to_agent": "codex-b",
                    "owner_agent": "codex-a",
                }
            ]
            input_path.write_text(json.dumps(rows), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.ops.coordination_topology",
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
        self.assertEqual(payload["metrics"]["boundary_crossing_count"], 1)
        self.assertEqual(payload["privacy_boundary"]["forbidden_marker_count"], 0)
        self.assertNotIn("PRIVATE_COORDINATION_TEXT", encoded)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("source://private/raw-handle", encoded)

if __name__ == "__main__":
    unittest.main()
