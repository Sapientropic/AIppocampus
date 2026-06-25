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
RUNTIME_PREFIX = "skills/aippocampus/scripts/aippocampus_runtime/"
SOURCE_IO_OWNER_PATHS = {
    "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py",
    "skills/aippocampus/scripts/aippocampus_runtime/io_integrity.py",
    "skills/aippocampus/scripts/aippocampus_runtime/question/source_refs.py",
    "skills/aippocampus/scripts/aippocampus_runtime/dream/source_refs.py",
}
SOURCE_REF_HELPER_NAMES = {
    "source_ref_key",
    "source_ref_key_set",
    "clean_source_ref",
    "clean_source_refs",
    "normalize_source_refs",
    "merge_source_refs",
    "source_ref_fingerprint",
    "source_ref_digest",
}
COMPAT_FIELD_TOKENS = ("compat", "legacy")
COMPAT_METADATA_TOKENS = ("owner", "removal", "default", "exposure")
FIELD_ONLY_TEST_PATH_TOKENS = (
    "apw",
    "deepen",
    "foreground",
    "mcp",
    "open",
    "recall",
    "source_open",
    "source_reopen",
)
FIELD_ONLY_ASSERT_KEYS = {
    "recall_selector",
    "recall_selector_available",
    "recall_selector_id",
    "route_count",
    "selector",
    "source_backed",
    "source_ref_count",
}
COMPACT_DEBUG_KEYS = {
    "cache",
    "debug",
    "feedback_controls",
    "operator_detail_command",
    "operator_detail_command_template",
    "policy_matrix",
    "runtime_provenance",
    "selector_inventory",
}
FOLLOW_THROUGH_TOKENS = {
    "agent_deepen",
    "agent_open",
    "assert_cli_recall_deepens_to_source",
    "assert_deepen_opened_expected_source",
    "assert_mcp_recall_deepens_to_source",
    "opened_anchor_hits",
    "source_anchor_gate",
    "source_window",
    "target_source_matched",
    "window_terms",
}
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
    "source_jsonl_owner_bypass": Rule(
        rule_id="source_jsonl_owner_bypass",
        severity="warning",
        owner_hint=(
            "Use aippocampus_runtime.source.io_kernel.load_jsonl_dict_rows, "
            "load_jsonl_dict_rows_with_line_field, or an approved source IO wrapper."
        ),
        owner_issue="#2698",
        description="Source-backed JSONL appears to be parsed line-by-line outside the IO kernel.",
    ),
    "atomic_write_owner_bypass": Rule(
        rule_id="atomic_write_owner_bypass",
        severity="warning",
        owner_hint=(
            "Use aippocampus_runtime.io_integrity.prepared_atomic_replace or "
            "atomic_write_* helpers instead of fixed .tmp files or ad hoc replace/rename."
        ),
        owner_issue="#2698",
        description="Runtime writer appears to bypass shared atomic write helpers.",
    ),
    "source_ref_helper_duplicate": Rule(
        rule_id="source_ref_helper_duplicate",
        severity="warning",
        owner_hint=(
            "Reuse source.io_kernel source-ref helpers or a documented owner wrapper; "
            "do not grow local source-ref key/normalization copies."
        ),
        owner_issue="#2698",
        description="Local source-ref key/normalization helper duplicates the source-ref owner.",
    ),
    "compat_field_metadata_missing": Rule(
        rule_id="compat_field_metadata_missing",
        severity="warning",
        owner_hint=(
            "Compatibility fields need nearby owner, removal condition, and default "
            "exposure boundary metadata; do not expose aliases in compact foreground by habit."
        ),
        owner_issue="#2699",
        description="Compatibility/legacy field is missing owner/removal/default exposure metadata.",
    ),
    "field_only_followthrough_test": Rule(
        rule_id="field_only_followthrough_test",
        severity="warning",
        owner_hint=(
            "Use product_probe_helpers recall/deepen/open assertions or another real "
            "follow-through probe before treating fields, route counts, or selectors as success."
        ),
        owner_issue="#2699",
        description="Recall/MCP/APW/source-open test appears to assert payload fields without follow-through.",
    ),
    "compact_debug_field_test": Rule(
        rule_id="compact_debug_field_test",
        severity="warning",
        owner_hint=(
            "Compact foreground tests should assert action-sized behavior; detail/operator "
            "debug fields belong behind full/detail profiles or frontstage assertions."
        ),
        owner_issue="#2699",
        description="Compact foreground test appears to require debug/operator fields.",
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


def _qualified_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
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


def _constant_strings(node: ast.AST) -> list[str]:
    values: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            values.append(child.value)
    return values


def _node_name_text(node: ast.AST) -> str:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.append(child.id)
        elif isinstance(child, ast.Attribute):
            names.append(child.attr)
    return " ".join(names).casefold()


def _is_runtime_path(path: str) -> bool:
    return path.startswith(RUNTIME_PREFIX)


def _is_owner_path(path: str, owners: set[str] = SOURCE_IO_OWNER_PATHS) -> bool:
    return path in owners


def _is_line_like_json_arg(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        name = node.id.casefold()
        return name in {"line", "raw_line", "json_line", "jsonl_line"} or name.endswith("_line")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr in {"strip", "rstrip"} and _is_line_like_json_arg(node.func.value)
    return False


def _window_text(lines: list[str], line_no: int, *, radius: int = 5) -> str:
    start = max(0, line_no - radius - 1)
    end = min(len(lines), line_no + radius)
    return "\n".join(lines[start:end]).casefold()


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


def _source_jsonl_owner_bypass_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_runtime_path(path) or _is_owner_path(path):
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _qualified_call_name(node.func) not in {"json.loads", "loads"}:
            continue
        if not node.args or not _is_line_like_json_arg(node.args[0]):
            continue
        findings.append(
            _finding(
                rule_id="source_jsonl_owner_bypass",
                path=path,
                line=int(getattr(node, "lineno", 0) or 0),
                message="json.loads(line) bypasses source IO kernel loss accounting.",
                baseline=baseline,
                changed_files=changed_files,
            )
        )
    return findings


def _node_mentions_tmp(node: ast.AST) -> bool:
    text = " ".join([_node_name_text(node), *_constant_strings(node)]).casefold()
    return "tmp" in text or "temp" in text or "staged" in text


def _atomic_write_owner_bypass_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_runtime_path(path) or _is_owner_path(path):
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        qname = _qualified_call_name(node.func)
        if qname in {"os.replace", "os.rename"}:
            findings.append(
                _finding(
                    rule_id="atomic_write_owner_bypass",
                    path=path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    message="os.replace/os.rename bypasses shared atomic write helpers.",
                    baseline=baseline,
                    changed_files=changed_files,
                )
            )
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"replace", "rename"}:
            if len(node.args) == 1 and _node_mentions_tmp(node.func.value):
                findings.append(
                    _finding(
                        rule_id="atomic_write_owner_bypass",
                        path=path,
                        line=int(getattr(node, "lineno", 0) or 0),
                        message="tmp Path.replace/rename bypasses shared atomic write helpers.",
                        baseline=baseline,
                        changed_files=changed_files,
                    )
                )
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"with_name", "with_suffix"}:
            if any(".tmp" in value.casefold() for value in _constant_strings(node)):
                findings.append(
                    _finding(
                        rule_id="atomic_write_owner_bypass",
                        path=path,
                        line=int(getattr(node, "lineno", 0) or 0),
                        message="fixed .tmp staging path bypasses shared atomic write helpers.",
                        baseline=baseline,
                        changed_files=changed_files,
                    )
                )
    return findings


