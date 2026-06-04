from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools" / "aippocampus"
sys.path.insert(0, str(TOOLS))

import run_tests  # noqa: E402

SLOW_REVIEW_CUES = (
    "smoke",
    "real_history",
    "object_storage",
    "onboard",
    "plugin",
    "hook",
    "stage_0_5",
)

# These modules look operational but are intentionally cheap, deterministic unit
# guards. Future additions matching SLOW_REVIEW_CUES should not slide into fast
# by default; update this set only after checking that the module has no live
# service dependency, broad registry scan, plugin install, or long-running smoke.
FAST_REVIEWED_SENSITIVE_MODULES = {
    "tests.aippocampus.test_aippocampus_lifecycle_hook",
    "tests.aippocampus.test_codex_long_session_smoke",
    "tests.aippocampus.test_cross_agent_continuity_smoke",
    "tests.aippocampus.test_diagnose_hooks",
    "tests.aippocampus.test_fresh_thread_real_history_smoke",
    "tests.aippocampus.test_generic_jsonl_integration_smoke",
    "tests.aippocampus.test_install_lifecycle_hook",
    "tests.aippocampus.test_install_prompt_hook",
    "tests.aippocampus.test_macos_install_smoke_workflow",
    "tests.aippocampus.test_memory_pain_prompt_hook_smoke",
    "tests.aippocampus.test_multilingual_prompt_hook_smoke",
    "tests.aippocampus.test_openai_agents_sdk_smoke",
    "tests.aippocampus.test_question_confirmation_live_smoke",
    "tests.aippocampus.test_question_tracking_scale_smoke",
    "tests.aippocampus.test_recall_funnel_smoke",
    "tests.aippocampus.test_semantic_paraphrase_reuse_smoke",
    "tests.aippocampus.test_semantic_scope_source_review",
    "tests.aippocampus.test_simulate_prompt_hook",
    "tests.aippocampus.test_synthetic_scale_capacity_smoke",
}

BENCHMARK_SMOKE_REVIEWED_NON_BENCHMARK_MODULES = {
    # The E2E50 seed scanner is a public-safe deterministic benchmark support
    # guard, not a completed benchmark mirror. Keep it explicit so benchmark
    # smoke does not become a catch-all lane for unrelated fast tests.
    "tests.aippocampus.test_e2e50_seed_candidates",
}


