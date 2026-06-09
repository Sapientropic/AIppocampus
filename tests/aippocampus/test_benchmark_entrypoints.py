from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_repo_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


class BenchmarkEntrypointTests(unittest.TestCase):
    def test_provider_conformance_supports_direct_and_module_json_entrypoints(self) -> None:
        direct = run_repo_python(
            "benchmarks/aippocampus/benchmark_provider_conformance.py",
            "--json",
        )
        module = run_repo_python(
            "-m",
            "benchmarks.aippocampus.benchmark_provider_conformance",
            "--json",
        )

        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(module.returncode, 0, module.stderr)
        self.assertEqual(json.loads(direct.stdout)["kind"], "aippocampus_provider_conformance_benchmark")
        self.assertEqual(json.loads(module.stdout)["kind"], "aippocampus_provider_conformance_benchmark")

    def test_source_evidence_graph_extraction_direct_help_names_supported_runner(self) -> None:
        result = run_repo_python(
            "benchmarks/aippocampus/source_evidence/graph_extraction.py",
            "--help",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ImportError", result.stderr)
        self.assertIn("library-only", result.stdout)
        self.assertIn("benchmark_source_evidence_retrieval.py", result.stdout)

    def test_memory_pain_companion_helpers_explain_library_only_contract(self) -> None:
        for helper in ("memory_hygiene.py", "note_memory_drift.py"):
            with self.subTest(helper=helper):
                help_result = run_repo_python(f"benchmarks/aippocampus/{helper}", "--help")
                json_result = run_repo_python(f"benchmarks/aippocampus/{helper}", "--json")

                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertIn("library-only", help_result.stdout)
                self.assertIn("benchmark_memory_decision_gate.py", help_result.stdout)

                self.assertEqual(json_result.returncode, 0, json_result.stderr)
                payload = json.loads(json_result.stdout)
                self.assertEqual(payload["status"], "library_only")
                self.assertEqual(payload["supported_runner"], "benchmarks/aippocampus/benchmark_memory_decision_gate.py")


if __name__ == "__main__":
    unittest.main()
