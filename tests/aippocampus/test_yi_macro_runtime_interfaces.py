from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import (  # noqa: E402
    audit,
    cross_grain,
    hexagram,
    transform_orbit,
    transition_taxonomy,
)


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

    def test_cross_grain_projection_reports_layer_line_trigram_and_orbit_without_authority_upgrade(self) -> None:
        broken = cross_grain.project_cross_grain_projection((1, 0, 1, 0, 1, 0))
        orbit = cross_grain.project_cross_grain_projection("既济", target="未济")

        self.assertEqual(broken["kind"], "yi_macro_cross_grain_projection")
        self.assertEqual([item["layer"] for item in broken["three_powers_projection"]], ["earth", "human", "heaven"])
        self.assertIn("broken_coupling_earth_heaven", broken["six_line_projection"]["reason_codes"])
        self.assertTrue(broken["trigram_projection"]["not_full_hexagram_state"])
        self.assertEqual(orbit["transform_orbit_projection"]["relation"], "same_reversible_orbit")
        for packet in (broken, orbit):
            self.assertEqual(packet["authority_level"], "navigation_only")
            self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
            self.assertFalse(packet["fact_claim_allowed"])
            self.assertFalse(packet["ranking_weight_changes"])

    def test_change_line_transition_records_local_medium_and_inversion_without_advice(self) -> None:
        local = cross_grain.macro_transition_record("乾", (1,), source_refs=[{"source_id": "local"}])
        medium = cross_grain.macro_transition_record("乾", (1, 2, 3), source_refs=[{"source_id": "medium"}])
        inversion = cross_grain.macro_transition_record("乾", (1, 2, 3, 4, 5, 6), source_refs=[{"source_id": "inversion"}])

        self.assertEqual(local["perturbation_band"], "local")
        self.assertEqual(local["changed_line_layers"], [{"line": 1, "layer": "earth"}])
        self.assertEqual(local["dominant_changed_layer"], "earth")
        self.assertEqual(medium["perturbation_band"], "medium")
        self.assertEqual(medium["changed_layer_counts"], {"earth": 2, "human": 1, "heaven": 0})
        self.assertEqual(medium["dominant_changed_layer"], "earth")
        self.assertEqual(inversion["perturbation_band"], "inversion")
        self.assertEqual(inversion["dominant_changed_layer"], "multi_layer")
        self.assertTrue(inversion["review_policy"]["requires_conflict_review_before_action"])
        for packet in (local, medium, inversion):
            self.assertEqual(packet["authority_level"], "navigation_only")
            self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
            self.assertFalse(packet["fact_claim_allowed"])
            self.assertFalse(packet["foreground_advice_allowed"])

    def test_nuclear_basin_is_locked_to_explain_only_without_route_merge_or_ranking_effect(self) -> None:
        policy = cross_grain.nuclear_basin_explain_policy("乾")

        self.assertEqual(policy["decision"], "explain_only_lock")
        self.assertEqual(policy["projection_kind"], "non_invertible_nuclear_projection")
        self.assertFalse(policy["route_merge_allowed"])
        self.assertFalse(policy["ranking_weight_changes"])
        self.assertFalse(policy["source_support_from_basin_membership"])
        self.assertFalse(policy["foreground_emitted"])

    def test_transition_taxonomy_composes_existing_structural_reducers(self) -> None:
        same = transition_taxonomy.transition_taxonomy("乾", "乾")
        next_pair = transition_taxonomy.transition_taxonomy("蹇", "解")
        orbit = transition_taxonomy.transition_taxonomy("既济", "未济")
        distant = transition_taxonomy.transition_taxonomy("乾", "兑")

        self.assertIn("same_state", same["structural_labels"])
        self.assertIn("king_wen_next", next_pair["structural_labels"])
        self.assertIn("king_wen_pair_internal", next_pair["structural_labels"])
        self.assertIn("king_wen_pair_reverse", next_pair["structural_labels"])
        self.assertIn("reverse_and_opposite", orbit["structural_labels"])
        self.assertIn("same_cr_orbit", orbit["structural_labels"])
        self.assertIn("hamming_2", distant["structural_labels"])
        self.assertIn("perturbation_local", distant["structural_labels"])
        for packet in (same, next_pair, orbit, distant):
            self.assertTrue(packet["structural_labels"])
            self.assertEqual(packet["authority_level"], "navigation_only")
            self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
            self.assertFalse(packet["fact_claim_allowed"])
            self.assertFalse(packet["foreground_action_allowed"])

    def test_transition_inventory_covers_all_64x64_pairs_with_stable_counts(self) -> None:
        inventory = transition_taxonomy.transition_inventory()
        counts = inventory["label_counts"]

        self.assertEqual(inventory["state_count"], 64)
        self.assertEqual(inventory["transition_count"], 4096)
        self.assertEqual(counts["same_state"], 64)
        self.assertEqual(counts["hamming_1"], 384)
        self.assertEqual(counts["perturbation_local"], 1344)
        self.assertEqual(counts["king_wen_next"], 63)
        self.assertEqual(counts["king_wen_prev"], 63)
        self.assertEqual(counts["king_wen_pair_internal"], 64)
        self.assertEqual(counts["opposite"], 64)
        self.assertEqual(counts["reverse"], 64)
        self.assertEqual(counts["same_cr_orbit"], 224)
        self.assertNotIn("king_wen_anti_habituation", counts)
        self.assertNotIn("anti_habituation", counts)
        profile = inventory["aggregate_audit_context"]["king_wen_sequence_profile"]
        self.assertEqual(profile["adjacent_transition_count"], 63)
        self.assertTrue(profile["boundary"]["not_training_schedule"])
        self.assertEqual(inventory["aggregate_audit_context"]["pair_label_effect"], "none")
        self.assertEqual(inventory["aggregate_audit_context"]["ranking_weight_effect"], "none")
        self.assertEqual(inventory["aggregate_audit_context"]["claim_permission_effect"], "none")
        self.assertEqual(inventory["authority_level"], "navigation_only")
        self.assertEqual(inventory["claim_permission"], "no_claim_before_reopen")
        self.assertFalse(inventory["fact_claim_allowed"])
        self.assertNotIn("poem", inventory["non_goals"])
        self.assertFalse(inventory["raw_source_or_user_data_included"])


if __name__ == "__main__":
    unittest.main()
