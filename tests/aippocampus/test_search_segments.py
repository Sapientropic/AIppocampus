from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import segment_search  # noqa: E402


class SegmentSearchTests(unittest.TestCase):
    def _write_manifest(self, root: Path, segments: list[dict]) -> Path:
        segments_dir = root / "segments"
        segments_dir.mkdir()
        manifest = segments_dir / "manifest.json"
        manifest.write_text(
            json.dumps({"segment_count": len(segments), "segments": segments}),
            encoding="utf-8",
        )
        return segments_dir

    def _source_hit(
        self,
        *,
        stable_source_id: str,
        source_ref: str,
        snippet: str,
        score: float,
        line: int,
        message_id: str | None = None,
    ) -> dict:
        return {
            "id": line,
            "line": line,
            "timestamp": "",
            "role": "assistant",
            "kind": "message",
            "score": score,
            "stable_source_id": stable_source_id,
            "thread_key": "session:deep",
            "message_id": message_id or stable_source_id.rsplit(":", 1)[-1],
            "source_ref": source_ref,
            "snippet": snippet,
            "signals": {},
        }

    def test_missing_manifest_reports_build_required_without_surprise_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(segment_search.subprocess, "run") as run:
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["forgotten thread"],
                        cwd=root,
                        segments_dir=root / "segments",
                        build_segments=False,
                    )
                )

        run.assert_not_called()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "segments_unavailable")
        self.assertEqual(payload["availability"]["reason"], "manifest_missing")
        self.assertTrue(payload["availability"]["build_required"])
        self.assertFalse(payload["availability"]["build_requested"])
        self.assertEqual(payload["matches"], [])
        self.assertEqual(payload["fanout"]["planned_segment_count"], 0)
        self.assertEqual(payload["fanout"]["searched_segment_count"], 0)

    def test_fanout_budget_plans_before_sqlite_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_paths = [root / f"seg-{idx}.sqlite" for idx in range(1, 4)]
            for path in sqlite_paths:
                path.write_text("", encoding="utf-8")
            segments_dir = self._write_manifest(
                root,
                [
                    {
                        "id": "seg-old",
                        "sqlite": str(sqlite_paths[0]),
                        "start_line": 1,
                        "end_line": 10,
                    },
                    {
                        "id": "seg-mid",
                        "sqlite": str(sqlite_paths[1]),
                        "start_line": 11,
                        "end_line": 20,
                    },
                    {
                        "id": "seg-new",
                        "sqlite": str(sqlite_paths[2]),
                        "start_line": 21,
                        "end_line": 30,
                    },
                ],
            )
            opened: list[Path] = []

            def fake_search(index: Path, *args, **kwargs) -> list[dict]:
                opened.append(Path(index))
                return [
                    {
                        "id": 1,
                        "line": 25,
                        "timestamp": "",
                        "role": "assistant",
                        "kind": "message",
                        "score": 9.0,
                        "snippet": "newest match",
                        "signals": {},
                    }
                ]

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["memory"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                        fanout_budget=1,
                    )
                )

        self.assertEqual(opened, [sqlite_paths[2]])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["fanout"]["planned_segment_count"], 1)
        self.assertEqual(payload["fanout"]["searched_segment_count"], 1)
        self.assertEqual(payload["fanout"]["skipped_segment_count"], 2)
        self.assertTrue(payload["fanout"]["budget_exhausted"])
        self.assertEqual(payload["matches"][0]["segment_id"], "seg-new")

    def test_segment_planning_keeps_recency_order_without_temporal_cue(self) -> None:
        segments = [
            {
                "id": "seg-old",
                "start_line": 1,
                "end_line": 10,
                "end_global_id": 10,
            },
            {
                "id": "seg-mid",
                "start_line": 11,
                "end_line": 20,
                "end_global_id": 20,
            },
            {
                "id": "seg-new",
                "start_line": 21,
                "end_line": 30,
                "end_global_id": 30,
            },
        ]

        planned, fanout = segment_search.plan_segments(
            segments,
            segment_search.SegmentSearchOptions(
                patterns=["memory"],
                fanout_budget=2,
            ),
        )

        self.assertEqual([segment["id"] for _, segment in planned], ["seg-new", "seg-mid"])
        self.assertFalse(fanout["temporal_cue_parsed"])
        self.assertEqual(fanout["temporal_boosted_segments"], [])

    def test_segment_planning_prioritizes_explicit_date_inside_budget(self) -> None:
        segments = [
            {
                "id": "seg-jan",
                "start_line": 1,
                "end_line": 10,
                "end_global_id": 10,
                "start_timestamp": "2026-01-01T00:00:00Z",
                "end_timestamp": "2026-01-31T23:59:59Z",
            },
            {
                "id": "seg-feb",
                "start_line": 11,
                "end_line": 20,
                "end_global_id": 20,
                "start_timestamp": "2026-02-01T00:00:00Z",
                "end_timestamp": "2026-02-28T23:59:59Z",
            },
            {
                "id": "seg-mar",
                "start_line": 21,
                "end_line": 30,
                "end_global_id": 30,
                "start_timestamp": "2026-03-01T00:00:00Z",
                "end_timestamp": "2026-03-31T23:59:59Z",
            },
        ]

        planned, fanout = segment_search.plan_segments(
            segments,
            segment_search.SegmentSearchOptions(
                patterns=["what did we decide on 2026-01-15"],
                fanout_budget=1,
            ),
        )

        self.assertEqual([segment["id"] for _, segment in planned], ["seg-jan"])
        self.assertTrue(fanout["temporal_cue_parsed"])
        self.assertEqual(fanout["temporal_cue_kind"], "date_exact")
        self.assertEqual(fanout["temporal_boosted_segments"], ["seg-jan"])
        self.assertEqual(fanout["planned_segments"][0]["segment_id"], "seg-jan")
        self.assertTrue(fanout["planned_segments"][0]["temporal_boosted"])
        self.assertEqual(fanout["effective_max_segments"], 1)

    def test_temporal_cue_falls_back_to_recency_for_legacy_manifest_without_timestamps(self) -> None:
        segments = [
            {
                "id": "seg-old",
                "start_line": 1,
                "end_line": 10,
                "end_global_id": 10,
            },
            {
                "id": "seg-new",
                "start_line": 11,
                "end_line": 20,
                "end_global_id": 20,
            },
        ]

        planned, fanout = segment_search.plan_segments(
            segments,
            segment_search.SegmentSearchOptions(
                patterns=["what did we decide on 2026-01-15"],
                fanout_budget=1,
            ),
        )

        self.assertEqual([segment["id"] for _, segment in planned], ["seg-new"])
        self.assertTrue(fanout["temporal_cue_parsed"])
        self.assertEqual(fanout["temporal_boosted_segments"], [])
        self.assertFalse(fanout["planned_segments"][0]["temporal_boosted"])

    def test_segment_planning_prioritizes_chinese_relative_temporal_cue(self) -> None:
        segments = [
            {
                "id": "seg-dec",
                "start_line": 1,
                "end_line": 10,
                "end_global_id": 10,
                "start_timestamp": "2025-12-01T00:00:00Z",
                "end_timestamp": "2025-12-31T23:59:59Z",
            },
            {
                "id": "seg-feb",
                "start_line": 11,
                "end_line": 20,
                "end_global_id": 20,
                "start_timestamp": "2026-02-01T00:00:00Z",
                "end_timestamp": "2026-02-28T23:59:59Z",
            },
        ]

        planned, fanout = segment_search.plan_segments(
            segments,
            segment_search.SegmentSearchOptions(
                patterns=["半年前我们说了什么"],
                fanout_budget=1,
                now="2026-06-08T00:00:00Z",
            ),
        )

        self.assertEqual([segment["id"] for _, segment in planned], ["seg-dec"])
        self.assertEqual(fanout["temporal_cue_kind"], "relative_half_year")
        self.assertEqual(fanout["temporal_boosted_segments"], ["seg-dec"])
        self.assertEqual(fanout["skipped_segment_count"], 1)

    def test_segment_planning_prioritizes_english_relative_temporal_cue(self) -> None:
        segments = [
            {
                "id": "seg-apr",
                "start_line": 1,
                "end_line": 10,
                "end_global_id": 10,
                "start_timestamp": "2026-04-01T00:00:00Z",
                "end_timestamp": "2026-04-30T23:59:59Z",
            },
            {
                "id": "seg-may",
                "start_line": 11,
                "end_line": 20,
                "end_global_id": 20,
                "start_timestamp": "2026-05-01T00:00:00Z",
                "end_timestamp": "2026-05-31T23:59:59Z",
            },
            {
                "id": "seg-jun",
                "start_line": 21,
                "end_line": 30,
                "end_global_id": 30,
                "start_timestamp": "2026-06-01T00:00:00Z",
                "end_timestamp": "2026-06-08T00:00:00Z",
            },
        ]

        planned, fanout = segment_search.plan_segments(
            segments,
            segment_search.SegmentSearchOptions(
                patterns=["what happened last month"],
                fanout_budget=1,
                now="2026-06-08T00:00:00Z",
            ),
        )

        self.assertEqual([segment["id"] for _, segment in planned], ["seg-may"])
        self.assertEqual(fanout["temporal_cue_kind"], "relative_last_month")
        self.assertEqual(fanout["temporal_boosted_segments"], ["seg-may"])
        self.assertTrue(fanout["budget_exhausted"])

    def test_full_fanout_overrides_budget_for_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_paths = [root / f"seg-{idx}.sqlite" for idx in range(1, 4)]
            for path in sqlite_paths:
                path.write_text("", encoding="utf-8")
            segments_dir = self._write_manifest(
                root,
                [
                    {"id": "seg-a", "sqlite": str(sqlite_paths[0]), "end_line": 10},
                    {"id": "seg-b", "sqlite": str(sqlite_paths[1]), "end_line": 20},
                    {"id": "seg-c", "sqlite": str(sqlite_paths[2]), "end_line": 30},
                ],
            )
            opened: list[Path] = []

            def fake_search(index: Path, *args, **kwargs) -> list[dict]:
                opened.append(Path(index))
                return []

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["memory"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                        fanout_budget=1,
                        full_fanout=True,
                    )
                )

        self.assertEqual(opened, [sqlite_paths[2], sqlite_paths[1], sqlite_paths[0]])
        self.assertEqual(payload["fanout"]["mode"], "full")
        self.assertEqual(payload["fanout"]["planned_segment_count"], 3)
        self.assertEqual(payload["fanout"]["skipped_segment_count"], 0)

    def test_search_payload_emits_opt_in_outcome_feedback_without_raw_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "seg.sqlite"
            sqlite_path.write_text("", encoding="utf-8")
            segments_dir = self._write_manifest(
                root,
                [{"id": "seg-a", "sqlite": str(sqlite_path), "start_line": 1, "end_line": 10}],
            )
            feedback_path = root / "recall-outcomes.jsonl"

            def fake_search(index: Path, *args, **kwargs) -> list[dict]:
                return [
                    {
                        "id": 1,
                        "line": 8,
                        "timestamp": "",
                        "role": "assistant",
                        "kind": "message",
                        "score": 9.0,
                        "snippet": "public-safe match",
                        "source_ref": "src-public",
                        "signals": {},
                    }
                ]

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["where is the jade memento? sk-test-public-fixture"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="hybrid",
                        outcome_feedback_path=feedback_path,
                        outcome_signal="ignored",
                        outcome_run_id="run-public",
                    )
                )
            event = json.loads(feedback_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertTrue(payload["outcome_feedback"]["emitted"])
        self.assertEqual(event["outcome_signal"], "ignored")
        self.assertEqual(event["route_family"], "segmented-hybrid")
        dumped = json.dumps(event, ensure_ascii=False)
        self.assertNotIn("jade memento", dumped)
        self.assertNotIn("sk-test-public-fixture", dumped)

    def test_merge_topk_dedupes_stable_source_join_keys_across_segments(self) -> None:
        results = [
            {
                "segment_id": "seg-overlap-a",
                "id": 10,
                "line": 100,
                "role": "assistant",
                "kind": "message",
                "score": 100.0,
                "stable_source_id": "clean:thread:msg-1",
                "source_ref": "source:target",
                "snippet": "overlap winner",
                "signals": {},
            },
            {
                "segment_id": "seg-overlap-b",
                "id": 3,
                "line": 102,
                "role": "assistant",
                "kind": "message",
                "score": 99.0,
                "stable_source_id": "clean:thread:msg-1",
                "source_ref": "source:duplicate-loser",
                "snippet": "overlap duplicate",
                "signals": {},
            },
            {
                "segment_id": "seg-context",
                "id": 4,
                "line": 500,
                "role": "assistant",
                "kind": "message",
                "score": 90.0,
                "stable_source_id": "clean:thread:msg-2",
                "source_ref": "source:support",
                "snippet": "different source",
                "signals": {},
            },
        ]

        selected = segment_search.merge_topk(results, limit=2)

        self.assertEqual(
            [item["source_ref"] for item in selected],
            ["source:target", "source:support"],
        )

    def test_merge_topk_reports_source_key_dedupe_count_without_old_shard_regression(self) -> None:
        results = [
            {
                "segment_id": "seg-legacy-a",
                "id": 1,
                "line": 10,
                "role": "assistant",
                "kind": "message",
                "score": 100.0,
                "source_ref": "source:legacy-a",
                "snippet": "legacy hit a",
                "signals": {},
            },
            {
                "segment_id": "seg-legacy-b",
                "id": 1,
                "line": 10,
                "role": "assistant",
                "kind": "message",
                "score": 99.0,
                "source_ref": "source:legacy-b",
                "snippet": "legacy hit b",
                "signals": {},
            },
            {
                "segment_id": "seg-stable-a",
                "id": 5,
                "line": 40,
                "role": "assistant",
                "kind": "message",
                "score": 98.0,
                "thread_key": "session:one",
                "message_id": "msg-stable",
                "source_ref": "source:stable-winner",
                "snippet": "stable winner",
                "signals": {},
            },
            {
                "segment_id": "seg-stable-b",
                "id": 2,
                "line": 42,
                "role": "assistant",
                "kind": "message",
                "score": 97.0,
                "thread_key": "session:one",
                "message_id": "msg-stable",
                "source_ref": "source:stable-loser",
                "snippet": "stable duplicate",
                "signals": {},
            },
        ]

        selected, diagnostics = segment_search.merge_topk_with_diagnostics(results, limit=3)

        self.assertEqual(diagnostics["source_key_dedupe_count"], 1)
        self.assertIn("source:legacy-a", [item["source_ref"] for item in selected])
        self.assertIn("source:legacy-b", [item["source_ref"] for item in selected])
        self.assertIn("source:stable-winner", [item["source_ref"] for item in selected])
        self.assertNotIn("source:stable-loser", [item["source_ref"] for item in selected])

    def test_search_resolves_segment_generation_pointer_with_lkg_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments_dir = root / "segments"
            old_gen = segments_dir / "generations" / "gen_old"
            new_gen = segments_dir / "generations" / "gen_new"
            old_gen.mkdir(parents=True)
            new_gen.mkdir(parents=True)
            old_sqlite = old_gen / "seg-old.sqlite"
            new_sqlite = new_gen / "seg-new.sqlite"
            old_sqlite.write_text("", encoding="utf-8")
            new_sqlite.write_text("", encoding="utf-8")
            (old_gen / "manifest.json").write_text(
                json.dumps(
                    {
                        "segment_count": 1,
                        "segments": [
                            {"id": "seg-old", "sqlite": str(old_sqlite), "end_line": 10}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (new_gen / "manifest.json").write_text(
                json.dumps(
                    {
                        "segment_count": 1,
                        "segments": [
                            {"id": "seg-new", "sqlite": str(new_sqlite), "end_line": 20}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (segments_dir / "manifest.json").write_text(
                json.dumps({"segment_count": 0, "segments": []}),
                encoding="utf-8",
            )
            (segments_dir / "segments.pointer.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "aippocampus_segments_pointer",
                        "current_generation": "gen_new",
                        "last_known_good_generation": "gen_old",
                        "current": "generations/gen_new/manifest.json",
                        "last_known_good": "generations/gen_old/manifest.json",
                        "stable": "manifest.json",
                    }
                ),
                encoding="utf-8",
            )
            opened: list[Path] = []

            def fake_search(index: Path, *args, **kwargs) -> list[dict]:
                opened.append(Path(index))
                return [
                    {
                        "id": 1,
                        "line": 20,
                        "timestamp": "",
                        "role": "assistant",
                        "kind": "message",
                        "score": 9.0,
                        "snippet": "match",
                        "signals": {},
                    }
                ]

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                current_payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["memory"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                    )
                )
                (new_gen / "manifest.json").unlink()
                fallback_payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["memory"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                    )
                )

        self.assertEqual(opened, [new_sqlite, old_sqlite])
        self.assertEqual(Path(current_payload["source"]), new_gen / "manifest.json")
        self.assertEqual(Path(fallback_payload["source"]), old_gen / "manifest.json")
        self.assertEqual(current_payload["matches"][0]["segment_id"], "seg-new")
        self.assertEqual(fallback_payload["matches"][0]["segment_id"], "seg-old")

    def test_search_pins_resolved_segment_generation_for_query_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            segments_dir = root / "segments"
            current = segments_dir / "generations" / "gen_current"
            current.mkdir(parents=True)
            sqlite_path = current / "seg-current.sqlite"
            sqlite_path.write_text("", encoding="utf-8")
            (current / "manifest.json").write_text(
                json.dumps(
                    {
                        "segment_count": 1,
                        "segments": [
                            {"id": "seg-current", "sqlite": str(sqlite_path), "end_line": 5}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            segments_dir.mkdir(exist_ok=True)
            (segments_dir / "manifest.json").write_text(
                json.dumps({"segment_count": 0, "segments": []}),
                encoding="utf-8",
            )
            (segments_dir / "segments.pointer.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "aippocampus_segments_pointer",
                        "current_generation": "gen_current",
                        "last_known_good_generation": "gen_current",
                        "current": "generations/gen_current/manifest.json",
                        "last_known_good": "generations/gen_current/manifest.json",
                        "stable": "manifest.json",
                    }
                ),
                encoding="utf-8",
            )
            observed_pins: list[dict] = []

            def fake_search(index: Path, *args, **kwargs) -> list[dict]:
                self.assertEqual(Path(index), sqlite_path)
                pins = list((segments_dir / ".reader-pins").glob("*.json"))
                self.assertEqual(len(pins), 1)
                observed_pins.append(json.loads(pins[0].read_text(encoding="utf-8")))
                return []

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["memory"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                    )
                )

        self.assertTrue(payload["ok"])
        self.assertEqual([item.get("generation") for item in observed_pins], ["gen_current"])
        self.assertFalse(list((segments_dir / ".reader-pins").glob("*.json")))

    def test_search_payload_reports_partial_turn_boundary_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_sqlite = root / "seg-partial-a.sqlite"
            second_sqlite = root / "seg-partial-b.sqlite"
            first_sqlite.write_text("", encoding="utf-8")
            second_sqlite.write_text("", encoding="utf-8")
            segments_dir = self._write_manifest(
                root,
                [
                    {
                        "id": "seg-partial-a",
                        "sqlite": str(first_sqlite),
                        "start_line": 1,
                        "end_line": 9,
                        "start_global_id": 1,
                        "end_global_id": 2,
                        "start_turn_index": 7,
                        "end_turn_index": 7,
                        "starts_with_partial_turn": False,
                        "ends_with_partial_turn": True,
                        "partial_turn_indices": [7],
                    },
                    {
                        "id": "seg-partial-b",
                        "sqlite": str(second_sqlite),
                        "start_line": 10,
                        "end_line": 20,
                        "start_global_id": 3,
                        "end_global_id": 4,
                        "start_turn_index": 7,
                        "end_turn_index": 7,
                        "starts_with_partial_turn": True,
                        "ends_with_partial_turn": False,
                        "partial_turn_indices": [7],
                    }
                ],
            )

            def fake_search(index: Path, *args, **kwargs) -> list[dict]:
                if Path(index) != second_sqlite:
                    return []
                return [
                    {
                        "id": 1,
                        "line": 12,
                        "timestamp": "",
                        "role": "assistant",
                        "kind": "message",
                        "turn_index": 7,
                        "score": 9.0,
                        "snippet": "partial turn match",
                        "signals": {},
                    }
                ]

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["memory"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                    )
                )

        diagnostics = payload["turn_boundary_diagnostics"]
        self.assertTrue(diagnostics["has_partial_turn_boundaries"])
        self.assertEqual(diagnostics["partial_segment_count"], 2)
        self.assertEqual(diagnostics["partial_turn_indices"], [7])
        self.assertEqual(diagnostics["partial_segments"][0]["segment_id"], "seg-partial-a")
        self.assertTrue(payload["matches"][0]["segment_starts_with_partial_turn"])
        self.assertEqual(payload["matches"][0]["segment_turn_range"], [7, 7])
        self.assertEqual(
            payload["matches"][0]["cross_boundary_turn_context"],
            {
                "status": "identified",
                "turn_indices": [7],
                "adjacent_segment_ids": ["seg-partial-a"],
                "stitched": False,
            },
        )

    def test_explicit_deep_search_recovers_second_hop_source_joined_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_sqlite = root / "seg-old.sqlite"
            new_sqlite = root / "seg-new.sqlite"
            old_sqlite.write_text("", encoding="utf-8")
            new_sqlite.write_text("", encoding="utf-8")
            segments_dir = self._write_manifest(
                root,
                [
                    {"id": "seg-old", "sqlite": str(old_sqlite), "end_line": 10},
                    {"id": "seg-new", "sqlite": str(new_sqlite), "end_line": 20},
                ],
            )

            def fake_search(index: Path, query_terms: list[str], *args, **kwargs) -> list[dict]:
                terms = set(query_terms)
                if "sphinx" in terms and Path(index) == old_sqlite:
                    return [
                        self._source_hit(
                            stable_source_id="clean:recovered",
                            source_ref="source:recovered",
                            snippet="Sphinx Atlas final decision lives in this older route.",
                            score=8.0,
                            line=8,
                        )
                    ]
                if Path(index) == new_sqlite:
                    return [
                        self._source_hit(
                            stable_source_id="clean:seed",
                            source_ref="source:seed",
                            snippet="The durable anchor for that forgotten project was Sphinx Atlas.",
                            score=9.0,
                            line=18,
                        )
                    ]
                return []

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["forgotten project"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                        deep=True,
                        deep_max_hops=1,
                    )
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["source_ref"] for item in payload["matches"]],
            ["source:seed", "source:recovered"],
        )
        self.assertEqual(
            {item["source_ref"]: item["recall_hop"] for item in payload["matches"]},
            {"source:seed": 0, "source:recovered": 1},
        )
        deep = payload["deep_recall"]
        self.assertTrue(deep["enabled"])
        self.assertEqual(deep["mode"], "explicit_deep_recall")
        self.assertEqual(deep["completed_hops"], 1)
        self.assertEqual(deep["stop_reason"], "max_hops")
        self.assertEqual(payload["fanout"]["searched_segment_count"], 2)
        self.assertEqual(deep["searched_segment_count"], 2)
        self.assertIn("sphinx", deep["hops"][1]["query_terms"])
        self.assertEqual(deep["hops"][1]["added_source_key_count"], 1)

    def test_explicit_deep_search_stops_when_second_hop_adds_no_source_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "seg.sqlite"
            sqlite_path.write_text("", encoding="utf-8")
            segments_dir = self._write_manifest(
                root,
                [{"id": "seg", "sqlite": str(sqlite_path), "end_line": 10}],
            )
            call_count = 0

            def fake_search(index: Path, query_terms: list[str], *args, **kwargs) -> list[dict]:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return [
                        self._source_hit(
                            stable_source_id="clean:seed",
                            source_ref="source:seed",
                            snippet="The route anchor was Sphinx Atlas.",
                            score=9.0,
                            line=4,
                        )
                    ]
                return [
                    self._source_hit(
                        stable_source_id="clean:seed",
                        source_ref="source:duplicate",
                        snippet="Duplicate Sphinx Atlas overlap.",
                        score=8.0,
                        line=5,
                    )
                ]

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["forgotten project"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                        deep=True,
                        deep_max_hops=3,
                    )
                )

        self.assertEqual([item["source_ref"] for item in payload["matches"]], ["source:seed"])
        self.assertEqual(payload["merge_diagnostics"]["source_key_dedupe_count"], 1)
        deep = payload["deep_recall"]
        self.assertEqual(deep["stop_reason"], "no_new_source_keys")
        self.assertEqual(deep["hops"][1]["added_source_keys"], [])
        self.assertEqual(deep["hops"][1]["added_source_key_count"], 0)

    def test_explicit_deep_search_candidate_budget_stops_before_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "seg.sqlite"
            sqlite_path.write_text("", encoding="utf-8")
            segments_dir = self._write_manifest(
                root,
                [{"id": "seg", "sqlite": str(sqlite_path), "end_line": 10}],
            )
            searched_terms: list[list[str]] = []

            def fake_search(index: Path, query_terms: list[str], *args, **kwargs) -> list[dict]:
                searched_terms.append(list(query_terms))
                return [
                    self._source_hit(
                        stable_source_id="clean:seed",
                        source_ref="source:seed",
                        snippet="The route anchor was Sphinx Atlas.",
                        score=9.0,
                        line=4,
                    )
                ]

            with mock.patch.object(segment_search, "search_hybrid_index", side_effect=fake_search):
                payload = segment_search.search_segments_payload(
                    segment_search.SegmentSearchOptions(
                        patterns=["forgotten project"],
                        cwd=root,
                        segments_dir=segments_dir,
                        mode="ranked",
                        deep=True,
                        deep_max_hops=3,
                        deep_candidate_budget=1,
                    )
                )

        self.assertEqual(len(searched_terms), 1)
        deep = payload["deep_recall"]
        self.assertEqual(deep["stop_reason"], "candidate_budget")
        self.assertEqual(deep["skipped_expansions"][0]["reason"], "candidate_budget")
        self.assertEqual(deep["completed_hops"], 0)


if __name__ == "__main__":
    unittest.main()
