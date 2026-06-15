from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_learning_loop_public_companion as companion  # noqa: E402


class LearningLoopPublicCompanionBenchmarkTests(unittest.TestCase):
    def test_public_companion_eval_separates_private_comparable_and_public_metrics(self) -> None:
        report = companion.run_public_companion_eval()

        self.assertEqual(report["kind"], "aippocampus_learning_loop_public_companion_eval")
        self.assertTrue(report["ok"], report)
        self.assertIn("private_dogfood_comparable_metrics", report)
        self.assertIn("public_reproducible_metrics", report)
        public = report["public_reproducible_metrics"]
        self.assertGreater(public["vcs_future_event_surface_before_later_event_count"], 0)
        self.assertGreater(public["negative_no_durable_lesson_count"], 0)
        self.assertFalse(public["state_bench_official_score_claimed"])
        self.assertFalse(report["public_quality_gate_ok"])
        self.assertFalse(report["quality_gate_ok"])
        self.assertEqual(
            public["workflow_guidance_status"],
            "not_applicable_no_eligible_public_shape",
        )
        self.assertEqual(public["workflow_source_shape_eligible_count"], 0)
        surfaces = report["companion_surfaces"]
        self.assertTrue(surfaces["future_event_route_surface_companion"]["ok"])
        self.assertEqual(
            surfaces["workflow_guidance_companion"]["status"],
            "not_applicable_no_eligible_public_shape",
        )
        self.assertEqual(
            surfaces["workflow_guidance_companion"][
                "zero_denominator_interpretation"
            ],
            "guidance_not_measured_for_this_public_corpus",
        )
        self.assertIn("official_state_bench_score", report["cannot_claim"])
        self.assertIn("benchmark_vcs_future_event_recall.py", " ".join(report["reused_benchmark_files"]))

    def test_public_companion_cli_emits_json_without_raw_fixture_text(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "benchmarks/aippocampus/benchmark_learning_loop_public_companion.py",
                "--json",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_learning_loop_public_companion_eval")
        self.assertNotIn("Reject this Redis lock PR", serialized)
        self.assertNotIn("app-layer gateway validation", serialized)
        self.assertFalse(payload["privacy_boundary"]["raw_text_serialized"])
        self.assertFalse(payload["privacy_boundary"]["private_history_used"])


if __name__ == "__main__":
    unittest.main()
