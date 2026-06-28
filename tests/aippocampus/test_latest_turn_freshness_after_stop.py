from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime.hooks import lifecycle as hook
from tests.aippocampus.product_probe_helpers import call_mcp_tool_payload

SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"


class LatestTurnFreshnessAfterStopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "workspace"
        self.cwd.mkdir()
        (self.cwd / "thread-anchors.md").write_text("# Anchors\n", encoding="utf-8")

        self.codex_home = self.root / "codex-home"
        self.registry_dir = self.root / "registry"
        self.sessions_dir = self.codex_home / "sessions" / "2026" / "06" / "28"
        self.sessions_dir.mkdir(parents=True)
        self.rollout = self.sessions_dir / "rollout-latest-stop-proof.jsonl"
        self.session_id = "latest-stop-proof"
        self.latest_anchor = "latest Stop freshness anchor 2859 opened from clean source"

        self.old_env = {
            "AIPPOCAMPUS_REGISTRY_DIR": os.environ.get("AIPPOCAMPUS_REGISTRY_DIR"),
            "CODEX_HOME": os.environ.get("CODEX_HOME"),
            "PYTHONPATH": os.environ.get("PYTHONPATH"),
        }
        os.environ["AIPPOCAMPUS_REGISTRY_DIR"] = str(self.registry_dir)
        os.environ["CODEX_HOME"] = str(self.codex_home)
        pythonpath = str(SCRIPTS_ROOT)
        if self.old_env["PYTHONPATH"]:
            pythonpath = pythonpath + os.pathsep + self.old_env["PYTHONPATH"]
        os.environ["PYTHONPATH"] = pythonpath

    def tearDown(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _write_rollout_rows(self, rows: list[dict[str, object]]) -> None:
        self.rollout.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def _base_rows(self) -> list[dict[str, object]]:
        return [
            {
                "type": "session_meta",
                "payload": {
                    "id": self.session_id,
                    "timestamp": "2026-06-28T00:00:00Z",
                    "cwd": str(self.cwd),
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-28T00:00:01Z",
                "payload": {
                    "type": "user_message",
                    "message": "set up a stale clean-source proof",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-28T00:00:02Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "old final answer before the Stop freshness refresh",
                },
            },
        ]

    def _append_latest_turn_after_initial_artifacts(self) -> None:
        with self.rollout.open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-28T00:01:01Z",
                        "payload": {
                            "type": "user_message",
                            "message": "does Stop make the latest final source-openable?",
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-28T00:01:02Z",
                        "payload": {
                            "type": "agent_message",
                            "phase": "final_answer",
                            "message": self.latest_anchor,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        future = time.time() + 30.0
        os.utime(self.rollout, (future, future))

    def _build_initial_stale_artifacts(self) -> None:
        self._write_rollout_rows(self._base_rows())
        for action in ("build_index", "build_clean_source", "register"):
            result = hook.run_action(self.cwd, action)
            self.assertNotIn("error", result)

    def test_stop_refresh_makes_latest_final_reopenable_through_mcp_and_registry_search(
        self,
    ) -> None:
        self._build_initial_stale_artifacts()
        self._append_latest_turn_after_initial_artifacts()

        with mock.patch.object(
            hook,
            "start_detached_json",
            return_value={
                "detached": True,
                "pid": 0,
                "log": str(self.root / "detached-suppressed-in-test.log"),
                "command": ["suppressed-in-test"],
            },
        ):
            result = hook.run_maintenance(
                "Stop",
                self.cwd,
                state_file=self.root / "lifecycle-state.json",
                now_ts=time.time() + 60.0,
                max_elapsed_ms=0,
            )

        self.assertEqual(result["errors"], [])
        self.assertTrue(result["freshness"]["latest_visible_gap"])
        self.assertIn("build_index", result["actions"])
        self.assertIn("build_clean_source", result["actions"])
        self.assertIn("register", result["actions"])

        latest = call_mcp_tool_payload("latest_reply", {"cwd": str(self.cwd)})
        self.assertEqual(latest["status"], "clean_source_final_answer")
        self.assertIn(self.latest_anchor, latest["message"]["text"])
        self.assertEqual(
            latest["source_reopen_action"]["tool_name"],
            "get_turn_context",
        )

        opened = call_mcp_tool_payload(
            "get_turn_context",
            {
                "cwd": str(self.cwd),
                **latest["source_reopen_action"]["arguments"],
            },
        )
        opened_text = json.dumps(opened.get("messages"), ensure_ascii=False)
        self.assertIn(self.latest_anchor, opened_text)

        search = call_mcp_tool_payload(
            "search_memory",
            {
                "cwd": str(self.cwd),
                "registry_dir": str(self.registry_dir),
                "scope": "all_registered_sources",
                "query": self.latest_anchor,
            },
        )
        self.assertEqual(search["foreground_action"]["tool_name"], "search_memory")
        self.assertTrue(search["foreground_action"]["arguments"]["open_source"])

        search_opened = call_mcp_tool_payload(
            "search_memory",
            {
                "cwd": str(self.cwd),
                "registry_dir": str(self.registry_dir),
                **search["foreground_action"]["arguments"],
            },
        )
        self.assertEqual(search_opened["source_boundary"]["authority"], "source_open")
        self.assertIn(
            self.latest_anchor,
            json.dumps(search_opened["source_window_preview"], ensure_ascii=False),
        )


if __name__ == "__main__":
    unittest.main()
