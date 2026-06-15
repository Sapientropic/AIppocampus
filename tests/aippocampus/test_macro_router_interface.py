from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import state as macro_state  # noqa: E402
from aippocampus_runtime.navigation import macro_field_atlas  # noqa: E402
from aippocampus_runtime.navigation import macro_router_interface as interface  # noqa: E402
from aippocampus_runtime.recall import macro_live_recall  # noqa: E402


class MacroRouterInterfaceTests(unittest.TestCase):
    def test_macro_state_projects_navigation_only_router_context(self) -> None:
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="蹇",
            changing_lines=(3,),
            source_refs=({"source_id": "macro-router-source"},),
            updated_at="2026-06-11T10:00:00Z",
            active_layer="人",
            momentum={"basis": {"support_delta": 0.2}},
        )

        context = interface.build_macro_router_context(entry)
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True)

        self.assertEqual(context["kind"], "macro_router_context")
        self.assertEqual(context["scope"], "project:AIppocampus")
        self.assertEqual(context["authority_level"], "navigation_only")
        self.assertEqual(context["claim_permission"], "no_claim_before_reopen")
        self.assertFalse(context["fact_claim_allowed"])
        self.assertEqual(context["active_layer"], "human")
        self.assertEqual(context["relation_position"]["situation_role"], "shi")
        self.assertEqual(context["relation_position"]["current_agent_default_role"], "ying")
        self.assertEqual(context["hexagram_state"]["perturbation_band"], "local")
        self.assertEqual(context["momentum"]["direction"], "rising")
        self.assertEqual(context["router_effects"]["preferred_route_layers"], ["human"])
        self.assertEqual(context["router_effects"]["fanout_bias"], "narrow")
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("macro-router-source", encoded)

    def test_router_observation_needs_source_refs_and_never_writes_macro_state(self) -> None:
        observation = interface.build_router_macro_observation(
            scope="project:AIppocampus",
            router_packets=[
                {
                    "macro_layer": "heaven",
                    "emitted": True,
                    "source_handles": [{"source_id": "route-source"}],
                    "router_diagnostics": {
                        "reason_codes": [
                            "stale_or_conflicted_source_reopen",
                            "repeated_route_failure",
                        ],
                    },
                }
            ],
            source_event_refs=("issue:#1243",),
        )
        no_source = interface.build_router_macro_observation(
            scope="project:AIppocampus",
            router_packets=[{"macro_layer": "earth", "emitted": True}],
        )

        self.assertEqual(observation["kind"], "router_macro_observation")
        self.assertEqual(observation["observed_layer_distribution"]["heaven"], 1.0)
        self.assertEqual(observation["signals"]["stale_conflict_count"], 1)
        self.assertEqual(observation["signals"]["repeated_route_failure_count"], 1)
        self.assertTrue(observation["candidate_macro_update"]["eligible_for_macro_update"])
        self.assertEqual(observation["macro_state_mutation_count"], 0)
        self.assertEqual(observation["write_mode"], "observation_only_no_hot_path_write")
        self.assertFalse(no_source["candidate_macro_update"]["eligible_for_macro_update"])
        self.assertEqual(no_source["macro_state_mutation_count"], 0)

    def test_macro_field_projection_adds_compact_legacy_attention_guidance(self) -> None:
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="蹇",
            changing_lines=(2,),
            source_refs=({"source_id": "macro-field-router-source"},),
            updated_at="2026-06-15T10:00:00Z",
            active_layer="人",
        )
        atlas = macro_field_atlas.materialize_macro_field_atlas(
            [
                {
                    "section_id": "section:release",
                    "title": "release closeout",
                    "task_family": "closeout",
                    "freshness": "current",
                    "source_refs": [{"source_id": "source:release"}],
                },
                {
                    "section_id": "section:verification",
                    "title": "verification gate",
                    "task_family": "verification",
                    "freshness": "current",
                    "source_refs": [{"source_id": "source:verification"}],
                },
            ],
            query="release verification",
            top_n=2,
        )

        context = interface.build_macro_router_context(
            entry,
            macro_field_projection=atlas["foreground_projection"],
        )
        guidance = context["router_effects"]["foreground_attention_guidance"]
        encoded = json.dumps(context, ensure_ascii=False, sort_keys=True)

        self.assertEqual(guidance["kind"], "macro_field_legacy_attention_guidance")
        self.assertEqual(guidance["lane_count"], 2)
        self.assertEqual(guidance["lanes"][0]["section_id"], "section:release")
        self.assertTrue(guidance["lanes"][0]["source_reopen_required"])
        self.assertIn("macro_field_projection_consumed", guidance["reason_codes"])
        self.assertIn("macro_field_projection_is_source_truth", context["cannot_claim"])
        self.assertTrue(
            context["source_boundary"]["macro_field_projection_source_reopen_required"]
        )
        self.assertNotIn('"selected_sections":', encoded)
        self.assertNotIn('"edges":', encoded)
        self.assertNotIn("source:release", encoded)
        self.assertNotIn("macro-field-router-source", encoded)

    def test_macro_field_projection_absent_keeps_legacy_context_unchanged(self) -> None:
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="蹇",
            changing_lines=(3,),
            updated_at="2026-06-15T10:00:00Z",
            active_layer="人",
        )

        legacy = interface.build_macro_router_context(entry)
        explicit_none = interface.build_macro_router_context(entry, macro_field_projection=None)
        invalid = interface.build_macro_router_context(
            entry,
            macro_field_projection={"kind": "macro_field_atlas_materialization"},
        )

        self.assertEqual(legacy, explicit_none)
        self.assertEqual(legacy, invalid)
        self.assertNotIn("foreground_attention_guidance", legacy["router_effects"])

    def test_macro_live_recall_context_transmits_macro_field_projection(self) -> None:
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            updated_at="2026-06-15T10:00:00Z",
            active_layer="人",
        )
        projection = {
            "status": "current",
            "state": entry,
            "foreground_projection": {
                "kind": "macro_field_foreground_projection",
                "schema_version": 1,
                "posture": "single",
                "primary_lane": {
                    "lane_id": "lane:primary",
                    "role": "primary",
                    "section_id": "section:runtime",
                    "title": "runtime lane",
                    "posture_id": "steady_carry",
                    "attention_bandwidth": "narrow",
                    "agent_instruction": "source_reopen_required",
                },
                "secondary_lanes": [],
                "lane_count": 1,
                "warnings": [],
            },
        }

        context = macro_live_recall.context_from_projection(projection)

        self.assertIsNotNone(context)
        assert context is not None
        guidance = context["router_effects"]["foreground_attention_guidance"]
        self.assertEqual(guidance["lanes"][0]["lane_id"], "lane:primary")
        self.assertIn("macro_field_projection_consumed", guidance["reason_codes"])

    def test_fixture_report_covers_hard_mask_and_active_layer_boundaries(self) -> None:
        report = interface.build_macro_router_interface_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["human_fanout_first_route"], "human_issue")
        self.assertEqual(report["earth_fanout_first_route"], "earth_tests")
        self.assertFalse(report["masked_packet"]["emitted"])
        self.assertIn("privacy_domain", report["masked_packet"]["masks_applied"])
        self.assertEqual(report["metrics"]["macro_context_claim_ready_count"], 0)
        self.assertEqual(report["metrics"]["masked_macro_bias_emission_count"], 0)
        self.assertEqual(report["metrics"]["hot_path_macro_state_write_count"], 0)
        self.assertIn("macro_context_as_evidence", report["cannot_claim"])
        self.assertNotIn("PRIVATE", encoded)


if __name__ == "__main__":
    unittest.main()
