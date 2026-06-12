from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import audit, hexagram, transform_orbit  # noqa: E402


class YiMacroRuntimeInterfaceAuditTests(unittest.TestCase):
    def test_canonical_table_covers_issue_1272_primitives_and_links(self) -> None:
        report = audit.build_yi_runtime_interface_audit_report()
        primitive_ids = {row["primitive_id"] for row in report["primitives"]}

        self.assertTrue(report["ok"])
        self.assertEqual(report["discussion_links"]["dynamics"], "#1210")
        self.assertEqual(report["discussion_links"]["topology"], "#1262")
        self.assertEqual(report["discussion_links"]["local_global_gluing"], "#1270")
        self.assertTrue(
            {
                "hexagram_state_six_bit",
                "changing_lines",
                "hamming_perturbation_width",
                "nuclear_opposite_reverse_transforms",
                "king_wen_sequence_movement",
                "three_powers_route_facets",
                "shi_ying_role_positioning",
                "xiao_xi_momentum",
                "internal_line_topology",
                "proper_or_improper_position",
                "najia_active_axis_timing",
                "guaqi_source_epoch_cadence",
            }.issubset(primitive_ids)
        )

    def test_foreground_macro_primitives_have_action_grammar_and_never_evidence(self) -> None:
        report = audit.build_yi_runtime_interface_audit_report()

        self.assertEqual(report["metrics"]["foreground_guardrail_violation_count"], 0)
        for row in report["primitives"]:
            if not row["foreground_emitted"]:
                continue
            self.assertEqual(row["action_grammar"], "direction_only")
            self.assertEqual(row["authority_level"], "navigation_only")
            self.assertEqual(row["claim_permission"], "no_claim_before_reopen")
            self.assertFalse(row["fact_claim_allowed"])

    def test_deepen_only_and_research_only_primitives_stay_out_of_foreground(self) -> None:
        fixtures = audit.build_yi_runtime_interface_audit_report()["fixtures"]
        deepen_only = fixtures["deepen_explain_only"]
        research_only = fixtures["research_only"]

        self.assertEqual(deepen_only["primitive_id"], "nuclear_opposite_reverse_transforms")
        self.assertIn("deepen_explain_only", deepen_only["roles"])
        self.assertFalse(deepen_only["foreground_emitted"])
        self.assertFalse(deepen_only["fact_claim_allowed"])
        self.assertEqual(research_only["primitive_id"], "proper_or_improper_position")
        self.assertIn("research_only", research_only["roles"])
        self.assertFalse(research_only["fact_claim_allowed"])

    def test_hamming_momentum_and_topology_sheaf_fixtures_change_behavior_without_authority_upgrade(self) -> None:
        fixtures = audit.build_yi_runtime_interface_audit_report()["fixtures"]
        movement = fixtures["hamming_and_momentum"]
        topology_sheaf = fixtures["topology_sheaf_consumption"]

        self.assertTrue(movement["hamming_changes_fanout"])
        self.assertGreater(
            movement["large_shift"]["candidate_limit"],
            movement["local_shift"]["candidate_limit"],
        )
        self.assertTrue(movement["momentum_changes_recheck"])
        self.assertIn(
            "momentum_first_decay_recheck",
            movement["decaying_momentum"]["recheck_on"],
        )
        self.assertEqual(topology_sheaf["authority_level"], "navigation_only")
        self.assertFalse(topology_sheaf["fact_claim_allowed"])
        self.assertEqual(
            topology_sheaf["consumer_contract"]["global_glue_boundary"],
            "source_reopen_required_before_claim",
        )

    def test_transform_orbit_reports_reversible_relation_without_authority_upgrade(self) -> None:
        inventory = transform_orbit.reversible_orbit_inventory()

        self.assertEqual(inventory["operation_set"], "cr_reversible")
        self.assertEqual(inventory["orbit_count"], 20)
        self.assertEqual(inventory["size_distribution"], {2: 8, 4: 12})
        self.assertEqual(transform_orbit.apply_operation("乾", "opposite").name, "坤")
        self.assertEqual(transform_orbit.apply_operation("既济", "reverse").name, "未济")

        packet = transform_orbit.macro_transform_orbit_diagnostic("既济", "未济")
        self.assertEqual(packet["relation"], "same_reversible_orbit")
        self.assertEqual(packet["authority_level"], "navigation_only")
        self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
        self.assertFalse(packet["fact_claim_allowed"])
        self.assertFalse(packet["foreground_emitted"])

    def test_transform_orbit_keeps_line_flips_and_nuclear_out_of_reversible_orbit(self) -> None:
        qian = hexagram.hexagram_by_name("乾")
        neighbor = transform_orbit.line_flip_neighbors(qian)[0]

        self.assertEqual(transform_orbit.relation_label(qian, neighbor), "adjacent_flip")
        self.assertEqual(transform_orbit.relation_label("乾", "坎"), "different_route_family")
        self.assertNotIn("nuclear", transform_orbit.REVERSIBLE_OPERATION_SETS["cr_reversible"])

        nuclear_counterexamples = [
            item
            for item in hexagram.HEXAGRAMS
            if item.nuclear.name
            not in {member["name"] for member in transform_orbit.reversible_orbit_members(item)}
        ]
        self.assertTrue(nuclear_counterexamples)
        nuclear_report = transform_orbit.nuclear_basin_inventory()
        self.assertEqual(nuclear_report["basin_count"], 4)
        self.assertEqual(nuclear_report["basin_size_distribution"], {16: 4})

    def test_timing_primitives_are_report_only_and_do_not_replace_currentness_or_temporal_heads(self) -> None:
        rows = {row["primitive_id"]: row for row in audit.primitive_role_table()}
        active_axis = rows["najia_active_axis_timing"]
        cadence = rows["guaqi_source_epoch_cadence"]

        self.assertIn("recheck_timing", active_axis["roles"])
        self.assertIn("research_only", active_axis["roles"])
        self.assertIn("recheck_timing", cadence["roles"])
        self.assertFalse(active_axis["foreground_emitted"])
        self.assertFalse(cadence["foreground_emitted"])
        self.assertFalse(active_axis["fact_claim_allowed"])
        self.assertFalse(cadence["fact_claim_allowed"])
        self.assertIn("currentness_head_replacement", active_axis["non_goals"])
        self.assertIn("literal_calendar_or_solar_term_system", cadence["non_goals"])


if __name__ == "__main__":
    unittest.main()
