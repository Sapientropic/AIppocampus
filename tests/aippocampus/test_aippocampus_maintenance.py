from __future__ import annotations

import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import maintenance as maintenance  # noqa: E402


class AippocampusMaintenanceTests(unittest.TestCase):
    def test_degraded_report_records_failed_action_and_keeps_independent_refresh(self) -> None:
        health_calls = [
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "stale"},
                    {
                        "id": "prepare_graphify_corpus",
                        "severity": "info",
                        "reason": "index stale",
                    },
                ],
            },
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "still stale"},
                ],
            },
            {
                "ok": False,
                "recommended_actions": [
                    {"id": "build_index", "severity": "warning", "reason": "still stale"},
                ],
            },
        ]

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.navigation.cognitive_map":
                return 0, {"ok": True}, "{}", ""
            self.fail(f"unexpected JSON command: {cmd}")

        def fake_text(cmd: list[str]) -> tuple[int, str, str]:
            if module_for(cmd) == "aippocampus_runtime.recall.index_builder":
                return 3, "", "index writer locked"
            self.fail(f"unexpected text command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch.object(maintenance, "run_text_checked", side_effect=fake_text),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(
                [
                    "--cwd",
                    ".",
                    "--no-refresh-graphify",
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["maintenance_status"], "degraded")
        self.assertEqual(payload["action_failures"][0]["id"], "build_index")
        self.assertIn("index writer locked", payload["action_failures"][0]["message"])
        self.assertIn(
            "build_cognitive_map",
            [item["id"] for item in payload["action_results"]],
        )
        self.assertEqual(
            payload["remaining_recommended_actions"],
            [{"id": "build_index", "severity": "warning", "reason": "still stale"}],
        )

    def test_fail_fast_preserves_legacy_raise_on_failed_action(self) -> None:
        with (
            mock.patch.object(
                maintenance,
                "run_json",
                return_value={
                    "ok": False,
                    "recommended_actions": [
                        {"id": "build_index", "severity": "warning", "reason": "stale"}
                    ],
                },
            ),
            mock.patch.object(maintenance, "run_text", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                maintenance.main(["--cwd", ".", "--fail-fast", "--json"])

    def test_graphify_refresh_is_skipped_when_index_rebuild_fails(self) -> None:
        stale_health = {
            "ok": False,
            "recommended_actions": [
                {"id": "build_index", "severity": "warning", "reason": "stale"},
                {
                    "id": "prepare_graphify_corpus",
                    "severity": "info",
                    "reason": "index stale",
                },
            ],
        }
        health_calls = [stale_health, stale_health, stale_health]

        def module_for(cmd: list[str]) -> str:
            return cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else Path(cmd[1]).stem

        def fake_json(cmd: list[str]) -> tuple[int, dict | None, str, str]:
            module = module_for(cmd)
            if module == "aippocampus_runtime.health":
                return 0, health_calls.pop(0), "{}", ""
            if module == "aippocampus_runtime.navigation.cognitive_map":
                return 0, {"ok": True}, "{}", ""
            if module == "aippocampus_runtime.ops.graphify_corpus":
                self.fail("Graphify refresh should wait for a successful index rebuild")
            self.fail(f"unexpected JSON command: {cmd}")

        with (
            mock.patch.object(maintenance, "run_json_checked", side_effect=fake_json),
            mock.patch.object(
                maintenance,
                "run_text_checked",
                return_value=(2, "", "index writer locked"),
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = maintenance.main(["--cwd", ".", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(payload["maintenance_status"], "blocked")
        self.assertEqual(
            payload["skipped_due_to_failure"],
            [
                {
                    "id": "prepare_graphify_corpus",
                    "reason": "depends_on_failed_build_index",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
