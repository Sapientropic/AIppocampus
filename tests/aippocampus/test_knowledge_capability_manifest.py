from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "knowledge_sources"
    / "public_safe_capability_manifest.json"
)
REGISTRY = REPO_ROOT / "tests" / "fixtures" / "knowledge_sources" / "public_safe_registry.json"

from aippocampus_runtime.knowledge import capability_types

EXPECTED_SKILL_TYPES = {
    "declarative_knowledge",
    "procedural_operation",
    "perceptual_parsing",
    "judgment_gating",
    "interactive_communication",
    "learning_adaptation",
    "metacognitive",
    "social_relational",
    "tool_affordance",
}
HIGH_RISK_CAPABILITY_ID = "knowledge.contract_review.risk_flag.high.v1"
LOW_RISK_CAPABILITY_ID = "knowledge.claim_lookup.low.v1"
TOOL_ID = "knowledge.claim_lookup"

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

class KnowledgeCapabilityManifestTests(unittest.TestCase):
    def test_public_safe_manifest_validates_typed_sections(self) -> None:
        manifest = load_json(MANIFEST)

        report = capability_types.validate_capability_manifest(manifest)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["schema_version"], "aippocampus.capability_manifest.v1")
        self.assertEqual(report["truth_boundary"], "execution_boundary_not_fact_source")
        self.assertEqual(report["public_api_status"], "internal_architecture_prototype")
        self.assertEqual(set(report["skill_types"]), EXPECTED_SKILL_TYPES)
        self.assertIn(HIGH_RISK_CAPABILITY_ID, report["capability_ids"])
        self.assertEqual(report["blocker_codes"], [])

        high = next(
            item
            for item in manifest["capabilities"]
            if item["capability_id"] == HIGH_RISK_CAPABILITY_ID
        )
        for required in {
            "schema_version",
            "capability_id",
            "version",
            "owner",
            "risk_level",
            "domain",
            "skill_types",
            "memory_policy",
            "privacy_policy",
            "source_requirements",
            "tool_permissions",
            "side_effects",
            "output_classes",
            "evaluation_protocols",
            "supersession",
            "last_reviewed_at",
        }:
            self.assertIn(required, high)
        self.assertIn("parse_contract_clause", high["capability_graph"]["nodes"])
        self.assertIn("human_review_boundary", high["capability_graph"]["nodes"])

    def test_same_tool_has_different_low_and_high_risk_permissions(self) -> None:
        manifest = load_json(MANIFEST)

        profiles = capability_types.tool_permission_profiles(manifest, TOOL_ID)

        by_capability = {item["capability_id"]: item for item in profiles}
        low = by_capability[LOW_RISK_CAPABILITY_ID]
        high = by_capability[HIGH_RISK_CAPABILITY_ID]

        self.assertEqual(low["risk_level"], "low")
        self.assertEqual(high["risk_level"], "high")
        self.assertFalse(low["can_emit_high_risk_answer"])
        self.assertTrue(high["requires_high_risk_gate"])
        self.assertFalse(high["source_text_allowed_external"])
        self.assertTrue(
            {"source_reopen", "active_claim", "current_lifecycle"}.issubset(
                set(high["requires"])
            )
        )
        self.assertNotIn("source_reopen", low["requires"])

    def test_high_risk_capability_rejects_unsourced_or_routing_only_claim(self) -> None:
        manifest = load_json(MANIFEST)
        registry = load_json(REGISTRY)

        report = capability_types.evaluate_manifest_case(
            manifest,
            registry,
            case_id="contract_review_embedding_only",
        )

        self.assertEqual(report["output_state"], "source_reopen_required")
        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["risk_flags"], [])
        self.assertIn("source_reopen_required", report["gate_codes"])
        self.assertIn("embedding_hit_is_navigation_only", report["cannot_claim"])

    def test_high_risk_capability_rejects_stale_or_superseded_claim(self) -> None:
        manifest = load_json(MANIFEST)
        registry = load_json(REGISTRY)

        report = capability_types.evaluate_manifest_case(
            manifest,
            registry,
            case_id="contract_review_superseded_claim",
        )

        self.assertEqual(report["output_state"], "human_review_required")
        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["risk_flags"], [])
        self.assertTrue(
            {
                "claim_effective_status:superseded",
                "source_effective_status:superseded",
            }.intersection(report["gate_codes"]),
            report,
        )
        self.assertIn("inactive_or_unpromoted_claim_not_answerable", report["cannot_claim"])

    def test_high_risk_same_tool_private_partition_needs_explicit_permission(self) -> None:
        manifest = load_json(MANIFEST)
        registry = load_json(REGISTRY)

        report = capability_types.evaluate_manifest_case(
            manifest,
            registry,
            case_id="contract_review_private_external_route",
        )

        self.assertEqual(report["output_state"], "human_review_required")
        self.assertFalse(report["can_emit_high_risk_answer"])
        self.assertEqual(report["risk_flags"], [])
        self.assertIn("privacy_partition_not_allowed", report["gate_codes"])
        self.assertFalse(report["privacy"]["source_text_allowed_external"])

    def test_manifest_report_sanitizes_text_and_local_paths(self) -> None:
        manifest = load_json(MANIFEST)
        registry = load_json(REGISTRY)

        payload = capability_types.run_manifest_smoke(manifest, registry)

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_capability_manifest_smoke")
        self.assertFalse(payload["privacy_boundary"]["raw_input_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])

        serialized = json.dumps(payload, ensure_ascii=False)
        manifest_text = json.dumps(manifest, ensure_ascii=False)
        for claim in registry["claims"]:
            self.assertNotIn(claim["claim_text"], serialized)
        self.assertNotIn("Synthetic SecretCo", serialized)
        self.assertNotIn("IGNORE_PREVIOUS_INSTRUCTIONS", serialized)
        self.assertNotIn(str(REPO_ROOT), serialized)
        self.assertIn("Synthetic SecretCo", manifest_text)

if __name__ == "__main__":
    unittest.main()
