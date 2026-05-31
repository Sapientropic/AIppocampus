from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "macos-install-smoke.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "aippocampus-ci.yml"
INSTALL_GUIDE = REPO_ROOT / "docs" / "guides" / "install-guide.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
RELEASE_CHECKLIST = REPO_ROOT / "docs" / "guides" / "release-checklist.md"


class MacOSInstallSmokeWorkflowTests(unittest.TestCase):
    def test_workflow_is_manual_macos_install_smoke_without_secrets(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("name: macOS Install Smoke", text)
        self.assertRegex(text, r"(?m)^on:\n\s+workflow_dispatch:")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("runs-on: ${{ inputs.runner-label }}", text)
        self.assertIn("macos-latest", text)
        self.assertIn("actions/setup-python", text)
        self.assertIn("python -m pip install -e .", text)
        self.assertIn("aippocampus --help", text)
        self.assertIn("aippocampus mcp list-tools", text)
        self.assertIn("tools/aippocampus/docs/check_docs_health.py --json", text)
        self.assertIn("tests.aippocampus.test_run_tests_tiers", text)
        self.assertIn("actions/upload-artifact@v7", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("runner.temp", text)

    def test_documentation_explains_windows_side_trigger(self) -> None:
        text = INSTALL_GUIDE.read_text(encoding="utf-8")

        self.assertIn("### Remote macOS install smoke", text)
        self.assertIn("gh workflow run macos-install-smoke.yml", text)
        self.assertIn("gh run watch", text)

        workflow_ref = re.escape(".github/workflows/macos-install-smoke.yml")
        self.assertRegex(text, workflow_ref)

    def test_setuptools_package_data_keeps_dotted_package_name_literal(self) -> None:
        text = PYPROJECT.read_text(encoding="utf-8")

        self.assertIn('"aippocampus_runtime.vault" = [', text)
        self.assertNotIn("\naippocampus_runtime.vault = [", text)

    def test_pr_ci_exercises_editable_install_and_build_metadata(self) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("python -m pip install ruff mypy coverage build", text)
        self.assertIn("python -m pip install -e .", text)
        self.assertIn("python -m build --sdist --wheel", text)

    def test_release_checklist_includes_install_build_and_macos_path_gate(self) -> None:
        text = RELEASE_CHECKLIST.read_text(encoding="utf-8")

        self.assertIn("uv run --python 3.12 python -c", text)
        self.assertIn("python -m build --sdist --wheel", text)
        self.assertIn("macOS", text)
        self.assertIn("TMPDIR", text)


if __name__ == "__main__":
    unittest.main()
