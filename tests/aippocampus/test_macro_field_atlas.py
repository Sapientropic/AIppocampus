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
        hard_edges = [edge for edge in report["edges"] if edge["edge_kind"] == "hard_overlap_edge"]
        self.assertEqual(len(hard_edges), 6)
        self.assertIn("basis", hard_edges[0])
        self.assertIn(hard_edges[0]["status"], {"active", "needs_overlap_recheck", "needs_source_reopen"})

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
