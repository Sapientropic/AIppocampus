from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.update import cli as update_cli
from tests.aippocampus.update_sync_fixtures import provider_env

REPO_ROOT = Path(__file__).resolve().parents[2]


class PromptHookLatencyStatusTests(unittest.TestCase):
    def test_update_status_keeps_stale_latency_history_out_of_current_issues(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp, provider_env():
            root = Path(tmp)
            codex_home = root / "codex-home"
            registry = root / "registry"
            hooks_json = codex_home / "hooks.json"
            telemetry_path = registry / "aippocampus_prompt_hook_skip_telemetry.json"
            telemetry_path.parent.mkdir(parents=True)
            telemetry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "updated_at": "2000-01-01T00:00:00Z",
                        "total_events": 12,
                        "hook_budget_ms_counts": {"4300": 7},
                        "latency_ms": {
                            "buckets": {
                                "hook_elapsed": {"gte_4300": 2},
                                "hook_total": {"gte_4300": 3},
                            },
                            "last": {
                                "hook_elapsed": 2597.04,
                                "hook_total": 2737.06,
                                "runtime_load": 76.2,
                                "startup_import_io": 140.02,
                            },
                        },
                        "last_event": {
                            "timestamp": "2000-01-01T00:00:00Z",
                            "decision": "skip",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            update_cli.install_prompt.install(hooks_json, timeout=5)
            stdout = StringIO()

            with patch.dict(os.environ, {"AIPPOCAMPUS_REGISTRY_DIR": str(registry)}):
                with redirect_stdout(stdout):
                    code = update_cli.main(
                        [
                            "status",
                            "--repo-root",
                            str(REPO_ROOT),
                            "--codex-home",
                            str(codex_home),
                            "--no-child-check",
                            "--agent-json",
                            "--operator-json",
                        ]
                    )

        payload = json.loads(stdout.getvalue())
        ambient = payload["ambient_recall"]
        action_surfaces = {payload["foreground_action"].get("surface")} | {
            item.get("surface") for item in payload["safe_next_actions"]
        }

        self.assertEqual(code, 0, payload)
        self.assertNotIn("prompt_hook:latency_risk", ambient["issue_codes"])
        self.assertNotIn("prompt_hook_latency", action_surfaces)
        self.assertEqual(ambient["latency_risk"]["status"], "stale_history_only")
        self.assertEqual(ambient["latency_risk"]["freshness_status"], "stale_history_only")
        self.assertEqual(
            ambient["latency_risk"]["historical_status"],
            "historical_near_timeout_seen",
        )
        self.assertNotIn("foreground_latency_red_line_violation_count", ambient["latency_risk"])
        self.assertNotIn("historical_foreground_latency_red_line_violation_count", ambient["latency_risk"])


if __name__ == "__main__":
    unittest.main()
