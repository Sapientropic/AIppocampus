from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
EVIDENCE_MAP = REPO_ROOT / "docs" / "evidence" / "benchmark-evidence-map.md"
BENCHMARK_PLAN = (
    REPO_ROOT / "docs" / "evidence" / "benchmarks" / "memory-decision-benchmark-plan.md"
)
sys.path.insert(0, str(BENCHMARKS))

import benchmark_continuous_memory_arms as benchmark  # noqa: E402


class ContinuousMemoryArmsBenchmarkTests(unittest.TestCase):
    def test_report_has_public_safe_memory_attribution_arms(self) -> None:
        payload = benchmark.run_benchmark()

        self.assertEqual(payload["kind"], "aippocampus_continuous_memory_arms_benchmark")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "diagnostic_attribution_controls")
        self.assertEqual(
            set(payload["arms"]),
            {
                "no_memory",
                "true_aippocampus_memory",
                "sham_unrelated_memory",
                "stale_wrong_memory",
                "oracle_memory",
            },
        )
        self.assertEqual(payload["config"]["uses_live_model"], False)
        self.assertEqual(payload["config"]["uses_private_history"], False)
        self.assertIn("author_written_synthetic", payload["config"]["scenario_provenance"])
        self.assertIn("full #378 continuous-memory superiority", payload["cannot_claim"])
        self.assertIn("complete #410 cost and harm ledger", payload["cannot_claim"])

    def test_attribution_metrics_separate_presence_correctness_stale_and_oracle(self) -> None:
        payload = benchmark.run_benchmark()
        metrics = payload["metrics"]
        by_arm = metrics["by_arm"]

        self.assertEqual(metrics["case_count"], 4)
        self.assertEqual(metrics["arm_count"], 5)
        self.assertEqual(metrics["memory_presence_effect"], 0.0)
        self.assertGreater(metrics["memory_correctness_effect"], 0.0)
        self.assertGreater(metrics["stale_memory_harm"], 0.0)
        self.assertGreater(metrics["oracle_headroom"], 0.0)
        self.assertEqual(by_arm["sham_unrelated_memory"]["success_rate"], by_arm["no_memory"]["success_rate"])
        self.assertGreater(
            by_arm["true_aippocampus_memory"]["success_rate"],
            by_arm["sham_unrelated_memory"]["success_rate"],
        )
        self.assertGreater(
            by_arm["oracle_memory"]["success_rate"],
            by_arm["true_aippocampus_memory"]["success_rate"],
        )
        self.assertEqual(
            metrics["source_reopen_obedience_by_arm"]["true_aippocampus_memory"],
            1.0,
        )
        self.assertEqual(metrics["source_reopen_obedience_by_arm"]["oracle_memory"], 1.0)
        self.assertEqual(metrics["source_reopen_obedience_by_arm"]["stale_wrong_memory"], 0.0)

    def test_cases_and_rows_are_sanitized_by_default(self) -> None:
        payload = benchmark.run_benchmark()
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["privacy_boundary"]["public_safe_synthetic_fixtures"], True)
        self.assertEqual(payload["privacy_boundary"]["raw_source_snippets_in_report"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_in_report"], False)
        self.assertEqual(payload["privacy_boundary"]["case_ids_are_hashed"], True)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn("Bearer ", encoded)
        self.assertNotIn("api_key", encoded.lower())
        for row in payload["rows"]:
            self.assertIn("case_id_sha1", row)
            self.assertNotIn("case_id", row)
            self.assertNotIn("correct_memory_text", row)
            self.assertNotIn("source_ref", row)
            self.assertIn("memory_packet_shape", row)

    def test_stale_wrong_arm_is_a_diagnostic_stressor_not_product_claim(self) -> None:
        payload = benchmark.run_benchmark()
        stale_rows = [row for row in payload["rows"] if row["arm"] == "stale_wrong_memory"]

        self.assertGreater(len(stale_rows), 0)
        self.assertTrue(any(row["harm_score"] >= 3 for row in stale_rows))
        self.assertTrue(all(not row["source_backed_hit"] for row in stale_rows))
        self.assertIn(
            "stale wrong arm is an adversarial diagnostic stressor, not a product mode",
            payload["interpretation_notes"],
        )

    def test_docs_register_runner_and_claim_boundary(self) -> None:
        evidence_map = EVIDENCE_MAP.read_text(encoding="utf-8")
        benchmark_plan = BENCHMARK_PLAN.read_text(encoding="utf-8")

        self.assertIn("benchmarks/aippocampus/benchmark_continuous_memory_arms.py", evidence_map)
        self.assertIn("Continuous-memory attribution arms", evidence_map)
        self.assertIn("true_aippocampus_memory", benchmark_plan)
        self.assertIn("sham_unrelated_memory", benchmark_plan)
        self.assertIn("stale_wrong_memory", benchmark_plan)
        self.assertIn("oracle_memory", benchmark_plan)
        self.assertIn("memory_presence_effect", benchmark_plan)
        self.assertIn("memory_correctness_effect", benchmark_plan)
        self.assertIn("not a public superiority claim", benchmark_plan)

    def test_cli_emits_json_and_can_write_report(self) -> None:
        output = REPO_ROOT / ".tmp" / "test-continuous-memory-arms.json"
        if output.exists():
            output.unlink()

        result = subprocess.run(
            [
                sys.executable,
                str(BENCHMARKS / "benchmark_continuous_memory_arms.py"),
                "--json",
                "--output",
                str(output),
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

        stdout_payload = json.loads(result.stdout)
        file_payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(stdout_payload["kind"], "aippocampus_continuous_memory_arms_benchmark")
        self.assertEqual(file_payload["metrics"], stdout_payload["metrics"])


if __name__ == "__main__":
    unittest.main()
