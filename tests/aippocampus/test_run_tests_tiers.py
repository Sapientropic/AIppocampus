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
from test_tier_manifest import (  # noqa: E402
    BROAD_PR_PRIMARY_TIERS,
    PR_PRIMARY_TIERS,
    PRIMARY_TIER_ORDER,
)

QUICK_FORBIDDEN_TAGS = {
    "browser",
    "cross_agent",
    "host",
    "install",
    "integration",
    "mcp",
    "optional_dependency",
    "provider",
    "release",
    "slow",
    "smoke",
    "sync",
}

BENCHMARK_SMOKE_REVIEWED_NON_BENCHMARK_MODULES = {
    # The E2E50 seed scanner is a public-safe deterministic benchmark support
    # guard, not a completed benchmark mirror. The case-pack scorer is a real
    # benchmark mirror module and is therefore covered by the benchmark subset
    # assertion below instead of this exception list. Keep exceptions explicit
    # so benchmark smoke does not become a catch-all lane for unrelated tests.
    "tests.aippocampus.test_e2e50_seed_candidates",
}

PR_CRITICAL_MODULES = {
    "tests.aippocampus.test_benchmark_graph_extraction_boundary",
}


class RunTestsTierTests(unittest.TestCase):
    def test_main_preflights_tempdir_before_loading_tests(self) -> None:
        events: list[str] = []

        with (
            mock.patch.object(
                run_tests,
                "runtime_import_preflight_issue",
                side_effect=lambda: events.append("runtime") or None,
                create=True,
            ),
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
            exit_code = run_tests.main(["--tier", "pr"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(events, ["runtime", "tempdir", "run"])

    def test_runtime_import_preflight_reports_hidden_editable_pth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site_packages = Path(tmp) / "site-packages"
            site_packages.mkdir()
            editable_pth = site_packages / "__editable__.aippocampus-0.2.0.pth"
            editable_pth.write_text(
                str(run_tests.REPO_ROOT / "skills" / "aippocampus" / "scripts") + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(run_tests.importlib.util, "find_spec", return_value=None),
                mock.patch.object(run_tests.site, "getsitepackages", return_value=[str(site_packages)]),
                mock.patch.object(run_tests, "_path_has_hidden_flag", return_value=True),
            ):
                issue = run_tests.runtime_import_preflight_issue()

        self.assertIsNotNone(issue)
        self.assertIn("aippocampus_runtime", issue)
        self.assertIn("hidden .pth", issue)
        self.assertIn("chflags -R nohidden .venv", issue)

    def test_runtime_source_path_bypasses_hidden_editable_pth_for_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "runtime-source"
            package_root = source_root / "aippocampus_runtime_probe"
            package_root.mkdir(parents=True)
            (package_root / "__init__.py").write_text("", encoding="utf-8")

            site_packages = Path(tmp) / "site-packages"
            site_packages.mkdir()
            editable_pth = site_packages / "__editable__.aippocampus-0.2.0.pth"
            editable_pth.write_text(str(source_root) + "\n", encoding="utf-8")

            previous_sys_path = list(sys.path)
            previous_pythonpath = os.environ.get("PYTHONPATH")
            try:
                sys.path[:] = [entry for entry in sys.path if entry != str(source_root)]
                os.environ.pop("PYTHONPATH", None)
                with (
                    mock.patch.object(run_tests, "RUNTIME_PACKAGE", "aippocampus_runtime_probe"),
                    mock.patch.object(run_tests, "RUNTIME_SOURCE_ROOT", source_root),
                    mock.patch.object(run_tests.site, "getsitepackages", return_value=[str(site_packages)]),
                    mock.patch.object(run_tests, "_path_has_hidden_flag", return_value=True),
                ):
                    run_tests.ensure_runtime_source_path()
                    issue = run_tests.runtime_import_preflight_issue()

                self.assertIsNone(issue)
                self.assertEqual(sys.path[0], str(source_root))
                self.assertEqual(os.environ["PYTHONPATH"].split(os.pathsep)[0], str(source_root))
            finally:
                sys.path[:] = previous_sys_path
                if previous_pythonpath is None:
                    os.environ.pop("PYTHONPATH", None)
                else:
                    os.environ["PYTHONPATH"] = previous_pythonpath

    def test_main_stops_before_running_tests_when_runtime_import_preflight_fails(self) -> None:
        with (
            io.StringIO() as stderr,
            contextlib.redirect_stderr(stderr),
            mock.patch.object(
                run_tests,
                "runtime_import_preflight_issue",
                return_value="runtime import diagnostic",
                create=True,
            ),
            mock.patch.object(run_tests, "ensure_usable_tempdir") as ensure_tempdir,
            mock.patch.object(run_tests, "run_modules") as run_modules,
        ):
            exit_code = run_tests.main(["--tier", "pr"])
            error_text = stderr.getvalue()

        self.assertEqual(exit_code, 2)
        self.assertIn("runtime import diagnostic", error_text)
        ensure_tempdir.assert_not_called()
        run_modules.assert_not_called()

    def test_main_can_run_benchmark_suite_profile_before_selected_tier(self) -> None:
        events: list[str] = []

        with (
            mock.patch.object(run_tests, "runtime_import_preflight_issue", return_value=None, create=True),
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
        counts = {
            "tests.aippocampus.test_alpha": 3,
            "tests.aippocampus.test_beta": 7,
            "tests.aippocampus.test_benchmark_gamma": 11,
            "tests.aippocampus.test_onboard_codex": 13,
        }

        with (
            mock.patch.object(
                run_tests,
                "modules_for_tier",
                side_effect=lambda tier: {
                    "quick": ["tests.aippocampus.test_alpha"],
                    "pr": ["tests.aippocampus.test_alpha", "tests.aippocampus.test_beta"],
                    "benchmark": ["tests.aippocampus.test_benchmark_gamma"],
                    "full": [
                        "tests.aippocampus.test_alpha",
                        "tests.aippocampus.test_beta",
                        "tests.aippocampus.test_benchmark_gamma",
                        "tests.aippocampus.test_onboard_codex",
                    ],
                }.get(tier, []),
            ),
            mock.patch.object(
                run_tests,
                "count_tests_for_module",
                side_effect=lambda module: counts[module],
            ),
        ):
            report = run_tests.build_tier_report(tiers=("quick", "pr", "benchmark", "full"))

        self.assertEqual(report["kind"], "aippocampus_test_tier_report")
        self.assertEqual(report["tiers"]["full"]["module_count"], 4)
        self.assertEqual(report["tiers"]["full"]["test_count"], 34)
        self.assertEqual(report["tiers"]["pr"]["module_count"], 2)
        self.assertEqual(report["tiers"]["pr"]["test_count"], 10)
        self.assertEqual(
            report["tiers"]["pr"]["top_modules"],
            [
                {"module": "tests.aippocampus.test_beta", "test_count": 7},
                {"module": "tests.aippocampus.test_alpha", "test_count": 3},
            ],
        )
        self.assertEqual(report["tier_aliases"]["fast"], "pr")
        self.assertEqual(report["tiers"]["quick"]["budget"]["module_count_target"], 46)
        self.assertEqual(report["tiers"]["quick"]["budget"]["test_count_target"], 330)
        self.assertEqual(report["tiers"]["quick"]["budget"]["module_count_status"], "within_target")
        self.assertEqual(report["tiers"]["quick"]["budget"]["test_count_status"], "within_target")
        self.assertEqual(report["tiers"]["pr"]["budget"]["module_count_target"], 70)
        self.assertEqual(report["tiers"]["pr"]["budget"]["test_count_target"], 500)
        self.assertTrue(
            any(
                "broad-pr aliases" in limitation
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

    def test_shard_modules_is_stable_by_sorted_module_name(self) -> None:
        modules = [
            "tests.aippocampus.test_zulu",
            "tests.aippocampus.test_alpha",
            "tests.aippocampus.test_mango",
            "tests.aippocampus.test_beta",
        ]

        self.assertEqual(
            run_tests.shard_modules(modules, shard_index=0, shard_total=2),
            [
                "tests.aippocampus.test_alpha",
                "tests.aippocampus.test_mango",
            ],
        )
        self.assertEqual(
            run_tests.shard_modules(modules, shard_index=1, shard_total=2),
            [
                "tests.aippocampus.test_beta",
                "tests.aippocampus.test_zulu",
            ],
        )

    def test_main_applies_shard_and_writes_timings_json(self) -> None:
        modules = [
            "tests.aippocampus.test_zulu",
            "tests.aippocampus.test_alpha",
            "tests.aippocampus.test_mango",
            "tests.aippocampus.test_beta",
        ]
        timing_rows = [
            {
                "module": "tests.aippocampus.test_beta",
                "primary_tier": "pr",
                "test_count": 2,
                "duration_seconds": 0.25,
                "ok": True,
            },
            {
                "module": "tests.aippocampus.test_zulu",
                "primary_tier": "pr",
                "test_count": 3,
                "duration_seconds": 0.5,
                "ok": True,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            timings_path = Path(tmp) / "timings.json"
            with (
                mock.patch.object(
                    run_tests,
                    "runtime_import_preflight_issue",
                    return_value=None,
                    create=True,
                ),
                mock.patch.object(run_tests, "ensure_usable_tempdir", return_value=Path(".")),
                mock.patch.object(run_tests, "modules_for_tier", return_value=modules),
                mock.patch.object(
                    run_tests,
                    "run_modules_with_timings",
                    return_value=(True, timing_rows),
                ) as run_with_timings,
                mock.patch.object(run_tests, "run_modules") as run_modules,
            ):
                exit_code = run_tests.main(
                    [
                        "--tier",
                        "pr",
                        "--shard-index",
                        "1",
                        "--shard-total",
                        "2",
                        "--timings-json",
                        str(timings_path),
                    ],
                )
            payload = json.loads(timings_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        run_with_timings.assert_called_once_with(
            ["tests.aippocampus.test_beta", "tests.aippocampus.test_zulu"],
            verbosity=1,
        )
        run_modules.assert_not_called()
        self.assertEqual(payload["kind"], "aippocampus_test_module_timings")
        self.assertEqual(payload["selected_tier"], "pr")
        self.assertEqual(payload["module_count"], 2)
        self.assertEqual(payload["test_count"], 5)
        self.assertEqual(payload["shard"], {"index": 1, "total": 2})
        self.assertEqual(payload["modules"], timing_rows)
        self.assertEqual(payload["budget"]["elapsed_seconds_target"], 180.0)

    def test_quick_timings_report_exposes_inner_loop_drift_without_failing(self) -> None:
        rows = [
            {
                "module": "tests.aippocampus.test_alpha",
                "primary_tier": "quick",
                "test_count": 2,
                "duration_seconds": 20.0,
                "ok": True,
            },
            {
                "module": "tests.aippocampus.test_beta",
                "primary_tier": "quick",
                "test_count": 3,
                "duration_seconds": 11.0,
                "ok": True,
            },
        ]

        report = run_tests.build_timings_report(selected_tier="quick", rows=rows, shard=None)

        self.assertEqual(report["elapsed_seconds"], 31.0)
        self.assertEqual(report["budget"]["elapsed_seconds_target"], 30.0)
        self.assertEqual(report["budget"]["elapsed_seconds_status"], "over_target")
        self.assertIn("drift", report["budget"]["note"])

    def test_invalid_or_empty_shards_fail_before_running_tests(self) -> None:
        with (
            io.StringIO() as stderr,
            contextlib.redirect_stderr(stderr),
            mock.patch.object(run_tests, "run_modules") as run_modules,
        ):
            exit_code = run_tests.main(
                ["--tier", "pr", "--shard-index", "0", "--shard-total", "0"],
            )
            error_text = stderr.getvalue()

        self.assertEqual(exit_code, 2)
        self.assertIn("shard-total must be greater than zero", error_text)
        run_modules.assert_not_called()

        with (
            io.StringIO() as stderr,
            contextlib.redirect_stderr(stderr),
            mock.patch.object(run_tests, "ensure_usable_tempdir"),
            mock.patch.object(run_tests, "modules_for_tier", return_value=["tests.fake"]),
            mock.patch.object(run_tests, "run_modules") as run_modules,
        ):
            exit_code = run_tests.main(
                ["--tier", "pr", "--shard-index", "1", "--shard-total", "2"],
            )
            error_text = stderr.getvalue()

        self.assertEqual(exit_code, 2)
        self.assertIn("no tests selected for tier: pr", error_text)
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

    def test_manifest_matches_real_test_modules(self) -> None:
        discovered = set(run_tests.discover_modules())

        self.assertEqual(
            sorted(discovered - run_tests.TEST_MODULE_CLASSIFICATIONS.keys()),
            [],
        )
        self.assertEqual(
            sorted(run_tests.TEST_MODULE_CLASSIFICATIONS.keys() - discovered),
            [],
        )

    def test_new_test_modules_fail_until_classified(self) -> None:
        discovered = run_tests.discover_modules() + ["tests.aippocampus.test_new_surface"]

        with (
            mock.patch.object(run_tests, "discover_modules", return_value=discovered),
            self.assertRaisesRegex(ValueError, "unclassified test modules"),
        ):
            run_tests.modules_for_tier("pr")

    def test_pr_is_fast_local_gate_and_broad_pr_preserves_old_surface(self) -> None:
        quick = set(run_tests.modules_for_tier("quick"))
        pr = set(run_tests.modules_for_tier("pr"))
        broad_pr = set(run_tests.modules_for_tier("broad-pr"))
        unexpected = [
            module
            for module in sorted(quick)
            if set(run_tests.TEST_MODULE_CLASSIFICATIONS[module].tags) & QUICK_FORBIDDEN_TAGS
        ]

        self.assertEqual(unexpected, [])
        self.assertLess(quick, pr)
        self.assertLess(pr, broad_pr)
        self.assertLess(len(pr) * 3, len(broad_pr))
        self.assertTrue(PR_CRITICAL_MODULES.isdisjoint(quick))
        self.assertLessEqual(PR_CRITICAL_MODULES, pr)

    def test_fast_is_compatibility_alias_for_pr(self) -> None:
        self.assertEqual(run_tests.modules_for_tier("fast"), run_tests.modules_for_tier("pr"))

    def test_ci_and_deterministic_aliases_keep_broad_pr_coverage(self) -> None:
        self.assertEqual(run_tests.modules_for_tier("ci"), run_tests.modules_for_tier("broad-pr"))
        self.assertEqual(
            run_tests.modules_for_tier("deterministic"),
            run_tests.modules_for_tier("broad-pr"),
        )

    def test_tiers_partition_the_discovered_test_modules(self) -> None:
        discovered = set(run_tests.discover_modules())
        primary_sets = {
            tier: {
                module
                for module, classification in run_tests.TEST_MODULE_CLASSIFICATIONS.items()
                if classification.primary_tier == tier
            }
            for tier in PRIMARY_TIER_ORDER
        }

        for left in PRIMARY_TIER_ORDER:
            for right in PRIMARY_TIER_ORDER:
                if left == right:
                    continue
                self.assertEqual(primary_sets[left] & primary_sets[right], set())
        self.assertEqual(set().union(*primary_sets.values()), discovered)
        self.assertEqual(
            set(run_tests.modules_for_tier("pr")),
            set().union(*(primary_sets[tier] for tier in PR_PRIMARY_TIERS)),
        )
        self.assertEqual(
            set(run_tests.modules_for_tier("broad-pr")),
            set().union(*(primary_sets[tier] for tier in BROAD_PR_PRIMARY_TIERS)),
        )

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

        self.assertIn("quick", help_text)
        self.assertIn("pr", help_text)
        self.assertIn("broad-pr", help_text)
        self.assertIn("benchmark-smoke", help_text)
        self.assertIn("--benchmark-suite-profile", help_text)
        self.assertIn("--timings-json", help_text)
        self.assertIn("target of about", help_text.lower())
        self.assertIn("--shard-index", help_text)
        self.assertIn("--tier pr", workflow)
        self.assertIn("--tier broad-pr", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("PR test tier with canonical coverage", workflow)
        self.assertIn("Python 3.13 quick compatibility tier", workflow)
        self.assertIn("--tier quick", workflow)
        self.assertIn(
            "--tier benchmark-smoke --benchmark-suite-profile public-fast",
            workflow,
        )
        self.assertIn("coverage-pr-canonical", workflow)
        self.assertNotIn("coverage-${{ matrix.python-version }}", workflow)
        self.assertNotIn("python benchmarks/aippocampus/benchmark_suite.py", workflow)

    def test_benchmark_extra_is_stable_contributor_install_target(self) -> None:
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("optional-dependencies", pyproject["project"])
        self.assertIn("benchmark", pyproject["project"]["optional-dependencies"])
        self.assertEqual(pyproject["project"]["optional-dependencies"]["benchmark"], [])


if __name__ == "__main__":
    unittest.main()
