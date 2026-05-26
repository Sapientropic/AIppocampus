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


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import subconscious_agent as agent  # noqa: E402
import subconscious_jobs as jobs  # noqa: E402
import subconscious_review as review  # noqa: E402
import subconscious_worker as worker  # noqa: E402


class CliJsonContractTests(unittest.TestCase):
    def run_main_json(self, module: object, argv: list[str]) -> tuple[int, dict]:
        stdout = io.StringIO()
        with patch.object(sys, "argv", argv), patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(stdout):
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

    def test_agent_missing_api_key_returns_json_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self.run_main_json(
                agent,
                ["subconscious_agent.py", "--registry-dir", tmp, "--json"],
            )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "missing_api_key")

    def test_review_missing_api_key_returns_json_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self.run_main_json(
                review,
                ["subconscious_review.py", "--registry-dir", tmp, "--json"],
            )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "missing_api_key")

    def test_jobs_all_samples_failed_promotes_top_level_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self.run_main_json(
                jobs,
                ["subconscious_jobs.py", "--registry-dir", tmp, "--json", "--concurrency", "1"],
            )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "missing_api_key")


if __name__ == "__main__":
    unittest.main()
