from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]


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
            "tools/aippocampus/test_tier_manifest.py",
            "tools/aippocampus/test_plan.py",
        }:
            categories.add("test_runner")
        if path.startswith("tests/aippocampus/"):
            categories.add("tests")
        if path.startswith("benchmarks/aippocampus/") or path.startswith("benchmark_corpus/"):
            categories.add("benchmark")
        if path.startswith("tests/aippocampus/test_benchmark"):
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
        if path.startswith("plugins/aippocampus/"):
            categories.add("plugin")
    return categories


def build_test_plan(changed_files: list[str]) -> dict[str, object]:
    normalized_files = [_repo_relative(path) for path in changed_files]
    categories = classify_changed_files(normalized_files)
    commands: list[PlannedCommand] = []
    changed_test_modules = _changed_test_modules(normalized_files)

    if not normalized_files:
        _add_command(
            commands,
            PlannedCommand(
                command="python tools/aippocampus/run_tests.py --tier quick",
                reason="No changed files were detected; quick is the lowest-cost sanity check.",
                scope="sanity",
            ),
        )

    if changed_test_modules:
        _add_command(
            commands,
            PlannedCommand(
                command=f"python -m unittest {' '.join(changed_test_modules)} -v",
                reason="Run changed test modules first so failures point to the edited surface.",
                scope="focused",
            ),
        )

    if "docs" in categories or "skill_surface" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command="python tools/aippocampus/docs/check_docs_health.py --json",
                reason="Docs and skill-surface edits need the documentation health guard.",
                scope="focused",
            ),
        )

    if "test_runner" in categories or "ci_workflow" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=(
                    "python -m unittest "
                    "tests.aippocampus.test_run_tests_tiers "
                    "tests.aippocampus.test_test_plan -v"
                ),
                reason="Test-runner and CI changes must prove the tier/planner contract directly.",
                scope="focused",
            ),
        )
        _add_command(
            commands,
            PlannedCommand(
                command="python tools/aippocampus/run_tests.py --report-json",
                reason="Tier membership/count drift should be visible before a broad run.",
                scope="diagnostic",
            ),
        )

    if "hooks" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=(
                    "python -m unittest "
                    "tests.aippocampus.test_prompt_hook_hot_path "
                    "tests.aippocampus.test_install_prompt_hook "
                    "tests.aippocampus.test_aippocampus_lifecycle_hook -v"
                ),
                reason="Hook edits can affect foreground latency and install behavior.",
                scope="focused",
            ),
        )

    if "mcp" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command="python -m unittest tests.aippocampus.test_aippocampus_mcp_server -v",
                reason="MCP edits need the host-facing tool contract test.",
                scope="focused",
            ),
        )

    if "benchmark" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command=(
                    "python tools/aippocampus/run_tests.py --tier benchmark-smoke "
                    "--benchmark-suite-profile public-fast"
                ),
                reason="Benchmark-adjacent edits need the public-fast benchmark smoke lane.",
                scope="surface",
            ),
        )

    if "runtime" in categories or "plugin" in categories or "skill_surface" in categories:
        _add_command(
            commands,
            PlannedCommand(
                command="python tools/aippocampus/run_tests.py --tier pr",
                reason="Runtime, plugin, and skill edits should pass the fast local PR gate.",
                scope="pre-push",
            ),
        )

    if not commands:
        _add_command(
            commands,
            PlannedCommand(
                command="python tools/aippocampus/run_tests.py --tier quick",
                reason="No specific surface mapping matched; quick is the safe first check.",
                scope="sanity",
            ),
        )

    return {
        "kind": "aippocampus_changed_surface_test_plan",
        "schema_version": 1,
        "changed_files": normalized_files,
        "categories": sorted(categories),
        "commands": [command.as_dict() for command in commands],
        "followup": [
            "Run `python tools/aippocampus/run_tests.py --tier pr` before push when the planner did not already include it.",
            "Let CI own `broad-pr`, benchmark-smoke, platform, and CodeQL coverage unless the changed surface specifically needs a local broad run.",
        ],
        "boundary": (
            "Focused verification is an agent usefulness tool. It does not replace "
            "CI, broad-pr, benchmark-smoke, or release/full lanes."
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    changed_files = (
        sorted({_repo_relative(path) for path in args.changed_file})
        if args.changed_file
        else collect_changed_files(base=args.base)
    )
    plan = build_test_plan(changed_files)
    if args.json:
        json.dump(plan, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print("AIppocampus changed-surface verification plan")
    print(f"Changed files: {len(changed_files)}")
    for command in plan["commands"]:
        print(f"- {command['command']}")
        print(f"  {command['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
