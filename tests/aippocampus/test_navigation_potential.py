from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.coding import agency_affordance as agency  # noqa: E402
from aippocampus_runtime.navigation import navigation_potential as nav  # noqa: E402
from aippocampus_runtime.navigation import repo_familiarity  # noqa: E402


def source_ref(line: int, *, thread_key: str = "session:navigation") -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": f"msg-{line}",
        "source_line": line,
        "timestamp": "2026-06-07T00:00:00Z",
    }


def repo_row(
    *,
    kind: str = "runtime_owner",
    landmark: str = "foreground hook semantic budget",
    route_terms: list[str] | None = None,
    decision_shadow: dict[str, object] | None = None,
    freshness: str = "current",
) -> dict[str, object]:
    return {
        "kind": kind,
        "landmark": landmark,
        "route_terms": route_terms or ["hook", "semantic", "budget"],
        "boundary": "Repo familiarity can route source reopen, but it is not current code truth.",
        "route": {
            "files": ["skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"],
            "tests": ["tests/aippocampus/test_aippocampus_prompt_hook.py"],
        },
        "source_refs": [{"path": "docs/architecture/runtime/cognitive-runtime-architecture.md", "line": 160}],
        "freshness": freshness,
        "invalidation": {
            "commit": "abc123",
            "files": [
                {
                    "path": "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py",
                    "sha256": "hash-hook",
                }
            ],
        },
        "why_now": "Relevant when changing hook semantic budget or prompt-hook routing.",
        "action_delta_required": "Inspect hook prompt owner before changing semantic budget.",
        "first_source_to_reopen": "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py",
        "stop_after": "Stop after prompt-hook tests confirm the budget boundary.",
        "decision_shadow": decision_shadow or {"status": "candidate", "source_thickness": "usable"},
        "do_not_use_for": ["current code claims without reopening source"],
    }


def repo_cards(*rows: dict[str, object]) -> list[dict[str, object]]:
    return repo_familiarity.build_repo_familiarity_cards(
        {"source_rows": list(rows), "repo_commit": "abc123"}
    )


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

    def test_repo_familiarity_fresh_card_offers_constructive_coding_route(self) -> None:
        packet = repo_familiarity.select_repo_familiarity_packet(
            repo_cards(repo_row()),
            task="Change prompt hook semantic budget without increasing foreground latency",
            current_fingerprints={
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py": "hash-hook"
            },
            current_commit="abc123",
        )
        projection = nav.build_navigation_potential_projection(
            repo_familiarity_cards=packet["selected_cards"],
            topic_epoch="epoch-repo-familiarity",
        )

        potential = projection["potentials"][0]

        self.assertEqual(potential["source_kind"], "source_backed_familiarity_card")
        self.assertEqual(potential["status"], "unresolved")
        self.assertEqual(potential["affordance"], "offer_next_step")
        self.assertTrue(potential["foreground_eligible"])
        self.assertEqual(potential["proposed_action"]["verb"], "offer_next_step")
        self.assertIn(
            "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py",
            potential["proposed_action"]["object"],
        )
        self.assertIn("stop after: Stop after prompt-hook tests", " ".join(potential["preconditions"]))

        affordance_map = agency.build_agency_affordance_map(
            cognitive_map_inputs=projection["agency_affordance_inputs"],
            topic_epoch="epoch-repo-familiarity",
        )
        selection = agency.select_agency_tickets(
            affordance_map,
            trigger="compaction_loss",
            topic_epoch="epoch-repo-familiarity",
        )

        ticket = selection["foreground_tickets"][0]
        self.assertEqual(ticket["intervention_level"], "offer_next_step")
        self.assertIn("reopen first source", " ".join(ticket["preconditions"]))
        self.assertIn("current code claims", " ".join(ticket["do_not_do"]))

    def test_repo_familiarity_stale_card_is_refresh_not_foreground_route(self) -> None:
        projection = nav.build_navigation_potential_projection(
            repo_familiarity_cards=repo_cards(repo_row(freshness="stale")),
            topic_epoch="epoch-repo-stale",
        )

        potential = projection["potentials"][0]

        self.assertEqual(potential["status"], "stale")
        self.assertEqual(potential["affordance"], "backstage_prepare")
        self.assertEqual(potential["proposed_action"]["verb"], "refresh_sources")
        self.assertFalse(potential["foreground_eligible"])

    def test_repo_familiarity_rejected_route_surfaces_constraint_without_overclaim(self) -> None:
        projection = nav.build_navigation_potential_projection(
            repo_familiarity_cards=repo_cards(
                repo_row(
                    kind="decision_shadow",
                    landmark="rejected registry route card",
                    route_terms=["registry", "rejected", "route"],
                    decision_shadow={
                        "status": "candidate",
                        "source_thickness": "usable",
                        "route_constraint": "rejected_route",
                    },
                )
            ),
            topic_epoch="epoch-repo-rejected",
        )

        potential = projection["potentials"][0]
        encoded = json.dumps(potential, ensure_ascii=False)

        self.assertEqual(potential["status"], "corrected")
        self.assertEqual(potential["affordance"], "surface_warning")
        self.assertEqual(potential["proposed_action"]["verb"], "warn_route")
        self.assertTrue(potential["source_refs"])
        self.assertTrue(potential["foreground_eligible"])
        self.assertNotIn("still_rejected", encoded)

    def test_repo_familiarity_non_coding_task_does_not_inject_affordance(self) -> None:
        packet = repo_familiarity.select_repo_familiarity_packet(
            repo_cards(repo_row()),
            task="Write a warm note about weekend tea",
            current_fingerprints={
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py": "hash-hook"
            },
            current_commit="abc123",
        )
        projection = nav.build_navigation_potential_projection(
            repo_familiarity_cards=packet["selected_cards"],
            topic_epoch="epoch-non-coding",
        )

        self.assertEqual(packet["selected_cards"], [])
        self.assertEqual(projection["potential_count"], 0)
        self.assertEqual(projection["agency_affordance_inputs"], [])


if __name__ == "__main__":
    unittest.main()
