from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from aippocampus_runtime.io_integrity import (
    cleanup_stale_tmp_artifacts,
    prepared_atomic_replace,
    stale_tmp_recovery_card,
)


class IoIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_interleaved_atomic_replace_writers_use_distinct_tmp_paths(self) -> None:
        path = self.root / "state.json"

        with prepared_atomic_replace(path) as first_tmp:
            first_tmp.write_text("first", encoding="utf-8")
            with prepared_atomic_replace(path) as second_tmp:
                second_tmp.write_text("second", encoding="utf-8")
                self.assertNotEqual(first_tmp, second_tmp)
            self.assertEqual(path.read_text(encoding="utf-8"), "second")
        self.assertEqual(path.read_text(encoding="utf-8"), "first")

        leftovers = list(self.root.glob(".*.aippocampus-*.tmp"))
        self.assertEqual(leftovers, [])

    def test_stale_tmp_recovery_counts_historical_patterns_and_bytes(self) -> None:
        stale_files = {
            ".threads.json.tmp-20260625": b"threads",
            "source_index.sqlite.tmp-20260625": b"sqlite",
            ".state.json.aippocampus-123.tmp": b"atomic",
            ".plugin.tmp-update": b"update",
            ".plugin.tmp-rollback": b"rollback",
        }
        for name, body in stale_files.items():
            path = self.root / name
            path.write_bytes(body)
            old = time.time() - 600
            path.touch()
            path.write_bytes(body)
            os.utime(path, (old, old))
        plugin_tmp = self.root / ".aippocampus.tmp-aippocampus-install"
        plugin_tmp.mkdir()
        (plugin_tmp / "payload.json").write_text("{}", encoding="utf-8")
        sqlite_build = self.root / ".source_index.sqlite.sqlite-build-123"
        sqlite_build.mkdir()
        (sqlite_build / "source_index.sqlite").write_bytes(b"db")
        ignored = self.root / "user-owned.tmp"
        ignored.write_text("leave me alone", encoding="utf-8")
        old = time.time() - 600
        for path in [
            plugin_tmp,
            plugin_tmp / "payload.json",
            sqlite_build,
            sqlite_build / "source_index.sqlite",
            ignored,
        ]:
            os.utime(path, (old, old))

        card = stale_tmp_recovery_card(self.root, max_age_seconds=300)

        self.assertFalse(card["ok"])
        self.assertEqual(card["stale_tmp_file_count"], 5)
        self.assertEqual(card["orphaned_plugin_install_dir_count"], 1)
        self.assertEqual(card["stale_tmp_by_pattern"]["legacy_threads_json_tmp_dash"]["count"], 1)
        self.assertEqual(card["stale_tmp_by_pattern"]["legacy_tmp_dash"]["count"], 3)
        self.assertEqual(card["stale_tmp_by_pattern"]["aippocampus_atomic_write_tmp"]["count"], 1)
        self.assertEqual(card["stale_tmp_by_pattern"]["plugin_install_tmp_dir"]["count"], 1)
        self.assertEqual(card["stale_tmp_by_pattern"]["sqlite_build_tmp_dir"]["count"], 1)
        self.assertGreater(card["stale_tmp_total_bytes"], 0)
        self.assertEqual(
            card["safe_next_actions"][1]["command"],
            "aippocampus maintenance apply --cleanup-interrupted-writes --summary-json",
        )

    def test_cleanup_stale_tmp_artifacts_deletes_only_ai_owned_patterns(self) -> None:
        owned = self.root / ".threads.json.tmp-20260625"
        owned.write_text("stale", encoding="utf-8")
        ignored = self.root / "user-owned.tmp"
        ignored.write_text("keep", encoding="utf-8")
        old = time.time() - 600

        for path in [owned, ignored]:
            os.utime(path, (old, old))

        result = cleanup_stale_tmp_artifacts(self.root, max_age_seconds=300)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(owned.exists())
        self.assertTrue(ignored.exists())


if __name__ == "__main__":
    unittest.main()
