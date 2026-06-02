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

import benchmark_knowledge_pollution as benchmark  # noqa: E402
from aippocampus_runtime.knowledge import capability_contract  # noqa: E402


class KnowledgePollutionBenchmarkTests(unittest.TestCase):
    def test_contract_review_capability_fixture_validates_required_fields(self) -> None:
        fixture = benchmark.load_fixture()

        report = capability_contract.validate_capability_contract(
            fixture["capability_contract"]
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["schema_version"], "aippocampus.capability_contract.v1")
        self.assertEqual(report["capability_id"], "synthetic_contract_review.v1")
        self.assertEqual(report["risk_level"], "high")
        self.assertIn("ksrc-legal-statute-like", report["allowed_sources"])
        self.assertIn("source_reopen_required", report["required_permissions"])
        self.assertIn("legal_advice_or_compliance_certification", report["cannot_claim"])

    def test_benchmark_reports_required_pollution_and_privacy_metrics(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_knowledge_pollution_benchmark")
        self.assertTrue(payload["ok"], payload)
        metrics = payload["metrics"]
        for key in {
            "contamination_escape_rate",
            "stale_source_harm_rate",
            "authority_override_rate",
            "privacy_partition_leak_rate",
            "source_reopen_required_violation_count",
            "unsupported_claim_rate",
        }:
            self.assertIn(key, metrics)
        self.assertEqual(metrics["contamination_escape_rate"], 0.0)
        self.assertEqual(metrics["stale_source_harm_rate"], 0.0)
        self.assertEqual(metrics["authority_override_rate"], 0.0)
        self.assertEqual(metrics["privacy_partition_leak_rate"], 0.0)
        self.assertEqual(metrics["source_reopen_required_violation_count"], 0)
        self.assertEqual(metrics["unsupported_claim_rate"], 0.0)

        families = {case["family"] for case in payload["cases"]}
        self.assertTrue(
            {
                "stale_guideline",
                "old_law",
                "source_looking_fake_authority",
                "prompt_injection_inside_source_text",
                "authority_override",
                "model_summary_as_truth",
                "medical_to_legal_partition",
                "therapy_to_work_partition",
                "contract_secret_external_tool",
                "cross_case_context_bleed",
            }.issubset(families)
        )

    def test_contract_review_prototype_emits_bounded_risk_flags(self) -> None:
        payload = benchmark.run_benchmark()
        by_id = {case["case_id"]: case for case in payload["cases"]}

        supported = by_id["contract_review_supported_risk_flag"]
        self.assertEqual(supported["output_state"], "answer_with_cited_bounds")
        self.assertIn("source_backed_contract_risk_flag", supported["risk_flags"])
        self.assertTrue(supported["cited_boundaries"])
        self.assertIn("legal_advice_or_compliance_certification", supported["cannot_claim"])

        missing = by_id["contract_review_missing_jurisdiction"]
        self.assertEqual(missing["output_state"], "missing_context_question")
        self.assertTrue(missing["missing_context_questions"])
        self.assertIn("missing_jurisdiction_scope", missing["gate_codes"])

        reopen = by_id["contract_review_embedding_only"]
        self.assertEqual(reopen["output_state"], "source_reopen_required")
        self.assertIn("embedding_hit_is_navigation_only", reopen["cannot_claim"])

    def test_default_report_sanitizes_fixture_text(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertFalse(payload["privacy_boundary"]["raw_input_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["absolute_paths_emitted"])

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("IGNORE_PREVIOUS_INSTRUCTIONS", serialized)
        self.assertNotIn("Synthetic SecretCo", serialized)
        self.assertNotIn("therapy conversation says", serialized)
        self.assertNotIn(str(REPO_ROOT), serialized)


if __name__ == "__main__":
    unittest.main()
