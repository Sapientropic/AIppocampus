from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.cli import facade  # noqa: E402
from aippocampus_runtime.ops import uninstall  # noqa: E402


class UninstallInventoryTests(unittest.TestCase):
    def test_package_facade_resolves_top_level_uninstall_command(self) -> None:
        invocation = facade.resolve_command(["uninstall", "--dry-run", "--json"])

        self.assertEqual(invocation.command, "uninstall")
        self.assertEqual(invocation.module_name, "aippocampus_runtime.ops.uninstall")
        self.assertEqual(invocation.script_name, "uninstall.py")
        self.assertEqual(invocation.args, ["--dry-run", "--json"])

    def test_dry_run_inventory_redacts_paths_and_separates_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            registry = root / "registry"
            workspace = root / "workspace"
            (codex_home / "aippocampus-marketplace").mkdir(parents=True)
            (codex_home / "plugins" / "cache" / "aippocampus-local").mkdir(parents=True)
            (codex_home / "skills" / "aippocampus").mkdir(parents=True)
            (registry / "threads").mkdir(parents=True)
            (workspace / ".claude").mkdir(parents=True)
            (workspace / ".claude" / "settings.json").write_text("{}", encoding="utf-8")

            payload = uninstall.build_inventory(
                codex_home_path=codex_home,
                registry_dir=registry,
                cwd=workspace,
            )

        encoded = json.dumps(payload, ensure_ascii=False)
        by_id = {item["id"]: item for item in payload["artifacts"]}
        self.assertTrue(payload["dry_run"])
        self.assertTrue(by_id["codex_marketplace"]["exists"])
        self.assertFalse(by_id["codex_marketplace"]["user_data"])
        self.assertTrue(by_id["registry_root"]["user_data"])
        self.assertEqual(payload["foreground_action"]["command"], "aippocampus uninstall --purge --json")
        self.assertFalse(payload["privacy"]["local_paths_emitted"])
        self.assertNotIn(str(root), encoded)

    def test_purge_skips_registry_without_explicit_user_data_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            registry = root / "registry"
            workspace = root / "workspace"
            marketplace = codex_home / "aippocampus-marketplace"
            cache = codex_home / "plugins" / "cache" / "aippocampus-local"
            skill = codex_home / "skills" / "aippocampus"
            for path in (marketplace, cache, skill, registry, workspace):
                path.mkdir(parents=True, exist_ok=True)
            with mock.patch(
                "aippocampus_runtime.hooks.claude_code.uninstall_hooks",
                return_value={"ok": True, "changed": False},
            ):
                payload = uninstall.purge(
                    codex_home_path=codex_home,
                    registry_dir=registry,
                    cwd=workspace,
                    confirm_user_data=False,
                )

            self.assertFalse(marketplace.exists())
            self.assertFalse(cache.exists())
            self.assertFalse(skill.exists())
            self.assertTrue(registry.exists())

        self.assertIn({"id": "registry_root", "reason": "requires_confirm_user_data"}, payload["skipped"])
        self.assertFalse(payload["confirm_user_data"])
        self.assertEqual(payload["foreground_action"]["command"], "aippocampus uninstall --dry-run --json")


if __name__ == "__main__":
    unittest.main()
