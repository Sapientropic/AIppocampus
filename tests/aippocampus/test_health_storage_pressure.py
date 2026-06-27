from __future__ import annotations

import json
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from aippocampus_runtime import health, health_stages
from tests.aippocampus.health_fixtures import health_workspace


def write_rollout(path: Path, cwd: Path) -> None:
    rows = [
        {
            "type": "session_meta",
            "payload": {
                "id": "health-storage-session",
                "timestamp": "2026-06-05T00:00:00Z",
                "cwd": str(cwd),
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-05T00:00:01Z",
            "payload": {"type": "user_message", "message": "storage pressure check"},
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-05T00:00:02Z",
            "payload": {
                "type": "agent_message",
                "phase": "final_answer",
                "message": "bounded storage pressure answer",
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_current_artifacts(root: Path, workspace: Path, rollout: Path) -> dict[str, Path]:
    anchors = workspace / "thread-anchors.md"
    anchors.write_text("# Anchors\n", encoding="utf-8")
    visibility = health.rollout_visibility_stats(rollout)
    current_message_count, last_line = health.count_messages(rollout)
    index_dir = root / "index"
    index_dir.mkdir()
    (index_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-06-01T00:00:00Z",
                "message_count": current_message_count,
                "source_rollout_size": rollout.stat().st_size,
                "last_message_line": last_line,
                "anchor_sha256": health.file_sha256(anchors),
                "rag": {"enabled": True, "chunk_count": 1},
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
                "created_at": "2026-06-01T00:00:00Z",
                "schema_version": 2,
                "source_rollout_size": rollout.stat().st_size,
                "message_count": visibility.expected_clean_source_message_count,
                "turn_count": visibility.expected_clean_source_turn_count,
                "source_texture_count": 1,
                "upgrade_contract": {"source_backed": True},
                "source_texture_policy": {
                    "boundary": "source texture rows are rebuildable interpretation inputs, not source truth.",
                },
            }
        ),
        encoding="utf-8",
    )
    (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
    (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
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


class HealthStoragePressureTests(unittest.TestCase):
    def _agent_json_with_report(self, report: dict[str, object]) -> tuple[int, dict[str, object]]:
        with (
            mock.patch("aippocampus_runtime.health.build_health_report", return_value=report),
            mock.patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = health.main(["--agent-json"])
        return code, json.loads(stdout.getvalue())

    def test_agent_json_storage_pressure_uses_bounded_summary_as_primary(self) -> None:
        reports = [
            (
                {
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "recommended_actions": [{
                        "id": "storage_gc_rebuildable_cache",
                        "severity": "warning",
                        "reason": "Generated rebuildable cache pressure is high",
                    }],
                    "product_readiness": {
                        "ready": True,
                        "ordinary_first_recall_usable": True,
                        "maintenance_recommended": True,
                        "storage_pressure_cleanup_recommended": True,
                    },
                    "privacy": {},
                },
                "storage_pressure_known",
            ),
            (
                {
                    "ok": True,
                    "cwd": "C:/private/work",
                    "checks": [],
                    "recommended_actions": [],
                    "product_readiness": {
                        "ready": True,
                        "ordinary_first_recall_usable": True,
                        "maintenance_recommended": False,
                        "storage_pressure_cleanup_recommended": None,
                    },
                    "storage_pressure": {"status": "deferred", "pressure": None},
                    "privacy": {},
                },
                "storage_pressure_unassessed",
            ),
        ]
        for report, primary_flag in reports:
            code, payload = self._agent_json_with_report(report)
            self.assertEqual(code, 0)
            self.assertEqual(payload["foreground_action"]["id"], "review_storage_gc_summary")
            self.assertEqual(
                payload["foreground_action"]["command"],
                "aippocampus storage gc --dry-run --summary-json --cwd .",
            )
            self.assertTrue(payload["foreground_action"]["primary"][primary_flag])
        self.assertTrue(payload["maintenance_summary"]["storage"]["assessment"], "unassessed")

    def test_health_json_detail_full_bounds_generation_gc_candidates(self) -> None:
        candidates = [
            {
                "generation": f"gen_{index:04d}",
                "bytes": 1024 + index,
                "relative_path": f"index/generations/gen_{index:04d}",
            }
            for index in range(40)
        ]
        payload = {
            "ok": True,
            "cwd": "C:/private/work",
            "index": {
                "generations": {
                    "status": "ok",
                    "old_generation_count": 40,
                    "generation_gc_candidate_count": 40,
                    "generation_gc_candidate_bytes": 40960,
                    "generation_gc_candidates": candidates,
                }
            },
            "segments": {
                "generations": {
                    "status": "ok",
                    "old_generation_count": 40,
                    "generation_gc_candidate_count": 40,
                    "generation_gc_candidate_bytes": 20480,
                    "generation_gc_candidates": candidates,
                }
            },
            "freshness": {"latest_visible_gap": False},
            "storage_pressure": {"available": True, "pressure": False},
            "host_state_confounds": {"available": True},
            "recommended_actions": [],
            "privacy": {},
        }

        public = health.public_health_report(payload)

        for generations in (
            public["index"]["generations"],
            public["segments"]["generations"],
        ):
            self.assertEqual(generations["generation_gc_candidate_count"], 40)
            self.assertEqual(generations["generation_gc_candidates_returned"], 12)
            self.assertTrue(generations["generation_gc_candidate_detail_deferred"])
            self.assertLessEqual(len(generations["generation_gc_candidates"]), 12)
            self.assertEqual(
                generations["bounded_gc_detail_command"],
                "aippocampus storage gc --dry-run --json --top 1 --cwd .",
            )
            self.assertEqual(
                generations["full_gc_detail_command"],
                "aippocampus storage gc --dry-run --json --full --cwd .",
            )

    def test_health_surfaces_cheap_old_generation_pressure_without_expensive_scan(self) -> None:
        with health_workspace() as (root, workspace):
            rollout = workspace / "rollout.jsonl"
            write_rollout(rollout, workspace)
            paths = write_current_artifacts(root, workspace, rollout)
            registry_dir = root / "registry"
            registry_dir.mkdir()
            (registry_dir / "threads.json").write_text('{"threads":[]}', encoding="utf-8")
            index_dir = paths["index_dir"]
            current = index_dir / "generations" / "gen_20260605T010000_current"
            old = index_dir / "generations" / "gen_20260605T004500_old"
            current.mkdir(parents=True)
            old.mkdir(parents=True)
            (current / "source_index.sqlite").write_bytes(b"current")
            (old / "source_index.sqlite").write_bytes(b"x" * (health.STORAGE_PRESSURE_RECLAIMABLE_BYTES + 1))
            (index_dir / "source_index.pointer.json").write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_sqlite_index_pointer",
                        "current_generation": current.name,
                        "last_known_good_generation": current.name,
                        "current": f"generations/{current.name}/source_index.sqlite",
                        "last_known_good": f"generations/{current.name}/source_index.sqlite",
                        "stable": "source_index.sqlite",
                        "compatibility_path": "source_index.sqlite",
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(health_stages, "locate_rollout", return_value=rollout),
                mock.patch.object(
                    health,
                    "registry_cache_pressure_report",
                    side_effect=AssertionError("cheap generation pressure should not run registry scan"),
                ),
            ):
                full = health.build_health_report(
                    health.HealthOptions(
                        cwd=workspace,
                        registry_dir=registry_dir,
                        **paths,
                    )
                )

        action_ids = [item["id"] for item in full["recommended_actions"]]
        self.assertIn("storage_gc_rebuildable_cache", action_ids)
        self.assertTrue(full["product_readiness"]["storage_pressure_cleanup_recommended"])
        self.assertFalse(full["product_readiness"]["maintenance_required_before_recall"])
        compact = health.compact_health_payload(health.public_health_report(full))
        self.assertEqual(compact["foreground_action"]["id"], "review_storage_gc_summary")
        self.assertEqual(
            compact["foreground_action"]["command"],
            "aippocampus storage gc --dry-run --summary-json --cwd .",
        )
        self.assertTrue(compact["foreground_action"]["primary"]["ordinary_first_recall_usable"])


if __name__ == "__main__":
    unittest.main()
