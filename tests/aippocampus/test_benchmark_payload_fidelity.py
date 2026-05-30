from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import benchmark_payload_fidelity as benchmark  # noqa: E402


class PayloadFidelityBenchmarkTests(unittest.TestCase):
    def test_summarize_results_counts_payload_failures(self) -> None:
        rows = [
            {
                "expected": "should_skip",
                "actual": "skip",
                "decision_correct": True,
                "payload_correct": True,
                "source_fidelity": True,
                "privacy_breach": False,
                "parked_memory_injected": False,
                "evidence_without_source": False,
            },
            {
                "expected": "should_scent",
                "actual": "scent",
                "decision_correct": True,
                "payload_correct": False,
                "source_fidelity": True,
                "privacy_breach": False,
                "parked_memory_injected": True,
                "evidence_without_source": False,
            },
            {
                "expected": "should_evidence",
                "actual": "evidence",
                "decision_correct": True,
                "payload_correct": False,
                "source_fidelity": False,
                "privacy_breach": False,
                "parked_memory_injected": False,
                "evidence_without_source": True,
            },
        ]

        metrics = benchmark.summarize_results(rows)

        self.assertEqual(metrics["total_cases"], 3)
        self.assertEqual(metrics["payload_correct_count"], 1)
        self.assertEqual(metrics["parked_memory_injection_count"], 1)
        self.assertEqual(metrics["evidence_without_source_count"], 1)
        self.assertEqual(metrics["source_fidelity_rate"], 0.6667)

    def test_payload_benchmark_checks_context_shape_without_leaking_text(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)

        self.assertEqual(payload["kind"], "aippocampus_payload_fidelity_benchmark")
        self.assertGreaterEqual(payload["metrics"]["total_cases"], 5)
        self.assertEqual(payload["privacy_boundary"]["raw_context_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_emitted"], False)
        self.assertEqual(payload["metrics"]["privacy_breach_count"], 0)
        self.assertEqual(payload["metrics"]["evidence_without_source_count"], 0)
        self.assertEqual(payload["metrics"]["parked_memory_injection_count"], 0)
        for case in payload["cases"]:
            self.assertIn("context_sha1", case)
            self.assertNotIn("context", case)
            self.assertNotIn("prompt", case)
            self.assertIn(case["expected"], benchmark.EXPECTED_LABELS)
            self.assertIn(case["actual"], benchmark.ACTUAL_DECISIONS)

    def test_payload_benchmark_private_debug_requires_explicit_opt_in(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=True)

        self.assertEqual(payload["privacy_boundary"]["raw_context_emitted"], True)
        self.assertTrue(any("context" in case for case in payload["cases"]))

    def test_payload_benchmark_includes_public_memory_pain_boundaries(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=False)

        summary = payload["memory_pain_fixtures"]
        self.assertIn("write_time_pollution", summary["families"])
        self.assertIn("compaction_continuity", summary["families"])
        self.assertEqual(summary["privacy_breach_count"], 0)
        self.assertEqual(summary["evidence_without_source_count"], 0)
        self.assertEqual(summary["unsupported_evidence_count"], 0)
        self.assertIn("competitor_superiority", payload["cannot_claim"])

        rows = [
            row
            for row in payload["cases"]
            if row.get("memory_pain_family")
        ]
        self.assertGreaterEqual(len(rows), 5)
        self.assertFalse(any("prompt" in row for row in rows))
        self.assertFalse(any("context" in row for row in rows))
        self.assertTrue(all(row.get("public_sources") for row in rows))


if __name__ == "__main__":
    unittest.main()
