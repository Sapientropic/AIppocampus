from __future__ import annotations

import json
import unittest

from aippocampus_runtime.runtime_recheck_events import build_runtime_recheck_event
from aippocampus_runtime.source_shape import (
    build_source_shape_descriptor,
    explain_source_shape_descriptor,
    project_source_shape_for_foreground,
    source_shape_active_recall_priorities,
)


def source_ref(label: str) -> dict[str, object]:
    return {
        "thread_key": f"thread-{label}",
        "message_id": f"msg-{label}",
        "turn_id": f"turn-{label}",
        "source_line": 12,
    }

def complete_temporal() -> dict[str, object]:
    return {
        "source_coverage_time": {"start": "2026-06-13T00:00:00Z", "end": "2026-06-13T01:00:00Z"},
        "materialized_at": "2026-06-13T01:05:00Z",
        "built_at": "2026-06-13T01:06:00Z",
        "valid_after": "2026-06-13T01:06:00Z",
        "review_after": "2026-06-20T00:00:00Z",
        "source_epoch": "source-v1",
        "topic_epoch": "topic-v1",
    }

class SourceShapeRuntimeTests(unittest.TestCase):
    def test_descriptor_owner_returns_complete_incomplete_or_diagnostic_only(self) -> None:
        complete = build_source_shape_descriptor(
            producer="parallel_derivation_fixture",
            source_refs=[source_ref("complete")],
            source_snapshot={
                "snapshot_id": "snap-complete",
                "source_ids": ["source-a"],
                "source_epoch": "source-v1",
            },
            derivation_dag={"nodes": ["source", "macro"], "edges": [["source", "macro"]]},
            temporal=complete_temporal(),
            guard_inputs={"projection_allowed": True, "parallel_compatibility": "complete"},
            created_at="2026-06-13T01:06:00Z",
        )
        missing_time = build_source_shape_descriptor(
            producer="parallel_derivation_fixture",
            source_refs=[source_ref("missing-time")],
            derivation_dag={"nodes": ["source"], "edges": []},
            temporal={"materialized_at": "2026-06-13T01:05:00Z"},
            guard_inputs={"parallel_compatibility": "complete"},
            created_at="2026-06-13T01:06:00Z",
        )
        blocked = build_source_shape_descriptor(
            producer="parallel_derivation_fixture",
            source_refs=[],
            derivation_dag={"nodes": ["source"], "edges": []},
            temporal=complete_temporal(),
            guard_inputs={"privacy_state": "private", "projection_allowed": True},
            created_at="2026-06-13T01:06:00Z",
        )

        self.assertEqual(complete["descriptor_state"], "complete")
        self.assertTrue(complete["projection"]["projection_allowed"])
        self.assertEqual(missing_time["descriptor_state"], "incomplete")
        self.assertFalse(missing_time["projection"]["projection_allowed"])
        self.assertEqual(blocked["descriptor_state"], "diagnostic_only")
        self.assertEqual(blocked["dominant_guard"]["guard"], "privacy_boundary")
        self.assertFalse(blocked["projection"]["projection_allowed"])

    def test_temporal_semantics_use_section_window_and_epoch_recheck_without_age_claim(self) -> None:
        mapped = build_source_shape_descriptor(
            producer="section_window_fixture",
            source_refs=[source_ref("section")],
            derivation_dag={"nodes": ["section"], "edges": []},
            temporal={
                "section_time_window": {
                    "local_start": "2026-06-13T00:00:00+08:00",
                    "local_end": "2026-06-13T01:00:00+08:00",
                },
                "materialized_at": "2026-06-13T01:05:00Z",
                "source_epoch": "source-v1",
            },
            guard_inputs={"parallel_compatibility": "complete"},
            created_at="2026-06-13T01:06:00Z",
        )
        suspect = build_source_shape_descriptor(
            producer="familiarity_card_fixture",
            source_refs=[source_ref("epoch")],
            derivation_dag={"nodes": ["card", "source"], "edges": [["source", "card"]]},
            temporal={
                **complete_temporal(),
                "invalidation_epoch": "source-v2",
            },
            guard_inputs={"parallel_compatibility": "complete"},
            created_at="2026-06-13T01:06:00Z",
        )

        self.assertEqual(
            mapped["temporal_semantics"]["source_coverage_time"]["mapped_from"],
            "section_time_window",
        )
        self.assertEqual(mapped["descriptor_state"], "complete")
        self.assertEqual(suspect["descriptor_state"], "incomplete")
        self.assertEqual(suspect["dominant_guard"]["reason_code"], "source_epoch_mismatch")
        foreground = project_source_shape_for_foreground(suspect)
        self.assertIn("check_currentness", foreground["risk_flags"])
        self.assertIn("source_epoch_mismatch", foreground["triage_rank_reason_codes"])
        self.assertNotIn("calendar_age", json.dumps(suspect, sort_keys=True))

    def test_guard_order_retains_explain_diagnostics_without_later_authority_raise(self) -> None:
        descriptor = build_source_shape_descriptor(
            producer="compatibility_fixture",
            source_refs=[source_ref("guard")],
            derivation_dag={"nodes": ["source", "macro"], "edges": [["source", "macro"]]},
            compatibility_diagnostics={
                "result": "obstruction",
                "reason_codes": ["local_global_obstruction"],
            },
            temporal={
                **complete_temporal(),
                "invalidation_reasons": ["semantic_invalidation"],
            },
            guard_inputs={
                "privacy_state": "private",
                "authority_level": "source_open",
                "claim_permission": "source_open",
                "parallel_compatibility": "missing",
                "projection_allowed": True,
            },
            created_at="2026-06-13T01:06:00Z",
        )

        foreground = project_source_shape_for_foreground(descriptor)
        explain = explain_source_shape_descriptor(descriptor)
        reasons = {row["reason_code"] for row in explain["guard_diagnostics"]}

        self.assertEqual(descriptor["dominant_guard"]["guard"], "privacy_boundary")
        self.assertEqual(foreground["route_posture"], "blocked")
        self.assertEqual(foreground["authority_level"], "direction_only")
        self.assertEqual(foreground["claim_permission"], "none")
        self.assertIn("semantic_invalidation", reasons)
        self.assertIn("claim_permission_downgraded", reasons)
        self.assertIn("local_global_obstruction", reasons)
        self.assertIn("parallel_derivation_incomplete", reasons)

    def test_foreground_projection_keeps_dream_avatar_macro_and_compatibility_compact(self) -> None:
        descriptor = build_source_shape_descriptor(
            producer="mixed_surface_fixture",
            source_refs=[source_ref("mixed")],
            derivation_dag={"nodes": ["dream", "avatar", "macro", "source"], "edges": []},
            compatibility_diagnostics={
                "result": "obstruction",
                "reason_codes": ["interlayer_obstruction"],
            },
            temporal=complete_temporal(),
            guard_inputs={"parallel_compatibility": "complete"},
            signals={
                "dream": {"status": "adjudicated_reopen_hint"},
                "avatar": {"posture": "shadowed"},
                "macro": {"reason_code": "macro_recheck"},
                "compatibility": {"status": "obstruction"},
            },
            created_at="2026-06-13T01:06:00Z",
        )
        foreground = project_source_shape_for_foreground(descriptor)
        encoded = json.dumps(foreground, ensure_ascii=False, sort_keys=True)

        self.assertEqual(foreground["route_posture"], "shadowed")
        self.assertEqual(foreground["action_grammar"], "direction_with_ref")
        self.assertIn("compatibility_obstruction", foreground["risk_flags"])
        self.assertTrue(foreground["source_reopen_required_before_claim"])
        self.assertNotIn("guard_diagnostics", foreground)
        self.assertNotIn("temporal_semantics", foreground)
        self.assertNotIn("adjudicated_reopen_hint", encoded)
        self.assertNotIn("macro_recheck", encoded)
        self.assertNotIn("avatar", encoded)
        self.assertNotIn("dream", encoded)

    def test_runtime_recheck_and_descriptor_feed_active_recall_priority_navigation_only(self) -> None:
        event = build_runtime_recheck_event(
            producer="dream_worker",
            reason_code="dream_macro_recheck",
            source_refs=[source_ref("dream")],
            scope={"kind": "dream", "pack_id": "pack-1"},
            source_shape_id="dream:pack-1",
            target_surfaces=("active_recall_priority", "dream_seed"),
            created_at="2026-06-13T01:06:00Z",
        )
        descriptor = build_source_shape_descriptor(
            producer="decision_shadow_fixture",
            source_refs=[source_ref("boundary")],
            derivation_dag={"nodes": ["boundary"], "edges": []},
            temporal=complete_temporal(),
            guard_inputs={"parallel_compatibility": "complete", "freshness": "stale"},
            created_at="2026-06-13T01:06:00Z",
        )

        priorities = source_shape_active_recall_priorities([event, descriptor])

        self.assertEqual(len(priorities), 2)
        for priority in priorities:
            self.assertEqual(priority["authority_level"], "direction_only")
            self.assertEqual(priority["claim_permission"], "none")
            self.assertTrue(priority["source_reopen_required_before_claim"])
            self.assertIn("source_reopen_required", priority["risk_flags"])
        self.assertIn("runtime_recheck_event", priorities[0]["triage_rank_reason_codes"])
        self.assertIn("check_currentness", priorities[1]["risk_flags"])

if __name__ == "__main__":
    unittest.main()
