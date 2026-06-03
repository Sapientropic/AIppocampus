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


if __name__ == "__main__":
    unittest.main()
