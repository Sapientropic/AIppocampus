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

import benchmark_conversational_media_ingest_recall as benchmark  # noqa: E402


class ConversationalMediaIngestRecallBenchmarkTests(unittest.TestCase):
    def test_fixture_declares_media_anchors_inside_conversation_sources(self) -> None:
        fixture = benchmark.load_fixture()
        report = benchmark.validate_fixture(fixture)

        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["schema_version"],
            "aippocampus.conversational_media_ingest_fixture.v1",
        )
        self.assertEqual(report["conversation_count"], 4)
        self.assertGreaterEqual(report["media_anchor_count"], 4)
        self.assertEqual(
            {"conversation_turn", "media_source"},
            set(report["source_kinds"]),
        )
        self.assertEqual(
            report["consent_boundary"],
            "task_scoped_user_provided_media_only",
        )

        for media in fixture["media_sources"]:
            self.assertIn("attached_to_turn_id", media)
            self.assertIn(media["attached_to_turn_id"], report["turn_ids"])
            self.assertIn("source_anchor", media)
            self.assertEqual(media["origin_policy"], "user_provided_same_task")

    def test_report_distinguishes_text_hint_visual_reopen_and_combined_success(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(
            payload["kind"],
            "aippocampus_conversational_media_ingest_recall_benchmark",
        )
        self.assertTrue(payload["ok"], payload)
        metrics = payload["metrics"]
        for key in {
            "personal_reference_resolution_rate",
            "visual_source_reopen_rate",
            "text_hint_leakage_rate",
            "stale_label_correction_success_rate",
            "unsupported_visual_claim_rate",
            "hidden_durable_write_count",
        }:
            self.assertIn(key, metrics)
            if key != "hidden_durable_write_count":
                self.assertIn(key, payload["rate_estimates"])

        self.assertEqual(metrics["personal_reference_resolution_rate"], 1.0)
        self.assertEqual(metrics["visual_source_reopen_rate"], 1.0)
        self.assertEqual(metrics["text_hint_leakage_rate"], 0.0)
        self.assertEqual(metrics["stale_label_correction_success_rate"], 1.0)
        self.assertEqual(metrics["unsupported_visual_claim_rate"], 0.0)
        self.assertEqual(metrics["hidden_durable_write_count"], 0)

        arms = payload["control_arms"]
        self.assertEqual(arms["text_only_conversational_hint"]["visual_claim_allowed"], False)
        self.assertEqual(arms["media_only_corpus_retrieval"]["personal_label_available"], False)
        self.assertEqual(arms["combined_source_backed_recall"]["success_rate"], 1.0)
        self.assertEqual(arms["stale_label_correction"]["success_rate"], 1.0)

    def test_cases_keep_user_wording_and_media_evidence_separate(self) -> None:
        payload = benchmark.run_benchmark()
        by_id = {case["case_id"]: case for case in payload["cases"]}

        combined = by_id["cmir-personal-reference-combined"]
        self.assertTrue(combined["support"]["conversation_hint"])
        self.assertTrue(combined["support"]["media_reopened"])
        self.assertTrue(combined["support"]["visual_claim_requires_media"])
        self.assertEqual(combined["answer_state"], "answer_with_combined_sources")

        leakage = by_id["cmir-text-only-leakage-control"]
        self.assertTrue(leakage["support"]["conversation_hint"])
        self.assertFalse(leakage["support"]["media_reopened"])
        self.assertFalse(leakage["text_hint_leakage"])
        self.assertEqual(leakage["answer_state"], "abstain_requires_media_reopen")

        stale = by_id["cmir-stale-label-correction"]
        self.assertTrue(stale["stale_label_corrected"])
        self.assertEqual(stale["selected_label_source_id"], "turn-correction-001")
        self.assertIn("turn-upload-004", stale["rejected_stale_source_ids"])

    def test_default_report_sanitizes_transcript_text_media_text_and_local_paths(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertFalse(payload["privacy_boundary"]["raw_transcript_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_media_bytes_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])
        self.assertFalse(payload["privacy_boundary"]["hidden_durable_write_performed"])

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Grace", serialized)
        self.assertNotIn("crayfish", serialized.lower())
        self.assertNotIn("843", serialized)
        self.assertNotIn(str(REPO_ROOT), serialized)

    def test_fixture_validation_rejects_media_without_attached_turn(self) -> None:
        fixture = benchmark.load_fixture()
        fixture["media_sources"][0]["attached_to_turn_id"] = "missing-turn"

        report = benchmark.validate_fixture(fixture)

        self.assertFalse(report["ok"])
        self.assertIn("media_source_unknown_attached_turn", report["blocker_codes"])

    def test_source_open_replay_reports_public_safe_upload_selection_flow(self) -> None:
        payload = benchmark.run_benchmark(source_open_replay=True)

        self.assertTrue(payload["ok"], payload)
        metrics = payload["metrics"]
        expected_metrics = {
            "conversational_media_replay_case_count",
            "fixture_boolean_only_case_count",
            "live_or_declared_media_provider_case_count",
            "conversation_turn_source_open_rate",
            "attached_media_source_open_rate",
            "personal_reference_resolution_rate",
            "text_hint_as_visual_proof_violation_count",
            "stale_label_correction_success_rate",
            "hidden_durable_write_count",
            "background_media_access_denied_count",
            "unsupported_visual_claim_rate",
            "provider_unavailable_blocker_count",
            "raw_media_bytes_public_reported_count",
            "absolute_path_leak_count",
            "live_product_lift_claimed",
        }
        self.assertTrue(expected_metrics.issubset(metrics), sorted(metrics))
        self.assertEqual(metrics["conversational_media_replay_case_count"], 7)
        self.assertEqual(metrics["fixture_boolean_only_case_count"], 6)
        self.assertEqual(metrics["live_or_declared_media_provider_case_count"], 1)
        self.assertEqual(metrics["conversation_turn_source_open_rate"], 1.0)
        self.assertEqual(metrics["attached_media_source_open_rate"], 1.0)
        self.assertEqual(metrics["personal_reference_resolution_rate"], 1.0)
        self.assertEqual(metrics["text_hint_as_visual_proof_violation_count"], 0)
        self.assertEqual(metrics["stale_label_correction_success_rate"], 1.0)
        self.assertEqual(metrics["hidden_durable_write_count"], 0)
        self.assertEqual(metrics["background_media_access_denied_count"], 1)
        self.assertEqual(metrics["unsupported_visual_claim_rate"], 0.0)
        self.assertEqual(metrics["provider_unavailable_blocker_count"], 1)
        self.assertEqual(metrics["raw_media_bytes_public_reported_count"], 0)
        self.assertEqual(metrics["absolute_path_leak_count"], 0)
        self.assertFalse(metrics["live_product_lift_claimed"])

        replay_cases = {case["case_id"]: case for case in payload["source_open_replay_cases"]}
        self.assertEqual(
            set(replay_cases),
            {
                "same_task_upload_success",
                "text_hint_not_visual_proof",
                "media_only_label_missing",
                "stale_label_correction",
                "hidden_durable_write_blocked",
                "background_media_denied",
                "provider_unavailable_hold_open",
            },
        )
        self.assertTrue(replay_cases["same_task_upload_success"]["source_open"]["conversation_turn"])
        self.assertTrue(replay_cases["same_task_upload_success"]["source_open"]["attached_media"])
        self.assertEqual(
            replay_cases["text_hint_not_visual_proof"]["answer_state"],
            "hold_open_requires_attached_media_source_open",
        )
        self.assertTrue(replay_cases["media_only_label_missing"]["label_missing"])
        self.assertTrue(replay_cases["hidden_durable_write_blocked"]["blocked"])
        self.assertTrue(replay_cases["background_media_denied"]["blocked"])
        self.assertTrue(replay_cases["provider_unavailable_hold_open"]["provider_blocked"])

    def test_source_open_replay_cli_flag_is_declared(self) -> None:
        parser = benchmark.build_arg_parser()
        args = parser.parse_args(["--source-open-replay", "--json"])

        self.assertTrue(args.source_open_replay)


if __name__ == "__main__":
    unittest.main()
