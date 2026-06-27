from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import site
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from benchmark_test_classification import (
    is_benchmark_shaped_module,
    require_benchmark_fast_lane_profile,
)
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
    TIER_SHRINK_REPLACEMENT_LANES,
    validate_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = REPO_ROOT / "tests" / "aippocampus"
RUNTIME_PACKAGE = "aippocampus_runtime"
RUNTIME_SOURCE_ROOT = REPO_ROOT / "skills" / "aippocampus" / "scripts"
FALLBACK_TEST_TMPDIR = REPO_ROOT / ".aippocampus" / "test-tmp"
TEMP_ENV_NAMES = ("TMPDIR", "TEMP", "TMP")
TEMP_PROBE_PREFIX = "aippocampus-test-runner-"
# Timing artifacts are local evidence, not a default truth source. Keep default
# reports empty unless the operator explicitly passes --timing-artifact; stale
# ignored files under benchmark_corpus/reports must not masquerade as current PR
# speed evidence.
DEFAULT_TIMING_ARTIFACTS: tuple[Path, ...] = ()

TIER_REPORT_TOP_LIMIT = 10
RUNNER_VERSION = "aippocampus-run-tests-v2"
TIMINGS_SCHEMA_VERSION = 2
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
BROAD_SUITE_REVIEW_TARGETS: dict[str, BroadSuiteReviewTarget] = {
    "broad-pr": {
        "module_count_review_threshold": 300,
        "test_count_review_threshold": 2500,
        "label": "Broad PR",
    },
    "full": {
        "module_count_review_threshold": 400,
        "test_count_review_threshold": 3500,
        "label": "Full",
    },
}


class TierModuleRow(TypedDict):
    module: str
    test_count: int


class ModuleSetManifestRow(TypedDict):
    module: str
    test_count: int


class ModuleTimingRow(TypedDict):
    module: str
    primary_tier: str
    test_count: int
    duration_seconds: float
    ok: bool


class BroadSuiteReviewTarget(TypedDict):
    module_count_review_threshold: int
    test_count_review_threshold: int
    label: str


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
    module_status = _target_status(
        module_count,
        budget["module_count_target"],
    )
    test_status = _target_status(
        test_count,
        budget["test_count_target"],
    )
    over_target = module_status == "over_target" or test_status == "over_target"
    return {
        "module_count_target": budget["module_count_target"],
        "test_count_target": budget["test_count_target"],
        "module_count_status": module_status,
        "test_count_status": test_status,
        "budget_outcome": (
            "over_target_action_recommended" if over_target else "within_target"
        ),
        "recommended_action": (
            {
                "id": f"review_{normalized_tier}_tier_budget_drift",
                "label": f"Review {label} tier budget drift",
                "mutation_risk": "planning_only",
                "why": (
                    "Split heavy modules, reclassify tier membership, or update "
                    "targets with dated rationale; do not turn this soft drift into "
                    "a hard gate without review."
                ),
            }
            if over_target
            else None
        ),
        "note": note,
        "tier_label": label,
    }


