from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.source import provenance_codebook as codebook  # noqa: E402

FIXTURE = (
    REPO_ROOT
    / "benchmark_corpus"
    / "sparse_provenance"
    / "public_clean_source_like_events.jsonl"
)


class SparseProvenanceCodebookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = codebook._load_jsonl(FIXTURE)
        self.codebook = codebook.build_codebook(self.rows)

    def test_builds_content_addressed_chunks_with_dedupe_and_manifest_hash(self) -> None:
        metrics = self.codebook["metrics"]
        first_entry = self.codebook["entries"][0]

        self.assertEqual(metrics["source_entry_count"], 8)
        self.assertEqual(metrics["unique_chunk_count"], 6)
        self.assertEqual(metrics["deduped_entry_count"], 2)
        self.assertGreater(metrics["dedupe_saved_bytes"], 0)
        self.assertLess(metrics["compression_ratio"], 1.0)
        self.assertTrue(self.codebook["manifest_hash"].startswith("manifest_"))
        self.assertEqual(
            first_entry["source_fingerprint_fields"],
            [
                "content_hash",
                "source_id",
                "privacy_partition",
                "policy_version",
                "lifecycle_state",
            ],
        )

    def test_lookup_returns_route_handles_and_reduces_scan_work(self) -> None:
        lookup = codebook.lookup_routes(self.codebook, "route chain calibration")
        encoded = json.dumps(lookup, ensure_ascii=False)

        self.assertGreaterEqual(len(lookup["routes"]), 1)
        self.assertLess(
            lookup["metrics"]["route_index_candidate_count"],
            lookup["metrics"]["naive_scan_entry_count"],
        )
        self.assertGreater(lookup["metrics"]["lookup_candidate_reduction"], 0)
        self.assertGreater(lookup["metrics"]["blocked_candidate_match_count"], 0)
        self.assertTrue(lookup["routes"][0]["route_handle"].startswith("spc:manifest_"))
        self.assertNotIn("recovered all three public", encoded)
        self.assertNotIn("Quarantined private", encoded)
        self.assertNotIn("Deleted no-recall", encoded)

    def test_rehydrates_selected_route_with_manifest_and_hash_proof(self) -> None:
        lookup = codebook.lookup_routes(self.codebook, "route chain topk2")
        hydrated = codebook.rehydrate_route(self.codebook, lookup["routes"][0]["route_handle"])

        self.assertEqual(hydrated["status"], "ok")
        self.assertIn("Route-chain calibration top-k2", hydrated["text"])
        proof = hydrated["proof"]
        self.assertEqual(proof["manifest_hash"], self.codebook["manifest_hash"])
        self.assertTrue(proof["reconstruction_hash_match"])
        self.assertEqual(proof["source_fingerprint"], lookup["routes"][0]["source_fingerprint"])

    def test_blocked_lifecycle_and_privacy_partitions_do_not_rehydrate_or_emit(self) -> None:
        deleted = next(
            entry
            for entry in self.codebook["entries"]
            if entry["lifecycle_state"] == "deleted_no_recall"
        )
        blocked = codebook.rehydrate_route(
            self.codebook,
            codebook.route_handle_for(self.codebook, deleted),
        )
        report = codebook.build_report(self.rows, query="route chain agent facade")

        self.assertEqual(blocked["status"], "blocked")
        self.assertNotIn("text", blocked)
        self.assertTrue(
            all(value == 0 for value in report["quality"]["red_lines"].values()),
            report["quality"]["red_lines"],
        )
        self.assertEqual(report["quality"]["metrics"]["wrong_source_reconstruction_count"], 0)

    def test_topology_preservation_check_keeps_route_relations_below_truth_layer(self) -> None:
        report = codebook.build_report(self.rows, query="route chain")
        topology = report["quality"]["topology_preservation_check"]
        route = report["lookup"]["routes"][0]

        self.assertEqual(topology["status"], "ok")
        self.assertIn("source_support_chain", topology["preserves"])
        self.assertIn("topology_hash", route["topology"])
        self.assertEqual(route["claim_permission"], "no_claim_before_reopen")


if __name__ == "__main__":
    unittest.main()
