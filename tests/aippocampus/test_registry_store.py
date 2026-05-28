from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import registry_store  # noqa: E402


class RegistryStoreTests(unittest.TestCase):
    def test_load_registry_rejects_corrupt_existing_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "threads.json"
            registry_path.write_text("{broken", encoding="utf-8")

            with self.assertRaises(registry_store.RegistryReadError):
                registry_store.load_registry(registry_path)

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
        updated = registry_store.upsert_thread(
            registry,
            {"thread_key": "session:one", "title": "new", "updated_at": "2026-01-03"},
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "threads.json"
            md_path = root / "threads.md"
            registry_store.save_registry(updated, json_path, md_path)

            data = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")

        self.assertEqual([item["thread_key"] for item in data["threads"]], ["session:one", "session:two"])
        self.assertEqual(data["threads"][0]["title"], "new")
        self.assertIn("Thread Memory Registry", markdown)
        self.assertIn("session:one", markdown)


if __name__ == "__main__":
    unittest.main()
