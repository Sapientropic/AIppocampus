from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.dream import input_pack  # noqa: E402
from aippocampus_runtime.recall.continuity_domains import (
    materialize_continuity_domains,  # noqa: E402
)
from aippocampus_runtime.runtime_recheck_events import (  # noqa: E402
    build_runtime_recheck_event,
    runtime_recheck_events_from_continuity_domains_snapshot,
)


def source_ref(label: str) -> dict[str, object]:
    return {
        "thread_key": f"thread-{label}",
        "message_id": f"msg-{label}",
        "turn_id": f"turn-{label}",
        "source_line": 10,
        "role": "user",
    }


class RuntimeRecheckEventTests(unittest.TestCase):
    def test_shared_event_shape_dedupes_without_raising_authority(self) -> None:
        ref = source_ref("shared")
        rows = [
            build_runtime_recheck_event(
                producer="dream_worker",
                reason_code="dream_macro_recheck",
                source_refs=[ref],
                scope={"kind": "dream", "pack_id": "pack-1"},
                source_shape_id="dream:pack-1",
                target_surfaces=("macro", "dream"),
                created_at="2026-06-14T00:00:00Z",
            ),
            build_runtime_recheck_event(
                producer="semantic_gate",
                reason_code="semantic_invalidation",
                source_refs=[ref],
                scope={"kind": "semantic_route", "route_id": "route-1"},
                source_shape_id="semantic:route-1",
                target_surfaces=("active_recall",),
                created_at="2026-06-14T00:00:00Z",
            ),
            build_runtime_recheck_event(
                producer="local_global_compatibility",
                reason_code="local_global_obstruction",
                source_refs=[ref],
                scope={"kind": "compatibility", "basis": "cross_derivation"},
                source_shape_id="compat:cross-derivation",
                target_surfaces=("macro_recheck", "subconscious_review"),
                created_at="2026-06-14T00:00:00Z",
            ),
        ]
        duplicate = build_runtime_recheck_event(
            producer="dream_worker",
            reason_code="dream_macro_recheck",
            source_refs=[ref],
            scope={"kind": "dream", "pack_id": "pack-1"},
            source_shape_id="dream:pack-1",
            target_surfaces=("macro", "dream"),
            created_at="2026-06-14T01:00:00Z",
        )

        field_sets = {tuple(sorted(row)) for row in rows}
        self.assertEqual(len(field_sets), 1)
        self.assertEqual(rows[0]["event_id"], duplicate["event_id"])
        for row in rows:
            self.assertEqual(row["authority_level"], "direction_only")
            self.assertEqual(row["claim_permission"], "none")
            self.assertEqual(row["degrade_to"], "navigation_diagnostic")
            self.assertFalse(row["consumer_policy"]["may_mutate_source_truth"])
            self.assertFalse(row["consumer_policy"]["may_raise_authority"])
            self.assertFalse(row["consumer_policy"]["may_emit_foreground_fact"])

    def test_continuity_domain_lifecycle_emits_navigation_only_recheck_events(self) -> None:
        snapshot = materialize_continuity_domains(
            [
                {
                    "event_kind": "domain_created",
                    "domain_id": "cd-route-conflict",
                    "title": "Route conflict",
                    "summary": "Domain summary is not source truth.",
                    "source_refs": [source_ref("support")],
                },
                {
                    "event_kind": "counter_source_added",
                    "domain_id": "cd-route-conflict",
                    "source_refs": [source_ref("counter")],
                },
                {
                    "event_kind": "correction_source_added",
                    "domain_id": "cd-route-conflict",
                    "source_refs": [source_ref("correction")],
                },
                {
                    "event_kind": "boundary_pinned",
                    "domain_id": "cd-route-conflict",
                    "effect": "require_source_reopen",
                    "source_refs": [source_ref("boundary")],
                },
                {
                    "event_kind": "domain_created",
                    "domain_id": "cd-old-route",
                    "source_refs": [source_ref("old")],
                },
                {
                    "event_kind": "domain_superseded",
                    "domain_id": "cd-old-route",
                    "source_refs": [source_ref("newer")],
                },
                {
                    "event_kind": "domain_created",
                    "domain_id": "cd-blocked-route",
                    "source_refs": [source_ref("blocked-support")],
                },
                {
                    "event_kind": "boundary_pinned",
                    "domain_id": "cd-blocked-route",
                    "effect": "block_hook",
                    "source_refs": [source_ref("blocked-boundary")],
                },
            ]
        )

        events = runtime_recheck_events_from_continuity_domains_snapshot(snapshot)
        reasons = {event["reason_code"] for event in events}
        encoded = json.dumps(events, ensure_ascii=False)

        self.assertIn("continuity_domain_conflict_recheck", reasons)
        self.assertIn("continuity_domain_boundary_constraint", reasons)
        self.assertIn("continuity_domain_currentness_recheck", reasons)
        self.assertIn("continuity_domain_route_unavailable", reasons)
        self.assertNotIn("Domain summary is not source truth.", encoded)
        for event in events:
            self.assertEqual(event["authority_level"], "direction_only")
            self.assertEqual(event["claim_permission"], "none")
            self.assertIn("active_recall_priority", event["target_surfaces"])
            self.assertTrue(event["consumer_policy"]["requires_source_reopen_before_claim"])

    def test_dream_consumes_runtime_recheck_only_as_seed_constraint(self) -> None:
        event = build_runtime_recheck_event(
            producer="continuity_domain_evidence_trail",
            reason_code="continuity_domain_boundary_constraint",
            source_refs=[source_ref("dream-boundary")],
            scope={"kind": "continuity_domain", "domain_id": "cd-boundary"},
            source_shape_id="continuity_domain:cd-boundary",
            target_surfaces=("dream_seed", "macro_recheck"),
            created_at="2026-06-14T00:00:00Z",
        )
        macro_only = build_runtime_recheck_event(
            producer="continuity_domain_lifecycle",
            reason_code="continuity_domain_route_unavailable",
            source_refs=[source_ref("macro-only")],
            scope={"kind": "continuity_domain", "domain_id": "cd-blocked"},
            source_shape_id="continuity_domain:cd-blocked",
            target_surfaces=("macro_recheck",),
            created_at="2026-06-14T00:00:00Z",
        )

        seed = input_pack.seed_from_row(event)

        self.assertIsNotNone(seed)
        assert seed is not None
        self.assertEqual(seed.seed_kind, "runtime_recheck")
        self.assertIn("continuity_domain_boundary_constraint", seed.frontiers)
        self.assertIn("runtime recheck event is direction-only navigation", seed.negative_contexts)
        self.assertIsNone(input_pack.seed_from_row(macro_only))


if __name__ == "__main__":
    unittest.main()
