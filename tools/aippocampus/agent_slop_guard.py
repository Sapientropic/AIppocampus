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
from pathlib import Path
from typing import Any

from agent_slop_compact_fields import compact_field_violations
from agent_slop_guard_rules import OWNER_LAYER_CONTRACTS, RULES
from agent_slop_projection import compact_report

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
PERFORMANCE_HOT_PATH_PREFIXES = (
    "skills/aippocampus/scripts/aippocampus_runtime/navigation/",
    *HOT_PATH_PREFIXES,
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
REGISTRY_WRITER_OWNER_PATHS = {
    "skills/aippocampus/scripts/aippocampus_runtime/registry/store.py",
    "skills/aippocampus/scripts/aippocampus_runtime/registry/api.py",
}
REGISTRY_MUTATION_PREFIXES = (
    "skills/aippocampus/scripts/aippocampus_runtime/registry/",
    "skills/aippocampus/scripts/aippocampus_runtime/sync/",
    "skills/aippocampus/scripts/aippocampus_runtime/update/",
)
# These modules are the documented local-lock owners. Other runtime callers
# should import an owner helper instead of copying os.O_EXCL lock loops.
LOCAL_LOCK_OWNER_PATHS = {
    "skills/aippocampus/scripts/aippocampus_runtime/artifacts/publish.py",
    "skills/aippocampus/scripts/aippocampus_runtime/artifacts/generation_pins.py",
    "skills/aippocampus/scripts/aippocampus_runtime/dream/local_lock.py",
    "skills/aippocampus/scripts/aippocampus_runtime/local_file_lock.py",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/active_recall_lock.py",
    "skills/aippocampus/scripts/aippocampus_runtime/registry/store.py",
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
BROAD_EXCEPTION_BOUNDARY_MARKER = "aippocampus-debt-ok: broad-exception-boundary"
ATOMIC_WRITE_BOUNDARY_MARKER = "aippocampus-agent-slop-ok: directory-replace-boundary"
PERFORMANCE_UNBOUNDED_TOKENS = (
    "candidate",
    "candidates",
    "edge",
    "edges",
    "message",
    "messages",
    "raw_stats",
    "registry",
    "related_terms",
    "rows",
    "source_refs",
    "term_refs",
    "terms",
    "thread",
    "threads",
)
PERFORMANCE_BOUNDED_TOKENS = (
    "budget",
    "bounded",
    "diagnostic",
    "limit",
    "preview",
    "report",
    "sample",
    "top",
)
PERFORMANCE_DB_CALLS = {
    "execute",
    "executemany",
    "upsert_concept",
    "upsert_edge",
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


def _is_performance_hot_path(path: str) -> bool:
    return path.startswith(PERFORMANCE_HOT_PATH_PREFIXES)


def _loop_text(node: ast.For) -> str:
    return f"{_node_name_text(node.target)} {_node_name_text(node.iter)} {' '.join(_constant_strings(node.iter))}".casefold()


def _node_text(node: ast.AST) -> str:
    return f"{_node_name_text(node)} {' '.join(_constant_strings(node))}".casefold()


def _mentions_unbounded_product_collection(text: str) -> bool:
    lowered = text.casefold()
    return any(token in lowered for token in PERFORMANCE_UNBOUNDED_TOKENS)


def _mentions_bounded_context(text: str) -> bool:
    lowered = text.casefold()
    return any(token in lowered for token in PERFORMANCE_BOUNDED_TOKENS)


def _constant_int(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value)
    return None


def _iter_is_bounded(node: ast.AST) -> bool:
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return len(node.elts) <= 12
    if isinstance(node, ast.Subscript):
        return True
    if isinstance(node, ast.Call):
        call = _call_name(node.func)
        if call == "range":
            values = [_constant_int(arg) for arg in node.args]
            if values and all(value is not None for value in values):
                return max(value or 0 for value in values) <= 128
        if call in {"enumerate", "islice"} and node.args:
            return _iter_is_bounded(node.args[0])
    return _mentions_bounded_context(_node_text(node))


def _loop_is_unbounded_product_work(node: ast.For) -> bool:
    text = _loop_text(node)
    return _mentions_unbounded_product_collection(text) and not _iter_is_bounded(node.iter)


def _loop_body_text(node: ast.For) -> str:
    return " ".join(_node_text(stmt) for stmt in node.body).casefold()


def _is_diagnostic_or_report_loop(node: ast.For) -> bool:
    return _mentions_bounded_context(f"{_loop_text(node)} {_loop_body_text(node)}")


def _nested_for_children(node: ast.For) -> list[ast.For]:
    children: list[ast.For] = []
    for stmt in node.body:
        for child in ast.walk(stmt):
            if isinstance(child, ast.For):
                children.append(child)
    return children


def _nested_loop_pair_is_risky(outer_text: str, inner_text: str) -> bool:
    combined = f"{outer_text} {inner_text}".casefold()
    if "raw_stats" in combined and "candidate" in combined:
        return True
    if "raw_stats" in combined and "substring" in combined:
        return True
    if "source_ref" in combined and "existing" in combined:
        return True
    return False


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
    text: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not path.startswith(HOT_PATH_PREFIXES):
        return []
    lines = text.splitlines()
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
        line_no = int(getattr(node, "lineno", 0) or 0)
        if BROAD_EXCEPTION_BOUNDARY_MARKER in _window_text(lines, line_no):
            continue
        findings.append(
            _finding(
                rule_id="hot_path_silent_fallback",
                path=path,
                line=line_no,
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


def _compat_or_legacy_field_name(value: str) -> bool:
    lowered = value.casefold().replace("-", "_")
    if "legacy" in lowered:
        return True
    return "compat" in [part for part in lowered.split("_") if part]


def _atomic_write_owner_bypass_findings(
    tree: ast.AST,
    *,
    path: str,
    text: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_runtime_path(path) or _is_owner_path(path):
        return []
    lines = text.splitlines()
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
                if ATOMIC_WRITE_BOUNDARY_MARKER in _window_text(
                    lines,
                    int(getattr(node, "lineno", 0) or 0),
                ):
                    continue
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


def _registry_writer_owner_bypass_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_runtime_path(path) or path in REGISTRY_WRITER_OWNER_PATHS:
        return []
    if not path.startswith(REGISTRY_MUTATION_PREFIXES):
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
            "load_registry",
            "save_registry",
            "registry_writer_lease",
        }:
            findings.append(
                _finding(
                    rule_id="registry_writer_owner_bypass",
                    path=path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    message=f"local {node.name} duplicates the registry writer owner.",
                    baseline=baseline,
                    changed_files=changed_files,
                )
            )
            continue
        if isinstance(node, ast.Call) and _call_name(node.func) == "save_registry":
            findings.append(
                _finding(
                    rule_id="registry_writer_owner_bypass",
                    path=path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    message="save_registry call outside registry owner can bypass registry_writer_lease.",
                    baseline=baseline,
                    changed_files=changed_files,
                )
            )
    return findings


def _local_lock_owner_bypass_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_runtime_path(path) or path in LOCAL_LOCK_OWNER_PATHS:
        return []
    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _qualified_call_name(node.func) != "os.open":
            continue
        node_text = _node_text(node)
        if "o_excl" not in node_text and ".lock" not in node_text:
            continue
        findings.append(
            _finding(
                rule_id="local_lock_owner_bypass",
                path=path,
                line=int(getattr(node, "lineno", 0) or 0),
                message="os.O_EXCL lock copy bypasses the local-lock owner helpers.",
                baseline=baseline,
                changed_files=changed_files,
            )
        )
    return findings


def _performance_owner_for(path: str, message: str) -> str:
    text = f"{path} {message}".casefold()
    if "association" in text or "raw_stats" in text:
        return "#2705"
    if "continuity_domain" in text or "message" in text or "source_ref" in text:
        return "#2708"
    if "expand" in text or "neighbor" in text or "hub" in text:
        return "#2709"
    if "upsert" in text or "concept" in text or "edge" in text:
        return "#2706"
    if "reset_graph" in text or "rebuild" in text:
        return "#2710"
    return "#2707"


def _performance_finding(
    *,
    rule_id: str,
    path: str,
    line: int,
    message: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> dict[str, Any]:
    finding = _finding(
        rule_id=rule_id,
        path=path,
        line=line,
        message=message,
        baseline=baseline,
        changed_files=changed_files,
    )
    if finding["baseline_status"] == "new":
        finding["owner_issue"] = _performance_owner_for(path, message)
    finding["matched_shape"] = message
    return finding


def _performance_nested_loop_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_performance_hot_path(path):
        return []
    findings: list[dict[str, Any]] = []
    for outer in ast.walk(tree):
        if not isinstance(outer, ast.For):
            continue
        if not _loop_is_unbounded_product_work(outer) or _is_diagnostic_or_report_loop(outer):
            continue
        outer_text = _loop_text(outer)
        for inner in _nested_for_children(outer):
            if not _loop_is_unbounded_product_work(inner) or _is_diagnostic_or_report_loop(inner):
                continue
            inner_text = _loop_text(inner)
            if not _nested_loop_pair_is_risky(outer_text, inner_text):
                continue
            message = f"nested_loop:{outer_text} x {inner_text}"
            findings.append(
                _performance_finding(
                    rule_id="performance_hot_path_nested_loop",
                    path=path,
                    line=int(getattr(inner, "lineno", getattr(outer, "lineno", 0)) or 0),
                    message=message,
                    baseline=baseline,
                    changed_files=changed_files,
                )
            )
    return findings


def _materialized_arg_text(node: ast.Call) -> str:
    if not node.args:
        return ""
    return _node_text(node.args[0])


def _performance_loop_materialization_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_performance_hot_path(path):
        return []
    findings: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For):
            continue
        if not _loop_is_unbounded_product_work(loop) or _is_diagnostic_or_report_loop(loop):
            continue
        for child in ast.walk(loop):
            if not isinstance(child, ast.Call):
                continue
            call = _call_name(child.func)
            if call not in {"list", "sorted"}:
                continue
            arg_text = _materialized_arg_text(child)
            if not _mentions_unbounded_product_collection(arg_text):
                continue
            if child.args and _iter_is_bounded(child.args[0]):
                continue
            message = f"loop_materialization:{call}({arg_text}) inside {_loop_text(loop)}"
            key = (int(getattr(child, "lineno", getattr(loop, "lineno", 0)) or 0), call)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                _performance_finding(
                    rule_id="performance_hot_path_loop_materialization",
                    path=path,
                    line=int(getattr(child, "lineno", getattr(loop, "lineno", 0)) or 0),
                    message=message,
                    baseline=baseline,
                    changed_files=changed_files,
                )
            )
    return findings


def _performance_db_work_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    if not _is_performance_hot_path(path):
        return []
    findings: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For):
            continue
        if not _loop_is_unbounded_product_work(loop) or _is_diagnostic_or_report_loop(loop):
            continue
        for child in ast.walk(loop):
            if not isinstance(child, ast.Call):
                continue
            qname = _qualified_call_name(child.func)
            call = _call_name(child.func)
            if call not in PERFORMANCE_DB_CALLS and not qname.endswith(".execute"):
                continue
            # A local resolver/cache wrapper is the accepted #2706 shape; the
            # red light is for direct DB/upsert work in the product loop.
            if call in {"resolve", "resolve_concept"}:
                continue
            message = f"loop_db_work:{qname or call} inside {_loop_text(loop)}"
            key = (int(getattr(child, "lineno", getattr(loop, "lineno", 0)) or 0), qname or call)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                _performance_finding(
                    rule_id="performance_hot_path_repeated_db_work",
                    path=path,
                    line=int(getattr(child, "lineno", getattr(loop, "lineno", 0)) or 0),
                    message=message,
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
                if not _compat_or_legacy_field_name(lowered):
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


def _public_compact_field_findings(
    tree: ast.AST,
    *,
    path: str,
    baseline: Mapping[str, str],
    changed_files: set[str],
) -> list[dict[str, Any]]:
    return [
        _finding(
            rule_id=str(item["rule_id"]),
            path=path,
            line=int(item["line"]),
            message=str(item["message"]),
            baseline=baseline,
            changed_files=changed_files,
        )
        for item in compact_field_violations(tree, path=path)
    ]


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
            text=text,
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
            text=text,
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
        _registry_writer_owner_bypass_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _local_lock_owner_bypass_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _performance_nested_loop_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _performance_loop_materialization_findings(
            tree,
            path=path,
            baseline=baseline_map,
            changed_files=changed,
        )
    )
    findings.extend(
        _performance_db_work_findings(
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
    findings.extend(
        _public_compact_field_findings(
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
        # Some AST-derived fingerprints include multiline SQL or trailing
        # expression whitespace. Preserve the exact string or the baseline turns
        # into permanent noise whenever those findings are present.
        raw_fingerprint = row.get("fingerprint")
        fingerprint = "" if raw_fingerprint is None else str(raw_fingerprint)
        if not fingerprint.strip():
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
        "owner_layer_contracts": list(OWNER_LAYER_CONTRACTS),
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


def apply_hard_gate_semantics(report: dict[str, Any], *, fail_on_violations: bool) -> None:
    if report.get("fixture_failure_count"):
        report["ok"] = False
        report["gate_status"] = "failed"
        report["advisory"] = False
        return
    if fail_on_violations and report.get("changed_surface_unbaselined_count"):
        report["ok"] = False
        report["gate_status"] = "failed"
        report["advisory"] = False
        report["failure_reason"] = "changed_surface_unbaselined_findings"


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
    parser.add_argument(
        "--detail",
        choices=("compact", "full"),
        default="compact",
        help="Compact is failure-first; full includes rule catalogs and owner contracts.",
    )
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


def _detail_command(args: argparse.Namespace) -> str:
    parts = ["python", "tools/aippocampus/agent_slop_guard.py", "--json", "--detail", "full"]
    if args.all:
        parts.append("--all")
    for path in args.changed_file or []:
        parts.extend(["--changed-file", path])
    if args.fixture_root:
        parts.extend(["--fixture-root", str(args.fixture_root)])
    if args.fail_on_violations:
        parts.append("--fail-on-violations")
    return " ".join(parts)


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
    apply_hard_gate_semantics(report, fail_on_violations=bool(args.fail_on_violations))
    payload: Mapping[str, Any] = (
        report
        if args.detail == "full"
        else compact_report(report, detail_command=_detail_command(args))
    )
    output = json.dumps(payload, ensure_ascii=False, indent=2 if args.json else None)
    print(output)
    if report["fixture_failure_count"]:
        return 1
    if args.fail_on_violations and report["changed_surface_unbaselined_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
