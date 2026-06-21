from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_benchmark_module

REPO_ROOT = Path(__file__).resolve().parents[2]

benchmark = import_benchmark_module("benchmark_multimodal_corpus_retrieval")

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

    def test_source_open_replay_reports_required_cohorts_and_public_safe_metrics(self) -> None:
        payload = benchmark.run_benchmark(source_open_replay=True)

        self.assertEqual(payload["tracks"]["deterministic_fixture"]["status"], "scored")
        self.assertEqual(payload["tracks"]["source_open_replay"]["status"], "scored")
        self.assertEqual(payload["tracks"]["provider_blocked"]["status"], "blocked")

        replay_case_ids = {
            case["case_id"] for case in payload["tracks"]["source_open_replay"]["cases"]
        }
        self.assertEqual(
            {
                "caption_shortcut_control",
                "raw_media_required_success",
                "unsupported_visual_detail",
                "stale_or_weaker_source_conflict",
                "cross_modal_join",
                "provider_unavailable_hold_open",
            },
            replay_case_ids,
        )

        metrics = payload["metrics"]
        for key in {
            "multimodal_replay_case_count",
            "deterministic_fixture_only_case_count",
            "live_or_declared_media_provider_case_count",
            "raw_media_source_open_success_rate",
            "visual_or_document_claim_source_open_rate",
            "caption_shortcut_violation_count",
            "unsupported_visual_claim_rate",
            "stale_or_weaker_source_selected_rate",
            "cross_modal_join_success_rate",
            "abstention_accuracy",
            "provider_unavailable_blocker_count",
            "raw_media_bytes_public_reported_count",
            "absolute_path_leak_count",
            "live_product_lift_claimed",
        }:
            self.assertIn(key, metrics)

        self.assertEqual(metrics["multimodal_replay_case_count"], 6)
        self.assertEqual(metrics["deterministic_fixture_only_case_count"], 4)
        self.assertEqual(metrics["live_or_declared_media_provider_case_count"], 0)
        self.assertEqual(metrics["caption_shortcut_violation_count"], 0)
        self.assertEqual(metrics["provider_unavailable_blocker_count"], 1)
        self.assertEqual(metrics["raw_media_bytes_public_reported_count"], 0)
        self.assertEqual(metrics["absolute_path_leak_count"], 0)
        self.assertFalse(metrics["live_product_lift_claimed"])
        self.assertIn("media_provider_unavailable", payload["blocker_codes"])

    def test_declared_media_provider_is_counted_without_claiming_live_quality(self) -> None:
        payload = benchmark.run_benchmark(
            source_open_replay=True,
            declared_media_provider="declared_public_safe_provider",
        )

        metrics = payload["metrics"]
        self.assertEqual(metrics["live_or_declared_media_provider_case_count"], 1)
        self.assertEqual(metrics["provider_unavailable_blocker_count"], 0)
        self.assertFalse(metrics["live_product_lift_claimed"])
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
