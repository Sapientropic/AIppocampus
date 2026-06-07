from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.coding import agency_affordance as agency  # noqa: E402
from aippocampus_runtime.navigation import navigation_potential as nav  # noqa: E402


def source_ref(line: int, *, thread_key: str = "session:navigation") -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": f"msg-{line}",
        "source_line": line,
        "timestamp": "2026-06-07T00:00:00Z",
    }


class NavigationPotentialTests(unittest.TestCase):
    def test_superseded_route_is_suppressed_not_resurfaced(self) -> None:
        projection = nav.build_navigation_potential_projection(
            cognitive_routes=[
                {
                    "kind": "cognitive_map_route",
                    "route_id": "route-old",
                    "title": "Old recall route",
                    "summary": "The older route should not resurface as a normal recall candidate.",
                    "route_cues": ["old recall route"],
                    "source_refs": [source_ref(10)],
                }
            ],
            concept_edges=[
                {
                    "edge_type": "supersedes",
                    "src_route_id": "route-new",
                    "dst_route_id": "route-old",
                    "status": "verified",
                    "source_refs": [source_ref(11)],
                }
            ],
        )

        potential = projection["potentials"][0]

        self.assertEqual(potential["status"], "superseded")
        self.assertEqual(potential["affordance"], "silent")
        self.assertEqual(potential["action_grammar"], "ignore_or_blocked")
        self.assertFalse(potential["foreground_eligible"])
        self.assertEqual(potential["diagnostics"]["suppressed_reason"], "superseded")
        self.assertIn("concept_graph", {row["source"] for row in potential["diagnostics"]["signals"]})

    def test_unresolved_frontier_route_offers_bounded_next_step_and_feeds_agency(self) -> None:
        route_ref = source_ref(20)
        frontier_ref = source_ref(21)
        projection = nav.build_navigation_potential_projection(
            cognitive_routes=[
                {
                    "kind": "cognitive_map_route",
                    "route_id": "route-frontier",
                    "status": "unresolved",
                    "title": "Navigation potential bridge",
                    "summary": "Continue from the frontier where cognitive routes become bounded actions.",
                    "current_frontier": "Wire the source-backed route into agency as an offer, not as truth.",
                    "route_cues": ["navigation potential", "bounded actions"],
                    "source_refs": [route_ref],
                }
            ],
            journeys=[
                {
                    "kind": "aippocampus_journey",
                    "journey_id": "journey-frontier",
                    "route_id": "route-frontier",
                    "status": "camped",
                    "current_frontier": "The map needs an action-bearing next step.",
                    "current_frontier_source_refs": [frontier_ref],
                    "source_refs": [route_ref, frontier_ref],
                    "active_questions": ["How should the route become an action?"],
                }
            ],
            topic_epoch="epoch-frontier",
        )

        potential = projection["potentials"][0]

        self.assertEqual(potential["status"], "unresolved")
        self.assertEqual(potential["frontier_proximity"], "high")
        self.assertEqual(potential["affordance"], "offer_next_step")
        self.assertEqual(potential["action_grammar"], "reopenable_route")
        self.assertEqual(potential["proposed_action"]["verb"], "offer_next_step")
        self.assertTrue(potential["foreground_eligible"])
        self.assertFalse(potential["matched_terms_only"])
        self.assertFalse(potential["diagnostics"]["raw_prompt_stored"])
        self.assertIn("journey", {row["source"] for row in potential["diagnostics"]["signals"]})

        affordance_map = agency.build_agency_affordance_map(
            cognitive_map_inputs=projection["agency_affordance_inputs"],
            topic_epoch="epoch-frontier",
        )
        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="compaction_loss",
            topic_epoch="epoch-frontier",
        )

        self.assertEqual(len(selection["foreground_tickets"]), 1)
        self.assertEqual(selection["foreground_tickets"][0]["intervention_level"], "offer_next_step")
        self.assertEqual(selection["foreground_tickets"][0]["source_thickness"], "usable")

    def test_corrected_route_surfaces_warning_instead_of_repeating_old_path(self) -> None:
        projection = nav.build_navigation_potential_projection(
            cognitive_routes=[
                {
                    "kind": "cognitive_map_route",
                    "route_id": "route-corrected",
                    "title": "Ignored import route",
                    "summary": "Do not repeat the old registry import route without a state check.",
                    "route_cues": ["registry import route"],
                    "source_refs": [source_ref(30)],
                }
            ],
            correction_windows=[
                {
                    "kind": "correction_active_task_anchor",
                    "target_route_id": "route-corrected",
                    "instruction": "Warn before repeating this route.",
                    "adjudication_status": "valid_ignored",
                    "source_refs": [source_ref(31)],
                }
            ],
        )

        potential = projection["potentials"][0]

        self.assertEqual(potential["status"], "corrected")
        self.assertEqual(potential["affordance"], "surface_warning")
        self.assertEqual(potential["proposed_action"]["verb"], "warn_route")
        self.assertEqual(potential["correction_count"], 1)
        self.assertTrue(potential["foreground_eligible"])
        self.assertIn(
            "correction_window",
            {row["source"] for row in potential["diagnostics"]["signals"]},
        )

    def test_source_thin_frontier_scent_remains_non_authoritative(self) -> None:
        projection = nav.build_navigation_potential_projection(
            cognitive_routes=[
                {
                    "kind": "cognitive_map_route",
                    "route_id": "route-thin",
                    "status": "unresolved",
                    "frontier_proximity": "high",
                    "title": "Source-thin navigation scent",
                    "summary": "The words resemble an open frontier, but no source is reopenable yet.",
                    "current_frontier": "Potential next step exists only as scent.",
                    "route_cues": ["source-thin frontier"],
                }
            ]
        )

        potential = projection["potentials"][0]

        self.assertEqual(potential["source_thickness"], "thin")
        self.assertEqual(potential["action_grammar"], "direction_only")
        self.assertEqual(potential["affordance"], "backstage_prepare")
        self.assertFalse(potential["foreground_eligible"])
        self.assertTrue(potential["matched_terms_only"])
        self.assertEqual(projection["foreground_eligible_count"], 0)


if __name__ == "__main__":
    unittest.main()