class RunTestsTierTests(unittest.TestCase):
    def test_main_preflights_tempdir_before_loading_tests(self) -> None:
        events: list[str] = []

        with (
            mock.patch.object(
                run_tests,
                "ensure_usable_tempdir",
                side_effect=lambda: events.append("tempdir"),
                create=True,
            ),
            mock.patch.object(run_tests, "modules_for_tier", return_value=["tests.fake"]),
            mock.patch.object(
                run_tests,
                "run_modules",
                side_effect=lambda modules, verbosity: events.append("run") or True,
            ),
        ):
            exit_code = run_tests.main(["--tier", "fast"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["tempdir", "run"])

    def test_main_can_run_benchmark_suite_profile_before_selected_tier(self) -> None:
        events: list[str] = []

        with (
            mock.patch.object(
                run_tests,
                "ensure_usable_tempdir",
                side_effect=lambda: events.append("tempdir"),
                create=True,
            ),
            mock.patch.object(run_tests, "modules_for_tier", return_value=["tests.fake"]),
            mock.patch.object(
                run_tests,
                "run_benchmark_suite_profile",
                side_effect=lambda profile: events.append(f"suite:{profile}") or True,
            ),
            mock.patch.object(
                run_tests,
                "run_modules",
                side_effect=lambda modules, verbosity: events.append("run") or True,
            ),
        ):
            exit_code = run_tests.main(
                [
                    "--tier",
                    "benchmark-smoke",
                    "--benchmark-suite-profile",
                    "public-fast",
                ],
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["tempdir", "suite:public-fast", "run"])

    def test_tier_report_exposes_module_counts_test_counts_and_top_contributors(self) -> None:
        fake_modules = [
            "tests.aippocampus.test_alpha",
            "tests.aippocampus.test_beta",
            "tests.aippocampus.test_benchmark_gamma",
            "tests.aippocampus.test_onboard_codex",
        ]
        counts = {
            "tests.aippocampus.test_alpha": 3,
            "tests.aippocampus.test_beta": 7,
            "tests.aippocampus.test_benchmark_gamma": 11,
            "tests.aippocampus.test_onboard_codex": 13,
        }

        with (
            mock.patch.object(run_tests, "discover_modules", return_value=fake_modules),
            mock.patch.object(
                run_tests,
                "count_tests_for_module",
                side_effect=lambda module: counts[module],
            ),
        ):
            report = run_tests.build_tier_report()

        self.assertEqual(report["kind"], "aippocampus_test_tier_report")
        self.assertEqual(report["tiers"]["full"]["module_count"], 4)
        self.assertEqual(report["tiers"]["full"]["test_count"], 34)
        self.assertEqual(report["tiers"]["fast"]["module_count"], 2)
        self.assertEqual(report["tiers"]["fast"]["test_count"], 10)
        self.assertEqual(
            report["tiers"]["fast"]["top_modules"],
            [
                {"module": "tests.aippocampus.test_beta", "test_count": 7},
                {"module": "tests.aippocampus.test_alpha", "test_count": 3},
            ],
        )
        self.assertTrue(
            any(
                "fast is still exclusion-based" in limitation
                for limitation in report["known_limitations"]
            ),
        )

    def test_report_json_cli_prints_report_without_running_tests(self) -> None:
        report = {
            "kind": "aippocampus_test_tier_report",
            "tiers": {"fast": {"module_count": 1, "test_count": 2}},
        }

        with (
            io.StringIO() as stdout,
            contextlib.redirect_stdout(stdout),
            mock.patch.object(run_tests, "ensure_usable_tempdir", return_value=Path(".")),
            mock.patch.object(run_tests, "build_tier_report", return_value=report),
            mock.patch.object(run_tests, "run_modules") as run_modules,
        ):
            exit_code = run_tests.main(["--report-json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload, report)
        run_modules.assert_not_called()

    def test_benchmark_suite_profile_runner_requires_json_ok(self) -> None:
        completed = run_tests.subprocess.CompletedProcess(
            args=["python"],
            returncode=0,
            stdout='{"ok": true, "status": "quality_gate_passed", "elapsed_ms": 12.5}',
            stderr="",
        )

        with (
            io.StringIO() as stdout,
            contextlib.redirect_stdout(stdout),
            mock.patch.object(run_tests.subprocess, "run", return_value=completed) as run,
        ):
            ok = run_tests.run_benchmark_suite_profile("public-fast")

        self.assertTrue(ok)
        command = run.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertIn("benchmark_suite.py", command[1])
        self.assertEqual(command[-3:], ["--profile", "public-fast", "--json"])

    def test_tempdir_preflight_uses_fallback_when_default_temp_is_unusable(self) -> None:
        calls: list[Path | None] = []

        def fake_probe(path: Path | None) -> None:
            calls.append(path)
            if path is None:
                raise OSError("delete denied")

        with tempfile.TemporaryDirectory() as tmp:
            fallback = Path(tmp) / "runner-temp"
            fallback_identity = fallback.resolve()
            previous_tempdir = getattr(run_tests.tempfile, "tempdir", None)
            with (
                mock.patch.object(run_tests, "_probe_tempdir", side_effect=fake_probe),
                mock.patch.object(run_tests, "FALLBACK_TEST_TMPDIR", fallback),
                mock.patch.dict(os.environ, {}, clear=False),
            ):
                try:
                    selected = run_tests.ensure_usable_tempdir()
                    selected_env = {name: os.environ[name] for name in run_tests.TEMP_ENV_NAMES}
                finally:
                    run_tests.tempfile.tempdir = previous_tempdir

            self.assertEqual(selected, fallback_identity)
            self.assertEqual(calls, [None, fallback_identity])
            for name in run_tests.TEMP_ENV_NAMES:
                self.assertEqual(selected_env[name], str(fallback_identity))

    def test_slow_module_overrides_match_real_test_modules(self) -> None:
        discovered = set(run_tests.discover_modules())

        self.assertEqual(sorted(run_tests.SLOW_MODULES - discovered), [])

    def test_review_sensitive_modules_do_not_enter_fast_by_default(self) -> None:
        fast = set(run_tests.modules_for_tier("fast"))
        unexpected = sorted(
            module
            for module in fast
            if any(cue in module for cue in SLOW_REVIEW_CUES)
            and module not in FAST_REVIEWED_SENSITIVE_MODULES
        )

        self.assertEqual(unexpected, [])

    def test_tiers_partition_the_discovered_test_modules(self) -> None:
        discovered = set(run_tests.discover_modules())
        fast = set(run_tests.modules_for_tier("fast"))
        slow = set(run_tests.modules_for_tier("slow"))
        benchmark = set(run_tests.modules_for_tier("benchmark"))

        self.assertEqual(fast & slow, set())
        self.assertEqual(fast & benchmark, set())
        self.assertEqual(slow & benchmark, set())
        self.assertEqual(fast | slow | benchmark, discovered)

    def test_benchmark_smoke_is_curated_public_lane(self) -> None:
        benchmark = set(run_tests.modules_for_tier("benchmark"))
        smoke = set(run_tests.modules_for_tier("benchmark-smoke"))
        benchmark_smoke = smoke - BENCHMARK_SMOKE_REVIEWED_NON_BENCHMARK_MODULES

        self.assertTrue(smoke)
        self.assertTrue(benchmark_smoke)
        self.assertLess(benchmark_smoke, benchmark)
        self.assertLessEqual(benchmark_smoke, benchmark)
        self.assertEqual(smoke, run_tests.BENCHMARK_SMOKE_MODULES)
        self.assertLessEqual(BENCHMARK_SMOKE_REVIEWED_NON_BENCHMARK_MODULES, smoke)
        self.assertTrue(BENCHMARK_SMOKE_REVIEWED_NON_BENCHMARK_MODULES.isdisjoint(benchmark))
        self.assertNotIn("tests.aippocampus.test_benchmark_live_semantic_gate", smoke)
        self.assertFalse(any("real_history" in module for module in smoke))

    def test_benchmark_smoke_tier_is_exposed_in_cli_and_ci(self) -> None:
        help_text = run_tests.build_parser().format_help()
        workflow = (REPO_ROOT / ".github" / "workflows" / "aippocampus-ci.yml").read_text(
            encoding="utf-8",
        )

        self.assertIn("benchmark-smoke", help_text)
        self.assertIn("--benchmark-suite-profile", help_text)
        self.assertIn(
            "--tier benchmark-smoke --benchmark-suite-profile public-fast",
            workflow,
        )
        self.assertNotIn("python benchmarks/aippocampus/benchmark_suite.py", workflow)

    def test_benchmark_extra_is_stable_contributor_install_target(self) -> None:
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("optional-dependencies", pyproject["project"])
        self.assertIn("benchmark", pyproject["project"]["optional-dependencies"])
        self.assertEqual(pyproject["project"]["optional-dependencies"]["benchmark"], [])


if __name__ == "__main__":
    unittest.main()
