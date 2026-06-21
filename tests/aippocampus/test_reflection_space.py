from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.reflection import space as reflection  # noqa: E402


class ReflectionSpaceTests(unittest.TestCase):
    def make_journeys(self) -> tuple[dict, dict]:
        return reflection.fixture_journeys()

    def test_topology_renders_small_journey_graph_with_user_actions(self) -> None:
        first, second = self.make_journeys()

        topology = reflection.build_reflection_topology([first, second], topic_epoch="epoch-map")

        journey_nodes = [node for node in topology["nodes"] if node["node_type"] == "journey"]
        waypoint_nodes = [node for node in topology["nodes"] if node["node_type"] == "waypoint"]
        frontier_nodes = [node for node in topology["nodes"] if node["node_type"] == "current_frontier"]

        self.assertEqual(topology["kind"], reflection.TOPOLOGY_KIND)
        self.assertEqual(len(journey_nodes), 2)
        self.assertGreaterEqual(len(waypoint_nodes), 6)
        self.assertEqual(len(frontier_nodes), 2)
        self.assertTrue(all(node["source_refs"] for node in journey_nodes))
        self.assertIn("expand", journey_nodes[0]["available_actions"])
        self.assertIn("merge", journey_nodes[0]["available_actions"])
        self.assertIn("abandon", journey_nodes[0]["available_actions"])
        self.assertIn("revive", journey_nodes[1]["available_actions"])
        self.assertFalse(topology["interaction_contract"]["clean_source_mutation"])

    def test_merge_revive_and_abandon_feedback_are_surface_only(self) -> None:
        first, second = self.make_journeys()
        first_refs_before = list(first["source_refs"])
        feedback = [
            {
                "action": "merge",
                "journey_id": first["journey_id"],
                "merge_target": second["journey_id"],
                "source_refs": first["source_refs"][:1],
            },
            {
                "action": "abandon",
                "journey_id": first["journey_id"],
                "source_refs": first["source_refs"][:1],
            },
            {
                "action": "revive",
                "journey_id": second["journey_id"],
                "source_refs": second["source_refs"][:1],
            },
        ]

        topology = reflection.build_reflection_topology([first, second], feedback_rows=feedback)

        self.assertEqual(first["source_refs"], first_refs_before)
        self.assertGreaterEqual(len(topology["feedback_adjustments"]), 5)
        for adjustment in topology["feedback_adjustments"]:
            self.assertIn(adjustment["surface"], {"ranking", "confidence", "visibility"})
            self.assertTrue(adjustment["source_refs"])
            self.assertFalse(adjustment["clean_source_mutation"])
            self.assertFalse(adjustment["journey_mutation"])
            self.assertIn("aar_strategy", adjustment["applies_to"])

    def test_recall_effects_turning_points_and_corrections_adjust_aar_strategy(self) -> None:
        first, _ = self.make_journeys()
        feedback = [
            {
                "recall_effect": "helpful",
                "journey_id": first["journey_id"],
                "note": "The recall card changed the next question.",
                "source_refs": first["current_frontier_source_refs"],
            },
            {
                "recall_effect": "ignored",
                "journey_id": first["journey_id"],
                "note": "The nudge did not change the conversation.",
                "source_refs": first["current_frontier_source_refs"],
            },
            {
                "action": "turning_point",
                "journey_id": first["journey_id"],
                "note": "The frontier shifted after this moment.",
                "source_refs": first["current_frontier_source_refs"],
            },
            {
                "action": "user_correction",
                "journey_id": first["journey_id"],
                "note": "User corrected the map label.",
                "source_refs": first["current_frontier_source_refs"],
            },
        ]

        topology = reflection.build_reflection_topology([first], feedback_rows=feedback)
        actions = {item["feedback_action"] for item in topology["aar_strategy_adjustments"]}
        surfaces = {item["surface"] for item in topology["aar_strategy_adjustments"]}

        self.assertEqual(
            actions,
            {"recall_helpful", "recall_ignored", "turning_point", "user_correction"},
        )
        self.assertIn("ranking", surfaces)
        self.assertIn("confidence", surfaces)
        self.assertIn("visibility", surfaces)

    def test_adjudicated_dream_hypotheses_enter_reflection_as_audited_nodes(self) -> None:
        first, _ = self.make_journeys()
        dream_row = {
            "candidate_type": "dream_hypothesis",
            "candidate_key": "wm_dream_continuity",
            "review_state": "agent_adjudicated",
            "downstream_use": ["working_memory", "reflection_space"],
            "title": "Continuity dream bridge",
            "summary": "A quiet hypothesis about continuity and source reopen behavior.",
            "confidence": 0.67,
            "source_refs": first["source_refs"][:1],
            "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
            "dream_function": "amplification",
            "sensitive_use_gate": {"state": "allowed"},
            "journey_bridge_hypothesis": {
                "status": "dream_bridge_not_source_fact",
                "bridge_kind": "shared_unblock_condition",
                "source_journey_refs": [f"journey:{first['journey_id']}", "journey:other"],
                "shared_pattern": "both routes camp before replacing an old structure",
                "possible_reason": "each journey may be waiting for a reversible boundary",
                "unblock_condition": "define rollback before rebuilding",
                "falsification_cues": ["source shows an external-only blocker"],
                "foreground_use": "journey_unblock_probe_not_evidence",
            },
        }
        blocked = {
            **dream_row,
            "candidate_key": "wm_dream_blocked",
            "sensitive_use_gate": {"state": "blocked"},
        }

        topology = reflection.build_reflection_topology(
            [first],
            dream_hypotheses=[dream_row, blocked],
            topic_epoch="epoch-dream-reflection",
        )

        dream_nodes = [node for node in topology["nodes"] if node["node_type"] == "dream_hypothesis"]
        dream_edges = [edge for edge in topology["edges"] if edge["edge_type"] == "dream_hypothesis_source_overlap"]

        self.assertEqual(len(dream_nodes), 1)
        self.assertEqual(dream_nodes[0]["truth_boundary"], "adjudicated_dream_hypothesis_not_fact")
        self.assertTrue(dream_nodes[0]["source_reopen_required_for_strong_claims"])
        self.assertEqual(dream_nodes[0]["journey_bridge_hypothesis"]["status"], "dream_bridge_not_source_fact")
        self.assertIn("inspect_journey_bridge", dream_nodes[0]["available_actions"])
        self.assertEqual(len(dream_edges), 1)
        self.assertEqual(topology["ignored_dream_hypothesis_count"], 1)
        self.assertTrue(topology["interaction_contract"]["dream_hypotheses_are_interpretive_not_facts"])

    def test_unsourced_unknown_feedback_is_ignored(self) -> None:
        first, _ = self.make_journeys()

        topology = reflection.build_reflection_topology(
            [first],
            feedback_rows=[
                {
                    "action": "revive",
                    "journey_id": "missing",
                    "note": "No source refs and no target journey.",
                }
            ],
        )

        self.assertEqual(topology["feedback_adjustments"], [])
        self.assertEqual(topology["ignored_feedback_count"], 1)

    def test_fixture_smoke_declares_claim_boundaries(self) -> None:
        payload = reflection.run_fixture_smoke()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient")
        self.assertGreater(payload["metrics"]["node_count"], 0)
        self.assertIn(
            "scheduler_or_aar_runtime_enforcement",
            payload["topology"]["cannot_claim"],
        )
        self.assertEqual(
            payload["topology"]["interaction_contract"]["feedback_mutates_only"],
            ["ranking", "confidence", "visibility"],
        )
        self.assertTrue(
            payload["topology"]["interaction_contract"]["aar_or_host_must_apply_visibility_guard"]
        )
        self.assertIn(
            "foreground_ticket_selection_or_visible_context_suppression",
            payload["topology"]["cannot_claim"],
        )

    def test_default_entrypoint_is_operator_only_card_not_empty_fixture_claim(self) -> None:
        payload = reflection.default_reflection_space_card()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "operator_only_no_input")
        self.assertTrue(payload["operator_only"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(payload["foreground_action"]["id"], "run_reflection_fixture_smoke")
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(payload["safe_next_actions"], [])


if __name__ == "__main__":
    unittest.main()
