from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "multimodal_sources"
    / "public_safe_answer_gate.json"
)

from aippocampus_runtime.model import multimodal_answer_gate


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))

class MultimodalAnswerGateTests(unittest.TestCase):
    def test_public_safe_fixture_validates_candidate_packet_shape(self) -> None:
        fixture = load_fixture()

        report = multimodal_answer_gate.validate_answer_gate_fixture(fixture)

        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["schema_version"],
            "aippocampus.multimodal_answer_gate_fixture.v1",
        )
        self.assertEqual(report["case_count"], 7)
        self.assertTrue(
            {
                "temporal_window",
                "entity_reference",
                "place_event",
                "document_payment_relation",
                "source_authority_precedence",
            }.issubset(set(report["join_reasons"]))
        )
        self.assertTrue(report["truth_boundary"]["candidate_packet_is_not_answer"])

    def test_gate_allows_supported_personal_conflict_and_event_cases(self) -> None:
        fixture = load_fixture()

        personal = multimodal_answer_gate.evaluate_answer_gate_case(
            fixture,
            case_id="personalized_reference_supported",
        )
        amount = multimodal_answer_gate.evaluate_answer_gate_case(
            fixture,
            case_id="conflicting_amount_prefers_final_receipt",
        )
        event = multimodal_answer_gate.evaluate_answer_gate_case(
            fixture,
            case_id="cross_modal_event_join_supported",
        )

        self.assertEqual(personal["output_state"], "answer_with_reopened_sources")
        self.assertIn("entity_reference", personal["join_reasons"])
        self.assertEqual(personal["selected_source_ids"], ["mmsrc-user-image-001"])

        self.assertEqual(amount["output_state"], "answer_with_reopened_sources")
        self.assertEqual(amount["selected_source_ids"], ["mmsrc-final-receipt-001"])
        self.assertIn("source_authority_precedence", amount["join_reasons"])

        self.assertEqual(event["output_state"], "answer_with_reopened_sources")
        self.assertTrue(
            {"temporal_window", "place_event", "document_payment_relation"}.issubset(
                set(event["join_reasons"])
            )
        )
        self.assertEqual(
            set(event["selected_source_ids"]),
            {"mmsrc-user-image-001", "mmsrc-calendar-event-001"},
        )

    def test_gate_abstains_when_requested_detail_is_not_source_backed(self) -> None:
        fixture = load_fixture()

        report = multimodal_answer_gate.evaluate_answer_gate_case(
            fixture,
            case_id="unsupported_detail_abstains",
        )

        self.assertEqual(report["output_state"], "abstain_unsupported_detail")
        self.assertFalse(report["can_emit_answer"])
        self.assertIn("unsupported_detail_not_visible", report["blocker_codes"])

    def test_gate_blocks_missing_reopen_background_scan_and_hidden_write(self) -> None:
        fixture = load_fixture()

        missing_reopen = multimodal_answer_gate.evaluate_answer_gate_case(
            fixture,
            case_id="visual_claim_without_source_reopen",
        )
        background = multimodal_answer_gate.evaluate_answer_gate_case(
            fixture,
            case_id="background_media_without_selection",
        )
        hidden_write = multimodal_answer_gate.evaluate_answer_gate_case(
            fixture,
            case_id="hidden_durable_write_during_task_use",
        )

        self.assertEqual(missing_reopen["output_state"], "source_reopen_required")
        self.assertEqual(missing_reopen["metrics"]["source_reopen_required_violation_count"], 1)
        self.assertIn("source_reopen_required", missing_reopen["blocker_codes"])

        self.assertEqual(background["output_state"], "blocked_policy_violation")
        self.assertEqual(background["metrics"]["background_scan_violation_count"], 1)
        self.assertIn("background_media_denied_by_default", background["blocker_codes"])

        self.assertEqual(hidden_write["output_state"], "blocked_policy_violation")
        self.assertEqual(hidden_write["metrics"]["hidden_durable_write_violation_count"], 1)
        self.assertIn("hidden_durable_write_performed", hidden_write["blocker_codes"])

    def test_smoke_metrics_and_report_are_sanitized(self) -> None:
        fixture = load_fixture()

        payload = multimodal_answer_gate.run_answer_gate_smoke(fixture)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_multimodal_answer_gate_smoke")
        self.assertEqual(payload["metrics"]["case_count"], 7)
        self.assertEqual(payload["metrics"]["source_reopen_required_violation_count"], 1)
        self.assertEqual(payload["metrics"]["background_scan_violation_count"], 1)
        self.assertEqual(payload["metrics"]["hidden_durable_write_violation_count"], 1)
        self.assertFalse(payload["privacy_boundary"]["raw_media_bytes_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_prompt_text_emitted"])

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("SYNTHETIC_VISUAL_DETAIL_DO_NOT_EMIT", serialized)
        self.assertNotIn("SYNTHETIC_BACKGROUND_PATH_TOKEN_DO_NOT_EMIT", serialized)
        self.assertNotIn("SYNTHETIC_DURABLE_WRITE_PAYLOAD_DO_NOT_EMIT", serialized)

if __name__ == "__main__":
    unittest.main()