def _source_ref_helper_duplicate_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_runtime_path(path) or _is_owner_path(path):
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in SOURCE_REF_HELPER_NAMES:
            continue
        findings.append(
            _finding(
                rule_id="source_ref_helper_duplicate",
                path=path,
                line=int(getattr(node, "lineno", 0) or 0),
                message=f"local {node.name} helper duplicates the source-ref owner.",
                baseline=baseline,
                changed_files=changed_files,
            )
        )
    return findings


def _compat_field_metadata_missing_findings(
    tree: ast.AST,
    *,
    path: str,
    text: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_runtime_path(path):
        return []
    lines = text.splitlines()
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if key is None:
                continue
            for value in _constant_strings(key):
                lowered = value.casefold()
                if not any(token in lowered for token in COMPAT_FIELD_TOKENS):
                    continue
                line_no = int(getattr(key, "lineno", getattr(node, "lineno", 0)) or 0)
                window = _window_text(lines, line_no)
                if all(token in window for token in COMPAT_METADATA_TOKENS):
                    continue
                findings.append(
                    _finding(
                        rule_id="compat_field_metadata_missing",
                        path=path,
                        line=line_no,
                        message=(
                            "compatibility/legacy field lacks owner/removal/default exposure metadata."
                        ),
                        baseline=baseline,
                        changed_files=changed_files,
                    )
                )
    return findings


def _assert_call_key_literals(node: ast.Call) -> set[str]:
    call_name = _call_name(node.func)
    if not call_name.startswith("assert") or call_name.startswith("assertNot"):
        return set()
    values = {value.casefold() for value in _constant_strings(node)}
    for child in ast.walk(node):
        if isinstance(child, ast.Subscript):
            values.update(value.casefold() for value in _constant_strings(child.slice))
    return values


def _function_has_followthrough(node: ast.AST) -> bool:
    body_text = " ".join([_node_name_text(node), *(_constant_strings(node))]).casefold()
    return any(token in body_text for token in FOLLOW_THROUGH_TOKENS)


def _test_scope_is_followthrough_sensitive(path: str, name: str) -> bool:
    if not path.startswith("tests/aippocampus/"):
        return False
    if path == "tests/aippocampus/product_probe_helpers.py":
        return False
    text = f"{path}/{name}".casefold()
    return any(token in text for token in FIELD_ONLY_TEST_PATH_TOKENS)


def _field_only_test_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _test_scope_is_followthrough_sensitive(path, node.name):
            continue
        asserted_keys: set[str] = set()
        first_key_line = int(getattr(node, "lineno", 0) or 0)
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            keys = _assert_call_key_literals(child)
            if not keys:
                continue
            matched = (keys & FIELD_ONLY_ASSERT_KEYS) | (keys & COMPACT_DEBUG_KEYS)
            if matched and first_key_line == int(getattr(node, "lineno", 0) or 0):
                first_key_line = int(getattr(child, "lineno", first_key_line) or first_key_line)
            asserted_keys.update(matched)
        if not asserted_keys:
            continue
        has_followthrough = _function_has_followthrough(node)
        compact_context = "compact" in f"{path}/{node.name}".casefold()
        debug_keys = asserted_keys & COMPACT_DEBUG_KEYS
        if debug_keys and compact_context:
            findings.append(
                _finding(
                    rule_id="compact_debug_field_test",
                    path=path,
                    line=first_key_line,
                    message="compact foreground test requires detail/operator/debug fields.",
                    baseline=baseline,
                    changed_files=changed_files,
                )
            )
            continue
        field_keys = asserted_keys & FIELD_ONLY_ASSERT_KEYS
        if field_keys and not has_followthrough:
            findings.append(
                _finding(
                    rule_id="field_only_followthrough_test",
                    path=path,
                    line=first_key_line,
                    message="payload field assertions lack deepen/open/source follow-through.",
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
    findings.extend(
        _source_jsonl_owner_bypass_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _atomic_write_owner_bypass_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _source_ref_helper_duplicate_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _compat_field_metadata_missing_findings(
            tree,
            path=path,
            text=text,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _field_only_test_findings(
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
