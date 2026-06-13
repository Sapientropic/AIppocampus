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
    packet_text = prompt.split("AIppocampus packet:\n", 1)[1].split(
        "\n\nAllowed action_code values:",
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

    def test_live_model_runner_scores_generated_action_choices(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_chat(messages, config):  # type: ignore[no-untyped-def]
            prompt = messages[-1]["content"]
            packet = _packet_from_prompt(prompt)
            if packet["present"]:
                action = packet["recommended_action_codes"][0]
            else:
                action = "manual_search_requested"
            calls.append((action, str(config.temperature)))
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action_code": action,
                                    "needs_manual_search": action == "manual_search_requested",
                                    "would_reopen_source": action
                                    == "source_reopen_before_risky_action",
                                    "over_constrained": False,
                                    "useful_next_action": action != "manual_search_requested",
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
                max_cases=4,
                chat_fn=fake_chat,
            )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertEqual(payload["kind"], "aippocampus_e2e50_silent_constraint_live_behavior_pilot")
        self.assertEqual(payload["execution"]["live_model_calls"], 8)
        self.assertEqual(payload["execution"]["settings"]["temperature_requested"], None)
        self.assertFalse(payload["execution"]["settings"]["temperature_sent"])
        self.assertEqual(payload["arms"]["baseline_minimal_context"]["manual_search_count"], 4)
        self.assertEqual(payload["arms"]["aippocampus_packet"]["correct_rate"], 1.0)
        self.assertGreater(payload["metrics"]["assisted_correct_rate_lift"], 0)
        self.assertEqual(payload["red_lines"]["private_or_sensitive_context_used_count"], 0)
        self.assertEqual(payload["red_lines"]["invalid_action_count"], 0)
        self.assertEqual(len(calls), 8)
        self.assertNotIn("e2e50-binding-constraint-public", encoded)
        self.assertNotIn('"behavior_trace":', encoded)
        self.assertFalse(payload["execution"]["api_key_value_printed"])
        self.assertNotIn('"api_key":"test"', encoded)

    def test_cli_summary_omits_case_and_model_output_fields(self) -> None:
        payload = {
            "kind": benchmark.REPORT_KIND,
            "schema_version": benchmark.SCHEMA_VERSION,
            "ok": True,
            "status": "live_model_behavior_pilot_complete",
            "contract_gate_ok": True,
            "quality_gate_ok": False,
            "metrics": {"assisted_correct_rate_lift": 0.06},
            "arms": {
                "baseline_minimal_context": {"correct_rate": 0.94},
                "aippocampus_packet": {"correct_rate": 1.0},
            },
            "cases": [{"model_output_excerpt": "SHOULD_NOT_REACH_STDOUT"}],
        }

        summary = benchmark.cli_summary(payload)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["kind"], benchmark.REPORT_KIND)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["assisted_correct_rate_lift"], 0.06)
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
