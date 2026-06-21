from __future__ import annotations

import unittest

from aippocampus_runtime.recall.associative_path_source_shape import (
    build_associative_path_source_shape,
)


def source_ref(suffix: str = "one") -> dict[str, object]:
    return {
        "thread_key": "thread:apw",
        "source_id": f"src:{suffix}",
        "message_id": f"msg:{suffix}",
        "line": 12,
    }


class AssociativePathSourceShapeTests(unittest.TestCase):
    def test_private_apw_candidate_blocks_before_foreground_projection(self) -> None:
        shaped = build_associative_path_source_shape(
            {
                "route_id": "route:private",
                "scope_bucket": "user_private",
                "freshness": "current",
            },
            refs=[source_ref("private")],
        )

        projection = shaped["projection"]

        self.assertEqual(projection["route_posture"], "blocked")
        self.assertEqual(projection["action_grammar"], "ignore_or_blocked")
        self.assertIn("boundary_requires_review", projection["risk_flags"])
        self.assertEqual(shaped["descriptor"]["dominant_guard"]["guard"], "privacy_boundary")

    def test_unknown_freshness_stays_shadowed_with_currentness_recheck(self) -> None:
        shaped = build_associative_path_source_shape(
            {
                "route_id": "route:unknown-freshness",
                "scope_bucket": "project",
                "freshness": "unknown",
            },
            refs=[source_ref("unknown")],
        )

        projection = shaped["projection"]

        self.assertEqual(projection["route_posture"], "shadowed")
        self.assertEqual(projection["action_grammar"], "direction_with_ref")
        self.assertIn("freshness_unknown", projection["triage_rank_reason_codes"])
        self.assertIn("check_currentness", projection["risk_flags"])
        self.assertEqual(shaped["guard_inputs"]["freshness"], "unknown")


if __name__ == "__main__":
    unittest.main()
