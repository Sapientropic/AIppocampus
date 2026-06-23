from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, cast

REPO_ROOT = Path(__file__).resolve().parents[2]
DEBT_REPORT_SCRIPT = "tools/aippocampus/docs/debt_report.py"
PORTABLE_PYTHON_COMMAND = "python"
CI_RUFF_COMMAND = "ruff check skills plugins tests tools benchmarks benchmark_corpus"
CI_MYPY_COMMAND = "mypy"
FALLBACK_CANONICAL_CI_PYTHON = "3.12"
STATIC_PYTHON_ROOTS = (
    "skills/",
    "plugins/",
    "tests/",
    "tools/",
    "benchmarks/",
    "benchmark_corpus/",
)
STATIC_CONFIG_PATHS = {
    "pyproject.toml",
}
CHECK_TOOLING_PATHS = {
    "tools/aippocampus/run_tests.py",
    "tools/aippocampus/test_tier_manifest.py",
    "tools/aippocampus/test_plan.py",
}
APW_PARITY_SURFACES = frozenset(
    {
        "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_inputs.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_walker.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/apw_route_identity.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/why_diagnostics.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_cache.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli_support.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_catalog.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_deepen_projection.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/recall_navigation.py",
    }
)
APW_PARITY_TEST_MODULES = (
    "tests.aippocampus.test_associative_path_inputs",
    "tests.aippocampus.test_agent_recall_apw_fallback",
    "tests.aippocampus.test_aippocampus_mcp_server_recall",
    "tests.aippocampus.test_benchmark_associative_path_walker",
)
RECALL_INTEGRATION_READINESS_SURFACES = frozenset(
    {
        "tools/aippocampus/recall_integration_readiness.py",
        "tools/aippocampus/smoke/known_artifact_recall_dogfood.py",
        "tools/aippocampus/smoke/smoke_repo_familiarity.py",
        "tools/aippocampus/smoke/smoke_repo_familiarity_foreground_experiment.py",
        "skills/aippocampus/scripts/aippocampus_runtime/navigation/repo_familiarity.py",
        "skills/aippocampus/scripts/aippocampus_runtime/ops/repo_familiarity_foreground_experiment.py",
        "skills/aippocampus/scripts/aippocampus_runtime/ops/repo_familiarity_foreground_experiment_fixtures.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_cache.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_deepen_projection.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_handlers.py",
        "skills/aippocampus/scripts/aippocampus_runtime/mcp/tool_catalog.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/hook_agent_affordance.py",
        "skills/aippocampus/scripts/aippocampus_runtime/recall/feedback_events.py",
    }
)
DEBT_REGISTER_SOURCES = (
    REPO_ROOT / "docs" / "architecture" / "architecture-debt-register.md",
    REPO_ROOT / "docs" / "evidence" / "reports" / "architecture-debt-snapshot-2026-06-04.md",
)
BUDGET_ROW_RE = re.compile(r"^\|\s*`(?P<path>[^`]+\.py)`\s*\|", re.MULTILINE)
REGISTER_BUDGET_ROW_RE = re.compile(
    r"^\|\s*`(?P<path>[^`]+\.py)`\s*"
    r"\|\s*(?P<current>\d+)\s*\|\s*(?P<budget>\d+)\s*\|",
    re.MULTILINE,
)
LARGE_CHANGED_TEST_MODULE_THRESHOLD = 5
LOW_MARGIN_GUARD_LIMIT = 9

from benchmark_test_classification import (
    benchmark_fast_lane_profile_for,
    is_benchmark_shaped_module,
)
from test_tier_manifest import TEST_MODULE_CLASSIFICATIONS


@dataclass(frozen=True)
class PlannedCommand:
    command: str
    reason: str
    scope: str

    def as_dict(self) -> dict[str, str]:
        return {"command": self.command, "reason": self.reason, "scope": self.scope}


