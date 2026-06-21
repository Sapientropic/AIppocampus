from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

class CodeqlWorkflowTests(unittest.TestCase):
    def test_python_codeql_pr_filter_keeps_runtime_paths_scanned(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "codeql.yml").read_text(
            encoding="utf-8"
        )
        config = (REPO_ROOT / ".github" / "codeql" / "codeql-config.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("python-codeql-filter:", workflow)
        self.assertIn("needs: python-codeql-filter", workflow)
        self.assertIn("config-file: ./.github/codeql/codeql-config.yml", workflow)

        for path in (
            "skills/aippocampus/scripts",
            "tools/aippocampus",
            "plugins/aippocampus",
        ):
            self.assertIn(path, workflow)
            self.assertIn(path, config)

        self.assertIn("paths-ignore:", config)
        self.assertIn("benchmarks", config)
        self.assertIn("docs", config)
