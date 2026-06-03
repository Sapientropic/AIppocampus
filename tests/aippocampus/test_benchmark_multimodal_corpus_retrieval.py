from __future__ import annotations

import json
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

import benchmark_multimodal_corpus_retrieval as benchmark  # noqa: E402


class MultimodalCorpusRetrievalBenchmarkTests(unittest.TestCase):
    def test_fixture_declares_public_safe_sources_and_derived_artifact_provenance(self) -> None:
        fixture = benchmark.load_fixture()
        report = benchmark.validate_fixture(fixture)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["schema_version"], "aippocampus.multimodal_corpus_fixture.v1")
        self.assertEqual(report["source_count"], 6)
        self.assertEqual(report["qa_case_count"], 4)
        self.assertGreaterEqual(report["derived_artifact_count"], 8)
        self.assertEqual(
            {
                "image",
                "video_frame",
                "email_message",
                "receipt",
                "invoice",
                "calendar_location",
            },
            set(report["source_modalities"]),
        )

        for artifact in fixture["derived_artifacts"]:
            self.assertIn(artifact["parent_source_id"], report["source_ids"])
            self.assertIn("source_anchor", artifact)
            self.assertIn("provider_route", artifact)
            self.assertIn("confidence", artifact)
            self.assertIn("created_at", artifact)

    def test_derived_text_mode_reports_required_metrics_and_query_shapes(self) -> None:
        payload = benchmark.run_benchmark(raw_media_mode="disabled")

        self.assertEqual(payload["kind"], "aippocampus_multimodal_corpus_retrieval_benchmark")
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "fixture_contract_scored")
        self.assertEqual(payload["tracks"]["derived_text"]["status"], "scored")
        self.assertEqual(payload["tracks"]["raw_media"]["status"], "skipped_provider_not_configured")

        metrics = payload["metrics"]
        for key in {
            "retrieval_recall_at_3",
            "source_reopen_success_rate",
            "unsupported_visual_claim_rate",
            "stale_or_weaker_source_selected_rate",
            "cross_modal_join_success_rate",
            "abstention_accuracy",
        }:
            self.assertIn(key, metrics)
            self.assertIn(key, payload["rate_estimates"])

        self.assertEqual(metrics["retrieval_recall_at_3"], 1.0)
        self.assertEqual(metrics["source_reopen_success_rate"], 1.0)
        self.assertEqual(metrics["unsupported_visual_claim_rate"], 0.0)
        self.assertEqual(metrics["stale_or_weaker_source_selected_rate"], 0.0)
        self.assertEqual(metrics["cross_modal_join_success_rate"], 1.0)
        self.assertEqual(metrics["abstention_accuracy"], 1.0)

        query_shapes = {case["query_shape"] for case in payload["cases"]}
        self.assertEqual(
            {
                "personalized_reference",
                "conflict_resolution",
                "cross_modal_join",
                "unsupported_detail",
            },
            query_shapes,
        )

    def test_raw_media_mode_uses_original_source_anchors_without_claiming_provider_quality(self) -> None:
        payload = benchmark.run_benchmark(raw_media_mode="deterministic_fixture")

        raw_media = payload["tracks"]["raw_media"]
        self.assertEqual(raw_media["status"], "scored")
        self.assertEqual(raw_media["provider_route"], "deterministic_fixture")
        self.assertEqual(raw_media["metrics"]["source_reopen_success_rate"], 1.0)
        self.assertEqual(raw_media["metrics"]["unsupported_visual_claim_rate"], 0.0)
        self.assertIn("live_vision_model_quality", payload["cannot_claim"])
        self.assertIn("raw_media_model_answer_quality", payload["cannot_claim"])

    def test_default_report_sanitizes_fixture_text_and_local_paths(self) -> None:
        payload = benchmark.run_benchmark(raw_media_mode="deterministic_fixture")

        self.assertFalse(payload["privacy_boundary"]["raw_fixture_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_media_exported"])
        self.assertFalse(payload["privacy_boundary"]["external_model_called"])
        self.assertEqual(
            payload["privacy_boundary"]["output_shape"],
            "sanitized_ids_hashes_anchors_and_metrics",
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Grace", serialized)
        self.assertNotIn("Marigold Gallery", serialized)
        self.assertNotIn("synthetic invoice", serialized.lower())
        self.assertNotIn(str(REPO_ROOT), serialized)

    def test_fixture_validation_rejects_derived_artifacts_without_parent_source(self) -> None:
        fixture = benchmark.load_fixture()
        fixture["derived_artifacts"][0]["parent_source_id"] = "missing-source"

        report = benchmark.validate_fixture(fixture)

        self.assertFalse(report["ok"])
        self.assertIn("derived_artifact_unknown_parent_source", report["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
