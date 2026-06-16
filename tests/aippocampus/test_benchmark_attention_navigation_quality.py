from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_attention_navigation_quality as benchmark  # noqa: E402


class AttentionNavigationQualityBenchmarkTests(unittest.TestCase):
    def test_report_measures_navigation_quality_and_red_lines_separately(self) -> None:
        payload = benchmark.run_attention_navigation_quality()
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["kind"], "aippocampus_attention_navigation_quality")
        self.assertTrue(payload["ok"], json.dumps(payload, ensure_ascii=False, indent=2))
        self.assertNotIn("score", payload)
        self.assertNotIn("aggregate_score", payload)

        families = {case["family"] for case in payload["cases"]}
        self.assertTrue(
            {
                "positive_route",
                "hard_mask",
                "stale_currentness",
                "conflict",
                "action_time",
                "anti_nag",
            }.issubset(families)
        )

        metrics = payload["metrics"]
        self.assertEqual(metrics["route_precision_at_1"]["rate"], 1.0)
        self.assertEqual(metrics["route_recall_at_k"]["rate"], 1.0)
        self.assertEqual(metrics["source_reopen_success_rate"]["rate"], 1.0)
        self.assertEqual(metrics["wrong_source_evidence_rate"]["rate"], 0.0)
        self.assertEqual(metrics["false_preactivation_rate"]["rate"], 0.0)

        red_lines = payload["hard_red_lines"]
        for name, value in red_lines.items():
            with self.subTest(red_line=name):
                self.assertEqual(value, 0)

        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["private_text_emitted"])
        self.assertNotIn("PRIVATE_", rendered)
        self.assertNotIn("gold_answer", rendered)
        self.assertIn("broad_memory_qa_quality", payload["cannot_claim"])
        self.assertIn("live_host_behavior_lift", payload["cannot_claim"])

    def test_gate_names_separate_contract_design_public_quality_and_default(self) -> None:
        payload = benchmark.run_attention_navigation_quality()

        self.assertTrue(payload["contract_safety_gate_ok"])
        self.assertTrue(payload["router_design_gate_ok"])
        self.assertFalse(payload["public_quality_gate_ok"])
        self.assertFalse(payload["default_adoption_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(
            payload["quality_gate_semantics"]["quality_gate_ok_means"],
            "public_quality_gate_ok",
        )
        self.assertIn(
            "representative_public_or_default_router_quality",
            payload["cannot_claim"],
        )

    def test_public_holdout_cohort_reports_maturity_without_live_host_claims(self) -> None:
        payload = benchmark.run_attention_navigation_public_holdout_cohort()

        self.assertEqual(payload["kind"], "aippocampus_attention_navigation_public_cohort")
        self.assertTrue(payload["contract_safety_gate_ok"])
        self.assertTrue(payload["router_design_gate_ok"])
        self.assertTrue(payload["public_quality_gate_ok"])
        self.assertTrue(payload["default_adoption_gate_ok"])
        self.assertTrue(payload["explicit_agent_recall_auto_gate_ok"])
        self.assertFalse(payload["privacy_boundary"]["raw_source_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["private_text_emitted"])
        self.assertGreaterEqual(payload["benchmark_maturity"]["holdout_case_count"], 10)
        self.assertEqual(payload["benchmark_maturity"]["holdout_used_for_tuning_count"], 0)
        self.assertGreaterEqual(
            payload["metrics"]["families_with_holdout_count"],
            8,
        )
        self.assertEqual(payload["hard_red_lines"]["privacy_bypass_count"], 0)
        self.assertEqual(payload["hard_red_lines"]["masked_source_resurrection_count"], 0)
        self.assertEqual(payload["hard_red_lines"]["source_backed_claim_without_reopen"], 0)
        self.assertEqual(payload["hard_red_lines"]["stale_as_current_count"], 0)
        self.assertEqual(payload["metrics"]["feature_hurt_case_count"], 0)
        self.assertIn("live_host_behavior_lift", payload["cannot_claim"])

    def test_cli_profiles_expose_public_cohort_and_contract_smoke(self) -> None:
        public_proc = subprocess.run(
            [
                sys.executable,
                "benchmarks/aippocampus/benchmark_attention_navigation_quality.py",
                "--profile",
                "public-cohort",
                "--json",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        contract_proc = subprocess.run(
            [
                sys.executable,
                "benchmarks/aippocampus/benchmark_attention_navigation_quality.py",
                "--profile",
                "contract-smoke",
                "--json",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(public_proc.returncode, 0, public_proc.stderr)
        self.assertEqual(contract_proc.returncode, 0, contract_proc.stderr)
        public_payload = json.loads(public_proc.stdout)
        contract_payload = json.loads(contract_proc.stdout)

        self.assertEqual(
            public_payload["kind"],
            "aippocampus_attention_navigation_public_cohort",
        )
        self.assertTrue(public_payload["public_quality_gate_ok"])
        self.assertEqual(
            contract_payload["kind"],
            "aippocampus_attention_navigation_quality",
        )
        self.assertTrue(contract_payload["contract_gate_ok"])
        self.assertFalse(contract_payload["public_quality_gate_ok"])

    def test_red_line_violation_fails_even_when_average_route_rate_is_high(self) -> None:
        cases = benchmark.fixture_navigation_quality_cases()
        bad_cases = copy.deepcopy(cases)
        masked = next(case for case in bad_cases if case["family"] == "hard_mask")
        masked["packet"]["emitted"] = True
        masked["packet"]["source_handles"] = [
            {"source_id": "clean:private", "segment_id": "leaked", "reopen_required": True}
        ]

        payload = benchmark.evaluate_navigation_quality_cases(bad_cases)

        self.assertFalse(payload["ok"])
        self.assertGreater(payload["hard_red_lines"]["privacy_bypass_count"], 0)
        self.assertGreater(payload["hard_red_lines"]["masked_source_resurrection_count"], 0)
        self.assertGreater(payload["metrics"]["route_precision_at_1"]["rate"], 0.8)
        self.assertNotIn("aggregate_score", payload)


if __name__ == "__main__":
    unittest.main()
