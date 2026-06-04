from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
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

from aippocampus_runtime import health as health  # noqa: E402


class AippocampusHealthTests(unittest.TestCase):
    def test_health_phase_boundaries_have_separate_registry_and_rendering_owners(self) -> None:
        from aippocampus_runtime import health_registry, health_render  # noqa: PLC0415

        self.assertIs(health.registry_health_report, health_registry.registry_health_report)
        self.assertIs(health.render_health_text, health_render.render_health_text)

    def test_recommended_script_command_uses_posix_codex_home_on_macos(self) -> None:
        with mock.patch.object(health.os, "name", "posix"):
            command = health.recommended_script_command("build_index.py", Path("/tmp/work space"))

        self.assertEqual(
            command,
            'PYTHONPATH="$CODEX_HOME/skills/aippocampus/scripts" '
            'python -m aippocampus_runtime.recall.index_builder --cwd "/tmp/work space"',
        )

    def test_recommended_script_command_keeps_powershell_shape_on_windows(self) -> None:
        with mock.patch.object(health.os, "name", "nt"):
            command = health.recommended_script_command("build_index.py", "C:/work")
        expected_cwd = "C:" + "\\work"

        self.assertEqual(
            command,
            '$env:PYTHONPATH="$env:CODEX_HOME\\skills\\aippocampus\\scripts"; '
            f'python -m aippocampus_runtime.recall.index_builder --cwd "{expected_cwd}"',
        )

    def test_question_stats_are_fail_open_diagnostics(self) -> None:
        with mock.patch.object(
            health,
            "question_health_stats",
            side_effect=RuntimeError("bad local staging file"),
        ):
            payload = health.load_question_stats(
                jobs_path=Path("subconscious_jobs.jsonl"),
                registry_path=Path("threads.json"),
                resolve_registry_refs=True,
            )

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "question_health_error")
        self.assertEqual(payload["error_type"], "RuntimeError")

    def test_missing_question_jobs_are_unavailable_not_maintenance_blockers(self) -> None:
        payload = health.load_question_stats(
            jobs_path=Path("missing-subconscious-jobs.jsonl"),
            registry_path=None,
        )

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "jobs_missing")

    def test_question_stats_default_to_aggregate_with_registry_ref_resolution(self) -> None:
        with mock.patch.object(
            health,
            "question_health_stats",
            return_value={
                "available": True,
                "tracked_question_count": 1,
                "lifecycle": [{"title": "private question"}],
                "longest_running_open_question": {"title": "private question"},
            },
        ) as stats:
            payload = health.load_question_stats(
                jobs_path=Path("subconscious_jobs.jsonl"),
                registry_path=Path("threads.json"),
            )

        stats.assert_called_once_with(
            Path("subconscious_jobs.jsonl"),
            registry_path=Path("threads.json"),
            dormant_after_days=health.DEFAULT_DORMANT_AFTER_DAYS,
        )
        self.assertTrue(payload["available"])
        self.assertEqual(payload["tracked_question_count"], 1)
        self.assertNotIn("lifecycle", payload)
        self.assertNotIn("longest_running_open_question", payload)

    def test_activity_diagnostics_are_advisory_not_threshold_replacements(self) -> None:
        self.assertEqual(
            health.activity_class(
                message_delta=30,
                byte_delta=0,
                stale_age_seconds=300,
                max_stale_messages=25,
                max_stale_bytes=5_000,
            ),
            "high_activity",
        )
        self.assertEqual(
            health.activity_class(
                message_delta=2,
                byte_delta=10,
                stale_age_seconds=2 * 24 * 3600,
                max_stale_messages=25,
                max_stale_bytes=5_000,
            ),
            "quiet",
        )

    def test_registry_wide_health_aggregates_without_default_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp)
            thread_dir = registry_dir / "threads" / "thread-1"
            (thread_dir / "index").mkdir(parents=True)
            (thread_dir / "clean-source").mkdir()
            (thread_dir / "index" / "manifest.json").write_text(
                json.dumps({"created_at": "2026-06-01T00:00:00Z", "message_count": 8}),
                encoding="utf-8",
            )
            (thread_dir / "clean-source" / "manifest.json").write_text("{}", encoding="utf-8")
            (thread_dir / "clean-source" / "messages.jsonl").write_text("one\n", encoding="utf-8")
            (registry_dir / "threads.json").write_text(
                json.dumps(
                    {
                        "threads": [
                            {
                                "thread_key": "provider:private-thread-title",
                                "message_count": 10,
                                "rollout_size": 2048,
                                "paths": {"registry_thread_store": "threads/thread-1"},
                                "health": {
                                    "ok": False,
                                    "recommended_actions": [
                                        {"id": "build_index", "severity": "warning"}
                                    ],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = health.registry_health_report(registry_dir=registry_dir)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["thread_count"], 1)
        self.assertEqual(payload["recommended_action_counts"], {"build_index": 1})
        self.assertFalse(payload["privacy"]["message_bodies_read"])
        self.assertFalse(payload["privacy"]["paths_included"])
        thread = payload["top_threads"][0]
        self.assertIn("thread_ref", thread)
        self.assertNotIn("private-thread-title", json.dumps(payload))
        self.assertNotIn("thread_dir", thread)

    def test_registry_wide_cli_can_emit_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "threads.json").write_text(json.dumps({"threads": []}), encoding="utf-8")
            with mock.patch("sys.stdout", new=StringIO()) as stdout:
                code = health.main(["--registry-wide", "--registry-dir", tmp, "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["thread_count"], 0)

    def test_health_reports_intentional_storage_eviction_not_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            rollout.write_text('{"type":"event_msg","payload":{"type":"user_message","message":"hi"}}\n', encoding="utf-8")
            anchors = workspace / "thread-anchors.md"
            anchors.write_text("# Anchors\n- still present\n", encoding="utf-8")
            index_dir = root / "index"
            index_dir.mkdir()
            manifest_path = index_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "created_at": "2026-06-01T00:00:00Z",
                        "message_count": 1,
                        "source_rollout_size": rollout.stat().st_size,
                        "last_message_line": 1,
                        "rag": {"enabled": True},
                    }
                ),
                encoding="utf-8",
            )
            (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
            evictions = index_dir / "evictions"
            evictions.mkdir()
            eviction_manifest = evictions / "storage-gc-test.json"
            eviction_manifest.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_storage_eviction_manifest",
                        "schema_version": 1,
                        "eviction_status": "applied",
                        "evicted_at": "2026-06-02T00:00:00Z",
                        "candidate_id": "retention:rebuildable-main-sqlite",
                        "tier": "rebuildable_cache",
                        "evicted_paths": [{"relative_path": "source_index.sqlite"}],
                        "rebuild_command": (
                            "python -m aippocampus_runtime.recall.index_builder "
                            "--cwd <workspace>"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            clean = root / "clean-source"
            clean.mkdir()
            clean_manifest = {
                "schema_version": 2,
                "upgrade_contract": {"source_backed": True},
                "source_rollout_size": rollout.stat().st_size,
                "message_count": 1,
                "turn_count": 1,
            }
            (clean / "manifest.json").write_text(json.dumps(clean_manifest), encoding="utf-8")
            (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
            (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
            graphify = root / "graphify-corpus"
            graphify.mkdir()
            (graphify / "corpus_manifest.json").write_text(
                json.dumps({"source_index_manifest_sha256": health.file_sha256(manifest_path)}),
                encoding="utf-8",
            )
            segments = root / "segments"
            checkpoint = root / "checkpoint_state.json"

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        index_dir=index_dir,
                        clean_source_dir=clean,
                        graphify_corpus=graphify,
                        segments_dir=segments,
                        checkpoint_state=checkpoint,
                        anchors=anchors,
                    )
                )

        self.assertTrue(payload["index"]["intentional_eviction"]["detected"])
        self.assertTrue(payload["index"]["intentional_eviction"]["rebuildable"])
        self.assertEqual(
            payload["index"]["intentional_eviction"]["manifest"],
            str(eviction_manifest),
        )
        self.assertIn(
            "aippocampus_runtime.recall.index_builder",
            payload["index"]["intentional_eviction"]["rebuild_command"],
        )
        self.assertIn(
            "source_index.sqlite intentionally evicted as rebuildable cache",
            payload["index"]["reasons"],
        )
        self.assertNotIn("source_index.sqlite is missing", payload["index"]["reasons"])

    def test_health_ignores_eviction_manifest_older_than_index_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            rollout.write_text('{"type":"event_msg","payload":{"type":"user_message","message":"hi"}}\n', encoding="utf-8")
            anchors = workspace / "thread-anchors.md"
            anchors.write_text("# Anchors\n- still present\n", encoding="utf-8")
            index_dir = root / "index"
            index_dir.mkdir()
            (index_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "created_at": "2026-06-03T00:00:00Z",
                        "message_count": 1,
                        "source_rollout_size": rollout.stat().st_size,
                        "last_message_line": 1,
                        "rag": {"enabled": True},
                    }
                ),
                encoding="utf-8",
            )
            (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
            evictions = index_dir / "evictions"
            evictions.mkdir()
            (evictions / "storage-gc-old.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_storage_eviction_manifest",
                        "schema_version": 1,
                        "eviction_status": "applied",
                        "evicted_at": "2026-06-02T00:00:00Z",
                        "candidate_id": "retention:rebuildable-main-sqlite",
                        "tier": "rebuildable_cache",
                        "evicted_paths": [{"relative_path": "source_index.sqlite"}],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        index_dir=index_dir,
                        clean_source_dir=root / "clean-source",
                        graphify_corpus=root / "graphify-corpus",
                        segments_dir=root / "segments",
                        checkpoint_state=root / "checkpoint_state.json",
                        anchors=anchors,
                    )
                )

        self.assertFalse(payload["index"]["intentional_eviction"]["detected"])
        self.assertIn("source_index.sqlite is missing", payload["index"]["reasons"])

    def test_health_reports_legacy_alias_names_without_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            rollout.write_text(
                '{"type":"event_msg","payload":{"type":"user_message","message":"hi"}}\n',
                encoding="utf-8",
            )
            anchors = workspace / "thread-anchors.md"
            anchors.write_text("# Anchors\n", encoding="utf-8")
            index_dir = workspace / ".aippocampus" / "index"
            index_dir.mkdir(parents=True)
            (index_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "created_at": "2026-06-03T00:00:00Z",
                        "message_count": 1,
                        "source_rollout_size": rollout.stat().st_size,
                        "last_message_line": 1,
                        "rag": {"enabled": True},
                    }
                ),
                encoding="utf-8",
            )
            (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
            clean = root / "clean-source"
            clean.mkdir()
            (clean / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "upgrade_contract": {"source_backed": True},
                        "source_rollout_size": rollout.stat().st_size,
                        "message_count": 1,
                        "turn_count": 1,
                    }
                ),
                encoding="utf-8",
            )
            (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
            (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
            graphify = root / "graphify-corpus"
            graphify.mkdir()
            manifest_path = index_dir / "manifest.json"
            (graphify / "corpus_manifest.json").write_text(
                json.dumps({"source_index_manifest_sha256": health.file_sha256(manifest_path)}),
                encoding="utf-8",
            )

            with (
                mock.patch.dict(health.os.environ, {"USERPROFILE": str(root / "home")}, clear=True),
                mock.patch.object(health, "codex_home", return_value=root / "codex-home"),
                mock.patch.object(health, "locate_rollout", return_value=rollout),
                mock.patch.object(
                    health,
                    "aippocampus_registry_resolution",
                    return_value={
                        "path": str(root / "codex-home" / "aippocampus-registry"),
                        "source": "CODEX_HOME/aippocampus-registry",
                        "legacy_fallback": True,
                    },
                ),
            ):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        index_dir=index_dir,
                        clean_source_dir=clean,
                        graphify_corpus=graphify,
                        segments_dir=root / "segments",
                        checkpoint_state=root / "checkpoint_state.json",
                        anchors=anchors,
                    )
                )
        aliases = {entry["alias"] for entry in payload["legacy_aliases"]["active"]}
        encoded_aliases = json.dumps(payload["legacy_aliases"], ensure_ascii=False)

        self.assertEqual(aliases, {"CODEX_HOME/aippocampus-registry", ".aippocampus/"})
        self.assertFalse(payload["legacy_aliases"]["value_printed"])
        self.assertFalse(payload["legacy_aliases"]["local_paths_included"])
        self.assertNotIn(str(root), encoded_aliases)


if __name__ == "__main__":
    unittest.main()
