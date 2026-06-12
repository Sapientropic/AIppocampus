from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_avatar_bounded_resonance as benchmark  # noqa: E402


class AvatarBoundedResonanceBenchmarkTests(unittest.TestCase):
    def test_default_fixture_runs_public_safe_proxy_arms(self) -> None:
        payload = benchmark.run_benchmark()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["kind"], "aippocampus_avatar_bounded_resonance_pilot")
        self.assertEqual(payload["claim_level"], "exploratory_public_safe_deterministic_proxy")
        self.assertEqual(payload["execution"]["mode"], "deterministic_scripted_proxy_v0")
        self.assertEqual(payload["execution"]["live_model_calls"], 0)
        self.assertEqual(payload["coverage"]["case_count"], 12)
        self.assertEqual(payload["coverage"]["arm_count"], 5)
        self.assertEqual(payload["coverage"]["case_arm_count"], 60)
        self.assertEqual(payload["coverage"]["missing_or_out_of_range_families"], [])

        for family_count in payload["coverage"]["family_counts"].values():
            self.assertGreaterEqual(family_count, 3)
            self.assertLessEqual(family_count, 5)

        self.assertEqual(
            payload["metrics"]["best_proxy_arm"],
            "D_bounded_resonance",
        )
        self.assertTrue(payload["metrics"]["bounded_resonance_beats_explicit_instruction_proxy"])
        self.assertTrue(payload["metrics"]["bounded_resonance_beats_neutral_posture_proxy"])
        self.assertTrue(payload["metrics"]["alias_only_drifts_more_than_bounded_resonance"])
        self.assertEqual(
            payload["red_lines"]["bounded_resonance_off_topic_archetype_expansion_count"],
            0,
        )
        self.assertEqual(payload["red_lines"]["bounded_resonance_archetype_used_as_authority_count"], 0)
        self.assertEqual(payload["red_lines"]["factual_claim_from_resonance_count"], 0)
        self.assertEqual(payload["red_lines"]["private_or_sensitive_context_used_count"], 0)
        self.assertFalse(payload["recommendation"]["default_runtime_recommended"])
        self.assertEqual(payload["recommendation"]["bounded_resonance_proxy_signal"], "continue")

        self.assertIn("deterministic_proxy_runner_applies_arms_a_to_e", payload["can_claim"])
        self.assertIn("live_llm_or_host_behavior_lift", payload["cannot_claim"])
        self.assertIn("default_foreground_avatar_runtime_readiness", payload["cannot_claim"])
        self.assertIn("archetype_or_resonance_as_authority", payload["cannot_claim"])
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("E:\\", encoded)
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn("api_key", encoded.lower())
        for row in payload["cases"]:
            self.assertIn("case_hash", row)
            self.assertNotIn("case_id", row)
            self.assertNotIn("scenario", row)
            self.assertNotIn("prompt", row)

    def test_incomplete_fixture_cannot_pass_contract_gate(self) -> None:
        fixture = {
            "kind": "aippocampus_avatar_bounded_resonance_fixture",
            "cases": [
                {
                    "case_id": "single_closeout",
                    "family": "closeout_broad_issue_risk",
                    "scenario": "A too-small fixture should not pass.",
                }
            ],
        }

        payload = benchmark.run_benchmark(fixture)

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["status"], "fixture_incomplete")

    def test_cli_json_entrypoint(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py",
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], "aippocampus_avatar_bounded_resonance_pilot")
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
