from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime import health  # noqa: E402
from aippocampus_runtime.ops import storage_eviction, storage_governance  # noqa: E402
from aippocampus_runtime.recall import index_builder, rollout_search  # noqa: E402


class StorageGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry"
        self.thread = self.registry / "threads" / "session-one"
        self.clean = self.thread / "clean-source"
        self.index = self.thread / "index"
        self.segment = self.index / "segments" / "seg-000001"
        self.clean.mkdir(parents=True)
        self.segment.mkdir(parents=True)

        self.raw_rollout = self.root / "rollout.jsonl"
        self.raw_rollout.write_text(
            "\n".join(
                json.dumps(row, ensure_ascii=False)
                for row in [
                    {
                        "type": "session_meta",
                        "payload": {"id": "session-one", "cwd": str(self.root)},
                    },
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-01T00:00:00Z",
                        "payload": {
                            "type": "user_message",
                            "message": "storage governance rebuild verification phrase",
                        },
                    },
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-01T00:00:01Z",
                        "payload": {
                            "type": "agent_message",
                            "phase": "final_answer",
                            "message": "storage governance answer",
                        },
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.anchors = self.root / "thread-anchors.md"
        self.anchors.write_text("# Anchors\n- source ref stays reopenable\n", encoding="utf-8")

        (self.registry / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:one",
                            "paths": {"rollout": str(self.raw_rollout)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.clean / "manifest.json").write_text(
            json.dumps({"kind": "aippocampus_clean_source"}), encoding="utf-8"
        )
        (self.clean / "messages.jsonl").write_text(
            json.dumps({"text": "private phrase that must not leak"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        (self.clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
        (self.clean / "semantic-scope-labels.jsonl").write_text("{}\n", encoding="utf-8")

        (self.index / "manifest.json").write_text(
            json.dumps({"kind": "aippocampus_index"}), encoding="utf-8"
        )
        (self.index / "messages.jsonl").write_bytes(b"indexed-message-cache")
        self.sqlite = self.index / "source_index.sqlite"
        self.sqlite.write_bytes(b"x" * 31)
        (self.index / "source_index.sqlite-wal").write_bytes(b"wal")
        (self.index / "source_index.sqlite-shm").write_bytes(b"shm")
        (self.index / "source_index.sqlite-journal").write_bytes(b"journal")
        (self.segment / "source_index.sqlite").write_bytes(b"y" * 17)
        (self.index / "segments" / "manifest.json").write_text(
            json.dumps({"segment_count": 1}), encoding="utf-8"
        )

        self.retention_path = self.root / "retention_report.json"
        self.retention_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "rollout": {"size_bytes": self.raw_rollout.stat().st_size},
                    "anchors": {"exists": True, "count": 2, "path": str(self.anchors)},
                    "index_dir": str(self.index),
                    "items": [
                        {
                            "id": "must-keep-active-rollout",
                            "label": "Active Codex rollout JSONL",
                            "kind": "live_source_of_truth",
                            "path": str(self.raw_rollout),
                            "bytes": self.raw_rollout.stat().st_size,
                            "action": "do_not_modify_live_file",
                            "safety": "must_keep",
                            "evidence": ["Live source must not be deleted."],
                        },
                        {
                            "id": "rebuildable-main-sqlite",
                            "label": "Main SQLite/FTS index",
                            "kind": "rebuildable_generated_index",
                            "path": str(self.index / "source_index.sqlite"),
                            "bytes": 31,
                            "action": "rebuildable_delete_under_disk_pressure",
                            "safety": (
                                "safe_to_delete_after_raw_rollout_and_anchors_are_available"
                            ),
                            "evidence": ["Created by build_index.py from exact source."],
                        },
                        {
                            "id": "review-artifacts",
                            "label": "Ad hoc UI review screenshots/JSON traces",
                            "kind": "user_review_artifact",
                            "path": str(self.index),
                            "bytes": 13,
                            "action": "archive_or_delete_after_human_review",
                            "safety": "needs_human_confirmation",
                            "evidence": ["Review traces are not source text."],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _retention_payload(self) -> dict:
        return json.loads(self.retention_path.read_text(encoding="utf-8"))

    def _write_retention_payload(self, payload: dict) -> None:
        self.retention_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_index_generation(self, generation_id: str, size: int) -> Path:
        generation_dir = self.index / "generations" / generation_id
        generation_dir.mkdir(parents=True)
        (generation_dir / "source_index.sqlite").write_bytes(b"g" * size)
        return generation_dir

    def _write_segment_generation(self, generation_id: str, size: int) -> Path:
        generation_dir = self.index / "segments" / "generations" / generation_id
        shard_dir = generation_dir / "seg-000001"
        shard_dir.mkdir(parents=True)
        (generation_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "segment_count": 1,
                    "generation_id": generation_id,
                    "segments": [
                        {"id": "seg-000001", "sqlite": str(shard_dir / "source_index.sqlite")}
                    ],
                }
            ),
            encoding="utf-8",
        )
        (shard_dir / "source_index.sqlite").write_bytes(b"s" * size)
        return generation_dir

    def _mark_path_old(self, path: Path) -> None:
        stale_time = time.time() - (7 * 60 * 60)
        os.utime(path, (stale_time, stale_time))

    def _mark_generation_old(self, generation_dir: Path) -> None:
        for path in [generation_dir, *generation_dir.rglob("*")]:
            self._mark_path_old(path)

    def _write_reader_pin(self, pointer_parent: Path, generation_dir: Path) -> Path:
        pins = pointer_parent / ".reader-pins"
        pins.mkdir(parents=True, exist_ok=True)
        pin = pins / f"reader-pin-{generation_dir.name}.json"
        pin.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_generation_reader_pin",
                    "pid": os.getpid(),
                    "generation": generation_dir.name,
                    "created_at": "2026-06-05T00:00:00Z",
                    "ttl_seconds": 21600,
                    "target_relative_path": (
                        f"generations/{generation_dir.name}/manifest.json"
                        if pointer_parent.name == "segments"
                        else f"generations/{generation_dir.name}/source_index.sqlite"
                    ),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return pin

    def _assert_no_workspace_absolute_paths(self, payload: object) -> None:
        root_text = str(self.root)
        normalized_root = root_text.replace("\\", "/")

        def visit(value: object, trail: str) -> None:
            if isinstance(value, str):
                normalized_value = value.replace("\\", "/")
                self.assertNotIn(root_text, value, trail)
                self.assertNotIn(normalized_root, normalized_value, trail)
                return
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(child, f"{trail}.{key}")
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{trail}[{index}]")

        visit(payload, "$")

    def test_dry_run_uses_existing_reports_without_leaking_private_text_or_paths(self) -> None:
        plan = storage_governance.build_plan(
            self.root,
            registry_dir=self.registry,
            retention_report_path=self.retention_path,
            class_filter="rebuildable",
        )
        payload = json.dumps(plan, ensure_ascii=False)

        self.assertFalse(plan["privacy"]["reads_raw_rollout_bodies"])
        self.assertFalse(plan["privacy"]["reads_clean_source_message_bodies"])
        self.assertTrue(plan["privacy"]["loads_existing_retention_report"])
        self.assertNotIn("private phrase", payload)
        self._assert_no_workspace_absolute_paths(plan)

        self.assertEqual(plan["metrics"]["eviction_candidate_count"], 1)
        candidate = plan["candidates"][0]
        self.assertEqual(candidate["id"], "retention:rebuildable-main-sqlite")
        self.assertEqual(candidate["tier"], "rebuildable_cache")
        self.assertEqual(candidate["path"]["relative_path"], "source_index.sqlite")
        self.assertNotIn("path", candidate["path"])
        self.assertEqual(candidate["preconditions"]["raw_or_archive_source"]["status"], "passed")
        self.assertEqual(
            candidate["preconditions"]["active_thread_exclusion"]["status"],
            "blocked_by_default",
        )

    def test_dry_run_json_cli_bounds_candidates_by_top_unless_full_requested(self) -> None:
        with patch("sys.stdout", new=StringIO()) as stdout:
            code = storage_governance.main(
                [
                    "gc",
                    "--dry-run",
                    "--cwd",
                    str(self.root),
                    "--registry-dir",
                    str(self.registry),
                    "--retention-report",
                    str(self.retention_path),
                    "--top",
                    "1",
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "dry_run_ready")
        self.assertEqual(payload["candidate_count_total"], 2)
        self.assertEqual(payload["candidates_returned"], 1)
        self.assertTrue(payload["candidates_truncated"])
        self.assertEqual(len(payload["candidates"]), 1)
        self.assertTrue(payload["candidates"][0]["candidate_handle"].startswith("candidate_"))
        self.assertFalse(payload["privacy"]["raw_session_like_ids_emitted"])
        self.assertNotIn("session-one", encoded)
        self.assertNotIn("session:one", encoded)
        self.assertEqual(payload["full_audit_flag"], "--full")

    def test_dry_run_summary_json_is_foreground_bounded(self) -> None:
        with patch("sys.stdout", new=StringIO()) as stdout:
            code = storage_governance.main(
                [
                    "gc",
                    "--dry-run",
                    "--cwd",
                    str(self.root),
                    "--registry-dir",
                    str(self.registry),
                    "--retention-report",
                    str(self.retention_path),
                    "--top",
                    "1",
                    "--summary-json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "dry_run_ready")
        self.assertEqual(payload["kind"], "aippocampus_storage_gc_summary")
        self.assertNotIn("candidates", payload)
        self.assertNotIn("candidate_samples", payload)
        self.assertEqual(payload["candidate_count_total"], 2)
        self.assertEqual(payload["sample_candidate_count"], 0)
        self.assertTrue(payload["candidate_detail_deferred"])
        self.assertEqual(payload["metrics_status"], "computed")
        self.assertEqual(payload["pressure_interpretation"], "pressure_present")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertEqual(action_ids[:3], ["bounded_storage_audit", "stop_without_cleanup", "apply_rebuildable_after_audit"])
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
        self.assertEqual(
            payload["safe_next_actions"][2]["mutation_risk"],
            "explicit_local_delete_of_rebuildable_cache",
        )
        self.assertTrue(payload["safe_next_actions"][2]["requires_prior_audit"])
        self.assertIn("deterministic_checks", payload["safe_next_actions"][2])
        self.assertIn("rollback_or_rebuild_boundary", payload["safe_next_actions"][2])
        self.assertEqual(
            payload["safe_next_action"]["command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(
            payload["comparable_metrics_command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(payload["risk_boundary"]["apply_requires_explicit_flag"], True)
        self.assertFalse(payload["privacy"]["raw_session_like_ids_emitted"])
        self.assertNotIn("session-one", encoded)
        self.assertNotIn("session:one", encoded)

    def test_summary_json_without_mode_defaults_to_no_write_dry_run_card(self) -> None:
        with patch("sys.stdout", new=StringIO()) as stdout:
            code = storage_governance.main(
                [
                    "gc",
                    "--cwd",
                    str(self.root),
                    "--registry-dir",
                    str(self.registry),
                    "--retention-report",
                    str(self.retention_path),
                    "--top",
                    "1",
                    "--summary-json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["mode"], "dry_run")
        self.assertTrue(payload["read_only"])
        self.assertEqual(
            payload["safe_next_action"]["command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(payload["pressure_interpretation"], "pressure_present")

    def test_summary_json_without_existing_reports_defers_full_scan_instead_of_building_capacity(
        self,
    ) -> None:
        with (
            patch.object(
                storage_governance.storage_capacity_report,
                "build_report",
                side_effect=AssertionError("summary card should not build capacity report"),
            ),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = storage_governance.main(
                [
                    "gc",
                    "--dry-run",
                    "--cwd",
                    str(self.root),
                    "--registry-dir",
                    str(self.registry),
                    "--summary-json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_storage_gc_summary")
        self.assertEqual(payload["status"], "needs_full_scan")
        self.assertTrue(payload["read_only"])
        self.assertTrue(payload["needs_full_scan"])
        self.assertTrue(payload["candidate_detail_deferred"])
        self.assertEqual(payload["metrics_status"], "not_computed_in_summary_mode")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(payload["safe_next_actions"][0]["id"], "bounded_storage_audit")
        self.assertEqual(payload["safe_next_actions"][1]["id"], "stop_without_cleanup")
        self.assertNotIn(
            "apply_rebuildable_after_audit",
            [action["id"] for action in payload["safe_next_actions"]],
        )
        self.assertEqual(
            payload["safe_next_action"]["command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(
            payload["comparable_metrics_command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(
            payload["operator_audit_command"],
            "aippocampus storage gc --dry-run --json --full --cwd .",
        )

    def test_dry_run_falls_back_to_capacity_aggregate_when_retention_report_is_missing(
        self,
    ) -> None:
        plan = storage_governance.build_plan(
            self.root,
            registry_dir=self.registry,
        )
        payload = json.dumps(plan, ensure_ascii=False)

        self.assertFalse(plan["privacy"]["loads_existing_retention_report"])
        self.assertEqual(plan["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(plan["surface_class"], "foreground_storage_gc_plan")
        keys = list(plan)
        self.assertLess(keys.index("foreground_action"), keys.index("policy_model"))
        self.assertLess(keys.index("agent_next_action"), keys.index("candidates"))
        self.assertLess(keys.index("safe_next_actions"), keys.index("metrics"))
        self.assertGreater(plan["metrics"]["reclaimable_rebuildable_bytes"], 0)
        self.assertGreaterEqual(plan["metrics"]["eviction_candidate_count"], 1)
        self.assertIn("Path-level retention candidates are unavailable", plan["warnings"][0])
        self.assertNotIn("private phrase", payload)
        self._assert_no_workspace_absolute_paths(plan)
        self.assertEqual(plan["candidates"][0]["source_report"]["kind"], "storage_capacity_report")
        self.assertEqual(plan["candidates"][0]["actionability"], "plan_only_aggregate")
        self.assertIn("path-level retention candidates", plan["candidates"][0]["plan_only_reason"])
        self.assertIn("rebuild_note", plan["candidates"][0])
        self.assertNotIn("rebuild_command", plan["candidates"][0])
        self.assertEqual(
            plan["agent_next_action"]["command"],
            "aippocampus storage gc --dry-run --json --full --cwd .",
        )
        self.assertTrue(
            all(" --apply " not in action["command"] for action in plan["safe_next_actions"])
        )

    def test_capacity_fallback_cli_redacts_session_like_ids_by_default(self) -> None:
        with patch("sys.stdout", new=StringIO()) as stdout:
            code = storage_governance.main(
                [
                    "gc",
                    "--dry-run",
                    "--cwd",
                    str(self.root),
                    "--registry-dir",
                    str(self.registry),
                    "--top",
                    "2",
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "dry_run_ready")
        self.assertFalse(payload["privacy"]["raw_session_like_ids_emitted"])
        self.assertGreaterEqual(payload["candidate_count_total"], 1)
        self.assertTrue(payload["candidates"][0]["candidate_handle"].startswith("candidate_"))
        self.assertEqual(payload["candidates"][0]["actionability"], "plan_only_aggregate")
        self.assertIn("rebuild_note", payload["candidates"][0])
        self.assertNotIn("rebuild_command", payload["candidates"][0])
        self.assertNotIn("capacity:session-one", encoded)
        self.assertNotIn("session-one", encoded)
        self.assertNotIn("session:one", encoded)

    def test_apply_rebuildable_main_sqlite_writes_manifest_and_preserves_sources(self) -> None:
        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            retention_report_path=self.retention_path,
            class_filter="rebuildable",
            include_active=True,
            include_paths=True,
        )
        payload = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "apply")
        self.assertEqual(result["metrics"]["eviction_applied_count"], 1)
        self.assertFalse(self.sqlite.exists())
        for suffix in ("-wal", "-shm", "-journal"):
            self.assertFalse((self.index / f"source_index.sqlite{suffix}").exists())
        self.assertTrue(self.raw_rollout.exists())
        self.assertTrue((self.clean / "messages.jsonl").exists())
        self.assertTrue(self.anchors.exists())
        self.assertNotIn("private phrase", payload)

        manifest_path = Path(result["applied"][0]["manifest"])
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["kind"], "aippocampus_storage_eviction_manifest")
        self.assertEqual(manifest["candidate_id"], "retention:rebuildable-main-sqlite")
        self.assertEqual(manifest["eviction_status"], "applied")
        self.assertEqual(manifest["evicted_paths"][0]["relative_path"], "source_index.sqlite")
        self.assertEqual(manifest["source_preconditions"]["raw_or_archive_source"]["status"], "passed")
        self.assertIn("aippocampus_runtime.recall.index_builder", manifest["rebuild_command"])

    def test_apply_health_then_documented_rebuild_path_restores_index(self) -> None:
        apply_result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            retention_report_path=self.retention_path,
            class_filter="rebuildable",
            include_active=True,
            include_paths=True,
        )

        with patch.object(health, "locate_rollout", return_value=self.raw_rollout):
            degraded = health.build_health_report(
                health.HealthOptions(
                    cwd=self.root,
                    index_dir=self.index,
                    clean_source_dir=self.clean,
                    anchors=self.anchors,
                    graphify_corpus=self.root / "graphify-corpus",
                    segments_dir=self.root / "segments",
                    checkpoint_state=self.root / "checkpoint_state.json",
                    registry_dir=self.registry,
                )
            )
        self.assertTrue(degraded["index"]["intentional_eviction"]["detected"])
        self.assertIn(
            "source_index.sqlite intentionally evicted as rebuildable cache",
            degraded["index"]["reasons"],
        )

        with patch("sys.stdout", new=StringIO()):
            rebuild_code = index_builder.main(
                [
                    "--cwd",
                    str(self.root),
                    "--rollout",
                    str(self.raw_rollout),
                    "--output-dir",
                    str(self.index),
                    "--anchors",
                    str(self.anchors),
                    "--no-rag-cache",
                    "--json",
                ]
            )

        with patch.object(health, "locate_rollout", return_value=self.raw_rollout):
            restored = health.build_health_report(
                health.HealthOptions(
                    cwd=self.root,
                    index_dir=self.index,
                    clean_source_dir=self.clean,
                    anchors=self.anchors,
                    graphify_corpus=self.root / "graphify-corpus",
                    segments_dir=self.root / "segments",
                    checkpoint_state=self.root / "checkpoint_state.json",
                    registry_dir=self.registry,
                )
            )

        self.assertTrue(apply_result["ok"])
        self.assertEqual(rebuild_code, 0)
        self.assertTrue(self.sqlite.exists())
        search_hits = rollout_search.search_index_literal(
            self.sqlite,
            ["storage governance rebuild verification phrase"],
            limit=5,
            snippet_chars=200,
        )
        self.assertFalse(restored["index"]["intentional_eviction"]["detected"])
        self.assertNotIn(
            "source_index.sqlite intentionally evicted as rebuildable cache",
            restored["index"]["reasons"],
        )
        self.assertNotIn("source_index.sqlite is missing", restored["index"]["reasons"])
        self.assertEqual(len(search_hits), 1)
        self.assertIn("storage governance rebuild verification phrase", search_hits[0]["snippet"])

    def test_public_health_actions_keep_commands_runnable_after_path_redaction(self) -> None:
        action = health.health_action(
            "build_index",
            "warning",
            "index is stale",
            "aippocampus_runtime.recall.index_builder",
            self.root,
        )
        public = health.public_health_report(
            {
                "cwd": str(self.root),
                "recommended_actions": [action],
                "privacy": {},
            }
        )

        public_action = public["recommended_actions"][0]
        self.assertEqual(public_action["command"], "aippocampus maintenance plan --summary-json")
        self.assertEqual(public_action["facade_command"], "aippocampus maintenance plan --summary-json")
        self.assertNotIn(str(self.root), json.dumps(public, ensure_ascii=False))
        self.assertNotIn("<local-path-redacted>", public_action["command"])

        private = health.public_health_report(
            {
                "cwd": str(self.root),
                "recommended_actions": [action],
                "privacy": {},
            },
            include_paths=True,
        )
        self.assertIn(str(self.root), private["recommended_actions"][0]["facade_command"])

    def test_apply_blocks_raw_or_missing_source_precondition(self) -> None:
        payload = self._retention_payload()
        payload["rollout"] = {"size_bytes": 0}
        self._write_retention_payload(payload)

        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            retention_report_path=self.retention_path,
            class_filter="rebuildable",
            include_active=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked"][0]["reason_code"], "precondition_failed")
        self.assertTrue(self.sqlite.exists())

    def test_apply_blocks_active_thread_without_include_active(self) -> None:
        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            retention_report_path=self.retention_path,
            class_filter="rebuildable",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked"][0]["reason_code"], "precondition_failed")
        self.assertIn("active_thread_exclusion", result["blocked"][0]["failed_preconditions"])
        self.assertTrue(self.sqlite.exists())

    def test_apply_blocks_non_stale_writer_or_export_lease(self) -> None:
        (self.index / ".index-publish.lock").write_text("writer active\n", encoding="utf-8")

        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            retention_report_path=self.retention_path,
            class_filter="rebuildable",
            include_active=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked"][0]["reason_code"], "active_lease")
        self.assertTrue(self.sqlite.exists())

    def test_apply_blocks_target_outside_retention_index_dir(self) -> None:
        outside = self.root / "other-index" / "source_index.sqlite"
        outside.parent.mkdir()
        outside.write_bytes(b"do not delete")
        payload = self._retention_payload()
        for item in payload["items"]:
            if item["id"] == "rebuildable-main-sqlite":
                item["path"] = str(outside)
        self._write_retention_payload(payload)

        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            retention_report_path=self.retention_path,
            class_filter="rebuildable",
            include_active=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked"][0]["reason_code"], "unsafe_target_path")
        self.assertTrue(self.sqlite.exists())
        self.assertTrue(outside.exists())

    def test_apply_rejects_capacity_aggregate_candidates_without_path_level_evidence(self) -> None:
        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            class_filter="rebuildable",
            include_active=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked"][0]["reason_code"], "path_level_retention_required")
        self.assertTrue(self.sqlite.exists())

    def test_dry_run_blocks_old_generation_cleanup_before_reader_pin_ttl_elapsed(self) -> None:
        current = self._write_index_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_index_generation("gen_20260605T005900_lkg", 37)
        old = self._write_index_generation("gen_20260605T004500_old", 29)
        pointer_path = self.index / "source_index.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                    "compatibility_path": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        plan = storage_governance.build_plan(
            self.root,
            registry_dir=self.registry,
        )
        old_generation_candidates = [
            item
            for item in plan["candidates"]
            if item["kind"] == "rebuildable_old_index_generations"
        ]

        self.assertEqual(len(old_generation_candidates), 1)
        candidate = old_generation_candidates[0]
        self.assertEqual(candidate["tier"], "rebuildable_cache")
        self.assertEqual(candidate["bytes"], 29)
        self.assertEqual(candidate["source_report"]["section"], "index_generations")
        self.assertEqual(candidate["source_report"]["current_generation"], current.name)
        self.assertEqual(candidate["source_report"]["last_known_good_generation"], last_known_good.name)
        self.assertEqual(candidate["path"]["relative_path"], f"threads/session-one/index/generations/{old.name}")
        self.assertEqual(
            candidate["preconditions"]["reader_pin_or_ttl_contract"]["status"],
            "blocked",
        )
        self.assertEqual(candidate["source_report"].get("cleanup_status"), "blocked_ttl_window")
        self.assertIn("ttl_window_not_elapsed", candidate["evidence"])
        self._assert_no_workspace_absolute_paths(plan)

    def test_dry_run_marks_old_generation_cleanup_passed_after_reader_pin_ttl(self) -> None:
        current = self._write_index_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_index_generation("gen_20260605T005900_lkg", 37)
        old = self._write_index_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        pointer_path = self.index / "source_index.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                    "compatibility_path": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)

        plan = storage_governance.build_plan(
            self.root,
            registry_dir=self.registry,
            include_paths=True,
        )
        candidate = next(
            item
            for item in plan["candidates"]
            if item["kind"] == "rebuildable_old_index_generations"
        )

        self.assertEqual(
            candidate["preconditions"]["reader_pin_or_ttl_contract"]["status"],
            "passed",
        )
        self.assertEqual(candidate["source_report"].get("cleanup_status"), "eligible")
        self.assertIn("no_active_reader_pins", candidate["evidence"])
        self.assertIn("ttl_window_elapsed", candidate["evidence"])

    def test_dry_run_blocks_old_generation_cleanup_with_active_reader_pin(self) -> None:
        current = self._write_index_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_index_generation("gen_20260605T005900_lkg", 37)
        old = self._write_index_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        self._write_reader_pin(self.index, old)
        pointer_path = self.index / "source_index.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                    "compatibility_path": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)

        plan = storage_governance.build_plan(
            self.root,
            registry_dir=self.registry,
            include_paths=True,
        )
        candidate = next(
            item
            for item in plan["candidates"]
            if item["kind"] == "rebuildable_old_index_generations"
        )

        self.assertEqual(
            candidate["preconditions"]["reader_pin_or_ttl_contract"]["status"],
            "blocked",
        )
        self.assertEqual(candidate["source_report"].get("cleanup_status"), "blocked_active_reader_pin")
        self.assertIn("active_reader_pin_count=1", candidate["evidence"])

    def test_apply_deletes_old_index_generation_after_reader_pin_ttl_contract_passes(self) -> None:
        current = self._write_index_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_index_generation("gen_20260605T005900_lkg", 37)
        old = self._write_index_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        pointer_path = self.index / "source_index.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                    "compatibility_path": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)

        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            class_filter="rebuildable",
            include_active=True,
            include_paths=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(old.exists())
        self.assertTrue(current.exists())
        self.assertTrue(last_known_good.exists())
        self.assertEqual(result["applied"][0]["candidate_id"], f"capacity:session-one:old-index-generation:{old.name}")
        self.assertTrue(
            any(item["candidate_id"] == "capacity:session-one:generated-cache" for item in result["skipped"])
        )
        manifest = json.loads(Path(result["applied"][0]["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["kind_label"], "rebuildable_old_index_generations")
        self.assertEqual(manifest["source_preconditions"]["reader_pin_or_ttl_contract"]["status"], "passed")

    def test_apply_blocks_generation_cleanup_when_pointer_disappears_after_planning(self) -> None:
        current = self._write_index_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_index_generation("gen_20260605T005900_lkg", 37)
        old = self._write_index_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        pointer_path = self.index / "source_index.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                    "compatibility_path": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)
        plan = storage_governance.build_plan(
            self.root,
            registry_dir=self.registry,
            include_paths=True,
        )
        pointer_path.unlink()

        result = storage_eviction.apply_rebuildable_evictions(
            plan,
            include_active=True,
            include_paths=True,
        )

        self.assertFalse(result["applied"])
        self.assertTrue(old.exists())
        blocked = [
            item
            for item in result["blocked"]
            if item["candidate_id"] == f"capacity:session-one:old-index-generation:{old.name}"
        ]
        self.assertEqual(blocked[0]["reason_code"], "precondition_failed")
        self.assertIn("last_known_good_pointer", blocked[0]["failed_preconditions"])

    def test_apply_blocks_legacy_path_only_pointer_that_now_protects_generation(self) -> None:
        current = self._write_index_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_index_generation("gen_20260605T005900_lkg", 37)
        old = self._write_index_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        pointer_path = self.index / "source_index.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                    "compatibility_path": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)
        plan = storage_governance.build_plan(
            self.root,
            registry_dir=self.registry,
            include_paths=True,
        )
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current": f"generations/{old.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)

        result = storage_eviction.apply_rebuildable_evictions(
            plan,
            include_active=True,
            include_paths=True,
        )

        self.assertFalse(result["applied"])
        self.assertTrue(old.exists())
        blocked = [
            item
            for item in result["blocked"]
            if item["candidate_id"] == f"capacity:session-one:old-index-generation:{old.name}"
        ]
        self.assertIn("last_known_good_pointer", blocked[0]["failed_preconditions"])

    def test_dry_run_identifies_old_segment_generation_gc_candidates_with_reader_pin_contract(self) -> None:
        current = self._write_segment_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_segment_generation("gen_20260605T005900_lkg", 37)
        old = self._write_segment_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        old_bytes = sum(path.stat().st_size for path in old.rglob("*") if path.is_file())
        segments_dir = self.index / "segments"
        pointer_path = segments_dir / "segments.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_segments_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/manifest.json",
                    "last_known_good": f"generations/{last_known_good.name}/manifest.json",
                    "stable": "manifest.json",
                    "compatibility_path": "manifest.json",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)

        plan = storage_governance.build_plan(self.root, registry_dir=self.registry)
        old_generation_candidates = [
            item
            for item in plan["candidates"]
            if item["kind"] == "rebuildable_old_segment_generations"
        ]

        self.assertEqual(len(old_generation_candidates), 1)
        candidate = old_generation_candidates[0]
        self.assertEqual(candidate["tier"], "rebuildable_cache")
        self.assertEqual(candidate["bytes"], old_bytes)
        self.assertEqual(candidate["source_report"]["section"], "segment_generations")
        self.assertEqual(candidate["source_report"]["current_generation"], current.name)
        self.assertEqual(candidate["source_report"]["last_known_good_generation"], last_known_good.name)
        self.assertEqual(
            candidate["path"]["relative_path"],
            f"threads/session-one/index/segments/generations/{old.name}",
        )
        self.assertEqual(
            candidate["preconditions"]["reader_pin_or_ttl_contract"]["status"],
            "passed",
        )
        self.assertEqual(candidate["source_report"].get("cleanup_status"), "eligible")
        self.assertTrue(old.exists())
        self._assert_no_workspace_absolute_paths(plan)

    def test_apply_deletes_old_segment_generation_after_reader_pin_ttl_contract_passes(self) -> None:
        current = self._write_segment_generation("gen_20260605T010000_current", 41)
        old = self._write_segment_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        segments_dir = self.index / "segments"
        (segments_dir / "manifest.json").write_text(
            (current / "manifest.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        pointer_path = segments_dir / "segments.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_segments_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": current.name,
                    "current": f"generations/{current.name}/manifest.json",
                    "last_known_good": f"generations/{current.name}/manifest.json",
                    "stable": "manifest.json",
                    "compatibility_path": "manifest.json",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)

        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            class_filter="rebuildable",
            include_active=True,
            include_paths=True,
        )

        self.assertTrue(result["ok"])
        self.assertFalse(old.exists())
        self.assertTrue(current.exists())
        self.assertEqual(result["applied"][0]["candidate_id"], f"capacity:session-one:old-segment-generation:{old.name}")

    def test_apply_blocks_old_segment_generation_when_rebuild_lease_is_active(self) -> None:
        current = self._write_segment_generation("gen_20260605T010000_current", 41)
        old = self._write_segment_generation("gen_20260605T004500_old", 29)
        self._mark_generation_old(old)
        segments_dir = self.index / "segments"
        (segments_dir / "manifest.json").write_text(
            (current / "manifest.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        pointer_path = segments_dir / "segments.pointer.json"
        pointer_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_segments_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": current.name,
                    "current": f"generations/{current.name}/manifest.json",
                    "last_known_good": f"generations/{current.name}/manifest.json",
                    "stable": "manifest.json",
                    "compatibility_path": "manifest.json",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._mark_path_old(pointer_path)
        (segments_dir / ".rebuild.lock").write_text("active segment writer\n", encoding="utf-8")

        result = storage_governance.apply_plan(
            self.root,
            registry_dir=self.registry,
            class_filter="rebuildable",
            include_active=True,
            include_paths=True,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(old.exists())
        blocked = [
            item
            for item in result["blocked"]
            if item["candidate_id"] == f"capacity:session-one:old-segment-generation:{old.name}"
        ]
        self.assertEqual(blocked[0]["reason_code"], "active_lease")

    def test_apply_cli_returns_json_result(self) -> None:
        with patch("sys.stdout", new=StringIO()) as stdout:
            code = storage_governance.main(
                [
                    "gc",
                    "--apply",
                    "--cwd",
                    str(self.root),
                    "--registry-dir",
                    str(self.registry),
                    "--retention-report",
                    str(self.retention_path),
                    "--class",
                    "rebuildable",
                    "--include-active",
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "apply")
        self.assertEqual(payload["metrics"]["eviction_applied_count"], 1)


if __name__ == "__main__":
    unittest.main()
