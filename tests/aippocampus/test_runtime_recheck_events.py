from __future__ import annotations

import json
import unittest

from aippocampus_runtime.dream import input_pack
from aippocampus_runtime.recall.continuity_domains import (
    materialize_continuity_domains,
)
from aippocampus_runtime.runtime_recheck_events import (
    build_runtime_recheck_event,
    macro_review_input_from_runtime_recheck_event,
    runtime_recheck_event_from_dream_finding,
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

    def test_adjudicated_dream_finding_emits_macro_recheck_without_state_mutation(self) -> None:
        finding = {
            "kind": "aippocampus_dream_finding",
            "dream_finding_id": "dream-obstruction-1",
            "finding_kind": "dream_synthesized",
            "dream_function": "compensatory",
            "candidate_kind": "blind_spot",
            "review_state": "agent_adjudicated",
            "adjudication_result": {"status": "accepted"},
            "title": "Dream obstruction: missing lower support",
            "summary": "A source-backed Dream hypothesis asks Macro to recheck an obstruction.",
            "source_refs": [source_ref("dream-a"), source_ref("dream-b")],
            "trust_horizon": "2026-06-30T00:00:00Z",
            "invalidation_triggers": ["source_correction", "stage_recheck"],
        }

        event = runtime_recheck_event_from_dream_finding(
            finding,
            source_shape_id="source_shape:dream-obstruction-1",
            created_at="2026-06-14T00:00:00Z",
        )
        review_input = macro_review_input_from_runtime_recheck_event(event)

        self.assertEqual(event["kind"], "runtime_recheck_event")
        self.assertEqual(event["reason_code"], "dream_obstruction_recheck")
        self.assertEqual(event["authority_level"], "direction_only")
        self.assertEqual(event["claim_permission"], "none")
        self.assertEqual(event["degrade_to"], "macro_review_input")
        self.assertIn("macro_recheck", event["target_surfaces"])
        self.assertIn("stage_tracker_review", event["target_surfaces"])
        self.assertFalse(event["consumer_policy"]["may_mutate_source_truth"])
        self.assertFalse(event["consumer_policy"]["may_raise_authority"])
        self.assertFalse(event["consumer_policy"]["may_emit_foreground_fact"])
        self.assertFalse(event["macro_recheck_policy"]["may_update_hexagram"])
        self.assertFalse(event["macro_recheck_policy"]["may_update_momentum"])
        self.assertFalse(event["macro_recheck_policy"]["may_update_stage_tracker"])

        self.assertIsNotNone(review_input)
        assert review_input is not None
        self.assertEqual(review_input["kind"], "macro_recheck_review_input")
        self.assertEqual(review_input["write_effect"], "none")
        self.assertFalse(review_input["fact_claim_allowed"])
        self.assertFalse(review_input["foreground_eligible"])
        self.assertIn("navigation_only_macro_review_input", review_input["diagnostics"])

        non_adjudicated = runtime_recheck_event_from_dream_finding(
            {
                **finding,
                "dream_finding_id": "dream-not-ready",
                "review_state": "needs_review",
                "adjudication_result": {"status": "parked"},
            }
        )
        self.assertEqual(non_adjudicated["kind"], "runtime_recheck_event_rejection")
        self.assertEqual(
            non_adjudicated["reason_code"],
            "dream_not_adjudicated_for_macro_recheck",
        )

    def test_dream_cut_point_and_compensatory_findings_route_to_specific_recheck_reasons(self) -> None:
        base = {
            "kind": "aippocampus_dream_finding",
            "finding_kind": "dream_synthesized",
            "review_state": "agent_adjudicated",
            "adjudication_result": {"status": "accepted"},
            "source_refs": [source_ref("dream-c"), source_ref("dream-d")],
        }
        cut_point = runtime_recheck_event_from_dream_finding(
            {
                **base,
                "dream_finding_id": "dream-cut-point",
                "dream_function": "prospective",
                "candidate_kind": "trajectory_hint",
                "recheck_on": ["line_topology_stage_review"],
                "summary": "A Dream cut_point asks stage movement to be reviewed.",
            }
        )
        compensatory = runtime_recheck_event_from_dream_finding(
            {
                **base,
                "dream_finding_id": "dream-compensatory",
                "dream_function": "compensatory",
                "candidate_kind": "approach_bias",
                "summary": "Accepted compensatory probe.",
            }
        )

        self.assertEqual(cut_point["reason_code"], "dream_cut_point_stage_review")
        self.assertEqual(compensatory["reason_code"], "dream_compensatory_probe_accepted")
        self.assertFalse(cut_point["macro_recheck_policy"]["may_update_three_powers"])
        self.assertFalse(compensatory["macro_recheck_policy"]["may_update_hexagram"])

if __name__ == "__main__":
    unittest.main()
