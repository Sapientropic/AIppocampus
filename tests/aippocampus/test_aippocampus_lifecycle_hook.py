from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.hooks import lifecycle as hook  # noqa: E402


class MemoryMaintenanceHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.now = 1_800_000_000.0

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def health(
        self,
        action_ids: list[str] | None = None,
        *,
        segments_exists: bool = False,
        latest_gap: bool = False,
        rollout_message_count: int = 10,
        rollout_last_message_line: int = 20,
        clean_expected_message_count: int = 8,
        clean_expected_turn_count: int = 4,
    ) -> dict:
        action_ids = action_ids or []
        return {
            "ok": True,
            "rollout": {
                "message_count": rollout_message_count,
                "last_message_line": rollout_last_message_line,
            },
            "index": {"exists": True, "stale": "build_index" in action_ids},
            "clean_source": {
                "exists": True,
                "stale": "build_clean_source" in action_ids,
                "expected_message_count": clean_expected_message_count,
                "expected_turn_count": clean_expected_turn_count,
            },
            "segments": {"exists": segments_exists, "stale": "build_segments" in action_ids},
            "freshness": {
                "latest_visible_gap": latest_gap,
                "raw_newer_than_index": latest_gap,
                "raw_newer_than_clean_source": latest_gap,
                "expected_clean_source_message_count": clean_expected_message_count,
                "expected_clean_source_turn_count": clean_expected_turn_count,
            },
            "recommended_actions": [
                {"id": action_id, "severity": "suggestion"} for action_id in action_ids
            ],
        }

    def test_user_prompt_submit_never_schedules_maintenance(self) -> None:
        actions = hook.decide_actions(
            "UserPromptSubmit",
            self.health(["build_index"]),
            {},
            now_ts=self.now,
        )

        self.assertEqual(actions, [])

    def test_stop_builds_index_and_registers_when_due(self) -> None:
        actions = hook.decide_actions(
            "Stop",
            self.health(["build_index"]),
            {},
            now_ts=self.now,
        )

        self.assertEqual(
            actions,
            [
                "build_index",
                "build_clean_source",
                "register",
                "build_associations",
                "subconscious_maybe_start",
            ],
        )

    def test_stop_respects_cooldown(self) -> None:
        actions = hook.decide_actions(
            "Stop",
            self.health(["build_index"]),
            {"last_stop_ts": self.now - 60},
            now_ts=self.now,
        )

        self.assertEqual(actions, [])

    def test_stop_latest_turn_gap_bypasses_cooldown_once_per_visible_marker(self) -> None:
        actions = hook.decide_actions(
            "Stop",
            self.health(
                ["build_index", "build_clean_source"],
                latest_gap=True,
                rollout_message_count=12,
                rollout_last_message_line=25,
                clean_expected_message_count=10,
                clean_expected_turn_count=5,
            ),
            {"last_stop_ts": self.now - 60},
            now_ts=self.now,
        )

        self.assertEqual(
            actions,
            [
                "build_index",
                "build_clean_source",
                "register",
                "build_associations",
                "subconscious_maybe_start",
            ],
        )

        repeated = hook.decide_actions(
            "Stop",
            self.health(
                ["build_index", "build_clean_source"],
                latest_gap=True,
                rollout_message_count=12,
                rollout_last_message_line=25,
                clean_expected_message_count=10,
                clean_expected_turn_count=5,
            ),
            {
                "last_stop_ts": self.now - 60,
                "last_latest_turn_refresh_marker": "m12:l25:cm10:ct5",
            },
            now_ts=self.now,
        )

        self.assertEqual(repeated, [])

    def test_precompact_forces_index_refresh_even_without_recommendation(self) -> None:
        actions = hook.decide_actions(
            "PreCompact",
            self.health([]),
            {"last_compact_ts": self.now - 60},
            now_ts=self.now,
        )

        self.assertEqual(
            actions, ["build_index", "build_clean_source", "register", "build_associations"]
        )

    def test_existing_segments_refresh_when_stale_but_new_segments_are_not_spawned(self) -> None:
        stale_existing = hook.decide_actions(
            "Stop",
            self.health(["build_segments"], segments_exists=True),
            {},
            now_ts=self.now,
        )
        not_existing = hook.decide_actions(
            "Stop",
            self.health(["build_segments"], segments_exists=False),
            {},
            now_ts=self.now,
        )

        self.assertEqual(
            stale_existing,
            ["build_segments", "register", "build_associations", "subconscious_maybe_start"],
        )
        self.assertEqual(
            not_existing, ["register", "build_associations", "subconscious_maybe_start"]
        )

    def test_state_key_is_stable_and_path_safe(self) -> None:
        key1 = hook.state_key(self.cwd)
        key2 = hook.state_key(self.cwd)

        self.assertEqual(key1, key2)
        self.assertNotIn(str(self.cwd), key1)

    def test_run_json_decodes_child_utf8_output(self) -> None:
        script = self.cwd / "emit_utf8.py"
        script.write_text(
            "import json\nprint(json.dumps({'text': '小海马体'}, ensure_ascii=False))\n",
            encoding="utf-8",
        )

        result = hook.run_json([sys.executable, str(script)])

        self.assertEqual(result["text"], "小海马体")

    def test_build_associations_is_enqueued_detached(self) -> None:
        original = hook.start_detached_json
        seen: dict[str, object] = {}

        def fake_start(cmd: list[str], *, log_name: str) -> dict:
            seen["cmd"] = cmd
            seen["log_name"] = log_name
            return {"detached": True, "pid": 1234, "log": "diagnostic.log", "command": cmd}

        try:
            hook.start_detached_json = fake_start
            result = hook.run_action(self.cwd, "build_associations")
        finally:
            hook.start_detached_json = original

        self.assertTrue(result["detached"])
        self.assertIn(
            "aippocampus_runtime.navigation.associations",
            " ".join(str(item) for item in seen["cmd"]),
        )
        self.assertEqual(seen["log_name"], "build_associations_hook.log")

    def test_subconscious_scheduler_is_enqueued_detached_without_foreground_timeout(self) -> None:
        original = hook.start_detached_json
        seen: dict[str, object] = {}

        def fake_start(cmd: list[str], *, log_name: str) -> dict:
            seen["cmd"] = cmd
            seen["log_name"] = log_name
            return {"detached": True, "pid": 5678, "log": "subconscious.log", "command": cmd}

        try:
            hook.start_detached_json = fake_start
            result = hook.run_action(self.cwd, "subconscious_maybe_start")
        finally:
            hook.start_detached_json = original

        rendered = " ".join(str(item) for item in seen["cmd"])
        self.assertTrue(result["detached"])
        self.assertIn("aippocampus_runtime.subconscious.scheduler", rendered)
        self.assertIn("--maybe-start", rendered)
        self.assertNotIn("run_json_timeout", rendered)
        self.assertEqual(seen["log_name"], "subconscious_scheduler_hook.log")

    def test_detached_action_output_uses_log_retention_runner(self) -> None:
        log = self.cwd / "logs" / "build_associations_hook.log"
        child = [sys.executable, "-c", "print('child output')"]
        fake_proc = mock.Mock(pid=4242)

        with (
            mock.patch.object(hook, "maintenance_log_path", return_value=log),
            mock.patch.object(hook.subprocess, "Popen", return_value=fake_proc) as popen,
        ):
            result = hook.start_detached_json(child, log_name=log.name)

        wrapped_cmd = popen.call_args.args[0]
        kwargs = popen.call_args.kwargs
        rendered = " ".join(str(item) for item in wrapped_cmd)
        self.assertEqual(result["pid"], 4242)
        self.assertIn("aippocampus_runtime.ops.log_retention", rendered)
        self.assertIn("--", wrapped_cmd)
        self.assertEqual(wrapped_cmd[-len(child) :], child)
        self.assertIs(kwargs["stdout"], hook.subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], hook.subprocess.DEVNULL)

    def test_budget_capped_latest_turn_refresh_returns_dirty_diagnostic_without_marker(
        self,
    ) -> None:
        original_run_health = hook.run_health
        original_run_action = hook.run_action
        health_payload = self.health(
            ["build_index", "build_clean_source"],
            latest_gap=True,
            rollout_message_count=12,
            rollout_last_message_line=25,
            clean_expected_message_count=10,
            clean_expected_turn_count=5,
        )
        state_file = self.cwd / "state.json"

        def fake_run_health(cwd: Path) -> dict:
            del cwd
            return health_payload

        def fake_run_action(cwd: Path, action: str) -> dict:
            raise AssertionError(f"budget should skip {action} before execution")

        try:
            hook.run_health = fake_run_health
            hook.run_action = fake_run_action
            result = hook.run_maintenance(
                "Stop",
                self.cwd,
                state_file=state_file,
                now_ts=self.now,
                max_elapsed_ms=1,
            )
        finally:
            hook.run_health = original_run_health
            hook.run_action = original_run_action

        state = hook.load_state(state_file)
        workspace_state = state["workspaces"][hook.state_key(self.cwd)]

        self.assertTrue(result["freshness"]["latest_visible_gap"])
        self.assertEqual(result["skipped_actions"][0]["reason"], "foreground_budget")
        self.assertNotIn("last_latest_turn_refresh_marker", workspace_state)


if __name__ == "__main__":
    unittest.main()
