from __future__ import annotations

import json
import unittest
from typing import Any

from aippocampus_runtime.dream import lifecycle as dream_lifecycle
from aippocampus_runtime.dream import working_memory as wm
from aippocampus_runtime.dream import working_memory_compaction as compaction
from aippocampus_runtime.ops.activation_authority_audit import (
    apply_dead_letter_candidate_manifest,
)


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, Any]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }

def adjudicated_finding(**overrides: Any) -> dict[str, Any]:
    refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
    finding: dict[str, Any] = {
        "finding_kind": "dream_synthesized",
        "dream_function": "amplification",
        "review_state": "agent_adjudicated",
        "title": "Continuity source-ref bridge",
        "summary": "Use as a tentative bridge only when it changes the route.",
        "confidence": 0.66,
        "source_refs": refs,
        "bridge_claims": [
            {"claim": "This is a hypothesis over selected source refs.", "source_refs": refs}
        ],
        "downstream_use": ["working_memory", "ambient_recall_card"],
        "activation_cues": ["continuity source review", "source-ref continuity"],
    }
    finding.update(overrides)
    return finding

def dead_letter_manifest_for_row(
    row: dict[str, Any],
    *,
    protected: bool = False,
) -> dict[str, Any]:
    surface = {
        "surface_id": row["candidate_key"],
        "surface_kind": "working_memory",
        "pruning_action": "park",
        "wrong_route_drag_count": 4,
        "source_reopen_attempt_count": 4,
        "source_reopen_success_count": 0,
        "source_refs": row["source_refs"],
        "provenance_pointer": "dream-working-memory:test-fixture",
    }
    if protected:
        surface["dream_input_refs"] = ["dream-input-still-references-row"]
    return apply_dead_letter_candidate_manifest(
        [surface],
        applied_at="2026-06-05T01:00:00Z",
    )

class DreamWorkingMemoryCompactionTests(unittest.TestCase):
    def test_dead_letter_manifest_compacts_matching_working_memory_payload(self) -> None:
        rows = wm.adjudicated_dream_findings_to_working_memory([adjudicated_finding()])
        original = rows[0]
        manifest = dead_letter_manifest_for_row(original)

        next_rows, report = compaction.compact_dream_working_memory_payloads_from_dead_letter_manifest(
            rows,
            manifest,
            compacted_at="2026-06-05T01:05:00Z",
        )

        self.assertEqual(report["kind"], "aippocampus_dream_working_memory_payload_compaction_manifest")
        self.assertEqual(report["status"], "compacted")
        self.assertEqual(report["metrics"]["payload_compacted_count"], 1)
        self.assertEqual(report["metrics"]["dead_lettered_update_count"], 1)
        compacted = next_rows[0]
        self.assertTrue(compacted["payload_compacted"])
        self.assertEqual(compacted["surface_kind"], "working_memory")
        self.assertEqual(compacted["status"], "payload_compacted")
        self.assertEqual(compacted["lifecycle_action"], "payload_compacted")
        self.assertEqual(compacted["dead_letter_lifecycle_action"], "dead_lettered")
        self.assertEqual(compacted["source_ref_count"], 2)
        self.assertTrue(compacted["source_refs_preserved"])
        self.assertEqual(compacted["provenance_pointer_hash"], manifest["updates"][0]["provenance_pointer_hash"])
        self.assertNotIn("title", compacted)
        self.assertNotIn("summary", compacted)
        self.assertNotIn("recommendation", compacted)
        self.assertNotIn("trigger_terms", compacted)
        self.assertNotIn("activation_cues", compacted)
        self.assertNotIn("source_refs", compacted)
        self.assertNotIn("trust_horizon", compacted)
        self.assertNotIn("candidate_key", compacted)
        self.assertEqual(
            dream_lifecycle.dream_lifecycle_state(compacted),
            "payload_compacted",
        )
        self.assertEqual(
            dream_lifecycle.public_authority_tier(compacted),
            "diagnostic_only",
        )
        self.assertEqual(
            dream_lifecycle.working_memory_delivery_posture(compacted)["delivery_source_posture"],
            "diagnostic_only",
        )

        serialized_report = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("Continuity source-ref bridge", serialized_report)
        self.assertNotIn("tentative bridge", serialized_report)
        self.assertNotIn("session:a", serialized_report)
        self.assertFalse(report["contract"]["foreground_hook_mutation"])
        self.assertFalse(report["privacy_boundary"]["raw_activation_payload_serialized"])

    def test_working_memory_compaction_skips_protected_and_unsafe_updates(self) -> None:
        rows = wm.adjudicated_dream_findings_to_working_memory([adjudicated_finding()])
        protected_manifest = dead_letter_manifest_for_row(rows[0], protected=True)

        next_rows, protected_report = (
            compaction.compact_dream_working_memory_payloads_from_dead_letter_manifest(
                rows,
                protected_manifest,
                compacted_at="2026-06-05T01:05:00Z",
            )
        )

        self.assertFalse(next_rows[0].get("payload_compacted"))
        self.assertEqual(protected_report["metrics"]["payload_compacted_count"], 0)
        self.assertEqual(protected_report["skipped"][0]["skip_reason"], "referenced_row_protected")

        unsafe_manifest = dead_letter_manifest_for_row(rows[0])
        unsafe_manifest["updates"][0]["source_refs_preserved"] = False
        _next_rows, unsafe_report = (
            compaction.compact_dream_working_memory_payloads_from_dead_letter_manifest(
                rows,
                unsafe_manifest,
                compacted_at="2026-06-05T01:05:00Z",
            )
        )

        self.assertEqual(unsafe_report["metrics"]["payload_compacted_count"], 0)
        self.assertEqual(unsafe_report["metrics"]["unsafe_update_count"], 1)
        self.assertEqual(unsafe_report["skipped"][0]["skip_reason"], "unsafe_dead_letter_update")

if __name__ == "__main__":
    unittest.main()
