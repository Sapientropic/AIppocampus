from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import storage_capacity_report  # noqa: E402


class StorageCapacityReportTests(unittest.TestCase):
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
        self.raw_rollout.write_text("raw audit bytes only\n", encoding="utf-8")

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
        (self.registry / "threads.md").write_text("# registry\n", encoding="utf-8")
        (self.registry / "semantic_triggers.jsonl").write_text(
            json.dumps({"trigger": "source-backed"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        (self.clean / "manifest.json").write_text(
            json.dumps({"kind": "aippocampus_clean_source"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.clean / "messages.jsonl").write_text(
            json.dumps(
                {"message_id": "m1", "text": "private phrase that must not leak"},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.clean / "turns.jsonl").write_text(
            json.dumps({"turn_id": "t1"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (self.clean / "semantic-scope-labels.jsonl").write_text(
            json.dumps({"message_id": "m1", "scope_labels": ["project_work"]}) + "\n",
            encoding="utf-8",
        )

        (self.index / "manifest.json").write_text(
            json.dumps({"kind": "aippocampus_index"}), encoding="utf-8"
        )
        (self.index / "messages.jsonl").write_bytes(b"indexed-message-cache")
        (self.index / "source_index.sqlite").write_bytes(b"x" * 31)
        (self.index / "graph.json").write_text(
            json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
        )
        (self.segment / "messages.jsonl").write_bytes(b"segment-message-cache")
        (self.segment / "source_index.sqlite").write_bytes(b"y" * 17)
        (self.index / "segments" / "manifest.json").write_text(
            json.dumps(
                {
                    "segment_count": 1,
                    "segments": [
                        {"id": "seg-000001", "sqlite": str(self.segment / "source_index.sqlite")}
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_report_counts_clean_source_generated_indexes_and_fanout(self) -> None:
        report = storage_capacity_report.build_report(self.registry, top=5)

        canonical_clean_bytes = sum(
            (self.clean / name).stat().st_size
            for name in ("manifest.json", "messages.jsonl", "turns.jsonl")
        )
        generated_index_bytes = sum(
            path.stat().st_size for path in self.index.rglob("*") if path.is_file()
        )

        self.assertEqual(report["totals"]["thread_count"], 1)
        self.assertEqual(report["totals"]["canonical_clean_source_bytes"], canonical_clean_bytes)
        self.assertEqual(report["totals"]["generated_index_bytes"], generated_index_bytes)
        self.assertEqual(report["totals"]["main_sqlite_count"], 1)
        self.assertEqual(report["totals"]["segment_sqlite_count"], 1)
        self.assertEqual(report["query_fanout"]["worst_case_sqlite_handles"], 2)
        self.assertEqual(report["top_threads"][0]["thread_dir"], "session-one")
        self.assertGreater(report["totals"]["index_amplification_ratio"], 0)

    def test_report_estimates_current_sync_policy_without_sqlite_indexes(self) -> None:
        report = storage_capacity_report.build_report(self.registry, top=5)

        current_sync_bytes = report["sync"]["current_policy_bytes"]
        self.assertGreater(current_sync_bytes, 0)
        self.assertEqual(report["sync"]["current_policy_main_sqlite_bytes"], 0)
        self.assertLess(current_sync_bytes, report["totals"]["total_registry_bytes"])

    def test_report_does_not_include_clean_source_text_or_absolute_paths_by_default(self) -> None:
        report = storage_capacity_report.build_report(self.registry, top=5)
        payload = json.dumps(report, ensure_ascii=False)

        self.assertNotIn("private phrase that must not leak", payload)
        self.assertNotIn(str(self.root), payload)
        self.assertIn("session-one", payload)


if __name__ == "__main__":
    unittest.main()
