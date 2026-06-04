from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
ASSETS = SCRIPTS / "aippocampus_runtime" / "vault" / "dashboard_assets"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.vault import dashboard as packaged_dashboard  # noqa: E402
from aippocampus_runtime.vault import dashboard as vault_dashboard  # noqa: E402


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
        package_assets = SCRIPTS / "aippocampus_runtime" / "vault" / "dashboard_assets"
        self.assertEqual(packaged_dashboard._DASHBOARD_ASSET_DIR, package_assets)
        self.assertTrue((package_assets / "dashboard_v2.js").exists())
        self.assertTrue((package_assets / "dashboard_v2.css").exists())
        script = (package_assets / "dashboard_v2.js").read_text(encoding="utf-8")
        css = (package_assets / "dashboard_v2.css").read_text(encoding="utf-8")

        self.assertIn("const body = document.body;", script)
        self.assertIn("--codex-pane-divider", css)
        self.assertEqual(vault_dashboard.dashboard_interaction_script_v2(), script)
        self.assertEqual(vault_dashboard.dashboard_css_v2(), css)

    def test_dashboard_runtime_uses_structured_body_nodes(self) -> None:
        script = (ASSETS / "dashboard_v2.js").read_text(encoding="utf-8")

        self.assertIn("body_nodes", script)
        self.assertNotIn("template.innerHTML = String(bodyHtml", script)

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

    def test_json_script_escapes_html_delimiters(self) -> None:
        rendered = packaged_dashboard.json_script(
            {"body": "</script><img src=x onerror=alert(1)>", "safe": "ok"}
        )

        self.assertNotIn("</script", rendered.lower())
        self.assertNotIn("<img", rendered.lower())
        self.assertIn("\\u003c", rendered)

    def test_dashboard_pane_data_escapes_dynamic_health_counts(self) -> None:
        pages = packaged_dashboard.dashboard_pane_data_v2(
            health={
                "ok": True,
                "anchors": {"count": "<img src=x onerror=alert(1)>"},
                "rollout": {"message_count": "<svg onload=alert(2)>"},
            },
            anchors=[],
            checkpoint_state={},
            recent_messages=[],
        )

        health_body = pages["health"]["body"].lower()
        self.assertNotIn("<img", health_body)
        self.assertNotIn("<svg", health_body)
        self.assertIn("&lt;img", health_body)
        self.assertIn("&lt;svg", health_body)

    def test_dashboard_pane_data_includes_structured_body_nodes(self) -> None:
        pages = packaged_dashboard.dashboard_pane_data_v2(
            health={"ok": True},
            anchors=[],
            checkpoint_state={},
            recent_messages=[],
        )

        self.assertIsInstance(pages["now"]["body_nodes"], list)
        self.assertIsInstance(pages["health"]["body_nodes"], list)
        self.assertEqual(pages["now"]["body_nodes"][0]["tag"], "div")


if __name__ == "__main__":
    unittest.main()