def _repo_relative(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    return normalized[2:] if normalized.startswith("./") else normalized


def local_python_command() -> str:
    """Return the interpreter that is running the planner, shell-quoted."""
    executable = str(Path(sys.executable).resolve())
    return '"' + executable.replace('"', '\\"') + '"'


def python_command(*, local_executable: bool = False) -> str:
    """Return a copy-pasteable Python command.

    The default must stay portable because planner JSON is often pasted into PRs,
    issues, and handoffs. Operators who need the exact interpreter can opt in with
    ``--local-executable`` instead of leaking a host-specific path by accident.
    """

    if local_executable:
        return local_python_command()
    return PORTABLE_PYTHON_COMMAND


def py_command(args: str, *, local_executable: bool = False) -> str:
    return f"{python_command(local_executable=local_executable)} {args}"


def py_script(script: str, args: str = "", *, local_executable: bool = False) -> str:
    suffix = f" {args}" if args else ""
    return f"{python_command(local_executable=local_executable)} {script}{suffix}"


def shell_arg(value: str) -> str:
    if not value or any(char.isspace() or char in {'"', "'"} for char in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def debt_report_args(changed_files: Iterable[str]) -> str:
    changed_args = " ".join(
        f"--changed-file {shell_arg(path)}" for path in sorted(set(changed_files))
    )
    prefix = "--changed-surface-only --json"
    return prefix if not changed_args else f"{prefix} {changed_args}"


def architecture_debt_tracked_paths() -> set[str]:
    paths: set[str] = set()
    for source in DEBT_REGISTER_SOURCES:
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        paths.update(match.group("path") for match in BUDGET_ROW_RE.finditer(text))
    return paths


def architecture_debt_low_margin_paths() -> set[str]:
    paths: set[str] = set()
    for source in DEBT_REGISTER_SOURCES:
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        for match in REGISTER_BUDGET_ROW_RE.finditer(text):
            current = int(match.group("current"))
            budget = int(match.group("budget"))
            if budget - current <= LOW_MARGIN_GUARD_LIMIT:
                paths.add(match.group("path"))
    return paths


def _debt_report_is_red() -> bool:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / DEBT_REPORT_SCRIPT), "--headroom-only", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode != 0


def architecture_debt_plan_reason(changed_files: Iterable[str]) -> str:
    tracked = architecture_debt_tracked_paths()
    changed_tracked = sorted(path for path in changed_files if path in tracked)
    low_margin = architecture_debt_low_margin_paths()
    changed_low_margin = sorted(path for path in changed_tracked if path in low_margin)
    if changed_tracked:
        preview = ", ".join(changed_tracked[:3])
        suffix = "" if len(changed_tracked) <= 3 else f", +{len(changed_tracked) - 3} more"
        pressure = ""
        if changed_low_margin:
            low_preview = ", ".join(changed_low_margin[:2])
            low_suffix = (
                "" if len(changed_low_margin) <= 2 else f", +{len(changed_low_margin) - 2} more"
            )
            pressure = (
                f" Low-margin guard pressure touched: {low_preview}{low_suffix}; "
                "start with a split/trim decision before growing these owners."
            )
        return (
            f"Architecture-debt tracked file(s) changed: {preview}{suffix}. "
            "Run the headroom preflight early; use the register count refresh command "
            "only for count-only drift, not for over-budget owner growth. This is not "
            "a substitute for functional tests."
            f"{pressure}"
        )
    if _debt_report_is_red():
        return (
            "Architecture debt report is already red. Run the headroom preflight "
            "before late closeout; if the failure is count-only drift, refresh the "
            "register counts with debt_report.py, but split or justify real over-budget "
            "owner growth. This is not a substitute for functional tests."
        )
    return ""


def changed_surface_debt_plan_reason(changed_files: Iterable[str]) -> str:
    changed_python = sorted(path for path in changed_files if _is_static_python_surface(path))
    if not changed_python:
        return ""
    preview = ", ".join(changed_python[:3])
    suffix = "" if len(changed_python) <= 3 else f", +{len(changed_python) - 3} more"
    return (
        f"Python changed surface touched: {preview}{suffix}. Run the lightweight "
        "debt gate so duplicate helpers, hot-path broad exceptions, compact debug "
        "field literals, and giant-function growth are acceptance-bearing before closeout."
    )


def _load_pyproject() -> dict[str, object]:
    path = REPO_ROOT / "pyproject.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def _mypy_config() -> dict[str, object]:
    tool = _load_pyproject().get("tool", {})
    if not isinstance(tool, dict):
        return {}
    mypy = tool.get("mypy", {})
    return mypy if isinstance(mypy, dict) else {}


def canonical_ci_python_version() -> str:
    value = _mypy_config().get("python_version")
    if isinstance(value, str) and value:
        return value
    return FALLBACK_CANONICAL_CI_PYTHON


def _version_minor(version: str) -> str:
    parts = version.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}.{parts[1]}"
    return version


