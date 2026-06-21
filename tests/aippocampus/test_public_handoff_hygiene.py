from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

class PublicHandoffHygieneTests(unittest.TestCase):
    def test_codeowners_routes_public_review_surfaces(self) -> None:
        codeowners = REPO_ROOT / ".github" / "CODEOWNERS"
        self.assertTrue(codeowners.exists(), "public handoff needs broad CODEOWNERS routing")

        lines = [
            line.split("#", 1)[0].strip()
            for line in codeowners.read_text(encoding="utf-8").splitlines()
        ]
        entries = [line.split() for line in lines if line]
        patterns = {entry[0] for entry in entries if len(entry) >= 2}
        owners = {owner for entry in entries for owner in entry[1:]}

        self.assertTrue(any(owner.startswith("@") for owner in owners), owners)
        self.assertTrue(
            {
                "*",
                "/docs/",
                "/skills/aippocampus/",
                "/tests/aippocampus/",
                "/.github/workflows/",
                "/plugins/aippocampus/",
                "/examples/",
            }.issubset(patterns),
            patterns,
        )

    def test_pyproject_explains_intentional_package_root(self) -> None:
        lines = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        package_dir_line = next(
            index for index, line in enumerate(lines) if 'package-dir = {"" = "skills/aippocampus/scripts"}' in line
        )
        nearby_comment = "\n".join(lines[max(0, package_dir_line - 4) : package_dir_line]).lower()

        self.assertIn("installable", nearby_comment)
        self.assertIn("runtime", nearby_comment)
        self.assertIn("skills/aippocampus/scripts", nearby_comment)

    def test_contributing_names_private_anchor_and_ignored_artifact_cleanup(self) -> None:
        text = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").lower()

        self.assertIn("thread-anchors.md", text)
        self.assertIn("private local work anchor", text)
        self.assertIn("git clean -ndx", text)
        self.assertIn("dist/", text)
        self.assertIn("build/", text)
        self.assertIn(".tmp/", text)
        self.assertIn("do not delete `.aippocampus/`", text)

    def test_fresh_clone_example_runs_without_private_state(self) -> None:
        example = REPO_ROOT / "examples" / "first-move-agent-gesture" / "agent_first_move_demo.py"
        readme = example.with_name("README.md")
        self.assertTrue(readme.exists(), "fresh-clone example needs a short README")
        self.assertTrue(example.exists(), "fresh-clone example needs a runnable script")

        completed = subprocess.run(
            [sys.executable, str(example), "--json"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(completed.stdout)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["gesture"], "source_backed_continuity_gesture_v1")
        self.assertTrue(payload["no_private_data_required"])
        self.assertFalse(payload["external_api_required"])
        self.assertIn("docs/guides/public-api.md", payload["source_refs"])
        self.assertNotIn(str(REPO_ROOT), completed.stdout)

if __name__ == "__main__":
    unittest.main()
