from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import storage_capacity_report  # noqa: E402


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

    def test_report_exposes_planned_query_fanout_budget(self) -> None:
        extra_threads = []
        for key, label in (
            ("session-alpha", "alpha research notes"),
            ("session-beta", "beta operations notes"),
        ):
            thread = self.registry / "threads" / key
            clean = thread / "clean-source"
            index = thread / "index"
            clean.mkdir(parents=True)
            index.mkdir(parents=True)
            (clean / "manifest.json").write_text(
                json.dumps({"kind": "aippocampus_clean_source"}), encoding="utf-8"
            )
            (clean / "messages.jsonl").write_text("{}\n", encoding="utf-8")
            (clean / "turns.jsonl").write_text("{}\n", encoding="utf-8")
            (index / "source_index.sqlite").write_bytes(b"sqlite")
            extra_threads.append({"thread_key": key, "project_label": label})

        registry = json.loads((self.registry / "threads.json").read_text(encoding="utf-8"))
        registry["threads"].extend(extra_threads)
        (self.registry / "threads.json").write_text(
            json.dumps(registry, ensure_ascii=False), encoding="utf-8"
        )

        report = storage_capacity_report.build_report(
            self.registry, top=5, planner_query="alpha", fanout_budget=1
        )
        planner = report["query_planner"]

        self.assertEqual(planner["worst_case_sqlite_handles"], 4)
        self.assertEqual(planner["candidate_thread_count"], 1)
        self.assertEqual(planner["planned_sqlite_handles"], 1)
        self.assertLess(
            planner["planned_sqlite_handles"], planner["worst_case_sqlite_handles"]
        )
        self.assertFalse(planner["fallback_used"])

    def test_report_does_not_include_clean_source_text_or_absolute_paths_by_default(self) -> None:
        report = storage_capacity_report.build_report(self.registry, top=5)
        payload = json.dumps(report, ensure_ascii=False)

        self.assertNotIn("private phrase that must not leak", payload)
        self.assertNotIn(str(self.root), payload)
        self.assertIn("session-one", payload)

    def test_report_exposes_generation_gc_metrics_without_absolute_paths(self) -> None:
        current = self._write_index_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_index_generation("gen_20260605T005900_lkg", 37)
        old = self._write_index_generation("gen_20260605T004500_old", 29)
        (self.index / "source_index.pointer.json").write_text(
            json.dumps(
                {
                    "kind": "aippocampus_sqlite_index_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/source_index.sqlite",
                    "last_known_good": f"generations/{last_known_good.name}/source_index.sqlite",
                    "stable": "source_index.sqlite",
                    "compatibility_path": "source_index.sqlite",
                    "publish_latency_ms": 12.25,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        report = storage_capacity_report.build_report(self.registry, top=5)
        payload = json.dumps(report, ensure_ascii=False)
        generations = report["top_threads"][0]["index_generations"]

        self.assertTrue(generations["pointer_exists"])
        self.assertEqual(generations["status"], "ok")
        self.assertEqual(generations["current_generation"], current.name)
        self.assertEqual(generations["last_known_good_generation"], last_known_good.name)
        self.assertEqual(generations["generation_count"], 3)
        self.assertEqual(generations["old_generation_count"], 1)
        self.assertEqual(generations["old_generation_bytes"], 29)
        self.assertEqual(generations["generation_gc_candidate_count"], 1)
        self.assertEqual(generations["generation_gc_candidate_bytes"], 29)
        self.assertEqual(generations["publish_latency_ms"], 12.25)
        self.assertGreaterEqual(generations["pointer_load_ms"], 0.0)
        self.assertEqual(
            generations["generation_gc_candidates"][0]["relative_path"],
            f"threads/session-one/index/generations/{old.name}",
        )
        self.assertNotIn(str(self.root), payload)

    def test_report_exposes_segment_generation_gc_metrics_without_absolute_paths(self) -> None:
        current = self._write_segment_generation("gen_20260605T010000_current", 41)
        last_known_good = self._write_segment_generation("gen_20260605T005900_lkg", 37)
        old = self._write_segment_generation("gen_20260605T004500_old", 29)
        old_bytes = storage_capacity_report.dir_size(old)
        segments_dir = self.index / "segments"
        (segments_dir / "segments.pointer.json").write_text(
            json.dumps(
                {
                    "kind": "aippocampus_segments_pointer",
                    "current_generation": current.name,
                    "last_known_good_generation": last_known_good.name,
                    "current": f"generations/{current.name}/manifest.json",
                    "last_known_good": f"generations/{last_known_good.name}/manifest.json",
                    "stable": "manifest.json",
                    "compatibility_path": "manifest.json",
                    "publish_latency_ms": 9.5,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (segments_dir / "manifest.json").write_text(
            (current / "manifest.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        report = storage_capacity_report.build_report(self.registry, top=5)
        payload = json.dumps(report, ensure_ascii=False)
        generations = report["top_threads"][0]["segment_generations"]

        self.assertTrue(generations["pointer_exists"])
        self.assertEqual(generations["status"], "ok")
        self.assertEqual(generations["current_generation"], current.name)
        self.assertEqual(generations["last_known_good_generation"], last_known_good.name)
        self.assertEqual(generations["generation_count"], 3)
        self.assertEqual(generations["old_generation_count"], 1)
        self.assertEqual(generations["old_generation_bytes"], old_bytes)
        self.assertEqual(generations["generation_gc_candidate_count"], 1)
        self.assertEqual(generations["generation_gc_candidate_bytes"], old_bytes)
        self.assertEqual(generations["publish_latency_ms"], 9.5)
        self.assertGreaterEqual(generations["pointer_load_ms"], 0.0)
        self.assertEqual(
            generations["generation_gc_candidates"][0]["relative_path"],
            f"threads/session-one/index/segments/generations/{old.name}",
        )
        self.assertEqual(report["totals"]["segment_old_generation_count"], 1)
        self.assertEqual(report["totals"]["segment_generation_gc_candidate_count"], 1)
        self.assertEqual(report["totals"]["segment_generation_gc_candidate_bytes"], old_bytes)
        self.assertEqual(report["top_threads"][0]["segment_sqlite_count"], 1)
        self.assertEqual(report["top_threads"][0]["segment_sqlite_bytes"], 41)
        self.assertNotIn(str(self.root), payload)


if __name__ == "__main__":
    unittest.main()
