from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import artifact_publish  # noqa: E402
import build_index  # noqa: E402
import search_rollout  # noqa: E402


def canonical(path: str | Path) -> Path:
    return Path(path).resolve()


def message(*, sha1: str, text: str) -> dict:
    return {
        "line": 1,
        "timestamp": "2026-05-30T00:00:00Z",
        "role": "user",
        "kind": "message",
        "phase": "",
        "turn_index": 1,
        "is_final": False,
        "sha1": sha1,
        "text": text,
    }


TURN = {
    "id": 1,
    "user_line": 1,
    "user_timestamp": "2026-05-30T00:00:00Z",
    "final_line": None,
    "final_timestamp": None,
    "fallback_assistant_line": None,
    "fallback_assistant_timestamp": None,
    "commentary_count": 0,
    "tool_call_count": 0,
    "tool_output_count": 0,
    "start_line": 1,
    "end_line": 1,
}


def write_legacy_sqlite(path: Path, text: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE messages(sha1 TEXT PRIMARY KEY, text TEXT)")
        con.execute("INSERT INTO messages(sha1, text) VALUES (?, ?)", ("legacy", text))
        con.commit()
    finally:
        con.close()


class BuildIndexTests(unittest.TestCase):
    def test_rebuild_succeeds_while_reader_holds_existing_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            build_index.make_sqlite(
                sqlite_path,
                [message(sha1="old", text="old visible text")],
                [],
                [TURN],
                rag_cache=False,
            )

            reader = sqlite3.connect(sqlite_path)
            try:
                reader.execute("BEGIN")
                self.assertEqual(
                    reader.execute("SELECT text FROM messages").fetchone()[0],
                    "old visible text",
                )

                build_index.make_sqlite(
                    sqlite_path,
                    [message(sha1="new", text="new visible text")],
                    [],
                    [TURN],
                    rag_cache=False,
                )

                self.assertEqual(
                    reader.execute("SELECT text FROM messages").fetchone()[0],
                    "old visible text",
                )
                reader.commit()
                self.assertEqual(
                    reader.execute("SELECT text FROM messages").fetchone()[0],
                    "new visible text",
                )
            finally:
                reader.close()

            fresh = sqlite3.connect(sqlite_path)
            try:
                self.assertEqual(
                    fresh.execute("SELECT text FROM messages").fetchone()[0],
                    "new visible text",
                )
            finally:
                fresh.close()

            leftovers = sorted(
                path.name
                for path in Path(tmp).iterdir()
                if ".tmp-" in path.name or path.name == ".index-publish.lock"
            )
            self.assertEqual(leftovers, [])

    def test_make_sqlite_rejects_concurrent_publish_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".index-publish.lock").write_text("held", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "lease already held"):
                build_index.make_sqlite(
                    root / "source_index.sqlite",
                    [message(sha1="new", text="new visible text")],
                    [],
                    [TURN],
                    rag_cache=False,
                )

    def test_artifact_lease_recovers_stale_lease_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lease = root / ".index-publish.lock"
            lease.write_text("interrupted writer\n", encoding="utf-8")
            stale_time = time.time() - 10
            os.utime(lease, (stale_time, stale_time))

            with artifact_publish.artifact_lease(
                root,
                ".index-publish.lock",
                stale_after_seconds=1,
            ) as active:
                self.assertEqual(active, lease)
                payload = json.loads(lease.read_text(encoding="utf-8"))
                self.assertEqual(payload["kind"], "aippocampus_artifact_writer_lease")

            self.assertFalse(lease.exists())

    def test_locked_legacy_destination_publishes_versioned_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "source_index.sqlite"
            write_legacy_sqlite(sqlite_path, "legacy visible text")

            reader = sqlite3.connect(sqlite_path)
            try:
                reader.execute("BEGIN")
                self.assertEqual(
                    reader.execute("SELECT text FROM messages").fetchone()[0],
                    "legacy visible text",
                )

                status = build_index.make_sqlite(
                    sqlite_path,
                    [message(sha1="new", text="new visible text")],
                    [],
                    [TURN],
                    rag_cache=False,
                    sqlite_busy_timeout_ms=100,
                )

                publish = status["publish"]
                self.assertEqual(publish["publish_method"], "versioned_pointer_fallback")
                current = Path(publish["current"])
                self.assertTrue(current.is_file())
                self.assertEqual(artifact_publish.resolve_sqlite_index_path(sqlite_path), current)

                current_con = sqlite3.connect(current)
                try:
                    self.assertEqual(
                        current_con.execute("SELECT text FROM messages").fetchone()[0],
                        "new visible text",
                    )
                finally:
                    current_con.close()

                self.assertEqual(
                    reader.execute("SELECT text FROM messages").fetchone()[0],
                    "legacy visible text",
                )
            finally:
                reader.close()

    def test_resolve_sqlite_index_path_uses_last_known_good_when_current_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "source_index.sqlite"
            versions = root / "versions"
            versions.mkdir()
            current = versions / "source_index-missing.sqlite"
            last_known_good = versions / "source_index-lkg.sqlite"
            write_legacy_sqlite(last_known_good, "last good text")
            (root / "source_index.pointer.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "aippocampus_sqlite_index_pointer",
                        "stable": str(sqlite_path),
                        "current": str(current),
                        "last_known_good": str(last_known_good),
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                artifact_publish.resolve_sqlite_index_path(sqlite_path),
                last_known_good,
            )

    def test_auto_index_path_follows_project_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_dir = root / ".aippocampus"
            versions = index_dir / "versions"
            versions.mkdir(parents=True)
            current = versions / "source_index-current.sqlite"
            write_legacy_sqlite(current, "current text")
            (index_dir / "source_index.pointer.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "aippocampus_sqlite_index_pointer",
                        "stable": "source_index.sqlite",
                        "current": "versions/source_index-current.sqlite",
                        "last_known_good": "source_index.sqlite",
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                search_rollout.auto_index_path(str(root), None, prefer_existing=True),
                canonical(current),
            )


if __name__ == "__main__":
    unittest.main()
