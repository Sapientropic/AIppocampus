from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "aippocampus"
sys.path.insert(0, str(PLUGIN_ROOT))

import build_plugin_package  # noqa: E402
import smoke_plugin_install  # noqa: E402
import smoke_real_codex_host  # noqa: E402


class PluginDistributionTests(unittest.TestCase):
    def test_manifest_exposes_ui_metadata_and_mcp_without_auto_enabling_hooks(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "aippocampus")
        self.assertEqual(manifest["license"], "Apache-2.0")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertNotIn("hooks", manifest)
        self.assertIn("privacy", manifest["interface"]["longDescription"].casefold())
        self.assertIn("explicit", manifest["interface"]["longDescription"].casefold())
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)
        self.assertTrue(all(len(item) <= 128 for item in manifest["interface"]["defaultPrompt"]))

        server = mcp_config["mcpServers"]["aippocampus"]
        self.assertEqual(server["command"], "python")
        self.assertIn("./skills/aippocampus/scripts/aippocampus_mcp_server.py", server["args"])

    def test_build_package_copies_skill_mcp_config_and_hook_installers(self) -> None:
        output = REPO_ROOT / "dist" / "test-aippocampus-plugin"
        try:
            result = build_plugin_package.build_package(REPO_ROOT, output)

            built_root = Path(result["output_dir"])
            self.assertEqual(built_root, output)
            self.assertTrue((built_root / ".codex-plugin" / "plugin.json").exists())
            self.assertTrue((built_root / ".mcp.json").exists())
            self.assertTrue((built_root / "skills" / "aippocampus" / "SKILL.md").exists())
            self.assertTrue(
                (
                    built_root / "skills" / "aippocampus" / "scripts" / "aippocampus_mcp_server.py"
                ).exists()
            )
            self.assertTrue(
                (
                    built_root
                    / "skills"
                    / "aippocampus"
                    / "scripts"
                    / "install_aippocampus_prompt_hook.py"
                ).exists()
            )
            self.assertTrue(
                (
                    built_root
                    / "skills"
                    / "aippocampus"
                    / "scripts"
                    / "install_aippocampus_lifecycle_hook.py"
                ).exists()
            )
            self.assertFalse((built_root / "skills" / "aippocampus" / "__pycache__").exists())
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_build_package_refuses_to_replace_repo_external_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "existing"
            outside.mkdir()
            (outside / "keep.txt").write_text("do not delete", encoding="utf-8")

            with self.assertRaises(ValueError):
                build_plugin_package.build_package(REPO_ROOT, outside)

            self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "do not delete")

    def test_package_level_install_smoke_runs_mcp_and_uninstalls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = Path(tmp) / "plugins"
            result = smoke_plugin_install.smoke_plugin_install(REPO_ROOT, install_root)

            install_dir = Path(result["install_dir"])
            self.assertTrue(result["ok"])
            self.assertTrue(result["installed"])
            self.assertTrue(result["mcp_smoke_ok"])
            self.assertTrue(result["uninstalled"])
            self.assertFalse(install_dir.exists())
            self.assertIn("search_memory", result["mcp_tools"])
            self.assertFalse(result["hooks_auto_enabled"])

    def test_install_smoke_exercises_installed_mcp_config_as_jsonrpc_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = Path(tmp) / "plugins"
            result = smoke_plugin_install.smoke_plugin_install(REPO_ROOT, install_root)

            self.assertTrue(result["mcp_jsonrpc_smoke_ok"])
            self.assertEqual(
                result["mcp_jsonrpc_request_methods"],
                ["initialize", "notifications/initialized", "tools/list", "tools/call"],
            )
            self.assertEqual(result["mcp_jsonrpc_response_ids"], [1, 2, 3])
            self.assertIn("sync_status", result["mcp_jsonrpc_tools"])
            self.assertEqual(
                result["mcp_jsonrpc_tool_payload"]["status"], "available_requires_sync_dir"
            )
            self.assertFalse(result["mcp_jsonrpc_tool_is_error"])
            self.assertEqual(
                result["alternate_client_surface"]["kind"],
                "standalone_mcp_stdio_jsonrpc_client",
            )
            self.assertFalse(result["alternate_client_surface"]["headless_codex_app_server"])
            self.assertFalse(result["alternate_client_surface"]["interactive_desktop_ui"])
            self.assertIn(
                "tools/call:sync_status", result["alternate_client_surface"]["operations"]
            )

    def test_install_smoke_does_not_cleanup_unsafe_build_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install_root = Path(tmp) / "plugins"
            with mock.patch.object(smoke_plugin_install.shutil, "rmtree") as mocked_rmtree:
                with self.assertRaises(ValueError):
                    smoke_plugin_install.smoke_plugin_install(
                        REPO_ROOT,
                        install_root,
                        build_output=REPO_ROOT,
                    )

            self.assertFalse(mocked_rmtree.called)
            self.assertTrue(REPO_ROOT.exists())

    def test_install_smoke_rejects_external_build_output_without_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install_root = root / "plugins"
            external = root / "external-build"
            external.mkdir()
            (external / "keep.txt").write_text("keep", encoding="utf-8")

            with mock.patch.object(smoke_plugin_install.shutil, "rmtree") as mocked_rmtree:
                with self.assertRaises(ValueError):
                    smoke_plugin_install.smoke_plugin_install(
                        REPO_ROOT,
                        install_root,
                        build_output=external,
                    )

            self.assertFalse(mocked_rmtree.called)
            self.assertEqual((external / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_real_codex_smoke_marketplace_manifest_uses_codex_local_source_contract(self) -> None:
        output = REPO_ROOT / "dist" / "test-real-codex-plugin-package"
        run_id = "unit"
        marketplace_root = REPO_ROOT / ".tmp" / f"aippocampus-real-codex-marketplace-{run_id}"
        try:
            build_plugin_package.build_package(REPO_ROOT, output)
            marketplace_name, root, plugin_dir = smoke_real_codex_host.prepare_local_marketplace(
                REPO_ROOT,
                output,
                run_id,
            )
            marketplace = json.loads(
                (root / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
            )

            self.assertEqual(marketplace_name, "aippocampus-real-smoke-unit")
            self.assertEqual(root, marketplace_root)
            self.assertTrue((plugin_dir / ".codex-plugin" / "plugin.json").exists())
            self.assertEqual(
                marketplace["plugins"][0]["source"],
                {"source": "local", "path": "./plugins/aippocampus"},
            )
            self.assertEqual(
                marketplace["plugins"][0]["policy"],
                {"installation": "AVAILABLE", "authentication": "ON_USE"},
            )
        finally:
            shutil.rmtree(output, ignore_errors=True)
            shutil.rmtree(marketplace_root, ignore_errors=True)

    def test_real_codex_smoke_validator_requires_host_install_tool_call_and_cleanup(self) -> None:
        result = {
            "plugin_read_before": {"installed": False},
            "plugin_read_after_install": {
                "installed": True,
                "enabled": True,
                "mcpServers": ["aippocampus"],
                "skills": ["aippocampus:aippocampus"],
            },
            "mcp_status": {
                "tool_names": ["search_memory", "sync_status", "memory_health"],
            },
            "mcp_tool_is_error": False,
            "mcp_tool_payload": {
                "status": "available_requires_sync_dir",
                "backend": "local_folder",
                "commands": ["status", "push", "pull", "repair"],
            },
            "cleanup": {
                "plugin_uninstall_ok": True,
                "marketplace_remove_ok": True,
                "marketplace_root_exists": False,
            },
        }

        ok, failures = smoke_real_codex_host.validate_smoke(result)

        self.assertTrue(ok)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
