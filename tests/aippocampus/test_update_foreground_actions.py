from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.update import (
    agent_status_summary,
    plugin_cache,
    status_actions,
)
from aippocampus_runtime.update import cli as update_cli
from tests.aippocampus.test_update_sync import (
    provider_env,
    run_update,
    write_minimal_repo,
)


class UpdateForegroundActionTests(unittest.TestCase):
    def test_plan_surface_hooks_returns_narrow_foreground_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            registry = root / "registry"
            write_minimal_repo(repo)

            code, payload = run_update(
                "plan",
                "--surface",
                "hooks",
                "--repo-root",
                str(repo),
                "--codex-home",
                str(codex_home),
                "--no-child-check",
            )

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["mode"], "plan")
        self.assertEqual(payload["summary"]["plan_surface_filter"], ["hooks"])
        self.assertEqual(payload["summary"]["plan_scope"], "selected_surfaces")
        self.assertIn("hooks", payload["surfaces"])
        self.assertEqual(payload["summary"]["needs_action"], ["hooks"])

        stdout = StringIO()
        with patch.dict("os.environ", {"AIPPOCAMPUS_REGISTRY_DIR": str(registry)}):
            with redirect_stdout(stdout):
                compact_code = update_cli.main(
                    [
                        "plan",
                        "--surface",
                        "hooks",
                        "--repo-root",
                        str(repo),
                        "--codex-home",
                        str(codex_home),
                        "--no-child-check",
                        "--agent-json",
                    ]
                )
        compact = json.loads(stdout.getvalue())
        self.assertEqual(compact_code, 0, compact)
        self.assertEqual(compact["summary"]["plan_surface_filter"], ["hooks"])
        self.assertEqual(compact["summary"]["plan_scope"], "selected_surfaces")
        self.assertNotIn("foreground_status_cards", compact)
        surfaces = {
            action.get("surface")
            for action in [compact["foreground_action"], *compact["safe_next_actions"]]
        }
        self.assertIn("action_hints", surfaces)
        self.assertIn("hooks", surfaces)
        self.assertEqual(compact["ambient_recall"]["stage"], "installed")

    def test_agent_status_projection_distinguishes_deferred_hooks_from_missing_hooks(self) -> None:
        common = {
            "ok": True,
            "mode": "status",
            "summary": {"core_ready": True, "needs_action": [], "plan_scope": "all_surfaces"},
            "surfaces": {
                "agent_callable": {},
                "llm": {"visible_in_current_process": False, "status": "ready"},
            },
        }
        deferred = agent_status_summary.compact_agent_status_report(
            {
                **common,
                "surfaces": {
                    **common["surfaces"],
                    "hooks": {
                        "status": "deferred",
                        "operator_detail_available": True,
                        "deferred_component": "hooks_status",
                    },
                },
            },
            schema_version=1,
        )
        missing = agent_status_summary.compact_agent_status_report(
            {
                **common,
                "surfaces": {**common["surfaces"], "hooks": {"status": "missing"}},
            },
            schema_version=1,
        )

        self.assertEqual(deferred["ambient_recall"]["stage"], "installed")
        self.assertIn("hooks:deferred", deferred["ambient_recall"]["issue_codes"])
        self.assertIn("hooks_status", deferred["summary"]["deferred_components"])
        self.assertEqual(missing["ambient_recall"]["stage"], "installed")
        self.assertIn("hooks:missing", missing["ambient_recall"]["issue_codes"])
        self.assertNotIn("hooks_status", missing["summary"]["deferred_components"])

    def test_plugin_cache_recovery_splits_path_template_from_executable_command(self) -> None:
        fields = status_actions.executable_update_action_fields(
            "run `aippocampus update apply --surface plugin --plugin-marketplace-dir <path>` to refresh the local marketplace copy",
            fallback_command=status_actions.PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND,
        )

        self.assertEqual(fields["command"], status_actions.PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND)
        self.assertEqual(
            fields["command_template"],
            "aippocampus update apply --surface plugin --plugin-marketplace-dir <path>",
        )
        self.assertIn("plugin_marketplace_dir", fields["requires"])
        self.assertEqual(executable_command_violations(fields), [])

    def test_plugin_cache_status_exposes_structured_repair_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            package = root / "package"
            marketplace = root / "marketplace"
            for plugin_root in (source, package):
                manifest = plugin_root / ".codex-plugin" / "plugin.json"
                manifest.parent.mkdir(parents=True)
                manifest.write_text(
                    json.dumps({"id": "aippocampus", "version": "1.0.0"}),
                    encoding="utf-8",
                )

            payload = plugin_cache.build_plugin_cache_status(
                source_root=source,
                package_root=package,
                codex_home_path=root / "codex-home",
                marketplace_dir=marketplace,
            )

        self.assertTrue(payload["recommended_action_cards"])
        card = payload["recommended_action_cards"][0]
        self.assertEqual(card["id"], "plugin_cache_recovery")
        self.assertEqual(card["command"], status_actions.PLUGIN_CACHE_DEFAULT_REPAIR_COMMAND)
        self.assertIn("command_template", card)
        self.assertIn("plugin_marketplace_dir", card["requires"])
        self.assertEqual(executable_command_violations(payload["recommended_action_cards"]), [])

    def test_apply_dry_run_agent_json_maps_to_scoped_plan_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex-home"
            write_minimal_repo(repo)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = update_cli.main(
                    [
                        "apply",
                        "--surface",
                        "hooks",
                        "--dry-run",
                        "--repo-root",
                        str(repo),
                        "--codex-home",
                        str(codex_home),
                        "--no-child-check",
                        "--agent-json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["mode"], "plan")
        self.assertTrue(payload["write_boundary"]["no_write_happened"])
        self.assertEqual(payload["summary"]["plan_scope"], "selected_surfaces")
        self.assertEqual(payload["summary"]["plan_surface_filter"], ["hooks"])
