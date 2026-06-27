from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import test_plan
from test_plan_commands import py_script, shell_arg

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1

SCOPE_PRIORITY = {
    "worktree": 0,
    "static": 10,
    "architecture-debt": 20,
    "changed-surface-debt": 30,
    "changed-surface-advisory": 40,
    "focused": 60,
    "diagnostic": 80,
    "pre-push": 90,
    "surface": 95,
    "sanity": 100,
}
DEFAULT_MODE = "preflight"
FULL_MODES = {"closeout", "pre-push"}
# Default preflight is an early red-light gate for agents while they are still
# editing. Closeout proof remains in the planner, but it must be explicit so a
# large dirty recall/MCP/APW branch cannot turn every iteration into a slow
# acceptance run.
DEFAULT_PREFLIGHT_BASE_SCOPES = {
    "worktree",
    "static",
    "architecture-debt",
    "changed-surface-debt",
    "changed-surface-advisory",
    "diagnostic",
    "sanity",
}
DEFAULT_PREFLIGHT_LIGHT_FOCUSED_SCOPES = {
    "focused:agent-slop-guard",
    "focused:broad-test-tooling",
    "focused:pr",
}
DEFAULT_PREFLIGHT_MAX_FOCUSED_UNITTEST_MODULES = 2
UNITTEST_MODULE_RE = re.compile(r"-m\s+unittest\s+(?P<modules>.+?)\s+-v\b")


