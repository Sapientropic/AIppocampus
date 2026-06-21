from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from aippocampus_runtime import health as health
from aippocampus_runtime.warm_ambient.hook_seen_threads import (
    hook_seen_ledger_path_for_registry,
    hook_seen_thread_ref,
    record_hook_seen_thread,
)
from tests.aippocampus.health_fixtures import health_workspace


class AippocampusHealthTests(unittest.TestCase):
    def test_agent_json_health_is_compact_and_path_redacted(self) -> None:
        private_path = "C:/private/aippocampus/clean-source/messages.jsonl"
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": False,
                    "cwd": private_path,
                    "checks": [{"name": "clean_source", "path": private_path}],
                    "recommended_actions": [
                        {
                            "id": "refresh_clean_source",
                            "reason": "clean source is stale",
                            "command": "python -m aippocampus_runtime.source.clean_source",
                        }
                    ],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])

        raw = stdout.getvalue()
        payload = json.loads(raw)
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_health_card")
        self.assertEqual(payload["detail"], "compact")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["foreground_action"]["id"], "refresh_clean_source")
        self.assertEqual(payload["foreground_action"]["id"], "refresh_clean_source")
        self.assertNotIn("recommended_actions", payload)
        self.assertNotIn("freshness", payload)
        self.assertNotIn("storage_pressure", payload)
        self.assertNotIn("host_state_confounds", payload)
        self.assertNotIn(private_path, raw)

    def test_agent_json_health_does_not_promote_advisory_actions_when_ready(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "recommended_actions": [
                        {
                            "id": "prepare_graphify_corpus",
                            "severity": "info",
                            "reason": "graphify corpus was prepared from an older index manifest",
                            "facade_command": "aippocampus maintenance --cwd C:/private/work",
                        },
                        {
                            "id": "checkpoint",
                            "severity": "suggestion",
                            "reason": "checkpoint can wait until idle",
                            "facade_command": "aippocampus maintenance --cwd C:/private/work",
                        },
                    ],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["foreground_action"]["id"], "continue_with_nonblocking_maintenance")
        self.assertTrue(payload["foreground_action"]["primary"]["ordinary_first_recall_usable"])
        self.assertEqual(
            payload["maintenance_summary"]["recommended_action_ids"][0],
            "prepare_graphify_corpus",
        )

    def test_exit_code_stays_zero_for_ready_with_optional_maintenance(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "product_readiness": {
                        "status": "ready_with_optional_maintenance",
                        "ready": True,
                        "ordinary_first_recall_usable": True,
                        "maintenance_recommended": True,
                        "maintenance_required_before_recall": False,
                    },
                    "recommended_actions": [
                        {
                            "id": "checkpoint",
                            "severity": "suggestion",
                            "reason": "checkpoint can wait until idle",
                            "facade_command": "aippocampus maintenance --cwd C:/private/work",
                        }
                    ],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json", "--exit-code"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ordinary_first_recall_usable"])
        self.assertEqual((payload["first_recall_phase"], payload["cold_start_expected"]), ("steady_state_available", False))
        self.assertEqual(payload["readiness_card"]["state"], "ready_with_optional_maintenance")
        self.assertTrue(payload["readiness_card"]["usable_now"])
        self.assertFalse(payload["readiness_card"]["blocks_first_recall"])

    def test_default_exit_code_is_nonzero_when_first_recall_is_blocked(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": False,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "product_readiness": {
                        "status": "needs_maintenance",
                        "ready": False,
                        "ordinary_first_recall_usable": False,
                        "maintenance_recommended": True,
                        "maintenance_required_before_recall": True,
                    },
                    "recommended_actions": [
                        {
                            "id": "refresh_clean_source",
                            "severity": "critical",
                            "reason": "clean source missing",
                            "facade_command": "aippocampus maintenance --cwd C:/private/work",
                        }
                    ],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ordinary_first_recall_usable"])

    def test_agent_json_health_uses_no_action_only_when_clean_ready(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "recommended_actions": [],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["foreground_action"]["id"], "no_action")
        self.assertEqual(payload["maintenance_summary"]["recommended_action_count"], 0)

    def test_agent_json_preserves_high_severity_storage_pressure_action(self) -> None:
        pressure_action = {
            "id": "storage_gc_rebuildable_cache",
            "severity": "warning",
            "reason": "Generated rebuildable cache pressure is high",
            "facade_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        }
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": False,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "recommended_actions": [
                        {"id": "refresh_clean_source", "severity": "warning", "reason": "stale"},
                        {"id": "build_index", "severity": "warning", "reason": "stale"},
                        {"id": "prepare_graphify_corpus", "severity": "info", "reason": "old"},
                        pressure_action,
                    ],
                    "storage_pressure": {
                        "available": True,
                        "pressure": True,
                        "reasons": ["reclaimable_rebuildable_cache_bytes_high"],
                    },
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])

        payload = json.loads(stdout.getvalue())
        action_ids = payload["maintenance_summary"]["recommended_action_ids"]

        self.assertEqual(code, 0)
        self.assertIn("storage_gc_rebuildable_cache", action_ids)
        self.assertNotIn("storage_pressure", payload)
        self.assertTrue(payload["maintenance_summary"]["storage"]["pressure"])

    def test_agent_json_storage_pressure_is_visible_but_not_primary_when_ready(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "recommended_actions": [
                        {
                            "id": "storage_gc_rebuildable_cache",
                            "severity": "warning",
                            "reason": "Generated rebuildable cache pressure is high",
                            "facade_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                        }
                    ],
                    "product_readiness": {
                        "ready": True,
                        "ordinary_first_recall_usable": True,
                        "maintenance_recommended": True,
                        "storage_pressure_cleanup_recommended": True,
                        "status": "ready_with_storage_pressure",
                    },
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["foreground_action"]["id"], "continue_with_nonblocking_maintenance")
        self.assertEqual(payload["foreground_action"]["when_idle"]["id"], "review_storage_gc_summary")
        self.assertEqual(
            payload["foreground_action"]["when_idle"]["command"],
            "aippocampus storage gc --dry-run --summary-json --cwd .",
        )
        self.assertEqual(
            payload["maintenance_summary"]["storage"]["bounded_audit_available"],
            True,
        )
        self.assertEqual(
            payload["maintenance_summary"]["recommended_action_ids"][0],
            "storage_gc_rebuildable_cache",
        )
        self.assertNotIn("storage_pressure", payload)

    def test_agent_json_freshness_degraded_keeps_executable_latest_guidance(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "product_readiness": {
                        "ready": True,
                        "ordinary_first_recall_usable": True,
                        "freshness_degraded": True,
                        "latest_current_thread_may_be_missing": True,
                        "maintenance_recommended": True,
                        "status": "ready_with_freshness_degraded",
                    },
                    "recommended_actions": [
                        {
                            "id": "build_clean_source",
                            "severity": "warning",
                            "reason": "latest clean source missing",
                            "facade_command": "aippocampus maintenance",
                        },
                        {
                            "id": "build_index",
                            "severity": "warning",
                            "reason": "latest index missing",
                            "facade_command": "aippocampus maintenance",
                        },
                    ],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["foreground_action"]["id"], "continue_with_nonblocking_maintenance")
        self.assertEqual(payload["readiness_card"]["state"], "ready_with_freshness_degraded")
        self.assertTrue(payload["readiness_card"]["usable_now"])
        self.assertFalse(payload["readiness_card"]["blocks_first_recall"])
        self.assertTrue(payload["readiness_card"]["blocks_exact_latest"])
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("review_maintenance_plan", action_ids)
        self.assertIn("apply_after_user_consent", action_ids)
        review_action = next(
            action for action in payload["safe_next_actions"] if action["id"] == "review_maintenance_plan"
        )
        apply_action = next(
            action for action in payload["safe_next_actions"] if action["id"] == "apply_after_user_consent"
        )
        self.assertEqual(review_action["command"], "aippocampus maintenance plan --summary-json")
        self.assertEqual(apply_action["command"], "aippocampus maintenance apply --summary-json")
        self.assertTrue(apply_action["write_boundary"]["explicit_user_consent_required"])
        self.assertTrue(payload["foreground_action"]["primary"]["ordinary_first_recall_usable"])
        self.assertTrue(payload["blocks_exact_latest_claims"])
        self.assertNotIn("freshness", payload)

    def test_agent_json_health_card_excludes_operator_only_objects(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [{"name": f"check-{index}"} for index in range(20)],
                    "product_readiness": {
                        "ready": True,
                        "ordinary_first_recall_usable": True,
                        "freshness_degraded": True,
                        "latest_current_thread_may_be_missing": True,
                        "maintenance_recommended": True,
                        "storage_pressure_cleanup_recommended": True,
                        "status": "ready_with_freshness_degraded",
                    },
                    "freshness": {
                        "latest_visible_gap": True,
                        "index_message_delta": 12,
                        "clean_source_message_delta": 4,
                        "rollout_message_count": 999,
                    },
                    "storage_pressure": {
                        "available": True,
                        "pressure": True,
                        "metrics": {"generated_index_amplification_ratio": 16.0},
                        "dry_run_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                    },
                    "host_state_confounds": {
                        "available": True,
                        "artifact_scope": "codex_host_state_not_aippocampus_registry",
                        "logs_db_wal": {"total_bytes": 123456},
                    },
                    "recommended_actions": [
                        {
                            "id": "build_clean_source",
                            "severity": "warning",
                            "reason": "latest clean source missing",
                            "facade_command": "aippocampus maintenance",
                        },
                        {
                            "id": "storage_gc_rebuildable_cache",
                            "severity": "warning",
                            "reason": "generated cache pressure",
                            "facade_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                        },
                    ],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--json"])

        raw = stdout.getvalue()
        payload = json.loads(raw)

        self.assertEqual(code, 0)
        self.assertLess(len(raw), 3200)
        self.assertEqual(payload["kind"], "aippocampus_health_card")
        self.assertTrue(payload["ordinary_first_recall_usable"])
        self.assertTrue(payload["blocks_exact_latest_claims"])
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("review_maintenance_plan", action_ids)
        self.assertIn("apply_after_user_consent", action_ids)
        self.assertEqual(
            payload["foreground_action"]["when_idle"]["command"],
            "aippocampus storage gc --dry-run --summary-json --cwd .",
        )
        self.assertEqual(
            payload["maintenance_summary"]["storage"]["bounded_audit_available"],
            True,
        )
        for operator_key in (
            "freshness",
            "storage_pressure",
            "host_state_confounds",
            "recommended_actions",
            "checks",
            "product_readiness",
            "cwd",
        ):
            self.assertNotIn(operator_key, payload)

    def test_health_json_detail_full_keeps_operator_diagnostics(self) -> None:
        with (
            mock.patch(
                "aippocampus_runtime.health.build_health_report",
                return_value={
                    "ok": True,
                    "cwd": "C:/private/work",
                    "freshness": {"latest_visible_gap": False},
                    "storage_pressure": {"available": True, "pressure": False},
                    "host_state_confounds": {"available": True},
                    "recommended_actions": [],
                    "privacy": {},
                },
            ),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--json", "--detail", "full"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertNotEqual(payload.get("kind"), "aippocampus_health_card")
        self.assertIn("freshness", payload)
        self.assertIn("storage_pressure", payload)
        self.assertIn("host_state_confounds", payload)

    def test_human_health_prints_copy_pasteable_next_commands(self) -> None:
        payload = {
            "ok": False,
            "rollout": {"path": "rollout.jsonl", "size": 10, "message_count": 2},
            "index": {"stale": True, "message_delta": 1, "byte_delta": 1, "rag": {}},
            "clean_source": {"stale": True},
            "segments": {"exists": False, "needed": False},
            "checkpoint": {"due": False},
            "graphify": {"stale": False},
            "storage": {},
            "question_stats": {},
            "background_cognition": {},
            "logs": {},
            "health_trajectory": {},
            "product_readiness": {
                "status": "needs_maintenance",
                "ready": False,
                "blocking_action_count": 2,
            },
            "recommended_actions": [
                {
                    "id": "build_clean_source",
                    "severity": "warning",
                    "reason": "latest visible clean-source messages are missing",
                    "command": "python -m aippocampus_runtime.source.clean_source --cwd .",
                    "facade_command": "aippocampus maintenance --cwd .",
                },
                {
                    "id": "build_index",
                    "severity": "warning",
                    "reason": "latest visible messages are newer than the index",
                    "command": "python -m aippocampus_runtime.recall.index_builder --cwd .",
                    "facade_command": "aippocampus maintenance --cwd .",
                },
            ],
        }

        with mock.patch("sys.stdout", new=StringIO()) as stdout:
            health.render_health_text(payload)

        text = stdout.getvalue()
        self.assertIn("AIppocampus health", text)
        self.assertIn("readiness: partial (needs_maintenance)", text)
        self.assertIn("can_continue_recall_now: partial", text)
        self.assertIn("blocks_exact_latest_claims: no", text)
        self.assertIn("best next action: build_clean_source", text)
        self.assertIn("repair: aippocampus maintenance --cwd .", text)
        self.assertNotIn("fix:", text)
        self.assertIn("recommended actions:", text)
        self.assertIn("Next actions:", text)
        self.assertIn("1. build_clean_source [repair]: aippocampus maintenance --cwd .", text)
        self.assertIn("2. build_index [repair]: aippocampus maintenance --cwd .", text)
        self.assertNotIn("python -m aippocampus_runtime", text)

    def test_human_health_mentions_plan_when_freshness_degraded_but_recall_usable(self) -> None:
        payload = {
            "ok": True,
            "rollout": {"path": "rollout.jsonl", "size": 10, "message_count": 2},
            "index": {"stale": False, "message_delta": 0, "byte_delta": 0, "rag": {}},
            "clean_source": {"stale": False, "exists": True},
            "segments": {"exists": False, "needed": False},
            "checkpoint": {"due": False},
            "graphify": {"stale": False},
            "storage": {},
            "question_stats": {},
            "background_cognition": {},
            "logs": {},
            "health_trajectory": {},
            "product_readiness": {
                "status": "ready_with_freshness_degraded",
                "ready": True,
                "ordinary_first_recall_usable": True,
                "freshness_degraded": True,
                "latest_current_thread_may_be_missing": True,
            },
            "recommended_actions": [
                {
                    "id": "build_clean_source",
                    "severity": "warning",
                    "reason": "latest visible clean-source messages are missing",
                    "facade_command": "aippocampus maintenance --cwd .",
                }
            ],
        }

        with mock.patch("sys.stdout", new=StringIO()) as stdout:
            health.render_health_text(payload)

        text = stdout.getvalue()
        self.assertIn("can_continue_recall_now: yes", text)
        self.assertIn("blocks_exact_latest_claims: yes", text)
        self.assertIn("inspect: aippocampus maintenance plan --summary-json", text)

    def write_rollout(
        self,
        path: Path,
        cwd: Path,
        *,
        session_id: str = "health-session",
        include_second_turn: bool = False,
    ) -> None:
        rows = [
            {
                "type": "session_meta",
                "payload": {
                    "id": session_id,
                    "timestamp": "2026-06-05T00:00:00Z",
                    "cwd": str(cwd),
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-05T00:00:01Z",
                "payload": {
                    "type": "user_message",
                    "message": "first source-backed freshness question",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-05T00:00:02Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "commentary",
                    "message": "checking local source",
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-06-05T00:00:03Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "first final source-backed answer",
                },
            },
        ]
        if include_second_turn:
            rows.extend(
                [
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-05T00:01:01Z",
                        "payload": {
                            "type": "user_message",
                            "message": "latest source-backed freshness marker",
                        },
                    },
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-05T00:01:02Z",
                        "payload": {
                            "type": "agent_message",
                            "phase": "final_answer",
                            "message": "latest final answer must be searchable",
                        },
                    },
                ]
            )
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def write_current_artifacts(
        self,
        root: Path,
        workspace: Path,
        rollout: Path,
        *,
        index_created_at: str = "2026-06-01T00:00:00Z",
        clean_created_at: str = "2026-06-01T00:00:00Z",
        rag_enabled: bool = True,
        clean_schema: int = 2,
        clean_upgrade_contract: bool = True,
    ) -> dict[str, Path]:
        anchors = workspace / "thread-anchors.md"
        anchors.write_text("# Anchors\n", encoding="utf-8")
        visibility = health.rollout_visibility_stats(rollout)
        current_message_count, last_line = health.count_messages(rollout)
        index_dir = root / "index"
        index_dir.mkdir()
        manifest = {
            "created_at": index_created_at,
            "message_count": current_message_count,
            "source_rollout_size": rollout.stat().st_size,
            "last_message_line": last_line,
            "anchor_sha256": health.file_sha256(anchors),
        }
        if rag_enabled:
            manifest["rag"] = {"enabled": True, "chunk_count": 1}
        (index_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
        (index_dir / "source_index.sqlite").write_bytes(b"index")
        clean = root / "clean-source"
        clean.mkdir()
        clean_manifest = {
            "created_at": clean_created_at,
            "schema_version": clean_schema,
            "source_rollout_size": rollout.stat().st_size,
            "message_count": visibility.expected_clean_source_message_count,
            "turn_count": visibility.expected_clean_source_turn_count,
            "source_texture_count": 1,
            "source_texture_policy": {
                "boundary": "source texture rows are rebuildable interpretation inputs, not source truth.",
            },
        }
        if clean_upgrade_contract:
            clean_manifest["upgrade_contract"] = {"source_backed": True}
        (clean / "manifest.json").write_text(json.dumps(clean_manifest), encoding="utf-8")
        (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
        (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
        (clean / "source-texture.jsonl").write_text(
            json.dumps(
                {
                    "texture_id": "tex_1",
                    "signal_kind": "self_correction_signal",
                    "truth_boundary": "texture_signal_not_source_fact",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        graphify = root / "graphify-corpus"
        graphify.mkdir()
        (graphify / "corpus_manifest.json").write_text(
            json.dumps({"source_index_manifest_sha256": health.file_sha256(index_dir / "manifest.json")}),
            encoding="utf-8",
        )
        return {
            "anchors": anchors,
            "index_dir": index_dir,
            "clean_source_dir": clean,
            "graphify_corpus": graphify,
            "segments_dir": root / "segments",
            "checkpoint_state": root / "checkpoint_state.json",
        }

    def write_latest_turn_gap_artifacts(
        self,
        root: Path,
        workspace: Path,
    ) -> tuple[Path, dict[str, Path]]:
        rollout = workspace / "rollout.jsonl"
        self.write_rollout(rollout, workspace, include_second_turn=False)
        current_size = rollout.stat().st_size
        rollout.write_text(
            rollout.read_text(encoding="utf-8")
            + "\n".join(
                json.dumps(row, ensure_ascii=False)
                for row in [
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-05T00:01:01Z",
                        "payload": {
                            "type": "user_message",
                            "message": "latest source-backed freshness marker",
                        },
                    },
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-05T00:01:02Z",
                        "payload": {
                            "type": "agent_message",
                            "phase": "final_answer",
                            "message": "latest final answer must be searchable",
                        },
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        anchors = workspace / "thread-anchors.md"
        anchors.write_text("# Anchors\n", encoding="utf-8")
        index_dir = root / "index"
        index_dir.mkdir()
        (index_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "created_at": "2026-06-05T00:00:03Z",
                    "message_count": 3,
                    "source_rollout_size": current_size,
                    "last_message_line": 4,
                    "anchor_sha256": health.file_sha256(anchors),
                    "rag": {"enabled": True},
                }
            ),
            encoding="utf-8",
        )
        (index_dir / "messages.jsonl").write_text("{}\n", encoding="utf-8")
        (index_dir / "source_index.sqlite").write_bytes(b"index")
        clean = root / "clean-source"
        clean.mkdir()
        (clean / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "upgrade_contract": {"source_backed": True},
                    "source_rollout_size": current_size,
                    "message_count": 2,
                    "turn_count": 1,
                }
            ),
            encoding="utf-8",
        )
        (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
        (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
        return rollout, {
            "anchors": anchors,
            "index_dir": index_dir,
            "clean_source_dir": clean,
            "graphify_corpus": root / "graphify-corpus",
            "segments_dir": root / "segments",
            "checkpoint_state": root / "checkpoint_state.json",
        }

    def test_registry_cache_pressure_report_uses_storage_governance_metrics(self) -> None:
        with mock.patch(
            "aippocampus_runtime.ops.storage_governance.build_plan",
            return_value={
                "metrics": {
                    "reclaimable_rebuildable_bytes": 2 * 1024 * 1024 * 1024,
                    "reclaimable_rebuildable_human": "2.0 GB",
                    "protected_source_bytes": 128 * 1024 * 1024,
                    "protected_source_human": "128.0 MB",
                    "generated_index_amplification_ratio": 16.0,
                    "eviction_candidate_count": 140,
                }
            },
        ) as build_plan:
            report = health.registry_cache_pressure_report(
                Path("workspace"),
                Path("registry"),
            )

        build_plan.assert_called_once()
        self.assertTrue(report["available"])
        self.assertTrue(report["pressure"])
        self.assertEqual(report["status"], "pressure")
        self.assertIn("reclaimable_rebuildable_cache_bytes_high", report["reasons"])
        self.assertEqual(
            report["dry_run_command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(
            report["summary_command"],
            "aippocampus storage gc --dry-run --summary-json --cwd .",
        )
        self.assertEqual(
            report["repair_command"],
            "aippocampus storage gc --apply --class rebuildable --summary-json --cwd .",
        )
        self.assertTrue(report["source_history_protected"])
        self.assertFalse(report["privacy_boundary"]["paths_included"])

    def test_health_surfaces_generated_cache_pressure_as_safe_repair_action(self) -> None:
        with health_workspace() as (root, workspace):
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(root, workspace, rollout)
            registry_dir = root / "registry"
            registry_dir.mkdir()
            (registry_dir / "threads.json").write_text('{"threads":[]}', encoding="utf-8")

            pressure = {
                "available": True,
                "status": "pressure",
                "pressure": True,
                "reasons": ["reclaimable_rebuildable_cache_bytes_high"],
                "metrics": {
                    "reclaimable_rebuildable_human": "2.0 GB",
                    "generated_index_amplification_ratio": 16.0,
                },
                "dry_run_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
                "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
                "repair_command": "aippocampus storage gc --apply --class rebuildable --summary-json --cwd .",
                "source_history_protected": True,
                "foreground_blocking": False,
            }
            with (
                mock.patch.object(health, "locate_rollout", return_value=rollout),
                mock.patch.object(
                    health,
                    "registry_cache_pressure_report",
                    return_value=pressure,
                ),
            ):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        registry_dir=registry_dir,
                        include_operator_diagnostics=True,
                        include_expensive_diagnostics=True,
                        **paths,
                    )
                )

        action_ids = [item["id"] for item in payload["recommended_actions"]]
        self.assertIn("storage_gc_rebuildable_cache", action_ids)
        action = next(
            item
            for item in payload["recommended_actions"]
            if item["id"] == "storage_gc_rebuildable_cache"
        )
        self.assertEqual(action["severity"], "warning")
        self.assertEqual(
            action["command"],
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        )
        self.assertEqual(payload["storage_pressure"], pressure)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["product_readiness"]["ordinary_first_recall_usable"])
        self.assertFalse(payload["product_readiness"]["maintenance_required_before_recall"])
        self.assertTrue(payload["product_readiness"]["storage_pressure_cleanup_recommended"])

    def test_health_reports_codex_host_state_confounds_without_paths_or_ids(self) -> None:
        with health_workspace() as (root, workspace):
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(root, workspace, rollout)
            registry_dir = root / "registry"
            registry_dir.mkdir()
            (registry_dir / "threads.json").write_text('{"threads":[]}', encoding="utf-8")
            codex = root / "codex-home"
            (codex / "logs").mkdir(parents=True)
            (codex / "sessions" / "private-session-id").mkdir(parents=True)
            (codex / "logs" / "state.sqlite").write_bytes(b"x" * 128)
            (codex / "logs" / "state.sqlite-wal").write_bytes(b"y" * 64)
            (codex / "sessions" / "private-session-id" / "rollout.jsonl").write_bytes(b"z" * 256)
            (codex / "threads.json").write_text(
                '{"threads":[{"id":"private-thread-id"}]}',
                encoding="utf-8",
            )

            with (
                mock.patch.object(health, "codex_home", return_value=codex),
                mock.patch.object(health, "locate_rollout", return_value=rollout),
            ):
                payload = health.build_health_report(
                    health.HealthOptions(cwd=workspace, registry_dir=registry_dir, include_operator_diagnostics=True, **paths)
                )

        confounds = payload["host_state_confounds"]
        encoded = json.dumps(confounds, ensure_ascii=False)

        self.assertTrue(confounds["available"])
        self.assertEqual(confounds["artifact_scope"], "codex_host_state_not_aippocampus_registry")
        self.assertGreater(confounds["logs_db_wal"]["total_bytes"], 0)
        self.assertGreater(confounds["session_store"]["total_bytes"], 0)
        self.assertTrue(confounds["thread_list"]["available"])
        self.assertFalse(confounds["privacy_boundary"]["paths_included"])
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("private-session-id", encoded)
        self.assertNotIn("private-thread-id", encoded)

    def test_health_keeps_small_latest_turn_gap_advisory_before_bulk_stale_threshold(self) -> None:
        with health_workspace() as (root, workspace):
            rollout, paths = self.write_latest_turn_gap_artifacts(root, workspace)

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        **paths,
                        max_stale_messages=25,
                        max_stale_bytes=5 * 1024 * 1024,
                    )
                )

        action_ids = [item["id"] for item in payload["recommended_actions"]]

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["freshness"]["latest_visible_gap"])
        self.assertTrue(payload["freshness"]["raw_newer_than_index"])
        self.assertTrue(payload["freshness"]["raw_newer_than_clean_source"])
        self.assertEqual(payload["index"]["message_delta"], 2)
        self.assertEqual(payload["clean_source"]["expected_message_delta"], 2)
        self.assertEqual(payload["product_readiness"]["status"], "ready_with_live_delta")
        self.assertNotIn("build_index", action_ids)
        self.assertNotIn("build_clean_source", action_ids)

    def test_health_recommends_source_maintenance_at_bulk_stale_threshold(self) -> None:
        with health_workspace() as (root, workspace):
            rollout, paths = self.write_latest_turn_gap_artifacts(root, workspace)

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        **paths,
                        max_stale_messages=2,
                        max_stale_bytes=5 * 1024 * 1024,
                    )
                )

        action_ids = [item["id"] for item in payload["recommended_actions"]]

        self.assertTrue(payload["ok"])
        self.assertIn("build_index", action_ids)
        self.assertIn("build_clean_source", action_ids)
        self.assertEqual(payload["product_readiness"]["status"], "ready_with_freshness_degraded")
        self.assertTrue(payload["product_readiness"]["ordinary_first_recall_usable"])
        self.assertTrue(payload["product_readiness"]["freshness_degraded"])
        self.assertTrue(payload["product_readiness"]["latest_current_thread_may_be_missing"])
        self.assertFalse(payload["product_readiness"]["maintenance_required_before_recall"])
        self.assertLess(action_ids.index("build_clean_source"), action_ids.index("build_index"))
        index_action = next(item for item in payload["recommended_actions"] if item["id"] == "build_index")
        self.assertEqual(index_action["depends_on"], ["build_clean_source"])
        self.assertEqual(index_action["blocked_until"], "build_clean_source_current")
        self.assertTrue(
            any("latest visible" in item["reason"] for item in payload["recommended_actions"])
        )

    def test_health_treats_one_live_message_delta_as_product_ready(self) -> None:
        with health_workspace() as (root, workspace):
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(root, workspace, rollout)
            rollout.write_text(
                rollout.read_text(encoding="utf-8")
                + json.dumps(
                    {
                        "type": "event_msg",
                        "timestamp": "2026-06-05T00:02:01Z",
                        "payload": {
                            "type": "agent_message",
                            "phase": "commentary",
                            "message": "health command is running",
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(health.HealthOptions(cwd=workspace, **paths))

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["freshness"]["raw_newer_than_index"])
        self.assertEqual(payload["index"]["message_delta"], 1)
        self.assertEqual(payload["product_readiness"]["status"], "ready_with_live_delta")
        self.assertTrue(payload["product_readiness"]["live_delta_tolerated"])
        self.assertNotIn("build_index", [item["id"] for item in payload["recommended_actions"]])

    def test_health_cli_json_redacts_paths_by_default_and_can_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(root, workspace, rollout)
            args = [
                "--cwd",
                str(workspace),
                "--index-dir",
                str(paths["index_dir"]),
                "--clean-source-dir",
                str(paths["clean_source_dir"]),
                "--graphify-corpus",
                str(paths["graphify_corpus"]),
                "--segments-dir",
                str(paths["segments_dir"]),
                "--checkpoint-state",
                str(paths["checkpoint_state"]),
                "--anchors",
                str(paths["anchors"]),
                "--json",
            ]

            with (
                mock.patch.object(health, "locate_rollout", return_value=rollout),
                mock.patch("sys.stdout", new=StringIO()) as stdout,
            ):
                code = health.main(args)
            public_payload = json.loads(stdout.getvalue())

            with (
                mock.patch.object(health, "locate_rollout", return_value=rollout),
                mock.patch("sys.stdout", new=StringIO()) as stdout,
            ):
                include_code = health.main(
                    [
                        *[arg for arg in args if arg != "--json"],
                        "--operator-json",
                        "--json",
                        "--include-paths",
                    ]
                )
            private_payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(include_code, 0)
        public_encoded = json.dumps(public_payload, ensure_ascii=False)
        self.assertEqual(public_payload["detail"], "compact")
        self.assertNotIn(str(workspace), public_encoded)
        self.assertEqual(public_payload["kind"], "aippocampus_health_card")
        self.assertNotIn("cwd", public_payload)
        self.assertNotIn("privacy", public_payload)
        self.assertEqual(private_payload["cwd"], str(workspace.resolve()))
        self.assertTrue(private_payload["privacy"]["paths_included"])

    def test_health_text_render_preserves_rollout_metadata_after_path_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(root, workspace, rollout)

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(health.HealthOptions(cwd=workspace, **paths))

        public_payload = health.public_health_report(payload)

        self.assertEqual(public_payload["rollout"]["path"], health.LOCAL_PATH_REDACTION)
        self.assertEqual(public_payload["rollout"]["size"], payload["rollout"]["size"])
        self.assertEqual(
            public_payload["rollout"]["message_count"],
            payload["rollout"]["message_count"],
        )
        with mock.patch("sys.stdout", new=StringIO()) as stdout:
            health.render_health_text(public_payload)

        self.assertIn(f"rollout: {health.LOCAL_PATH_REDACTION}", stdout.getvalue())

    def test_health_trajectory_reports_age_without_age_only_preemptive_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(
                root,
                workspace,
                rollout,
                index_created_at="2026-06-01T00:00:00Z",
                clean_created_at="2026-06-01T00:00:00Z",
            )

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(health.HealthOptions(cwd=workspace, **paths))

        trajectory = payload["health_trajectory"]
        self.assertGreater(trajectory["index_age_hours"], 0)
        self.assertGreater(trajectory["clean_source_age_hours"], 0)
        self.assertEqual(trajectory["expected_degradation"], "low")
        self.assertEqual(trajectory["preemptive_actions"], [])
        self.assertNotIn("age_only", trajectory["preemptive_reason_codes"])

    def test_health_trajectory_emits_preemptive_actions_for_concrete_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(
                root,
                workspace,
                rollout,
                rag_enabled=False,
                clean_schema=1,
                clean_upgrade_contract=False,
            )

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(health.HealthOptions(cwd=workspace, **paths))

        trajectory = payload["health_trajectory"]
        self.assertEqual(
            trajectory["preemptive_actions"],
            ["build_clean_source", "build_index"],
        )
        self.assertIn("rag_cache_missing", trajectory["preemptive_reason_codes"])
        self.assertIn("clean_source_schema_drift", trajectory["preemptive_reason_codes"])
        self.assertEqual(
            trajectory["preemptive_action_reasons"]["build_index"],
            ["rag_cache_missing"],
        )

    def test_health_reports_source_texture_as_rebuildable_interpretation_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(root, workspace, rollout)

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(health.HealthOptions(cwd=workspace, **paths))

        texture = payload["clean_source"]["source_texture"]
        self.assertTrue(texture["exists"])
        self.assertEqual(texture["row_count"], 1)
        self.assertTrue(texture["rebuildable"])
        self.assertFalse(texture["canonical_source"])
        self.assertEqual(texture["truth_boundary"], "texture_signal_not_source_fact")
        self.assertEqual(texture["consumer_boundary"], "interpretation_input_only")
        self.assertNotIn("build_clean_source", [item["id"] for item in payload["recommended_actions"]])

    def test_health_reports_source_intake_quality_without_private_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            paths = self.write_current_artifacts(root, workspace, rollout)
            clean = paths["clean_source_dir"]
            manifest_path = clean / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update(
                {
                    "registry_entry_count": 2,
                    "materialized_source_count": 1,
                    "derived_summary_count": 1,
                    "user_facing_summary_count": 0,
                    "source_refs": [{"source_ref_hash": "ref_broken", "reopenable": False}],
                    "source_intake": {
                        "hook": {"available": False, "version_status": "stale_versioned_path"},
                        "restart_durability_status": "degraded",
                    },
                }
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (clean / "messages.jsonl").write_text(
                json.dumps({"message_id": "m1", "tool_payload": {"secret": "sk-health123456"}})
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(health.HealthOptions(cwd=workspace, **paths))

        source_intake = payload["clean_source"]["source_intake"]
        encoded = json.dumps(source_intake, ensure_ascii=False, sort_keys=True)
        self.assertEqual(source_intake["source_quality_status"], "degraded")
        self.assertEqual(source_intake["metrics"]["hook_available"], False)
        self.assertEqual(source_intake["metrics"]["stale_hook_path_count"], 1)
        self.assertEqual(source_intake["metrics"]["registry_clean_source_mismatch_count"], 1)
        self.assertEqual(source_intake["metrics"]["derived_summary_mismatch_count"], 1)
        self.assertEqual(source_intake["metrics"]["unreopenable_handle_count"], 1)
        self.assertEqual(source_intake["metrics"]["polluted_source_event_count"], 1)
        self.assertNotIn("sk-health123456", encoded)
        self.assertFalse(source_intake["privacy_boundary"]["raw_tool_payload_emitted"])

    def test_health_reports_oversized_logs_without_log_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            rollout = workspace / "rollout.jsonl"
            self.write_rollout(rollout, workspace)
            anchors = workspace / "thread-anchors.md"
            anchors.write_text("# Anchors\n", encoding="utf-8")
            registry_dir = root / "registry"
            log = registry_dir / "logs" / "build_associations_hook.log"
            log.parent.mkdir(parents=True)
            log.write_text(
                "private prompt text and source snippet should not appear\n",
                encoding="utf-8",
            )

            with mock.patch.object(health, "locate_rollout", return_value=rollout):
                payload = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        anchors=anchors,
                        registry_dir=registry_dir,
                        graphify_corpus=root / "graphify-corpus",
                        segments_dir=root / "segments",
                        checkpoint_state=root / "checkpoint_state.json",
                        max_log_bytes=10,
                    )
                )

        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["logs"]["oversized"])
        self.assertEqual(payload["logs"]["items"][0]["artifact_name"], log.name)
        self.assertIn("rotate_logs", [item["id"] for item in payload["recommended_actions"]])
        self.assertIn("aippocampus logs rotate", rendered)
        self.assertNotIn("private prompt text", rendered)
        self.assertNotIn("source snippet", rendered)

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
            f'{health.quote_posix_double(sys.executable)} '
            '-m aippocampus_runtime.recall.index_builder --cwd "/tmp/work space"',
        )

    def test_recommended_script_command_keeps_powershell_shape_on_windows(self) -> None:
        with mock.patch.object(health.os, "name", "nt"):
            command = health.recommended_script_command("build_index.py", "C:/work")
        expected_cwd = "C:" + "\\work"

        self.assertEqual(
            command,
            '$env:PYTHONPATH="$env:CODEX_HOME\\skills\\aippocampus\\scripts"; '
            f'& "{health.PureWindowsPath(sys.executable)}" '
            f'-m aippocampus_runtime.recall.index_builder --cwd "{expected_cwd}"',
        )

    def test_health_action_keeps_operator_command_and_adds_facade_command(self) -> None:
        with mock.patch.object(health.os, "name", "posix"):
            item = health.health_action(
                "build_index",
                "warning",
                "index stale",
                "build_index.py",
                Path("/tmp/work space"),
            )

        self.assertIn("python", item["command"])
        self.assertIn("-m aippocampus_runtime.recall.index_builder", item["command"])
        self.assertEqual(
            item["facade_command"],
            'aippocampus maintenance --cwd "/tmp/work space"',
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

    def test_background_cognition_reports_freshness_without_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "private workspace"
            workspace.mkdir()
            registry_path = root / "threads.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "threads": [
                            {
                                "project_label": "private-project-label",
                                "paths": {"workspace": str(workspace)},
                                "clean_turn_count": 20,
                                "clean_message_count": 40,
                                "updated_at": "2026-06-06T10:00:00Z",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (root / "subconscious_state.json").write_text(
                json.dumps(
                    {
                        "projects": {
                            "private-project-label": {
                                "last_run_ts": 1780627200.0,
                                "last_run_at": "2026-06-05T00:00:00Z",
                                "last_clean_turn_count": 4,
                                "last_clean_message_count": 8,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            jobs_path = root / "subconscious_jobs.jsonl"
            jobs_path.write_text(
                json.dumps(
                    {
                        "created_at": "2026-06-05T00:10:00Z",
                        "project_label": "private-project-label",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "dream_queue.jsonl").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_dream_queue_item",
                        "created_at": "2026-06-06T08:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "aippocampus_prompt_hook_skip_telemetry.json").write_text(
                json.dumps(
                    {
                        "updated_at": "2026-06-06T09:00:00Z",
                        "semantic_diagnostic_counts": {"semantic_skipped": 2},
                    }
                ),
                encoding="utf-8",
            )
            (root / "aippocampus_prompt_hook_last_status.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_prompt_hook_audit_status",
                        "last_prompt_hook": {
                            "timestamp": "2026-06-06T09:30:00Z",
                            "memory_surface": "candidate",
                            "card_count": 3,
                            "source_backed_count": 1,
                            "candidate_count": 2,
                            "warm_background": {"status": "scheduled", "spawned": True},
                        },
                    }
                ),
                encoding="utf-8",
            )
            warm_dir = root / "ambient_warm_jobs"
            warm_dir.mkdir()
            (warm_dir / "warm-public.json").write_text(
                json.dumps({"created_at": "2026-06-06T09:35:00Z"}),
                encoding="utf-8",
            )
            (warm_dir / "warm-public.result.json").write_text(
                json.dumps({"completed_at": "2026-06-06T09:36:00Z"}),
                encoding="utf-8",
            )
            now = health.datetime(2026, 6, 6, 12, 0, 0, tzinfo=health.timezone.utc)

            with mock.patch.dict(
                health.os.environ,
                {
                    "AIPPOCAMPUS_SUBCONSCIOUS_HOOK": "1",
                    "AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "1",
                    "AIPPOCAMPUS_SEMANTIC_GATE": "off",
                    "AIPPOCAMPUS_DREAM_DELIVERY_MODE": "shadow",
                },
                clear=True,
            ):
                payload = health.background_cognition_health(
                    root=root,
                    registry_path=registry_path,
                    jobs_path=jobs_path,
                    cwd=workspace,
                    now=now,
                )

        encoded = json.dumps(payload, ensure_ascii=False)
        subconscious = payload["lanes"]["subconscious"]
        warm = payload["lanes"]["warm_ambient"]
        dream = payload["lanes"]["dream"]
        semantic = payload["lanes"]["semantic_gate"]
        prompt_hook = payload["lanes"]["prompt_hook_affordance"]

        self.assertEqual(subconscious["due_state"], "due")
        self.assertEqual(
            subconscious["diagnostic"]["new_turns_since_last_run"],
            16,
        )
        self.assertEqual(warm["freshness_state"], "fresh")
        self.assertEqual(dream["freshness_state"], "fresh")
        self.assertEqual(semantic["due_state"], "disabled")
        self.assertEqual(prompt_hook["latest"]["source_backed_count"], 1)
        self.assertEqual(subconscious["last_run_at"], "2026-06-05T00:00:00Z")
        self.assertIn("freshness_age_hours", subconscious)
        self.assertFalse(payload["privacy_boundary"]["local_paths_included"])
        self.assertNotIn(str(workspace), encoded)
        self.assertNotIn("private-project-label", encoded)

    def test_background_cognition_subconscious_defaults_disabled_without_explicit_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            now = health.datetime(2026, 6, 6, 12, 0, 0, tzinfo=health.timezone.utc)

            with mock.patch.dict(health.os.environ, {}, clear=True):
                payload = health.background_cognition_health(
                    root=root,
                    registry_path=root / "threads.json",
                    jobs_path=root / "subconscious_jobs.jsonl",
                    cwd=workspace,
                    now=now,
                )

        subconscious = payload["lanes"]["subconscious"]
        self.assertFalse(subconscious["enabled"])
        self.assertEqual(subconscious["due_state"], "disabled")
        self.assertEqual(subconscious["skip_reason"], "disabled_by_env")

    def test_warm_ambient_pending_job_is_not_reported_as_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            jobs_path = root / "subconscious_jobs.jsonl"
            jobs_path.write_text("", encoding="utf-8")
            warm_dir = root / "ambient_warm_jobs"
            warm_dir.mkdir()
            (warm_dir / "warm-public.json").write_text(
                json.dumps({"created_at": "2026-06-06T09:35:00Z"}),
                encoding="utf-8",
            )
            now = health.datetime(2026, 6, 6, 9, 40, 0, tzinfo=health.timezone.utc)

            with mock.patch.dict(
                health.os.environ,
                {
                    "AIPPOCAMPUS_SUBCONSCIOUS_HOOK": "0",
                    "AIPPOCAMPUS_WARM_RECALL_BACKGROUND": "1",
                    "AIPPOCAMPUS_SEMANTIC_GATE": "off",
                    "AIPPOCAMPUS_DREAM_DELIVERY_MODE": "off",
                },
                clear=True,
            ):
                payload = health.background_cognition_health(
                    root=root,
                    registry_path=root / "threads.json",
                    jobs_path=jobs_path,
                    cwd=workspace,
                    now=now,
                )

        warm = payload["lanes"]["warm_ambient"]
        activity = warm["job_activity"]
        self.assertFalse(warm["currently_running"])
        self.assertFalse(activity["worker_process_active"])
        self.assertFalse(activity["pending_jobs_are_worker_evidence"])
        self.assertEqual(activity["pending_recent_count"], 1)
        self.assertEqual(warm["next_operator_action"], "aippocampus warm status --json")
        self.assertEqual(payload["running_lane_count"], 0)

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
            ledger_path = hook_seen_ledger_path_for_registry(registry_dir / "threads.json")
            record_hook_seen_thread(
                ledger_path,
                thread_id="private-thread-title",
                workspace="private-workspace",
                current_thread_key="provider:private-thread-title",
            )
            record_hook_seen_thread(
                ledger_path,
                thread_id="missing-fresh-thread",
                workspace="private-workspace",
            )
            with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    json.dumps(
                        {
                            "kind": "aippocampus_hook_seen_thread",
                            "schema_version": 1,
                            "recorded_at": "1970-01-01T00:00:00Z",
                            "thread_ref": hook_seen_thread_ref("session:very-old-missing"),
                            "workspace_ref": "workspace_test",
                            "registration_expectation": "registry_clean_source_or_blocked",
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )

            payload = health.registry_health_report(registry_dir=registry_dir)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["thread_count"], 1)
        self.assertEqual(payload["recommended_action_counts"], {"build_index": 1})
        self.assertFalse(payload["privacy"]["message_bodies_read"])
        self.assertFalse(payload["privacy"]["paths_included"])
        reconciliation = payload["source_intake"]["hook_seen_registry_reconciliation"]
        self.assertEqual(
            reconciliation["metrics"]["hook_seen_but_not_registered_count"],
            2,
        )
        candidate_states = {item["state"] for item in reconciliation["candidates"]}
        self.assertIn("pending_repair", candidate_states)
        self.assertIn("stale_ledger_row", candidate_states)
        thread = payload["top_threads"][0]
        self.assertIn("thread_ref", thread)
        self.assertNotIn("private-thread-title", json.dumps(payload))
        self.assertNotIn("missing-fresh-thread", json.dumps(payload))
        self.assertNotIn("very-old-missing", json.dumps(payload))
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

    def test_health_reports_generation_pointer_fallback_and_gc_candidates(self) -> None:
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
            lkg_dir = index_dir / "generations" / "gen_20260605T005900_lkg"
            old_dir = index_dir / "generations" / "gen_20260605T004500_old"
            lkg_dir.mkdir(parents=True)
            old_dir.mkdir(parents=True)
            (lkg_dir / "source_index.sqlite").write_bytes(b"lkg")
            (old_dir / "source_index.sqlite").write_bytes(b"old-generation")
            (index_dir / "source_index.pointer.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_sqlite_index_pointer",
                        "current_generation": "gen_20260605T010000_missing",
                        "last_known_good_generation": lkg_dir.name,
                        "current": "generations/gen_20260605T010000_missing/source_index.sqlite",
                        "last_known_good": f"generations/{lkg_dir.name}/source_index.sqlite",
                        "stable": "source_index.sqlite",
                        "compatibility_path": "source_index.sqlite",
                        "publish_latency_ms": 20.5,
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

        generations = payload["index"]["generations"]
        self.assertEqual(generations["status"], "current_missing_last_known_good_available")
        self.assertEqual(generations["fallback_used"], "last_known_good")
        self.assertFalse(generations["current_generation_exists"])
        self.assertTrue(generations["last_known_good_generation_exists"])
        self.assertEqual(generations["old_generation_count"], 1)
        self.assertEqual(generations["generation_gc_candidate_count"], 1)
        self.assertEqual(generations["generation_gc_candidate_bytes"], len(b"old-generation"))
        self.assertEqual(generations["publish_latency_ms"], 20.5)
        self.assertNotIn("source_index.sqlite is missing", payload["index"]["reasons"])

    def test_health_reports_segment_generation_pointer_fallback_and_gc_candidates(self) -> None:
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
            (index_dir / "source_index.sqlite").write_bytes(b"stable")
            segments_dir = root / "segments"
            lkg_dir = segments_dir / "generations" / "gen_20260605T005900_lkg"
            old_dir = segments_dir / "generations" / "gen_20260605T004500_old"
            lkg_shard = lkg_dir / "seg-000001"
            old_shard = old_dir / "seg-000001"
            lkg_shard.mkdir(parents=True)
            old_shard.mkdir(parents=True)
            (lkg_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "created_at": "2026-06-04T00:00:00Z",
                        "segment_count": 1,
                        "source_rollout_size": rollout.stat().st_size,
                        "message_count": 1,
                        "segments": [
                            {"id": "seg-000001", "sqlite": str(lkg_shard / "source_index.sqlite")}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (old_dir / "manifest.json").write_text(
                json.dumps({"segment_count": 1, "generation_id": old_dir.name}),
                encoding="utf-8",
            )
            (lkg_shard / "source_index.sqlite").write_bytes(b"lkg")
            (old_shard / "source_index.sqlite").write_bytes(b"old-segment-generation")
            old_generation_bytes = sum(
                path.stat().st_size for path in old_dir.rglob("*") if path.is_file()
            )
            (segments_dir / "manifest.json").write_text(
                (lkg_dir / "manifest.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (segments_dir / "segments.pointer.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_segments_pointer",
                        "current_generation": "gen_20260605T010000_missing",
                        "last_known_good_generation": lkg_dir.name,
                        "current": "generations/gen_20260605T010000_missing/manifest.json",
                        "last_known_good": f"generations/{lkg_dir.name}/manifest.json",
                        "stable": "manifest.json",
                        "compatibility_path": "manifest.json",
                        "publish_latency_ms": 10.75,
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
                        segments_dir=segments_dir,
                        checkpoint_state=root / "checkpoint_state.json",
                        anchors=anchors,
                    )
                )

        generations = payload["segments"]["generations"]
        self.assertEqual(generations["status"], "current_missing_last_known_good_available")
        self.assertEqual(generations["fallback_used"], "last_known_good")
        self.assertFalse(generations["current_generation_exists"])
        self.assertTrue(generations["last_known_good_generation_exists"])
        self.assertEqual(generations["old_generation_count"], 1)
        self.assertEqual(generations["generation_gc_candidate_count"], 1)
        self.assertEqual(
            generations["generation_gc_candidate_bytes"],
            old_generation_bytes,
        )
        self.assertEqual(generations["publish_latency_ms"], 10.75)

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
