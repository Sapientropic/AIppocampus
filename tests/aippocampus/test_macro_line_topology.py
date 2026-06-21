from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from aippocampus_runtime.macro import line_topology


def _relation(report: dict[str, object], pair_id: str) -> dict[str, object]:
    relations = report["ying_relations"]
    assert isinstance(relations, list)
    for relation in relations:
        assert isinstance(relation, dict)
        if relation["pair_id"] == pair_id:
            return relation
    raise AssertionError(f"missing relation {pair_id!r}")

class MacroLineTopologyTests(unittest.TestCase):
    def test_axis_mapping_names_one_explicit_six_line_fixture_map(self) -> None:
        axes = line_topology.axis_mapping()

        self.assertEqual([axis["line"] for axis in axes], [1, 2, 3, 4, 5, 6])
        self.assertEqual([axis["layer"] for axis in axes], ["earth", "earth", "human", "human", "heaven", "heaven"])
        self.assertEqual(axes[0]["axis_id"], "earth_substrate_evidence")
        self.assertEqual(axes[3]["axis_id"], "human_workflow_coordination")
        self.assertIn("why_this_line", axes[5])

    def test_ying_diagnostics_point_to_specific_broken_couplings(self) -> None:
        earth_human = line_topology.build_line_topology_diagnostics((0, 1, 1, 1, 0, 0))
        earth_heaven = line_topology.build_line_topology_diagnostics((1, 0, 1, 0, 1, 0))
        human_heaven = line_topology.build_line_topology_diagnostics((1, 1, 0, 0, 0, 1))

        self.assertEqual(_relation(earth_human, "earth_human")["status"], "missing_lower_support")
        self.assertIn("broken_coupling_earth_human", earth_human["reason_codes"])
        self.assertEqual(_relation(earth_heaven, "earth_heaven")["status"], "missing_lower_support")
        self.assertIn("broken_coupling_earth_heaven", earth_heaven["reason_codes"])
        self.assertEqual(_relation(human_heaven, "human_heaven")["status"], "missing_lower_support")
        self.assertIn("broken_coupling_human_heaven", human_heaven["reason_codes"])

    def test_adjacent_relations_use_terms_without_claim_authority(self) -> None:
        report = line_topology.build_line_topology_diagnostics((0, 1, 1, 0, 0, 1))
        adjacent = report["adjacent_relations"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertIsInstance(adjacent, list)
        self.assertIn("乘", encoded)
        self.assertIn("比", encoded)
        self.assertEqual(report["authority_level"], "navigation_only")
        self.assertEqual(report["claim_permission"], "no_claim_before_reopen")
        self.assertFalse(report["fact_claim_allowed"])
        self.assertFalse(report["ranking_weight_changes"])
        self.assertIn("does_topology_reduce_wrong_layer_recall", report["evaluation_questions"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("PRIVATE", encoded)

    def test_path_resonance_validation_is_behavior_oriented_not_symbolic_authority(self) -> None:
        doc = (REPO_ROOT / "docs" / "research" / "journey-tracking.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("P6a 验证重构", doc)
        self.assertIn("agent-usefulness", doc)
        self.assertIn("wrong-layer recall avoided", doc)
        self.assertIn("specific cross-layer coupling flagged", doc)
        self.assertIn("fanout/deepen rationale clarified", doc)
        self.assertIn("symbolic_match_without_route_usefulness", doc)
        self.assertIn("interesting_topology_navigation_only", doc)
        self.assertIn("#1219 可以作为 diagnostic-only V0 先 ship", doc)
        self.assertIn("factual support", doc)
        self.assertIn("默认排名权重", doc)

if __name__ == "__main__":
    unittest.main()
