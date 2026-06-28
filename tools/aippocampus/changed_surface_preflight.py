from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import test_plan
from guard_registry import (
    COMMAND_METADATA_KEYS,
    compact_output_budget_for_guard,
    decorate_command,
    phase_for_scope,
)
from test_plan_commands import py_script, shell_arg

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1

SCOPE_PRIORITY = {
    "worktree": 0,
    "static": 10,
    "architecture-debt": 20,
    "changed-surface-debt": 30,
    "changed-surface-advisory": 40,
    "packaged-runtime": 50,
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
    "packaged-runtime",
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
CHANGED_FILE_ARG_RE = re.compile(
    r"\s+--changed-file\s+(?P<path>\"[^\"]+\"|'[^']+'|[^\s]+)"
)
WINDOWS_COMMAND_SOFT_LIMIT = 7000


@dataclass(frozen=True)
class CommandResult:
    command: str
    scope: str
    status: str
    returncode: int
    elapsed_ms: int
    stdout: str
    stderr: str
    metadata: Mapping[str, Any] | None = None

    def compact(self) -> dict[str, Any]:
        metadata = dict(self.metadata or {})
        row: dict[str, Any] = {
            "command": self.command,
            "scope": self.scope,
            "status": self.status,
            "returncode": self.returncode,
            "elapsed_ms": self.elapsed_ms,
        }
        for key in COMMAND_METADATA_KEYS:
            if key in metadata:
                row[key] = metadata[key]
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


def ordered_plan_commands(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    commands = [
        decorate_command(item)
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
    return phase_for_scope(scope)


def _command_runs_in_mode(item: Mapping[str, Any], *, mode: str) -> bool:
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
    planned: Sequence[Mapping[str, Any]],
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
                "gate_classes": [],
                "scopes": [],
            },
        )
        bucket["command_count"] += 1
        scope = str(item.get("scope") or "unknown")
        if scope not in bucket["scopes"]:
            bucket["scopes"].append(scope)
        gate_class = str(item.get("gate_class") or "hard")
        if gate_class not in bucket["gate_classes"]:
            bucket["gate_classes"].append(gate_class)
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


def duplicate_test_modules(planned: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    owners: dict[str, list[dict[str, str]]] = {}
    for item in planned:
        command = str(item.get("command") or "")
        for module in _unittest_modules(command):
            owners.setdefault(module, []).append(
                {
                    "scope": str(item.get("scope") or "unknown"),
                    "command": command,
                    "guard_id": str(item.get("guard_id") or ""),
                    "gate_class": str(item.get("gate_class") or ""),
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
                "severity": "advisory",
                "owner_reason": "multi-owner focused slice",
                "reason": (
                    "module appears in multiple focused slices because it spans "
                    "more than one changed owner surface; run once per closeout "
                    "claim or rely on the explicit closeout/pre-push mode."
                ),
            }
        )
    return duplicates


def duplicate_run_findings(planned: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    by_command: dict[str, list[Mapping[str, Any]]] = {}
    for item in planned:
        command = str(item.get("command") or "")
        if not command:
            continue
        by_command.setdefault(command, []).append(item)
    for command, rows in sorted(by_command.items()):
        if len(rows) > 1:
            findings.append(
                {
                    "kind": "exact_duplicate_command",
                    "severity": "hard",
                    "command": command,
                    "command_count": len(rows),
                    "reason": "The same command is scheduled more than once without an owner reason.",
                }
            )
    commands_text = "\n".join(str(item.get("command") or "") for item in planned)
    if "--tier quick" in commands_text and "--tier pr" in commands_text:
        findings.append(
            {
                "kind": "quick_before_pr_duplicate",
                "severity": "hard",
                "reason": "`pr` includes `quick`; do not require quick immediately before pr.",
            }
        )
    for duplicate in duplicate_test_modules(planned):
        findings.append(
            {
                "kind": "duplicate_focused_module",
                "severity": duplicate["severity"],
                "module": duplicate["module"],
                "command_count": duplicate["command_count"],
                "owner_reason": duplicate["owner_reason"],
                "reason": duplicate["reason"],
            }
        )
    return findings


def duplicate_run_budget(planned: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    findings = duplicate_run_findings(planned)
    hard_findings = [item for item in findings if item.get("severity") == "hard"]
    return {
        "status": "fail" if hard_findings else "pass",
        "hard_finding_count": len(hard_findings),
        "advisory_finding_count": len(findings) - len(hard_findings),
        "findings": findings[:3],
        "policy": (
            "Hard only for exact duplicate commands or quick stacked before pr; "
            "multi-owner focused modules are advisory when an owner reason is present."
        ),
    }


def _unquote_changed_path(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _manifest_command_for_long_changed_surface(command: str) -> tuple[str, Path | None]:
    if (
        len(command) < WINDOWS_COMMAND_SOFT_LIMIT
        or "tools/aippocampus/docs/debt_report.py" not in command
        or "--changed-file " not in command
    ):
        return command, None
    changed_files = [
        _unquote_changed_path(match.group("path"))
        for match in CHANGED_FILE_ARG_RE.finditer(command)
    ]
    if len(changed_files) < 20:
        return command, None
    tmp = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        prefix="aippo-changed-surface-",
        suffix=".txt",
    )
    with tmp:
        tmp.write("\n".join(changed_files))
        tmp.write("\n")
    shortened = CHANGED_FILE_ARG_RE.sub("", command)
    return f"{shortened} --changed-file-list {shell_arg(tmp.name)}", Path(tmp.name)


def run_shell_command(command: str) -> CommandResult:
    run_command, manifest_path = _manifest_command_for_long_changed_surface(command)
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            run_command,
            cwd=REPO_ROOT,
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    finally:
        if manifest_path is not None:
            manifest_path.unlink(missing_ok=True)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return CommandResult(
        command=run_command,
        scope="unknown",
        status="pass" if proc.returncode == 0 else "fail",
        returncode=int(proc.returncode),
        elapsed_ms=elapsed_ms,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        metadata=None,
    )


def _metadata_from_plan_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item[key] for key in COMMAND_METADATA_KEYS if key in item}


def _compact_skipped_command(item: Mapping[str, Any]) -> dict[str, Any]:
    row = {
        "command": item["command"],
        "scope": item["scope"],
    }
    for key in ("gate_class", "verification_owner", "guard_id", "cost_budget", "ci_owned"):
        if key in item:
            row[key] = item[key]
    return row


def _compact_manual_claim(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("gate_class", "verification_owner", "guard_id", "reason")
        if key in item and item[key] not in {None, ""}
    }


def _compact_duplicate_run_budget(report: Mapping[str, Any]) -> dict[str, Any]:
    row = {
        "status": report.get("status"),
        "hard_finding_count": report.get("hard_finding_count", 0),
        "advisory_finding_count": report.get("advisory_finding_count", 0),
    }
    findings = report.get("findings")
    if isinstance(findings, list) and findings:
        first = findings[0]
        if isinstance(first, Mapping):
            row["first_finding"] = {
                key: first[key]
                for key in (
                    "kind",
                    "severity",
                    "module",
                    "command_count",
                    "owner_reason",
                    "reason",
                )
                if key in first
            }
    return row


def _verification_cost(
    *,
    mode: str,
    planned: Sequence[Mapping[str, Any]],
    results: Sequence[CommandResult],
    skipped_by_mode: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    elapsed_ms = sum(result.elapsed_ms for result in results)
    target_ms = 120_000 if mode == DEFAULT_MODE else 600_000
    slow_threshold_ms = 30_000 if mode == DEFAULT_MODE else 90_000
    slow = [
        {
            "command": result.command,
            "scope": result.scope,
            "elapsed_ms": result.elapsed_ms,
            "guard_id": (result.metadata or {}).get("guard_id"),
        }
        for result in sorted(results, key=lambda item: item.elapsed_ms, reverse=True)
        if result.elapsed_ms >= slow_threshold_ms
    ][:3]
    planned_counts: dict[str, int] = {}
    for item in planned:
        budget = str(item.get("cost_budget") or "unknown")
        planned_counts[budget] = planned_counts.get(budget, 0) + 1
    return {
        "status": "over_target" if elapsed_ms > target_ms else "within_target",
        "mode": mode,
        "elapsed_ms": elapsed_ms,
        "target_ms": target_ms,
        "slow_command_count": len(slow),
        "top_slow_commands": slow,
        "planned_cost_budgets": planned_counts,
        "ci_owned_skipped_count": sum(1 for item in skipped_by_mode if item.get("ci_owned")),
        "policy": (
            "Default preflight is a fast early red-light gate; closeout/pre-push may "
            "run slower focused proof. CI-owned broad/benchmark/platform lanes are "
            "not default local rituals."
        ),
    }


def _compact_verification_cost(report: Mapping[str, Any]) -> dict[str, Any]:
    row = {
        "status": report.get("status"),
        "elapsed_ms": report.get("elapsed_ms"),
        "target_ms": report.get("target_ms"),
        "slow_command_count": report.get("slow_command_count", 0),
        "ci_owned_skipped_count": report.get("ci_owned_skipped_count", 0),
    }
    slow = report.get("top_slow_commands")
    if isinstance(slow, list) and slow:
        row["first_slow_command"] = slow[0]
    return row


def _compact_preflight_report(report: Mapping[str, Any]) -> dict[str, Any]:
    compact = {
        "kind": report.get("kind"),
        "schema_version": report.get("schema_version"),
        "ok": report.get("ok"),
        "status": report.get("status"),
        "runnable_gates_status": report.get("runnable_gates_status"),
        "gate_class": report.get("gate_class"),
        "verification_owner": report.get("verification_owner"),
        "guard_id": report.get("guard_id"),
        "owner_doc": report.get("owner_doc"),
        "mode": report.get("mode"),
        "changed_file_count": report.get("changed_file_count"),
        "affected_files": list(report.get("changed_files") or [])[:3],
        "planned_command_count": report.get("planned_command_count"),
        "mode_runnable_command_count": report.get("mode_runnable_command_count"),
        "ran_command_count": report.get("ran_command_count"),
        "skipped_command_count": report.get("skipped_command_count"),
        "skipped_by_mode_count": report.get("skipped_by_mode_count"),
        "first_failure": report.get("first_failure"),
        "manual_required_claim_count": report.get("manual_required_claim_count"),
        "first_manual_required_claim": report.get("first_manual_required_claim"),
        "duplicate_run_budget": _compact_duplicate_run_budget(
            report.get("duplicate_run_budget") or {}
        ),
        "verification_cost": _compact_verification_cost(
            report.get("verification_cost") or {}
        ),
        "compact_output_budget": report.get("compact_output_budget"),
        "detail_command": report.get("detail_command"),
        "closeout_command": report.get("closeout_command"),
    }
    return {key: value for key, value in compact.items() if value not in (None, [])}


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
    caller_supplied_changed_files = bool(changed_files)
    normalized_changed = (
        list(changed_files)
        if changed_files
        else test_plan.collect_changed_files(base=base)
    )
    plan = test_plan.build_test_plan(
        list(normalized_changed),
        local_executable=local_executable,
        diff_check_base=base if not caller_supplied_changed_files else None,
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
            metadata=_metadata_from_plan_item(item),
        )
        results.append(result)
        if result.returncode != 0:
            first_failure = result
            break

    skipped_after_failure = runnable[len(results) :]
    manual_required = [
        item
        for item in list(plan.get("manual_required_claims") or [])
        if isinstance(item, Mapping)
    ]
    runnable_gates_passed = first_failure is None
    ok = runnable_gates_passed and not manual_required
    status = (
        "fail"
        if first_failure is not None
        else "manual_required_pending"
        if manual_required
        else "pass"
    )
    row = CommandResult.full if detail == "full" else CommandResult.compact
    guard_id = "changed-surface-preflight"
    report = {
        "kind": "aippocampus_changed_surface_preflight",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": status,
        "runnable_gates_status": "pass" if runnable_gates_passed else "fail",
        "gate_class": "hard",
        "verification_owner": "local_fail_fast" if selected_mode == DEFAULT_MODE else "local_closeout",
        "guard_id": guard_id,
        "owner_doc": "docs/architecture/ops/guard-lifecycle-registry.md",
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
        "manual_required_claim_count": len(manual_required),
        "first_manual_required_claim": (
            _compact_manual_claim(manual_required[0]) if manual_required else None
        ),
        "manual_required_claims": [
            _compact_manual_claim(item) for item in manual_required
        ] if detail == "full" else [],
        "commands": [row(item) for item in results],
        "skipped_commands": [_compact_skipped_command(item) for item in [*skipped_after_failure, *skipped_by_mode][:5]],
        "skipped_by_mode": [
            {
                "command": item["command"],
                "scope": item["scope"],
                "phase": _phase_for_scope(str(item["scope"])),
                "gate_class": item.get("gate_class"),
                "verification_owner": item.get("verification_owner"),
                "guard_id": item.get("guard_id"),
                "cost_budget": item.get("cost_budget"),
                "ci_owned": item.get("ci_owned"),
                "reason": (
                    "closeout/pre-push proof is explicit; default preflight stays "
                    "fail-fast, red-light, and light focused only."
                ),
            }
            for item in skipped_by_mode
        ],
        "phase_plan": _phase_plan(planned, mode=selected_mode),
        "duplicate_test_modules": duplicate_test_modules(planned),
        "duplicate_run_budget": duplicate_run_budget(planned),
        "verification_cost": _verification_cost(
            mode=selected_mode,
            planned=planned,
            results=results,
            skipped_by_mode=skipped_by_mode,
        ),
        "compact_output_budget": compact_output_budget_for_guard(guard_id),
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
    return _compact_preflight_report(report) if detail == "compact" else report


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
        print(f"  gate: {failure.get('gate_class')} ({failure.get('guard_id')})")
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
    cost = report.get("verification_cost")
    if isinstance(cost, Mapping):
        print(
            "Verification cost: "
            f"{cost.get('status')} {cost.get('elapsed_ms')}ms/"
            f"{cost.get('target_ms')}ms"
        )
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
