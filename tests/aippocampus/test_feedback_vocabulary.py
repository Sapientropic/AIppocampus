from __future__ import annotations

import unittest

from aippocampus_runtime.recall.feedback import vocabulary
from aippocampus_runtime.recall.feedback.outcome import build_recall_outcome_event
from aippocampus_runtime.source.agent_trace_admission import (
    behavior_training_signal_from_trace,
    classify_trace_row,
)


class FeedbackVocabularyTests(unittest.TestCase):
    def test_foreground_aliases_normalize_to_canonical_feedback_signals(self) -> None:
        self.assertEqual(vocabulary.normalize_feedback_signal("helped"), "source_reopen_success")
        self.assertEqual(vocabulary.normalize_feedback_signal("wrong_route"), "wrong_route_drag")
        self.assertEqual(vocabulary.normalize_feedback_signal("corrected"), "user_correction")
        self.assertEqual(vocabulary.normalize_feedback_signal("park"), "parked")
        self.assertEqual(vocabulary.feedback_signal_polarity("helped"), "positive")
        self.assertEqual(vocabulary.feedback_signal_polarity("wrong"), "hard_negative")
        self.assertEqual(vocabulary.feedback_signal_polarity("stale"), "parked")

    def test_active_flow_signals_have_explicit_default_deltas(self) -> None:
        missing = sorted(vocabulary.ACTIVE_FLOW_SIGNALS - set(vocabulary.DEFAULT_SIGNAL_DELTAS))

        self.assertEqual(missing, [])
        self.assertEqual(vocabulary.DEFAULT_SIGNAL_DELTAS["user_correction"], -1.0)

    def test_active_flow_signals_have_explicit_recall_outcome_policy(self) -> None:
        self.assertEqual(
            set(vocabulary.ACTIVE_FLOW_RECALL_OUTCOME_POLICY),
            vocabulary.ACTIVE_FLOW_SIGNALS,
        )
        self.assertLessEqual(
            set(vocabulary.ACTIVE_FLOW_RECALL_OUTCOME_POLICY.values()),
            vocabulary.RECALL_OUTCOME_SIGNALS,
        )
        self.assertLessEqual(
            set(vocabulary.OUTCOME_ALIASES.values()),
            vocabulary.ACTIVE_FLOW_SIGNALS,
        )

    def test_recall_outcomes_have_explicit_calibration_policy(self) -> None:
        missing = sorted(
            vocabulary.RECALL_OUTCOME_SIGNALS
            - set(vocabulary.RECALL_OUTCOME_CALIBRATION_DELTAS)
        )

        self.assertEqual(missing, [])
        self.assertGreater(vocabulary.RECALL_OUTCOME_CALIBRATION_DELTAS["user_confirmed_helpful"], 0)
        self.assertGreater(vocabulary.RECALL_OUTCOME_CALIBRATION_DELTAS["manual_search_avoided"], 0)
        self.assertLess(vocabulary.RECALL_OUTCOME_CALIBRATION_DELTAS["recall_added_noise"], 0)

    def test_recall_outcome_feedback_uses_shared_aliases(self) -> None:
        self.assertEqual(
            vocabulary.normalize_recall_outcome_signal("helped"),
            "source_reopen_success",
        )
        self.assertEqual(
            vocabulary.normalize_recall_outcome_signal("confirmed"),
            "user_confirmed_helpful",
        )
        self.assertEqual(
            vocabulary.normalize_recall_outcome_signal("wrong_route"),
            "wrong_route_drag",
        )
        self.assertEqual(
            vocabulary.normalize_recall_outcome_signal("corrected"),
            "user_correction",
        )
        self.assertEqual(vocabulary.normalize_recall_outcome_signal("unknown"), "ignored")
        event = build_recall_outcome_event(
            raw_query="where did we leave the thread?",
            run_id="run-confirmed",
            route_family="active_path",
            scoring_policy="default",
            delivered_candidates=[],
            outcome_signal="confirmed",
        )

        self.assertEqual(event["outcome_signal"], "user_confirmed_helpful")

    def test_apw_followthrough_maps_are_owned_by_shared_vocabulary(self) -> None:
        self.assertEqual(
            vocabulary.APW_FOLLOWTHROUGH_OUTCOME_TO_SIGNAL["source_helped_task"],
            "user_confirmed",
        )
        self.assertEqual(
            vocabulary.APW_FOLLOWTHROUGH_OUTCOME_TO_SIGNAL["wrong_hop"],
            "wrong_route_drag",
        )
        self.assertIn("source_helped_task", vocabulary.APW_FOLLOWTHROUGH_POSITIVE_OUTCOMES)
        self.assertIn("wrong_hop", vocabulary.APW_FOLLOWTHROUGH_NEGATIVE_OUTCOMES)

    def test_trace_admission_uses_canonical_feedback_aliases(self) -> None:
        helped_row = {
            "trace_id": "alias-helped",
            "outcome": "helped",
            "source_refs": [{"thread_key": "thread-a", "message_id": "msg-a", "line": 4}],
        }
        wrong_row = {
            "trace_id": "alias-wrong-route",
            "outcome": "wrong_route",
            "route_id": "route-a",
        }

        helped_classified = classify_trace_row(helped_row)
        helped_signal = behavior_training_signal_from_trace(helped_row)
        wrong_signal = behavior_training_signal_from_trace(wrong_row)

        self.assertEqual(helped_classified["trace_family"], "successful_recall_deepen_source_open")
        self.assertEqual(helped_signal["outcome"], "source_reopen_success")
        self.assertEqual(helped_signal["training_role"], "positive_demo")
        self.assertEqual(wrong_signal["outcome"], "wrong_route_drag")
        self.assertEqual(wrong_signal["training_role"], "hard_negative")


if __name__ == "__main__":
    unittest.main()
