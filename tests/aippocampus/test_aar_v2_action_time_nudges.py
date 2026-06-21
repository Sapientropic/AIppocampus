from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.reflection.aar_v2 import (
    AAR_V2_REPORT_KIND,
    build_aar_v2_report,
    match_action_time_nudges,
    summarize_feedback_metrics,
)


class AARV2ActionTimeNudgeTests(unittest.TestCase):
    def test_report_proposes_source_claim_record_without_raw_private_text(self) -> None:
        report = build_aar_v2_report(
            [
                {
                    "kind": "source_backed_postmortem",
                    "pattern_id": "weak-memory-claim",
                    "summary": "Agent almost made a profile claim from scent only.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [
                        {
                            "source_id": "clean:postmortem",
                            "message_id": "m1",
                            "thread_key": "E:" + "\\private\\thread.jsonl",
                        }
                    ],
                    "counterfactual": "Reopening source would have prevented the unsupported claim.",
                    "prompt": "raw prompt text should not be serialized",
                    "path": "E:" + "\\private\\thread.jsonl",
                },
                {
                    "kind": "model_guess",
                    "summary": "Looks plausible, but no source refs.",
                    "action_class": "specific_memory_source_claim",
                },
            ]
        )

        self.assertEqual(report["kind"], AAR_V2_REPORT_KIND)
        self.assertTrue(report["no_write"])
        self.assertEqual(report["candidate_count"], 1)
        candidate = report["candidate_records"][0]
        self.assertEqual(candidate["action_class"], "specific_memory_source_claim")
        self.assertEqual(candidate["trigger"]["claim_support_levels"], ["scent", "candidate", "dream"])
        self.assertTrue(candidate["advisory_only"])
        self.assertFalse(candidate["can_support_factual_claim"])
        self.assertEqual(candidate["counterfactual_hypothesis"]["status"], "provisional")
        self.assertEqual(candidate["source_refs"][0]["source_id"], "clean:postmortem")
        self.assertIn("<redacted:local-path>", candidate["source_refs"][0]["thread_key"])

        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw prompt text", serialized)
        self.assertNotIn("private\\thread", serialized)

    def test_action_time_nudge_fires_for_specific_claim_from_weak_context_only(self) -> None:
        report = build_aar_v2_report(
            [
                {
                    "kind": "explicit_correction",
                    "pattern_id": "claim-before-source",
                    "summary": "Specific memory claims from scent need source reopen.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [{"source_id": "clean:correction", "message_id": "m2"}],
                }
            ]
        )
        records = report["candidate_records"]

        weak_match = match_action_time_nudges(
            records,
            {
                "action_class": "specific_memory_source_claim",
                "support_level": "scent",
                "specific_memory_claim": True,
                "visible_context_has_source": False,
                "estimated_reopen_tool_calls": 2,
            },
        )
        visible_source_match = match_action_time_nudges(
            records,
            {
                "action_class": "specific_memory_source_claim",
                "support_level": "scent",
                "specific_memory_claim": True,
                "visible_context_has_source": True,
            },
        )
        low_risk_match = match_action_time_nudges(
            records,
            {
                "action_class": "routine_summary",
                "support_level": "scent",
                "specific_memory_claim": False,
                "visible_context_has_source": False,
            },
        )

        self.assertEqual(weak_match["nudge_count"], 1)
        nudge = weak_match["nudges"][0]
        self.assertEqual(nudge["recommended_action"], "reopen_source_before_specific_claim")
        self.assertTrue(nudge["advisory_only"])
        self.assertFalse(nudge["can_support_factual_claim"])
        self.assertEqual(nudge["evidence_boundary"], "nudge_routes_attention_not_truth")
        self.assertEqual(nudge["counterfactual_hypothesis"]["status"], "provisional")
        self.assertEqual(nudge["nudge_cost"]["estimated_tool_calls"], 2)
        self.assertEqual(weak_match["metrics"]["prevented_failure_signal_count"], 1)
        self.assertEqual(visible_source_match["nudge_count"], 0)
        self.assertEqual(low_risk_match["nudge_count"], 0)

    def test_counterfactual_requires_supporting_evidence_before_status_upgrade(self) -> None:
        unsupported = build_aar_v2_report(
            [
                {
                    "kind": "source_backed_postmortem",
                    "pattern_id": "unsupported-counterfactual",
                    "summary": "A model-only counterfactual should stay provisional.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [{"source_id": "clean:postmortem", "message_id": "m3"}],
                    "counterfactual_support": [{"kind": "model_simulation", "source_refs": []}],
                }
            ]
        )["candidate_records"][0]
        supported = build_aar_v2_report(
            [
                {
                    "kind": "source_backed_postmortem",
                    "pattern_id": "supported-counterfactual",
                    "summary": "Source reopen confirmed the nudge changed outcome.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [{"source_id": "clean:postmortem", "message_id": "m4"}],
                    "counterfactual_support": [
                        {
                            "kind": "source_reopen",
                            "source_refs": [{"source_id": "clean:reopen", "message_id": "m5"}],
                        }
                    ],
                }
            ]
        )["candidate_records"][0]

        self.assertEqual(unsupported["counterfactual_hypothesis"]["status"], "provisional")
        self.assertEqual(supported["counterfactual_hypothesis"]["status"], "supported")
        self.assertEqual(
            supported["counterfactual_hypothesis"]["supporting_evidence_kinds"],
            ["source_reopen"],
        )
        self.assertTrue(supported["counterfactual_hypothesis"]["still_not_causal_truth"])

    def test_stale_unsupported_or_rejected_review_rows_do_not_become_nudges(self) -> None:
        report = build_aar_v2_report(
            [
                {
                    "kind": "source_backed_postmortem",
                    "review_status": "stale",
                    "pattern_id": "stale-row",
                    "summary": "Old source claim pattern that no longer applies.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [{"source_id": "clean:old", "message_id": "m6"}],
                },
                {
                    "kind": "source_backed_postmortem",
                    "review_status": "unsupported",
                    "pattern_id": "unsupported-row",
                    "summary": "Looks plausible but the review did not support it.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [{"source_id": "clean:unsupported", "message_id": "m7"}],
                },
                {
                    "kind": "source_backed_postmortem",
                    "review_status": "rejected",
                    "pattern_id": "rejected-row",
                    "summary": "Reviewer rejected this adjustment.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [{"source_id": "clean:rejected", "message_id": "m8"}],
                },
                {
                    "kind": "source_backed_postmortem",
                    "review_status": "accepted",
                    "pattern_id": "accepted-row",
                    "summary": "Accepted adjustment can advise source reopen.",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [{"source_id": "clean:accepted", "message_id": "m9"}],
                },
            ]
        )

        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["ignored_count"], 3)
        self.assertEqual(report["candidate_records"][0]["pattern_id"], "accepted-row")

    def test_feedback_metrics_feed_later_keep_demote_without_mutating_source(self) -> None:
        metrics = summarize_feedback_metrics(
            [
                {
                    "feedback": "useful",
                    "prevented_failure_signal": True,
                    "nudge_cost": {"tool_calls": 2, "tokens": 80},
                    "source_refs": [{"source_id": "clean:outcome", "message_id": "m6"}],
                },
                {
                    "feedback": "ignored",
                    "nudge_cost": {"tool_calls": 1, "tokens": 30},
                    "source_refs": [{"source_id": "clean:outcome", "message_id": "m7"}],
                },
                {
                    "feedback": "false_positive",
                    "nudge_cost": {"tool_calls": 1, "tokens": 20},
                    "source_refs": [{"source_id": "clean:outcome", "message_id": "m8"}],
                },
            ]
        )

        self.assertEqual(metrics["feedback_count"], 3)
        self.assertEqual(metrics["useful_nudge_count"], 1)
        self.assertEqual(metrics["ignored_nudge_count"], 1)
        self.assertEqual(metrics["false_positive_nudge_count"], 1)
        self.assertEqual(metrics["prevented_failure_signal_count"], 1)
        self.assertEqual(metrics["nudge_cost"]["tool_calls"], 4)
        self.assertEqual(metrics["nudge_cost"]["tokens"], 130)
        self.assertAlmostEqual(metrics["false_positive_nudge_rate"], 1 / 3)
        self.assertFalse(metrics["clean_source_mutation"])
        self.assertFalse(metrics["truth_status_changed"])

if __name__ == "__main__":
    unittest.main()
