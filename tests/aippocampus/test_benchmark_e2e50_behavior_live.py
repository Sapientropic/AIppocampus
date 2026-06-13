from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
if str(BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS))

import benchmark_e2e50_behavior_live as benchmark  # noqa: E402


def _packet_from_prompt(prompt: str) -> dict[str, object]:
    if "AIppocampus packet:\n" not in prompt:
        return {"present": False}
    separator = (
        "\n\nAllowed action_code values:"
        if "\n\nAllowed action_code values:" in prompt
        else "\n\nReturn exactly this JSON shape:"
    )
    packet_text = prompt.split("AIppocampus packet:\n", 1)[1].split(
        separator,
        1,
    )[0]
    return json.loads(packet_text)


class E2E50LiveBehaviorBenchmarkTests(unittest.TestCase):
    def test_action_vocabulary_covers_fixture_expected_codes(self) -> None:
        fixture = benchmark.case_pack_benchmark.load_fixture()
        missing: set[str] = set()
        for case in fixture["cases"]:
            expected = case.get("expected_behavior") or {}
            for key in ("required_codes", "forbidden_codes", "stale_rule_codes"):
                missing.update(
                    code
                    for code in expected.get(key, [])
                    if code not in benchmark.ACTION_GLOSS
                )

        self.assertEqual(missing, set())

    def test_blind_surface_baseline_prompt_omits_label_oracle_leaks(self) -> None:
        case = benchmark.case_pack_benchmark.load_fixture()["cases"][0]
        prompt = benchmark._case_prompt(  # noqa: SLF001
            case,
            "baseline_minimal_context",
            prompt_mode=benchmark.PROMPT_MODE_BLIND_SURFACE,
        )

        self.assertNotIn("case_family:", prompt)
        self.assertNotIn("safe_route_used", prompt)
        self.assertNotIn("Allowed action_code values", prompt)
        self.assertNotIn("AIppocampus packet", prompt)
        self.assertIn("No additional source-backed continuity packet is available", prompt)

    def test_live_model_runner_scores_generated_action_choices(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_chat(messages, config):  # type: ignore[no-untyped-def]
            prompt = messages[-1]["content"]
            packet = _packet_from_prompt(prompt)
            if packet["present"]:
                action = str(
                    packet.get("recommended_next_action_id")
                    or packet.get("recommended_action_codes", [""])[0]
                )
            else:
                action = "manual_search"
            calls.append((action, str(config.temperature)))
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "next_action_id": action,
                                    "needs_manual_search": action == "manual_search",
                                    "would_reopen_source": action == "open_source_first",
                                    "over_constrained": False,
                                    "useful_next_action": action != "manual_search",
                                    "rationale": "public-safe action choice",
                                }
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            }

        with mock.patch.dict(os.environ, {"AIPPOCAMPUS_TEST_KEY": "test"}, clear=False):
            payload = benchmark.run_live_model_benchmark(
                model="mock-model",
                base_url="http://127.0.0.1:9",
                api_key_env="AIPPOCAMPUS_TEST_KEY",
                max_cases=8,
                chat_fn=fake_chat,
            )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertTrue(payload["quality_gate_ok"])
        self.assertTrue(payload["claim_gate_ok"])
        self.assertTrue(payload["behavior_validation_closeout_ok"])
        self.assertEqual(
            payload["claim_level"],
            "public_safe_blind_surface_live_behavior_pilot",
        )
        self.assertEqual(payload["kind"], "aippocampus_e2e50_silent_constraint_live_behavior_pilot")
        self.assertEqual(payload["execution"]["prompt_mode"], benchmark.PROMPT_MODE_BLIND_SURFACE)
        self.assertEqual(payload["execution"]["live_model_calls"], 16)
        self.assertEqual(payload["execution"]["settings"]["temperature_requested"], None)
        self.assertFalse(payload["execution"]["settings"]["temperature_sent"])
        self.assertEqual(payload["arms"]["baseline_minimal_context"]["manual_search_count"], 8)
        self.assertEqual(payload["arms"]["aippocampus_packet"]["correct_rate"], 1.0)
        self.assertGreater(payload["metrics"]["assisted_correct_rate_lift"], 0)
        self.assertTrue(payload["metrics"]["reported_lift_valid_for_behavior_claim"])
        self.assertFalse(payload["prompt_leakage_audit"]["baseline_prompt_exposes_case_family"])
        self.assertFalse(payload["prompt_leakage_audit"]["baseline_prompt_includes_packet_shell"])
        self.assertFalse(payload["prompt_leakage_audit"]["requires_blind_surface_task_fixture"])
        self.assertIn("baseline_lift_from_label_oracle_prompt", payload["cannot_claim"])
        self.assertIn(
            "public_safe_e2e50_blind_surface_behavior_runner_exists",
            payload["can_claim"],
        )
        self.assertEqual(payload["red_lines"]["private_or_sensitive_context_used_count"], 0)
        self.assertEqual(payload["red_lines"]["invalid_action_count"], 0)
        self.assertEqual(len(calls), 16)
        self.assertNotIn("e2e50-binding-constraint-public", encoded)
        self.assertNotIn('"behavior_trace":', encoded)
        self.assertFalse(payload["execution"]["api_key_value_printed"])
        self.assertNotIn('"api_key":"test"', encoded)

    def test_label_oracle_mode_cannot_close_behavior_claim(self) -> None:
        def fake_chat(messages, config):  # type: ignore[no-untyped-def]
            packet = _packet_from_prompt(messages[-1]["content"])
            action = (
                str(packet.get("recommended_action_codes", ["manual_search_requested"])[0])
                if packet["present"]
                else "manual_search_requested"
            )
            return {
                "choices": [{"message": {"content": json.dumps({"action_code": action})}}],
                "usage": {},
            }

        with mock.patch.dict(os.environ, {"AIPPOCAMPUS_TEST_KEY": "test"}, clear=False):
            payload = benchmark.run_live_model_benchmark(
                model="mock-model",
                base_url="http://127.0.0.1:9",
                api_key_env="AIPPOCAMPUS_TEST_KEY",
                max_cases=1,
                prompt_mode=benchmark.PROMPT_MODE_LABEL_ORACLE,
                chat_fn=fake_chat,
            )

        self.assertFalse(payload["claim_gate_ok"])
        self.assertFalse(payload["behavior_validation_closeout_ok"])
        self.assertTrue(payload["prompt_leakage_audit"]["baseline_prompt_exposes_case_family"])
        self.assertTrue(payload["prompt_leakage_audit"]["baseline_prompt_includes_packet_shell"])

    def test_cli_summary_omits_case_and_model_output_fields(self) -> None:
        summary = benchmark.cli_summary()
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["kind"], benchmark.REPORT_KIND)
        self.assertEqual(summary["status"], "summary_only")
        self.assertEqual(
            summary["stdout_boundary"],
            "summary_only_use_output_for_sanitized_full_report",
        )
        self.assertNotIn("cases", summary)
        self.assertNotIn("SHOULD_NOT_REACH_STDOUT", encoded)

    def test_invalid_action_keeps_contract_incomplete_without_prompt_leak(self) -> None:
        def fake_chat(messages, config):  # type: ignore[no-untyped-def]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action_code": "PRIVATE_SENTINEL_BAD_ACTION",
                                    "needs_manual_search": False,
                                    "would_reopen_source": False,
                                    "over_constrained": False,
                                    "useful_next_action": False,
                                    "rationale": "bad action",
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }

        with mock.patch.dict(os.environ, {"AIPPOCAMPUS_TEST_KEY": "test"}, clear=False):
            payload = benchmark.run_live_model_benchmark(
                model="mock-model",
                base_url="http://127.0.0.1:9",
                api_key_env="AIPPOCAMPUS_TEST_KEY",
                max_cases=1,
                chat_fn=fake_chat,
            )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["red_lines"]["invalid_action_count"], 2)
        self.assertNotIn("PRIVATE_SENTINEL_BAD_ACTION", encoded)
        self.assertNotIn("e2e50-binding-constraint-public", encoded)

    def test_missing_api_key_blocks_before_live_call(self) -> None:
        with mock.patch.dict(os.environ, {"AIPPOCAMPUS_TEST_KEY": ""}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "missing API key env var"):
                benchmark.run_live_model_benchmark(
                    model="mock-model",
                    base_url="http://127.0.0.1:9",
                    api_key_env="AIPPOCAMPUS_TEST_KEY",
                    max_cases=1,
                    chat_fn=lambda messages, config: {},
                )


if __name__ == "__main__":
    unittest.main()
