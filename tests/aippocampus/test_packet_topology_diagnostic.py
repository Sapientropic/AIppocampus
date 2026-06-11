from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import packet_topology_diagnostic  # noqa: E402


class PacketTopologyDiagnosticTests(unittest.TestCase):
    def test_fixture_detects_relation_failures_without_becoming_truth_layer(self) -> None:
        report = packet_topology_diagnostic.build_packet_topology_report()
        by_id = {item["case_id"]: item for item in report["diagnostics"]}
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_packet_topology_diagnostic")
        self.assertEqual(report["diagnostic_kind"], "packet_topology_diagnostic")
        self.assertTrue(report["contract_gate_ok"], json.dumps(report, indent=2))
        self.assertTrue(report["safety_gate_ok"], json.dumps(report, indent=2))
        self.assertFalse(report["usefulness_gate_ok"])
        self.assertEqual(report["runtime_boundary"], "post_packet_explain_side")
        self.assertFalse(report["every_turn_scan"])
        self.assertFalse(report["new_score_layer"])
        self.assertFalse(report["topology_is_truth_source"])
        self.assertNotIn('"position"', encoded)

        self.assertEqual(report["metrics"]["case_count"], 8)
        self.assertEqual(report["metrics"]["navigation_as_claim_count"], 1)
        self.assertEqual(report["metrics"]["candidate_as_authority_count"], 1)
        self.assertEqual(report["metrics"]["macro_as_decision_count"], 1)
        self.assertEqual(report["metrics"]["source_handle_as_fact_count"], 1)
        self.assertEqual(report["metrics"]["agency_suppression_count"], 1)
        self.assertEqual(report["metrics"]["knot_without_unlinking_move_count"], 1)
        self.assertEqual(report["metrics"]["explicit_route_cycle_count"], 1)
        self.assertEqual(report["metrics"]["missing_middle_or_cut_point_count"], 1)
        self.assertEqual(report["metrics"]["healthy_relation_preserved_count"], 1)

        self.assertEqual(by_id["healthy_navigation_packet"]["diagnostic"], "relation_preserved")
        self.assertEqual(by_id["direction_only_used_as_evidence"]["diagnostic"], "authority_overreach")
        self.assertEqual(by_id["macro_rendered_as_action_instruction"]["diagnostic"], "authority_overreach")
        self.assertEqual(by_id["dream_candidate_rendered_as_certainty"]["diagnostic"], "authority_overreach")
        self.assertEqual(by_id["narrative_missing_middle"]["diagnostic"], "missing_middle_or_cut_point")
        self.assertEqual(by_id["repeated_failed_route_cycle"]["diagnostic"], "explicit_route_cycle")
        self.assertEqual(by_id["overfiltered_useful_packet"]["diagnostic"], "agency_suppression_fixture")
        self.assertEqual(by_id["obligation_knot_without_unlinking"]["diagnostic"], "knot_without_unlinking_move")

        for item in report["diagnostics"]:
            self.assertEqual(item["claim_permission"], "navigation_only_not_fact")
            self.assertEqual(item["full_diagnostic_surface"], "explain_debug_or_campus")
            self.assertTrue(item["foreground_projection_tiny"])

    def test_borromean_break_counts_only_when_foreground_visible_or_action_shaping(self) -> None:
        report = packet_topology_diagnostic.build_packet_topology_report(
            [
                {
                    "case_id": "idle_background_candidate",
                    "packet_type": "dream_candidate",
                    "borromean_break": True,
                    "foreground_visible": False,
                    "action_shaping": False,
                },
                {
                    "case_id": "foreground_action_packet",
                    "packet_type": "memory_packet",
                    "borromean_break": True,
                    "foreground_visible": True,
                    "action_shaping": True,
                },
            ]
        )

        self.assertEqual(report["metrics"]["borromean_break_count"], 1)
        self.assertEqual(report["diagnostics"][0]["diagnostic"], "relation_preserved")
        self.assertEqual(report["diagnostics"][1]["diagnostic"], "authority_overreach")

    def test_cli_report_sanitizes_private_packet_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "packet-topology-private.json"
            rows = [
                {
                    "case_id": "private_packet",
                    "packet_type": "memory_packet",
                    "output_mode": "direction_only",
                    "rendered_as_evidence": True,
                    "source_handle": "source://private/raw-handle",
                    "raw_source_text": "PRIVATE_PACKET_TEXT must not leave diagnostics",
                    "local_path": str(root / "private-rollout.jsonl"),
                }
            ]
            input_path.write_text(json.dumps(rows), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.ops.packet_topology_diagnostic",
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
        self.assertNotIn("PRIVATE_PACKET_TEXT", encoded)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("source://private/raw-handle", encoded)


if __name__ == "__main__":
    unittest.main()
