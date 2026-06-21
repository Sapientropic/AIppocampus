from __future__ import annotations

import json
import unittest

from aippocampus_runtime.macro import three_powers
from aippocampus_runtime.navigation import macro_router_interface
from aippocampus_runtime.navigation import navigation_potential as nav
from aippocampus_runtime.navigation.parallel_derivation_bundle import (
    build_parallel_derivation_bundle,
    dependency_dag,
    preflattening_gate_for_route_affordance,
)


def ref(label: str) -> dict[str, object]:
    return {"source_id": f"src-{label}", "message_id": f"msg-{label}", "source_line": 10}

def snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "snap-1316",
        "source_ids": ["src-shared"],
        "source_epoch": "source-v1",
        "topic_epoch": "topic-v1",
        "source_coverage_time": {"start": "2026-06-13T00:00:00Z", "end": "2026-06-13T01:00:00Z"},
    }

def derivation(
    derivation_id: str,
    kind: str,
    refs: list[dict[str, object]],
    *,
    shape: dict[str, object] | None = None,
    prereqs: list[str] | None = None,
    family: str = "project",
) -> dict[str, object]:
    return {
        "derivation_id": derivation_id,
        "derivation_kind": kind,
        "derived_from_state_id": "state-1316",
        "prerequisite_derivation_ids": prereqs or [],
        "source_refs": refs,
        "source_family": family,
        "shape": shape or {},
    }

def route_candidates() -> list[dict[str, object]]:
    return [
        {
            "route_id": "route-earth",
            "title": "Earth route",
            "source_family": "artifact",
            "source_refs": [ref("shared")],
        },
        {
            "route_id": "route-heaven",
            "title": "Heaven route",
            "source_family": "roadmap",
            "source_refs": [ref("shared")],
        },
    ]

