from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime import schema_profiles  # noqa: E402


class SchemaProfileTests(unittest.TestCase):
    def test_identity_minimal_projection_round_trips_without_rich_fields(self) -> None:
        rich_record = {
            "schema_version": "aippocampus.knowledge_source_manifest.v1",
            "record_id": "ksrc-official-guideline-like",
            "source_ref": {
                "kind": "knowledge_source",
                "source_id": "ksrc-official-guideline-like",
            },
            "content_hash_sha256": "a" * 64,
            "created_at": "2026-06-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
            "authority": {"level": "official_primary"},
            "review": {"status": "reviewed"},
            "privacy": {"class": "public"},
            "diagnostics": {"latency_ms": 12},
            "high_risk": {"jurisdiction_scope": ["synthetic"]},
        }

        minimal = schema_profiles.project_record_for_profile(
            rich_record,
            "identity_minimal",
        )
        round_tripped = json.loads(json.dumps(minimal))
        report = schema_profiles.validate_profile_record(
            round_tripped,
            "identity_minimal",
        )

        self.assertEqual(
            [
                "schema_version",
                "record_id",
                "source_ref",
                "content_hash_sha256",
                "created_at",
                "updated_at",
            ],
            list(round_tripped),
        )
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["profile"], "identity_minimal")
        self.assertNotIn("authority", round_tripped)
        self.assertNotIn("diagnostics", round_tripped)
        self.assertNotIn("high_risk", round_tripped)

    def test_high_risk_profile_requires_extra_fields_without_widening_retrieval(self) -> None:
        ordinary_retrieval_record = {
            "schema_version": "aippocampus.clean_chunk.v1",
            "record_id": "chunk-public-safe-001",
            "source_ref": {
                "source_id": "thread-public-safe",
                "event_id": "event-001",
                "line_start": 1,
                "line_end": 3,
            },
            "content_hash_sha256": "b" * 64,
            "created_at": "2026-06-01T00:00:00Z",
            "updated_at": "2026-06-01T00:00:00Z",
            "retrieval": {"source_refs": ["thread-public-safe:event-001"]},
        }

        retrieval_report = schema_profiles.validate_profile_record(
            ordinary_retrieval_record,
            "retrieval_runtime",
        )
        high_risk_report = schema_profiles.validate_profile_record(
            ordinary_retrieval_record,
            "high_risk_required",
        )

        self.assertTrue(retrieval_report["ok"], retrieval_report)
        self.assertFalse(high_risk_report["ok"])
        self.assertEqual(
            {
                "missing_authority",
                "missing_review",
                "missing_lifecycle",
                "missing_privacy",
                "missing_conflict",
                "missing_source_reopen_policy",
            },
            set(high_risk_report["error_codes"]),
        )

        high_risk_record = {
            **ordinary_retrieval_record,
            "authority": {"level": "official_primary"},
            "review": {"status": "reviewed", "reviewed_by": "synthetic-reviewer"},
            "lifecycle": {"status": "active"},
            "privacy": {"class": "public"},
            "conflict": {"status": "none"},
            "source_reopen_policy": {"required": True},
            "diagnostics": {"latency_ms": 42},
        }
        high_risk_projection = schema_profiles.project_record_for_profile(
            high_risk_record,
            "high_risk_required",
        )
        high_risk_ok = schema_profiles.validate_profile_record(
            high_risk_projection,
            "high_risk_required",
        )

        self.assertTrue(high_risk_ok["ok"], high_risk_ok)
        self.assertNotIn("diagnostics", high_risk_projection)
        self.assertIn(
            "field_completeness_is_not_product_quality",
            high_risk_ok["cannot_claim"],
        )
        self.assertIn(
            "wide_metadata_does_not_replace_source_reopen",
            high_risk_ok["cannot_claim"],
        )

        diagnostic_projection = schema_profiles.project_record_for_profile(
            high_risk_record,
            "diagnostic_metrics",
        )
        self.assertIn("diagnostics", diagnostic_projection)
        self.assertNotIn("authority", diagnostic_projection)

    def test_foreground_action_card_profile_projects_out_audit_only_fields(self) -> None:
        card = {
            "decision": "use_route_first",
            "why": "A source-backed route is likely relevant.",
            "next_action": "deepen",
            "claim_boundary": "no_claim_before_reopen",
            "route_label": "release route",
            "metrics": {"too_much": True},
            "red_lines": {"audit": True},
        }

        projected = schema_profiles.project_record_for_profile(card, "foreground_action_card")
        report = schema_profiles.validate_profile_record(projected, "foreground_action_card")

        self.assertTrue(report["ok"], report)
        self.assertNotIn("metrics", projected)
        self.assertNotIn("red_lines", projected)
        self.assertIn("metrics", schema_profiles.FOREGROUND_ACTION_CARD_AUDIT_ONLY_KEYS)


if __name__ == "__main__":
    unittest.main()
