from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import storage_governance  # noqa: E402


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
        self.raw_rollout.write_text("raw bytes with private phrase\n", encoding="utf-8")

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
        (self.index / "source_index.sqlite").write_bytes(b"x" * 31)
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
                    "anchors": {"exists": True, "count": 2},
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
        self.assertNotIn(str(self.root), payload)

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

    def test_dry_run_falls_back_to_capacity_aggregate_when_retention_report_is_missing(
        self,
    ) -> None:
        plan = storage_governance.build_plan(self.root, registry_dir=self.registry)
        payload = json.dumps(plan, ensure_ascii=False)

        self.assertFalse(plan["privacy"]["loads_existing_retention_report"])
        self.assertGreater(plan["metrics"]["reclaimable_rebuildable_bytes"], 0)
        self.assertGreaterEqual(plan["metrics"]["eviction_candidate_count"], 1)
        self.assertIn("Path-level retention candidates are unavailable", plan["warnings"][0])
        self.assertNotIn("private phrase", payload)
        self.assertNotIn(str(self.root), payload)
        self.assertEqual(plan["candidates"][0]["source_report"]["kind"], "storage_capacity_report")

    def test_apply_mode_is_explicitly_unsupported_and_does_not_plan_deletion(self) -> None:
        with patch("sys.stdout", new=StringIO()) as stdout:
            code = storage_governance.main(["gc", "--apply", "--json"])

        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error"]["code"], "storage_gc_apply_not_implemented")
        self.assertEqual(payload["error"]["class"], "usage_error")
        self.assertIsNone(payload["data"])


if __name__ == "__main__":
    unittest.main()
