from __future__ import annotations

import json
import unittest

from aippocampus_runtime.macro import hexagram, perturbation, three_powers


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
        self.assertEqual(
            earth["facet_counts"],
            {"earth": 1, "human": 1, "heaven": 1, "unknown": 0},
        )
        for packet in (earth, human, heaven):
            self.assertEqual(packet["authority_level"], "navigation_only")
            self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
            self.assertFalse(packet["fact_claim_allowed"])

    def test_query_layer_can_be_explicit_or_inferred(self) -> None:
        explicit = three_powers.infer_active_layer("anything", explicit_layer="地")
        earth = three_powers.infer_active_layer("show benchmark evidence and tests")
        human = three_powers.infer_active_layer("what issue or PR should the agent do next")
        heaven = three_powers.infer_active_layer("roadmap thesis and public positioning")
        unknown = three_powers.infer_active_layer("continue the thing")

        self.assertEqual(explicit["active_layer"], "earth")
        self.assertEqual(explicit["source"], "explicit")
        self.assertEqual(earth["active_layer"], "earth")
        self.assertEqual(human["active_layer"], "human")
        self.assertEqual(heaven["active_layer"], "heaven")
        self.assertEqual(unknown["active_layer"], "unknown")
        self.assertEqual(unknown["source"], "semantic_profile_absent")
        self.assertEqual(explicit["ambiguity_status"], "explicit_override")
        self.assertEqual(earth["ambiguity_status"], "clear")
        self.assertTrue(earth["keyword_fallback_used"])

    def test_mixed_queries_report_active_layer_ambiguity_without_upgrading_authority(self) -> None:
        issue_tests = three_powers.infer_active_layer("issue PR test source coverage")
        roadmap_evidence = three_powers.infer_active_layer("roadmap benchmark")

        self.assertEqual(issue_tests["active_layer"], "unknown")
        self.assertEqual(issue_tests["ambiguity_status"], "ambiguous_tie")
        self.assertEqual(issue_tests["candidate_layers"], ["earth", "human"])
        self.assertIn("ambiguous_layer_tie", issue_tests["reason_codes"])
        self.assertEqual(roadmap_evidence["ambiguity_status"], "ambiguous_tie")
        self.assertEqual(roadmap_evidence["candidate_layers"], ["earth", "heaven"])
        self.assertIn("semantic_profile_absent", issue_tests["reason_codes"])

    def test_keyword_fallback_cannot_dominate_source_backed_route_signal(self) -> None:
        packet = three_powers.apply_three_powers_fanout(
            "issue issue issue",
            [
                {
                    "route_id": "keyword_issue_without_sources",
                    "source_family": "issue",
                    "source_handles": [],
                },
                {
                    "route_id": "source_backed_tests",
                    "source_family": "tests",
                    "source_handles": [
                        {"source_id": "s1"},
                        {"source_id": "s2"},
                        {"source_id": "s3"},
                        {"source_id": "s4"},
                    ],
                },
            ],
        )

        self.assertTrue(packet["keyword_fallback_used"])
        self.assertEqual(packet["layer_match_bonus"], 0)
        self.assertFalse(packet["layer_bias_applied"])
        self.assertEqual(
            packet["layer_bias_suppressed_reason"],
            "keyword_fallback_below_ranking_confidence",
        )
        self.assertIn("keyword_fallback_below_ranking_confidence", packet["diagnostics"])
        self.assertEqual(packet["ranked_candidates"][0]["route_id"], "source_backed_tests")
        self.assertIn("keyword_fallback_used", packet["diagnostics"])

    def test_semantic_layer_profile_can_drive_ranking_without_keyword_fallback(self) -> None:
        packet = three_powers.apply_three_powers_fanout(
            "",
            _route_candidates(),
            three_powers_layer_profile={"scores": {"heaven": 0.9, "earth": 0.1}},
        )

        self.assertEqual(packet["active_layer"], "heaven")
        self.assertFalse(packet["keyword_fallback_used"])
        self.assertEqual(packet["three_powers_layer_profile_source"], "semantic_profile")
        self.assertTrue(packet["layer_bias_applied"])
        self.assertEqual(packet["ranked_candidates"][0]["route_id"], "route_roadmap")

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

    def test_line_topology_diagnostics_do_not_change_ranking(self) -> None:
        routes = _route_candidates()

        baseline = three_powers.apply_three_powers_fanout(
            "benchmark evidence",
            routes,
            active_layer="earth",
        )
        with_topology = three_powers.apply_three_powers_fanout(
            "benchmark evidence",
            routes,
            active_layer="earth",
            topology_hexagram=(1, 0, 1, 0, 1, 0),
        )

        self.assertEqual(
            [candidate["route_id"] for candidate in baseline["ranked_candidates"]],
            [candidate["route_id"] for candidate in with_topology["ranked_candidates"]],
        )
        self.assertEqual(baseline["selected_route_ids"], with_topology["selected_route_ids"])
        self.assertIn("broken_coupling_earth_heaven", with_topology["diagnostics"])
        self.assertEqual(with_topology["topology_diagnostics"]["authority_level"], "navigation_only")
        self.assertFalse(with_topology["topology_diagnostics"]["fact_claim_allowed"])
        self.assertFalse(with_topology["topology_diagnostics"]["ranking_weight_changes"])

if __name__ == "__main__":
    unittest.main()
