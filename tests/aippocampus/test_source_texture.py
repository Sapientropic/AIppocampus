from __future__ import annotations

import json
import unittest

from aippocampus_runtime.source.source_texture import (
    build_source_texture,
    build_source_texture_boundary_hints,
)


class SourceTextureTests(unittest.TestCase):
    def test_texture_rows_preserve_distinct_process_shape_without_payload_leakage(self) -> None:
        source_ref = {
            "source_id": "src_test",
            "source_ref": "codex:session:test#L12",
            "message_id": "msg_user_1",
            "turn_id": "turn_1",
            "turn_index": 1,
            "line": 12,
        }
        messages = [
            {
                "source_id": "src_test",
                "source_ref": "codex:session:test#L12",
                "source_line": 12,
                "message_id": "msg_user_1",
                "turn_id": "turn_1",
                "turn_index": 1,
                "role": "user",
                "content_sha256": "a" * 64,
                "timestamp": "2026-06-06T01:00:00Z",
                "text": "不是这个意思，我有点卡住，不确定后面怎么验证，先不要走 OAuth 路线。",
            }
        ]
        events = [
            {
                "event_id": "evt_fail_1",
                "source_id": "src_test",
                "source_ref": "codex:session:test#L20",
                "source_line": 20,
                "turn_index": 1,
                "hard_event_kind": "tool_call_failed",
                "status": "failed",
                "command_class": "test",
                "command_family": "python_unittest",
                "target_class": "focused_test_path",
                "test_target_class": "focused_test_path",
                "failure_family": "python_exception",
                "critical_operation_family": "test_check_command_result",
                "exit_code": 1,
                "path_fingerprints": ["sha256:0123456789abcdef"],
                "observation_sha256": "b" * 64,
            }
        ]
        route_notes = [
            {
                "route_id": "route_1",
                "route_id_hash": "route_hash_1",
                "note_type": "rejected_route",
                "source_refs": [source_ref],
                "note_source_ref": source_ref,
                "joined_evidence_refs": [
                    {
                        "evidence_kind": "behavior_event",
                        "event_id": "evt_fail_1",
                        "event_kind": "tool_call_failed",
                        "failure_family": "python_exception",
                        "source_ref": {
                            "source_id": "src_test",
                            "source_ref": "codex:session:test#L20",
                            "turn_index": 1,
                            "line": 20,
                        },
                    }
                ],
                "reason_codes": ["route_note", "rejected_route", "joined_to_adjacent_evidence"],
            }
        ]

        rows = build_source_texture(messages, events=events, route_notes=route_notes)

        signal_kinds = {row["signal_kind"] for row in rows}
        self.assertIn("self_correction_signal", signal_kinds)
        self.assertIn("uncertainty_or_frontier_signal", signal_kinds)
        self.assertIn("affect_marker", signal_kinds)
        self.assertIn("abandoned_direction", signal_kinds)
        self.assertIn("process_route_note", signal_kinds)
        self.assertIn("tool_failure_texture", signal_kinds)
        self.assertGreaterEqual(len(signal_kinds), 3)

        for row in rows:
            self.assertEqual(row["truth_boundary"], "texture_signal_not_source_fact")
            self.assertEqual(row["output_authority"], "interpretation_input_only")
            self.assertTrue(row["source_reopen_required_before_claim"])
            self.assertTrue(row.get("source_refs") or row.get("event_refs"), row)
            self.assertNotIn("text", row)
            self.assertNotIn("raw_commentary", row)
            self.assertNotEqual(row["signal_detail"], "generic")

        details = {row["signal_detail"] for row in rows}
        self.assertIn("visible_user_reformulation", details)
        self.assertIn("visible_stuckness", details)
        self.assertIn("route_note_rejected_route", details)
        self.assertIn("verification_failure", details)

        serialized = json.dumps(rows, ensure_ascii=False)
        for raw in (
            "不是这个意思",
            "OAuth 路线",
            "python tests",
            "Traceback",
            "C:\\Users",
            "API_KEY",
        ):
            self.assertNotIn(raw, serialized)

    def test_boundary_hints_are_derived_read_model_segments(self) -> None:
        canonical_segment = {
            "segment_id": "seg-stable-1",
            "source_refs": [{"message_id": "msg-long", "line": 12}],
            "start_line": 12,
            "end_line": 40,
        }
        texture_rows = [
            {
                "texture_id": "tex-correction",
                "signal_kind": "self_correction_signal",
                "signal_detail": "visible_user_correction",
                "truth_boundary": "texture_signal_not_source_fact",
                "source_refs": [{"message_id": "msg-long", "line": 18}],
            },
            {
                "texture_id": "tex-failure",
                "signal_kind": "tool_failure_texture",
                "signal_detail": "verification_failure",
                "truth_boundary": "texture_signal_not_source_fact",
                "source_refs": [{"message_id": "msg-long", "line": 28}],
            },
        ]

        before = json.dumps(canonical_segment, sort_keys=True)
        hints = build_source_texture_boundary_hints([canonical_segment], texture_rows)

        self.assertEqual(json.dumps(canonical_segment, sort_keys=True), before)
        self.assertEqual(
            [hint["canonical_segment_id"] for hint in hints],
            ["seg-stable-1", "seg-stable-1"],
        )
        self.assertTrue(all(hint["derived_segment_id"].startswith("texture_hint:") for hint in hints))
        self.assertTrue(all(hint["read_model_only"] for hint in hints))
        self.assertTrue(all(hint["source_reopen_required_before_claim"] for hint in hints))
        self.assertEqual(hints[0]["boundary_reason"], "visible_user_correction")

    def test_boundary_hints_only_project_trusted_boundary_rows(self) -> None:
        canonical_segment = {
            "segment_id": "seg-stable-1",
            "source_refs": [{"message_id": "msg-long", "line": 12}],
            "start_line": 12,
            "end_line": 40,
        }
        texture_rows = [
            {
                "texture_id": "tex-good",
                "signal_kind": "self_correction_signal",
                "signal_detail": "visible_user_correction",
                "truth_boundary": "texture_signal_not_source_fact",
                "source_refs": [{"message_id": "msg-long", "line": 18}],
            },
            {
                "texture_id": "tex-wrong-boundary",
                "signal_kind": "self_correction_signal",
                "signal_detail": "visible_user_correction",
                "truth_boundary": "raw_private_note",
                "source_refs": [{"message_id": "msg-long", "line": 18}],
            },
            {
                "texture_id": "tex-unsupported",
                "signal_kind": "affect_marker",
                "signal_detail": "affect_only",
                "truth_boundary": "texture_signal_not_source_fact",
                "source_refs": [{"message_id": "msg-long", "line": 18}],
            },
            {
                "texture_id": "tex-missing-refs",
                "signal_kind": "tool_failure_texture",
                "signal_detail": "verification_failure",
                "truth_boundary": "texture_signal_not_source_fact",
                "source_refs": [],
            },
        ]

        hints = build_source_texture_boundary_hints([canonical_segment], texture_rows)

        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["hint_id"].split("_", 1)[0], "sthint")
        self.assertEqual(hints[0]["boundary_reason"], "visible_user_correction")
        self.assertEqual(hints[0]["truth_boundary"], "texture_hint_read_model_not_source_fact")

if __name__ == "__main__":
    unittest.main()
