from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "multimodal_sources"
    / "public_safe_provider_routes.json"
)
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.model import multimodal_routing  # noqa: E402


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class MultimodalProviderRoutingTests(unittest.TestCase):
    def test_public_safe_provider_route_manifest_validates(self) -> None:
        manifest = load_fixture()

        report = multimodal_routing.validate_provider_route_manifest(manifest)

        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["schema_version"],
            "aippocampus.multimodal_provider_routes.v1",
        )
        self.assertEqual(report["route_count"], 3)
        self.assertEqual(
            {
                "deepseek-text-derived.v1",
                "local-ocr-current-task.v1",
                "synthetic-vision-current-task.v1",
            },
            set(report["route_ids"]),
        )
        self.assertIn("text", report["input_modalities"])
        self.assertIn("image", report["input_modalities"])
        self.assertTrue(report["truth_boundary"]["derived_outputs_are_navigation_only"])

    def test_text_only_route_rejects_raw_image_or_video_understanding(self) -> None:
        manifest = load_fixture()

        for case_id in ("raw_image_to_text_only_route", "raw_video_to_text_only_route"):
            with self.subTest(case_id=case_id):
                report = multimodal_routing.evaluate_provider_route_case(
                    manifest,
                    case_id=case_id,
                )

                self.assertFalse(report["allowed"])
                self.assertEqual(report["route_id"], "deepseek-text-derived.v1")
                self.assertIn(
                    "provider_route_missing_required_modality",
                    report["blocker_codes"],
                )
                self.assertIn("raw_media_not_allowed_by_route", report["blocker_codes"])
                self.assertFalse(report["raw_media_bytes_exported"])

    def test_text_only_route_can_process_navigation_derived_text(self) -> None:
        manifest = load_fixture()

        report = multimodal_routing.evaluate_provider_route_case(
            manifest,
            case_id="derived_caption_to_text_route",
        )

        self.assertTrue(report["allowed"], report)
        self.assertEqual(report["route_id"], "deepseek-text-derived.v1")
        self.assertEqual(report["input_kind"], "derived_text")
        self.assertFalse(report["can_claim_source_truth"])
        self.assertIn("derived_text_is_navigation_only", report["cannot_claim"])

    def test_user_provided_raw_media_allowed_but_background_media_denied(self) -> None:
        manifest = load_fixture()

        user_report = multimodal_routing.evaluate_provider_route_case(
            manifest,
            case_id="user_image_to_vision_route",
        )
        background_report = multimodal_routing.evaluate_provider_route_case(
            manifest,
            case_id="background_image_to_vision_route",
        )

        self.assertTrue(user_report["allowed"], user_report)
        self.assertEqual(user_report["origin_policy"], "user_provided_media")
        self.assertTrue(user_report["current_task_access_allowed"])
        self.assertFalse(user_report["hidden_durable_write_allowed"])

        self.assertFalse(background_report["allowed"])
        self.assertEqual(background_report["origin_policy"], "background_filesystem_media")
        self.assertIn("background_media_denied_by_default", background_report["blocker_codes"])

    def test_route_smoke_reports_are_sanitized(self) -> None:
        manifest = load_fixture()

        payload = multimodal_routing.run_provider_route_smoke(manifest)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_multimodal_provider_route_smoke")
        self.assertFalse(payload["privacy_boundary"]["raw_media_bytes_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_prompt_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("SYNTHETIC_RAW_IMAGE_BYTES_DO_NOT_EMIT", serialized)
        self.assertNotIn("SYNTHETIC_PRIVATE_PATH_TOKEN_DO_NOT_EMIT", serialized)
        self.assertNotIn("SYNTHETIC_PROVIDER_SECRET_TOKEN_DO_NOT_EMIT", serialized)


if __name__ == "__main__":
    unittest.main()