class ParallelDerivationBundleTests(unittest.TestCase):
    def test_source_basis_alignment_shared_partial_and_no_overlap(self) -> None:
        shared = build_parallel_derivation_bundle(
            [
                derivation("momentum", "momentum", [ref("shared")], shape={"direction": "steady"}),
                derivation("perturbation", "perturbation", [ref("shared")], shape={"band": "local"}),
            ],
            source_snapshot=snapshot(),
            created_at="2026-06-13T01:00:00Z",
        )
        partial = build_parallel_derivation_bundle(
            [
                derivation("momentum", "momentum", [ref("shared")], shape={"direction": "steady"}),
                derivation("topology", "line_topology", [ref("shared")], shape={"coupling": "ok"}),
                derivation("stage", "stage_tracker", [ref("stage")], shape={"movement": "stable"}),
            ],
            source_snapshot=snapshot(),
            created_at="2026-06-13T01:00:00Z",
        )
        no_overlap = build_parallel_derivation_bundle(
            [
                derivation("momentum", "momentum", [ref("a")], shape={"direction": "steady"}),
                derivation("perturbation", "perturbation", [ref("b")], shape={"band": "local"}),
            ],
            source_snapshot=snapshot(),
            created_at="2026-06-13T01:00:00Z",
        )

        self.assertEqual(shared["source_basis"]["alignment"], "shared")
        self.assertEqual(shared["compatibility"]["status"], "compatible")
        self.assertEqual(partial["source_basis"]["alignment"], "partial_overlap")
        self.assertEqual(partial["compatibility"]["status"], "tension")
        self.assertIn("partial_source_basis_overlap", partial["compatibility"]["reason_codes"])
        self.assertEqual(no_overlap["source_basis"]["alignment"], "no_overlap")
        self.assertEqual(no_overlap["compatibility"]["status"], "obstruction")
        self.assertFalse(no_overlap["compatibility"]["fact_claim_allowed"])

    def test_dependency_dag_valid_missing_cycle_and_reordered_input(self) -> None:
        valid = dependency_dag(
            [
                derivation("state", "macro_state", [ref("shared")]),
                derivation("momentum", "momentum", [ref("shared")], prereqs=["state"]),
                derivation("fanout", "three_powers", [ref("shared")], prereqs=["momentum"]),
            ]
        )
        missing = dependency_dag(
            [derivation("fanout", "three_powers", [ref("shared")], prereqs=["momentum"])]
        )
        cycle = dependency_dag(
            [
                derivation("momentum", "momentum", [ref("shared")], prereqs=["fanout"]),
                derivation("fanout", "three_powers", [ref("shared")], prereqs=["momentum"]),
            ]
        )
        reordered = dependency_dag(
            [
                derivation("fanout", "three_powers", [ref("shared")], prereqs=["momentum"]),
                derivation("momentum", "momentum", [ref("shared")]),
            ]
        )

        self.assertEqual(valid["topological_order"], ["state", "momentum", "fanout"])
        self.assertIn("dependency_dag_valid", valid["reason_codes"])
        self.assertIn("missing_prerequisite_derivation", missing["reason_codes"])
        self.assertTrue(cycle["cycle_detected"])
        self.assertIn("cyclic_derivation_dependency", cycle["reason_codes"])
        self.assertEqual(reordered["topological_order"], ["momentum", "fanout"])
        self.assertIn("input_order_repaired_by_dependency_dag", reordered["reason_codes"])

    def test_1316_cross_derivation_fixtures_emit_named_tension_or_obstruction(self) -> None:
        cases = {
            "latent_route_conflict": build_parallel_derivation_bundle(
                [
                    derivation("momentum", "momentum", [ref("shared")], shape={"direction": "rising"}),
                    derivation("shadow", "shadow_route", [ref("shared")], shape={"posture": "obstructed"}),
                ],
                source_snapshot=snapshot(),
                created_at="2026-06-13T01:00:00Z",
            ),
            "fanout_tension": build_parallel_derivation_bundle(
                [
                    derivation("perturbation", "perturbation", [ref("shared")], shape={"band": "large"}),
                    derivation("fanout", "three_powers", [ref("shared")], shape={"active_axis_width": "narrow"}),
                ],
                source_snapshot=snapshot(),
                created_at="2026-06-13T01:00:00Z",
            ),
            "interlayer_obstruction": build_parallel_derivation_bundle(
                [
                    derivation("heaven", "three_powers", [ref("shared")], shape={"heaven_direction": "clear"}),
                    derivation("earth", "earth_evidence", [ref("shared")], shape={"evidence": "missing"}),
                ],
                source_snapshot=snapshot(),
                created_at="2026-06-13T01:00:00Z",
            ),
            "same_structure_different_source_family": build_parallel_derivation_bundle(
                [
                    derivation(
                        "orbit-a",
                        "transform_orbit",
                        [ref("shared")],
                        shape={"orbit_id": "same"},
                        family="release_notes",
                    ),
                    derivation(
                        "orbit-b",
                        "transform_orbit",
                        [ref("shared")],
                        shape={"orbit_id": "same"},
                        family="roadmap",
                    ),
                ],
                source_snapshot=snapshot(),
                created_at="2026-06-13T01:00:00Z",
            ),
            "stage_movement_conflict": build_parallel_derivation_bundle(
                [
                    derivation("stage", "stage_tracker", [ref("shared")], shape={"movement": "reversal"}),
                    derivation("momentum", "momentum", [ref("shared")], shape={"direction": "rising"}),
                ],
                source_snapshot=snapshot(),
                created_at="2026-06-13T01:00:00Z",
            ),
        }

        for expected_reason, bundle in cases.items():
            with self.subTest(expected_reason=expected_reason):
                self.assertIn(expected_reason, bundle["compatibility"]["reason_codes"])
                self.assertIn(bundle["compatibility"]["status"], {"tension", "obstruction"})
                self.assertFalse(bundle["fact_claim_allowed"])
                encoded = json.dumps(bundle, ensure_ascii=False)
                self.assertNotIn(r"E:\private", encoded)

    def test_source_shape_descriptor_and_preflattening_gate_block_missing_compatibility(self) -> None:
        bundle = build_parallel_derivation_bundle(
            [
                derivation("momentum", "momentum", [ref("shared")], shape={"direction": "steady"}),
                derivation("fanout", "three_powers", [ref("shared")], shape={"active_axis_width": "narrow"}),
            ],
            source_snapshot=snapshot(),
            compute_compatibility=False,
            created_at="2026-06-13T01:00:00Z",
        )
        descriptor = bundle["source_shape_descriptor"]
        gate = preflattening_gate_for_route_affordance(bundle)

        self.assertEqual(bundle["compatibility"]["status"], "incomplete")
        self.assertEqual(descriptor["descriptor_state"], "incomplete")
        self.assertFalse(descriptor["projection"]["projection_allowed"])
        self.assertFalse(gate["flattening_allowed"])
        self.assertIn("missing_parallel_compatibility_diagnostics", gate["reason_codes"])
        self.assertEqual(gate["authority_level"], "navigation_only")
        self.assertEqual(gate["claim_permission"], "none")

    def test_three_powers_and_navigation_potential_consume_preflattening_gate(self) -> None:
        obstruction = build_parallel_derivation_bundle(
            [
                derivation("momentum", "momentum", [ref("shared")], shape={"direction": "rising"}),
                derivation("shadow", "shadow_route", [ref("shared")], shape={"posture": "obstructed"}),
            ],
            source_snapshot=snapshot(),
            created_at="2026-06-13T01:00:00Z",
        )
        tension = build_parallel_derivation_bundle(
            [
                derivation("perturbation", "perturbation", [ref("shared")], shape={"band": "large"}),
                derivation("fanout", "three_powers", [ref("shared")], shape={"active_axis_width": "narrow"}),
            ],
            source_snapshot=snapshot(),
            created_at="2026-06-13T01:00:00Z",
        )

        blocked_fanout = three_powers.apply_three_powers_fanout(
            "heaven route",
            route_candidates(),
            perturbation_packet={"fanout_hint": {"recommended_candidate_limit": 8}},
            parallel_derivation_bundle=obstruction,
            base_candidate_limit=2,
        )
        narrowed_fanout = three_powers.apply_three_powers_fanout(
            "heaven route",
            route_candidates(),
            perturbation_packet={"fanout_hint": {"recommended_candidate_limit": 8}},
            parallel_derivation_bundle=tension,
            base_candidate_limit=2,
        )
        projection = nav.build_navigation_potential_projection(
            cognitive_routes=[
                {
                    "route_id": "route-next",
                    "title": "Continue route",
                    "status": "open",
                    "frontier_proximity": "high",
                    "action_delta_required": "Open the next slice.",
                    "source_refs": [ref("shared")],
                    "source_thickness": "usable",
                }
            ],
            parallel_derivation_bundle=obstruction,
            now="2026-06-13T01:00:00Z",
        )
        context = macro_router_interface.build_macro_router_context(
            {
                "scope": {"kind": "project", "project": "AIppocampus"},
                "relation_position": {"active_layer": "heaven"},
                "perturbation": {"changed_line_count": 4},
                "parallel_derivation_bundle": obstruction,
            }
        )

        self.assertEqual(blocked_fanout["selected_route_ids"], [])
        self.assertEqual(blocked_fanout["fanout_policy"]["candidate_limit"], 0)
        self.assertIn("parallel_derivation_latent_route_conflict", blocked_fanout["diagnostics"])
        self.assertEqual(narrowed_fanout["fanout_policy"]["candidate_limit"], 1)
        potential = projection["potentials"][0]
        self.assertNotEqual(potential["affordance"], "offer_next_step")
        self.assertIn("parallel_derivation_recheck_required", potential["preconditions"])
        self.assertIn("parallel_derivation:latent_route_conflict", context["router_effects"]["recheck_triggers"])

if __name__ == "__main__":
    unittest.main()
