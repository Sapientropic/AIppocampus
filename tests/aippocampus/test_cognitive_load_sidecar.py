from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.recall import (
    cognitive_load_private_calibration as private_calibration,
)
from aippocampus_runtime.recall import (
    cognitive_load_sidecar as sidecar,
)


class CognitiveLoadSidecarTests(unittest.TestCase):
    def test_high_load_source_gets_bounded_boost_without_collapsing_score_reasons(self) -> None:
        high_ref = {"source_id": "thread:pitfall", "message_id": "m-high", "line": 42}
        ordinary_ref = {"source_id": "thread:ordinary", "message_id": "m-ordinary", "line": 7}
        payload = sidecar.build_cognitive_load_sidecar(
            [
                {
                    "event_id": "evt-correction",
                    "event_type": "user_correction",
                    "timestamp": "2026-06-05T00:00:00Z",
                    "source_refs": [high_ref],
                    "source_reopened": True,
                    "caution_hint_reviewed": True,
                    "caution_hint_useful": True,
                },
                {
                    "event_id": "evt-red-test",
                    "event_type": "failed_test",
                    "timestamp": "2026-06-05T00:05:00Z",
                    "source_refs": [high_ref],
                    "load_weight_reviewed": True,
                },
                {
                    "event_id": "evt-ordinary",
                    "event_type": "clarification",
                    "timestamp": "2026-06-05T00:10:00Z",
                    "source_refs": [ordinary_ref],
                },
            ],
            now="2026-06-06T00:00:00Z",
        )

        ranked = sidecar.apply_cognitive_load_boosts(
            [
                {
                    "candidate_id": "ordinary-keyword-match",
                    "source_refs": [ordinary_ref],
                    "semantic_score": 0.82,
                    "source_authority": 0.9,
                },
                {
                    "candidate_id": "expensive-debugging-pitfall",
                    "source_refs": [high_ref],
                    "semantic_score": 0.74,
                    "source_authority": 0.92,
                },
            ],
            payload,
        )

        self.assertEqual(ranked[0]["candidate_id"], "expensive-debugging-pitfall")
        self.assertLessEqual(ranked[0]["score_breakdown"]["cognitive_load_boost"], 0.16)
        self.assertIn("semantic_score", ranked[0]["score_breakdown"])
        self.assertIn("source_authority", ranked[0]["score_breakdown"])
        self.assertIn("cognitive_load_boost", ranked[0]["score_breakdown"])
        self.assertEqual(payload["metrics"]["high_load_source_reopen_rate"], 0.333333)
        self.assertEqual(payload["metrics"]["caution_hint_useful_rate"], 1.0)
        self.assertEqual(payload["metrics"]["load_weight_false_positive_rate"], 0.0)
        self.assertEqual(
            ranked[0]["cognitive_load"]["projection_boundary"],
            "routing_caution_not_affect_or_personality_truth",
        )
        self.assertIn("source_reopen_recommended", ranked[0]["cognitive_load"]["advisory_action"])

    def test_load_signal_cannot_override_weak_superseded_or_untrusted_source(self) -> None:
        ref = {"source_id": "thread:superseded", "message_id": "m-old", "line": 9}
        payload = sidecar.build_cognitive_load_sidecar(
            [
                {
                    "event_id": "evt-rollback",
                    "event_type": "rollback_or_revert",
                    "timestamp": "2026-05-25T00:00:00Z",
                    "source_refs": [ref],
                    "superseded_by_source_ref": {"source_id": "thread:newer", "message_id": "m-new"},
                }
            ],
            now="2026-06-06T00:00:00Z",
        )

        ranked = sidecar.apply_cognitive_load_boosts(
            [
                {
                    "candidate_id": "stale-high-load-source",
                    "source_refs": [ref],
                    "semantic_score": 0.91,
                    "source_authority": 0.2,
                    "source_status": "superseded",
                }
            ],
            payload,
        )

        self.assertEqual(ranked[0]["score_breakdown"]["cognitive_load_boost"], 0.0)
        self.assertEqual(ranked[0]["cognitive_load"]["advisory_action"], "refresh_sources")
        self.assertIn("source_truth_not_overridden", ranked[0]["cognitive_load"]["cannot_claim"])
        self.assertEqual(payload["metrics"]["invalidated_entry_count"], 1)

    def test_public_projection_omits_raw_paths_and_emotion_or_personality_claims(self) -> None:
        payload = sidecar.build_cognitive_load_sidecar(
            [
                {
                    "event_id": "evt-private",
                    "event_type": "failed_command",
                    "timestamp": "2026-06-05T00:00:00Z",
                    "source_refs": [
                        {
                            "source_id": "thread:private",
                            "message_id": "m-private",
                            "line": 12,
                            "path": "C:\\Users\\private\\raw-rollout.jsonl",
                        }
                    ],
                    "raw_note": "The user was stressed and has an anxious personality.",
                }
            ],
            now="2026-06-06T00:00:00Z",
        )
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertFalse(payload["privacy_boundary"]["raw_paths_emitted"])
        self.assertFalse(payload["privacy_boundary"]["emotion_or_personality_claims_emitted"])
        self.assertEqual(payload["metrics"]["overpersonalization_from_load_signal_count"], 0)
        self.assertIn("cognitive_load_as_affect_or_user_trait", payload["cannot_claim"])
        self.assertNotIn("C:\\Users\\private", encoded)
        self.assertNotIn("stressed", encoded)
        self.assertNotIn("anxious personality", encoded)

    def test_calibration_report_separates_load_routing_from_affect_truth(self) -> None:
        ref = {"source_id": "thread:calibration", "message_id": "m-load", "line": 15}
        payload = sidecar.build_cognitive_load_sidecar(
            [
                {
                    "event_id": "evt-correction",
                    "event_type": "user_correction",
                    "timestamp": "2026-06-05T00:00:00Z",
                    "source_refs": [ref],
                    "load_weight_reviewed": True,
                    "load_weight_false_positive": True,
                    "caution_hint_reviewed": True,
                    "overpersonalization_from_load_signal": True,
                    "raw_note": "The user felt overwhelmed and has an anxious personality.",
                }
            ],
            now="2026-06-06T00:00:00Z",
        )
        ranked = sidecar.apply_cognitive_load_boosts(
            [
                {
                    "candidate_id": "calibrated-load-candidate",
                    "source_refs": [ref],
                    "semantic_score": 0.7,
                    "source_authority": 0.9,
                }
            ],
            payload,
        )
        report = sidecar.build_cognitive_load_calibration_report(payload, ranked)

        self.assertEqual(report["kind"], "aippocampus_cognitive_load_calibration_report")
        self.assertEqual(report["mode"], "deterministic_public_safe_calibration")
        self.assertEqual(
            report["calibration_axes"]["routing_weight"]["status"],
            "bounded_routing_metadata",
        )
        self.assertEqual(
            report["calibration_axes"]["affect_or_personality_truth"]["status"],
            "blocked_not_inferred",
        )
        self.assertFalse(
            report["calibration_axes"]["affect_or_personality_truth"]["inference_allowed"],
        )
        self.assertEqual(
            report["calibration_axes"]["source_truth"]["status"],
            "source_authority_controls_load",
        )
        self.assertEqual(report["metrics"]["load_weight_false_positive_rate"], 1.0)
        self.assertEqual(report["metrics"]["overpersonalization_from_load_signal_count"], 1)

        readout = report["issue_readouts"]["github_575"]
        self.assertEqual(readout["calibration_report"], "deterministic_public_safe")
        self.assertEqual(readout["load_routing_weight"], "measured_as_bounded_score_delta")
        self.assertEqual(readout["affect_or_personality_truth"], "blocked_not_inferred")
        self.assertEqual(readout["private_real_history_calibration"], "not_measured")
        self.assertFalse(readout["closeout_eligible"])
        self.assertIn("private_real_history_calibration", report["cannot_claim"])

        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("overwhelmed", serialized)
        self.assertNotIn("anxious personality", serialized)
        self.assertNotIn("source_refs", serialized)

    def test_public_behavior_trace_feedback_report_measures_useful_drag_and_risk(self) -> None:
        helpful_ref = {"source_id": "public:trace-helpful", "message_id": "m-helpful", "line": 12}
        drag_ref = {"source_id": "public:trace-drag", "message_id": "m-drag", "line": 33}
        risk_ref = {
            "source_id": "public:trace-risk",
            "message_id": "m-risk",
            "line": 44,
            "path": r"C:\Users\Administrator\private\rollout.jsonl",
        }

        report = sidecar.build_public_behavior_trace_feedback_report(
            [
                {
                    "public_trace_id": "public-coding-helpful-caution",
                    "event_type": "user_correction",
                    "timestamp": "2026-06-05T00:00:00Z",
                    "source_refs": [helpful_ref],
                    "load_weight_reviewed": True,
                    "caution_hint_reviewed": True,
                    "caution_hint_useful": True,
                },
                {
                    "public_trace_id": "public-coding-irrelevant-drag",
                    "event_type": "failed_command",
                    "timestamp": "2026-06-05T00:05:00Z",
                    "source_refs": [drag_ref],
                    "load_weight_reviewed": True,
                    "load_weight_false_positive": True,
                    "irrelevant_load_drag": True,
                    "caution_hint_reviewed": True,
                    "caution_hint_useful": False,
                    "raw_note": "This public fixture should not serialize the irrelevant detour note.",
                },
                {
                    "public_trace_id": "public-coding-overpersonalization-risk",
                    "event_type": "rejected_route_retry",
                    "timestamp": "2026-06-05T00:10:00Z",
                    "source_refs": [risk_ref],
                    "load_weight_reviewed": True,
                    "overpersonalization_from_load_signal": True,
                    "raw_note": "The user is anxious and stressed.",
                },
            ],
            [
                {
                    "candidate_id": "helpful-caution-source",
                    "source_refs": [helpful_ref],
                    "semantic_score": 0.74,
                    "source_authority": 0.9,
                },
                {
                    "candidate_id": "drag-source",
                    "source_refs": [drag_ref],
                    "semantic_score": 0.78,
                    "source_authority": 0.88,
                },
            ],
            now="2026-06-06T00:00:00Z",
        )

        self.assertEqual(
            report["kind"],
            sidecar.PUBLIC_BEHAVIOR_TRACE_FEEDBACK_REPORT_KIND,
        )
        metrics = report["metrics"]
        self.assertEqual(metrics["public_behavior_trace_case_count"], 3)
        self.assertEqual(metrics["reviewed_feedback_case_count"], 3)
        self.assertEqual(metrics["helpful_caution_hint_count"], 1)
        self.assertEqual(metrics["irrelevant_load_drag_count"], 1)
        self.assertEqual(metrics["overpersonalization_from_load_signal_count"], 1)
        self.assertEqual(metrics["load_weight_false_positive_rate"], 0.333333)
        self.assertEqual(metrics["caution_hint_useful_rate"], 0.5)
        self.assertEqual(metrics["irrelevant_load_drag_rate"], 0.333333)

        outcomes = {case["feedback_outcome"] for case in report["case_summaries"]}
        self.assertEqual(
            outcomes,
            {
                "useful_caution_hint",
                "irrelevant_load_drag",
                "overpersonalization_risk",
            },
        )
        readout = report["issue_readouts"]["github_575"]
        self.assertEqual(readout["public_behavior_trace_feedback"], "measured_public_fixture")
        self.assertEqual(readout["false_positive_rate"], 0.333333)
        self.assertFalse(readout["closeout_eligible"])
        self.assertIn("live_hook_capture_quality", report["cannot_claim"])

        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("source_refs", serialized)
        self.assertNotIn("public:trace", serialized)
        self.assertNotIn("C:\\Users\\Administrator", serialized)
        self.assertNotIn("irrelevant detour note", serialized)
        self.assertNotIn("anxious", serialized)
        self.assertNotIn("stressed", serialized)

    def test_public_default_path_usefulness_report_can_keep_track_diagnostic_only(
        self,
    ) -> None:
        report = sidecar.build_public_default_path_usefulness_report(
            now="2026-06-14T00:00:00Z",
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(
            report["kind"],
            sidecar.PUBLIC_DEFAULT_PATH_USEFULNESS_REPORT_KIND,
        )
        self.assertEqual(report["status"], "validated_diagnostic_result")
        self.assertEqual(report["recommended_maturity"], "dogfood_diagnostic_only")
        self.assertEqual(report["metrics"]["case_count"], 4)
        self.assertEqual(report["metrics"]["useful_hint_count"], 1)
        self.assertEqual(report["metrics"]["wrong_route_drag_reduction_count"], 1)
        self.assertEqual(report["metrics"]["blind_deepen_reduction_count"], 1)
        self.assertEqual(report["metrics"]["no_hint_pass_count"], 2)
        self.assertEqual(report["metrics"]["default_path_regression_count"], 1)
        self.assertEqual(
            report["issue_readouts"]["github_1375"]["closeout_eligible"],
            True,
        )
        self.assertTrue(
            report["issue_readouts"]["github_575"]["diagnostic_only_recommended"]
        )
        self.assertFalse(
            report["issue_readouts"]["github_575"]["bounded_adoption_recommended"]
        )
        self.assertIn(
            "default_foreground_weighting_ready_when_regressions_exist",
            report["cannot_claim"],
        )
        self.assertFalse(report["privacy_boundary"]["raw_source_handles_emitted"])
        self.assertNotIn("public:load", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_private_history_calibration_measures_clean_source_without_leaking_text(self) -> None:
        messages = [
            {
                "message_id": "msg-private-correction",
                "turn_id": "turn-private",
                "source_id": "src-private",
                "source_line": 19,
                "timestamp": "2026-06-05T00:00:00Z",
                "role": "user",
                "text": (
                    "不对，不要再走 OAuth fallback 路线；请重新查 source。"
                    "C:\\Users\\Administrator\\secret\\private.md"
                ),
            },
            {
                "message_id": "msg-private-assistant",
                "turn_id": "turn-private",
                "source_id": "src-private",
                "source_line": 20,
                "role": "assistant",
                "text": "I will not be serialized into the calibration report.",
            },
        ]
        events = [
            {
                "event_id": "evt-private-failed-test",
                "source_id": "src-private",
                "source_line": 21,
                "timestamp": "2026-06-05T00:02:00Z",
                "hard_event_kind": "tool_call_failed",
                "event_kind": "tool_call_observed",
                "command_class": "test",
                "failure_family": "assertion_failure",
                "status": "failed",
                "source_ref": "C:\\Users\\Administrator\\secret\\rollout.jsonl#L21",
                "raw_command": "python secret_test.py",
            }
        ]

        payload = private_calibration.build_private_history_cognitive_load_calibration(
            messages,
            events,
            now="2026-06-06T00:00:00Z",
            registry_metrics={"thread_count_scanned": 1, "threads_with_signal_count": 1},
        )
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["status"], "measured_public_safe_aggregate")
        self.assertEqual(payload["input_surface"]["thread_count_scanned"], 1)
        self.assertEqual(payload["input_surface"]["threads_with_signal_count"], 1)
        self.assertGreaterEqual(payload["extraction_metrics"]["signal_event_count"], 3)
        self.assertGreater(payload["sidecar_projection"]["entry_count"], 0)
        self.assertIn(
            "user_correction",
            payload["extraction_metrics"]["signal_kind_counts"],
        )
        self.assertIn(
            "explicit_pitfall_marker",
            payload["extraction_metrics"]["signal_kind_counts"],
        )
        self.assertIn(
            "failed_test",
            payload["extraction_metrics"]["signal_kind_counts"],
        )
        readout = payload["issue_readouts"]["github_575"]
        self.assertEqual(
            readout["private_real_history_calibration"],
            "measured_public_safe_aggregate",
        )
        self.assertEqual(readout["live_hook_capture"], "not_run")
        self.assertFalse(readout["closeout_eligible"])
        self.assertNotIn(
            "private_real_history_calibration",
            payload["calibration_report"]["cannot_claim"],
        )
        self.assertIn(
            "user_visible_recall_improvement",
            payload["calibration_report"]["cannot_claim"],
        )

        self.assertFalse(payload["privacy_boundary"]["raw_private_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_source_refs_emitted"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_emitted"])
        self.assertNotIn("OAuth fallback", encoded)
        self.assertNotIn("C:\\Users\\Administrator", encoded)
        self.assertNotIn("secret_test.py", encoded)
        self.assertNotIn("rollout.jsonl", encoded)
        self.assertNotIn("I will not be serialized", encoded)

    def test_private_history_calibration_handles_no_signal_scan_without_false_closeout(
        self,
    ) -> None:
        payload = private_calibration.build_private_history_cognitive_load_calibration(
            [
                {
                    "message_id": "msg-ordinary",
                    "turn_id": "turn-ordinary",
                    "source_id": "src-ordinary",
                    "role": "user",
                    "text": "Ordinary implementation update with no load marker.",
                }
            ],
            [],
            now="2026-06-06T00:00:00Z",
            registry_metrics={"thread_count_scanned": 1},
        )

        self.assertEqual(payload["status"], "measured_no_signals")
        self.assertEqual(payload["extraction_metrics"]["signal_event_count"], 0)
        self.assertEqual(payload["sidecar_projection"]["entry_count"], 0)
        readout = payload["issue_readouts"]["github_575"]
        self.assertEqual(readout["private_real_history_calibration"], "measured_no_signals")
        self.assertFalse(readout["closeout_eligible"])

if __name__ == "__main__":
    unittest.main()
