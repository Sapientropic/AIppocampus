from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from benchmarks.aippocampus.shared.benchmark_entrypoints import benchmark_entrypoint_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"


def run_repo_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

def run_repo_python_without_provider_keys(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in list(env):
        if any(token in key.upper() for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD")):
            env.pop(key, None)
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env=env,
    )

class BenchmarkEntrypointTests(unittest.TestCase):
    def test_benchmark_readme_starts_with_task_first_run_choices(self) -> None:
        text = (REPO_ROOT / "benchmarks" / "aippocampus" / "README.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("## What To Run", text)
        self.assertIn("Ordinary PR confidence", text)
        self.assertIn("--tier benchmark-smoke --benchmark-suite-profile public-fast", text)
        self.assertIn("--profile release-evidence --output", text)
        self.assertIn("--output <report.json> --cite-summary", text)

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
        for helper in ("shared/memory_hygiene.py", "shared/note_memory_drift.py"):
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

    def test_json_postprocessors_report_missing_required_inputs_structurally(self) -> None:
        cases = (
            (
                "benchmarks/aippocampus/benchmark_longmemeval_rerank_analysis.py",
                ["--report"],
            ),
            (
                "benchmarks/aippocampus/benchmark_run_history_diff.py",
                ["--baseline", "--current"],
            ),
        )
        for script, missing in cases:
            with self.subTest(script=script):
                result = run_repo_python(script, "--json")

                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "missing_required_input")
                self.assertEqual(payload["missing_required_input"], missing)
                self.assertTrue(payload["report_generation_ok"])

    def test_live_provider_benchmark_reports_missing_key_as_json_skip(self) -> None:
        result = run_repo_python_without_provider_keys(
            "benchmarks/aippocampus/benchmark_e2e50_behavior_live.py",
            "--json",
            "--max-cases",
            "1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "skipped_missing_provider_key")
        self.assertTrue(payload["report_generation_ok"])
        self.assertFalse(payload["ok"])

    def test_json_report_generation_success_does_not_use_quality_failure_exit_code(self) -> None:
        result = run_repo_python(
            "benchmarks/aippocampus/benchmark_locomo_answer_usefulness.py",
            "--json",
            "--max-cases",
            "1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["report_generation_ok"])

    def test_entrypoint_manifest_classifies_known_slow_json_runners_without_running_them(self) -> None:
        manifest = benchmark_entrypoint_manifest(BENCHMARKS)
        by_name = {row["script"]: row for row in manifest["entrypoints"]}

        self.assertEqual(manifest["kind"], "aippocampus_benchmark_entrypoint_manifest")
        self.assertGreater(manifest["scanned_count"], 50)
        for script in (
            "benchmark_longmemeval_answer.py",
            "benchmark_source_evidence_retrieval.py",
            "benchmark_suite.py",
        ):
            self.assertEqual(by_name[script]["entrypoint_class"], "heavy_local_eval")
            self.assertEqual(by_name[script]["execution_status"], "not_run")
            self.assertEqual(by_name[script]["classification_basis"], "static_manifest_only")
            self.assertFalse(by_name[script]["public_fast_json_default"])
            self.assertIn("json_contract", by_name[script]["safe_sweep_modes"])

    def test_benchmark_suite_can_emit_entrypoint_manifest_json_quickly(self) -> None:
        result = run_repo_python(
            "benchmarks/aippocampus/benchmark_suite.py",
            "--entrypoint-manifest-json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        by_name = {row["script"]: row for row in payload["entrypoints"]}
        self.assertEqual(payload["kind"], "aippocampus_benchmark_entrypoint_manifest")
        self.assertEqual(by_name["benchmark_suite.py"]["entrypoint_class"], "heavy_local_eval")

if __name__ == "__main__":
    unittest.main()