@dataclass(frozen=True)
class CommandResult:
    command: str
    scope: str
    status: str
    returncode: int
    elapsed_ms: int
    stdout: str
    stderr: str

    def compact(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "command": self.command,
            "scope": self.scope,
            "status": self.status,
            "returncode": self.returncode,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.status != "pass":
            row["stdout_tail"] = _tail(self.stdout)
            row["stderr_tail"] = _tail(self.stderr)
        return row

    def full(self) -> dict[str, Any]:
        row = self.compact()
        row["stdout"] = self.stdout
        row["stderr"] = self.stderr
        return row


def _tail(text: str, *, max_lines: int = 24, max_chars: int = 4000) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    lines = cleaned.splitlines()[-max_lines:]
    tail = "\n".join(lines)
    return tail[-max_chars:]


def _scope_rank(scope: str) -> int:
    base = scope.split(":", 1)[0]
    return SCOPE_PRIORITY.get(base, 70)


def ordered_plan_commands(plan: Mapping[str, Any]) -> list[dict[str, str]]:
    commands = [
        {
            "command": str(item.get("command") or ""),
            "scope": str(item.get("scope") or "unknown"),
            "reason": str(item.get("reason") or ""),
        }
        for item in list(plan.get("commands") or [])
        if item.get("command")
    ]
    return [
        item
        for _, item in sorted(
            enumerate(commands),
            key=lambda pair: (_scope_rank(pair[1]["scope"]), pair[0]),
        )
    ]


def _scope_base(scope: str) -> str:
    return scope.split(":", 1)[0]


def _phase_for_scope(scope: str) -> str:
    base = _scope_base(scope)
    if base in {"worktree", "static"}:
        return "fail_fast"
    if base in {
        "architecture-debt",
        "changed-surface-debt",
        "changed-surface-advisory",
    }:
        return "red_light"
    if base in {"pre-push", "surface"}:
        return "closeout"
    if base == "diagnostic":
        return "diagnostic"
    if base == "sanity":
        return "sanity"
    return "focused"


def _command_runs_in_mode(item: Mapping[str, str], *, mode: str) -> bool:
    if mode in FULL_MODES:
        return True
    scope = str(item.get("scope") or "")
    if _scope_base(scope) in DEFAULT_PREFLIGHT_BASE_SCOPES:
        return True
    if scope in DEFAULT_PREFLIGHT_LIGHT_FOCUSED_SCOPES:
        return True
    if scope == "focused":
        modules = _unittest_modules(str(item.get("command") or ""))
        return 0 < len(modules) <= DEFAULT_PREFLIGHT_MAX_FOCUSED_UNITTEST_MODULES
    return False


def _phase_plan(
    planned: Sequence[Mapping[str, str]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in planned:
        phase = _phase_for_scope(str(item.get("scope") or "unknown"))
        bucket = grouped.setdefault(
            phase,
            {
                "phase": phase,
                "command_count": 0,
                "default_run_count": 0,
                "closeout_only_count": 0,
                "scopes": [],
            },
        )
        bucket["command_count"] += 1
        scope = str(item.get("scope") or "unknown")
        if scope not in bucket["scopes"]:
            bucket["scopes"].append(scope)
        if _command_runs_in_mode(item, mode=DEFAULT_MODE):
            bucket["default_run_count"] += 1
        else:
            bucket["closeout_only_count"] += 1
    phase_order = {
        "fail_fast": 0,
        "red_light": 1,
        "focused": 2,
        "diagnostic": 3,
        "sanity": 4,
        "closeout": 5,
    }
    return sorted(
        grouped.values(),
        key=lambda row: phase_order.get(str(row.get("phase") or ""), 99),
    )


def _unittest_modules(command: str) -> list[str]:
    match = UNITTEST_MODULE_RE.search(command)
    if not match:
        return []
    try:
        tokens = shlex.split(match.group("modules"))
    except ValueError:
        tokens = match.group("modules").split()
    return [token for token in tokens if token.startswith("tests.")]


def duplicate_test_modules(planned: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    owners: dict[str, list[dict[str, str]]] = {}
    for item in planned:
        command = str(item.get("command") or "")
        for module in _unittest_modules(command):
            owners.setdefault(module, []).append(
                {
                    "scope": str(item.get("scope") or "unknown"),
                    "command": command,
                }
            )
    duplicates = []
    for module, rows in sorted(owners.items()):
        if len(rows) <= 1:
            continue
        duplicates.append(
            {
                "module": module,
                "command_count": len(rows),
                "scopes": sorted({row["scope"] for row in rows}),
                "reason": (
                    "module appears in multiple focused slices because it spans "
                    "more than one changed owner surface; run once per closeout "
                    "claim or rely on the explicit closeout/pre-push mode."
                ),
            }
        )
    return duplicates


def run_shell_command(command: str) -> CommandResult:
    started = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        shell=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return CommandResult(
        command=command,
        scope="unknown",
        status="pass" if proc.returncode == 0 else "fail",
        returncode=int(proc.returncode),
        elapsed_ms=elapsed_ms,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )


def run_preflight(
    *,
    changed_files: Sequence[str],
    base: str,
    local_executable: bool = False,
    detail: str = "compact",
    mode: str = DEFAULT_MODE,
) -> dict[str, Any]:
    selected_mode = "pre-push" if mode == "prepush" else mode
    if selected_mode not in {DEFAULT_MODE, *FULL_MODES}:
        selected_mode = DEFAULT_MODE
    normalized_changed = (
        list(changed_files)
        if changed_files
        else test_plan.collect_changed_files(base=base)
    )
    plan = test_plan.build_test_plan(
        list(normalized_changed),
        local_executable=local_executable,
    )
    planned = ordered_plan_commands(plan)
    runnable = [item for item in planned if _command_runs_in_mode(item, mode=selected_mode)]
    skipped_by_mode = [item for item in planned if item not in runnable]
    results: list[CommandResult] = []
    first_failure: CommandResult | None = None

    for item in runnable:
        result = run_shell_command(item["command"])
        result = CommandResult(
            command=result.command,
            scope=item["scope"],
            status=result.status,
            returncode=result.returncode,
            elapsed_ms=result.elapsed_ms,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        results.append(result)
        if result.returncode != 0:
            first_failure = result
            break

    skipped_after_failure = runnable[len(results) :]
    ok = first_failure is None
    row = CommandResult.full if detail == "full" else CommandResult.compact
    return {
        "kind": "aippocampus_changed_surface_preflight",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": "pass" if ok else "fail",
        "mode": selected_mode,
        "changed_file_count": len(normalized_changed),
        "changed_files": list(normalized_changed),
        "planned_command_count": len(planned),
        "mode_runnable_command_count": len(runnable),
        "ran_command_count": len(results),
        "skipped_command_count": len(skipped_by_mode) + len(skipped_after_failure),
        "skipped_by_mode_count": len(skipped_by_mode),
        "skipped_after_failure_count": len(skipped_after_failure),
        "first_failure": row(first_failure) if first_failure else None,
        "commands": [row(item) for item in results],
        "skipped_commands": [
            {"command": item["command"], "scope": item["scope"]}
            for item in [*skipped_after_failure, *skipped_by_mode][:5]
        ],
        "skipped_by_mode": [
            {
                "command": item["command"],
                "scope": item["scope"],
                "phase": _phase_for_scope(item["scope"]),
                "reason": (
                    "closeout/pre-push proof is explicit; default preflight stays "
                    "fail-fast, red-light, and light focused only."
                ),
            }
            for item in skipped_by_mode
        ],
        "phase_plan": _phase_plan(planned, mode=selected_mode),
        "duplicate_test_modules": duplicate_test_modules(planned),
        "detail_command": _detail_command(
            normalized_changed,
            base=base,
            local_executable=local_executable,
            mode=selected_mode,
        ),
        "closeout_command": _detail_command(
            normalized_changed,
            base=base,
            local_executable=local_executable,
            mode="closeout",
        ),
        "planner_detail_command": _planner_detail_command(
            normalized_changed,
            base=base,
            local_executable=local_executable,
        ),
        "plan_categories": plan.get("categories") or [],
    }


def _changed_file_args(changed_files: Sequence[str]) -> list[str]:
    args: list[str] = []
    for path in changed_files:
        args.extend(["--changed-file", path])
    return args


def _changed_file_args_text(changed_files: Sequence[str]) -> str:
    return " ".join(f"--changed-file {shell_arg(path)}" for path in changed_files)


def _detail_command(
    changed_files: Sequence[str],
    *,
    base: str,
    local_executable: bool,
    mode: str,
) -> str:
    parts = ["--json", "--detail full"]
    if mode != DEFAULT_MODE:
        parts.extend(["--mode", mode])
    if local_executable:
        parts.append("--local-executable")
    if changed_files:
        parts.append(_changed_file_args_text(changed_files))
    else:
        parts.append(f"--base {shell_arg(base)}")
    return py_script(
        "tools/aippocampus/changed_surface_preflight.py",
        " ".join(parts),
        local_executable=local_executable,
    )


def _planner_detail_command(
    changed_files: Sequence[str],
    *,
    base: str,
    local_executable: bool,
) -> str:
    parts = ["--json", "--detail full"]
    if local_executable:
        parts.append("--local-executable")
    if changed_files:
        parts.append(_changed_file_args_text(changed_files))
    else:
        parts.append(f"--base {shell_arg(base)}")
    return py_script(
        "tools/aippocampus/test_plan.py",
        " ".join(parts),
        local_executable=local_executable,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the changed-surface preflight from the test planner."
    )
    parser.add_argument("--changed-file", action="append", help="Repo-relative changed file.")
    parser.add_argument("--base", default="origin/main", help="Base ref for changed-file discovery.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--detail",
        choices=("compact", "full"),
        default="compact",
        help="Compact is failure-first; full includes complete command stdout/stderr.",
    )
    parser.add_argument(
        "--local-executable",
        action="store_true",
        help="Use the current Python executable in planner commands.",
    )
    parser.add_argument(
        "--mode",
        choices=("preflight", "closeout", "pre-push"),
        default=DEFAULT_MODE,
        help=(
            "preflight runs fail-fast, red-light, diagnostic, and explicitly light "
            "focused probes; closeout/pre-push also run slow focused proof, PR, "
            "pre-push, and surface gates."
        ),
    )
    parser.add_argument(
        "--closeout",
        action="store_true",
        help="Alias for --mode closeout.",
    )
    parser.add_argument(
        "--pre-push",
        action="store_true",
        help="Alias for --mode pre-push.",
    )
    return parser


def _print_text(report: Mapping[str, Any]) -> None:
    status = str(report.get("status") or "unknown")
    print(f"AIppocampus changed-surface preflight: {status}")
    print(f"Changed files: {report.get('changed_file_count')}")
    print(f"Mode: {report.get('mode')}")
    print(
        "Ran: "
        f"{report.get('ran_command_count')} / {report.get('mode_runnable_command_count')} "
        f"(planned {report.get('planned_command_count')})"
    )
    failure = report.get("first_failure")
    if isinstance(failure, Mapping):
        print("First blocker:")
        print(f"  scope: {failure.get('scope')}")
        print(f"  command: {failure.get('command')}")
        if failure.get("stderr_tail"):
            print("  stderr:")
            print(str(failure.get("stderr_tail")))
        if failure.get("stdout_tail"):
            print("  stdout:")
            print(str(failure.get("stdout_tail")))
    else:
        print("No blockers.")
    if report.get("skipped_by_mode_count"):
        print(f"Closeout-only skipped: {report.get('skipped_by_mode_count')}")
        print(f"Closeout: {report.get('closeout_command')}")
    print(f"Detail: {report.get('detail_command')}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    mode = "closeout" if args.closeout else "pre-push" if args.pre_push else str(args.mode)
    report = run_preflight(
        changed_files=list(args.changed_file or []),
        base=str(args.base),
        local_executable=bool(args.local_executable),
        detail=str(args.detail),
        mode=mode,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0 if report["ok"] else int((report.get("first_failure") or {}).get("returncode") or 1)


if __name__ == "__main__":
    raise SystemExit(main())
