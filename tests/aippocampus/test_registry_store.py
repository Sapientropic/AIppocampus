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

    def test_update_registry_transaction_holds_lease_during_materialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "threads.json"
            md_path = root / "threads.md"
            materialize_started = threading.Event()
            peer_entered = threading.Event()
            peer_done = threading.Event()
            release_materialize = threading.Event()
            errors: list[BaseException] = []

            def transaction_worker() -> None:
                try:
                    def materialize() -> None:
                        materialize_started.set()
                        release_materialize.wait(timeout=5)

                    def update(registry: dict) -> dict:
                        return store.upsert_thread(
                            registry,
                            {
                                "thread_key": "transaction",
                                "title": "transaction",
                                "updated_at": "2026-06-03T00:00:01Z",
                            },
                        )

                    store.update_registry_transaction(
                        json_path,
                        md_path,
                        materialize=materialize,
                        updater=update,
                    )
                except BaseException as exc:
                    errors.append(exc)

            def peer_worker() -> None:
                try:
                    materialize_started.wait(timeout=5)
                    peer_entered.set()

                    def update(registry: dict) -> dict:
                        return store.upsert_thread(
                            registry,
                            {
                                "thread_key": "peer",
                                "title": "peer",
                                "updated_at": "2026-06-03T00:00:02Z",
                            },
                        )

                    store.update_registry(json_path, md_path, update)
                    peer_done.set()
                except BaseException as exc:
                    errors.append(exc)

            transaction = threading.Thread(target=transaction_worker)
            peer = threading.Thread(target=peer_worker)
            transaction.start()
            self.assertTrue(materialize_started.wait(timeout=5))
            peer.start()
            self.assertTrue(peer_entered.wait(timeout=5))
            host_timeout_sleep(
                0.05,
                reason="prove peer registry update waits while transaction materializes",
            )
            self.assertFalse(peer_done.is_set())
            release_materialize.set()
            transaction.join(timeout=5)
            peer.join(timeout=5)

            self.assertFalse(errors)
            self.assertTrue(peer_done.is_set())
            registry = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {entry["thread_key"] for entry in registry["threads"]},
                {"transaction", "peer"},
            )

if __name__ == "__main__":
    unittest.main()
