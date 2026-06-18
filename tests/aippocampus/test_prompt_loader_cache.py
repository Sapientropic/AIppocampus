from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime import io_mtime_cache  # noqa: E402
from aippocampus_runtime.dream import working_memory_publication  # noqa: E402
from aippocampus_runtime.navigation import associations, cognitive_map  # noqa: E402
from aippocampus_runtime.registry import store as registry_store  # noqa: E402


class PromptLoaderCacheTests(unittest.TestCase):
    def tearDown(self) -> None:
        io_mtime_cache.clear_mtime_cache()

    def test_json_loaders_reuse_unchanged_mtime_signature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "threads.json"
            cmap = root / "cognitive_map.json"
            assoc = root / "associations.json"
            registry.write_text(
                json.dumps({"schema_version": 1, "threads": []}),
                encoding="utf-8",
            )
            cmap.write_text(json.dumps({"routes": []}), encoding="utf-8")
            assoc.write_text(json.dumps({"schema_version": 1, "terms": {}}), encoding="utf-8")

            for _ in range(3):
                registry_store.load_registry(registry)
                cognitive_map.load_cognitive_map(cmap)
                associations.load_associations(assoc)

            self.assertEqual(io_mtime_cache.read_count(registry), 1)
            self.assertEqual(io_mtime_cache.read_count(cmap), 1)
            self.assertEqual(io_mtime_cache.read_count(assoc), 1)

            time.sleep(0.01)
            cmap.write_text(json.dumps({"routes": [{"route_id": "changed"}]}), encoding="utf-8")
            cognitive_map.load_cognitive_map(cmap)
            self.assertEqual(io_mtime_cache.read_count(cmap), 2)

    def test_working_memory_jsonl_loader_reuses_unchanged_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "working-memory.jsonl"
            path.write_text(
                json.dumps({"kind": "aippocampus_working_memory", "title": "one"})
                + "\n",
                encoding="utf-8",
            )

            for _ in range(3):
                rows = working_memory_publication.load_working_memory(path)
                self.assertEqual(len(rows), 1)

            self.assertEqual(io_mtime_cache.read_count(path), 1)

    def test_cognitive_map_matching_reuses_signature_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cognitive_map.json"
            path.write_text(
                json.dumps(
                    {
                        "routes": [
                            {
                                "route_id": f"route_{index}",
                                "route_cues": [f"decoy cue {index}"],
                                "confidence": 0.5,
                            }
                            for index in range(500)
                        ]
                        + [
                            {
                                "route_id": "route_target",
                                "route_cues": ["needle continuity route"],
                                "confidence": 0.9,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            data = cognitive_map.load_cognitive_map(path)
            first = cognitive_map.match_cognitive_map("needle continuity route", data)
            with mock.patch.object(
                cognitive_map,
                "cue_matches",
                side_effect=AssertionError("memoized match should not rescan cues"),
            ):
                second = cognitive_map.match_cognitive_map("needle continuity route", data)

        self.assertEqual(first, second)
        self.assertEqual(second[0]["route_id"], "route_target")


if __name__ == "__main__":
    unittest.main()
