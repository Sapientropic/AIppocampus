from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_docs_health as docs_health  # noqa: E402


class DocsHealthTests(unittest.TestCase):
    def test_skill_entrypoint_stays_slim_and_linked(self) -> None:
        result = docs_health.check_docs(ROOT)

        self.assertTrue(result["ok"], result["issues"])
        self.assertLessEqual(result["metrics"]["skill_lines"], docs_health.MAX_SKILL_LINES)
        self.assertLessEqual(result["metrics"]["skill_words"], docs_health.MAX_SKILL_WORDS)

    def test_private_thread_anchor_artifact_is_gitignored(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("thread-anchors.md", gitignore)


if __name__ == "__main__":
    unittest.main()
