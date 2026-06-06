from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops.topology_anchor_policy import (  # noqa: E402
    fixture_topology_anchor_report,
    topology_anchor_report,
)


class TopologyAnchorPolicyTests(unittest.TestCase):
    def test_fixture_protects_bridges_without_promoting_truth(self) -> None:
        report = fixture_topology_anchor_report()
        nodes = {node["node_id"]: node for node in report["nodes"]}

        self.assertEqual(nodes["old-low-frequency-bridge"]["classification"], "must_keep")
        self.assertLess(nodes["old-low-frequency-bridge"]["decay_multiplier"], 1.0)
        self.assertEqual(nodes["popular-noisy-hub"]["classification"], "ordinary_decay")
        self.assertTrue(nodes["popular-noisy-hub"]["noisy_hub_suppressed"])
        self.assertEqual(
            nodes["superseded-bridge-context"]["classification"], "review_before_archive"
        )
        self.assertTrue(nodes["superseded-bridge-context"]["stale_bridge_reopen_required"])
        self.assertEqual(nodes["model-only-topology"]["classification"], "diagnostic_only")
        self.assertFalse(any(node["promoted_to_current_fact"] for node in report["nodes"]))

    def test_metrics_match_issue_contract_names(self) -> None:
        report = fixture_topology_anchor_report()

        self.assertEqual(report["metrics"]["topology_protected_anchor_count"], 2)
        self.assertEqual(report["metrics"]["bridge_reopen_helpful_count"], 1)
        self.assertEqual(report["metrics"]["noisy_hub_suppression_count"], 1)
        self.assertEqual(report["metrics"]["stale_bridge_reopen_required_count"], 1)

    def test_privacy_block_overrides_bridge_pressure(self) -> None:
        report = topology_anchor_report(
            [
                {
                    "node_id": "private-bridge",
                    "source_refs": [{"source_id": "clean:private"}],
                    "cluster_ids": ["a", "b"],
                    "bridge_score": 0.9,
                    "privacy_blocked": True,
                }
            ]
        )

        self.assertEqual(report["nodes"][0]["classification"], "blocked")
        self.assertFalse(report["nodes"][0]["protected_by_topology"])


if __name__ == "__main__":
    unittest.main()
