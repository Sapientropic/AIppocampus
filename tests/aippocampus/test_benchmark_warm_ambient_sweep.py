from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
sys.path.insert(0, str(BENCHMARKS))

import benchmark_warm_ambient_sweep as sweep  # noqa: E402


class WarmAmbientSweepTests(unittest.TestCase):
    def test_sweep_expands_matrix_and_keeps_output_sanitized(self) -> None:
        calls: list[dict] = []

        def fake_benchmark(**kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "status": "sufficient",
                "live_model": kwargs["live"],
                "metrics": {
                    "case_count": 2,
                    "available_rate": 1.0,
                    "case_pass_rate": 1.0,
                    "false_evidence_count": 0,
                    "missing_source_refs_count": 0,
                    "scout_error_rate": 0.0,
                    "observed_scout_rate": 0.06,
                    "avg_elapsed_ms": float(kwargs["timeout"]) * 10,
                    "max_elapsed_ms": float(kwargs["timeout"]) * 10,
                    "scout_error_kinds": {},
                },
                "quality_gates": {"passed": True, "failed": []},
                "cases": [{"prompt": "raw private prompt should not escape"}],
                "privacy_boundary": {"raw_prompt_emitted": False},
            }

        with tempfile.TemporaryDirectory() as tmp:
            cases_file = Path(tmp) / "private-cases.jsonl"
            cases_file.write_text(
                json.dumps(
                    {
                        "case_id": "private",
                        "prompt": "raw private prompt should not escape",
                        "prompt_trace": [],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            payload = sweep.run_warm_ambient_recall_sweep(
                cases_file=cases_file,
                cwd=Path(tmp) / "workspace",
                live=True,
                wait_modes=("quorum_first", "wait_all"),
                max_workers_values=(3, 5),
                timeout_values=(8.0, 15.0),
                benchmark_fn=fake_benchmark,
            )

        raw = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["matrix"]["run_count"], 8)
        self.assertEqual(len(calls), 8)
        self.assertEqual(len(payload["runs"]), 8)
        self.assertEqual(len(payload["leaderboard"]), 8)
        self.assertTrue(all("cases" not in run for run in payload["runs"]))
        self.assertFalse(payload["privacy_boundary"]["raw_prompt_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_cases_emitted"])
        self.assertNotIn("raw private prompt", raw)
        self.assertIsNone(calls[0]["max_tokens"])

    def test_sweep_ranks_quality_before_latency(self) -> None:
        def fake_benchmark(**kwargs):
            wait_all = bool(kwargs["wait_all"])
            return {
                "ok": wait_all,
                "status": "sufficient" if wait_all else "insufficient",
                "live_model": False,
                "metrics": {
                    "case_count": 4,
                    "available_rate": 1.0 if wait_all else 0.5,
                    "case_pass_rate": 1.0 if wait_all else 0.5,
                    "false_evidence_count": 0,
                    "missing_source_refs_count": 0,
                    "scout_error_rate": 0.0,
                    "observed_scout_rate": 1.0 if wait_all else 0.06,
                    "avg_elapsed_ms": 2000.0 if wait_all else 20.0,
                    "max_elapsed_ms": 2000.0 if wait_all else 20.0,
                    "scout_error_kinds": {},
                },
                "quality_gates": {"passed": wait_all, "failed": [] if wait_all else ["case_pass_rate"]},
                "privacy_boundary": {"raw_prompt_emitted": False},
            }

        payload = sweep.run_warm_ambient_recall_sweep(
            live=False,
            wait_modes=("quorum_first", "wait_all"),
            max_workers_values=(5,),
            timeout_values=(2.0,),
            benchmark_fn=fake_benchmark,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["best"]["wait_mode"], "wait_all")
        self.assertEqual(payload["leaderboard"][0]["quality"]["case_pass_rate"], 1.0)
        self.assertGreater(
            payload["leaderboard"][0]["metrics"]["avg_elapsed_ms"],
            payload["leaderboard"][1]["metrics"]["avg_elapsed_ms"],
        )

    def test_sweep_passes_registry_to_warm_benchmark(self) -> None:
        calls: list[dict] = []

        def fake_benchmark(**kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "status": "sufficient",
                "live_model": False,
                "metrics": {
                    "case_count": 1,
                    "available_rate": 1.0,
                    "case_pass_rate": 1.0,
                    "false_evidence_count": 0,
                    "missing_source_refs_count": 0,
                    "scout_error_rate": 0.0,
                    "observed_scout_rate": 1.0,
                    "avg_elapsed_ms": 1.0,
                    "max_elapsed_ms": 1.0,
                    "scout_error_kinds": {},
                },
                "quality_gates": {"passed": True, "failed": []},
                "privacy_boundary": {"raw_prompt_emitted": False},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "threads.json"
            registry.write_text('{"schema_version":1,"threads":[]}', encoding="utf-8")
            payload = sweep.run_warm_ambient_recall_sweep(
                live=False,
                registry_path=registry,
                wait_modes=("wait_all",),
                max_workers_values=(5,),
                timeout_values=(2.0,),
                benchmark_fn=fake_benchmark,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(calls[0]["registry_path"], registry)
        self.assertIsNone(calls[0]["registry_dir"])

    def test_sweep_passes_case_concurrency_and_progress_dir(self) -> None:
        calls: list[dict] = []

        def fake_benchmark(**kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "status": "sufficient",
                "live_model": True,
                "metrics": {
                    "case_count": 3,
                    "available_rate": 1.0,
                    "case_pass_rate": 1.0,
                    "false_evidence_count": 0,
                    "missing_source_refs_count": 0,
                    "scout_error_rate": 0.0,
                    "observed_scout_rate": 0.2,
                    "avg_elapsed_ms": 1.0,
                    "max_elapsed_ms": 1.0,
                    "scout_error_kinds": {},
                },
                "quality_gates": {"passed": True, "failed": []},
                "privacy_boundary": {"raw_prompt_emitted": False},
            }

        with tempfile.TemporaryDirectory() as tmp:
            payload = sweep.run_warm_ambient_recall_sweep(
                live=True,
                case_offset=10,
                case_limit=3,
                case_workers=2,
                prefix_cache_warmup_scouts=2,
                prefix_cache_warmup_delay=0.25,
                progress_dir=Path(tmp) / "progress",
                benchmark_fn=fake_benchmark,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(calls[0]["case_offset"], 10)
        self.assertEqual(calls[0]["case_limit"], 3)
        self.assertEqual(calls[0]["case_workers"], 2)
        self.assertEqual(calls[0]["prefix_cache_warmup_scouts"], 2)
        self.assertEqual(calls[0]["prefix_cache_warmup_delay"], 0.25)
        self.assertIsNotNone(calls[0]["progress_jsonl"])
        self.assertEqual(payload["matrix"]["case_workers"], 2)
        self.assertEqual(payload["matrix"]["prefix_cache_warmup_scouts"], 2)
        self.assertTrue(payload["matrix"]["progress_dir_enabled"])

    def test_sweep_default_workers_match_full_warm_lane_count(self) -> None:
        calls: list[dict] = []

        def fake_benchmark(**kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "status": "sufficient",
                "live_model": True,
                "metrics": {
                    "case_count": 1,
                    "available_rate": 1.0,
                    "case_pass_rate": 1.0,
                    "false_evidence_count": 0,
                    "missing_source_refs_count": 0,
                    "scout_error_rate": 0.0,
                    "observed_scout_rate": 0.06,
                    "avg_elapsed_ms": 1.0,
                    "max_elapsed_ms": 1.0,
                    "scout_error_kinds": {},
                },
                "quality_gates": {"passed": True, "failed": []},
                "privacy_boundary": {"raw_prompt_emitted": False},
            }

        payload = sweep.run_warm_ambient_recall_sweep(
            live=True,
            benchmark_fn=fake_benchmark,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(calls[0]["max_workers"], 50)
        self.assertIsNone(calls[0]["max_tokens"])

    def test_sweep_reports_no_successful_runs(self) -> None:
        def fake_benchmark(**kwargs):
            del kwargs
            return {
                "ok": False,
                "status": "skipped_missing_api_key",
                "live_model": True,
                "metrics": {"case_count": 0},
                "quality_gates": {"passed": False, "failed": ["missing_api_key"]},
                "privacy_boundary": {"raw_prompt_emitted": False},
            }

        payload = sweep.run_warm_ambient_recall_sweep(
            live=True,
            wait_modes=("quorum_first",),
            max_workers_values=(5,),
            timeout_values=(30.0,),
            benchmark_fn=fake_benchmark,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no_successful_runs")
        self.assertEqual(payload["leaderboard"][0]["status"], "skipped_missing_api_key")

    def test_sweep_analysis_summarizes_failures_and_recommendations(self) -> None:
        def fake_benchmark(**kwargs):
            wait_all = bool(kwargs["wait_all"])
            workers = int(kwargs["max_workers"])
            if workers == 3:
                return {
                    "ok": False,
                    "status": "insufficient",
                    "live_model": True,
                    "metrics": {
                        "case_count": 5,
                        "available_rate": 0.4,
                        "case_pass_rate": 0.6,
                        "false_evidence_count": 1,
                        "missing_source_refs_count": 4,
                        "scout_error_rate": 0.2,
                        "observed_scout_rate": 0.04,
                        "avg_elapsed_ms": 100.0,
                        "max_elapsed_ms": 200.0,
                        "scout_error_kinds": {"read_timeout": 2},
                    },
                    "quality_gates": {
                        "passed": False,
                        "failed": ["available_rate", "case_pass_rate", "false_evidence_count"],
                    },
                    "privacy_boundary": {"raw_prompt_emitted": False},
                }
            return {
                "ok": True,
                "status": "sufficient",
                "live_model": True,
                "metrics": {
                    "case_count": 5,
                    "available_rate": 1.0,
                    "case_pass_rate": 1.0,
                    "false_evidence_count": 0,
                    "missing_source_refs_count": 0 if wait_all else 1,
                    "scout_error_rate": 0.0,
                    "observed_scout_rate": 1.0 if wait_all else 0.06,
                    "avg_elapsed_ms": 800.0 if wait_all else 120.0,
                    "max_elapsed_ms": 900.0 if wait_all else 150.0,
                    "scout_error_kinds": {},
                },
                "quality_gates": {"passed": True, "failed": []},
                "privacy_boundary": {"raw_prompt_emitted": False},
            }

        payload = sweep.run_warm_ambient_recall_sweep(
            live=True,
            wait_modes=("quorum_first", "wait_all"),
            max_workers_values=(3, 5),
            timeout_values=(30.0,),
            benchmark_fn=fake_benchmark,
        )

        analysis = payload["analysis"]

        self.assertEqual(analysis["foreground_recommendation"]["wait_mode"], "quorum_first")
        self.assertEqual(analysis["foreground_recommendation"]["max_workers"], 5)
        self.assertEqual(analysis["detached_recommendation"]["wait_mode"], "wait_all")
        self.assertEqual(analysis["detached_recommendation"]["max_workers"], 5)
        self.assertEqual(analysis["failure_distribution"]["failed_gate_counts"]["available_rate"], 2)
        self.assertEqual(analysis["failure_distribution"]["failed_gate_counts"]["case_pass_rate"], 2)
        self.assertEqual(analysis["failure_distribution"]["failed_gate_counts"]["false_evidence_count"], 2)
        self.assertEqual(analysis["failure_distribution"]["scout_error_kinds"]["read_timeout"], 4)
        self.assertIn("foreground", analysis["recommendation_notes"][0])


if __name__ == "__main__":
    unittest.main()
