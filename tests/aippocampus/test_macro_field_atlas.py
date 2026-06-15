from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import timing_affordance  # noqa: E402
from aippocampus_runtime.navigation import macro_field_atlas  # noqa: E402


def _section(index: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "section_id": f"section:{index}",
        "title": f"fixture section {index}",
        "scope": "project:ai",
        "topic_epoch": "epoch:1",
        "freshness": "current",
        "source_refs": [{"source_id": f"source:{index}"}],
        "task_family": "seed",
        "status": "active",
        "source_coverage_time": {
            "start": "2026-06-15T00:00:00Z",
            "end": "2026-06-15T01:00:00Z",
        },
    }
    row.update(overrides)
    return row


class MacroFieldAtlasTests(unittest.TestCase):
    def test_materializer_checks_only_selected_top_n_pairs(self) -> None:
        sections = [
            _section(index, title=f"atlas overlap target {index}" if index < 4 else f"background {index}")
            for index in range(52)
        ]

        report = macro_field_atlas.materialize_macro_field_atlas(
            sections,
            query="atlas overlap target",
            top_n=4,
        )

        self.assertEqual(report["input_section_count"], 52)
        self.assertEqual(report["selected_section_count"], 4)
        self.assertEqual(report["pairwise_hard_check_count"], 6)
        self.assertLess(report["pairwise_hard_check_count"], report["total_possible_pair_count"])
        self.assertFalse(report["all_pairs_recomputed"])
        self.assertTrue(report["source_shape_descriptor"]["compatibility_diagnostics_present"])
        hard_edges = [edge for edge in report["edges"] if edge["edge_kind"] == "hard_overlap_edge"]
        self.assertEqual(len(hard_edges), 6)
        self.assertIn("basis", hard_edges[0])
        self.assertIn(hard_edges[0]["status"], {"active", "needs_overlap_recheck", "needs_source_reopen"})

    def test_materializer_emits_local_global_source_shape_for_selected_sections(self) -> None:
        report = macro_field_atlas.materialize_macro_field_atlas(
            [
                _section(1, title="source shape selected", source_refs=[{"source_id": "shared"}]),
                _section(2, title="source shape selected", source_refs=[{"source_id": "shared"}]),
                _section(3, title="background"),
            ],
            query="source shape selected",
            top_n=2,
        )

        descriptor = report["source_shape_descriptor"]
        self.assertEqual(descriptor["producer"], "macro_field_atlas")
        self.assertEqual(descriptor["descriptor_state"], "complete")
        self.assertTrue(descriptor["compatibility_diagnostics_present"])
        self.assertTrue(descriptor["projection"]["projection_allowed"])
        self.assertEqual(descriptor["authority_level"], "direction_only")
        self.assertEqual(descriptor["claim_permission"], "none")
        self.assertEqual(
            descriptor["temporal_semantics"]["source_coverage_time"]["start"],
            "2026-06-15T00:00:00Z",
        )

    def test_materializer_source_shape_degrades_on_obstruction_and_blocked_boundary(self) -> None:
        obstructed = macro_field_atlas.materialize_macro_field_atlas(
            [
                _section(1, title="split runtime", scope="project:a", source_refs=[{"source_id": "a"}]),
                _section(2, title="split runtime", scope="project:b", source_refs=[{"source_id": "b"}]),
            ],
            query="split runtime",
            top_n=2,
        )
        blocked = macro_field_atlas.materialize_macro_field_atlas(
            [
                _section(1, title="private route", privacy_state="private", source_refs=[{"source_id": "private"}]),
                _section(2, title="private route", source_refs=[{"source_id": "public"}]),
            ],
            query="private route",
            top_n=2,
        )

        obstruction_descriptor = obstructed["source_shape_descriptor"]
        self.assertEqual(obstruction_descriptor["descriptor_state"], "incomplete")
        self.assertFalse(obstruction_descriptor["projection"]["projection_allowed"])
        self.assertEqual(obstruction_descriptor["signals"]["compatibility"]["status"], "obstruction")
        blocked_descriptor = blocked["source_shape_descriptor"]
        self.assertEqual(blocked_descriptor["descriptor_state"], "diagnostic_only")
        self.assertEqual(blocked_descriptor["dominant_guard"]["guard"], "privacy_boundary")
        self.assertEqual(blocked_descriptor["degrade_to"], "ignore_or_blocked")
        self.assertFalse(blocked_descriptor["projection"]["projection_allowed"])
        encoded = json.dumps(blocked_descriptor, ensure_ascii=False)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("raw_private_source_text", encoded)

    def test_declared_and_posture_edges_do_not_satisfy_glue(self) -> None:
        sections = [
            _section(1, title="closeout release", task_family="closeout"),
            _section(2, title="verification test", task_family="verification"),
        ]

        report = macro_field_atlas.materialize_macro_field_atlas(
            sections,
            query="closeout verification",
            top_n=2,
            declared_edges=[
                {
                    "source_event_id": "event:1",
                    "from_section_id": "section:1",
                    "to_section_id": "section:2",
                    "relation": "precondition",
                    "source_refs": [{"source_id": "source:declared"}],
                    "reasons": ["release requires verification"],
                }
            ],
        )
        soft = [
            edge
            for edge in report["edges"]
            if edge["edge_kind"] in {"declared_edge", "posture_dependency_edge"}
        ]

        self.assertTrue(soft)
        self.assertTrue(all(edge["may_satisfy_glue"] is False for edge in soft))
        self.assertEqual(report["foreground_projection"]["lane_count"], 2)
        self.assertTrue(report["foreground_projection"]["source_reopen_required"])

    def test_policy_lift_and_runtime_warnings_shape_compact_lanes(self) -> None:
        timing = timing_affordance.timing_affordance_feedback_gate(
            [{"outcome": "source_miss"}, {"outcome": "read_timeout"}]
        )
        report = macro_field_atlas.materialize_macro_field_atlas(
            [
                _section(1, title="closeout release", task_family="closeout"),
                _section(2, title="seed followup", task_family="seed"),
                _section(3, title="archivist boundary", task_family="archive"),
            ],
            query="closeout",
            top_n=3,
            posture_policies=[
                {
                    "accepted": True,
                    "from_posture_id": "seed_probe",
                    "to_posture_id": "archivist_boundary",
                    "relation": "seed_needs_source_boundary",
                    "lift": 0.2,
                }
            ],
            timing_affordance=timing,
            invariant_diagnostics=[{"runtime_recheck_reason": "source_reanchoring_required"}],
        )

        projection = report["foreground_projection"]
        encoded = json.dumps(projection, ensure_ascii=False)
        self.assertLessEqual(len(encoded.encode("utf-8")), projection["byte_budget"])
        self.assertIn(projection["posture"], {"mixed", "obstructed", "noisy"})
        self.assertEqual(projection["primary_lane"]["attention_bandwidth"], "reopen_first")
        self.assertIn("timing_affordance_falsified", projection["warnings"])
        self.assertIn("source_reanchoring_required", projection["warnings"])


if __name__ == "__main__":
    unittest.main()
