from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
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
from aippocampus_runtime.vault import sync as vault_sync  # noqa: E402
from aippocampus_runtime.vault import utils as vault_utils  # noqa: E402


class VaultDashboardAssetTests(unittest.TestCase):
    def test_vault_sync_default_json_is_read_only_and_redacts_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "memory-vault"
            with (
                mock.patch("sys.argv", ["aippocampus vault sync", "--vault", str(vault), "--json"]),
                mock.patch("sys.stdout", new_callable=StringIO) as stdout,
                mock.patch.object(vault_sync, "run_text") as run_text,
                mock.patch.object(vault_sync, "run_json") as run_json,
                mock.patch.object(vault_sync, "copy_dashboard_assets") as copy_assets,
                mock.patch.object(vault_sync, "register_current_thread") as register_thread,
            ):
                code = vault_sync.main()

            payload = json.loads(stdout.getvalue())
            encoded = json.dumps(payload, ensure_ascii=False)

            self.assertEqual(code, 0)
            self.assertFalse(vault.exists())
            run_text.assert_not_called()
            run_json.assert_not_called()
            copy_assets.assert_not_called()
            register_thread.assert_not_called()
            self.assertEqual(payload["kind"], "aippocampus_vault_sync")
            self.assertEqual(payload["mode"], "status")
            self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
            self.assertIn("foreground_action", payload)
            self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
            self.assertEqual(payload["foreground_action"]["id"], "preview_vault_sync_write_set")
            self.assertFalse(payload["privacy_boundary"]["local_paths_included"])
            self.assertNotIn(str(vault), encoded)

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
        self.assertTrue((package_assets / "aippocampus-site-mark.png").exists())
        script = (package_assets / "dashboard_v2.js").read_text(encoding="utf-8")
        css = (package_assets / "dashboard_v2.css").read_text(encoding="utf-8")

        self.assertIn("const body = document.body;", script)
        self.assertIn("--codex-pane-divider", css)
        self.assertEqual(vault_dashboard.dashboard_interaction_script_v2(), script)
        self.assertEqual(vault_dashboard.dashboard_css_v2(), css)

    def test_copy_dashboard_assets_includes_default_site_mark(self) -> None:
        with self.subTest("packaged default"):
            self.assertTrue(vault_utils.DEFAULT_SITE_MARK_SOURCE.exists())

        with tempfile.TemporaryDirectory() as tmp:
            assets = vault_utils.copy_dashboard_assets(Path(tmp))

            self.assertEqual(assets["site_mark"], "assets/site-mark.png")
            self.assertTrue((Path(tmp) / "_dashboards" / "assets" / "site-mark.png").exists())

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

    def test_html_dashboard_v2_uses_site_mark_as_favicon(self) -> None:
        rendered = vault_dashboard.html_dashboard_v2(
            thread_name="Demo thread",
            health={"ok": True},
            anchors=[],
            checkpoint_state={},
            recent_messages=[],
            vault=ROOT,
            assets={"site_mark": "assets/site-mark.png"},
        )

        self.assertIn('<link rel="icon" href="assets/site-mark.png">', rendered)
        self.assertIn("src='assets/site-mark.png'", rendered)

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

    def test_dashboard_home_starts_with_foreground_health_action(self) -> None:
        pages = packaged_dashboard.dashboard_pane_data_v2(
            health={
                "ok": True,
                "status": "ordinary recall usable",
                "product_readiness": {"ordinary_first_recall_usable": True},
                "recommended_actions": [
                    {
                        "id": "build_index",
                        "severity": "warning",
                        "command": "aippocampus maintenance --cwd . --json",
                    }
                ],
            },
            anchors=[],
            checkpoint_state={},
            recent_messages=[],
        )

        now_body = pages["now"]["body"]
        card_pos = now_body.index("foreground-action-card")
        self.assertLess(card_pos, now_body.index("Noteinfo"))
        self.assertLess(card_pos, now_body.index("从这里进入"))
        self.assertIn("ordinary_first_recall_usable", now_body)
        self.assertIn("blocks_first_recall", now_body)
        self.assertIn("blocks_exact_latest_claims", now_body)
        self.assertIn("aippocampus maintenance --cwd . --json", now_body)
        self.assertEqual(pages["now"]["body_nodes"][0]["tag"], "div")
        fields_node = next(
            child
            for child in pages["now"]["body_nodes"][0]["children"]
            if child.get("tag") == "dl"
        )
        self.assertEqual(
            fields_node["attrs"]["class"],
            "foreground-health-fields",
        )

    def test_dashboard_health_pane_exposes_foreground_decision_fields(self) -> None:
        pages = packaged_dashboard.dashboard_pane_data_v2(
            health={
                "ok": False,
                "status": "attention_needed",
                "product_readiness": {
                    "ordinary_first_recall_usable": False,
                    "freshness_degraded": True,
                },
                "recommended_actions": [
                    {
                        "id": "build_clean_source",
                        "severity": "critical",
                        "command": "aippocampus maintenance --cwd . --json",
                    }
                ],
            },
            anchors=[],
            checkpoint_state={},
            recent_messages=[],
        )

        health_body = pages["health"]["body"]
        self.assertLess(health_body.index("foreground-action-card"), health_body.index("状态："))
        self.assertIn("ordinary_first_recall_usable", health_body)
        self.assertIn("blocks_first_recall", health_body)
        self.assertIn("blocks_exact_latest_claims", health_body)
        self.assertIn("aippocampus maintenance --cwd . --json", health_body)

    def test_mobile_css_has_one_authoritative_scroll_model(self) -> None:
        css = (ASSETS / "dashboard_v2.css").read_text(encoding="utf-8")
        self.assertEqual(css.count("@media (max-width: 760px) {"), 1)
        mobile = css.split("@media (max-width: 760px) {", 1)[1]

        self.assertNotIn("body.codex-memory-dashboard {\n    height: auto !important", mobile)
        self.assertNotIn("overflow: visible !important;\n  }\n  .codex-memory-dashboard .site-body", mobile)
        self.assertRegex(
            mobile,
            r"\.codex-memory-dashboard \.render-container \{[^}]*overflow-y: auto !important;",
        )
        self.assertRegex(
            mobile,
            r"\.codex-memory-dashboard \.site-body-left-column \{[^}]*overflow-y: auto !important;",
        )
        self.assertRegex(
            mobile,
            r"\.codex-memory-dashboard \.site-body-right-column\.mobile-tools-drawer "
            r"\.site-body-right-column-inner \{[^}]*overflow-y: auto !important;",
        )
        self.assertRegex(
            mobile,
            r"\.codex-memory-dashboard \.markdown-preview-view \{[^}]*overflow: visible !important;",
        )

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
