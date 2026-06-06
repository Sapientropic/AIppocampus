from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.subconscious import agent_fallback_materializer  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    fake_test_windows_path,
)


class AgentFallbackMaterializerTests(unittest.TestCase):
    def test_rejects_fallback_candidates_without_source_backed_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root / "subconscious_jobs.jsonl"
            jobs.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_supported",
                        "job": "project_drift",
                        "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            results = root / "agent_fallback_results.jsonl"
            results.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_agent_fallback_result",
                        "candidates": [
                            {
                                "candidate_type": "project_memory",
                                "title": "Unsupported fallback",
                                "summary": "Agent synthesis without a source-finding join.",
                                "confidence": 0.99,
                                "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = agent_fallback_materializer.materialize_agent_fallback_results(
                results_path=results,
                jobs_path=jobs,
                output_path=root / "promotion_candidates.jsonl",
                no_write=True,
            )

        self.assertEqual(report["promotion_candidate_count"], 0)
        self.assertEqual(report["diagnostic_only_count"], 1)
        self.assertIn("missing_source_finding_ids", report["rejection_reasons"])
        self.assertFalse(report["wrote"])

    def test_rejects_fallback_candidates_with_partly_unresolved_source_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root / "subconscious_jobs.jsonl"
            jobs.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_supported",
                        "job": "project_drift",
                        "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            results = root / "agent_fallback_results.jsonl"
            results.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_agent_fallback_result",
                        "candidate": {
                            "candidate_type": "project_memory",
                            "title": "Mixed evidence",
                            "summary": "One real finding plus one invented id must not pass.",
                            "confidence": 0.82,
                            "source_finding_ids": ["sf_supported", "sf_missing"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = agent_fallback_materializer.materialize_agent_fallback_results(
                results_path=results,
                jobs_path=jobs,
                output_path=root / "promotion_candidates.jsonl",
                no_write=True,
            )

        self.assertEqual(report["promotion_candidate_count"], 0)
        self.assertEqual(report["diagnostic_only_count"], 1)
        self.assertEqual(
            report["rejection_reasons"],
            {"unresolved_source_finding_ids": 1},
        )

    def test_rejects_resolved_findings_without_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root / "subconscious_jobs.jsonl"
            jobs.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_unsupported",
                        "job": "project_drift",
                        "source_refs": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            results = root / "agent_fallback_results.jsonl"
            results.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_agent_fallback_result",
                        "candidate": {
                            "candidate_type": "project_memory",
                            "title": "Resolved but unsourced",
                            "summary": "A known finding id without refs is still not source-backed.",
                            "confidence": 0.82,
                            "source_finding_ids": ["sf_unsupported"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = agent_fallback_materializer.materialize_agent_fallback_results(
                results_path=results,
                jobs_path=jobs,
                output_path=root / "promotion_candidates.jsonl",
                no_write=True,
            )

        self.assertEqual(report["promotion_candidate_count"], 0)
        self.assertEqual(report["diagnostic_only_count"], 1)
        self.assertEqual(
            report["rejection_reasons"],
            {"source_finding_without_source_refs": 1},
        )

    def test_rejects_partly_sourced_joined_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root / "subconscious_jobs.jsonl"
            jobs.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_supported",
                        "job": "project_drift",
                        "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_unsourced",
                        "job": "project_drift",
                        "source_refs": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            results = root / "agent_fallback_results.jsonl"
            results.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_agent_fallback_result",
                        "candidate": {
                            "candidate_type": "project_memory",
                            "title": "Partly sourced",
                            "summary": "All joined findings must be source-backed.",
                            "confidence": 0.82,
                            "source_finding_ids": ["sf_supported", "sf_unsourced"],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = agent_fallback_materializer.materialize_agent_fallback_results(
                results_path=results,
                jobs_path=jobs,
                output_path=root / "promotion_candidates.jsonl",
                no_write=True,
            )

        self.assertEqual(report["promotion_candidate_count"], 0)
        self.assertEqual(report["diagnostic_only_count"], 1)
        self.assertEqual(
            report["rejection_reasons"],
            {"source_finding_without_source_refs": 1},
        )

    def test_source_joined_fallback_candidate_uses_existing_review_output_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root / "subconscious_jobs.jsonl"
            jobs.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "fingerprint": "sf_supported",
                        "job": "project_drift",
                        "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            results = root / "agent_fallback_results.jsonl"
            results.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_agent_fallback_result",
                        "task_id": "task-public",
                        "candidates": [
                            {
                                "candidate_type": "project_memory",
                                "title": f"Provider route {FAKE_TEST_OPENAI_API_KEY}",
                                "summary": f"Review {fake_test_windows_path('fallback.txt')}",
                                "recommendation": f"Bearer {FAKE_TEST_BEARER_TOKEN}",
                                "confidence": 0.86,
                                "source_finding_ids": ["sf_supported"],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output = root / "promotion_candidates.jsonl"

            report = agent_fallback_materializer.materialize_agent_fallback_results(
                results_path=results,
                jobs_path=jobs,
                output_path=output,
            )
            raw = output.read_text(encoding="utf-8")
            row = json.loads(raw)

        self.assertTrue(report["ok"])
        self.assertTrue(report["wrote"])
        self.assertEqual(report["promotion_candidate_count"], 1)
        self.assertEqual(row["source"], "agent_fallback_subconscious_review")
        self.assertEqual(row["source_finding_ids"], ["sf_supported"])
        self.assertEqual(row["source_ref_count"], 1)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, raw)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, raw)
        self.assertNotIn(FAKE_TEST_BEARER_TOKEN, raw)
        self.assertNotIn("Provider route", raw)


if __name__ == "__main__":
    unittest.main()