def _local_python_version_parts() -> tuple[int, int, int]:
    info = sys.version_info
    try:
        return (int(info.major), int(info.minor), int(info.micro))
    except AttributeError:
        return (int(info[0]), int(info[1]), int(info[2]))


def python_environment_summary() -> dict[str, object]:
    major, minor, micro = _local_python_version_parts()
    local_version = f"{major}.{minor}.{micro}"
    canonical_version = canonical_ci_python_version()
    local_minor = f"{major}.{minor}"
    canonical_minor = _version_minor(canonical_version)
    return {
        "local_python_version": local_version,
        "local_python_minor": local_minor,
        "canonical_ci_python_version": canonical_version,
        "canonical_ci_python_minor": canonical_minor,
        "minor_matches_ci": local_minor == canonical_minor,
    }


def planner_warnings(environment: dict[str, object]) -> list[dict[str, str]]:
    if environment.get("minor_matches_ci") is True:
        return []
    local_minor = str(environment.get("local_python_minor", "unknown"))
    canonical_minor = str(environment.get("canonical_ci_python_minor", "unknown"))
    return [
        {
            "kind": "python_minor_mismatch",
            "severity": "warning",
            "message": (
                f"Local Python minor {local_minor} differs from canonical CI {canonical_minor}. "
                "Keep CI-equivalent ruff/mypy and PR-gate results as the compatibility signal."
            ),
            "next_action": (
                "Use Python "
                f"{canonical_minor} for compatibility-sensitive failures with "
                "python tools/aippocampus/run_ci_parity.py --tier pr --json; do not run "
                "a broad matrix locally by default."
            ),
        }
    ]


def modules_with_tag(tag: str) -> list[str]:
    return sorted(
        module
        for module, classification in TEST_MODULE_CLASSIFICATIONS.items()
        if tag in classification.tags
    )


