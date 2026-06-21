from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from aippocampus_runtime.registry import store as store
from tests.aippocampus.timing_fixtures import host_timeout_sleep


class RegistryStoreTests(unittest.TestCase):
    def test_load_registry_rejects_corrupt_existing_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "threads.json"
            registry_path.write_text("{broken", encoding="utf-8")

            with self.assertRaises(store.RegistryReadError):
                store.load_registry(registry_path)

            self.assertEqual(registry_path.read_text(encoding="utf-8"), "{broken")

    def test_upsert_thread_replaces_existing_entry_and_saves_markdown(self) -> None:
        registry = {
            "schema_version": 1,
            "updated_at": "old",
            "threads": [
                {"thread_key": "session:one", "title": "old", "updated_at": "2026-01-01"},
                {"thread_key": "session:two", "title": "two", "updated_at": "2026-01-02"},
            ],
        }
        updated = store.upsert_thread(
            registry,
            {"thread_key": "session:one", "title": "new", "updated_at": "2026-01-03"},
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "threads.json"
            md_path = root / "threads.md"
            store.save_registry(updated, json_path, md_path)

            data = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")

        self.assertEqual(
            [item["thread_key"] for item in data["threads"]], ["session:one", "session:two"]
        )
        self.assertEqual(data["threads"][0]["title"], "new")
        self.assertIn("Thread Memory Registry", markdown)
        self.assertIn("session:one", markdown)

    def test_update_registry_serializes_concurrent_control_plane_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "threads.json"
            md_path = root / "threads.md"
            start = threading.Barrier(2)
            errors: list[BaseException] = []

            def worker(thread_key: str) -> None:
                try:
                    start.wait(timeout=5)

                    def update(registry: dict) -> dict:
                        host_timeout_sleep(
                            0.03,
                            reason="keep a writer inside the registry lease while the peer contends",
                        )
                        return store.upsert_thread(
                            registry,
                            {
                                "thread_key": thread_key,
                                "title": thread_key,
                                "updated_at": f"2026-06-03T00:00:0{thread_key[-1]}Z",
                            },
                        )

                    store.update_registry(json_path, md_path, update)
                except BaseException as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(target=worker, args=("thread-1",)),
                threading.Thread(target=worker, args=("thread-2",)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertFalse(errors)
            registry = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {entry["thread_key"] for entry in registry["threads"]},
                {"thread-1", "thread-2"},
            )
            self.assertIn("thread-1", md_path.read_text(encoding="utf-8"))
            self.assertIn("thread-2", md_path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
