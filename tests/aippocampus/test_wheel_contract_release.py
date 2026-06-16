from __future__ import annotations

import json
import sys
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "aippocampus" / "release"))

import check_wheel_contract as wheel_contract  # noqa: E402

PYPROJECT = REPO_ROOT / "pyproject.toml"
RELEASE_CHECKLIST = REPO_ROOT / "docs" / "guides" / "setup" / "release-checklist.md"
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-agent-discovery.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "aippocampus-ci.yml"


class WheelContractReleaseTests(unittest.TestCase):
    def test_public_import_matrix_covers_documented_runtime_owners(self) -> None:
        modules = set(wheel_contract.PUBLIC_IMPORT_MODULES)

        for module in (
            "aippocampus_runtime.artifacts.export_bundle",
            "aippocampus_runtime.artifacts.import_bundle",
            "aippocampus_runtime.cli.facade",
            "aippocampus_runtime.config.registry",
            "aippocampus_runtime.hooks.install_prompt",
            "aippocampus_runtime.hooks.install_lifecycle",
            "aippocampus_runtime.knowledge.answer_gate",
            "aippocampus_runtime.knowledge.schema",
            "aippocampus_runtime.mcp.server",
            "aippocampus_runtime.onboarding.facade",
            "aippocampus_runtime.ops.storage_governance",
            "aippocampus_runtime.registry.api",
            "aippocampus_runtime.recall.why_cli",
            "aippocampus_runtime.source.clean_source",
            "aippocampus_runtime.source.search",
            "aippocampus_runtime.sync.bundle",
            "aippocampus_runtime.sync.encrypted.admin",
            "aippocampus_runtime.sync.object_storage.cli",
            "aippocampus_runtime.update.cli",
            "aippocampus_runtime.vault.dashboard",
            "conversation_sources.generic_jsonl",
        ):
            self.assertIn(module, modules)

    def test_pyproject_packages_cover_public_import_owners(self) -> None:
        pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        packages = set(pyproject["tool"]["setuptools"]["packages"])
        owners = {
            wheel_contract.package_owner_for_module(module)
            for module in wheel_contract.PUBLIC_IMPORT_MODULES
        }

        self.assertEqual(sorted(owners - packages), [])

    def test_fresh_env_defaults_to_isolated_no_live_provider_config(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(
                "os.environ",
                {
                    "PATH": "test-path",
                    "AIPPOCAMPUS_OBJECT_STORE_URL": "https://example.invalid",
                    "AIPPOCAMPUS_SEMANTIC_GATE": "on",
                    "DEEPSEEK_API_KEY": "secret",
                    "PYTHONPATH": "source-tree",
                },
                clear=True,
            ):
                env = wheel_contract.fresh_env(
                    root / "work",
                    root / "repo",
                    include_live_provider=False,
                )

        self.assertEqual(env["PATH"], "test-path")
        self.assertNotIn("AIPPOCAMPUS_OBJECT_STORE_URL", env)
        self.assertNotIn("AIPPOCAMPUS_SEMANTIC_GATE", env)
        self.assertNotIn("DEEPSEEK_API_KEY", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertIn(str(root / "work"), env["AIPPOCAMPUS_REGISTRY_DIR"])

    def test_wheel_contract_checks_release_issue_surfaces(self) -> None:
        self.assertIn("recall_context", wheel_contract.EXPECTED_MCP_TOOLS)
        self.assertIn("recall_deepen", wheel_contract.EXPECTED_MCP_TOOLS)
        self.assertIn(("import", "conversation", "--help"), wheel_contract.PUBLIC_CLI_HELP_COMMANDS)
        self.assertIn(("hooks", "lifecycle", "--help"), wheel_contract.PUBLIC_CLI_HELP_COMMANDS)
        self.assertEqual(wheel_contract.CONTRACT_QUERY, "peppercorn continuity phrase")

        source = Path(wheel_contract.__file__).read_text(encoding="utf-8")
        for required in (
            "--no-index",
            "--no-deps",
            "MINIMAL_ENV_ALLOWLIST",
            "doctor",
            "config",
            "dashboard_v2.css",
            "dashboard_v2.js",
            "generic-jsonl",
            "register-source",
            "recall_context",
            "recall_deepen",
            "hooks",
            "install",
            "uninstall",
            "AIPPOCAMPUS_REGISTRY_DIR",
            "PYTHONPATH",
            "source_tree_modules",
        ):
            self.assertIn(required, source)

    def test_mcp_tool_contract_uses_full_json_catalog(self) -> None:
        calls: list[list[str]] = []
        payload = {"tools": [{"name": name} for name in wheel_contract.EXPECTED_MCP_TOOLS]}

        class Proc:
            returncode = 0
            stdout = json.dumps(payload)
            stderr = ""

        def fake_run_command(command: list[str], **_: object) -> Proc:
            calls.append(command)
            return Proc()

        with TemporaryDirectory() as tmp, patch.object(
            wheel_contract,
            "run_command",
            side_effect=fake_run_command,
        ):
            checks: list[wheel_contract.Check] = []
            wheel_contract.check_mcp_tools(
                Path(tmp) / "venv",
                Path(tmp),
                {},
                checks,
            )

        self.assertEqual(calls[0][1:], ["mcp", "list-tools", "--json"])
        self.assertEqual(checks[0].status, "pass")

    def test_release_docs_and_workflows_run_fresh_wheel_contract(self) -> None:
        checklist = RELEASE_CHECKLIST.read_text(encoding="utf-8")
        publish_workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        ci_workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        for text in (checklist, publish_workflow, ci_workflow):
            self.assertIn("tools/aippocampus/release/check_wheel_contract.py", text)
        self.assertIn("--wheel dist/*.whl --json", publish_workflow)
        self.assertIn("--wheel dist/*.whl --json", ci_workflow)


if __name__ == "__main__":
    unittest.main()
