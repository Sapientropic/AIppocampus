from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.subconscious import circuit_feedback as feedback  # noqa: E402


class CircuitFeedbackTests(unittest.TestCase):
    def test_feedback_ledger_is_public_safe_and_diagnostic_only(self) -> None:
        report = feedback.build_circuit_feedback_report(
            [
                {
                    "job_id": "question_extraction",
                    "quality_outcome": "source_ref_validation_failure",
                    "severity": 4,
                    "cost_proxy": 120,
                    "source_refs": [{"source_id": "src:1", "message_id": "m1"}],
                    "raw_prompt": "PRIVATE_PROMPT should not serialize",
                },
                {
                    "job_id": "question_extraction",
                    "quality_outcome": "false_positive",
                    "severity": 2,
                    "cost_proxy": 80,
                },
            ]
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], encoded)
        self.assertEqual(len(report["rows"]), 2)
        self.assertTrue(all(row["diagnostic_only"] for row in report["rows"]))
        self.assertFalse(any(row["supports_factual_claim"] for row in report["rows"]))
        self.assertGreater(report["policy"]["microcircuit_policy"]["threshold_delta"], 0)
        self.assertIn("source_ref_review", report["policy"]["fallback_branches"])
        self.assertNotIn("PRIVATE_PROMPT", encoded)

    def test_dynamic_orchestration_adds_conditional_branches_and_prevents_cycles(self) -> None:
        rows = feedback.feedback_rows_from_reports(
            [
                {"job_id": "question_extraction", "quality_outcome": "empty_output"},
                {"job_id": "cognitive_map", "quality_outcome": "useful_routed_candidate"},
                {"job_id": "cognitive_map", "quality_outcome": "source_reopen_follow_through"},
            ]
        )
        plan = feedback.dynamic_job_orchestration_plan(
            {
                "question_extraction": {},
                "theme_emergence": {"depends_on": ["question_extraction"]},
                "cognitive_map": {},
            },
            rows,
        )

        self.assertTrue(plan["cycle_prevention_ok"], plan)
        self.assertIn(
            "frontier_marker_extraction",
            plan["plan"]["question_extraction"]["conditional_branches"],
        )
        self.assertIn(
            "pattern_completion_learning_loop_review",
            plan["plan"]["cognitive_map"]["conditional_branches"],
        )
        self.assertTrue(plan["static_depends_on_preserved"])

        cyclic = feedback.dynamic_job_orchestration_plan(
            {"a": {"depends_on": ["b"]}, "b": {"depends_on": ["a"]}},
            [],
        )
        self.assertFalse(cyclic["cycle_prevention_ok"])
        self.assertTrue(cyclic["cycle_errors"])


if __name__ == "__main__":
    unittest.main()
