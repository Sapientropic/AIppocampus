from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import momentum, state  # noqa: E402


class MacroMomentumTests(unittest.TestCase):
    def test_phase_mapper_covers_twelve_phase_cycle_from_delta_basis(self) -> None:
        cases = [
            ({"support_delta": 0.05}, "fu", "turning"),
            ({"support_delta": 0.20}, "lin", "rising"),
            ({"support_delta": 0.40}, "tai", "rising"),
            ({"support_delta": 0.70}, "dazhuang", "rising"),
            ({"support_delta": 0.95}, "guai", "peaking"),
            ({"support_delta": 1.30}, "qian", "peaking"),
            ({"staleness_delta": 0.05}, "gou", "turning"),
            ({"staleness_delta": 0.20}, "dun", "declining"),
            ({"counter_evidence_delta": 0.40}, "pi", "declining"),
            ({"counter_evidence_delta": 0.65}, "guan", "declining"),
            ({"counter_evidence_delta": 0.95}, "bo", "hibernating"),
            ({"counter_evidence_delta": 1.30}, "kun", "hibernating"),
        ]

        for basis, phase, direction in cases:
            with self.subTest(phase=phase):
                block = momentum.build_momentum_block(basis)
                self.assertEqual(block["phase"], phase)
                self.assertEqual(block["direction"], direction)
                self.assertEqual(set(block["basis"]), set(momentum.MOMENTUM_BASIS_KEYS))
                self.assertEqual(block["authority_level"], "navigation_only")
                self.assertEqual(block["claim_permission"], "no_claim_before_reopen")
                self.assertFalse(block["fact_claim_allowed"])

    def test_momentum_state_adds_recheck_without_blending_with_perturbation(self) -> None:
        entry = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=(1,),
            source_refs=({"source_id": "momentum-source"},),
            updated_at="2026-06-11T10:00:00Z",
            momentum={"basis": {"support_delta": 1.30}},
        )
        turning = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=(1,),
            source_refs=({"source_id": "turn-source"},),
            updated_at="2026-06-11T10:00:00Z",
            momentum={"basis": {"user_correction_delta": 0.05}},
        )
        sleeping = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="坤",
            source_refs=({"source_id": "sleep-source"},),
            updated_at="2026-06-11T10:00:00Z",
        )

        self.assertEqual(entry["momentum"]["phase"], "qian")
        self.assertEqual(entry["momentum"]["direction"], "peaking")
        self.assertEqual(entry["perturbation"]["perturbation"], "distance_1")
        self.assertIn("momentum_overconfidence_watch", entry["recheck_on"])
        self.assertEqual(entry["stale_after_days"], 21)
        self.assertEqual(turning["momentum"]["phase"], "gou")
        self.assertIn("momentum_first_decay_recheck", turning["recheck_on"])
        self.assertEqual(turning["stale_after_days"], 14)
        self.assertEqual(sleeping["momentum"]["phase"], "kun")
        self.assertIn("momentum_hibernation_review", sleeping["recheck_on"])
        self.assertEqual(sleeping["stale_after_days"], 60)

    def test_momentum_validation_rejects_claim_or_rawish_block(self) -> None:
        entry = state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="泰",
            source_refs=({"source_id": "balanced-source"},),
            updated_at="2026-06-11T10:00:00Z",
            momentum={"basis": {"support_delta": 0.40}},
        )
        bad = dict(entry)
        bad["momentum"] = {
            **dict(entry["momentum"]),
            "direction": "peaking",
            "claim_permission": "bounded_claim_allowed",
            "fact_claim_allowed": True,
        }

        validation = state.validate_macro_orientation_state(entry)
        bad_validation = state.validate_macro_orientation_state(bad)
        encoded = json.dumps(entry["momentum"], ensure_ascii=False, sort_keys=True)

        self.assertTrue(validation["ok"], validation)
        self.assertFalse(bad_validation["ok"])
        self.assertIn("momentum_direction_mismatch", bad_validation["errors"])
        self.assertIn("momentum_claim_permission_must_require_reopen", bad_validation["errors"])
        self.assertIn("momentum_fact_claim_must_be_false", bad_validation["errors"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("PRIVATE", encoded)


if __name__ == "__main__":
    unittest.main()
