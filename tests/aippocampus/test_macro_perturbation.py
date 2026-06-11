from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import hexagram, perturbation  # noqa: E402


class MacroPerturbationTests(unittest.TestCase):
    def test_distance_bands_widen_fanout_without_authorizing_claims(self) -> None:
        local_target = hexagram.change_lines("乾", (1,))
        medium_target = hexagram.change_lines("乾", (1, 2, 3))
        large_target = hexagram.change_lines("屯", (1, 2, 5, 6))

        local = perturbation.build_perturbation_packet("乾", local_target)
        medium = perturbation.build_perturbation_packet("乾", medium_target)
        large = perturbation.build_perturbation_packet("屯", large_target)

        self.assertEqual(local["band"], "local")
        self.assertEqual(medium["band"], "medium")
        self.assertEqual(large["band"], "large")
        self.assertLess(
            local["fanout_hint"]["recommended_candidate_limit"],
            medium["fanout_hint"]["recommended_candidate_limit"],
        )
        self.assertLess(
            medium["fanout_hint"]["recommended_candidate_limit"],
            large["fanout_hint"]["recommended_candidate_limit"],
        )
        for packet in (local, medium, large):
            self.assertEqual(packet["authority_level"], "navigation_only")
            self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
            self.assertFalse(packet["fact_claim_allowed"])
            self.assertTrue(packet["source_boundary"]["navigation_only_not_fact"])

    def test_inversion_requires_reopen_or_conflict_review_before_high_risk_use(self) -> None:
        packet = perturbation.build_perturbation_packet("乾", "坤")

        self.assertEqual(packet["hamming_distance"], 6)
        self.assertEqual(packet["band"], "inversion")
        self.assertEqual(packet["route_policy"], "reopen_or_conflict_review")
        self.assertEqual(
            packet["source_reopen_policy"],
            "source_reopen_or_conflict_review_required",
        )
        self.assertTrue(packet["conflict_review_required"])
        self.assertEqual(packet["fanout_hint"]["recommended_candidate_limit"], 0)
        self.assertEqual(packet["fanout_hint"]["candidate_limit_after_review"], 8)
        self.assertIn(
            "inversion_requires_source_reopen_or_conflict_review",
            packet["reason_codes"],
        )
        self.assertFalse(packet["fact_claim_allowed"])

    def test_unpromoted_journey_signal_cannot_widen_project_fanout(self) -> None:
        blocked = perturbation.build_perturbation_packet(
            "屯",
            "蒙",
            signal_scale="journey",
            promoted_to_project=False,
        )
        promoted = perturbation.build_perturbation_packet(
            "屯",
            "蒙",
            signal_scale="journey",
            promoted_to_project=True,
        )

        self.assertEqual(blocked["hamming_distance"], 4)
        self.assertFalse(blocked["project_level_signal"])
        self.assertEqual(blocked["route_policy"], "no_project_fanout_from_unpromoted_signal")
        self.assertEqual(blocked["fanout_hint"]["recommended_candidate_limit"], 0)
        self.assertIn("scale_not_promoted_no_project_fanout", blocked["reason_codes"])

        self.assertTrue(promoted["project_level_signal"])
        self.assertEqual(promoted["route_policy"], "broad_fanout_with_stale_conflict_checks")
        self.assertGreater(promoted["fanout_hint"]["recommended_candidate_limit"], 0)

    def test_compact_label_is_foreground_safe(self) -> None:
        packet = perturbation.build_perturbation_packet("屯", "蒙")
        compact = perturbation.compact_perturbation_label(packet)
        encoded = json.dumps(compact, ensure_ascii=False, sort_keys=True)

        self.assertEqual(
            compact,
            {
                "movement": "large_shift",
                "perturbation": "distance_4",
                "changed_line_count": 4,
                "route_policy": "broad_fanout_with_stale_conflict_checks",
                "authority_level": "navigation_only",
                "claim_permission": "no_claim_before_reopen",
            },
        )
        self.assertNotIn("previous_hexagram", compact)
        self.assertNotIn("changed_lines", compact)
        self.assertNotIn("爻辞", encoded)
        self.assertNotIn("commentary", encoded)
        self.assertNotIn("interpretation", encoded)


if __name__ == "__main__":
    unittest.main()