def suite_growth_review_for_tier(
    tier: str,
    *,
    module_count: int,
    test_count: int,
    top_modules: list[TierModuleRow],
) -> dict[str, object] | None:
    """Return non-gating broad-suite growth telemetry."""

    normalized_tier = TIER_ALIASES.get(tier, tier)
    target = BROAD_SUITE_REVIEW_TARGETS.get(normalized_tier)
    if target is None:
        return None
    module_threshold = int(target["module_count_review_threshold"])
    test_threshold = int(target["test_count_review_threshold"])
    over_threshold = module_count > module_threshold or test_count > test_threshold
    return {
        "kind": "non_gating_suite_growth_review",
        "status": "review_recommended" if over_threshold else "within_review_threshold",
        "module_count_review_threshold": module_threshold,
        "test_count_review_threshold": test_threshold,
        "module_count_status": _target_status(module_count, module_threshold),
        "test_count_status": _target_status(test_count, test_threshold),
        "top_contributors": top_modules[:5],
        "recommended_action": (
            {
                "id": f"review_{normalized_tier.replace('-', '_')}_suite_growth",
                "label": f"Review {target['label']} suite growth",
                "mutation_risk": "planning_only",
                "why": (
                    "Review broad-suite growth, split heavy modules, or refresh dated "
                    "rationale; this is telemetry only and must not make broad coverage "
                    "the default local agent ritual."
                ),
            }
            if over_threshold
            else None
        ),
        "boundary": (
            "Non-gating observability for CI/pre-merge/release lanes; ordinary "
            "changed-surface planning should not add broad-pr/full solely because "
            "this hint exists."
        ),
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


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_module_set_manifest(
    *,
    selected_tier: str,
    rows: Iterable[Mapping[str, object]],
    runner_version: str = RUNNER_VERSION,
) -> dict[str, object]:
    def row_test_count(row: Mapping[str, object]) -> int:
        value = row.get("test_count", 0)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value)
        return 0

    normalized_tier = TIER_ALIASES.get(selected_tier, selected_tier)
    module_rows: list[ModuleSetManifestRow] = sorted(
        [
            {
                "module": str(row["module"]),
                "test_count": row_test_count(row),
            }
            for row in rows
            if "module" in row
        ],
        key=lambda row: row["module"],
    )
    module_list = [row["module"] for row in module_rows]
    module_list_hash = _json_sha256(module_list)
    module_count = len(module_rows)
    test_count = sum(row["test_count"] for row in module_rows)
    fingerprint_input = {
        "runner_version": runner_version,
        "normalized_tier": normalized_tier,
        "module_list_hash": module_list_hash,
        "module_count": module_count,
        "test_count": test_count,
    }
    return {
        "runner_version": runner_version,
        "selected_tier": selected_tier,
        "normalized_tier": normalized_tier,
        "module_count": module_count,
        "test_count": test_count,
        "module_list_hash": module_list_hash,
        "manifest_fingerprint": _json_sha256(fingerprint_input),
    }


def _timing_payload_manifest(payload: dict[str, object]) -> tuple[dict[str, object] | None, str | None]:
    manifest = payload.get("manifest")
    if isinstance(manifest, dict) and {
        "runner_version",
        "normalized_tier",
        "module_count",
        "test_count",
        "module_list_hash",
        "manifest_fingerprint",
    }.issubset(manifest):
        return manifest, None

    modules = payload.get("modules")
    selected_tier = payload.get("selected_tier")
    if not isinstance(modules, list) or not modules:
        return None, "timing artifact does not expose a comparable module set"
    if not isinstance(selected_tier, str) or not selected_tier:
        return None, "timing artifact does not identify its selected tier"
    return (
        build_module_set_manifest(
            selected_tier=selected_tier,
            rows=[row for row in modules if isinstance(row, dict)],
            runner_version=str(payload.get("runner_version", "legacy-timings-v1")),
        ),
        "derived_from_legacy_timing_rows",
    )


