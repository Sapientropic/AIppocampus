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
from aippocampus_runtime.recall import semantic_recall_gate as gate  # noqa: E402
from aippocampus_runtime.recall import semantic_trigger_compaction as compaction  # noqa: E402


def source_ref() -> dict[str, Any]:
    return {"thread_key": "session:semantic", "message_id": "msg-1", "line": 12}


def semantic_trigger_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "schema_version": 1,
        "kind": "aippocampus_semantic_trigger",
        "trigger_id": "st_dead_letter_semantic_trigger",
        "status": "active",
        "source": "semantic_trigger_router",
        "title": "Raw semantic trigger title",
        "concept": "Raw semantic concept",
        "aliases": ["raw semantic alias", "semantic dead letter cue"],
        "activation_cues": ["raw activation cue"],
        "when_to_use": "Raw trigger guidance should be compacted.",
        "when_not_to_use": "Raw negative guidance should be compacted.",
        "confidence": 0.91,
        "source_refs": [source_ref()],
    }
    row.update(overrides)
    return row


def dead_letter_manifest_for_trigger(
    row: dict[str, Any],
    *,
    protected: bool = False,
) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "surface_id": row["trigger_id"],
        "surface_kind": "semantic_trigger",
        "conflict_key": "semantic-dead-letter",
        "pruning_action": "retire",
        "wrong_route_drag_count": 4,
        "source_refs": row["source_refs"],
        "provenance_pointer": "semantic-triggers:test-fixture",
    }
    if protected:
        surface["promotion_candidate_refs"] = ["promotion-candidate-still-needs-trigger"]
    return apply_dead_letter_candidate_manifest(
        [surface],
        applied_at="2026-06-05T03:00:00Z",
    )


class SemanticTriggerCompactionTests(unittest.TestCase):
    def test_dead_letter_manifest_compacts_matching_semantic_trigger_payload(self) -> None:
        row = semantic_trigger_row()
        manifest = dead_letter_manifest_for_trigger(row)

        next_rows, report = compaction.compact_semantic_trigger_payloads_from_dead_letter_manifest(
            [row],
            manifest,
            compacted_at="2026-06-05T03:05:00Z",
        )

        self.assertEqual(report["kind"], "aippocampus_semantic_trigger_payload_compaction_manifest")
        self.assertEqual(report["status"], "compacted")
        self.assertEqual(report["metrics"]["payload_compacted_count"], 1)
        compacted = next_rows[0]
        self.assertTrue(compacted["payload_compacted"])
        self.assertEqual(compacted["surface_kind"], "semantic_trigger")
        self.assertEqual(compacted["status"], "payload_compacted")
        self.assertEqual(compacted["lifecycle_action"], "payload_compacted")
        self.assertEqual(compacted["dead_letter_lifecycle_action"], "dead_lettered")
        self.assertEqual(compacted["source_ref_count"], 1)
        self.assertTrue(compacted["source_refs_preserved"])
        self.assertEqual(
            compacted["provenance_pointer_hash"],
            manifest["updates"][0]["provenance_pointer_hash"],
        )
        self.assertNotIn("trigger_id", compacted)
        self.assertNotIn("title", compacted)
        self.assertNotIn("concept", compacted)
        self.assertNotIn("aliases", compacted)
        self.assertNotIn("activation_cues", compacted)
        self.assertNotIn("when_to_use", compacted)
        self.assertNotIn("when_not_to_use", compacted)
        self.assertNotIn("source_refs", compacted)

        serialized_report = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("Raw semantic", serialized_report)
        self.assertNotIn("raw activation cue", serialized_report)
        self.assertNotIn("session:semantic", serialized_report)
        self.assertFalse(report["contract"]["foreground_hook_mutation"])
        self.assertFalse(report["privacy_boundary"]["raw_activation_payload_serialized"])

    def test_semantic_trigger_compaction_skips_protected_and_unsafe_updates(self) -> None:
        row = semantic_trigger_row()
        protected_manifest = dead_letter_manifest_for_trigger(row, protected=True)

        next_rows, protected_report = (
            compaction.compact_semantic_trigger_payloads_from_dead_letter_manifest(
                [row],
                protected_manifest,
                compacted_at="2026-06-05T03:05:00Z",
            )
        )

        self.assertFalse(next_rows[0].get("payload_compacted"))
        self.assertEqual(protected_report["metrics"]["payload_compacted_count"], 0)
        self.assertEqual(protected_report["skipped"][0]["skip_reason"], "referenced_row_protected")

        unsafe_manifest = dead_letter_manifest_for_trigger(row)
        unsafe_manifest["updates"][0]["source_refs_preserved"] = False
        _next_rows, unsafe_report = (
            compaction.compact_semantic_trigger_payloads_from_dead_letter_manifest(
                [row],
                unsafe_manifest,
                compacted_at="2026-06-05T03:05:00Z",
            )
        )

        self.assertEqual(unsafe_report["metrics"]["payload_compacted_count"], 0)
        self.assertEqual(unsafe_report["metrics"]["unsafe_update_count"], 1)
        self.assertEqual(unsafe_report["skipped"][0]["skip_reason"], "unsafe_dead_letter_update")

    def test_compacted_semantic_trigger_tombstone_stays_out_of_foreground_gate(self) -> None:
        row = semantic_trigger_row()
        manifest = dead_letter_manifest_for_trigger(row)
        next_rows, _report = compaction.compact_semantic_trigger_payloads_from_dead_letter_manifest(
            [row],
            manifest,
            compacted_at="2026-06-05T03:05:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "semantic_triggers.jsonl"
            path.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in next_rows),
                encoding="utf-8",
            )

            self.assertEqual(gate.load_semantic_triggers(path), [])


if __name__ == "__main__":
    unittest.main()
