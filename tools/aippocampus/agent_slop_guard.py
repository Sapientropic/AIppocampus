#!/usr/bin/env python3
"""Advisory red-light guard for recurring agent-authored patch smells.

The guard is intentionally repo-native and changed-surface first. It should
make likely regressions visible early without turning all historical debt into
one noisy hard gate. Rule families stay narrow; child issues can add fixtures
and rules without inventing another report shape.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = REPO_ROOT / "tools" / "aippocampus" / "agent_slop_guard_baseline.json"
SCHEMA_VERSION = 1
HOT_PATH_PREFIXES = (
    "skills/aippocampus/scripts/aippocampus_runtime/source/",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/",
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/",
    "skills/aippocampus/scripts/aippocampus_runtime/update/",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/",
)
DEFAULT_SCAN_ROOTS = (
    "skills/aippocampus/scripts/aippocampus_runtime",
    "tests/aippocampus",
    "tools/aippocampus",
)
EXCLUDED_IMPLICIT_SCAN_PREFIXES = (
    "tests/aippocampus/agent_slop_guard_fixtures/",
)
DIAGNOSTIC_TOKENS = (
    "error",
    "error_code",
    "error_type",
    "warning",
    "diagnostic",
    "degraded",
    "status",
    "reason",
    "fallback",
    "failed",
    "skipped",
    "loss",
)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    owner_hint: str
    owner_issue: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "owner_hint": self.owner_hint,
            "owner_issue": self.owner_issue,
            "description": self.description,
        }


RULES: dict[str, Rule] = {
    "compact_projector_bypass": Rule(
        rule_id="compact_projector_bypass",
        severity="warning",
        owner_hint=(
            "Route MCP/CLI compact recovery through render_profiled_result or "
            "the compact projection owner; do not return text_result(public_payload(...))."
        ),
        owner_issue="#2696",
        description="MCP/CLI compact path appears to bypass compact/detail projection.",
    ),
    "hot_path_silent_fallback": Rule(
        rule_id="hot_path_silent_fallback",
        severity="warning",
        owner_hint=(
            "Use typed recovery with diagnostics/loss accounting, or baseline the "
            "historical debt to #2629/#2676 before touching this hot path."
        ),
        owner_issue="#2697",
        description="Hot-path broad exception hides failure by continuing or returning empty state.",
    ),
}


def repo_relative(path: Path | str, *, repo_root: Path = REPO_ROOT) -> str:
    value = Path(path)
    try:
        return value.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return value.as_posix().replace("\\", "/")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _contains_call(node: ast.AST, names: set[str]) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _call_name(child.func) in names:
            return True
    return False


def _exception_type_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return {"bare"}
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for item in node.elts:
            names.update(_exception_type_names(item))
        return names
    return set()


def _is_empty_literal(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, (ast.Dict, ast.List, ast.Set, ast.Tuple)):
        return len(getattr(node, "elts", getattr(node, "keys", ()))) == 0
    return isinstance(node, ast.Constant) and node.value in (None, "", False)


def _handler_is_silent_or_empty(handler: ast.ExceptHandler) -> bool:
    if all(isinstance(stmt, (ast.Pass, ast.Continue)) for stmt in handler.body):
        return True
    for stmt in handler.body:
        if isinstance(stmt, ast.Return) and _is_empty_literal(stmt.value):
            return True
    return False


def _handler_has_diagnostic_boundary(handler: ast.ExceptHandler) -> bool:
    body_text = " ".join(ast.dump(stmt, include_attributes=False).casefold() for stmt in handler.body)
    return any(token in body_text for token in DIAGNOSTIC_TOKENS)


def _fingerprint(rule_id: str, path: str, line: int, message: str) -> str:
    return f"{rule_id}:{path}:{line}:{message}"


def _finding(
    *,
    rule_id: str,
    path: str,
    line: int,
    message: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> dict[str, Any]:
    rule = RULES[rule_id]
    fingerprint = _fingerprint(rule_id, path, line, message)
    baseline_owner = baseline.get(fingerprint)
    changed_surface = not changed_files or path in changed_files
    return {
        "rule_id": rule_id,
        "file": path,
        "line": line,
        "severity": rule.severity,
        "owner_hint": rule.owner_hint,
        "owner_issue": baseline_owner or rule.owner_issue,
        "baseline_status": "baselined" if baseline_owner else "new",
        "changed_surface": changed_surface,
        "fingerprint": fingerprint,
        "message": message,
    }


def _compact_projector_bypass_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if "/mcp/" not in f"/{path}" and "agent_" not in Path(path).name:
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) != "text_result":
            continue
        call_args: list[ast.AST] = [*node.args, *(keyword.value for keyword in node.keywords)]
        if not any(_contains_call(arg, {"public_payload"}) for arg in call_args):
            continue
        findings.append(
            _finding(
                rule_id="compact_projector_bypass",
                path=path,
                line=int(getattr(node, "lineno", 0) or 0),
                message="text_result(public_payload(...)) bypasses compact/detail projection.",
                baseline=baseline,
                changed_files=changed_files,
            )
        )
    return findings


def _silent_fallback_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not path.startswith(HOT_PATH_PREFIXES):
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        names = _exception_type_names(node.type)
        if not ({"Exception", "BaseException", "bare"} & names):
            continue
        if not _handler_is_silent_or_empty(node):
            continue
        if _handler_has_diagnostic_boundary(node):
            continue
        findings.append(
            _finding(
                rule_id="hot_path_silent_fallback",
                path=path,
                line=int(getattr(node, "lineno", 0) or 0),
                message="broad exception continues or returns empty state without diagnostics.",
                baseline=baseline,
                changed_files=changed_files,
            )
        )
    return findings


def analyze_text(
    text: str,
    *,
    path: str,
    baseline: Mapping[str, str] | None = None,
    changed_files: set[str] | None = None,
) -> list[dict[str, Any]]:
    baseline_map = baseline or {}
    changed = changed_files or set()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [
            _finding(
                rule_id="hot_path_silent_fallback",
                path=path,
                line=int(exc.lineno or 0),
                message=f"could not parse Python file: {exc.msg}",
                baseline=baseline_map,
                changed_files=changed,
            )
        ]
    findings: list[dict[str, Any]] = []
    findings.extend(
        _compact_projector_bypass_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _silent_fallback_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    return findings


def _scan_roots() -> list[Path]:
    paths: list[Path] = []
    for root in DEFAULT_SCAN_ROOTS:
        paths.extend(
            path
            for path in (REPO_ROOT / root).rglob("*.py")
            if not _is_excluded_implicit_scan_path(repo_relative(path))
        )
    return paths


def _is_excluded_implicit_scan_path(path: str) -> bool:
    return path.startswith(EXCLUDED_IMPLICIT_SCAN_PREFIXES)


def _git_changed_files() -> list[str]:
    commands = (
        ["diff", "--name-only", "--diff-filter=ACMRTUXB", "origin/main...HEAD"],
        ["diff", "--name-only", "--diff-filter=ACMRTUXB"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"],
        ["ls-files", "--others", "--exclude-standard"],
    )
    changed: set[str] = set()
    for command in commands:
        completed = subprocess.run(
            ["git", *command],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            changed.update(line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip())
    return sorted(path for path in changed if not _is_excluded_implicit_scan_path(path))


def scan_files(
    paths: Sequence[Path],
    *,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file() or path.suffix != ".py":
            continue
        rel_path = repo_relative(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(
            analyze_text(
                text,
                path=rel_path,
                baseline=baseline,
                changed_files=changed_files,
            )
        )
    return sorted(findings, key=lambda item: (str(item["file"]), int(item["line"]), str(item["rule_id"])))


def load_baseline(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("findings") or data.get("baseline") or []
    else:
        rows = []
    baseline: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        fingerprint = str(row.get("fingerprint") or "").strip()
        if not fingerprint:
            continue
        baseline[fingerprint] = str(row.get("owner_issue") or row.get("owner") or "historical_baseline")
    return baseline


def run_fixture_root(
    root: Path,
    *,
    baseline: Mapping[str, str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    groups = (
        ("bad", True),
        ("blocked", True),
        ("allowed", False),
        ("allow", False),
    )
    for dirname, expect_findings in groups:
        directory = root / dirname
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            rel_path = path.relative_to(directory).as_posix()
            findings = analyze_text(
                path.read_text(encoding="utf-8"),
                path=rel_path,
                baseline=baseline,
                changed_files={rel_path},
            )
            passed = bool(findings) if expect_findings else not findings
            results.append(
                {
                    "fixture": rel_path,
                    "expectation": "blocked" if expect_findings else "allowed",
                    "passed": passed,
                    "finding_count": len(findings),
                    "rule_ids": sorted({str(item["rule_id"]) for item in findings}),
                }
            )
    return results


def build_report(
    *,
    paths: Sequence[Path],
    changed_files: set[str],
    baseline: Mapping[str, str],
    fixture_root: Path | None = None,
) -> dict[str, Any]:
    findings = scan_files(paths, baseline=baseline, changed_files=changed_files)
    unbaselined = [item for item in findings if item["baseline_status"] != "baselined"]
    changed_unbaselined = [
        item for item in unbaselined if item.get("changed_surface") is True
    ]
    fixture_results = run_fixture_root(fixture_root, baseline=baseline) if fixture_root else []
    fixture_failed = [item for item in fixture_results if item.get("passed") is not True]
    baselined = [item for item in findings if item["baseline_status"] == "baselined"]
    return {
        "kind": "aippocampus_agent_slop_guard",
        "schema_version": SCHEMA_VERSION,
        "advisory": True,
        "ok": not fixture_failed,
        "gate_status": "advisory",
        "rule_count": len(RULES),
        "rules": [rule.as_dict() for rule in RULES.values()],
        "scanned_file_count": len(paths),
        "finding_count": len(findings),
        "baselined_finding_count": len(baselined),
        "unbaselined_finding_count": len(unbaselined),
        "changed_surface_unbaselined_count": len(changed_unbaselined),
        "findings": findings,
        "fixture_results": fixture_results,
        "fixture_failure_count": len(fixture_failed),
        "baseline_policy": (
            "Historical debt may be baselined to owner issues; changed-surface "
            "unbaselined findings are visible by default and become hard only "
            "with --fail-on-violations."
        ),
    }


def _paths_from_args(args: argparse.Namespace) -> tuple[list[Path], set[str], str]:
    if args.all:
        paths = _scan_roots()
        return paths, {repo_relative(path) for path in paths}, "all"
    if args.fixture_root and not args.changed_file:
        return [], set(), "fixtures"
    changed_files = [item.replace("\\", "/") for item in (args.changed_file or [])]
    if not changed_files:
        changed_files = _git_changed_files()
    paths = [(REPO_ROOT / path) for path in changed_files]
    return paths, set(changed_files), "changed_surface"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run advisory AIppocampus agent-slop red lights.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--all", action="store_true", help="Scan default repo Python roots instead of changed files.")
    parser.add_argument("--changed-file", action="append", help="Repo-relative changed file to scan.")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Optional JSON baseline with finding fingerprints. Defaults to the repo baseline.",
    )
    parser.add_argument("--fixture-root", type=Path, help="Optional fixture root with bad/allowed Python files.")
    parser.add_argument(
        "--fail-on-violations",
        action="store_true",
        help="Exit nonzero for unbaselined changed-surface findings. Default is advisory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths, changed_files, mode = _paths_from_args(args)
    baseline = load_baseline(args.baseline or DEFAULT_BASELINE)
    report = build_report(
        paths=paths,
        changed_files=changed_files,
        baseline=baseline,
        fixture_root=args.fixture_root,
    )
    report["mode"] = mode
    output = json.dumps(report, ensure_ascii=False, indent=2 if args.json else None)
    print(output)
    if report["fixture_failure_count"]:
        return 1
    if args.fail_on_violations and report["changed_surface_unbaselined_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
