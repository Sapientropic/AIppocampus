from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = REPO_ROOT / "tests" / "aippocampus"
FALLBACK_TEST_TMPDIR = REPO_ROOT / ".aippocampus" / "test-tmp"
TEMP_ENV_NAMES = ("TMPDIR", "TEMP", "TMP")
TEMP_PROBE_PREFIX = "aippocampus-test-runner-"

SLOW_MODULES = {
    "tests.aippocampus.test_aippocampus_prompt_hook",
    "tests.aippocampus.test_dream_real_history_eval",
    "tests.aippocampus.test_life_wide_registry_smoke",
    "tests.aippocampus.test_object_storage_sync",
    "tests.aippocampus.test_onboard_codex",
    "tests.aippocampus.test_plugin_distribution",
    "tests.aippocampus.test_semantic_scope_real_history_smoke",
    "tests.aippocampus.test_stage_0_5_smoke",
}

BENCHMARK_SMOKE_MODULES = {
    # #279 support guard: this validates public-safe candidate seed discovery
    # only. It must not be used to claim E2E50 behavior benchmark quality.
    "tests.aippocampus.test_e2e50_seed_candidates",
    "tests.aippocampus.test_benchmark_field_continuity",
    "tests.aippocampus.test_benchmark_hippocampal_recall",
    "tests.aippocampus.test_benchmark_locomo_public_users",
    "tests.aippocampus.test_benchmark_knowledge_pollution",
    "tests.aippocampus.test_benchmark_public_longitudinal_users",
    "tests.aippocampus.test_benchmark_longmemeval_v2_context",
    "tests.aippocampus.test_benchmark_memoryagentbench",
    "tests.aippocampus.test_benchmark_published_reports",
    "tests.aippocampus.test_benchmark_segmented_merge_policy",
    "tests.aippocampus.test_benchmark_statistics",
    "tests.aippocampus.test_benchmark_suite",
    "tests.aippocampus.test_benchmark_vcs_future_event_recall",
}


def discover_modules() -> list[str]:
    return [
        f"tests.aippocampus.{path.stem}"
        for path in sorted(TEST_ROOT.glob("test_*.py"))
        if path.name != "__init__.py"
    ]


def modules_for_tier(tier: str) -> list[str]:
    modules = discover_modules()
    if tier == "full":
        return modules
    if tier == "benchmark-smoke":
        discovered = set(modules)
        return [module for module in sorted(BENCHMARK_SMOKE_MODULES) if module in discovered]
    if tier == "benchmark":
        return [module for module in modules if ".test_benchmark_" in module]
    if tier == "slow":
        return [module for module in modules if module in SLOW_MODULES]
    if tier == "fast":
        return [
            module
            for module in modules
            if ".test_benchmark_" not in module and module not in SLOW_MODULES
        ]
    raise ValueError(f"unknown test tier: {tier}")


def _probe_tempdir(parent: Path | None) -> None:
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
        temp_context = tempfile.TemporaryDirectory(prefix=TEMP_PROBE_PREFIX, dir=str(parent))
    else:
        temp_context = tempfile.TemporaryDirectory(prefix=TEMP_PROBE_PREFIX)
    with temp_context as tmp:
        probe = Path(tmp) / "probe.txt"
        probe.write_text("ok", encoding="utf-8")


def ensure_usable_tempdir() -> Path:
    try:
        _probe_tempdir(None)
        # Return the canonical spelling. macOS default temp paths are commonly
        # exposed as /var/... while the same directory resolves through
        # /private/var/...; downstream test cache keys should see one identity.
        return Path(tempfile.gettempdir()).resolve()
    except OSError as default_error:
        # Keep the fallback canonical too, otherwise macOS callers can compare
        # /var and /private/var spellings for the same tested directory.
        fallback = FALLBACK_TEST_TMPDIR.resolve()
        try:
            _probe_tempdir(fallback)
        except OSError as fallback_error:
            raise RuntimeError(
                "No usable temporary directory for the test runner. "
                f"Default temp failed: {default_error}. "
                f"Fallback {fallback} failed: {fallback_error}."
            ) from fallback_error
        # Keep unittest children on the verified fallback. Without this fail-fast
        # probe, Python can retry every default candidate per test case and leave
        # thousands of root-level temp probes when deletion is blocked.
        for name in TEMP_ENV_NAMES:
            os.environ[name] = str(fallback)
        tempfile.tempdir = str(fallback)
        return fallback


def run_modules(modules: list[str], *, verbosity: int) -> bool:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return result.wasSuccessful()


def run_benchmark_suite_profile(profile: str) -> bool:
    suite_path = REPO_ROOT / "benchmarks" / "aippocampus" / "benchmark_suite.py"
    command = [
        sys.executable,
        str(suite_path),
        "--profile",
        profile,
        "--json",
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        return False
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        print(f"benchmark suite profile {profile!r} did not emit valid JSON: {exc}", file=sys.stderr)
        print(completed.stdout[:2000], file=sys.stderr)
        return False
    if payload.get("ok") is not True:
        print(
            f"benchmark suite profile {profile!r} failed: "
            f"status={payload.get('status')!r}",
            file=sys.stderr,
        )
        return False
    elapsed_ms = payload.get("elapsed_ms")
    elapsed_text = f" in {elapsed_ms:.2f} ms" if isinstance(elapsed_ms, (int, float)) else ""
    print(f"benchmark suite profile {profile!r}: {payload.get('status', 'ok')}{elapsed_text}")
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AIppocampus unittest tiers.")
    parser.add_argument(
        "--tier",
        choices=("fast", "slow", "benchmark-smoke", "benchmark", "full"),
        default="fast",
        help=(
            "Test tier to run. Default is the deterministic fast suite. "
            "benchmark-smoke is the curated fresh-clone benchmark PR lane."
        ),
    )
    parser.add_argument(
        "--benchmark-suite-profile",
        choices=("public-fast",),
        help=(
            "Run benchmark_suite.py with the selected fresh-clone profile before "
            "the selected unittest tier. Intended for the CI benchmark smoke lane."
        ),
    )
    parser.add_argument("--list", action="store_true", help="List selected test modules.")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    modules = modules_for_tier(args.tier)
    if args.list:
        for module in modules:
            print(module)
        return 0
    if not modules:
        print(f"no tests selected for tier: {args.tier}", file=sys.stderr)
        return 2
    try:
        ensure_usable_tempdir()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.benchmark_suite_profile and not run_benchmark_suite_profile(
        args.benchmark_suite_profile,
    ):
        return 1
    return 0 if run_modules(modules, verbosity=max(1, args.verbose)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
