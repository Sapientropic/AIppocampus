from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (REPO_ROOT, BENCHMARKS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from source_evidence.capability_provenance import (  # noqa: E402
    benchmark_capability_provenance,
)


class BenchmarkCapabilityProvenanceTests(unittest.TestCase):
    def test_semantic_rerank_is_query_time_upper_bound_not_source_side_warming(self) -> None:
        provenance = benchmark_capability_provenance("semantic")

        self.assertEqual(provenance["mode_classification"], "query_time_llm_rerank_upper_bound")
        self.assertEqual(provenance["claim_level"], "benchmark_local_experiment")
        self.assertFalse(provenance["can_claim_source_side_warming"])
        self.assertIn("temporary_provider_prompt", provenance["benchmark_local_scaffolding"])
        self.assertIn("semantic_scope_builder", provenance["relevant_aippocampus_paths_not_used"])

    def test_source_semantic_cache_is_worker_surface_proxy_with_remaining_gap(self) -> None:
        provenance = benchmark_capability_provenance("source_semantic_cache")

        self.assertEqual(provenance["mode_classification"], "source_worker_surface_proxy")
        self.assertEqual(provenance["claim_level"], "aippocampus_proxy_baseline")
        self.assertFalse(provenance["can_claim_source_side_warming"])
        self.assertEqual(provenance["remaining_gap_issue"], "#1323")
        self.assertIn("aippocampus_working_memory_rows", provenance["aippocampus_capabilities_used"])
        self.assertIn("semantic_scope_labeling", provenance["relevant_aippocampus_paths_not_used"])

    def test_materialized_sidecar_cache_can_claim_source_side_warming_slice(self) -> None:
        provenance = benchmark_capability_provenance(
            "source_semantic_cache",
            source_semantic_sidecar_materializer="public_semantic_labeler",
        )

        self.assertEqual(
            provenance["mode_classification"],
            "source_semantic_scope_sidecar_cache",
        )
        self.assertEqual(
            provenance["claim_level"],
            "materialized_public_semantic_sidecar_benchmark",
        )
        self.assertTrue(provenance["can_claim_source_side_warming"])
        self.assertIn("semantic_scope_labeling", provenance["aippocampus_capabilities_used"])
        self.assertIn(
            "canonical_semantic_scope_sidecar",
            provenance["aippocampus_capabilities_used"],
        )
        self.assertNotIn(
            "semantic_scope_labeling",
            provenance["relevant_aippocampus_paths_not_used"],
        )

    def test_cold_retrieval_reports_actual_aippocampus_adapter_surface(self) -> None:
        provenance = benchmark_capability_provenance("off")

        self.assertEqual(provenance["mode_classification"], "cold_deterministic_retrieval")
        self.assertEqual(provenance["claim_level"], "aippocampus_capability_measurement")
        self.assertTrue(provenance["can_claim_retrieval_adapter_evidence"])
        self.assertIn("clean_source_adapter", provenance["aippocampus_capabilities_used"])


if __name__ == "__main__":
    unittest.main()
