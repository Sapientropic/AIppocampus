from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "knowledge_sources" / "public_safe_registry.json"

from aippocampus_runtime.knowledge import answer_gate


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))

def claim_by_id(payload: dict, claim_id: str) -> dict:
    return next(item for item in payload["claims"] if item["claim_id"] == claim_id)

def valid_context() -> dict:
    return {
        "domain_scope": ["synthetic-safety"],
        "jurisdiction_scope": ["synthetic-jurisdiction"],
        "as_of_date": "2026-06-01",
        "critical_variables": {"synthetic_subject": "known", "synthetic_risk_class": "known"},
        "allow_private_sources": False,
        "external_model_route": False,
    }

def reopened_evidence(payload: dict, claim_id: str) -> dict:
    claim = claim_by_id(payload, claim_id)
    return {
        "kind": "reopened_source_span",
        "claim_id": claim_id,
        "source_id": claim["source_id"],
        "source_anchor": claim["source_anchor"],
    }

class KnowledgeAnswerGateTests(unittest.TestCase):
    def test_embedding_hit_without_source_reopen_cannot_emit_high_risk_answer(self) -> None:
        payload = load_fixture()

        report = answer_gate.evaluate_high_risk_answer_gate(
            payload,
            claim_ids=["claim-official-span"],
            evidence_items=[
                {
                    "kind": "embedding_hit",
                    "claim_id": "claim-official-span",
                    "source_id": "ksrc-official-guideline-like",
                }
            ],
            context=valid_context(),
            required_context_keys=["synthetic_subject", "synthetic_risk_class"],
        )

        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["output_state"], "source_reopen_required")
        self.assertIn("embedding_hit_is_navigation_only", report["cannot_claim"])
        self.assertIn("source_reopen_required", report["gate_codes"])

    def test_missing_context_asks_before_answering_or_reopening_more_source(self) -> None:
        payload = load_fixture()
        context = valid_context()
        context.pop("jurisdiction_scope")
        context.pop("as_of_date")
        context["critical_variables"] = {"synthetic_subject": "known"}

        report = answer_gate.evaluate_high_risk_answer_gate(
            payload,
            claim_ids=["claim-official-span"],
            evidence_items=[reopened_evidence(payload, "claim-official-span")],
            context=context,
            required_context_keys=["synthetic_subject", "synthetic_risk_class"],
        )

        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["output_state"], "missing_context_question")
        self.assertIn("missing_jurisdiction_scope", report["gate_codes"])
        self.assertIn("missing_as_of_date", report["gate_codes"])
        self.assertIn("missing_critical_variable:synthetic_risk_class", report["gate_codes"])
        self.assertTrue(report["questions"])

    def test_generated_source_authority_requires_human_review(self) -> None:
        payload = load_fixture()

        report = answer_gate.evaluate_high_risk_answer_gate(
            payload,
            claim_ids=["claim-model-summary-only"],
            evidence_items=[reopened_evidence(payload, "claim-model-summary-only")],
            context=valid_context(),
            required_context_keys=["synthetic_subject", "synthetic_risk_class"],
        )

        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["output_state"], "human_review_required")
        self.assertIn("claim_not_promotion_eligible", report["gate_codes"])
        self.assertIn("claim_blocker:generated_claim_artifact", report["gate_codes"])
        self.assertIn("source_blocker:generated_source_artifact", report["gate_codes"])

    def test_reopened_active_claim_can_emit_only_with_cited_bounds_and_cannot_claims(self) -> None:
        payload = load_fixture()

        report = answer_gate.evaluate_high_risk_answer_gate(
            payload,
            claim_ids=["claim-official-span"],
            evidence_items=[reopened_evidence(payload, "claim-official-span")],
            context=valid_context(),
            required_context_keys=["synthetic_subject", "synthetic_risk_class"],
        )

        self.assertTrue(report["can_emit_high_risk_answer"], report)
        self.assertEqual(report["output_state"], "answer_with_cited_bounds")
        self.assertEqual(report["cited_boundaries"][0]["claim_id"], "claim-official-span")
        self.assertEqual(
            report["cited_boundaries"][0]["source_id"],
            "ksrc-official-guideline-like",
        )
        self.assertEqual(
            report["cited_boundaries"][0]["jurisdiction_scope"],
            ["synthetic-jurisdiction"],
        )
        self.assertIn("professional_certification_not_claimed", report["cannot_claim"])
        self.assertIn("source_text_not_exported_by_gate", report["cannot_claim"])
        self.assertFalse(report["source_boundary"]["source_text_exported"])
        self.assertFalse(report["source_boundary"]["claim_text_exported"])

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(claim_by_id(payload, "claim-official-span")["claim_text"], serialized)

    def test_conflicting_sources_require_visible_human_review_not_fake_consensus(self) -> None:
        payload = load_fixture()
        selected = {
            **claim_by_id(payload, "claim-official-span"),
            "conflict_set_id": "synthetic-safety-duty",
        }
        conflicting = {
            **selected,
            "claim_id": "claim-conflicting-guideline",
            "source_id": "ksrc-candidate-guideline-update",
            "promotion_status": "uncertain",
            "conflict_status": "conflicted",
            "claim_text": "Synthetic conflicting guidance requires review before use.",
        }
        payload["claims"] = [selected, conflicting]

        report = answer_gate.evaluate_high_risk_answer_gate(
            payload,
            claim_ids=["claim-official-span"],
            evidence_items=[reopened_evidence(payload, "claim-official-span")],
            context=valid_context(),
            required_context_keys=["synthetic_subject", "synthetic_risk_class"],
        )

        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["output_state"], "human_review_required")
        self.assertIn("conflict_set_uncleared", report["gate_codes"])
        self.assertEqual(report["conflict_sets"][0]["conflict_set_id"], "synthetic-safety-duty")
        self.assertIn("claim-conflicting-guideline", report["conflict_sets"][0]["claim_ids"])
        self.assertIn("conflicting_sources_not_averaged", report["cannot_claim"])

    def test_private_source_on_external_route_requires_permission_boundary(self) -> None:
        payload = load_fixture()
        context = {
            "domain_scope": ["conversation-memory"],
            "jurisdiction_scope": ["personal-context"],
            "as_of_date": "2026-06-01",
            "critical_variables": {"synthetic_subject": "known"},
            "allow_private_sources": False,
            "external_model_route": True,
        }

        report = answer_gate.evaluate_high_risk_answer_gate(
            payload,
            claim_ids=["claim-conversation-preference"],
            evidence_items=[reopened_evidence(payload, "claim-conversation-preference")],
            context=context,
            required_context_keys=["synthetic_subject"],
        )

        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["output_state"], "human_review_required")
        self.assertIn("private_source_permission_required", report["gate_codes"])
        self.assertFalse(report["privacy"]["source_text_allowed_external"])

if __name__ == "__main__":
    unittest.main()
