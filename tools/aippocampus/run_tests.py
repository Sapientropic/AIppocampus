from __future__ import annotations

import argparse
import os
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
        return Path(tempfile.gettempdir()).resolve()
    except OSError as default_error:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AIppocampus unittest tiers.")
    parser.add_argument(
        "--tier",
        choices=("fast", "slow", "benchmark", "full"),
        default="fast",
        help="Test tier to run. Default is the deterministic fast suite.",
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
    return 0 if run_modules(modules, verbosity=max(1, args.verbose)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