def _run_git_name_only(args: list[str]) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [
        _repo_relative(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    ]


def collect_changed_files(*, base: str) -> list[str]:
    changed: set[str] = set()
    changed.update(
        _run_git_name_only(["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...HEAD"])
    )
    changed.update(_run_git_name_only(["diff", "--name-only", "--diff-filter=ACMRTUXB"]))
    changed.update(_run_git_name_only(["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"]))
    changed.update(_run_git_name_only(["ls-files", "--others", "--exclude-standard"]))
    return sorted(changed)


def _test_module_for_path(path: str) -> str | None:
    normalized = _repo_relative(path)
    prefix = "tests/aippocampus/"
    if not normalized.startswith(prefix) or not normalized.endswith(".py"):
        return None
    stem = Path(normalized).stem
    if not stem.startswith("test_"):
        return None
    return f"tests.aippocampus.{stem}"


def _add_command(commands: list[PlannedCommand], command: PlannedCommand) -> None:
    if any(existing.command == command.command for existing in commands):
        return
    commands.append(command)


def _changed_test_modules(changed_files: Iterable[str]) -> list[str]:
    modules = {
        module
        for path in changed_files
        if (module := _test_module_for_path(path)) is not None
    }
    return sorted(modules)


def _changed_test_group_name(module: str) -> str:
    classification = TEST_MODULE_CLASSIFICATIONS.get(module)
    if classification is None:
        return "unclassified"
    if classification.primary_tier != "broad":
        return classification.primary_tier
    if "benchmark" in classification.tags:
        return "broad-benchmark-guard"
    if module in {
        "tests.aippocampus.test_run_tests_tiers",
        "tests.aippocampus.test_test_plan",
    }:
        return "broad-test-tooling"
    return "broad-runtime"


def _changed_test_module_groups(
    modules: Iterable[str],
    *,
    local_executable: bool = False,
) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = {}
    for module in sorted(modules):
        grouped.setdefault(_changed_test_group_name(module), []).append(module)

    groups: list[dict[str, object]] = []
    for group_name, group_modules in grouped.items():
        command = py_command(
            f"-m unittest {' '.join(group_modules)} -v",
            local_executable=local_executable,
        )
        groups.append(
            {
                "group": group_name,
                "module_count": len(group_modules),
                "modules": group_modules,
                "command": command,
                "reason": (
                    "Large dirty test surface slice grouped by tier and owner surface; "
                    "run the slice that matches your changed surface first."
                ),
            }
        )
    return sorted(groups, key=lambda group: str(group["command"]))


def _large_dirty_surface_warning(changed_test_modules: list[str]) -> dict[str, str]:
    return {
        "kind": "large_dirty_surface",
        "severity": "warning",
        "message": (
            f"{len(changed_test_modules)} changed test modules exceed the "
            f"{LARGE_CHANGED_TEST_MODULE_THRESHOLD}-module planner slice threshold."
        ),
        "next_action": (
            "Use changed_test_groups to pick the slice owned by your edit first; "
            "run all listed slices before closeout if you own the whole dirty surface."
        ),
    }


def _is_benchmark_fast_lane_guard(module: str | None) -> bool:
    if module is None or not is_benchmark_shaped_module(module):
        return False
    return benchmark_fast_lane_profile_for(module) is not None


def classify_changed_files(changed_files: Iterable[str]) -> set[str]:
    categories: set[str] = set()
    for raw_path in changed_files:
        path = _repo_relative(raw_path)
        if path.startswith("docs/") or path in {"README.md", "AGENTS.md"} or path.endswith(".md"):
            categories.add("docs")
        if path.startswith(".github/workflows/"):
            categories.add("ci_workflow")
        if path in {
            "tools/aippocampus/run_tests.py",
            "tools/aippocampus/run_ci_parity.py",
            "tools/aippocampus/test_tier_manifest.py",
            "tools/aippocampus/test_plan.py",
        }:
            categories.add("test_runner")
        if path.startswith("tools/aippocampus/release/"):
            categories.add("release_tool")
        if path.startswith("tests/aippocampus/"):
            categories.add("tests")
        if path.startswith("benchmarks/aippocampus/") or path.startswith("benchmark_corpus/"):
            categories.add("benchmark")
        if path.startswith("tests/aippocampus/test_benchmark"):
            module = _test_module_for_path(path)
            if _is_benchmark_fast_lane_guard(module):
                categories.add("benchmark_fast_lane_guard")
            else:
                categories.add("benchmark")
        if path.startswith("skills/aippocampus/SKILL.md") or path.startswith(
            "skills/aippocampus/references/"
        ):
            categories.add("skill_surface")
        if path.startswith("skills/aippocampus/scripts/aippocampus_runtime/hooks/"):
            categories.add("hooks")
        if path.startswith("skills/aippocampus/scripts/aippocampus_runtime/mcp/"):
            categories.add("mcp")
        if path.startswith("skills/aippocampus/scripts/"):
            categories.add("runtime")
        if path in APW_PARITY_SURFACES:
            categories.add("apw_parity")
        if path in RECALL_INTEGRATION_READINESS_SURFACES:
            categories.add("recall_integration_readiness")
        if path.startswith("plugins/aippocampus/"):
            categories.add("plugin")
    return categories


def _is_static_python_surface(path: str) -> bool:
    if path in STATIC_CONFIG_PATHS:
        return True
    return path.endswith(".py") and path.startswith(STATIC_PYTHON_ROOTS)


def _mypy_tracked_paths() -> set[str]:
    files = _mypy_config().get("files", [])
    if not isinstance(files, list):
        return set()
    return {
        _repo_relative(path)
        for path in files
        if isinstance(path, str) and path.endswith(".py")
    }


def _needs_static_gates(changed_files: Iterable[str], categories: set[str]) -> bool:
    return (
        any(_is_static_python_surface(path) for path in changed_files)
        or bool(categories & {"ci_workflow", "test_runner"})
    )


def _needs_mypy_gate(changed_files: Iterable[str], categories: set[str]) -> bool:
    tracked = _mypy_tracked_paths()
    for path in changed_files:
        if path in tracked:
            return True
        if path in CHECK_TOOLING_PATHS or path in STATIC_CONFIG_PATHS:
            return True
        if path.startswith("skills/aippocampus/scripts/aippocampus_runtime/") and path.endswith(
            ".py"
        ):
            return True
        if path.startswith("benchmarks/aippocampus/") and path.endswith(".py"):
            return True
        if path.startswith("plugins/aippocampus/") and path.endswith(".py"):
            return True
    return bool(categories & {"ci_workflow", "test_runner"})


def _add_static_gates(
    commands: list[PlannedCommand],
    changed_files: Iterable[str],
    categories: set[str],
) -> None:
    if not _needs_static_gates(changed_files, categories):
        return
    categories.add("static_gates")
    _add_command(
        commands,
        PlannedCommand(
            command=CI_RUFF_COMMAND,
            reason=(
                "CI runs this ruff gate before PR tests; run it early for Python-bearing "
                "surfaces so import-order and unused-import failures are not discovered late."
            ),
            scope="static",
        ),
    )
    if _needs_mypy_gate(changed_files, categories):
        categories.add("type_check")
        _add_command(
            commands,
            PlannedCommand(
                command=CI_MYPY_COMMAND,
                reason=(
                    "CI runs this mypy gate on the canonical typed surface; this changed "
                    "surface can affect that contract."
                ),
                scope="static",
            ),
        )


def build_test_plan(
    changed_files: list[str],
    *,
    local_executable: bool = False,
) -> dict[str, object]:
    normalized_files = [_repo_relative(path) for path in changed_files]
    categories = classify_changed_files(normalized_files)
    commands: list[PlannedCommand] = []
    changed_test_modules = _changed_test_modules(normalized_files)
    changed_test_groups: list[dict[str, object]] = []
    debt_reason = architecture_debt_plan_reason(normalized_files)
    changed_surface_debt_reason = changed_surface_debt_plan_reason(normalized_files)
    environment = python_environment_summary()
    warnings = planner_warnings(environment)
    large_dirty_surface = (
        len(changed_test_modules) > LARGE_CHANGED_TEST_MODULE_THRESHOLD
    )
    if large_dirty_surface:
        warnings.append(_large_dirty_surface_warning(changed_test_modules))
    if debt_reason:
        categories.add("architecture_debt")
    if changed_surface_debt_reason:
        categories.add("changed_surface_debt")

    if not normalized_files:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/run_tests.py",
                    "--tier quick",
                    local_executable=local_executable,
                ),
                reason="No changed files were detected; quick is the lowest-cost sanity check.",
                scope="sanity",
            ),
        )

    _add_static_gates(commands, normalized_files, categories)

    if changed_test_modules and large_dirty_surface:
        changed_test_groups = _changed_test_module_groups(
            changed_test_modules,
            local_executable=local_executable,
        )
        for group in changed_test_groups:
            _add_command(
                commands,
                PlannedCommand(
                    command=str(group["command"]),
                    reason=str(group["reason"]),
                    scope=f"focused:{group['group']}",
                ),
            )
    elif changed_test_modules:
        _add_command(
            commands,
            PlannedCommand(
                command=py_command(
                    f"-m unittest {' '.join(changed_test_modules)} -v",
                    local_executable=local_executable,
                ),
                reason="Run changed test modules first so failures point to the edited surface.",
                scope="focused",
            ),
        )

    if debt_reason:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    DEBT_REPORT_SCRIPT,
                    "--headroom-only --json",
                    local_executable=local_executable,
                ),
                reason=debt_reason,
                scope="architecture-debt",
            ),
        )

    if changed_surface_debt_reason:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    DEBT_REPORT_SCRIPT,
                    debt_report_args(normalized_files),
                    local_executable=local_executable,
                ),
                reason=changed_surface_debt_reason,
                scope="changed-surface-debt",
            ),
        )

    if "docs" in categories or "skill_surface" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/docs/check_docs_health.py",
                    "--json",
                    local_executable=local_executable,
                ),
                reason="Docs and skill-surface edits need the documentation health guard.",
                scope="focused",
            ),
        )

    if "test_runner" in categories or "ci_workflow" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=py_command(
                    "-m unittest "
                    "tests.aippocampus.test_run_tests_tiers "
                    "tests.aippocampus.test_test_plan -v",
                    local_executable=local_executable,
                ),
                reason="Test-runner and CI changes must prove the tier/planner contract directly.",
                scope="focused",
            ),
        )
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/run_tests.py",
                    "--report-json",
                    local_executable=local_executable,
                ),
                reason="Tier membership/count drift should be visible before a broad run.",
                scope="diagnostic",
            ),
        )

    if "release_tool" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=py_command(
                    "-m unittest "
                    "tests.aippocampus.test_agent_discovery_release_check "
                    "tests.aippocampus.test_public_boundary_check -v",
                    local_executable=local_executable,
                ),
                reason="Release tooling changes need focused checks for metadata readiness and public-boundary hygiene.",
                scope="focused",
            ),
        )
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/release/check_public_boundary.py",
                    "--json",
                    local_executable=local_executable,
                ),
                reason="Public-boundary tooling changes should prove the source scan still runs cleanly.",
                scope="public-boundary",
            ),
        )

    if "hooks" in categories:
        hook_behavior_modules = " ".join(modules_with_tag("hook_behavior"))
        _add_command(
            commands,
            PlannedCommand(
                command=py_command(
                    f"-m unittest {hook_behavior_modules} -v",
                    local_executable=local_executable,
                ),
                reason="Hook edits can affect foreground behavior, anti-nag quietness, and latency.",
                scope="focused",
            ),
        )

    if "mcp" in categories:
        mcp_contract_modules = " ".join(
            [
                "tests.aippocampus.test_aippocampus_mcp_server_catalog",
                "tests.aippocampus.test_aippocampus_mcp_server_recall",
                "tests.aippocampus.test_aippocampus_mcp_server_ops",
            ]
        )
        _add_command(
            commands,
            PlannedCommand(
                command=py_command(
                    f"-m unittest {mcp_contract_modules} -v",
                    local_executable=local_executable,
                ),
                reason="MCP edits need the split host-facing catalog, recall, and ops contract tests.",
                scope="focused",
            ),
        )

    if "apw_parity" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=py_command(
                    f"-m unittest {' '.join(APW_PARITY_TEST_MODULES)} -v",
                    local_executable=local_executable,
                ),
                reason=(
                    "APW input/fallback/projection edits must prove diagnostic-to-agent "
                    "parity on sidecar and real-clean-source fixtures; this is a contract "
                    "gate, not a broad benchmark quality claim."
                ),
                scope="focused:apw-parity",
            ),
        )

    if "recall_integration_readiness" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/recall_integration_readiness.py",
                    "--json",
                    local_executable=local_executable,
                ),
                reason=(
                    "Recall integration surfaces changed; verify designed/proxy paths are "
                    "classified separately from foreground-callable agent actions."
                ),
                scope="focused:recall-integration-readiness",
            ),
        )

    if "benchmark" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/run_tests.py",
                    "--tier benchmark-smoke --benchmark-suite-profile public-fast",
                    local_executable=local_executable,
                ),
                reason="Benchmark-adjacent edits need the public-fast benchmark smoke lane.",
                scope="surface",
            ),
        )

    if "runtime" in categories or "plugin" in categories or "skill_surface" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/run_tests.py",
                    "--tier pr",
                    local_executable=local_executable,
                ),
                reason="Runtime, plugin, and skill edits should pass the fast local PR gate.",
                scope="pre-push",
            ),
        )

    if not commands:
        _add_command(
            commands,
            PlannedCommand(
                command=py_script(
                    "tools/aippocampus/run_tests.py",
                    "--tier quick",
                    local_executable=local_executable,
                ),
                reason="No specific surface mapping matched; quick is the safe first check.",
                scope="sanity",
            ),
        )

    return {
        "kind": "aippocampus_changed_surface_test_plan",
        "schema_version": 2,
        "command_mode": "local_executable" if local_executable else "portable",
        "python_environment": environment,
        "warnings": warnings,
        "changed_files": normalized_files,
        "changed_test_groups": changed_test_groups,
        "categories": sorted(categories),
        "commands": [command.as_dict() for command in commands],
        "followup": [
            "Run planner-named static gates (`ruff check ...` and `mypy` when listed) before PR closeout.",
            "Run the focused commands first; run `pr` once when the planner names it, CI is unavailable, or CI is stale.",
            "`pr` already includes `quick`; use quick for iteration, not as a mandatory closeout step before pr.",
            "Let CI own `broad-pr`, benchmark-smoke, platform, coverage, and CodeQL unless the changed surface specifically needs a local broad run.",
        ],
        "boundary": (
            "Focused verification is an agent usefulness tool. It does not replace "
            "CI, publish-time wheel checks, or release-only public-state checks."
        ),
    }


