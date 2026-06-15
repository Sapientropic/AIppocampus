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
from aippocampus_runtime.topology import primitive_registry  # noqa: E402


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

        self.assertEqual(report["metrics"]["case_count"], 12)
        self.assertEqual(report["metrics"]["navigation_as_claim_count"], 1)
        self.assertEqual(report["metrics"]["candidate_as_authority_count"], 1)
        self.assertEqual(report["metrics"]["macro_as_decision_count"], 1)
        self.assertEqual(report["metrics"]["source_handle_as_fact_count"], 1)
        self.assertEqual(report["metrics"]["agency_suppression_count"], 1)
        self.assertEqual(report["metrics"]["knot_without_unlinking_move_count"], 1)
        self.assertEqual(report["metrics"]["explicit_route_cycle_count"], 1)
        self.assertEqual(report["metrics"]["missing_middle_or_cut_point_count"], 1)
        self.assertEqual(report["metrics"]["healthy_relation_preserved_count"], 2)
        self.assertEqual(report["metrics"]["borromean_break_count"], 3)

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

    def test_borromean_reducer_finds_missing_sides_without_manual_boolean(self) -> None:
        report = packet_topology_diagnostic.build_packet_topology_report(
            [
                {
                    "case_id": "missing_source_side",
                    "packet_type": "memory_packet",
                    "foreground_visible": True,
                    "user_need": "continue issue closeout",
                    "agent_agency_room": True,
                    "authority_level": "navigation_only",
                    "claim_permission": "no_claim_before_reopen",
                },
                {
                    "case_id": "missing_user_need_side",
                    "packet_type": "memory_packet",
                    "foreground_visible": True,
                    "source_refs": [{"source_id": "issue:#1548"}],
                    "agent_agency_room": True,
                    "authority_level": "navigation_only",
                    "claim_permission": "no_claim_before_reopen",
                },
                {
                    "case_id": "missing_agency_side",
                    "packet_type": "memory_packet",
                    "action_shaping": True,
                    "source_refs": [{"source_id": "issue:#1548"}],
                    "task_anchor": "continue issue closeout",
                    "rendered_as_action_instruction": True,
                    "authority_level": "navigation_only",
                    "claim_permission": "no_claim_before_reopen",
                },
                {
                    "case_id": "healthy_borromean_route",
                    "packet_type": "memory_packet",
                    "foreground_visible": True,
                    "source_refs": [{"source_id": "issue:#1548"}],
                    "task_anchor": "continue issue closeout",
                    "agent_agency_room": True,
                    "authority_level": "navigation_only",
                    "claim_permission": "no_claim_before_reopen",
                },
            ]
        )
        by_id = {item["case_id"]: item for item in report["diagnostics"]}

        self.assertEqual(report["metrics"]["borromean_break_count"], 3)
        self.assertIn(
            "borromean_missing_source_side",
            by_id["missing_source_side"]["reason_codes"],
        )
        self.assertIn(
            "borromean_missing_user_need_side",
            by_id["missing_user_need_side"]["reason_codes"],
        )
        self.assertIn(
            "borromean_missing_agent_agency_side",
            by_id["missing_agency_side"]["reason_codes"],
        )
        self.assertFalse(by_id["healthy_borromean_route"]["borromean_break_counted"])
        self.assertEqual(
            by_id["healthy_borromean_route"]["borromean_relation"]["status"],
            "preserved",
        )
        self.assertIn(
            "borromean_relation",
            by_id["missing_source_side"]["reducer_diagnostics"],
        )

    def test_topology_primitive_registry_separates_reducers_from_annotations(self) -> None:
        report = packet_topology_diagnostic.build_packet_topology_report(
            [
                {
                    "case_id": "reducer_case",
                    "packet_type": "memory_packet",
                    "output_mode": "direction_only",
                    "rendered_as_evidence": True,
                },
                {
                    "case_id": "annotation_case",
                    "packet_type": "narrative_packet",
                    "missing_middle": True,
                },
            ]
        )
        by_id = {item["case_id"]: item for item in report["diagnostics"]}
        registry = primitive_registry.topology_primitive_registry()

        self.assertEqual(
            registry["navigation_as_claim"]["provenance"],
            "reducer_backed",
        )
        self.assertEqual(
            registry["missing_middle_or_cut_point"]["provenance"],
            "annotation_backed",
        )
        self.assertIn("navigation_as_claim", by_id["reducer_case"]["reducer_diagnostics"])
        self.assertIn(
            "producer_annotated_missing_middle",
            by_id["annotation_case"]["reason_codes"],
        )
        self.assertEqual(
            by_id["annotation_case"]["diagnostic_provenance"],
            "annotation_backed",
        )
        self.assertIn("missing_middle_or_cut_point", report["topology_primitive_registry"])

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
