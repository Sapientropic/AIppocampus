from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops.activation_authority_audit import (  # noqa: E402
    apply_dead_letter_candidate_manifest,
)
from aippocampus_runtime.recall import active_recall_lock as locks  # noqa: E402
from aippocampus_runtime.recall import active_recall_lock_compaction as compaction  # noqa: E402


def source_ref() -> dict[str, Any]:
    return {"thread_key": "session:active-lock", "message_id": "msg-1", "line": 12}


def dead_letter_manifest_for_lock(
    lock: dict[str, Any],
    *,
    protected: bool = False,
) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "surface_id": lock["lock_id"],
        "surface_kind": "active_recall_lock",
        "conflict_key": "active-lock-dead-letter",
        "pruning_action": "retire",
        "wrong_route_drag_count": 4,
        "source_refs": lock["candidate_refs"],
        "provenance_pointer": "active-recall-lock:test-fixture",
    }
    if protected:
        surface["source_reopen_evidence_refs"] = ["reopen-evidence-still-needs-lock"]
    return apply_dead_letter_candidate_manifest(
        [surface],
        applied_at="2026-06-05T04:00:00Z",
    )


class ActiveRecallLockCompactionTests(unittest.TestCase):
    def test_dead_letter_manifest_compacts_matching_active_recall_lock_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock_path = root / "active_recall_locks.json"
            lock = locks.start_or_update_recall_lock(
                lock_path,
                prompt="raw prompt text must not survive compaction",
                thread_id="thread-a",
                workspace="E:/private/workspace",
                topic_epoch="epoch-active-lock",
                candidate_refs=[source_ref()],
                query_aliases=["raw active recall alias"],
                route_reasons=["raw active recall route reason"],
            )
            store = json.loads(lock_path.read_text(encoding="utf-8"))
            manifest = dead_letter_manifest_for_lock(lock)

            next_store, report = (
                compaction.compact_active_recall_lock_payloads_from_dead_letter_manifest(
                    store,
                    manifest,
                    compacted_at="2026-06-05T04:05:00Z",
                )
            )

            self.assertEqual(
                report["kind"],
                "aippocampus_active_recall_lock_payload_compaction_manifest",
            )
            self.assertEqual(report["status"], "compacted")
            self.assertEqual(report["metrics"]["payload_compacted_count"], 1)
            compacted = next_store["entries"][lock["lock_id"]]
            self.assertTrue(compacted["payload_compacted"])
            self.assertEqual(compacted["surface_kind"], "active_recall_lock")
            self.assertEqual(compacted["status"], "payload_compacted")
            self.assertEqual(compacted["state"], "failed")
            self.assertEqual(compacted["lifecycle_action"], "payload_compacted")
            self.assertEqual(compacted["dead_letter_lifecycle_action"], "dead_lettered")
            self.assertEqual(compacted["source_ref_count"], 1)
            self.assertTrue(compacted["source_refs_preserved"])
            self.assertEqual(
                compacted["provenance_pointer_hash"],
                manifest["updates"][0]["provenance_pointer_hash"],
            )
            self.assertNotIn("candidate_refs", compacted)
            self.assertNotIn("query_aliases", compacted)
            self.assertNotIn("route_reasons", compacted)
            self.assertNotIn("prompt_fingerprint", compacted)
            self.assertNotIn("workspace_fingerprint", compacted)
            self.assertNotIn("thread_fingerprint", compacted)
            self.assertNotIn("freshness_vector", compacted)

            lock_path.write_text(json.dumps(next_store, ensure_ascii=False), encoding="utf-8")
            public = locks.read_recall_lock(lock_path, lock["lock_id"], record_consumer_read=False)
            self.assertEqual(public["state"], "failed")
            self.assertEqual(public["candidate_refs"], [])
            self.assertEqual(public["query_aliases"], [])
            self.assertEqual(public["route_reasons"], [])

            serialized_report = json.dumps(report, ensure_ascii=False, sort_keys=True)
            serialized_store = json.dumps(next_store, ensure_ascii=False, sort_keys=True)
            self.assertNotIn("raw active recall", serialized_report)
            self.assertNotIn("session:active-lock", serialized_report)
            self.assertNotIn("raw active recall", serialized_store)
            self.assertNotIn("session:active-lock", serialized_store)
            self.assertFalse(report["contract"]["foreground_hook_mutation"])
            self.assertFalse(report["privacy_boundary"]["raw_activation_payload_serialized"])

    def test_active_recall_lock_compaction_skips_protected_and_unsafe_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock_path = root / "active_recall_locks.json"
            lock = locks.start_or_update_recall_lock(
                lock_path,
                prompt="route",
                thread_id="thread-a",
                workspace=str(root),
                topic_epoch="epoch-active-lock",
                candidate_refs=[source_ref()],
            )
            store = json.loads(lock_path.read_text(encoding="utf-8"))
            protected_manifest = dead_letter_manifest_for_lock(lock, protected=True)

            next_store, protected_report = (
                compaction.compact_active_recall_lock_payloads_from_dead_letter_manifest(
                    store,
                    protected_manifest,
                    compacted_at="2026-06-05T04:05:00Z",
                )
            )

            self.assertFalse(next_store["entries"][lock["lock_id"]].get("payload_compacted"))
            self.assertEqual(protected_report["metrics"]["payload_compacted_count"], 0)
            self.assertEqual(protected_report["skipped"][0]["skip_reason"], "referenced_row_protected")

            unsafe_manifest = dead_letter_manifest_for_lock(lock)
            unsafe_manifest["updates"][0]["source_refs_preserved"] = False
            _next_store, unsafe_report = (
                compaction.compact_active_recall_lock_payloads_from_dead_letter_manifest(
                    store,
                    unsafe_manifest,
                    compacted_at="2026-06-05T04:05:00Z",
                )
            )

            self.assertEqual(unsafe_report["metrics"]["payload_compacted_count"], 0)
            self.assertEqual(unsafe_report["metrics"]["unsafe_update_count"], 1)
            self.assertEqual(unsafe_report["skipped"][0]["skip_reason"], "unsafe_dead_letter_update")


if __name__ == "__main__":
    unittest.main()
