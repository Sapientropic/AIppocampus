from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (BENCHMARKS, SCRIPTS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import benchmark_state_dependent_preactivation as benchmark  # noqa: E402


class StateDependentPreactivationBenchmarkTests(unittest.TestCase):
    def test_state_dependent_arm_beats_simple_baseline_without_source_truth(self) -> None:
        payload = benchmark.run_state_dependent_preactivation_benchmark()

        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["contract_gate_ok"])
        self.assertFalse(payload["quality_gate_ok"])
        self.assertFalse(payload["public_quality_gate_ok"])
        self.assertEqual(payload["benchmark_maturity_level"], "contract_smoke")
        self.assertEqual(payload["sample_size"], payload["case_count"])
        self.assertEqual(payload["kind"], "aippocampus_state_dependent_preactivation_benchmark")
        self.assertFalse(payload["privacy_boundary"]["input_text_leak_emitted"])
        self.assertFalse(payload["privacy_boundary"]["local_paths_emitted"])
        self.assertNotIn("E:\\", encoded)

        baseline = payload["metrics"]["simple_warm_baseline"]
        stateful = payload["metrics"]["state_dependent"]
        self.assertEqual(stateful["preactivation_hit_rate"], 1.0)
        self.assertEqual(stateful["false_preactivation_rate"], 0.0)
        self.assertEqual(stateful["source_reopen_success_rate"], 1.0)
        self.assertEqual(stateful["foreground_noise_suppression_rate"], 1.0)
        self.assertGreater(baseline["false_preactivation_rate"], 0.0)
        self.assertLess(
            payload["comparison"]["state_dependent_false_preactivation_delta"],
            0,
        )
        self.assertLess(
            payload["comparison"]["state_dependent_source_reopen_cost_delta"],
            0,
        )
        self.assertEqual(stateful["latency_cost_proxy"]["model_call_count"], 0)

        allowed_grammar = {"direction_only", "direction_with_ref", "reopenable_route"}
        for case in payload["cases"]:
            for arm in case["arms"].values():
                for row in arm["predicted_domains"]:
                    self.assertIn(row["action_grammar"], allowed_grammar)
                    self.assertNotEqual(row["action_grammar"], "source_open")

        self.assertIn("state_dependent_preactivation_fixture_exists", payload["can_claim"])
        self.assertIn("preactivation_route_is_memory_truth", payload["cannot_claim"])

    def test_state_dependent_arm_suppresses_stale_privacy_and_conflict(self) -> None:
        payload = benchmark.run_state_dependent_preactivation_benchmark()
        unsafe_case = next(
            case for case in payload["cases"] if case["case_id"] == "unsafe_candidates_suppressed"
        )
        state_rows = {
            row["candidate_id"]: row
            for row in unsafe_case["arms"]["state_dependent"]["predicted_domains"]
        }

        self.assertEqual(state_rows["stale-route"]["status"], "suppressed")
        self.assertIn("stale_or_unknown_freshness", state_rows["stale-route"]["reason_codes"])
        self.assertEqual(state_rows["restricted-route"]["status"], "suppressed")
        self.assertIn("privacy_blocked", state_rows["restricted-route"]["reason_codes"])
        self.assertEqual(state_rows["conflicted-route"]["status"], "suppressed")
        self.assertIn(
            "stale_or_unknown_freshness",
            state_rows["conflicted-route"]["reason_codes"],
        )
        self.assertEqual(
            unsafe_case["arms"]["state_dependent"]["metrics"]["foreground_noise_suppression_rate"],
            1.0,
        )

    def test_cli_json_emits_summary_and_output_writes_full_sanitized_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "state-dependent-full.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "benchmarks/aippocampus/benchmark_state_dependent_preactivation.py",
                    "--json",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            written = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["kind"], benchmark.PREACTIVATION_BENCHMARK_KIND)
        self.assertNotIn("cases", payload)
        self.assertIn("cannot_claim", payload)
        self.assertEqual(payload["contract_gate_ok"], True)
        self.assertEqual(payload["quality_gate_ok"], False)
        self.assertEqual(payload["public_quality_gate_ok"], False)
        self.assertEqual(payload["sample_size"], payload["case_count"])
        self.assertEqual(payload["full_report_flag"], "--output <path>")
        self.assertTrue(payload["full_report_written"])
        self.assertEqual(payload["stdout_boundary"], "public_summary_no_cases_or_source_refs")
        self.assertNotIn("metrics", payload)
        self.assertNotIn("quality_gates", payload)
        self.assertFalse(payload["privacy_boundary"]["source_refs_emitted_to_stdout"])
        self.assertEqual(written["kind"], payload["kind"])
        self.assertIn("cases", written)


if __name__ == "__main__":
    unittest.main()
