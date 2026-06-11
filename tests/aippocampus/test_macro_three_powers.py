from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import hexagram, perturbation, three_powers  # noqa: E402


def _route_candidates() -> list[dict[str, object]]:
    return [
        {
            "route_id": "route_tests",
            "route_label": "test evidence route",
            "source_family": "tests",
            "output_mode": "bounded_evidence",
            "action_grammar": "bounded_evidence",
            "claim_permission": "bounded_claim_allowed",
            "source_handles": [{"source_id": "test_public_fixture"}],
            "source_text": "PRIVATE_SOURCE_SENTINEL",
        },
        {
            "route_id": "route_issue",
            "route_label": "issue coordination route",
            "source_family": "issue",
            "output_mode": "reopenable_route",
            "action_grammar": "reopenable_route",
            "claim_permission": "no_claim_before_reopen",
            "local_path": "C:\\private\\issue.md",
        },
        {
            "route_id": "route_roadmap",
            "route_label": "roadmap direction route",
            "source_family": "roadmap",
            "output_mode": "direction_only",
            "action_grammar": "direction_only",
            "claim_permission": "no_claim_before_reopen",
        },
    ]


class MacroThreePowersTests(unittest.TestCase):
    def test_same_query_prioritizes_different_routes_by_active_layer(self) -> None:
        routes = _route_candidates()

        earth = three_powers.apply_three_powers_fanout(
            "continue the continuity work",
            routes,
            active_layer="earth",
        )
        human = three_powers.apply_three_powers_fanout(
            "continue the continuity work",
            routes,
            active_layer="human",
        )
        heaven = three_powers.apply_three_powers_fanout(
            "continue the continuity work",
            routes,
            active_layer="heaven",
        )

        self.assertEqual(earth["ranked_candidates"][0]["route_id"], "route_tests")
        self.assertEqual(human["ranked_candidates"][0]["route_id"], "route_issue")
        self.assertEqual(heaven["ranked_candidates"][0]["route_id"], "route_roadmap")
        self.assertEqual(earth["facet_counts"], {"earth": 1, "human": 1, "heaven": 1})
        for packet in (earth, human, heaven):
            self.assertEqual(packet["authority_level"], "navigation_only")
            self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
            self.assertFalse(packet["fact_claim_allowed"])

    def test_query_layer_can_be_explicit_or_inferred(self) -> None:
        explicit = three_powers.infer_active_layer("anything", explicit_layer="地")
        earth = three_powers.infer_active_layer("show benchmark evidence and tests")
        human = three_powers.infer_active_layer("what issue or PR should the agent do next")
        heaven = three_powers.infer_active_layer("roadmap thesis and public positioning")

        self.assertEqual(explicit["active_layer"], "earth")
        self.assertEqual(explicit["source"], "explicit")
        self.assertEqual(earth["active_layer"], "earth")
        self.assertEqual(human["active_layer"], "human")
        self.assertEqual(heaven["active_layer"], "heaven")

    def test_perturbation_amplitude_controls_layer_aware_fanout(self) -> None:
        routes = [
            {
                "route_id": f"route_tests_{index}",
                "route_label": f"test route {index}",
                "source_family": "tests",
            }
            for index in range(6)
        ] + [
            {"route_id": "route_issue", "route_label": "issue route", "source_family": "issue"},
            {
                "route_id": "route_roadmap",
                "route_label": "roadmap route",
                "source_family": "roadmap",
            },
        ]
        local = perturbation.build_perturbation_packet(
            "乾",
            hexagram.change_lines("乾", (1,)),
        )
        medium = perturbation.build_perturbation_packet(
            "乾",
            hexagram.change_lines("乾", (1, 2, 3)),
        )
        large = perturbation.build_perturbation_packet(
            "屯",
            hexagram.change_lines("屯", (1, 2, 5, 6)),
        )
        inversion = perturbation.build_perturbation_packet("乾", "坤")

        local_packet = three_powers.apply_three_powers_fanout(
            "test evidence",
            routes,
            active_layer="earth",
            perturbation_packet=local,
        )
        medium_packet = three_powers.apply_three_powers_fanout(
            "test evidence",
            routes,
            active_layer="earth",
            perturbation_packet=medium,
        )
        large_packet = three_powers.apply_three_powers_fanout(
            "test evidence",
            routes,
            active_layer="earth",
            perturbation_packet=large,
        )
        inversion_packet = three_powers.apply_three_powers_fanout(
            "test evidence",
            routes,
            active_layer="earth",
            perturbation_packet=inversion,
        )

        self.assertEqual(local_packet["fanout_policy"]["candidate_limit"], 2)
        self.assertEqual(medium_packet["fanout_policy"]["candidate_limit"], 4)
        self.assertEqual(large_packet["fanout_policy"]["candidate_limit"], 8)
        self.assertLess(
            len(local_packet["selected_route_ids"]),
            len(medium_packet["selected_route_ids"]),
        )
        self.assertLess(
            len(medium_packet["selected_route_ids"]),
            len(large_packet["selected_route_ids"]),
        )
        self.assertEqual(inversion_packet["selected_route_ids"], [])
        self.assertIn(
            "inversion_requires_source_reopen_or_conflict_review",
            inversion_packet["diagnostics"],
        )

    def test_layer_disagreement_stays_navigation_only_and_public_safe(self) -> None:
        heaven_only = three_powers.apply_three_powers_fanout(
            "public positioning",
            [
                {
                    "route_id": "route_roadmap",
                    "route_label": "roadmap direction route",
                    "source_family": "roadmap",
                    "claim_permission": "no_claim_before_reopen",
                }
            ],
            active_layer="heaven",
        )
        earth_without_heaven = three_powers.apply_three_powers_fanout(
            "benchmark evidence",
            [_route_candidates()[0]],
            active_layer="earth",
        )
        encoded = json.dumps(earth_without_heaven, ensure_ascii=False, sort_keys=True)

        self.assertIn(
            "heaven_direction_clear_but_earth_evidence_missing",
            heaven_only["diagnostics"],
        )
        self.assertIn(
            "earth_supports_but_heaven_not_ready",
            earth_without_heaven["diagnostics"],
        )
        self.assertFalse(heaven_only["fact_claim_allowed"])
        self.assertEqual(
            heaven_only["ranked_candidates"][0]["claim_permission"],
            "no_claim_before_reopen",
        )
        self.assertEqual(
            earth_without_heaven["ranked_candidates"][0]["claim_permission"],
            "bounded_claim_allowed",
        )
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)


if __name__ == "__main__":
    unittest.main()