def assess_timing_artifact_freshness(
    path: Path,
    *,
    current_manifests: dict[str, dict[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {
        "path": str(path),
        "status": "missing",
    }
    if not path.is_file():
        result["reason"] = "timing artifact does not exist"
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **result,
            "status": "incomparable",
            "reason": f"timing artifact is not readable JSON: {exc}",
        }
    if not isinstance(payload, dict) or payload.get("kind") != "aippocampus_test_module_timings":
        return {
            **result,
            "status": "incomparable",
            "reason": "timing artifact kind is not aippocampus_test_module_timings",
        }
    if payload.get("shard") is not None:
        return {
            **result,
            "status": "incomparable",
            "reason": "sharded timing artifact covers a partial module set",
        }

    artifact_manifest, compatibility_note = _timing_payload_manifest(payload)
    if artifact_manifest is None:
        return {
            **result,
            "status": "incomparable",
            "reason": compatibility_note or "timing artifact lacks manifest metadata",
        }

    normalized_tier = str(
        artifact_manifest.get(
            "normalized_tier",
            TIER_ALIASES.get(str(payload.get("selected_tier", "")), str(payload.get("selected_tier", ""))),
        )
    )
    current_manifest = current_manifests.get(normalized_tier)
    if current_manifest is None:
        return {
            **result,
            "status": "incomparable",
            "selected_tier": payload.get("selected_tier"),
            "normalized_tier": normalized_tier,
            "reason": "no current manifest is available for the artifact tier",
        }

    compare_keys = (
        "runner_version",
        "module_count",
        "test_count",
        "module_list_hash",
        "manifest_fingerprint",
    )
    mismatches = [
        key
        for key in compare_keys
        if artifact_manifest.get(key) != current_manifest.get(key)
    ]
    status = "stale" if mismatches else "current"
    freshness: dict[str, object] = {
        **result,
        "status": status,
        "selected_tier": payload.get("selected_tier"),
        "normalized_tier": normalized_tier,
        "generated_at": payload.get("generated_at"),
        "artifact_manifest": artifact_manifest,
        "current_manifest": current_manifest,
        "mismatches": mismatches,
    }
    if compatibility_note:
        freshness["compatibility_note"] = compatibility_note
    if status == "stale":
        freshness["reason"] = (
            "timing artifact no longer matches the current tier manifest; "
            "do not treat its elapsed time as current speed evidence"
        )
    return freshness


def default_timing_artifact_paths() -> tuple[Path, ...]:
    return tuple(path for path in DEFAULT_TIMING_ARTIFACTS if path.is_file())


def benchmark_shaped_tier_summary(tier: str, modules: list[str]) -> dict[str, object]:
    normalized_tier = TIER_ALIASES.get(tier, tier)
    shaped_modules = [
        module
        for module in modules
        if is_benchmark_shaped_module(module)
    ]
    if normalized_tier in {"quick", "pr"}:
        fast_lane_profiles = [
            require_benchmark_fast_lane_profile(module).as_dict()
            for module in shaped_modules
        ]
        return {
            "role": "fast_lane_guard_surface",
            "fast_lane_module_count": len(fast_lane_profiles),
            "fast_lane_modules": fast_lane_profiles,
            "evidence_module_count": 0,
            "evidence_modules": [],
            "boundary": (
                "Benchmark-shaped modules should not live in quick/pr by default. "
                "Any exception must carry an explicit fast-lane category and "
                "rationale."
            ),
        }
    if normalized_tier in {"benchmark", "benchmark-smoke"}:
        evidence_modules = [
            {
                "module": module,
                "category": "benchmark_evidence",
                "rationale": (
                    "Selected by a benchmark evidence lane; use its result only "
                    "within the lane's documented benchmark scope."
                ),
            }
            for module in shaped_modules
        ]
        return {
            "role": "benchmark_evidence_lane",
            "fast_lane_module_count": 0,
            "fast_lane_modules": [],
            "evidence_module_count": len(evidence_modules),
            "evidence_modules": evidence_modules,
            "boundary": (
                "Benchmark evidence belongs to benchmark or benchmark-smoke lanes, "
                "not to quick/pr guard summaries."
            ),
        }
    return {
        "role": "ordinary_test_lane",
        "fast_lane_module_count": 0,
        "fast_lane_modules": [],
        "evidence_module_count": 0,
        "evidence_modules": [],
        "boundary": (
            "This tier is not a benchmark evidence lane; benchmark-shaped names "
            "need explicit review before entering quick/pr."
        ),
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
        selected = [
            module
            for module in modules
            if TEST_MODULE_CLASSIFICATIONS[module].primary_tier in PR_PRIMARY_TIERS
        ]
        benchmark_shaped_tier_summary(normalized_tier, selected)
        return selected
    if normalized_tier == "broad-pr":
        return [
            module
            for module in modules
            if TEST_MODULE_CLASSIFICATIONS[module].primary_tier in BROAD_PR_PRIMARY_TIERS
        ]
    if normalized_tier in {"quick", "pr", "broad", "smoke", "integration"}:
        selected = [
            module
            for module in modules
            if TEST_MODULE_CLASSIFICATIONS[module].primary_tier == normalized_tier
        ]
        if normalized_tier == "quick":
            benchmark_shaped_tier_summary(normalized_tier, selected)
        return selected
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


def ensure_runtime_source_path() -> None:
    if not RUNTIME_SOURCE_ROOT.exists():
        return
    runtime_source = str(RUNTIME_SOURCE_ROOT)
    if runtime_source not in sys.path:
        sys.path.insert(0, runtime_source)

    # Child test subprocesses should not depend on macOS processing editable
    # .pth files; the runner has a source-backed runtime route already.
    pythonpath = os.environ.get("PYTHONPATH", "")
    pythonpath_parts = [part for part in pythonpath.split(os.pathsep) if part]
    if runtime_source not in pythonpath_parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([runtime_source, *pythonpath_parts])
    importlib.invalidate_caches()


def _path_has_hidden_flag(path: Path) -> bool:
    hidden_flag = getattr(stat, "UF_HIDDEN", 0)
    if not hidden_flag:
        return False
    try:
        return bool(getattr(path.stat(), "st_flags", 0) & hidden_flag)
    except OSError:
        return False


def _runtime_source_pth_files() -> list[Path]:
    candidates: list[Path] = []
    site_dirs: list[str] = []
    try:
        site_dirs.extend(site.getsitepackages())
    except AttributeError:
        pass
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        site_dirs.append(user_site)
    runtime_source = str(RUNTIME_SOURCE_ROOT)
    for site_dir in dict.fromkeys(site_dirs):
        root = Path(site_dir)
        if not root.exists():
            continue
        for pth in sorted(root.glob("*.pth")):
            try:
                text = pth.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if runtime_source in text:
                candidates.append(pth)
    return candidates


def runtime_import_preflight_issue() -> str | None:
    if importlib.util.find_spec(RUNTIME_PACKAGE) is not None:
        return None

    editable_pth_files = _runtime_source_pth_files()
    hidden_pth_files = [pth for pth in editable_pth_files if _path_has_hidden_flag(pth)]
    if hidden_pth_files:
        names = ", ".join(pth.name for pth in hidden_pth_files)
        return (
            f"{RUNTIME_PACKAGE} is not importable even though an editable install path file "
            f"exists. Detected hidden .pth file(s): {names}. On macOS, Python can skip "
            "hidden .pth files during site initialization, which makes an editable install "
            "look successful while subprocess imports fail. If this is the repo-local "
            "virtualenv, repair only that environment with: "
            "chflags -R nohidden .venv. If the diagnostic still names specific .pth "
            "files, clear those files too with: "
            "find .venv -name '*.pth' -exec chflags nohidden {} +"
        )
    if editable_pth_files:
        names = ", ".join(pth.name for pth in editable_pth_files)
        return (
            f"{RUNTIME_PACKAGE} is not importable, but editable .pth file(s) exist: {names}. "
            "Check whether Python processed site-packages .pth files for this virtualenv, "
            "or recreate the repo-local .venv and rerun: python -m pip install -e \".[dev]\""
        )
    return (
        f"{RUNTIME_PACKAGE} is not importable. Run the contributor install from the repo "
        "root with a Python 3.12+ virtualenv: python -m pip install -e \".[dev]\""
    )


def count_tests_for_module(module: str) -> int:
    _ensure_repo_on_path()
    return unittest.defaultTestLoader.loadTestsFromName(module).countTestCases()


def build_tier_report(
    *,
    tiers: tuple[str, ...] = TEST_TIERS,
    top_limit: int = TIER_REPORT_TOP_LIMIT,
    timing_artifact_paths: Iterable[Path] = (),
) -> dict[str, object]:
    # This is an observation layer for #662's migration path. Keep it delegated
    # to modules_for_tier() until the explicit manifest exists, so the report
    # exposes the current drift without silently becoming a second tier contract.
    counts: dict[str, int] = {}
    report_tiers: dict[str, dict[str, object]] = {}
    current_manifests: dict[str, dict[str, object]] = {}

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
        manifest = build_module_set_manifest(selected_tier=tier, rows=module_rows)
        normalized_tier = TIER_ALIASES.get(tier, tier)
        current_manifests.setdefault(normalized_tier, manifest)
        report_tiers[tier] = {
            "module_count": len(modules),
            "test_count": sum(row["test_count"] for row in module_rows),
            "top_modules": top_modules,
            "budget": count_budget_for_tier(
                tier,
                module_count=len(modules),
                test_count=sum(row["test_count"] for row in module_rows),
            ),
            "growth_review": suite_growth_review_for_tier(
                tier,
                module_count=len(modules),
                test_count=sum(row["test_count"] for row in module_rows),
                top_modules=top_modules,
            ),
            "manifest": manifest,
            "benchmark_shaped": benchmark_shaped_tier_summary(tier, modules),
        }

    return {
        "kind": "aippocampus_test_tier_report",
        "schema_version": 2,
        "runner_version": RUNNER_VERSION,
        "generated_at": _utc_timestamp(),
        "tier_definitions": TIER_DESCRIPTIONS,
        "tier_aliases": TIER_ALIASES,
        "tier_shrink_replacement_lanes": TIER_SHRINK_REPLACEMENT_LANES,
        "tiers": report_tiers,
        "timing_artifacts": [
            assess_timing_artifact_freshness(path, current_manifests=current_manifests)
            for path in timing_artifact_paths
        ],
        "known_limitations": [
            "Use canonical tiers directly: quick for inner-loop checks, pr for "
            "local closeout, and broad-pr for old broad deterministic coverage.",
            "Benchmark-shaped modules should stay in benchmark evidence lanes by "
            "default. If one returns to quick/pr, it must carry an explicit "
            "fast-lane category and rationale.",
        ],
    }


def _probe_tempdir(parent: Path) -> None:
    parent.mkdir(parents=True, exist_ok=True)
    temp_context = tempfile.TemporaryDirectory(prefix=TEMP_PROBE_PREFIX, dir=str(parent))
    with temp_context as tmp:
        probe = Path(tmp) / "probe.txt"
        probe.write_text("ok", encoding="utf-8")


def _tempdir_parent_candidates() -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(label: str, value: str | Path | None) -> None:
        if value is None or str(value).strip() == "":
            return
        path = Path(value).expanduser()
        key = os.path.normcase(str(path))
        if key in seen:
            return
        seen.add(key)
        candidates.append((label, path))

    for name in TEMP_ENV_NAMES:
        add(f"env:{name}", os.environ.get(name))
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            add("windows:LOCALAPPDATA\\Temp", Path(local_app_data) / "Temp")
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            add("windows:USERPROFILE\\AppData\\Local\\Temp", Path(user_profile) / "AppData" / "Local" / "Temp")
        system_root = os.environ.get("SystemRoot")
        if system_root:
            add("windows:SystemRoot\\Temp", Path(system_root) / "Temp")
    else:
        for value in ("/tmp", "/var/tmp", "/usr/tmp"):
            add(f"posix:{value}", value)
    return candidates


def _activate_tempdir(path: Path) -> Path:
    selected = path.resolve()
    for name in TEMP_ENV_NAMES:
        os.environ[name] = str(selected)
    tempfile.tempdir = str(selected)
    return selected


def ensure_usable_tempdir() -> Path:
    default_errors: list[str] = []
    for label, candidate in _tempdir_parent_candidates():
        try:
            _probe_tempdir(candidate)
        except OSError as exc:
            default_errors.append(f"{label}={candidate}: {exc}")
            continue
        # Keep unittest children on the verified parent. Without this fail-fast
        # explicit parent, Python can retry implicit candidates and in hostile
        # hosts may leave random probes in the repository cwd.
        return _activate_tempdir(candidate)

    # Keep the fallback canonical too, otherwise macOS callers can compare
    # /var and /private/var spellings for the same tested directory.
    fallback = FALLBACK_TEST_TMPDIR.resolve()
    try:
        _probe_tempdir(fallback)
    except OSError as fallback_error:
        default_summary = "; ".join(default_errors) if default_errors else "no explicit candidates"
        raise RuntimeError(
            "No usable temporary directory for the test runner. "
            f"Default temp candidates failed: {default_summary}. "
            f"Fallback {fallback} failed: {fallback_error}."
        ) from fallback_error
    return _activate_tempdir(fallback)


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
        "schema_version": TIMINGS_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "generated_at": _utc_timestamp(),
        "selected_tier": selected_tier,
        "manifest": build_module_set_manifest(selected_tier=selected_tier, rows=rows),
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
    digest = payload.get("outcome_digest")
    counts = digest.get("counts") if isinstance(digest, dict) else None
    if isinstance(counts, dict):
        print(
            "benchmark outcome digest: "
            f"promoted={counts.get('public_quality_promoted', 0)} "
            f"diagnostic_only={counts.get('diagnostic_only', 0)} "
            f"adoption_blocked={counts.get('adoption_blocked', 0)} "
            f"owner_action={counts.get('owner_action', 0)}"
        )
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
        "--timing-artifact",
        action="append",
        type=Path,
        default=[],
        help=(
            "When used with --report-json, compare a timing artifact against "
            "the current tier manifest and report current/stale/incomparable."
        ),
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
        timing_artifacts = (
            tuple(args.timing_artifact)
            if args.timing_artifact
            else default_timing_artifact_paths()
        )
        json.dump(
            build_tier_report(timing_artifact_paths=timing_artifacts),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
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
    ensure_runtime_source_path()
    runtime_issue = runtime_import_preflight_issue()
    if runtime_issue:
        print(runtime_issue, file=sys.stderr)
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
