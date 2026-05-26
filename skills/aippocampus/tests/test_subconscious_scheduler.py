from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import subconscious_scheduler as scheduler  # noqa: E402


class SubconsciousSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "workspace"
        self.cwd.mkdir()
        self.registry = {
            "threads": [
                {
                    "title": "T-Sense · app",
                    "workspace_name": "T-Sense-App",
                    "project_label": "T-Sense",
                    "project_tags": ["T-Sense", "T-SENSE-APP"],
                    "clean_turn_count": 8,
                    "clean_message_count": 16,
                    "updated_at": "2026-05-26T00:00:00Z",
                    "paths": {"workspace": str(self.cwd)},
                },
                {
                    "title": "T-Sense · core",
                    "workspace_name": "tg-channel-scanner",
                    "project_label": "T-Sense",
                    "project_tags": ["T-Sense", "core"],
                    "clean_turn_count": 7,
                    "clean_message_count": 14,
                    "updated_at": "2026-05-26T01:00:00Z",
                    "paths": {"workspace": str(self.root / "core")},
                },
            ]
        }
        scheduler.save_json(self.root / "threads.json", self.registry)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def args(self, **overrides):
        defaults = {
            "registry_dir": str(self.root),
            "state_file": None,
            "cwd": str(self.cwd),
            "project": None,
            "all_projects": False,
            "cooldown_seconds": 3600,
            "min_new_turns": 5,
            "max_turns": 96,
            "max_findings": 220,
            "api_key_env": "DEEPSEEK_API_KEY",
            "dry_run": False,
        }
        defaults.update(overrides)
        return type("Args", (), defaults)()

    def test_project_for_cwd_uses_registered_workspace(self) -> None:
        label = scheduler.project_for_cwd(self.registry, self.cwd)

        self.assertEqual(label, "T-Sense")

    def test_due_reason_first_run(self) -> None:
        stats = scheduler.project_stats_from_registry(self.registry)["T-Sense"]

        reason = scheduler.due_reason(
            stats,
            {},
            now_ts=1_800_000_000,
            cooldown_seconds=3600,
            min_new_turns=5,
        )

        self.assertEqual(reason, "first_run")

    def test_due_reason_respects_cooldown(self) -> None:
        stats = scheduler.project_stats_from_registry(self.registry)["T-Sense"]

        reason = scheduler.due_reason(
            stats,
            {"last_run_ts": 1_800_000_000 - 60, "last_clean_turn_count": 0},
            now_ts=1_800_000_000,
            cooldown_seconds=3600,
            min_new_turns=5,
        )

        self.assertIsNone(reason)

    def test_maybe_start_skips_without_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = scheduler.maybe_start(self.args())

        self.assertEqual(result["skipped"], "missing_DEEPSEEK_API_KEY")

    def test_maybe_start_dry_run_reports_due_project(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            result = scheduler.maybe_start(self.args(dry_run=True))

        self.assertFalse(result["started"])
        self.assertEqual(result["projects"][0]["label"], "T-Sense")

    def test_maybe_start_respects_active_project_lease(self) -> None:
        state_file = self.root / "subconscious_state.json"
        scheduler.save_json(
            state_file,
            {
                "projects": {
                    "T-Sense": {
                        "lease_until_ts": 9_999_999_999,
                        "lease_id": "existing-lease",
                    }
                }
            },
        )
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True), patch.object(
            scheduler,
            "start_detached",
            side_effect=AssertionError("leased project should not start another detached worker"),
        ):
            result = scheduler.maybe_start(self.args(state_file=str(state_file)))

        self.assertFalse(result["started"])
        self.assertEqual(result["skipped"], "leased_projects")

    def test_concurrent_maybe_start_launches_one_detached_worker(self) -> None:
        state_file = self.root / "subconscious_state.json"
        launches = 0
        launch_lock = threading.Lock()
        release_second_thread = threading.Event()
        results: list[dict[str, object]] = []

        def slow_start_detached(cmd: list[str], *, root: Path) -> int:
            del cmd, root
            nonlocal launches
            with launch_lock:
                launches += 1
            release_second_thread.set()
            time.sleep(0.1)
            return 1234

        def call_maybe_start() -> None:
            release_second_thread.wait(timeout=1)
            results.append(scheduler.maybe_start(self.args(state_file=str(state_file))))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True), patch.object(
            scheduler,
            "start_detached",
            side_effect=slow_start_detached,
        ):
            first = threading.Thread(target=call_maybe_start)
            second = threading.Thread(target=call_maybe_start)
            first.start()
            second.start()
            release_second_thread.set()
            first.join(timeout=2)
            second.join(timeout=2)

        self.assertEqual(launches, 1)
        self.assertEqual(sum(1 for item in results if item.get("started")), 1)
        skipped = [item.get("skipped") for item in results if not item.get("started")]
        self.assertEqual(len(skipped), 1)
        self.assertIn(skipped[0], {"enqueue_locked", "leased_projects"})

    def test_staging_bootstrap_prevents_immediate_duplicate_first_run(self) -> None:
        jobs = self.root / "subconscious_jobs.jsonl"
        jobs.write_text(
            '{"created_at":"2026-05-26T00:00:00Z","source_refs":[{"project_label":"T-Sense"}]}\n',
            encoding="utf-8",
        )
        state = {"projects": {"T-Sense": {}}}
        stats = scheduler.project_stats_from_registry(self.registry)["T-Sense"]

        scheduler.bootstrap_project_state_from_staging(
            self.root,
            stats,
            state["projects"]["T-Sense"],
            now_ts=scheduler.parse_utc_ts("2026-05-26T01:00:00Z") or 0,
            cooldown_seconds=6 * 60 * 60,
        )

        self.assertEqual(state["projects"]["T-Sense"]["last_status"], "bootstrapped_from_staging")
        self.assertEqual(state["projects"]["T-Sense"]["last_clean_turn_count"], 15)


if __name__ == "__main__":
    unittest.main()
