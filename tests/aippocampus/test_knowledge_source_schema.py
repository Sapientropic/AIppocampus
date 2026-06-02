from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "knowledge_sources" / "public_safe_registry.json"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.knowledge import schema as knowledge_schema  # noqa: E402


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def source_by_id(payload: dict, source_id: str) -> dict:
    return next(item for item in payload["sources"] if item["source_id"] == source_id)


def claim_by_id(payload: dict, claim_id: str) -> dict:
    return next(item for item in payload["claims"] if item["claim_id"] == claim_id)


class KnowledgeSourceSchemaTests(unittest.TestCase):
    def test_public_safe_fixture_keeps_navigation_artifacts_candidate_only(self) -> None:
        payload = load_fixture()

        report = knowledge_schema.validate_knowledge_registry(payload, high_stakes=True)

        self.assertTrue(report["ok"], report)
        self.assertTrue(
            {
                "official_guideline_like",
                "legal_statute_like",
                "contract_clause",
                "conversation_turn",
                "low_quality_web_page",
                "model_generated_summary",
                "raw_upload",
            }.issubset({item["source_type"] for item in payload["sources"]})
        )
        self.assertTrue(report["sources"]["ksrc-official-guideline-like"]["activation_eligible"])
        self.assertEqual(
            report["sources"]["ksrc-garbage-upload"]["truth_boundary"],
            "quarantined",
        )
        self.assertIn(
            "missing_provenance_chain",
            report["sources"]["ksrc-garbage-upload"]["blocker_codes"],
        )
        self.assertEqual(
            report["sources"]["ksrc-low-quality-web"]["truth_boundary"],
            "quarantined",
        )
        self.assertIn(
            "tainted_source",
            report["sources"]["ksrc-low-quality-web"]["blocker_codes"],
        )
        self.assertEqual(
            report["sources"]["ksrc-model-summary"]["truth_boundary"],
            "candidate_only",
        )
        self.assertFalse(report["sources"]["ksrc-model-summary"]["activation_eligible"])
        self.assertEqual(
            report["sources"]["ksrc-stale-internal-note"]["truth_boundary"],
            "retired_or_superseded",
        )

    def test_high_stakes_active_source_requires_provenance_integrity_and_scope(self) -> None:
        manifest = {
            "schema_version": "aippocampus.knowledge_source_manifest.v1",
            "source_id": "ksrc-bad-active",
            "source_type": "official_guideline_like",
            "publisher": "Synthetic Authority",
            "authority_level": "official_primary",
            "ingest_status": "active",
            "privacy_class": "public",
            "taint_labels": [],
        }

        report = knowledge_schema.validate_knowledge_source_manifest(
            manifest,
            high_stakes=True,
        )

        self.assertFalse(report["ok"])
        self.assertFalse(report["activation_eligible"])
        self.assertEqual(
            {
                "missing_content_hash_sha256",
                "missing_access_policy",
                "missing_domain_scope",
                "missing_effective_date",
                "missing_jurisdiction_scope",
                "missing_last_verified_at",
                "missing_license",
                "missing_provenance_chain",
            },
            set(report["blocker_codes"]),
        )

    def test_claim_activation_requires_source_span_not_whole_document_blessing(self) -> None:
        payload = load_fixture()
        sources = {item["source_id"]: item for item in payload["sources"]}
        source_report = knowledge_schema.validate_knowledge_source_manifest(
            sources["ksrc-official-guideline-like"],
            high_stakes=True,
        )
        self.assertTrue(source_report["activation_eligible"], source_report)

        good_claim = claim_by_id(payload, "claim-official-span")
        good_report = knowledge_schema.validate_knowledge_claim(
            good_claim,
            sources=sources,
            high_stakes=True,
        )
        self.assertTrue(good_report["promotion_eligible"], good_report)

        whole_document_claim = dict(good_claim)
        whole_document_claim["claim_id"] = "claim-whole-document-shortcut"
        whole_document_claim["source_anchor"] = {"section_anchor": "sec-guideline-duty"}

        bad_report = knowledge_schema.validate_knowledge_claim(
            whole_document_claim,
            sources=sources,
            high_stakes=True,
        )

        self.assertFalse(bad_report["ok"])
        self.assertFalse(bad_report["promotion_eligible"])
        self.assertIn("missing_source_anchor_span", bad_report["blocker_codes"])

    def test_generated_summary_cannot_activate_claim_even_with_plausible_text(self) -> None:
        payload = load_fixture()
        sources = {item["source_id"]: item for item in payload["sources"]}
        claim = claim_by_id(payload, "claim-model-summary-only")
        claim = {**claim, "promotion_status": "activated", "review_status": "reviewed"}

        report = knowledge_schema.validate_knowledge_claim(
            claim,
            sources=sources,
            high_stakes=True,
        )

        self.assertFalse(report["ok"])
        self.assertFalse(report["promotion_eligible"])
        self.assertIn("source_not_activation_eligible", report["blocker_codes"])
        self.assertIn("generated_claim_artifact", report["blocker_codes"])

    def test_claim_activation_requires_review_signature_and_conflict_clearance(self) -> None:
        payload = load_fixture()
        sources = {item["source_id"]: item for item in payload["sources"]}
        good_claim = claim_by_id(payload, "claim-official-span")

        unsigned_claim = dict(good_claim)
        unsigned_claim["claim_id"] = "claim-unsigned"
        unsigned_claim.pop("reviewed_by")
        unsigned_claim.pop("review_signed_at")
        unsigned_claim.pop("confidence")
        unsigned_claim["conflict_status"] = "unreviewed"

        unsigned_report = knowledge_schema.validate_knowledge_claim(
            unsigned_claim,
            sources=sources,
            high_stakes=True,
        )

        self.assertFalse(unsigned_report["promotion_eligible"])
        self.assertIn("missing_reviewed_by", unsigned_report["blocker_codes"])
        self.assertIn("missing_review_signed_at", unsigned_report["blocker_codes"])
        self.assertIn("missing_confidence", unsigned_report["blocker_codes"])
        self.assertIn("claim_conflict_not_cleared", unsigned_report["blocker_codes"])

        conflicted_claim = {
            **good_claim,
            "claim_id": "claim-conflicted",
            "conflict_status": "conflicted",
            "conflict_set_id": "synthetic-safety-duty",
        }
        conflicted_report = knowledge_schema.validate_knowledge_claim(
            conflicted_claim,
            sources=sources,
            high_stakes=True,
        )

        self.assertFalse(conflicted_report["promotion_eligible"])
        self.assertIn("claim_conflict_not_cleared", conflicted_report["blocker_codes"])

        superseded_claim = {
            **good_claim,
            "claim_id": "claim-superseded",
            "superseded_by": "claim-newer-span",
        }
        superseded_report = knowledge_schema.validate_knowledge_claim(
            superseded_claim,
            sources=sources,
            high_stakes=True,
        )

        self.assertFalse(superseded_report["promotion_eligible"])
        self.assertIn("claim_superseded", superseded_report["blocker_codes"])

    def test_conversation_sources_are_valid_but_scoped_to_conversation_claims(self) -> None:
        payload = load_fixture()
        sources = {item["source_id"]: item for item in payload["sources"]}
        source_report = knowledge_schema.validate_knowledge_source_manifest(
            sources["ksrc-user-conversation"],
            high_stakes=True,
        )
        self.assertTrue(source_report["ok"], source_report)
        self.assertEqual(source_report["truth_boundary"], "scoped_source_artifact")

        claim = claim_by_id(payload, "claim-conversation-preference")
        report = knowledge_schema.validate_knowledge_claim(
            claim,
            sources=sources,
            high_stakes=True,
        )
        self.assertTrue(report["promotion_eligible"], report)

        legal_claim = {**claim, "claim_id": "claim-conversation-legal-overreach"}
        legal_claim["claim_scope"] = ["legal-contract-review"]
        legal_claim["jurisdiction_scope"] = ["contract-scope"]
        legal_claim["authority_level"] = "conversation_source"

        blocked = knowledge_schema.validate_knowledge_claim(
            legal_claim,
            sources=sources,
            high_stakes=True,
        )

        self.assertFalse(blocked["promotion_eligible"])
        self.assertIn("claim_scope_exceeds_source_scope", blocked["blocker_codes"])

    def test_update_events_keep_old_sources_auditable_and_gate_activation(self) -> None:
        payload = load_fixture()

        report = knowledge_schema.validate_knowledge_registry(payload, high_stakes=True)

        self.assertTrue(report["ok"], report)
        lifecycle = report["lifecycle"]
        self.assertEqual(lifecycle["update_event_count"], 4)
        self.assertTrue(lifecycle["old_sources_auditable"])
        self.assertIn("ksrc-official-guideline-old", lifecycle["source_ids_preserved"])
        self.assertEqual(
            lifecycle["sources"]["ksrc-official-guideline-old"]["effective_status"],
            "superseded",
        )
        self.assertEqual(
            lifecycle["sources"]["ksrc-retracted-advisory"]["effective_status"],
            "retracted",
        )
        self.assertFalse(
            lifecycle["sources"]["ksrc-candidate-guideline-update"]["activation_eligible"]
        )
        self.assertIn(
            "update_review_required",
            lifecycle["events"]["kevt-candidate-update"]["blocker_codes"],
        )

    def test_active_claims_are_downgraded_by_supersession_and_retraction_events(self) -> None:
        payload = load_fixture()
        sources = {item["source_id"]: item for item in payload["sources"]}
        old_claim = {
            **claim_by_id(payload, "claim-official-span"),
            "claim_id": "claim-old-active-span",
            "source_id": "ksrc-official-guideline-old",
            "superseded_by": None,
            "promotion_status": "activated",
        }
        retracted_claim = {
            **claim_by_id(payload, "claim-official-span"),
            "claim_id": "claim-retracted-active-span",
            "source_id": "ksrc-retracted-advisory",
            "claim_scope": ["synthetic-safety"],
            "promotion_status": "activated",
            "superseded_by": None,
        }

        lifecycle = knowledge_schema.evaluate_knowledge_lifecycle(
            {
                "sources": payload["sources"],
                "claims": [old_claim, retracted_claim],
                "update_events": payload["update_events"],
            },
            high_stakes=True,
        )

        self.assertTrue(lifecycle["ok"], lifecycle)
        self.assertEqual(
            lifecycle["claims"]["claim-old-active-span"]["effective_promotion_status"],
            "superseded",
        )
        self.assertIn(
            "source_superseded",
            lifecycle["claims"]["claim-old-active-span"]["lifecycle_reasons"],
        )
        self.assertEqual(
            lifecycle["claims"]["claim-retracted-active-span"]["effective_promotion_status"],
            "blocked",
        )
        self.assertIn(
            "source_retracted",
            lifecycle["claims"]["claim-retracted-active-span"]["lifecycle_reasons"],
        )
        self.assertIn("ksrc-official-guideline-old", sources)
        self.assertIn("ksrc-retracted-advisory", sources)

    def test_high_stakes_update_activation_requires_review_signature(self) -> None:
        payload = load_fixture()
        sources = {item["source_id"]: item for item in payload["sources"]}
        unsigned_event = {
            "schema_version": "aippocampus.knowledge_update_event.v1",
            "event_id": "kevt-unsigned-activation",
            "old_source_id": "ksrc-official-guideline-old",
            "new_source_id": "ksrc-official-guideline-like",
            "diff_type": "superseded",
            "impact_scope": ["synthetic-safety"],
            "affected_claims": ["claim-old-active-span"],
            "requires_review": True,
            "review_status": "reviewed",
            "reviewer": None,
            "review_signed_at": None,
            "activated_at": "2026-06-01T00:00:00Z",
            "rollback_source_id": "ksrc-official-guideline-old",
            "created_at": "2026-06-01T00:00:00Z",
        }

        report = knowledge_schema.validate_knowledge_update_event(
            unsigned_event,
            sources=sources,
            high_stakes=True,
        )

        self.assertFalse(report["activation_eligible"])
        self.assertIn("missing_reviewer", report["blocker_codes"])
        self.assertIn("missing_review_signed_at", report["blocker_codes"])


if __name__ == "__main__":
    unittest.main()
