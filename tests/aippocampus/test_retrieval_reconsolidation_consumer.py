from __future__ import annotations

import unittest

from aippocampus_runtime.recall.active_path_packet import build_active_path_packet
from aippocampus_runtime.reflection import (
    retrieval_reconsolidation,
    retrieval_reconsolidation_consumer,
)


def _candidate(candidate_type: str, outcome: str, *, refs: bool = True) -> dict[str, object]:
    return {
        "kind": retrieval_reconsolidation.RECONSOLIDATION_CANDIDATE_KIND,
        "candidate_id": f"candidate:{candidate_type}:{outcome}",
        "candidate_type": candidate_type,
        "outcome_category": outcome,
        "route": f"route:{candidate_type}",
        "source_refs": [{"source_id": "source:1"}] if refs else [],
    }

class RetrievalReconsolidationConsumerTests(unittest.TestCase):
    def test_consumer_routes_reviewed_candidates_without_source_mutation(self) -> None:
        report = retrieval_reconsolidation_consumer.consume_retrieval_reconsolidation_candidates(
            [
                _candidate("supersession_candidate", "superseded"),
                _candidate("refuted_recall_candidate", "refuted"),
                _candidate("revision_candidate", "stale"),
                _candidate("still_current_candidate", "still_current"),
            ]
        )
        states = {row["candidate_type"]: row for row in report["navigation_metadata"]}

        self.assertEqual(states["supersession_candidate"]["final_state"], "superseded")
        self.assertEqual(states["refuted_recall_candidate"]["final_state"], "superseded")
        self.assertEqual(states["revision_candidate"]["final_state"], "needs_source_reopen")
        self.assertEqual(states["still_current_candidate"]["final_state"], "routed")
        self.assertTrue(states["still_current_candidate"]["foreground_eligible"])
        self.assertFalse(report["clean_source_mutated"])
        self.assertFalse(report["raw_rollout_mutated"])
        self.assertFalse(report["formal_memory_promoted"])

    def test_missing_source_refs_do_not_rank(self) -> None:
        report = retrieval_reconsolidation_consumer.consume_retrieval_reconsolidation_candidates(
            [_candidate("still_current_candidate", "still_current", refs=False)]
        )
        row = report["navigation_metadata"][0]

        self.assertEqual(row["final_state"], "needs_source_reopen")
        self.assertFalse(row["rank_eligible"])
        self.assertIn("retrieval_consumer_updates_source_truth", report["cannot_claim"])

    def test_active_path_packet_consumes_navigation_metadata_without_claim_upgrade(self) -> None:
        packet = build_active_path_packet(
            retrieval_reconsolidation_candidates=[
                _candidate("still_current_candidate", "still_current"),
                _candidate("revision_candidate", "stale"),
                _candidate("supersession_candidate", "superseded"),
                _candidate("revision_candidate", "conflicted"),
                _candidate("still_current_candidate", "still_current", refs=False),
            ],
            max_paths=5,
        )
        paths = [row for row in packet["paths"] if row["origin"] == "retrieval_reconsolidation"]
        routes = {row["route"] for row in paths}
        serialized = str(packet)

        self.assertIn("reopen", routes)
        self.assertIn("ignore", routes)
        self.assertTrue(all(row["source_boundary"]["navigation_not_truth"] for row in paths))
        self.assertTrue(all(row["support_level"] == "candidate" for row in paths))
        self.assertNotIn("raw source", serialized.casefold())
        self.assertNotIn("conflicted", {row["currentness"] for row in paths})
        self.assertNotIn("source_open", {row["action_grammar"] for row in paths})

if __name__ == "__main__":
    unittest.main()
