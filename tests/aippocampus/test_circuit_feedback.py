from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.subconscious import circuit_feedback as feedback  # noqa: E402
from aippocampus_runtime.subconscious import jobs as job_runtime  # noqa: E402


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
        self.assertEqual(plan["scheduler_plan_changed_count"], 3)
        self.assertEqual(plan["runtime_consumer_count"], 1)
        self.assertEqual(plan["salience_decay_applied_count"], 0)
        self.assertEqual(plan["consumer_boundary"], "feedback_changes_scheduler_plan_not_source_truth")

        cyclic = feedback.dynamic_job_orchestration_plan(
            {"a": {"depends_on": ["b"]}, "b": {"depends_on": ["a"]}},
            [],
        )
        self.assertFalse(cyclic["cycle_prevention_ok"])
        self.assertTrue(cyclic["cycle_errors"])

    def test_jobs_runtime_exposes_feedback_plan_and_worker_budget_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = job_runtime.run_jobs(
                jobs=[],
                registry_path=root / "registry.json",
                timeline_path=root / "timeline.json",
                concept_graph_path=root / "graph.json",
                jobs_output_path=root / "jobs.jsonl",
                edges_output_path=root / "edges.jsonl",
                project=None,
                objective="",
                max_turns=1,
                max_steps=1,
                min_tool_steps=0,
                model="deepseek-chat",
                base_url="https://api.deepseek.com",
                api_key=None,
                max_tokens=None,
                timeout=1,
                temperature=0.0,
                dry_run=True,
                no_write=True,
            )

        self.assertTrue(result["ok"], result)
        self.assertIn("cognitive_runtime_feedback", result)
        self.assertIn("dynamic_job_orchestration", result)
        self.assertIn("semantic_subregion_budget", result)
        self.assertTrue(result["dynamic_job_orchestration"]["cycle_prevention_ok"])
        self.assertGreater(result["semantic_subregion_budget"]["job_circuit_count"], 0)


if __name__ == "__main__":
    unittest.main()
