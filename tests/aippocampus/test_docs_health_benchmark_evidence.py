from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "aippocampus" / "docs"))

import check_docs_health as docs_health  # noqa: E402


class DocsHealthBenchmarkEvidenceTests(unittest.TestCase):
    def test_recall_navigation_readme_requires_current_state_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            evidence = docs / "evidence"
            recall_nav = evidence / "benchmarks" / "reports" / "recall-navigation"
            recall_nav.mkdir(parents=True)
            (docs / "README.md").write_text(
                "# Docs\n\n- benchmark-evidence-map.md\n",
                encoding="utf-8",
            )
            (evidence / "benchmark-evidence-map.md").write_text(
                "\n".join(docs_health.REQUIRED_BENCHMARK_EVIDENCE_MAP_TERMS) + "\n",
                encoding="utf-8",
            )
            (recall_nav / "README.md").write_text(
                "# Recall Navigation Reports\n\n## Reports\n",
                encoding="utf-8",
            )

            issues = docs_health.benchmark_evidence_map_issues(repo)

        self.assertIn("recall-navigation README missing current-state card", issues)


if __name__ == "__main__":
    unittest.main()
