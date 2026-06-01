from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import subconscious_agent as agent  # noqa: E402
import subconscious_jobs as jobs  # noqa: E402
import subconscious_review as review  # noqa: E402
import subconscious_worker as worker  # noqa: E402


class CliJsonContractTests(unittest.TestCase):
    def run_main_json(self, module: object, argv: list[str]) -> tuple[int, dict]:
        stdout = io.StringIO()
        with (
            patch.object(sys, "argv", argv),
            patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stdout(stdout),
        ):
            code = module.main()
        return code, json.loads(stdout.getvalue())

    def test_worker_missing_api_key_returns_json_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self.run_main_json(
                worker,
                ["subconscious_worker.py", "--registry-dir", tmp, "--json"],
            )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "missing_api_key")
        self.assertEqual(payload["error"]["class"], "missing_prerequisite")

    def test_agent_missing_api_key_returns_json_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self.run_main_json(
                agent,
                ["subconscious_agent.py", "--registry-dir", tmp, "--json"],
            )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "missing_api_key")
        self.assertEqual(payload["error"]["class"], "missing_prerequisite")

    def test_review_missing_api_key_returns_json_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self.run_main_json(
                review,
                ["subconscious_review.py", "--registry-dir", tmp, "--json"],
            )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "missing_api_key")
        self.assertEqual(payload["error"]["class"], "missing_prerequisite")

    def test_jobs_all_samples_failed_promotes_top_level_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self.run_main_json(
                jobs,
                ["subconscious_jobs.py", "--registry-dir", tmp, "--json", "--concurrency", "1"],
            )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "missing_api_key")
        self.assertEqual(payload["error"]["class"], "missing_prerequisite")

    def test_jobs_json_uses_public_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            private_result = {
                "ok": True,
                "job_count": 1,
                "successful_job_count": 1,
                "failure_count": 0,
                "finding_count": 1,
                "edge_count": 1,
                "partial_failure": False,
                "wrote": True,
                "jobs_output": str(Path(tmp) / "subconscious_jobs.jsonl"),
                "edges_output": str(Path(tmp) / "subconscious_edges.jsonl"),
                "cache": {"available": True, "hit_tokens": 2, "miss_tokens": 3},
                "model_route": {
                    "provider": "deepseek",
                    "base_url": "https://private-model.example/v1",
                    "api_key_env": "PRIVATE_MODEL_KEY_ENV",
                },
                "jobs": [
                    {
                        "prompt_preview": "private prompt",
                        "findings": [{"summary": "private finding"}],
                        "final_attempts": [{"content": "private final"}],
                    }
                ],
            }
            with patch.object(jobs, "run_jobs_with_config", return_value=private_result):
                code, payload = self.run_main_json(
                    jobs,
                    ["subconscious_jobs.py", "--registry-dir", tmp, "--json"],
                )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0)
        self.assertEqual(payload["job_count"], 1)
        self.assertNotIn("jobs", payload)
        self.assertNotIn("jobs_output", payload)
        self.assertNotIn("private prompt", encoded)
        self.assertNotIn("PRIVATE_MODEL_KEY_ENV", encoded)
        self.assertNotIn("private-model.example", encoded)

    def test_worker_json_uses_public_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            private_result = {
                "ok": True,
                "dry_run": True,
                "timeline": str(Path(tmp) / "project_timeline.json"),
                "output": str(Path(tmp) / "subconscious_edges.jsonl"),
                "turn_count": 2,
                "edge_count": 1,
                "prompt_preview": "private prompt preview",
                "model_route": {
                    "provider": "deepseek",
                    "base_url": "https://private-model.example/v1",
                    "api_key_env": "PRIVATE_MODEL_KEY_ENV",
                },
                "edges": [{"why": "private edge rationale"}],
            }
            with patch.object(worker, "run_worker", return_value=private_result):
                code, payload = self.run_main_json(
                    worker,
                    ["subconscious_worker.py", "--registry-dir", tmp, "--json", "--dry-run"],
                )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["turn_count"], 2)
        self.assertNotIn("prompt_preview", payload)
        self.assertNotIn("edges", payload)
        self.assertNotIn("output", payload)
        self.assertNotIn("private prompt", encoded)
        self.assertNotIn("PRIVATE_MODEL_KEY_ENV", encoded)


if __name__ == "__main__":
    unittest.main()
