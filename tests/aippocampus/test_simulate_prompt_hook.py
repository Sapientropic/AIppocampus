from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (SMOKE, SCRIPTS):
    sys.path.insert(0, str(_path))

import simulate_prompt_hook as smoke  # noqa: E402


class SimulatePromptHookSmokeTests(unittest.TestCase):
    def test_default_cases_use_public_synthetic_project_fixture(self) -> None:
        positive_cases = [case for case in smoke.DEFAULT_CASES if not case.get("expect_decision")]
        skip_cases = [case for case in smoke.DEFAULT_CASES if case.get("expect_decision")]

        self.assertGreaterEqual(len(positive_cases), 1)
        self.assertGreaterEqual(len(skip_cases), 1)
        for case in positive_cases:
            self.assertEqual(case.get("expect_candidate_contains"), "Project Atlas")
            self.assertIn("Project Atlas", json.dumps(case, ensure_ascii=False))
        for case in skip_cases:
            self.assertEqual(case.get("expect_decision"), "skip")

    def test_default_smoke_fixture_is_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = smoke.build_default_fixture(Path(tmp))
            result = smoke.run_cases(
                smoke.DEFAULT_CASES,
                cwd=fixture.cwd,
                registry_path=fixture.registry_path,
                registry_dir=None,
                associations_path=fixture.associations_path,
                concept_graph_path=fixture.concept_graph_path,
                use_concept_graph=True,
                search_budget=3,
            )

        self.assertEqual(result["failed"], 0, result["rows"])
        self.assertGreaterEqual(result["case_count"], 4)
        self.assertIn("evidence", {row["decision"] for row in result["rows"]})
        self.assertIn("skip", {row["decision"] for row in result["rows"]})


if __name__ == "__main__":
    unittest.main()
