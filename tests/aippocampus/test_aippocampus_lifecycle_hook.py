from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

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

    def health(self, action_ids: list[str] | None = None, *, segments_exists: bool = False) -> dict:
        action_ids = action_ids or []
        return {
            "ok": True,
            "index": {"exists": True, "stale": "build_index" in action_ids},
            "segments": {"exists": segments_exists, "stale": "build_segments" in action_ids},
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


if __name__ == "__main__":
    unittest.main()
