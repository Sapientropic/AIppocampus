from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
):
    sys.path.insert(0, str(_path))

import benchmark_source_evidence_retrieval as benchmark  # noqa: E402


class GraphExtractionBoundaryBenchmarkTests(unittest.TestCase):
    def test_graph_extraction_boundary_track_models_scale_and_invalid_structure(self) -> None:
        payload = benchmark.run_graph_extraction_boundary_benchmark()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient")
        self.assertEqual(payload["metrics"]["case_count"], 4)
        self.assertEqual(payload["metrics"]["hit_rate_top3"], 1.0)
        self.assertGreaterEqual(payload["metrics"]["max_doc_bytes"], 50 * 1024)
        self.assertEqual(payload["metrics"]["foreground_extraction_required_count"], 0)
        self.assertEqual(payload["metrics"]["unsupported_graph_facts_as_evidence_count"], 0)
        self.assertEqual(
            payload["metrics"]["graph_sidecar_status_counts"],
            {"advisory": 2, "skipped": 1, "unavailable": 1},
        )
        failure_modes = payload["metrics"]["graph_failure_mode_counts"]
        self.assertEqual(failure_modes["timeout"], 1)
        self.assertEqual(failure_modes["unsupported_relation"], 1)
        self.assertEqual(failure_modes["duplicate_or_malformed_entities"], 1)
        for case in payload["cases"]:
            self.assertTrue(case["source_hit"], case)
            self.assertFalse(case["foreground_extraction_required"], case)
            self.assertFalse(case["graph_fact_usable_as_evidence"], case)
            self.assertIn("graph_sidecar_quality", case["cannot_claim"])
            self.assertNotIn("sentinel", case)
            self.assertNotIn("graph_sidecar_payload", case)

    def test_graph_extraction_boundary_private_debug_is_explicit(self) -> None:
        payload = benchmark.run_graph_extraction_boundary_benchmark(include_private_text=True)

        self.assertTrue(payload["privacy_boundary"]["raw_text_emitted"])
        self.assertTrue(payload["privacy_boundary"]["graph_payload_emitted"])
        self.assertTrue(any("sentinel" in case for case in payload["cases"]))
        self.assertTrue(any("graph_sidecar_payload" in case for case in payload["cases"]))


if __name__ == "__main__":
    unittest.main()
