from __future__ import annotations

import contextlib
import io
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

from aippocampus_runtime.artifacts import publish as artifact_publish  # noqa: E402
from aippocampus_runtime.recall import index_builder as build_index  # noqa: E402
from aippocampus_runtime.recall import rollout_search as search_rollout  # noqa: E402
from tests.aippocampus.redaction_fixtures import (  # noqa: E402
    fake_test_database_dsn,
    fake_test_email,
    fake_test_windows_path,
)


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

    def test_index_pointer_publishes_generation_and_reader_pins_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "source_index.sqlite"
            first_status = build_index.make_sqlite(
                sqlite_path,
                [message(sha1="old", text="old generation text")],
                [],
                [TURN],
                rag_cache=False,
            )
            first_publish = first_status["publish"]
            first_current = Path(first_publish["current"])
            first_generation = first_publish["current_generation"]

            self.assertEqual(first_current.name, "source_index.sqlite")
            self.assertEqual(first_current.parent.name, first_generation)
            self.assertEqual(first_current.parent.parent.name, "generations")

            reader = sqlite3.connect(first_current)
            try:
                reader.execute("BEGIN")
                self.assertEqual(
                    reader.execute("SELECT text FROM messages").fetchone()[0],
                    "old generation text",
                )

                second_status = build_index.make_sqlite(
                    sqlite_path,
                    [message(sha1="new", text="new generation text")],
                    [],
                    [TURN],
                    rag_cache=False,
                )
                second_publish = second_status["publish"]
                second_current = Path(second_publish["current"])
                pointer = json.loads((root / "source_index.pointer.json").read_text(encoding="utf-8"))

                self.assertNotEqual(second_current, first_current)
                self.assertEqual(second_current.parent.parent.name, "generations")
                self.assertEqual(second_publish["last_known_good_generation"], first_generation)
                self.assertEqual(pointer["current_generation"], second_publish["current_generation"])
                self.assertEqual(pointer["last_known_good_generation"], first_generation)
                self.assertEqual(pointer["compatibility_path"], "source_index.sqlite")
                self.assertEqual(
                    artifact_publish.resolve_sqlite_index_path(sqlite_path),
                    second_current,
                )
                self.assertEqual(
                    reader.execute("SELECT text FROM messages").fetchone()[0],
                    "old generation text",
                )
            finally:
                reader.close()

    def test_resolve_sqlite_index_path_falls_back_to_last_known_good_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "source_index.sqlite"
            first_status = build_index.make_sqlite(
                sqlite_path,
                [message(sha1="old", text="last known good generation")],
                [],
                [TURN],
                rag_cache=False,
            )
            first_current = Path(first_status["publish"]["current"])

            second_status = build_index.make_sqlite(
                sqlite_path,
                [message(sha1="new", text="dangling current generation")],
                [],
                [TURN],
                rag_cache=False,
            )
            second_publish = second_status["publish"]
            second_current = Path(second_publish["current"])
            self.assertNotEqual(second_current, first_current)

            second_current.unlink()

            pointer = json.loads((root / "source_index.pointer.json").read_text(encoding="utf-8"))
            self.assertEqual(pointer["current_generation"], second_publish["current_generation"])
            self.assertEqual(pointer["last_known_good_generation"], first_current.parent.name)
            self.assertEqual(
                artifact_publish.resolve_sqlite_index_path(sqlite_path),
                first_current,
            )

    def test_publish_does_not_prune_generations_without_reader_pin_ttl_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "source_index.sqlite"
            first_status = build_index.make_sqlite(
                sqlite_path,
                [message(sha1="first", text="first generation")],
                [],
                [TURN],
                rag_cache=False,
            )
            first_current = Path(first_status["publish"]["current"])

            build_index.make_sqlite(
                sqlite_path,
                [message(sha1="second", text="second generation")],
                [],
                [TURN],
                rag_cache=False,
            )
            build_index.make_sqlite(
                sqlite_path,
                [message(sha1="third", text="third generation")],
                [],
                [TURN],
                rag_cache=False,
            )

            self.assertTrue(first_current.is_file())

    def test_search_payload_pins_resolved_index_generation_for_query_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_dir = root / "index"
            current = index_dir / "generations" / "gen_current"
            current.mkdir(parents=True)
            sqlite_path = current / "source_index.sqlite"
            sqlite_path.write_bytes(b"")
            (index_dir / "source_index.pointer.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "aippocampus_sqlite_index_pointer",
                        "current_generation": "gen_current",
                        "last_known_good_generation": "gen_current",
                        "current": "generations/gen_current/source_index.sqlite",
                        "last_known_good": "generations/gen_current/source_index.sqlite",
                        "stable": "source_index.sqlite",
                    }
                ),
                encoding="utf-8",
            )
            observed_pins: list[dict] = []

            def fake_search(index: Path, *args, **kwargs) -> list[dict]:
                self.assertEqual(Path(index), sqlite_path)
                pin_dir = index_dir / ".reader-pins"
                pins = list(pin_dir.glob("*.json"))
                self.assertEqual(len(pins), 1)
                observed_pins.append(json.loads(pins[0].read_text(encoding="utf-8")))
                return []

            with unittest.mock.patch.object(
                search_rollout,
                "search_hybrid_index",
                side_effect=fake_search,
            ):
                payload = search_rollout.search_rollout_payload(
                    search_rollout.RolloutSearchOptions(
                        patterns=["memory"],
                        cwd=root,
                        index=index_dir / "source_index.sqlite",
                        mode="ranked",
                    )
                )

            self.assertEqual(payload["source"], str(sqlite_path))
            self.assertEqual(observed_pins[0]["generation"], "gen_current")
            self.assertFalse(list((index_dir / ".reader-pins").glob("*.json")))

    def test_raw_rollout_stream_search_bounds_large_tool_payload_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "rollout-large-tool.jsonl"
            huge_output = "needle " + ("tool-output-noise " * 600)
            rows = [
                {
                    "type": "session_meta",
                    "payload": {"id": "stream-session", "cwd": str(root)},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T00:00:01Z",
                    "payload": {"type": "user_message", "message": "normal visible prompt"},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-06-05T00:00:02Z",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-large",
                        "output": huge_output,
                    },
                },
            ]
            rollout.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )

            payload = search_rollout.search_rollout_payload(
                search_rollout.RolloutSearchOptions(
                    patterns=["needle"],
                    cwd=root,
                    rollout=rollout,
                    no_index=True,
                    include_tools=True,
                    snippet_chars=80,
                )
            )

        hit = payload["matches"][0]
        encoded_hit = json.dumps(hit, ensure_ascii=False)

        self.assertEqual(payload["source"], "raw_rollout")
        self.assertEqual(payload["source_kind"], "raw_rollout")
        self.assertEqual(hit["source_ref"], "raw-line:3")
        self.assertEqual(hit["payload_class"], "tool_event")
        self.assertTrue(hit["truncated"])
        self.assertGreater(hit["text_bytes"], hit["snippet_bytes"])
        self.assertNotIn("raw_payload", hit)
        self.assertNotIn("tool-output-noise " * 50, encoded_hit)

    def test_raw_rollout_stream_search_requires_audit_flag_for_full_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "rollout-audit-tool.jsonl"
            huge_output = "needle " + ("audit-full-payload " * 80)
            rows = [
                {
                    "type": "session_meta",
                    "payload": {"id": "stream-session", "cwd": str(root)},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-06-05T00:00:01Z",
                    "payload": {"type": "user_message", "message": "normal visible prompt"},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-06-05T00:00:02Z",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-audit",
                        "output": huge_output,
                    },
                },
            ]
            rollout.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )

            payload = search_rollout.search_rollout_payload(
                search_rollout.RolloutSearchOptions(
                    patterns=["needle"],
                    cwd=root,
                    rollout=rollout,
                    no_index=True,
                    include_tools=True,
                    include_raw_payload=True,
                    snippet_chars=80,
                )
            )

        hit = payload["matches"][0]

        self.assertIn("raw_payload", hit)
        self.assertIn("audit-full-payload " * 20, hit["raw_payload"])

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

    def test_public_export_index_profile_sanitizes_jsonl_and_sqlite_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript = root / "generic.jsonl"
            private_path = fake_test_windows_path("memory_gate.py")
            email = fake_test_email()
            database_dsn = fake_test_database_dsn()
            private_text = (
                f"Open {private_path}; email {email}; "
                f"database {database_dsn}."
            )
            transcript.write_text(
                json.dumps(
                    {
                        "session_id": "public-export-index",
                        "timestamp": "2026-06-03T00:00:00Z",
                        "cwd": str(root),
                        "role": "user",
                        "text": private_text,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "index"

            with contextlib.redirect_stdout(io.StringIO()):
                code = build_index.main(
                    [
                        "--provider",
                        "generic-jsonl",
                        "--cwd",
                        str(root),
                        "--rollout",
                        str(transcript),
                        "--output-dir",
                        str(output_dir),
                        "--redaction-profile",
                        "public-export",
                        "--json",
                    ]
                )

            self.assertEqual(code, 0)
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["redaction_profile"], "public-export")
            self.assertEqual(manifest["privacy_boundary"]["source_text_profile"], "public-export")

            messages_text = (output_dir / "messages.jsonl").read_text(encoding="utf-8")
            self.assertIn("<redacted:email>", messages_text)
            self.assertIn("<redacted:connection-string>", messages_text)
            self.assertIn("<redacted:local-path>", messages_text)
            for raw in (
                email,
                database_dsn,
                "FAKE_TEST_LOCAL_PATH",
            ):
                self.assertNotIn(raw, messages_text)

            con = sqlite3.connect(output_dir / "source_index.sqlite")
            try:
                sqlite_text = con.execute("SELECT text FROM messages").fetchone()[0]
                self.assertIn("<redacted:email>", sqlite_text)
                self.assertNotIn(email, sqlite_text)
                self.assertNotIn(database_dsn, sqlite_text)
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
