from __future__ import annotations

import unittest

from aippocampus_runtime.recall.prompt_recall_feedback_filter import _quiet_feedback_route_ids


class PromptRecallFeedbackFilterTests(unittest.TestCase):
    def test_mixed_feedback_uses_cumulative_pressure_for_anti_nag(self) -> None:
        negative_pressure = {
            "calibration": {
                "deltas": [
                    {
                        "route_id": "route:a",
                        "signal_counts": {
                            "wrong_route_drag": 3,
                            "source_reopen_success": 1,
                        },
                    }
                ]
            }
        }
        positive_pressure = {
            "calibration": {
                "deltas": [
                    {
                        "route_id": "route:b",
                        "signal_counts": {
                            "wrong_route_drag": 1,
                            "source_reopen_success": 3,
                        },
                    }
                ]
            }
        }

        self.assertEqual(
            _quiet_feedback_route_ids(negative_pressure),
            {"route:a", "deepen:route:a"},
        )
        self.assertEqual(_quiet_feedback_route_ids(positive_pressure), set())


if __name__ == "__main__":
    unittest.main()
