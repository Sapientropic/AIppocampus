from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import test_plan

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
) -> dict[str, Any]:
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
    results: list[CommandResult] = []
    first_failure: CommandResult | None = None

    for item in planned:
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

    skipped = planned[len(results) :]
    ok = first_failure is None
    row = CommandResult.full if detail == "full" else CommandResult.compact
    return {
        "kind": "aippocampus_changed_surface_preflight",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": "pass" if ok else "fail",
        "changed_file_count": len(normalized_changed),
        "changed_files": list(normalized_changed),
        "planned_command_count": len(planned),
        "ran_command_count": len(results),
        "skipped_command_count": len(skipped),
        "first_failure": row(first_failure) if first_failure else None,
        "commands": [row(item) for item in results],
        "skipped_commands": [
            {"command": item["command"], "scope": item["scope"]}
            for item in skipped[:5]
        ],
        "detail_command": _detail_command(
            normalized_changed,
            base=base,
            local_executable=local_executable,
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


def _detail_command(
    changed_files: Sequence[str],
    *,
    base: str,
    local_executable: bool,
) -> str:
    parts = ["python", "tools/aippocampus/changed_surface_preflight.py", "--json", "--detail", "full"]
    if local_executable:
        parts.append("--local-executable")
    if changed_files:
        parts.extend(_changed_file_args(changed_files))
    else:
        parts.extend(["--base", base])
    return " ".join(parts)


def _planner_detail_command(
    changed_files: Sequence[str],
    *,
    base: str,
    local_executable: bool,
) -> str:
    parts = ["python", "tools/aippocampus/test_plan.py", "--json", "--detail", "full"]
    if local_executable:
        parts.append("--local-executable")
    if changed_files:
        parts.extend(_changed_file_args(changed_files))
    else:
        parts.extend(["--base", base])
    return " ".join(parts)


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
    return parser


def _print_text(report: Mapping[str, Any]) -> None:
    status = str(report.get("status") or "unknown")
    print(f"AIppocampus changed-surface preflight: {status}")
    print(f"Changed files: {report.get('changed_file_count')}")
    print(f"Ran: {report.get('ran_command_count')} / {report.get('planned_command_count')}")
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
    print(f"Detail: {report.get('detail_command')}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_preflight(
        changed_files=list(args.changed_file or []),
        base=str(args.base),
        local_executable=bool(args.local_executable),
        detail=str(args.detail),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0 if report["ok"] else int((report.get("first_failure") or {}).get("returncode") or 1)


if __name__ == "__main__":
    raise SystemExit(main())
