from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import timing_affordance  # noqa: E402


class MacroTimingAffordanceTests(unittest.TestCase):
    def test_revival_with_thin_source_probes_gently(self) -> None:
        packet = timing_affordance.macro_timing_affordance(
            momentum={"phase": "revival"},
            source_shape={"freshness": "current", "source_coverage": "thin"},
        )

        self.assertEqual(packet["timing_posture"], "probe_gently")
        self.assertEqual(packet["attention_bandwidth"], "backstage")
        self.assertEqual(packet["claim_permission"], "none")

    def test_closeout_current_local_perturbation_acts_bounded(self) -> None:
        packet = timing_affordance.macro_timing_affordance(
            momentum={"phase": "closeout_pressure"},
            perturbation={"band": "local"},
            source_shape={"freshness": "current", "source_coverage": "strong"},
        )

        self.assertEqual(packet["timing_posture"], "act_now_bounded")
        self.assertEqual(packet["recommended_next"], "run_bounded_verification_then_close")

    def test_stale_or_conflict_reopens_first(self) -> None:
        packet = timing_affordance.macro_timing_affordance(
            perturbation={"conflict_review_required": True},
            topology={"broken_coupling": True},
            source_shape={"freshness": "stale"},
        )

        self.assertEqual(packet["timing_posture"], "conflict_reopen_first")
        self.assertEqual(packet["attention_bandwidth"], "reopen_first")

    def test_feedback_gate_needs_repeated_misses(self) -> None:
        single = timing_affordance.timing_affordance_feedback_gate(
            [{"outcome": "read_timeout"}]
        )
        repeated = timing_affordance.timing_affordance_feedback_gate(
            [{"outcome": "read_timeout"}, {"outcome": "source_miss"}]
        )

        self.assertFalse(single["timing_affordance_falsified"])
        self.assertTrue(repeated["timing_affordance_falsified"])
        self.assertEqual(repeated["runtime_recheck_reason"], "timing_affordance_falsified")
        self.assertTrue(repeated["boundary"]["budget_recommendation_is_not_policy_mutation"])


if __name__ == "__main__":
    unittest.main()
