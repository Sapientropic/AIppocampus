from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import TypedDict

from test_tier_manifest import (
    BENCHMARK_MODULES,
    BENCHMARK_SMOKE_MODULES,
    BROAD_PR_PRIMARY_TIERS,
    PR_PRIMARY_TIERS,
    SLOW_MODULES,
    TEST_MODULE_CLASSIFICATIONS,
    TEST_TIERS,
    TIER_ALIASES,
    TIER_DESCRIPTIONS,
    validate_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = REPO_ROOT / "tests" / "aippocampus"
FALLBACK_TEST_TMPDIR = REPO_ROOT / ".aippocampus" / "test-tmp"
TEMP_ENV_NAMES = ("TMPDIR", "TEMP", "TMP")
TEMP_PROBE_PREFIX = "aippocampus-test-runner-"

TIER_REPORT_TOP_LIMIT = 10
QUICK_BUDGET = {
    "module_count_target": 46,
    "test_count_target": 330,
    "elapsed_seconds_target": 30.0,
}
PR_BUDGET = {
    "module_count_target": 70,
    "test_count_target": 500,
    "elapsed_seconds_target": 180.0,
}


class TierModuleRow(TypedDict):
    module: str
    test_count: int


class ModuleTimingRow(TypedDict):
    module: str
    primary_tier: str
    test_count: int
    duration_seconds: float
    ok: bool


def _target_status(actual: int | float, target: int | float) -> str:
    return "within_target" if actual <= target else "over_target"


def count_budget_for_tier(
    tier: str,
    *,
    module_count: int,
    test_count: int,
) -> dict[str, object] | None:
    normalized_tier = TIER_ALIASES.get(tier, tier)
    if normalized_tier == "quick":
        budget = QUICK_BUDGET
        label = "Quick"
        note = (
            "Quick targets are drift indicators for the local inner loop, not "
            "portable performance SLAs."
        )
    elif normalized_tier == "pr":
        budget = PR_BUDGET
        label = "PR"
        note = (
            "PR targets keep the default local gate useful for agents. Broad "
            "pre-merge coverage belongs to broad-pr, benchmark-smoke, or full."
        )
    else:
        return None
    return {
        "module_count_target": budget["module_count_target"],
        "test_count_target": budget["test_count_target"],
        "module_count_status": _target_status(
            module_count,
            budget["module_count_target"],
        ),
        "test_count_status": _target_status(
            test_count,
            budget["test_count_target"],
        ),
        "note": note,
        "tier_label": label,
    }


def timing_budget_for_tier(selected_tier: str, *, elapsed_seconds: float) -> dict[str, object] | None:
    normalized_tier = TIER_ALIASES.get(selected_tier, selected_tier)
    if normalized_tier == "quick":
        budget = QUICK_BUDGET
        note = (
            "Use this quick timing budget to spot drift. It is not a hard "
            "cross-machine SLA."
        )
    elif normalized_tier == "pr":
        budget = PR_BUDGET
        note = (
            "Use this PR timing budget to keep the default agent pre-push gate "
            "fast enough to be useful. Escalate broad coverage to broad-pr."
        )
    else:
        return None
    target = budget["elapsed_seconds_target"]
    return {
        "elapsed_seconds_target": target,
        "elapsed_seconds_status": _target_status(elapsed_seconds, target),
        "note": note,
    }


def discover_modules() -> list[str]:
    return [
        f"tests.aippocampus.{path.stem}"
        for path in sorted(TEST_ROOT.glob("test_*.py"))
        if path.name != "__init__.py"
    ]


def modules_for_tier(tier: str) -> list[str]:
    modules = discover_modules()
    validate_manifest(set(modules))
    normalized_tier = TIER_ALIASES.get(tier, tier)
    if normalized_tier == "full":
        return modules
    if normalized_tier == "benchmark-smoke":
        discovered = set(modules)
        return [module for module in sorted(BENCHMARK_SMOKE_MODULES) if module in discovered]
    if normalized_tier == "benchmark":
        return [module for module in modules if module in BENCHMARK_MODULES]
    if normalized_tier == "slow":
        return [module for module in modules if module in SLOW_MODULES]
    if normalized_tier == "pr":
        return [
            module
            for module in modules
            if TEST_MODULE_CLASSIFICATIONS[module].primary_tier in PR_PRIMARY_TIERS
        ]
    if normalized_tier == "broad-pr":
        return [
            module
            for module in modules
            if TEST_MODULE_CLASSIFICATIONS[module].primary_tier in BROAD_PR_PRIMARY_TIERS
        ]
    if normalized_tier in {"quick", "pr", "broad", "smoke", "integration"}:
        return [
            module
            for module in modules
            if TEST_MODULE_CLASSIFICATIONS[module].primary_tier == normalized_tier
        ]
    raise ValueError(f"unknown test tier: {tier}")


def shard_modules(
    modules: list[str],
    *,
    shard_index: int,
    shard_total: int,
) -> list[str]:
    # Keep CI shards stable by module name until there is reviewed timing
    # history. Dynamic cost balancing from one local run can hide empty-shard
    # mistakes and makes reproduced PR failures harder to route back.
    return [
        module
        for position, module in enumerate(sorted(modules))
        if position % shard_total == shard_index
    ]


def normalize_shard_args(
    shard_index: int | None,
    shard_total: int | None,
) -> tuple[int, int] | None:
    if shard_index is None and shard_total is None:
        return None
    if shard_index is None or shard_total is None:
        raise ValueError("shard-index and shard-total must be supplied together")
    if shard_total <= 0:
        raise ValueError("shard-total must be greater than zero")
    if shard_index < 0:
        raise ValueError("shard-index must be zero or greater")
    if shard_index >= shard_total:
        raise ValueError("shard-index must be less than shard-total")
    return shard_index, shard_total


def _ensure_repo_on_path() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def count_tests_for_module(module: str) -> int:
    _ensure_repo_on_path()
    return unittest.defaultTestLoader.loadTestsFromName(module).countTestCases()


def build_tier_report(
    *,
    tiers: tuple[str, ...] = TEST_TIERS,
    top_limit: int = TIER_REPORT_TOP_LIMIT,
) -> dict[str, object]:
    # This is an observation layer for #662's migration path. Keep it delegated
    # to modules_for_tier() until the explicit manifest exists, so the report
    # exposes the current drift without silently becoming a second tier contract.
    counts: dict[str, int] = {}
    report_tiers: dict[str, dict[str, object]] = {}

    for tier in tiers:
        modules = modules_for_tier(tier)
        module_rows: list[TierModuleRow] = []
        for module in modules:
            test_count = counts.setdefault(module, count_tests_for_module(module))
            module_rows.append({"module": module, "test_count": test_count})
        top_modules = sorted(
            module_rows,
            key=lambda row: (-row["test_count"], row["module"]),
        )[:top_limit]
        report_tiers[tier] = {
            "module_count": len(modules),
            "test_count": sum(row["test_count"] for row in module_rows),
            "top_modules": top_modules,
            "budget": count_budget_for_tier(
                tier,
                module_count=len(modules),
                test_count=sum(row["test_count"] for row in module_rows),
            ),
        }

    return {
        "kind": "aippocampus_test_tier_report",
        "schema_version": 1,
        "tier_definitions": TIER_DESCRIPTIONS,
        "tier_aliases": TIER_ALIASES,
        "tiers": report_tiers,
        "known_limitations": [
            "fast is a compatibility alias for the fast local pr gate; "
            "deterministic and ci remain broad-pr aliases for the old broad "
            "deterministic surface.",
        ],
    }


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
    _ensure_repo_on_path()
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return result.wasSuccessful()


def run_modules_with_timings(
    modules: list[str],
    *,
    verbosity: int,
) -> tuple[bool, list[ModuleTimingRow]]:
    _ensure_repo_on_path()
    rows: list[ModuleTimingRow] = []
    ok = True
    for module in modules:
        suite = unittest.defaultTestLoader.loadTestsFromName(module)
        test_count = suite.countTestCases()
        started = time.perf_counter()
        result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
        duration = time.perf_counter() - started
        ok = ok and result.wasSuccessful()
        classification = TEST_MODULE_CLASSIFICATIONS.get(module)
        rows.append(
            {
                "module": module,
                "primary_tier": classification.primary_tier if classification else "unknown",
                "test_count": test_count,
                "duration_seconds": round(duration, 6),
                "ok": result.wasSuccessful(),
            }
        )
    return ok, rows


def build_timings_report(
    *,
    selected_tier: str,
    rows: list[ModuleTimingRow],
    shard: tuple[int, int] | None,
) -> dict[str, object]:
    elapsed_seconds = round(sum(row["duration_seconds"] for row in rows), 6)
    return {
        "kind": "aippocampus_test_module_timings",
        "schema_version": 1,
        "selected_tier": selected_tier,
        "module_count": len(rows),
        "test_count": sum(row["test_count"] for row in rows),
        "failed_module_count": sum(1 for row in rows if not row["ok"]),
        "elapsed_seconds": elapsed_seconds,
        "budget": timing_budget_for_tier(selected_tier, elapsed_seconds=elapsed_seconds),
        "shard": {"index": shard[0], "total": shard[1]} if shard else None,
        "modules": rows,
    }


def write_timings_report(
    path: Path,
    *,
    selected_tier: str,
    rows: list[ModuleTimingRow],
    shard: tuple[int, int] | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            build_timings_report(selected_tier=selected_tier, rows=rows, shard=shard),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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
        choices=TEST_TIERS,
        default="pr",
        help=(
            "Test tier to run. Default is the fast local PR gate. "
            "quick is the small local inner loop with a quick target of about "
            "46 modules, 330 tests, and 30s timing-report elapsed on current "
            "local hardware; pr targets about 70 modules, 500 tests, and 180s "
            "for ordinary pre-push use; broad-pr keeps the old deterministic "
            "smoke/integration coverage for CI or pre-merge use."
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
    parser.add_argument(
        "--report-json",
        action="store_true",
        help="Print tier module/test counts as JSON without running tests.",
    )
    parser.add_argument(
        "--timings-json",
        type=Path,
        help=(
            "Run the selected tier and write per-module timing data to this JSON "
            "file. This runs modules one at a time so slow contributors can be "
            "identified without changing tier membership; quick timing reports "
            "include budget drift fields."
        ),
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        help="Zero-based shard index for deterministic module sharding.",
    )
    parser.add_argument(
        "--shard-total",
        type=int,
        help="Total number of deterministic module shards.",
    )
    parser.add_argument("-v", "--verbose", action="count", default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        shard = normalize_shard_args(args.shard_index, args.shard_total)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.report_json:
        json.dump(build_tier_report(), sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    modules = modules_for_tier(args.tier)
    if shard is not None:
        modules = shard_modules(
            modules,
            shard_index=shard[0],
            shard_total=shard[1],
        )
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
    if args.timings_json:
        ok, rows = run_modules_with_timings(modules, verbosity=max(1, args.verbose))
        write_timings_report(
            args.timings_json,
            selected_tier=args.tier,
            rows=rows,
            shard=shard,
        )
        return 0 if ok else 1
    return 0 if run_modules(modules, verbosity=max(1, args.verbose)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
