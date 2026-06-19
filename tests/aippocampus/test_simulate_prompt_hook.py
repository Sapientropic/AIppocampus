from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (SMOKE, SCRIPTS):
    sys.path.insert(0, str(_path))

import simulate_prompt_hook as smoke  # noqa: E402
import smoke_prompt_hook_latency as latency_smoke  # noqa: E402


class SimulatePromptHookSmokeTests(unittest.TestCase):
    def test_default_cases_use_public_synthetic_project_fixture(self) -> None:
        positive_cases = [case for case in smoke.DEFAULT_CASES if not case.get("expect_decision")]
        skip_cases = [case for case in smoke.DEFAULT_CASES if case.get("expect_decision")]

        self.assertGreaterEqual(len(positive_cases), 1)
        self.assertGreaterEqual(len(skip_cases), 1)
        for case in positive_cases:
            self.assertEqual(case.get("expect_candidate_contains"), "Project Atlas")
            self.assertIn("Project Atlas", json.dumps(case, ensure_ascii=False))
        for case in skip_cases:
            self.assertEqual(case.get("expect_decision"), "skip")

    def test_default_smoke_fixture_is_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = smoke.build_default_fixture(Path(tmp))
            result = smoke.run_cases(
                smoke.DEFAULT_CASES,
                cwd=fixture.cwd,
                registry_path=fixture.registry_path,
                registry_dir=None,
                associations_path=fixture.associations_path,
                concept_graph_path=fixture.concept_graph_path,
                use_concept_graph=True,
                search_budget=3,
            )

        self.assertEqual(result["failed"], 0, result["rows"])
        self.assertGreaterEqual(result["case_count"], 4)
        self.assertIn("evidence", {row["decision"] for row in result["rows"]})
        self.assertIn("skip", {row["decision"] for row in result["rows"]})

    def test_latency_probe_summary_separates_startup_overhead_from_recall_work(self) -> None:
        rows = [
            {
                "wall_ms": 120.0,
                "hook_elapsed_ms": 20.0,
                "startup_import_io_ms": 100.0,
                "decision": "skip",
                "prompt": "secret raw prompt",
            },
            {
                "wall_ms": 240.0,
                "hook_elapsed_ms": 40.0,
                "startup_import_io_ms": 200.0,
                "decision": "skip",
                "source_text": "private source text",
            },
        ]

        report = latency_smoke.summarize_latency_rows(rows)

        self.assertEqual(report["run_count"], 2)
        self.assertEqual(report["wall_ms"]["p50"], 120.0)
        self.assertEqual(report["hook_elapsed_ms"]["p95"], 40.0)
        self.assertEqual(report["startup_import_io_ms"]["max"], 200.0)
        self.assertEqual(report["foreground_latency_red_line_violation_count"], 0)
        self.assertEqual(
            report["responsiveness_contract"]["privacy_boundary"],
            "aggregate_timing_only_no_raw_prompt_source_or_local_path",
        )
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("secret raw prompt", encoded)
        self.assertNotIn("private source text", encoded)

    def test_latency_probe_summary_reports_responsiveness_red_lines(self) -> None:
        rows = [
            {
                "wall_ms": 600.0,
                "hook_elapsed_ms": 90.0,
                "startup_import_io_ms": 510.0,
                "decision": "skip",
                "returncode": 0,
            },
            {
                "wall_ms": 4310.0,
                "hook_elapsed_ms": 180.0,
                "startup_import_io_ms": 4130.0,
                "decision": "skip",
                "returncode": 0,
            },
            {
                "wall_ms": 5050.0,
                "hook_elapsed_ms": 3600.0,
                "startup_import_io_ms": 1450.0,
                "decision": "skip",
                "returncode": 0,
            },
        ]

        report = latency_smoke.summarize_latency_rows(
            rows,
            hook_budget_ms=3500.0,
            host_timeout_ms=5000.0,
            subjective_prompt_p95_target_ms=250.0,
        )
        contract = report["responsiveness_contract"]

        self.assertEqual(report["foreground_latency_red_line_violation_count"], 2)
        self.assertEqual(contract["foreground_latency_red_line_violation_count"], 2)
        self.assertEqual(contract["hook_elapsed_budget_violation_count"], 1)
        self.assertEqual(contract["host_timeout_violation_count"], 1)
        self.assertEqual(contract["near_host_timeout_event_count"], 2)
        self.assertEqual(contract["subjective_prompt_p95_target_miss_count"], 1)
        self.assertEqual(contract["claim_boundary"].count("universal host latency"), 1)

    def test_latency_probe_cli_accepts_hook_budget_switches(self) -> None:
        with mock.patch(
            "smoke_prompt_hook_latency.run_latency_probe",
            return_value={
                "run_count": 1,
                "wall_ms": {"p95": 1.0},
                "startup_import_io_ms": {"p95": 1.0},
            },
        ) as run_probe:
            code = latency_smoke.main(
                [
                    "--runs",
                    "1",
                    "--semantic-gate",
                    "off",
                    "--search-budget",
                    "0",
                    "--hook-budget-ms",
                    "3000",
                    "--host-timeout-ms",
                    "4800",
                    "--subjective-p95-target-ms",
                    "600",
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        run_probe.assert_called_once()
        kwargs = run_probe.call_args.kwargs
        self.assertEqual(kwargs["semantic_gate"], "off")
        self.assertEqual(kwargs["search_budget"], 0)
        self.assertEqual(kwargs["hook_budget_ms"], 3000.0)
        self.assertEqual(kwargs["host_timeout_ms"], 4800.0)
        self.assertEqual(kwargs["subjective_prompt_p95_target_ms"], 600.0)


if __name__ == "__main__":
    unittest.main()
