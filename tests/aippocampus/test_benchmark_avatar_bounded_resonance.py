from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

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

    def test_live_model_mode_scores_public_fixture_without_provider_payloads(self) -> None:
        def fake_chat(messages: list[dict[str, str]], config: benchmark.ChatClientConfig) -> dict:
            prompt = json.loads(messages[1]["content"])
            arm_id = prompt["arm_id"]
            content = {
                "action_summary": "Open the source trail, verify scope, then take the smallest useful action.",
                "focus_codes": ["verification_before_claim", "source_reopen", "short_next_path"],
                "dead_end_detected_before_edit": int("debug" in prompt["scenario"]),
                "verification_before_claim": int(arm_id in {"A_explicit_instruction", "D_bounded_resonance"}),
                "premature_closeout_count": int(arm_id == "C_archetype_alias_only"),
                "useful_slice_preserved_count": int(arm_id in {"A_explicit_instruction", "D_bounded_resonance"}),
                "manual_search_count": 0 if arm_id == "D_bounded_resonance" else 1,
                "route_switch_quality": 3 if arm_id == "D_bounded_resonance" else 2,
                "completion_success": int(arm_id in {"A_explicit_instruction", "D_bounded_resonance"}),
                "over_caution_count": 0,
                "off_topic_archetype_expansion_count": 0,
                "archetype_used_as_authority_count": 0,
                "factual_claim_from_resonance_count": 0,
                "private_or_sensitive_context_used_count": 0,
            }
            return {
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "provider_private_payload": "SHOULD_NOT_BE_COPIED",
            }

        with mock.patch.dict(os.environ, {"TEST_AVATAR_API_KEY": "fake-key"}):
            payload = benchmark.run_live_model_benchmark(
                api_key_env="TEST_AVATAR_API_KEY",
                chat_fn=fake_chat,
            )
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["claim_level"], "exploratory_public_safe_live_model_pilot")
        self.assertEqual(payload["execution"]["mode"], "live_model_public_fixture_v0")
        self.assertEqual(payload["execution"]["live_model_calls"], 60)
        self.assertIsNone(payload["execution"]["settings"]["temperature_requested"])
        self.assertFalse(payload["execution"]["settings"]["temperature_sent"])
        self.assertEqual(payload["usage"]["token_usage"]["total_tokens"], 900)
        self.assertEqual(
            payload["usage"]["provider_cost_status"],
            "estimated_from_official_price_table",
        )
        self.assertGreater(payload["usage"]["cost_usd"], 0)
        self.assertIn("public_safe_live_model_avatar_runner_exists", payload["can_claim"])
        self.assertIn("live_llm_or_host_behavior_lift", payload["cannot_claim"])
        self.assertNotIn("SHOULD_NOT_BE_COPIED", encoded)
        self.assertNotIn("fake-key", encoded)
        self.assertNotIn("scenario", encoded)
        self.assertNotIn("posture_packet", encoded)
        for row in payload["cases"]:
            self.assertIn("model_output_excerpt", row)
            self.assertNotIn("prompt", row)
            self.assertNotIn("case_id", row)

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
