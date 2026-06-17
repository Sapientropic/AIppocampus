from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.contracts import executable_command_violations  # noqa: E402
from aippocampus_runtime.update import cli as update_cli  # noqa: E402
from aippocampus_runtime.update import status_actions  # noqa: E402
from tests.aippocampus.test_update_sync import (  # noqa: E402
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
        self.assertTrue(
            any(
                card["id"] in {"action_hint_setup", "action_hint_cache"}
                for card in compact["foreground_status_cards"]
            )
        )

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
