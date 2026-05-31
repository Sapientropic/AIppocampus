from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGER = REPO_ROOT / "tools" / "aippocampus" / "package_windows_binary.py"


def load_packager():
    spec = importlib.util.spec_from_file_location("package_windows_binary", PACKAGER)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WindowsBinaryPackagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packager = load_packager()

    def make_repo(self, root: Path) -> None:
        scripts = root / "skills" / "aippocampus" / "scripts"
        scripts.mkdir(parents=True)
        (root / "pyproject.toml").write_text(
            "\n".join(
                [
                    "[tool.setuptools]",
                    'package-dir = {"" = "skills/aippocampus/scripts"}',
                    'packages = ["aippocampus_runtime"]',
                    'py-modules = ["aippocampus_cli", "aippocampuslib"]',
                ]
            ),
            encoding="utf-8",
        )
        (scripts / "aippocampus_cli.py").write_text("def main(): return 0\n", encoding="utf-8")
        (scripts / "aippocampuslib.py").write_text("", encoding="utf-8")
        (scripts / ".aippocampus").mkdir()
        (scripts / ".aippocampus" / "registry.json").write_text("private", encoding="utf-8")
        (root / ".aippocampus").mkdir()
        (root / "transcripts").mkdir()

    def test_build_plan_uses_script_runtime_without_private_data_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            output = Path(tmp) / "out"
            self.make_repo(repo)

            plan = self.packager.make_packaging_plan(
                repo_root=repo,
                output_root=output,
                python_executable=Path("python.exe"),
            )

            command_parts = [str(part) for part in plan.command]
            command_text = json.dumps(command_parts)
            self.assertIn("--distpath", plan.command)
            self.assertIn(str(output / "dist"), command_parts)
            self.assertIn("--workpath", plan.command)
            self.assertIn(str(output / "build"), command_parts)
            self.assertIn("--specpath", plan.command)
            self.assertIn(str(output / "spec"), command_parts)
            self.assertIn("aippocampus_scripts", command_text)
            self.assertTrue(
                any(str(output / "runtime" / "aippocampus_scripts") in part for part in command_parts)
            )
            self.assertIn("--hidden-import=aippocampus_cli", plan.command)
            self.assertIn("--hidden-import=aippocampus_runtime", plan.command)
            self.assertNotIn(str(repo / ".aippocampus"), command_text)
            self.assertNotIn(str(repo / "transcripts"), command_text)
            self.assertEqual(plan.private_data_policy["source_runtime"], "skills/aippocampus/scripts")
            self.assertEqual(plan.private_data_policy["bundled_source"], "staged runtime copy")

            self.packager.stage_runtime_scripts(plan)
            self.assertTrue((output / "runtime" / "aippocampus_scripts" / "aippocampus_cli.py").is_file())
            self.assertFalse((output / "runtime" / "aippocampus_scripts" / ".aippocampus").exists())
            self.assertTrue(self.packager.private_data_guard(plan)["ok"])

    def test_entrypoint_runs_child_scripts_in_process_when_frozen(self) -> None:
        entrypoint = self.packager.render_binary_entrypoint()

        self.assertIn("import runpy", entrypoint)
        self.assertIn("aippocampus_scripts", entrypoint)
        self.assertIn("aippocampus_cli.run_script = _run_script_in_process", entrypoint)
        self.assertIn("runpy.run_path", entrypoint)

    def test_dry_run_json_does_not_claim_artifact_smoke_or_python_free_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            output = Path(tmp) / "out"
            self.make_repo(repo)

            result = self.packager.run_packaging(
                repo_root=repo,
                output_root=output,
                dry_run=True,
                require_pyinstaller=False,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(result["artifact_smoke_passed"])
        self.assertFalse(result["python_free_support_claimed"])
        self.assertIsNone(result["artifact"])
        self.assertTrue(result["private_data_guard"]["ok"])

    def test_windows_smoke_matrix_covers_representative_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            output = Path(tmp) / "out"
            self.make_repo(repo)
            clean_source = repo / "examples" / "public-memory-bundle" / "clean-source"
            clean_source.mkdir(parents=True)
            artifact = output / "dist" / "aippocampus.exe"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("fake", encoding="utf-8")
            plan = self.packager.make_packaging_plan(repo_root=repo, output_root=output)

            calls: list[list[str]] = []

            def fake_run(args: list[str], **kwargs: object) -> object:
                calls.append(args)
                command_args = args[1:]

                class Proc:
                    returncode = 1 if command_args[:2] == ["sync", "status"] else 0
                    stdout = (
                        '{"ok":false,"manifest_exists":false}'
                        if command_args[:2] == ["sync", "status"]
                        else json.dumps({"ok": True, "path": str(repo)})
                        if (
                            "--json" in command_args
                            or command_args[:2] == ["mcp", "list-tools"]
                            or command_args[:2] == ["onboard", "--status"]
                        )
                        else "usage: aippocampus"
                    )
                    stderr = ""

                return Proc()

            with patch.object(self.packager.subprocess, "run", side_effect=fake_run):
                smoke = self.packager._run_smoke(artifact, plan)

        smoke_by_name = {item["name"]: item for item in smoke}
        self.assertEqual(
            set(smoke_by_name),
            {
                "help",
                "health_help",
                "search_public_bundle",
                "mcp_list_tools",
                "onboard_status",
                "sync_empty_status",
                "hooks_status",
            },
        )
        self.assertTrue(all(item["ok"] for item in smoke))
        self.assertEqual(smoke_by_name["sync_empty_status"]["expected_returncodes"], [1])
        self.assertNotIn(str(repo), smoke_by_name["search_public_bundle"]["stdout_preview"])


if __name__ == "__main__":
    unittest.main()
