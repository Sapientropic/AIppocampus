from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import active_recall_lock as locks  # noqa: E402


class ActiveRecallLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:old",
                            "paths": {
                                "clean_source_messages_jsonl": str(
                                    self.root / "clean-source" / "messages.jsonl"
                                )
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        messages = self.root / "clean-source" / "messages.jsonl"
        messages.parent.mkdir()
        messages.write_text(
            json.dumps(
                {
                    "message_id": "msg-1",
                    "turn_id": "turn-1",
                    "turn_index": 3,
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "text": "Source-backed line that only reopen may show.",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lock_serializes_navigation_only_without_raw_prompt_or_workspace(self) -> None:
        path = self.root / "active-recall-locks.json"
        result = locks.start_or_update_recall_lock(
            path,
            prompt="继续 E:/private/workspace 里那个 SECRET_TOKEN=abc123 的潜意识语义判断",
            thread_id="thread-a",
            workspace="E:/private/workspace",
            topic_epoch="epoch-topic",
            registry_path=self.registry,
            candidate_refs=[
                {
                    "thread_key": "session:old",
                    "message_id": "msg-1",
                    "line": 42,
                    "snippet": "DO NOT STORE SOURCE TEXT",
                }
            ],
            query_aliases=["active recall lock"],
            route_reasons=["foreground scent has source refs"],
        )
        raw = path.read_text(encoding="utf-8")

        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["support_level"], "scent")
        self.assertTrue(result["source_reopen_required"])
        self.assertEqual(result["candidate_ref_count"], 1)
        self.assertEqual(result["reopenable_ref_count"], 1)
        self.assertNotIn("SECRET_TOKEN", raw)
        self.assertNotIn("private/workspace", raw.replace("\\", "/"))
        self.assertNotIn("DO NOT STORE SOURCE TEXT", raw)
        self.assertNotIn("潜意识语义判断", raw)
        self.assertEqual(result["candidate_refs"][0]["thread_key"], "session:old")
        self.assertNotIn("snippet", result["candidate_refs"][0])

    def test_expired_or_changed_freshness_lock_is_not_reused(self) -> None:
        path = self.root / "active-recall-locks.json"
        created = locks.start_or_update_recall_lock(
            path,
            prompt="same topic",
            thread_id="thread-a",
            workspace=str(self.root),
            topic_epoch="epoch-topic",
            registry_path=self.registry,
            candidate_refs=[{"thread_key": "session:old", "message_id": "msg-1"}],
            ttl_seconds=1,
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"][created["lock_id"]]["expires_unix"] = time.time() - 10
        path.write_text(json.dumps(data), encoding="utf-8")

        expired = locks.read_recall_lock(path, created["lock_id"])
        topic_changed = locks.read_recall_lock(
            path,
            created["lock_id"],
            topic_epoch="epoch-other",
            registry_freshness_fingerprint=created["registry_freshness_fingerprint"],
        )

        self.assertEqual(expired["state"], "expired")
        self.assertEqual(topic_changed["state"], "expired")
        self.assertIn("topic_epoch_changed", topic_changed["diagnostics"]["invalidated_by"])

    def test_concurrent_writes_merge_candidate_refs_without_corrupting_file(self) -> None:
        path = self.root / "active-recall-locks.json"

        def writer(index: int) -> None:
            locks.start_or_update_recall_lock(
                path,
                prompt="merge this lock",
                thread_id="thread-a",
                workspace=str(self.root),
                topic_epoch="epoch-merge",
                registry_path=self.registry,
                candidate_refs=[{"thread_key": "session:old", "message_id": f"msg-{index}"}],
                query_aliases=[f"alias-{index}"],
            )

        threads = [threading.Thread(target=writer, args=(index,)) for index in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], locks.LOCK_SCHEMA_VERSION)
        entry = next(iter(data["entries"].values()))
        self.assertEqual(len(entry["candidate_refs"]), 6)
        self.assertEqual(len(entry["query_aliases"]), 6)

    def test_enriched_model_lock_stays_scent_until_source_reopen(self) -> None:
        path = self.root / "active-recall-locks.json"
        pending = locks.start_or_update_recall_lock(
            path,
            prompt="semantic route",
            thread_id="thread-a",
            workspace=str(self.root),
            topic_epoch="epoch-topic",
            registry_path=self.registry,
            state="pending",
            query_aliases=["semantic route"],
        )
        ready = locks.enrich_recall_lock(
            path,
            lock_id=pending["lock_id"],
            candidate_refs=[{"thread_key": "session:old", "message_id": "msg-1", "line": 42}],
            query_aliases=["thinking alias"],
            route_reasons=["thinking scout found route"],
            diagnostics={"cold_model_call": True, "fast_scout_used": False},
        )
        reopened = locks.reopen_lock_sources(
            path,
            lock_id=pending["lock_id"],
            registry_path=self.registry,
        )

        self.assertEqual(ready["state"], "ready")
        self.assertEqual(ready["support_level"], "scent")
        self.assertTrue(ready["source_reopen_required"])
        self.assertNotIn("snippet", json.dumps(ready))
        self.assertEqual(reopened["support_level"], "evidence")
        self.assertEqual(reopened["matches"][0]["text"], "Source-backed line that only reopen may show.")

    def test_thread_only_refs_do_not_mark_lock_ready(self) -> None:
        path = self.root / "active-recall-locks.json"
        lock = locks.start_or_update_recall_lock(
            path,
            prompt="book series cue",
            thread_id="thread-a",
            workspace=str(self.root),
            topic_epoch="epoch-topic",
            registry_path=self.registry,
            candidate_refs=[{"thread_key": "session:old"}],
            route_reasons=["soft_hypothesis_thread_route"],
        )
        reopened = locks.reopen_lock_sources(
            path,
            lock_id=lock["lock_id"],
            registry_path=self.registry,
        )

        self.assertEqual(lock["state"], "pending")
        self.assertEqual(lock["candidate_ref_count"], 1)
        self.assertEqual(lock["reopenable_ref_count"], 0)
        self.assertFalse(reopened["ok"])
        self.assertEqual(reopened["state"], "pending")
        self.assertEqual(reopened["errors"][0]["code"], "lock_not_ready")

    def test_legacy_ready_lock_without_reopenable_refs_is_downgraded_on_read(self) -> None:
        path = self.root / "active-recall-locks.json"
        lock = locks.start_or_update_recall_lock(
            path,
            prompt="legacy route",
            thread_id="thread-a",
            workspace=str(self.root),
            topic_epoch="epoch-topic",
            registry_path=self.registry,
            candidate_refs=[{"thread_key": "session:old"}],
            state="ready",
        )

        self.assertEqual(lock["state"], "pending")
        self.assertTrue(lock["diagnostics"]["ready_downgraded_no_reopenable_refs"])


if __name__ == "__main__":
    unittest.main()
