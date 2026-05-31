from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dream_one_sidedness as one_sidedness  # noqa: E402


def source_ref(line: int) -> dict[str, object]:
    return {
        "thread_key": f"session:one-sided-{line}",
        "message_id": f"msg-{line}",
        "source_line": line,
    }


def waypoint(line: int, *, upper: str = "乾", lower: str = "震", refs: bool = True) -> dict[str, object]:
    return {
        "waypoint_id": f"wp-{line}",
        "moment": f"Source-backed waypoint {line}",
        "arc": {"upper_trigram": upper, "lower_trigram": lower},
        "source_refs": [source_ref(line)] if refs else [],
        "frontier_hint": "The route keeps stressing source survival from one side.",
    }


class DreamOneSidednessTests(unittest.TestCase):
    def test_gate_on_builds_source_backed_opposite_voice_probe(self) -> None:
        journey = {
            "journey_id": "journey-one-sided",
            "current_frontier": "The journey keeps treating source survival as the only route.",
            "waypoints": [waypoint(1), waypoint(2), waypoint(3)],
        }

        gate = one_sidedness.evaluate_one_sidedness_gate(journey)
        probe = one_sidedness.build_opposite_hexagram_probe(journey)

        self.assertTrue(gate["gate_open"])
        self.assertIn("same_trigram_family_persistence", gate["reasons"])
        self.assertIsNotNone(probe)
        assert probe is not None
        self.assertEqual(probe["finding_kind"], "dream_synthesized")
        self.assertEqual(probe["dream_function"], "compensatory")
        self.assertEqual(probe["voice_id"], "opposite_hexagram_voice")
        self.assertFalse(probe["foreground_eligible"])
        self.assertEqual(len(probe["source_refs"]), 3)
        self.assertTrue(probe["counter_evidence"])
        self.assertEqual(probe["opposite_arc"]["upper_trigram"], "坤")
        self.assertEqual(probe["opposite_arc"]["lower_trigram"], "巽")
        self.assertEqual(probe["voice_boundary"]["speaks_from"], "unresolved_journey_structure")
        self.assertNotIn("user probably", str(probe).casefold())

    def test_gate_off_suppresses_voice_even_when_opposite_arc_can_be_computed(self) -> None:
        journey = {
            "journey_id": "journey-balanced",
            "current_frontier": "A mixed route with only two same-family waypoints.",
            "waypoints": [waypoint(1), waypoint(2)],
        }

        arc = one_sidedness.compute_opposite_arc(journey["waypoints"][-1]["arc"])
        gate = one_sidedness.evaluate_one_sidedness_gate(journey)
        probe = one_sidedness.build_opposite_hexagram_probe(journey)

        self.assertEqual(arc["upper_trigram"], "坤")
        self.assertFalse(gate["gate_open"])
        self.assertEqual(probe, None)
        self.assertIn("one_sidedness_gate_closed", gate["suppression_reasons"])

    def test_repeated_question_and_absent_theme_require_source_refs(self) -> None:
        journey = {
            "journey_id": "journey-question-theme",
            "current_frontier": "Questions repeat, but source refs decide whether they count.",
            "waypoints": [waypoint(1, upper="乾", lower="震"), waypoint(2, upper="离", lower="坎")],
        }
        unsourced = one_sidedness.evaluate_one_sidedness_gate(
            journey,
            active_questions=[
                {"question_id": "q-route", "question": "What angle is missing?"},
                {"question_id": "q-route", "question": "What angle is missing?"},
            ],
            theme_residue=[{"theme": "counter-perspective", "status": "absent"}],
        )
        sourced = one_sidedness.evaluate_one_sidedness_gate(
            journey,
            active_questions=[
                {"question_id": "q-route", "question": "What angle is missing?", "source_refs": [source_ref(10)]},
                {"question_id": "q-route", "question": "What angle is missing?", "source_refs": [source_ref(11)]},
            ],
            theme_residue=[
                {"theme": "counter-perspective", "status": "absent", "source_refs": [source_ref(12)]},
                {"theme": "counter-perspective", "status": "residue", "source_refs": [source_ref(13)]},
            ],
        )

        self.assertFalse(unsourced["gate_open"])
        self.assertTrue(sourced["gate_open"])
        self.assertIn("repeated_questions_without_counter_perspective", sourced["reasons"])
        self.assertIn("recurring_absent_theme_residue", sourced["reasons"])

    def test_technical_thread_does_not_create_blind_spot_without_one_sidedness(self) -> None:
        journey = {
            "journey_id": "journey-technical",
            "current_frontier": "Refactor runtime scripts into packages with compatibility shims.",
            "waypoints": [
                waypoint(1, upper="乾", lower="震"),
                waypoint(2, upper="离", lower="坎"),
                waypoint(3, upper="艮", lower="兑"),
            ],
            "labels": ["runtime", "refactor", "compatibility"],
        }

        gate = one_sidedness.evaluate_one_sidedness_gate(journey)
        probe = one_sidedness.build_opposite_hexagram_probe(journey)

        self.assertFalse(gate["gate_open"])
        self.assertEqual(probe, None)
        self.assertIn("insufficient_source_backed_one_sidedness", gate["suppression_reasons"])


if __name__ == "__main__":
    unittest.main()