def build_release_preflight_plan(*, local_executable: bool = False) -> dict[str, object]:
    """Describe the lean local gate before tagging a CI-green release.

    Release verification has two owners that should not be collapsed into a
    single local ritual: PR CI proves the merged code, and the tag publish
    workflow proves the package artifact while publishing it. The local
    preflight only checks the pieces that can drift between "PR is green" and
    "tag is pushed": metadata coherence, public-boundary hygiene, and any
    focused surface checks the changed-file planner requested.
    """

    return {
        "kind": "aippocampus_release_preflight_plan",
        "schema_version": 2,
        "command_mode": "local_executable" if local_executable else "portable",
        "assumption": "Use after the release PR CI is green and before pushing the tag.",
        "gate_policy": {
            "default_local_closeout": "focused_plan_then_pr_once",
            "do_not_stack_quick_before_pr": True,
            "do_not_repeat_ci_owned_gates_after_green_pr": True,
            "broad_pr_benchmark_full_are_escalations": True,
            "publish_workflow_owns_wheel_and_registry_checks": True,
        },
        "local_closeout_sequence": [
            py_script(
                "tools/aippocampus/test_plan.py",
                "--json",
                local_executable=local_executable,
            ),
            "run focused commands named by the plan that have not already passed",
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier pr",
                local_executable=local_executable,
            ),
            py_script(
                "tools/aippocampus/release/check_public_boundary.py",
                "--json",
                local_executable=local_executable,
            ),
            py_script(
                "tools/aippocampus/docs/check_docs_health.py",
                "--json",
                local_executable=local_executable,
            ),
        ],
        "local_required": [
            {
                "command": py_script(
                    "tools/aippocampus/test_plan.py",
                    "--json",
                    local_executable=local_executable,
                ),
                "reason": (
                    "Record the changed-surface plan and run only the focused commands it "
                    "names that have not already passed in CI."
                ),
                "scope": "decision",
            },
            {
                "command": py_script(
                    "tools/aippocampus/docs/check_docs_health.py",
                    "--json",
                    local_executable=local_executable,
                ),
                "reason": "Release notes, docs pointers, and public claims must still resolve.",
                "scope": "release-preflight",
            },
            {
                "command": py_script(
                    "tools/aippocampus/release/check_public_boundary.py",
                    "--json",
                    local_executable=local_executable,
                ),
                "reason": "Scan release-facing tracked files for local paths, credentials, and private strings.",
                "scope": "public-boundary",
            },
            {
                "command": py_script(
                    "tools/aippocampus/release/check_agent_discovery_release.py",
                    "--offline --json",
                    local_executable=local_executable,
                ),
                "reason": (
                    "Before publication, verify local PyPI/MCP metadata without waiting on "
                    "remote indexes that cannot contain the new version yet."
                ),
                "scope": "release-preflight",
            },
            {
                "command": "git clean -ndX",
                "reason": (
                    "Preview ignored generated artifacts; remove only owned build output, "
                    "never private memory surfaces."
                ),
                "scope": "public-boundary",
            },
            {
                "command": "git diff --check",
                "reason": "Catch whitespace/conflict-marker mistakes cheaply before tagging.",
                "scope": "public-boundary",
            },
        ],
        "local_if_ci_unavailable_or_changed_after_ci": [
            {
                "command": CI_RUFF_COMMAND,
                "reason": "CI already owns this for a green PR; rerun locally only if CI is unavailable or stale.",
                "scope": "fallback",
            },
            {
                "command": CI_MYPY_COMMAND,
                "reason": "CI already owns this for a green PR; rerun locally only if CI is unavailable or stale.",
                "scope": "fallback",
            },
            {
                "command": py_script(
                    "tools/aippocampus/run_tests.py",
                    "--tier pr",
                    local_executable=local_executable,
                ),
                "reason": (
                    "`pr` includes `quick`; do not run both as a closeout ritual. CI "
                    "already owns this for a green PR."
                ),
                "scope": "fallback",
            },
        ],
        "ci_owned_do_not_repeat_locally_by_default": [
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier quick",
                local_executable=local_executable,
            ),
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier broad-pr",
                local_executable=local_executable,
            ),
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier benchmark-smoke --benchmark-suite-profile public-fast",
                local_executable=local_executable,
            ),
            py_script(
                "tools/aippocampus/run_coverage.py",
                "--tier pr",
                local_executable=local_executable,
            ),
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier full",
                local_executable=local_executable,
            ),
            "gh workflow run macos-install-smoke.yml -f runner-label=macos-latest -f python-version=3.12",
        ],
        "publish_workflow_owned": [
            py_command('-m pip install -e ".[release]"', local_executable=local_executable),
            py_script(
                "tools/aippocampus/run_tests.py",
                "--tier pr",
                local_executable=local_executable,
            ),
            "check-jsonschema server.json",
            py_command("-m build --sdist --wheel", local_executable=local_executable),
            py_command("-m twine check dist/*", local_executable=local_executable),
            py_script(
                "tools/aippocampus/release/check_wheel_contract.py",
                "--wheel dist/*.whl --json",
                local_executable=local_executable,
            ),
            "PyPI publish",
            "MCP Registry validate and publish",
        ],
        "escalate_locally_when": [
            "Run broad-pr locally only for tier-runner/manifest/CI changes when waiting for CI would hide the failure source.",
            "Run benchmark-smoke locally only for benchmark runner, benchmark fixture, or public benchmark claim changes.",
            "Run full locally only for repository-health or public-readiness claims that explicitly need the slow/benchmark/release-heavy surface.",
            "Run manual macOS install smoke for package/install/path-identity changes, or when the release itself claims fresh macOS install behavior.",
        ],
        "post_publish_required": [
            {
                "command": py_script(
                    "tools/aippocampus/release/check_agent_discovery_release.py",
                    "--wait-ready --wait-seconds 300 --poll-interval 20 "
                    "--fail-on-not-ready --json",
                    local_executable=local_executable,
                ),
                "reason": "After PyPI and MCP Registry publication, remote agent discovery must be claim-ready.",
                "scope": "post-publish",
            },
            {
                "command": py_command(
                    "-m pip index versions aippocampus --no-cache-dir",
                    local_executable=local_executable,
                ),
                "reason": "Confirm PyPI's public simple/index view has caught up before saying latest is available.",
                "scope": "post-publish",
            },
            {
                "command": py_command(
                    "-m pip install aippocampus==<version>",
                    local_executable=local_executable,
                ),
                "reason": "Install the released wheel in a fresh environment, not the checkout.",
                "scope": "post-publish",
            },
        ],
        "boundary": (
            "A routine patch/minor release should not re-run broad-pr, benchmark-smoke, "
            "coverage, full, and manual macOS smoke locally after green PR CI. Those "
            "lanes are escalation tools or CI/publish responsibilities."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan focused AIppocampus verification from changed files.")
    parser.add_argument("--base", default="origin/main", help="Base ref for committed changes.")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Provide an explicit changed file. Repeat for tests or scripted callers.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the plan as JSON.")
    parser.add_argument(
        "--local-executable",
        action="store_true",
        help="Use the exact local Python executable in emitted commands instead of portable python.",
    )
    parser.add_argument(
        "--release-preflight",
        action="store_true",
        help="Emit the lean local gate for a CI-green release before tagging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.release_preflight:
        plan = build_release_preflight_plan(local_executable=args.local_executable)
        if args.json:
            json.dump(plan, sys.stdout, ensure_ascii=False, indent=2)
            print()
            return 0

        print("AIppocampus release preflight plan")
        print(plan["assumption"])
        print("Local required:")
        local_required = cast(list[dict[str, str]], plan["local_required"])
        post_publish_required = cast(
            list[dict[str, str]], plan["post_publish_required"]
        )
        for command in local_required:
            print(f"- {command['command']}")
            print(f"  {command['reason']}")
        print("Post-publish required:")
        for command in post_publish_required:
            print(f"- {command['command']}")
            print(f"  {command['reason']}")
        return 0

    changed_files = (
        sorted({_repo_relative(path) for path in args.changed_file})
        if args.changed_file
        else collect_changed_files(base=args.base)
    )
    plan = build_test_plan(changed_files, local_executable=args.local_executable)
    if args.json:
        json.dump(plan, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print("AIppocampus changed-surface verification plan")
    environment = cast(dict[str, object], plan["python_environment"])
    print(
        "Python: "
        f"local {str(environment['local_python_version'])} / "
        f"CI {str(environment['canonical_ci_python_version'])}"
    )
    warnings = cast(list[dict[str, str]], plan["warnings"])
    commands = cast(list[dict[str, str]], plan["commands"])
    for warning in warnings:
        print(f"Warning: {warning['message']}")
        print(f"Next: {warning['next_action']}")
    print(f"Changed files: {len(changed_files)}")
    for command in commands:
        print(f"- {command['command']}")
        print(f"  {command['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
