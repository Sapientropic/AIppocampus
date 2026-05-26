from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aippocampus_lifecycle_hook as hook  # noqa: E402


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
            "recommended_actions": [{"id": action_id, "severity": "suggestion"} for action_id in action_ids],
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

        self.assertEqual(actions, ["build_index", "build_clean_source", "register", "build_associations", "subconscious_maybe_start"])

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

        self.assertEqual(actions, ["build_index", "build_clean_source", "register", "build_associations"])

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

        self.assertEqual(stale_existing, ["build_segments", "register", "build_associations", "subconscious_maybe_start"])
        self.assertEqual(not_existing, ["register", "build_associations", "subconscious_maybe_start"])

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


if __name__ == "__main__":
    unittest.main()
