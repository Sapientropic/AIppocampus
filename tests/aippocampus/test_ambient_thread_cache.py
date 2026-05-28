from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ambient_thread_cache as cache  # noqa: E402


class AmbientThreadCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_thread_cache_reuses_cards_without_raw_prompt_or_workspace_text(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        card = {
            "card_id": "arc_1",
            "theme": "continuity",
            "support_level": "scent",
            "source_refs": [{"thread_key": "session:old"}],
        }

        written = cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-1",
            cards=[card],
            mode="active_gentle_nudge",
            confidence="medium",
        )
        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-1",
        )
        raw = cache_path.read_text(encoding="utf-8")

        self.assertEqual(written["status"], "written")
        self.assertEqual(loaded["status"], "hit")
        self.assertEqual(loaded["cards"][0]["theme"], "continuity")
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("prompt", raw.casefold())

    def test_thread_cache_preserves_validation_and_topic_metadata(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        card = {
            "card_id": "arc_validation",
            "theme": "validated ambient recall",
            "support_level": "evidence",
            "source_refs": [{"thread_key": "session:old", "line": 42, "message_id": "msg-1"}],
            "source_validation": {
                "status": "supported",
                "checked_ref_count": 1,
                "supported_ref_count": 1,
            },
        }

        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-validation",
            cards=[card],
            mode="source_backed_recall_card",
            confidence="high",
            query_aliases=["ambient recall", "warm scout"],
            topic_epoch_decision={"action": "rotate", "label": "ambient recall", "confidence": 0.8},
            visibility_bias="source_backed_recall_card",
        )
        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-validation",
        )
        raw = cache_path.read_text(encoding="utf-8")

        self.assertEqual(loaded["status"], "hit")
        self.assertEqual(loaded["cards"][0]["source_validation"]["status"], "supported")
        self.assertEqual(loaded["query_aliases"], ["ambient recall", "warm scout"])
        self.assertEqual(loaded["topic_epoch_decision"]["action"], "rotate")
        self.assertEqual(loaded["visibility_bias"], "source_backed_recall_card")
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("prompt", raw.casefold())

    def test_cache_entry_expires(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-1",
            cards=[{"card_id": "arc_1", "theme": "old"}],
        )
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        first_key = next(iter(data["entries"]))
        data["entries"][first_key]["updated_unix"] = time.time() - 100
        cache_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = cache.read_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-1",
            ttl_seconds=1,
        )

        self.assertEqual(loaded["status"], "expired")
        self.assertEqual(loaded["cards"], [])

    def test_topic_epoch_is_stable_without_raw_prompt_text(self) -> None:
        first = cache.topic_epoch_from_terms(["ambient recall", "Card/cache", "ambient"])
        second = cache.topic_epoch_from_terms(["ambient", "Card/cache", "ambient recall"])
        different = cache.topic_epoch_from_terms(["routine coding", "button"])

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertTrue(first.startswith("epoch_"))

    def test_optional_residue_export_writes_dream_seed_without_raw_prompt_or_workspace(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        residue_path = self.root / "ambient-residue.jsonl"
        card = {
            "card_id": "arc_seed",
            "theme": "continuity after transformation",
            "support_level": "candidate",
            "visibility": "active_gentle_nudge",
            "source_refs": [{"thread_key": "session:old", "line": 42, "message_id": "msg-1"}],
        }

        result = cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-dream",
            cards=[card],
            residue_path=residue_path,
            residue_reason="topic_epoch_rotated",
        )
        rows = [
            json.loads(line)
            for line in residue_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        raw = residue_path.read_text(encoding="utf-8")

        self.assertEqual(result["residue_export"]["status"], "written")
        self.assertEqual(rows[0]["kind"], "aippocampus_ambient_residue")
        self.assertEqual(rows[0]["status"], "dream_seed")
        self.assertEqual(rows[0]["reason"], "topic_epoch_rotated")
        self.assertEqual(rows[0]["topic_epoch"], "epoch-dream")
        self.assertEqual(rows[0]["card_ids"], ["arc_seed"])
        self.assertEqual(rows[0]["support_levels"], ["candidate"])
        self.assertIn("dream_task_seed", rows[0]["downstream_use"])
        self.assertTrue(rows[0]["source_ref_fingerprints"])
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("prompt", raw.casefold())

    def test_residue_export_skips_unsourced_single_scent(self) -> None:
        cache_path = self.root / "ambient-thread-cache.json"
        residue_path = self.root / "ambient-residue.jsonl"

        result = cache.write_thread_cache(
            cache_path,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-scent",
            cards=[
                {
                    "card_id": "arc_scent",
                    "theme": "generic scent",
                    "support_level": "scent",
                    "visibility": "active_gentle_nudge",
                    "source_refs": [],
                }
            ],
            residue_path=residue_path,
            residue_reason="cache_expired",
        )

        self.assertEqual(result["residue_export"]["status"], "skipped_no_source_refs")
        self.assertFalse(residue_path.exists())


if __name__ == "__main__":
    unittest.main()
