from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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

from aippocampus_runtime.subconscious import scheduler  # noqa: E402


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

        self.assertEqual(result["skipped"], "missing_api_key")
        self.assertEqual(
            result["cognitive_worker"]["status"],
            "deterministic_only_missing_provider_and_agent",
        )

    def test_maybe_start_queues_agent_fallback_task_without_provider_key(self) -> None:
        captured: dict[str, object] = {}

        def fake_start_detached(cmd: list[str], *, root: Path) -> int:
            captured["cmd"] = cmd
            captured["root"] = root
            return 4321

        with (
            patch.dict(os.environ, {"AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE": "1"}, clear=True),
            patch.object(
                scheduler,
                "start_detached",
                side_effect=fake_start_detached,
            ),
        ):
            result = scheduler.maybe_start(self.args())

        queue_path = self.root / "agent_fallback_tasks.jsonl"
        queued = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]

        self.assertFalse(result["started"])
        self.assertTrue(result["queued"])
        self.assertEqual(result["skipped"], "agent_fallback_queued")
        self.assertEqual(result["agent_fallback_task_count"], 1)
        self.assertEqual(result["cognitive_worker"]["resolved_mode"], "agent_fallback")
        self.assertNotIn("cmd", captured)
        self.assertEqual(queued[0]["kind"], "agent_fallback_subconscious_task")
        self.assertEqual(queued[0]["provenance"], "agent_fallback")
        self.assertEqual(queued[0]["project_label"], "T-Sense")
        self.assertTrue(queued[0]["output_contract"]["source_refs_required"])
        self.assertFalse(queued[0]["output_contract"]["foreground_sync_wait"])
        self.assertNotIn(str(self.cwd), json.dumps(queued, ensure_ascii=False))

    def test_maybe_start_respects_subconscious_hook_disable_env(self) -> None:
        with patch.dict(
            os.environ,
            {"AIPPOCAMPUS_SUBCONSCIOUS_HOOK": "off", "DEEPSEEK_API_KEY": "x"},
            clear=True,
        ):
            result = scheduler.maybe_start(self.args(dry_run=True))

        self.assertEqual(result["skipped"], "disabled_by_env")
        self.assertEqual(result["projects"], [])

    def test_maybe_start_dry_run_reports_due_project(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            result = scheduler.maybe_start(self.args(dry_run=True))

        self.assertFalse(result["started"])
        self.assertEqual(result["projects"][0]["label"], "T-Sense")
        self.assertEqual(result["scheduler_diagnostics"][0]["due_state"], "due")
        self.assertEqual(result["scheduler_diagnostics"][0]["due_reason"], "first_run")

    def test_maybe_start_dry_run_reports_due_growth_since_previous_run(self) -> None:
        state_file = self.root / "subconscious_state.json"
        scheduler.save_json(
            state_file,
            {
                "projects": {
                    "T-Sense": {
                        "last_run_ts": time.time() - 7200,
                        "last_run_at": "2026-05-26T00:00:00Z",
                        "last_clean_turn_count": 3,
                        "last_clean_message_count": 6,
                        "last_status": "success",
                    }
                }
            },
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            result = scheduler.maybe_start(
                self.args(dry_run=True, state_file=str(state_file))
            )

        diagnostic = result["scheduler_diagnostics"][0]
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["projects"][0]["label"], "T-Sense")
        self.assertEqual(diagnostic["due_state"], "due")
        self.assertEqual(diagnostic["due_reason"], "new_turns:12")
        self.assertEqual(diagnostic["new_turns_since_last_run"], 12)
        self.assertEqual(diagnostic["new_messages_since_last_run"], 24)
        self.assertEqual(diagnostic["last_run_at"], "2026-05-26T00:00:00Z")

    def test_no_due_project_reports_growth_below_threshold_without_private_labels_publicly(
        self,
    ) -> None:
        state_file = self.root / "subconscious_state.json"
        scheduler.save_json(
            state_file,
            {
                "projects": {
                    "T-Sense": {
                        "last_run_ts": time.time() - 7200,
                        "last_run_at": "2026-05-26T00:00:00Z",
                        "last_clean_turn_count": 15,
                        "last_clean_message_count": 30,
                        "last_status": "success",
                    }
                }
            },
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            result = scheduler.maybe_start(
                self.args(dry_run=True, state_file=str(state_file))
            )

        self.assertEqual(result["skipped"], "no_due_projects")
        self.assertTrue(result["dry_run"])
        diagnostic = result["scheduler_diagnostics"][0]
        self.assertEqual(diagnostic["label"], "T-Sense")
        self.assertEqual(diagnostic["due_state"], "not_due")
        self.assertEqual(diagnostic["skip_reason"], "source_growth_below_threshold")
        self.assertEqual(diagnostic["new_turns_since_last_run"], 0)
        public = scheduler.public_scheduler_payload(result)
        encoded = json.dumps(public, ensure_ascii=False)
        self.assertEqual(
            public["scheduler_diagnostics"][0]["skip_reason"],
            "source_growth_below_threshold",
        )
        self.assertNotIn("T-Sense", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_old_project_name_reports_name_resolution_skip_reason(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            result = scheduler.maybe_start(
                self.args(dry_run=True, project="Old Project Name")
            )

        self.assertEqual(result["skipped"], "no_due_projects")
        diagnostic = result["scheduler_diagnostics"][0]
        self.assertEqual(diagnostic["due_state"], "blocked")
        self.assertEqual(diagnostic["skip_reason"], "project_name_not_resolved")
        public = scheduler.public_scheduler_payload(result)
        encoded = json.dumps(public, ensure_ascii=False)
        self.assertEqual(
            public["scheduler_diagnostics"][0]["skip_reason"],
            "project_name_not_resolved",
        )
        self.assertNotIn("Old Project Name", encoded)

    def test_missing_clean_source_freshness_reports_explicit_skip_reason(self) -> None:
        registry = {
            "threads": [
                {
                    "title": "T-Sense · stale",
                    "project_label": "T-Sense",
                    "clean_turn_count": 8,
                    "clean_message_count": 16,
                    "paths": {"workspace": str(self.cwd)},
                }
            ]
        }
        scheduler.save_json(self.root / "threads.json", registry)
        state_file = self.root / "subconscious_state.json"
        scheduler.save_json(
            state_file,
            {
                "projects": {
                    "T-Sense": {
                        "last_run_ts": time.time() - 7200,
                        "last_run_at": "2026-05-26T00:00:00Z",
                        "last_clean_turn_count": 8,
                        "last_clean_message_count": 16,
                        "last_status": "success",
                    }
                }
            },
        )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            result = scheduler.maybe_start(
                self.args(dry_run=True, state_file=str(state_file))
            )

        self.assertEqual(result["skipped"], "no_due_projects")
        diagnostic = result["scheduler_diagnostics"][0]
        self.assertEqual(diagnostic["due_state"], "not_due")
        self.assertEqual(diagnostic["skip_reason"], "missing_clean_source_freshness")
        public = scheduler.public_scheduler_payload(result)
        encoded = json.dumps(public, ensure_ascii=False)
        self.assertEqual(
            public["scheduler_diagnostics"][0]["skip_reason"],
            "missing_clean_source_freshness",
        )
        self.assertNotIn("T-Sense", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_shell_selection_policy_reports_core_routing_shapes(self) -> None:
        from aippocampus_runtime.subconscious import shell_selection

        tiny = shell_selection.select_shell(
            shell_selection.ShellSelectionInput(
                project_label="Tiny",
                due_reason="first_run",
                clean_turn_count=2,
                clean_message_count=4,
                thread_count=1,
            )
        )
        mature = shell_selection.select_shell(
            shell_selection.ShellSelectionInput(
                project_label="Mature",
                due_reason="new_turns:80",
                clean_turn_count=96,
                clean_message_count=192,
                thread_count=4,
            )
        )
        backlog = shell_selection.select_shell(
            shell_selection.ShellSelectionInput(
                project_label="Backlog",
                due_reason="new_turns:20",
                clean_turn_count=40,
                clean_message_count=80,
                thread_count=2,
                staging_backlog_rows=shell_selection.DEFAULT_MAX_BACKLOG_ROWS + 1,
            )
        )
        low_confidence = shell_selection.select_shell(
            shell_selection.ShellSelectionInput(
                project_label="Low Confidence",
                due_reason="new_turns:12",
                clean_turn_count=24,
                clean_message_count=48,
                thread_count=1,
                low_confidence_prior_count=shell_selection.DEFAULT_LOW_CONFIDENCE_PRIOR_LIMIT,
            )
        )

        self.assertEqual(tiny["decision"], "deterministic_only")
        self.assertIn("tiny_corpus", tiny["reasons"])
        self.assertEqual(mature["decision"], "agent_probe")
        self.assertIn("mature_multi_thread_corpus", mature["reasons"])
        self.assertEqual(backlog["decision"], "skip_due_to_backpressure")
        self.assertIn("staging_backlog_high", backlog["reasons"])
        self.assertEqual(low_confidence["decision"], "agent_probe")
        self.assertIn("low_confidence_prior_worker_output", low_confidence["reasons"])
        self.assertFalse(mature["will_start_expensive_agent"])

    def test_shell_selection_manual_override_is_explicit(self) -> None:
        from aippocampus_runtime.subconscious import shell_selection

        report = shell_selection.select_shell(
            shell_selection.ShellSelectionInput(
                project_label="Manual",
                due_reason="new_turns:50",
                clean_turn_count=80,
                clean_message_count=160,
                thread_count=4,
            ),
            override="worker",
        )

        self.assertEqual(report["decision"], "worker")
        self.assertTrue(report["overridden"])
        self.assertIn("manual_override", report["reasons"])
        self.assertIn("subconscious_worker.py", " ".join(report["manual_override_surface"]))

    def test_maybe_start_dry_run_includes_shell_selection_report(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True):
            result = scheduler.maybe_start(self.args(dry_run=True, shell_selection="worker"))

        project = result["projects"][0]
        self.assertEqual(project["label"], "T-Sense")
        self.assertEqual(project["shell_selection"]["decision"], "worker")
        self.assertTrue(project["shell_selection"]["overridden"])
        self.assertIn("manual_override", project["shell_selection"]["reasons"])

    def test_maybe_start_uses_parallel_deepseek_defaults_for_detached_worker(self) -> None:
        captured: dict[str, object] = {}

        def fake_start_detached(cmd: list[str], *, root: Path) -> int:
            captured["cmd"] = cmd
            captured["root"] = root
            return 4321

        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True),
            patch.object(
                scheduler,
                "start_detached",
                side_effect=fake_start_detached,
            ),
        ):
            result = scheduler.maybe_start(self.args())

        cmd = [str(item) for item in captured["cmd"]]
        self.assertTrue(result["started"])
        self.assertIn("--job-concurrency", cmd)
        self.assertEqual(cmd[cmd.index("--job-concurrency") + 1], "4")
        self.assertIn("--samples-per-job", cmd)
        self.assertEqual(cmd[cmd.index("--samples-per-job") + 1], "2")

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
        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True),
            patch.object(
                scheduler,
                "start_detached",
                side_effect=AssertionError(
                    "leased project should not start another detached worker"
                ),
            ),
        ):
            result = scheduler.maybe_start(self.args(state_file=str(state_file)))

        self.assertFalse(result["started"])
        self.assertEqual(result["skipped"], "leased_projects")
        self.assertEqual(
            result["scheduler_diagnostics"][0]["skip_reason"],
            "lease_active_or_stale",
        )

    def test_file_lock_reports_active_local_lock_without_recovery(self) -> None:
        lock_path = self.root / "active.lock"

        with scheduler.FileLock(lock_path, stale_seconds=60):
            with self.assertRaisesRegex(RuntimeError, "active local lock"):
                with scheduler.FileLock(lock_path, stale_seconds=60):
                    self.fail("second lock should not acquire while first lock is active")

        self.assertFalse(lock_path.exists())

    def test_file_lock_recovers_stale_lock_with_diagnostic_payload(self) -> None:
        lock_path = self.root / "stale.lock"
        lock_path.write_text('{"pid": 999999, "created_at": "old"}', encoding="utf-8")
        stale_time = time.time() - 20
        os.utime(lock_path, (stale_time, stale_time))

        with scheduler.FileLock(lock_path, stale_seconds=1):
            payload = json.loads(lock_path.read_text(encoding="utf-8"))

        self.assertTrue(payload["recovered_stale_lock"])
        self.assertGreaterEqual(payload["stale_age_seconds"], 1)
        self.assertEqual(payload["stale_threshold_seconds"], 1)
        self.assertFalse(lock_path.exists())

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

        with (
            patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x"}, clear=True),
            patch.object(
                scheduler,
                "start_detached",
                side_effect=slow_start_detached,
            ),
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

    def test_run_project_materializes_semantic_scope_labels_before_rebuilding_timeline(
        self,
    ) -> None:
        stats = scheduler.project_stats_from_registry(self.registry)["T-Sense"]
        commands: list[list[str]] = []

        def fake_run_text(
            cmd: list[str], *, cwd: Path = scheduler.SCRIPT_DIR, log: Path | None = None
        ) -> str:
            del cwd, log
            commands.append(cmd)
            return "ok"

        with patch.object(scheduler, "run_text", side_effect=fake_run_text):
            result = scheduler.run_project(
                stats,
                root=self.root,
                max_turns=8,
                max_findings=12,
                job_concurrency=1,
                samples_per_job=1,
                log=self.root / "log.txt",
            )

        def command_label(command: list[str]) -> str:
            if len(command) > 2 and command[1] == "-m":
                return command[2]
            return Path(command[1]).name

        scripts = [command_label(command) for command in commands]
        self.assertIn("aippocampus_runtime.source.semantic_scope_builder", scripts)
        self.assertIn("aippocampus_runtime.dream.sleep_cycle", scripts)
        self.assertIn("aippocampus_runtime.dream.retrospective_lifecycle", scripts)
        semantic_index = scripts.index("aippocampus_runtime.source.semantic_scope_builder")
        dream_index = scripts.index("aippocampus_runtime.dream.sleep_cycle")
        retrospective_index = scripts.index("aippocampus_runtime.dream.retrospective_lifecycle")
        timeline_indexes = [
            index
            for index, name in enumerate(scripts)
            if name == "aippocampus_runtime.navigation.project_timeline"
        ]
        self.assertLess(scripts.index("aippocampus_runtime.subconscious.jobs"), semantic_index)
        jobs_command = commands[scripts.index("aippocampus_runtime.subconscious.jobs")]
        self.assertIn("--event-salience-gate", jobs_command)
        self.assertTrue(any(index > semantic_index for index in timeline_indexes))
        self.assertGreater(
            dream_index,
            scripts.index("aippocampus_runtime.subconscious.candidate_router"),
        )
        self.assertGreater(retrospective_index, dream_index)
        dream_command = commands[dream_index]
        self.assertIn("--project", dream_command)
        self.assertEqual(dream_command[dream_command.index("--project") + 1], "T-Sense")
        self.assertIn("--write-staging", dream_command)
        self.assertNotIn("--no-write", dream_command)
        self.assertIn("--summary", dream_command)
        retrospective_command = commands[retrospective_index]
        self.assertIn("--project", retrospective_command)
        self.assertEqual(retrospective_command[retrospective_command.index("--project") + 1], "T-Sense")
        self.assertIn("--summary", retrospective_command)
        self.assertEqual(result["commands"], len(commands))
        self.assertTrue(all("--registry-dir" in command for command in commands))

    def test_main_without_strict_keeps_hook_fail_open(self) -> None:
        with (
            patch.object(sys, "argv", ["subconscious_scheduler.py", "--maybe-start"]),
            patch.object(
                scheduler,
                "maybe_start",
                side_effect=RuntimeError("boom"),
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = scheduler.main()

        self.assertEqual(code, 0)

    def test_main_strict_returns_nonzero_on_operator_error(self) -> None:
        with (
            patch.object(sys, "argv", ["subconscious_scheduler.py", "--maybe-start", "--strict"]),
            patch.object(
                scheduler,
                "maybe_start",
                side_effect=RuntimeError("boom"),
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = scheduler.main()

        self.assertEqual(code, 1)

    def test_main_json_uses_public_scheduler_projection(self) -> None:
        private_result = {
            "started": True,
            "pid": 1234,
            "log": str(self.root / "subconscious_scheduler.log"),
            "projects": [{"label": "Private Project", "reason": "missing_PRIVATE_TOKEN"}],
            "results": [{"project": "Private Project", "last_output": "private model output"}],
        }
        stdout = io.StringIO()
        with (
            patch.object(sys, "argv", ["subconscious_scheduler.py", "--maybe-start", "--json"]),
            patch.object(scheduler, "maybe_start", return_value=private_result),
            contextlib.redirect_stdout(stdout),
        ):
            code = scheduler.main()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["started"])
        self.assertTrue(payload["pid_present"])
        self.assertNotIn("log", payload)
        self.assertNotIn("projects", payload)
        self.assertNotIn("Private Project", encoded)
        self.assertNotIn("PRIVATE_TOKEN", encoded)
        self.assertNotIn(str(self.root), encoded)

    def test_main_json_can_include_explicit_private_policy_report(self) -> None:
        private_result = {
            "started": False,
            "dry_run": True,
            "projects": [
                {
                    "label": "Private Project",
                    "reason": "first_run",
                    "shell_selection": {
                        "decision": "worker",
                        "reasons": ["manual_override"],
                        "overridden": True,
                    },
                }
            ],
            "log": str(self.root / "subconscious_scheduler.log"),
        }
        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "subconscious_scheduler.py",
                    "--maybe-start",
                    "--dry-run",
                    "--json",
                    "--include-private-report",
                ],
            ),
            patch.object(scheduler, "maybe_start", return_value=private_result),
            contextlib.redirect_stdout(stdout),
        ):
            code = scheduler.main()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["projects"][0]["shell_selection"]["decision"], "worker")
        self.assertIn("Private Project", encoded)
        self.assertNotIn(str(self.root), encoded)

    def test_private_policy_report_redacts_missing_env_reason(self) -> None:
        private_result = {
            "started": False,
            "dry_run": True,
            "projects": [
                {
                    "label": "Private Project",
                    "reason": "missing_PRIVATE_TOKEN",
                    "shell_selection": {
                        "decision": "deterministic_only",
                        "reasons": ["tiny_corpus"],
                    },
                }
            ],
        }
        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "subconscious_scheduler.py",
                    "--maybe-start",
                    "--dry-run",
                    "--json",
                    "--include-private-report",
                ],
            ),
            patch.object(scheduler, "maybe_start", return_value=private_result),
            contextlib.redirect_stdout(stdout),
        ):
            code = scheduler.main()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["projects"][0]["reason"], "missing_api_key")
        self.assertNotIn("PRIVATE_TOKEN", encoded)


if __name__ == "__main__":
    unittest.main()
