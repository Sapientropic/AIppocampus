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
README = REPO_ROOT / "README.md"
READINESS = REPO_ROOT / "docs" / "evidence" / "readiness" / "stage-0-5-readiness.md"


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
        self.assertIn("cache: pip", text)
        self.assertIn("cache-dependency-path: pyproject.toml", text)
        self.assertIn('python -m pip install -e ".[dev]"', text)
        self.assertIn("aippocampus hooks status --codex-home .tmp/ci-codex-home --json", text)
        self.assertIn("aippocampus hooks install --codex-home .tmp/ci-codex-home --json", text)
        self.assertIn("python -m build --sdist --wheel", text)

    def test_pr_ci_runs_macos_default_tmpdir_path_identity_gate(self) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("macos-path-identity", text)
        self.assertIn("runs-on: macos-latest", text)
        self.assertIn('python-version: "3.12"', text)
        self.assertIn("tempfile.gettempdir()", text)
        self.assertIn(".resolve()", text)
        self.assertIn("python tools/aippocampus/run_tests.py --tier fast", text)
        self.assertIn("#402", text)
        self.assertIn("#140", text)
        self.assertIn("#242", text)
        macos_job = text.split("macos-path-identity", 1)[1]
        self.assertNotIn("TMPDIR:", macos_job)
        self.assertNotIn("TEMP:", macos_job)
        self.assertNotIn("TMP:", macos_job)

    def test_readiness_docs_distinguish_ubuntu_ci_from_macos_path_gate(self) -> None:
        readme = README.read_text(encoding="utf-8")
        readiness = READINESS.read_text(encoding="utf-8")

        for text in (readme, readiness):
            self.assertIn("Ubuntu", text)
            self.assertIn("macOS", text)
            self.assertIn("default TMPDIR", text)
            self.assertIn("path-identity", text)

    def test_macos_smoke_exercises_path_identity_regressions(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("tests.aippocampus.test_path_identity", text)
        self.assertIn(
            "test_related_thread_cache_canonicalizes_workspace_fingerprint",
            text,
        )
        self.assertIn(
            "test_memory_health_runs_in_process_for_frozen_binary_entrypoints",
            text,
        )
        self.assertIn("test_memory_health_cwd_uses_canonical_identity_for_path_aliases", text)
        self.assertIn("test_prompt_hook_uses_related_cache_after_paraphrase_epoch_miss", text)

    def test_release_checklist_includes_install_build_and_macos_path_gate(self) -> None:
        text = RELEASE_CHECKLIST.read_text(encoding="utf-8")

        self.assertIn("uv run --python 3.12 python -c", text)
        self.assertIn("python -m build --sdist --wheel", text)
        self.assertIn("macOS", text)
        self.assertIn("TMPDIR", text)


if __name__ == "__main__":
    unittest.main()
