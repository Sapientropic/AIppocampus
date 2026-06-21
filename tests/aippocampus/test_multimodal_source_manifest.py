from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "multimodal_sources" / "public_safe_manifest.json"

from aippocampus_runtime.source import multimodal_manifest


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))

class MultimodalSourceManifestTests(unittest.TestCase):
    def test_public_safe_fixture_defines_sources_origins_and_derived_artifacts(self) -> None:
        payload = load_fixture()

        report = multimodal_manifest.validate_multimodal_source_registry(payload)

        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["schema_version"],
            "aippocampus.multimodal_source_registry.v1",
        )
        self.assertEqual(report["source_count"], 4)
        self.assertEqual(report["derived_artifact_count"], 4)
        self.assertEqual(
            {
                "image",
                "chat_message",
                "receipt",
                "calendar_event",
            },
            set(report["source_media_types"]),
        )
        self.assertEqual(
            {
                "user_provided_media",
                "connected_library_media",
                "background_filesystem_media",
            },
            set(report["media_origin_policies"]),
        )

        policy = report["media_origin_policy"]
        self.assertTrue(policy["user_provided_media"]["current_task_access_allowed"])
        self.assertFalse(policy["user_provided_media"]["hidden_durable_write_allowed"])
        self.assertTrue(policy["user_provided_media"]["audit_event_required"])
        self.assertFalse(policy["user_provided_media"]["user_visible_confirmation_required"])
        self.assertTrue(policy["connected_library_media"]["configured_scope_required"])
        self.assertTrue(policy["background_filesystem_media"]["default_access_denied"])

        user_media = next(
            item
            for item in report["sources"].values()
            if item["origin_policy"] == "user_provided_media"
        )
        self.assertTrue(user_media["audit_event_required"])
        self.assertFalse(user_media["user_visible_confirmation_required"])

    def test_derived_artifacts_are_navigation_only_and_reopen_to_parent_anchors(self) -> None:
        payload = load_fixture()

        report = multimodal_manifest.validate_multimodal_source_registry(payload)

        self.assertTrue(report["ok"], report)
        for artifact_id, artifact_report in report["derived_artifacts"].items():
            with self.subTest(artifact_id=artifact_id):
                self.assertEqual(artifact_report["authority"], "navigation_only")
                self.assertTrue(artifact_report["parent_source_resolved"])
                self.assertTrue(artifact_report["parent_anchor_resolved"])
                self.assertFalse(artifact_report["truth_source"])

    def test_validation_rejects_derived_artifact_without_parent_source_anchor(self) -> None:
        payload = load_fixture()
        payload["derived_artifacts"][0]["parent_source_id"] = "missing-source"

        report = multimodal_manifest.validate_multimodal_source_registry(payload)

        self.assertFalse(report["ok"])
        self.assertIn("derived_artifact_unknown_parent_source", report["blocker_codes"])

    def test_validation_rejects_background_media_with_default_task_access(self) -> None:
        payload = load_fixture()
        background = next(
            source
            for source in payload["sources"]
            if source["origin_policy"] == "background_filesystem_media"
        )
        background["task_scoped_access"]["current_task_access_allowed"] = True

        report = multimodal_manifest.validate_multimodal_source_registry(payload)

        self.assertFalse(report["ok"])
        self.assertIn("background_media_default_access_not_denied", report["blocker_codes"])

    def test_validation_rejects_original_source_without_hash_or_anchor(self) -> None:
        payload = load_fixture()
        source = payload["sources"][0]
        source.pop("content_hash_sha256")
        source["source_anchor"] = {}

        report = multimodal_manifest.validate_multimodal_source_registry(payload)

        self.assertFalse(report["ok"])
        self.assertIn("source_missing_content_hash_sha256", report["blocker_codes"])
        self.assertIn("source_missing_anchor", report["blocker_codes"])

    def test_validation_rejects_source_without_source_id(self) -> None:
        payload = load_fixture()
        payload["sources"][0].pop("source_id")

        report = multimodal_manifest.validate_multimodal_source_registry(payload)

        self.assertFalse(report["ok"])
        self.assertIn("source_missing_source_id", report["blocker_codes"])

    def test_validation_rejects_derived_artifact_without_artifact_id(self) -> None:
        payload = load_fixture()
        payload["derived_artifacts"][0].pop("artifact_id")

        report = multimodal_manifest.validate_multimodal_source_registry(payload)

        self.assertFalse(report["ok"])
        self.assertIn("derived_artifact_missing_artifact_id", report["blocker_codes"])

if __name__ == "__main__":
    unittest.main()
