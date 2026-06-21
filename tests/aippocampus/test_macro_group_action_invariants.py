from __future__ import annotations

import unittest

from aippocampus_runtime.macro import hexagram, transform_orbit


class MacroGroupActionInvariantTests(unittest.TestCase):
    def test_group_diagnostic_names_opposite_reverse_without_claim_authority(self) -> None:
        target = transform_orbit.apply_operation(
            transform_orbit.apply_operation("屯", "opposite"),
            "reverse",
        )

        diagnostic = transform_orbit.yi_group_action_invariant_diagnostic(
            "屯",
            target,
            source_refs=[{"source_id": "fixture:yi"}],
        )
        inventory = transform_orbit.reversible_orbit_inventory(
            operation_set="opposite_reverse_v4"
        )

        self.assertEqual(diagnostic["kind"], "yi_group_action_invariant_diagnostic")
        self.assertEqual(diagnostic["relation"], "opposite_reverse")
        self.assertEqual(inventory["orbit_count"], 20)
        self.assertEqual(diagnostic["claim_permission"], "none")
        self.assertFalse(diagnostic["may_satisfy_invariant"])
        self.assertTrue(diagnostic["boundary"]["orbit_membership_is_not_source_evidence"])

    def test_line_flip_is_perturbation_not_orbit(self) -> None:
        target = hexagram.change_lines("乾", (1,))

        diagnostic = transform_orbit.yi_group_action_invariant_diagnostic("乾", target)

        self.assertEqual(diagnostic["relation"], "one_line_perturbation")
        self.assertTrue(diagnostic["perturbation_not_orbit"])
        self.assertEqual(diagnostic["runtime_recheck_reason"], "source_reanchoring_required")

    def test_reanchoring_tracks_churn_even_when_current_distance_cancels(self) -> None:
        audit = transform_orbit.source_reanchoring_audit(
            "乾",
            "乾",
            ["乾", "坤", "乾"],
            source_reopened=False,
        )

        self.assertEqual(audit["anchor_hamming_distance"], 0)
        self.assertEqual(audit["cumulative_transition_distance"], 12)
        self.assertTrue(audit["source_reanchoring_required"])
        self.assertTrue(audit["boundary"]["current_distance_does_not_cancel_transition_churn"])

    def test_orbit_oscillation_warns_on_ping_pong(self) -> None:
        audit = transform_orbit.orbit_oscillation_audit(["乾", "坤", "乾", "坤", "乾"])

        self.assertTrue(audit["orbit_oscillation_warning"])
        self.assertEqual(audit["runtime_recheck_reason"], "orbit_oscillation_warning")

if __name__ == "__main__":
    unittest.main()
