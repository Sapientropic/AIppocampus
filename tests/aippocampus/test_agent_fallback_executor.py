from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.subconscious import (
    agent_fallback_executor,
    agent_fallback_materializer,
)


class AgentFallbackExecutorTests(unittest.TestCase):
    def test_source_backed_task_produces_materializable_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = root / "agent_fallback_tasks.jsonl"
            tasks.write_text(
                json.dumps(
                    {
                        "kind": "agent_fallback_subconscious_task",
                        "created_at": "2026-06-07T00:00:00Z",
                        "project_label": "AIppocampus",
                        "reason": "first_run",
                        "provenance": "agent_fallback",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            jobs = root / "subconscious_jobs.jsonl"
            jobs.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_executor_supported",
                        "job": "project_drift",
                        "title": "Docs lanes are now source-reopenable",
                        "summary": "The docs IA work should keep current contracts and dated ledgers separate.",
                        "recommendation": "Use the grouped docs index before broad search.",
                        "source_refs": [
                            {
                                "thread_key": "session:one",
                                "assistant_line": 12,
                                "project_label": "AIppocampus",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            results = root / "agent_fallback_results.jsonl"

            report = agent_fallback_executor.produce_agent_fallback_results(
                tasks_path=tasks,
                jobs_path=jobs,
                results_path=results,
            )
            materialized = agent_fallback_materializer.materialize_agent_fallback_results(
                results_path=results,
                jobs_path=jobs,
                output_path=root / "promotion_candidates.jsonl",
                no_write=True,
            )
            result_rows = [
                json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(report["ok"])
        self.assertTrue(report["wrote"])
        self.assertEqual(report["result_row_count"], 1)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["diagnostic_only_count"], 0)
        self.assertEqual(result_rows[0]["kind"], "aippocampus_agent_fallback_result")
        self.assertEqual(result_rows[0]["provenance"], "agent_fallback_executor")
        self.assertEqual(
            result_rows[0]["candidates"][0]["source_finding_ids"],
            ["sf_executor_supported"],
        )
        self.assertEqual(materialized["promotion_candidate_count"], 1)
        self.assertEqual(materialized["diagnostic_only_count"], 0)

    def test_unsourced_findings_stay_diagnostic_only_and_write_no_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = root / "agent_fallback_tasks.jsonl"
            tasks.write_text(
                json.dumps(
                    {
                        "kind": "agent_fallback_subconscious_task",
                        "created_at": "2026-06-07T00:00:00Z",
                        "project_label": "AIppocampus",
                        "reason": "new_turns:12",
                        "provenance": "agent_fallback",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            jobs = root / "subconscious_jobs.jsonl"
            jobs.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_executor_unsourced",
                        "job": "project_drift",
                        "summary": "No refs means the fallback agent must not create a result.",
                        "source_refs": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            results = root / "agent_fallback_results.jsonl"

            report = agent_fallback_executor.produce_agent_fallback_results(
                tasks_path=tasks,
                jobs_path=jobs,
                results_path=results,
            )

        self.assertTrue(report["ok"])
        self.assertFalse(report["wrote"])
        self.assertEqual(report["result_row_count"], 0)
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["diagnostic_only_count"], 1)
        self.assertEqual(report["rejection_reasons"], {"source_finding_without_source_refs": 1})
        self.assertFalse(results.exists())

if __name__ == "__main__":
    unittest.main()
