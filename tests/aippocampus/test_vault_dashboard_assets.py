from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
ASSETS = SCRIPTS / "vault_dashboard_assets"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import vault_dashboard  # noqa: E402


class VaultDashboardAssetTests(unittest.TestCase):
    def test_public_asset_functions_delegate_to_versioned_assets(self) -> None:
        with mock.patch.object(
            vault_dashboard,
            "_load_dashboard_asset",
            side_effect=lambda filename: f"loaded:{filename}",
        ) as loader:
            self.assertEqual(
                vault_dashboard.dashboard_interaction_script_v2(),
                "loaded:dashboard_v2.js",
            )
            self.assertEqual(
                vault_dashboard.dashboard_css_v2(),
                "loaded:dashboard_v2.css",
            )

        self.assertEqual(
            [call.args for call in loader.call_args_list],
            [("dashboard_v2.js",), ("dashboard_v2.css",)],
        )

    def test_dashboard_asset_functions_return_file_contents(self) -> None:
        script = (ASSETS / "dashboard_v2.js").read_text(encoding="utf-8")
        css = (ASSETS / "dashboard_v2.css").read_text(encoding="utf-8")

        self.assertIn("const body = document.body;", script)
        self.assertIn("--codex-pane-divider", css)
        self.assertEqual(vault_dashboard.dashboard_interaction_script_v2(), script)
        self.assertEqual(vault_dashboard.dashboard_css_v2(), css)

    def test_html_dashboard_v2_inlines_asset_contents(self) -> None:
        script = (ASSETS / "dashboard_v2.js").read_text(encoding="utf-8")
        css = (ASSETS / "dashboard_v2.css").read_text(encoding="utf-8")

        rendered = vault_dashboard.html_dashboard_v2(
            thread_name="Demo thread",
            health={"ok": True},
            anchors=[],
            checkpoint_state={},
            recent_messages=[],
            vault=ROOT,
            assets={},
        )

        self.assertIn(f"<style>{css}</style>", rendered)
        self.assertIn(f"<script>{script}</script>", rendered)


if __name__ == "__main__":
    unittest.main()
