from __future__ import annotations

import unittest

from aippocampus_runtime.navigation import microcircuit_router as router
from aippocampus_runtime.navigation import navigation_potential


class MicrocircuitRouterTests(unittest.TestCase):
    def test_router_reports_candidate_space_diagnostics_and_prune_reasons(self) -> None:
        report = router.route_candidates(
            [
                {
                    "candidate_id": "gold",
                    "title": "preflight broad test",
                    "score": 0.7,
                    "cluster_id": "a",
                    "source_refs": [{"source_id": "src:gold"}],
                },
                {
                    "candidate_id": "same_cluster",
                    "title": "preflight",
                    "score": 0.6,
                    "cluster_id": "a",
                    "source_refs": [{"source_id": "src:gold"}],
                },
                {
                    "candidate_id": "wrong_source",
                    "title": "unrelated",
                    "score": 0.9,
                    "cluster_id": "b",
                    "source_refs": [{"source_id": "src:other"}],
                },
                {
                    "candidate_id": "low",
                    "title": "unmatched",
                    "score": -0.1,
                    "cluster_id": "c",
                    "source_refs": [{"source_id": "src:gold"}],
                },
            ],
            query_terms=["preflight", "test"],
            source_constraints={"source_ids": ["src:gold"]},
            gold_source_ids=["src:gold"],
            threshold=0.5,
            top_k=1,
            diversity_key="cluster_id",
        )

        diagnostics = report["diagnostics"]
        self.assertEqual(report["selected_candidates"][0]["candidate_id"], "gold")
        self.assertEqual(diagnostics["raw_pool_size"], 4)
        self.assertEqual(diagnostics["source_filter_prune_count"], 1)
        self.assertGreaterEqual(diagnostics["threshold_prune_count"], 1)
        self.assertTrue(diagnostics["gold_source_reached_pool"])
        self.assertTrue(diagnostics["gold_source_verifier_seen"])
        self.assertEqual(report["authority"], "candidate_structure_only_not_source_truth")

    def test_salience_decay_quiets_without_deleting_source(self) -> None:
        report = router.apply_controlled_salience_decay(
            [
                {
                    "candidate_id": "stale",
                    "status": "stale",
                    "source_refs": [{"source_id": "src:stale"}],
                },
                {
                    "candidate_id": "local",
                    "scope": "machine:local",
                    "source_refs": [{"source_id": "src:local"}],
                },
                {"candidate_id": "current", "status": "current"},
            ]
        )
        by_id = {row["candidate_id"]: row for row in report["rows"]}

        self.assertEqual(report["quieted_count"], 2)
        self.assertEqual(by_id["stale"]["foreground_prominence"], "quiet")
        self.assertTrue(by_id["stale"]["reopenable_from_source"])
        self.assertFalse(by_id["stale"]["source_deleted"])
        self.assertTrue(report["source_material_preserved"])

    def test_navigation_potential_uses_microcircuit_diagnostics(self) -> None:
        projection = navigation_potential.build_navigation_potential_projection(
            cognitive_routes=[
                {
                    "route_id": "route-frontier",
                    "status": "unresolved",
                    "title": "preflight route",
                    "summary": "Use preflight before broad test.",
                    "current_frontier": "Run focused checks first.",
                    "source_refs": [{"source_id": "src:frontier"}],
                }
            ]
        )

        self.assertEqual(projection["microcircuit_diagnostics"]["raw_pool_size"], 1)
        self.assertTrue(projection["rules"]["joint_transition_constraints_declared"])

if __name__ == "__main__":
    unittest.main()
