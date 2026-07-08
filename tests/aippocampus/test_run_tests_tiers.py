from __future__ import annotations

import ast
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

from tests.aippocampus.import_path_helpers import import_tool_root_module

run_tests = import_tool_root_module("run_tests")
test_tier_manifest = import_tool_root_module("test_tier_manifest")

BROAD_PR_PRIMARY_TIERS = test_tier_manifest.BROAD_PR_PRIMARY_TIERS
PR_PRIMARY_TIERS = test_tier_manifest.PR_PRIMARY_TIERS
PRIMARY_TIER_ORDER = test_tier_manifest.PRIMARY_TIER_ORDER

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
    "tests.aippocampus.test_prompt_hook_anti_nag_behavior",
}

PR_SIZE_DRIFT_SLACK = 10
TESTS_ROOT = REPO_ROOT / "tests" / "aippocampus"

def _raw_sleep_sites(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sites: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "sleep"
            and isinstance(func.value, ast.Name)
            and func.value.id == "time"
        ):
            sites.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
        elif isinstance(func, ast.Name) and func.id == "sleep":
            sites.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    return sites

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
        self.assertEqual(report["tier_aliases"], {})
        self.assertEqual(report["tiers"]["quick"]["budget"]["module_count_target"], 50)
        self.assertEqual(report["tiers"]["quick"]["budget"]["test_count_target"], 330)
        self.assertEqual(report["tiers"]["quick"]["budget"]["module_count_status"], "within_target")
        self.assertEqual(report["tiers"]["quick"]["budget"]["test_count_status"], "within_target")
        self.assertEqual(report["tiers"]["pr"]["budget"]["module_count_target"], 86)
        self.assertEqual(report["tiers"]["pr"]["budget"]["test_count_target"], 500)
        self.assertEqual(report["tiers"]["pr"]["budget"]["budget_outcome"], "within_target")
        self.assertEqual(report["tiers"]["pr"]["budget"]["target_updated_at"], "2026-07-08")
        self.assertIn("replacement lanes", report["tiers"]["pr"]["budget"]["replacement_lane_note"])
        self.assertIsNone(report["tiers"]["pr"]["budget"]["recommended_action"])
        self.assertTrue(
            any(
                "Use canonical tiers directly" in limitation
                for limitation in report["known_limitations"]
            ),
        )

    def test_count_budget_surfaces_actionable_drift_without_hard_failing(self) -> None:
        budget = run_tests.count_budget_for_tier(
            "pr",
            module_count=87,
            test_count=501,
        )

        self.assertIsNotNone(budget)
        assert budget is not None
        self.assertEqual(budget["module_count_status"], "over_target")
        self.assertEqual(budget["test_count_status"], "over_target")
        self.assertEqual(budget["budget_outcome"], "over_target_action_recommended")
        self.assertEqual(
            budget["recommended_action"]["id"],
            "review_pr_tier_budget_drift",
        )
        self.assertIn("soft drift", budget["recommended_action"]["why"])

    def test_broad_suite_growth_review_is_non_gating_telemetry(self) -> None:
        review = run_tests.suite_growth_review_for_tier(
            "broad-pr",
            module_count=381,
            test_count=3401,
            top_modules=[
                {"module": "tests.aippocampus.test_docs_health", "test_count": 85}
            ],
        )

        self.assertIsNotNone(review)
        assert review is not None
        self.assertEqual(review["kind"], "non_gating_suite_growth_review")
        self.assertEqual(review["status"], "review_recommended")
        self.assertEqual(review["recommended_action"]["mutation_risk"], "planning_only")
        self.assertEqual(review["review_decision_date"], "2026-07-08")
        self.assertIn("CI/pre-merge", review["review_rationale"])
        self.assertIn("must not make broad coverage", review["recommended_action"]["why"])
        self.assertIn("Non-gating", review["boundary"])
        self.assertIsNone(
            run_tests.suite_growth_review_for_tier(
                "pr",
                module_count=113,
                test_count=913,
                top_modules=[],
            )
        )

    def test_report_json_cli_prints_compact_report_without_running_tests(self) -> None:
        report = {
            "kind": "aippocampus_test_tier_report",
            "schema_version": 2,
            "runner_version": "test-runner",
            "generated_at": "2026-06-29T15:00:00Z",
            "tier_definitions": {"pr": "full catalog detail"},
            "tier_aliases": {},
            "tier_shrink_replacement_lanes": {},
            "tiers": {
                "pr": {
                    "module_count": 1,
                    "test_count": 2,
                    "budget": None,
                    "growth_review": None,
                    "benchmark_shaped": {"evidence_module_count": 0},
                    "top_modules": [{"module": "tests.fake", "test_count": 2}],
                }
            },
            "timing_artifacts": [],
            "known_limitations": ["full detail only"],
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
        self.assertEqual(payload["kind"], "aippocampus_test_tier_report_compact")
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["warning_count"], 0)
        self.assertEqual(payload["tiers"]["pr"]["module_count"], 1)
        self.assertIn("--detail full", payload["detail_command"])
        encoded = json.dumps(payload)
        self.assertNotIn("tier_definitions", encoded)
        self.assertNotIn("tier_aliases", encoded)
        self.assertNotIn("tier_shrink_replacement_lanes", encoded)
        self.assertNotIn("top_modules", encoded)
        self.assertNotIn("known_limitations", encoded)
        run_modules.assert_not_called()

    def test_report_json_cli_full_detail_preserves_catalog(self) -> None:
        report = {
            "kind": "aippocampus_test_tier_report",
            "tier_definitions": {"pr": "full catalog detail"},
            "tier_aliases": {},
            "tier_shrink_replacement_lanes": {"tests.full": {"replacement_lane": "pr-core"}},
            "tiers": {
                "pr": {
                    "module_count": 1,
                    "test_count": 2,
                    "top_modules": [{"module": "tests.fake", "test_count": 2}],
                }
            },
            "timing_artifacts": [{"status": "current"}],
            "known_limitations": ["operator catalog detail"],
        }

        with (
            io.StringIO() as stdout,
            contextlib.redirect_stdout(stdout),
            mock.patch.object(run_tests, "ensure_usable_tempdir", return_value=Path(".")),
            mock.patch.object(run_tests, "build_tier_report", return_value=report),
            mock.patch.object(run_tests, "run_modules") as run_modules,
        ):
            exit_code = run_tests.main(["--report-json", "--detail", "full"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload, report)
        run_modules.assert_not_called()

    def test_compact_tier_report_surfaces_budget_warning_action(self) -> None:
        report = {
            "runner_version": "test-runner",
            "generated_at": "2026-06-29T15:00:00Z",
            "tiers": {
                "pr": {
                    "module_count": 87,
                    "test_count": 501,
                    "budget": run_tests.count_budget_for_tier(
                        "pr",
                        module_count=87,
                        test_count=501,
                    ),
                    "growth_review": None,
                    "benchmark_shaped": {"evidence_module_count": 0},
                    "top_modules": [
                        {"module": "tests.aippocampus.test_heavy", "test_count": 100}
                    ],
                }
            },
            "timing_artifacts": [],
        }

        payload = run_tests.compact_tier_report(report)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "advisory_action_recommended")
        self.assertEqual(payload["warning_count"], 1)
        self.assertEqual(payload["first_warning"]["code"], "tier_count_budget_drift")
        self.assertEqual(
            payload["first_warning"]["recommended_action"]["id"],
            "review_pr_tier_budget_drift",
        )
        self.assertNotIn("top_modules", json.dumps(payload))

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
        self.assertEqual(report["compact_summary"]["status"], "advisory_over_target")
        self.assertEqual(
            report["compact_summary"]["top_slow_modules"][0]["module"],
            "tests.aippocampus.test_alpha",
        )
        self.assertIn("advisory", report["compact_summary"]["policy"])

    def test_timings_report_includes_manifest_freshness_metadata(self) -> None:
        rows = [
            {
                "module": "tests.aippocampus.test_alpha",
                "primary_tier": "pr",
                "test_count": 2,
                "duration_seconds": 0.5,
                "ok": True,
            },
            {
                "module": "tests.aippocampus.test_beta",
                "primary_tier": "pr",
                "test_count": 3,
                "duration_seconds": 0.75,
                "ok": True,
            },
        ]

        with mock.patch.object(run_tests, "_utc_timestamp", return_value="2026-06-21T12:00:00Z"):
            report = run_tests.build_timings_report(
                selected_tier="pr",
                rows=rows,
                shard=None,
            )

        manifest = report["manifest"]
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["runner_version"], run_tests.RUNNER_VERSION)
        self.assertEqual(report["generated_at"], "2026-06-21T12:00:00Z")
        self.assertEqual(manifest["normalized_tier"], "pr")
        self.assertEqual(manifest["module_count"], 2)
        self.assertEqual(manifest["test_count"], 5)
        self.assertEqual(len(manifest["module_list_hash"]), 64)
        self.assertEqual(len(manifest["manifest_fingerprint"]), 64)

    def test_timing_artifact_freshness_detects_stale_module_set(self) -> None:
        current = run_tests.build_module_set_manifest(
            selected_tier="pr",
            rows=[
                {"module": "tests.aippocampus.test_alpha", "test_count": 2},
                {"module": "tests.aippocampus.test_beta", "test_count": 3},
            ],
        )
        legacy_artifact = {
            "kind": "aippocampus_test_module_timings",
            "schema_version": 1,
            "selected_tier": "pr",
            "module_count": 1,
            "test_count": 2,
            "shard": None,
            "modules": [
                {
                    "module": "tests.aippocampus.test_alpha",
                    "primary_tier": "pr",
                    "test_count": 2,
                    "duration_seconds": 0.1,
                    "ok": True,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timings.json"
            path.write_text(json.dumps(legacy_artifact), encoding="utf-8")

            freshness = run_tests.assess_timing_artifact_freshness(
                path,
                current_manifests={"pr": current},
            )

        self.assertEqual(freshness["status"], "stale")
        self.assertEqual(freshness["selected_tier"], "pr")
        self.assertIn("module_count", freshness["mismatches"])
        self.assertIn("module_list_hash", freshness["mismatches"])

    def test_timing_artifact_without_module_set_is_incomparable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timings.json"
            path.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_test_module_timings",
                        "schema_version": 1,
                        "selected_tier": "pr",
                        "modules": [],
                    }
                ),
                encoding="utf-8",
            )

            freshness = run_tests.assess_timing_artifact_freshness(
                path,
                current_manifests={
                    "pr": run_tests.build_module_set_manifest(
                        selected_tier="pr",
                        rows=[{"module": "tests.aippocampus.test_alpha", "test_count": 1}],
                    )
                },
            )

        self.assertEqual(freshness["status"], "incomparable")
        self.assertIn("module set", freshness["reason"])

    def test_tier_report_can_include_timing_artifact_freshness(self) -> None:
        rows = [
            {
                "module": "tests.aippocampus.test_alpha",
                "primary_tier": "pr",
                "test_count": 2,
                "duration_seconds": 0.25,
                "ok": True,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timings.json"
            path.write_text(
                json.dumps(
                    run_tests.build_timings_report(
                        selected_tier="pr",
                        rows=rows,
                        shard=None,
                    )
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(
                    run_tests,
                    "modules_for_tier",
                    side_effect=lambda tier: ["tests.aippocampus.test_alpha"],
                ),
                mock.patch.object(
                    run_tests,
                    "count_tests_for_module",
                    side_effect=lambda module: 2,
                ),
            ):
                report = run_tests.build_tier_report(
                    tiers=("pr",),
                    timing_artifact_paths=(path,),
                )

        self.assertEqual(report["timing_artifacts"][0]["status"], "current")
        self.assertEqual(report["timing_artifacts"][0]["path"], str(path))

    def test_default_report_does_not_auto_discover_stale_local_timing_artifact(self) -> None:
        legacy_path = (
            run_tests.REPO_ROOT
            / "benchmark_corpus"
            / "reports"
            / "local-pr-tier-timings.json"
        )

        self.assertNotIn(legacy_path, run_tests.DEFAULT_TIMING_ARTIFACTS)
        self.assertEqual(run_tests.default_timing_artifact_paths(), ())

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
            stdout=(
                '{"ok": true, "status": "quality_gate_passed", "elapsed_ms": 12.5, '
                '"outcome_digest": {"counts": {"public_quality_promoted": 1, '
                '"diagnostic_only": 0, "adoption_blocked": 0, "owner_action": 2}}}'
            ),
            stderr="",
        )

        with (
            io.StringIO() as stdout,
            contextlib.redirect_stdout(stdout),
            mock.patch.object(run_tests.subprocess, "run", return_value=completed) as run,
        ):
            ok = run_tests.run_benchmark_suite_profile("public-fast")
            output = stdout.getvalue()

        self.assertTrue(ok)
        self.assertIn("benchmark outcome digest", output)
        self.assertIn("promoted=1", output)
        self.assertIn("owner_action=2", output)
        command = run.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertIn("benchmark_suite.py", command[1])
        self.assertEqual(command[-3:], ["--profile", "public-fast", "--json"])

    def test_tempdir_preflight_uses_fallback_when_default_temp_is_unusable(self) -> None:
        calls: list[Path] = []

        def fake_probe(path: Path) -> None:
            calls.append(path)
            if path.name == "default-temp":
                raise OSError("delete denied")

        with tempfile.TemporaryDirectory() as tmp:
            default_temp = Path(tmp) / "default-temp"
            fallback = Path(tmp) / "runner-temp"
            fallback_identity = fallback.resolve()
            previous_tempdir = getattr(run_tests.tempfile, "tempdir", None)
            with (
                mock.patch.object(run_tests, "_probe_tempdir", side_effect=fake_probe),
                mock.patch.object(
                    run_tests,
                    "_tempdir_parent_candidates",
                    return_value=[("env:TEMP", default_temp)],
                ),
                mock.patch.object(run_tests, "FALLBACK_TEST_TMPDIR", fallback),
                mock.patch.dict(os.environ, {}, clear=False),
            ):
                try:
                    selected = run_tests.ensure_usable_tempdir()
                    selected_env = {name: os.environ[name] for name in run_tests.TEMP_ENV_NAMES}
                finally:
                    run_tests.tempfile.tempdir = previous_tempdir

            self.assertEqual(selected, fallback_identity)
            self.assertEqual(calls, [default_temp, fallback_identity])
            for name in run_tests.TEMP_ENV_NAMES:
                self.assertEqual(selected_env[name], str(fallback_identity))

    def test_tempdir_preflight_never_uses_implicit_cwd_probe_when_candidates_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_repo_root = Path(tmp) / "repo"
            fake_repo_root.mkdir()
            leaked = fake_repo_root / "cwd-probe-leak"
            default_temp = Path(tmp) / "default-temp"
            fallback = Path(tmp) / "fallback-temp"
            previous_tempdir = getattr(run_tests.tempfile, "tempdir", None)

            def fake_tempdir(*, prefix: str, dir: str | None = None) -> object:
                if dir is None:
                    leaked.write_text("leaked", encoding="utf-8")
                raise OSError("temp denied")

            with (
                mock.patch.object(run_tests.tempfile, "TemporaryDirectory", side_effect=fake_tempdir),
                mock.patch.object(
                    run_tests,
                    "_tempdir_parent_candidates",
                    return_value=[("env:TEMP", default_temp)],
                ),
                mock.patch.object(run_tests, "FALLBACK_TEST_TMPDIR", fallback),
            ):
                try:
                    with self.assertRaises(RuntimeError):
                        run_tests.ensure_usable_tempdir()
                finally:
                    run_tests.tempfile.tempdir = previous_tempdir

            self.assertFalse(leaked.exists())

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

    def test_tests_do_not_use_raw_sleep_outside_timing_helper(self) -> None:
        offenders: list[str] = []
        for path in sorted(TESTS_ROOT.glob("test_*.py")):
            offenders.extend(_raw_sleep_sites(path))

        self.assertEqual(
            offenders,
            [],
            "Use timing_fixtures.host_timeout_sleep for host-time smokes, "
            "or fake time / advance_file_mtime for deterministic cache tests.",
        )

    def test_sleep_helper_is_not_a_test_tier_module(self) -> None:
        self.assertNotIn(
            "tests.aippocampus.timing_fixtures",
            run_tests.TEST_MODULE_CLASSIFICATIONS,
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
        # Keep this as a drift guard, not an off-by-one blocker when small
        # foreground contract tests enter the PR lane.
        self.assertLessEqual(len(pr) * 3, len(broad_pr) + PR_SIZE_DRIFT_SLACK)
        self.assertTrue(PR_CRITICAL_MODULES.isdisjoint(quick))
        self.assertLessEqual(PR_CRITICAL_MODULES, pr)

    def test_benchmark_shaped_fast_lane_modules_have_explicit_categories(self) -> None:
        report = run_tests.build_tier_report(tiers=("quick", "pr", "benchmark"))

        quick_shape = report["tiers"]["quick"]["benchmark_shaped"]
        pr_shape = report["tiers"]["pr"]["benchmark_shaped"]
        benchmark_shape = report["tiers"]["benchmark"]["benchmark_shaped"]

        self.assertEqual(quick_shape["fast_lane_module_count"], 0)
        self.assertEqual(pr_shape["fast_lane_module_count"], 0)
        self.assertEqual(quick_shape["evidence_module_count"], 0)
        self.assertEqual(pr_shape["evidence_module_count"], 0)
        self.assertGreater(benchmark_shape["evidence_module_count"], 0)
        replacement_lanes = report["tier_shrink_replacement_lanes"]
        self.assertIn(
            "tests.aippocampus.test_benchmark_entrypoints",
            replacement_lanes,
        )
        self.assertIn(
            "benchmark-smoke",
            replacement_lanes["tests.aippocampus.test_benchmark_entrypoints"][
                "replacement_lane"
            ],
        )

    def test_cli_recovery_card_catalog_has_pr_core_replacement_lane(self) -> None:
        report = run_tests.build_tier_report(tiers=("pr", "broad-pr"))
        replacement_lanes = report["tier_shrink_replacement_lanes"]

        self.assertIn(
            "tests.aippocampus.test_cli_recovery_cards_core",
            run_tests.modules_for_tier("pr"),
        )
        self.assertNotIn(
            "tests.aippocampus.test_cli_recovery_cards",
            run_tests.modules_for_tier("pr"),
        )
        self.assertIn(
            "tests.aippocampus.test_cli_recovery_cards",
            run_tests.modules_for_tier("broad-pr"),
        )
        self.assertEqual(
            replacement_lanes["tests.aippocampus.test_cli_recovery_cards"][
                "primary_tier"
            ],
            "broad",
        )
        self.assertIn(
            "test_cli_recovery_cards_core",
            replacement_lanes["tests.aippocampus.test_cli_recovery_cards"][
                "replacement_lane"
            ],
        )

    def test_future_benchmark_shaped_fast_lane_module_requires_rationale(self) -> None:
        with self.assertRaisesRegex(ValueError, "benchmark-shaped fast-lane"):
            run_tests.benchmark_shaped_tier_summary(
                "quick",
                ["tests.aippocampus.test_benchmark_new_fast_guard"],
            )

    def test_legacy_tier_aliases_are_not_exposed(self) -> None:
        self.assertEqual(run_tests.TIER_ALIASES, {})
        for tier in ("fast", "ci", "deterministic"):
            with self.assertRaisesRegex(ValueError, "unknown test tier"):
                run_tests.modules_for_tier(tier)
            self.assertNotIn(tier, run_tests.TEST_TIERS)

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
        self.assertIn("pull-requests: read", workflow)
        self.assertIn("PR test tier with canonical coverage", workflow)
        self.assertIn("PR_NUMBER: ${{ github.event.pull_request.number }}", workflow)
        self.assertIn('--pr "$PR_NUMBER"', workflow)
        self.assertNotIn("github.event.pull_request.body", workflow)
        self.assertNotIn("--body-env PR_BODY", workflow)
        self.assertIn("Python 3.13 quick compatibility tier", workflow)
        self.assertIn("--tier quick", workflow)
        self.assertIn(
            "--tier benchmark-smoke --benchmark-suite-profile public-fast",
            workflow,
        )
        self.assertIn("coverage-pr-canonical", workflow)
        self.assertNotIn("coverage-${{ matrix.python-version }}", workflow)
        self.assertNotIn("python benchmarks/aippocampus/benchmark_suite.py", workflow)

    def test_quick_and_pr_count_budgets_report_drift_without_hard_gating(self) -> None:
        for tier in ("quick", "pr"):
            modules = run_tests.modules_for_tier(tier)
            test_count = sum(run_tests.count_tests_for_module(module) for module in modules)
            budget = run_tests.count_budget_for_tier(
                tier,
                module_count=len(modules),
                test_count=test_count,
            )

            expected_module_status = (
                "within_target"
                if len(modules) <= budget["module_count_target"]
                else "over_target"
            )
            expected_test_status = (
                "within_target"
                if test_count <= budget["test_count_target"]
                else "over_target"
            )
            self.assertEqual(
                budget["module_count_status"],
                expected_module_status,
            )
            self.assertEqual(
                budget["test_count_status"],
                expected_test_status,
            )
            self.assertIn("target", budget["note"])
            self.assertTrue(
                "not" in budget["note"].casefold()
                or "broad" in budget["note"].casefold()
            )

    def test_benchmark_extra_is_stable_contributor_install_target(self) -> None:
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("optional-dependencies", pyproject["project"])
        self.assertIn("benchmark", pyproject["project"]["optional-dependencies"])
        self.assertEqual(pyproject["project"]["optional-dependencies"]["benchmark"], [])

if __name__ == "__main__":
    unittest.main()
