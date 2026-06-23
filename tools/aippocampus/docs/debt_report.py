#!/usr/bin/env python3
"""Emit the current architecture debt inventory from markdown budgets."""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE_DEBT_REGISTER = (
    REPO_ROOT / "docs" / "architecture" / "architecture-debt-register.md"
)
ARCHITECTURE_DEBT_SNAPSHOT = (
    REPO_ROOT
    / "docs"
    / "evidence"
    / "reports"
    / "architecture-debt-snapshot-2026-06-04.md"
)
BUDGET_ROW = re.compile(
    r"^\|\s*`(?P<path>[^`]+\.py)`\s*"
    r"\|\s*(?P<first>\d+)\s*\|(?:\s*(?P<second>\d+)\s*\|)?",
    re.MULTILINE,
)
REGISTER_COUNT_ROW = re.compile(
    r"^(?P<prefix>\|\s*`(?P<path>[^`]+\.py)`\s*\|\s*)"
    r"(?P<count>\d+)"
    r"(?P<suffix>\s*\|\s*\d+\s*\|.*)$"
)
REFRESH_REGISTER_COUNTS_COMMAND = (
    "python tools\\aippocampus\\docs\\debt_report.py --refresh-register-counts --write"
)
SMALL_DRIFT_LIMIT = 5
STALE_ALLOWANCE_MIN_BUDGET = 1000
STALE_ALLOWANCE_MAX_CURRENT = 300
STALE_ALLOWANCE_MAX_RATIO = 0.25
SINGLE_DIGIT_GUARD_MARGIN_LIMIT = 9
GIANT_FUNCTION_LINE_LIMIT = 250
SCAN_ROOTS = (
    "skills/aippocampus/scripts/aippocampus_runtime",
    "tests/aippocampus",
    "tools/aippocampus",
    "benchmarks/aippocampus",
)
HOT_PATH_PREFIXES = (
    "skills/aippocampus/scripts/aippocampus_runtime/source/",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/",
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/",
    "skills/aippocampus/scripts/aippocampus_runtime/update/",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/",
)
HELPER_NAME_TO_FAMILY = {
    "_without_empty": "without_empty",
    "_as_list": "as_list",
    "_as_dict": "as_dict",
    "_stable_id": "stable_id",
    "stable_id": "stable_id",
    "stable_hash": "stable_hash",
    "load_json": "json_load",
    "load_json_dict": "json_load",
    "iter_jsonl": "jsonl_read",
    "iter_jsonl_dict_rows": "jsonl_read",
    "iter_jsonl_dict_rows_with_line_numbers": "jsonl_read",
    "load_jsonl_dict_rows": "jsonl_read",
    "write_jsonl": "jsonl_write",
    "write_jsonl_dict_rows": "jsonl_write",
    "_write_json_atomic": "json_atomic_write",
    "write_json_atomic": "json_atomic_write",
    "source_ref_key": "source_ref_key",
    "safe_float": "safe_float",
    "parse_utc": "parse_utc",
}
CANONICAL_HELPER_PATHS = {
    "json_load": {"skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"},
    "jsonl_read": {"skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"},
    "jsonl_write": {"skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"},
    "json_atomic_write": {"skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"},
    "source_ref_key": {"skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"},
    "safe_float": {"skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"},
    "parse_utc": {"skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"},
}
COMPACT_DEBUG_FIELD_LITERALS = (
    "runtime_provenance",
    "source_anchor_gate",
    "operator_detail_command",
    "safe_next_actions",
    "weak_route_recovery_card",
    "apw_recovery_state",
    "last_recall_cache_available",
    "recall_selector_id",
    "route_count",
)
TEST_SCAFFOLD_HELPERS = {
    "run_cli",
    "write_jsonl",
    "source_ref",
    "fake_urlopen",
    "tearDown",
}
LOW_MARGIN_OWNER_ISSUES = {
    "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_action_hint.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domains.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/coding/episode_arc_private_adjudication.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/contracts.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/sync/object_storage/cli.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/ops/provider_doctor.py": "#2548",
    "tests/aippocampus/test_warm_ambient_recall.py": "#2548",
}


def script_line_count(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def inventory_sources() -> list[Path]:
    return [ARCHITECTURE_DEBT_REGISTER, ARCHITECTURE_DEBT_SNAPSHOT]


def budget_entries() -> dict[str, int]:
    entries: dict[str, int] = {}
    for source in inventory_sources():
        text = source.read_text(encoding="utf-8")
        for match in BUDGET_ROW.finditer(text):
            entries[match.group("path")] = int(match.group("second") or match.group("first"))
    return dict(sorted(entries.items()))


def registered_current_counts() -> dict[str, int]:
    """Return human-written current counts from the action register only.

    Budgets are contractual. The current-count column is just a convenience
    for readers, so this report warns on drift instead of letting stale copied
    numbers become another source of truth.
    """

    counts: dict[str, int] = {}
    text = ARCHITECTURE_DEBT_REGISTER.read_text(encoding="utf-8")
    for match in BUDGET_ROW.finditer(text):
        if match.group("second"):
            counts[match.group("path")] = int(match.group("first"))
    return counts


def split_boundary_entries() -> dict[str, str]:
    boundaries: dict[str, str] = {}
    for source in inventory_sources():
        text = source.read_text(encoding="utf-8")
        for line in text.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 5 or not cells[0].startswith("`") or not cells[0].endswith("`"):
                continue
            path = cells[0].strip("`")
            if path.endswith(".py"):
                boundaries.setdefault(path, cells[4])
    return boundaries


def layer_for_path(rel_path: str) -> str:
    if rel_path.startswith("skills/aippocampus/scripts/"):
        return "runtime"
    if rel_path.startswith("tests/"):
        return "tests"
    if rel_path.startswith("benchmarks/"):
        return "benchmarks"
    if rel_path.startswith("docs/"):
        return "docs"
    if rel_path.startswith("tools/"):
        return "tools"
    return "other"


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


@lru_cache(maxsize=1)
def scan_python_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        files.extend(
            path
            for path in base.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return tuple(sorted(files, key=repo_relative))


@lru_cache(maxsize=None)
def parse_python(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=repo_relative(path))
    except (OSError, SyntaxError):
        return None


def is_hot_path(rel_path: str) -> bool:
    return rel_path.startswith(HOT_PATH_PREFIXES)


@lru_cache(maxsize=1)
def helper_definitions() -> tuple[dict[str, object], ...]:
    definitions: list[dict[str, object]] = []
    for path in scan_python_files():
        rel_path = repo_relative(path)
        tree = parse_python(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            family = HELPER_NAME_TO_FAMILY.get(node.name)
            if family is None:
                continue
            definitions.append(
                {
                    "family": family,
                    "name": node.name,
                    "path": rel_path,
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "canonical_owner": rel_path in CANONICAL_HELPER_PATHS.get(family, set()),
                    "hot_path": is_hot_path(rel_path),
                }
            )
    return tuple(definitions)


def helper_duplication_inventory(*, detail: bool = False) -> dict[str, object]:
    definitions = list(helper_definitions())
    families: list[dict[str, object]] = []
    for family in sorted({str(item["family"]) for item in definitions}):
        family_defs = [item for item in definitions if item["family"] == family]
        local_defs = [item for item in family_defs if not item["canonical_owner"]]
        families.append(
            {
                "family": family,
                "definition_count": len(family_defs),
                "local_copy_count": len(local_defs),
                "hot_path_local_copy_count": sum(1 for item in local_defs if item["hot_path"]),
                "canonical_paths": sorted(CANONICAL_HELPER_PATHS.get(family, set())),
                "sample_definitions": family_defs[:20],
            }
        )
    return {
        "summary": {
            "family_count": len(families),
            "definition_count": len(definitions),
            "local_copy_count": sum(
                1 for item in definitions if not bool(item["canonical_owner"])
            ),
            "hot_path_local_copy_count": sum(
                1
                for item in definitions
                if not bool(item["canonical_owner"]) and bool(item["hot_path"])
            ),
        },
        "families": families,
        "definition_sample": definitions[:80],
        **({"definitions": definitions} if detail else {}),
    }


def exception_type_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return {"bare"}
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for element in node.elts:
            names.update(exception_type_names(element))
        return names
    return set()


@lru_cache(maxsize=1)
def broad_exception_handlers() -> tuple[dict[str, object], ...]:
    handlers: list[dict[str, object]] = []
    for path in scan_python_files():
        rel_path = repo_relative(path)
        tree = parse_python(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            names = exception_type_names(node.type)
            if not ({"Exception", "BaseException", "bare"} & names):
                continue
            pure_silent = all(isinstance(stmt, (ast.Pass, ast.Continue)) for stmt in node.body)
            handlers.append(
                {
                    "path": rel_path,
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "exception_types": sorted(names),
                    "hot_path": is_hot_path(rel_path),
                    "pure_silent": pure_silent,
                }
            )
    return tuple(handlers)


def broad_exception_inventory(*, detail: bool = False) -> dict[str, object]:
    handlers = list(broad_exception_handlers())
    by_file = Counter(str(item["path"]) for item in handlers)
    return {
        "summary": {
            "broad_total": len(handlers),
            "hot_path_broad_total": sum(1 for item in handlers if item["hot_path"]),
            "pure_silent_broad_except_total": sum(1 for item in handlers if item["pure_silent"]),
            "hot_path_pure_silent_total": sum(
                1 for item in handlers if item["hot_path"] and item["pure_silent"]
            ),
        },
        "top_files": [
            {"path": path, "count": count}
            for path, count in by_file.most_common(20)
        ],
        "handler_sample": handlers[:80],
        **({"handlers": handlers} if detail else {}),
    }


@lru_cache(maxsize=1)
def compact_debug_field_inventory() -> dict[str, object]:
    occurrences: list[dict[str, object]] = []
    mcp_root = REPO_ROOT / "skills" / "aippocampus" / "scripts" / "aippocampus_runtime" / "mcp"
    if mcp_root.exists():
        for path in sorted(mcp_root.rglob("*.py"), key=repo_relative):
            rel_path = repo_relative(path)
            text = path.read_text(encoding="utf-8")
            for field in COMPACT_DEBUG_FIELD_LITERALS:
                count = text.count(field)
                if count:
                    occurrences.append({"path": rel_path, "field": field, "count": count})
    return {
        "summary": {
            "field_family_count": len({str(item["field"]) for item in occurrences}),
            "occurrence_total": sum(int(item["count"]) for item in occurrences),
            "file_count": len({str(item["path"]) for item in occurrences}),
        },
        "occurrences": occurrences,
        "note": (
            "Static literal inventory only; compact/default behavior is enforced by "
            "MCP profile tests and changed-surface checks."
        ),
    }


@lru_cache(maxsize=1)
def giant_function_inventory() -> dict[str, object]:
    functions: list[dict[str, object]] = []
    for path in scan_python_files():
        rel_path = repo_relative(path)
        if not rel_path.startswith("skills/aippocampus/scripts/aippocampus_runtime/"):
            continue
        tree = parse_python(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            end = getattr(node, "end_lineno", None)
            if end is None:
                continue
            line_count = int(end) - int(node.lineno) + 1
            if line_count >= GIANT_FUNCTION_LINE_LIMIT:
                functions.append(
                    {
                        "path": rel_path,
                        "function": node.name,
                        "line": int(node.lineno),
                        "line_count": line_count,
                    }
                )
    functions.sort(key=lambda item: (-int(item["line_count"]), str(item["path"])))
    return {
        "threshold_lines": GIANT_FUNCTION_LINE_LIMIT,
        "summary": {"function_count": len(functions)},
        "functions": functions,
    }


def test_debt_inventory(*, detail: bool = False) -> dict[str, object]:
    definitions: list[dict[str, object]] = []
    for path in scan_python_files():
        rel_path = repo_relative(path)
        if not rel_path.startswith("tests/aippocampus/"):
            continue
        tree = parse_python(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TEST_SCAFFOLD_HELPERS:
                definitions.append(
                    {
                        "name": node.name,
                        "path": rel_path,
                        "line": int(getattr(node, "lineno", 0) or 0),
                    }
                )
    counts = Counter(str(item["name"]) for item in definitions)
    return {
        "summary": {
            "scaffold_definition_count": len(definitions),
            "duplicate_scaffold_family_count": sum(1 for count in counts.values() if count > 1),
        },
        "families": [
            {"name": name, "definition_count": count}
            for name, count in sorted(counts.items())
        ],
        "definition_sample": definitions[:80],
        **({"definitions": definitions} if detail else {}),
    }


def changed_surface_debt(changed_files: list[str] | None = None) -> dict[str, object]:
    normalized = sorted({path.replace("\\", "/") for path in changed_files or [] if path})
    warnings: list[dict[str, object]] = []
    changed_paths = [
        REPO_ROOT / path
        for path in normalized
        if path.endswith(".py") and (REPO_ROOT / path).is_file()
    ]
    helper_defs: list[dict[str, object]] = []
    broad_handlers: list[dict[str, object]] = []
    giant_functions: list[dict[str, object]] = []
    compact_occurrences: list[dict[str, object]] = []
    for path in changed_paths:
        rel_path = repo_relative(path)
        tree = parse_python(path)
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    family = HELPER_NAME_TO_FAMILY.get(node.name)
                    if family is not None:
                        item = {
                            "family": family,
                            "name": node.name,
                            "path": rel_path,
                            "line": int(getattr(node, "lineno", 0) or 0),
                            "canonical_owner": rel_path
                            in CANONICAL_HELPER_PATHS.get(family, set()),
                            "hot_path": is_hot_path(rel_path),
                        }
                        if not bool(item["canonical_owner"]):
                            helper_defs.append(item)
                    end = getattr(node, "end_lineno", None)
                    if (
                        end is not None
                        and rel_path.startswith("skills/aippocampus/scripts/aippocampus_runtime/")
                    ):
                        line_count = int(end) - int(node.lineno) + 1
                        if line_count >= GIANT_FUNCTION_LINE_LIMIT:
                            giant_functions.append(
                                {
                                    "path": rel_path,
                                    "function": node.name,
                                    "line": int(node.lineno),
                                    "line_count": line_count,
                                }
                            )
                if isinstance(node, ast.ExceptHandler):
                    names = exception_type_names(node.type)
                    if not ({"Exception", "BaseException", "bare"} & names):
                        continue
                    broad_handlers.append(
                        {
                            "path": rel_path,
                            "line": int(getattr(node, "lineno", 0) or 0),
                            "exception_types": sorted(names),
                            "hot_path": is_hot_path(rel_path),
                            "pure_silent": all(
                                isinstance(stmt, (ast.Pass, ast.Continue))
                                for stmt in node.body
                            ),
                        }
                    )
        if "/mcp/" in f"/{rel_path}":
            text = path.read_text(encoding="utf-8")
            for field in COMPACT_DEBUG_FIELD_LITERALS:
                count = text.count(field)
                if count:
                    compact_occurrences.append(
                        {"path": rel_path, "field": field, "count": count}
                    )
    for item in helper_defs:
        warnings.append(
            {
                "code": "changed_surface_duplicate_helper",
                "path": item["path"],
                "line": item["line"],
                "family": item["family"],
                "name": item["name"],
                "acceptance_bearing": True,
                "message": "Touched file defines a duplicate helper; migrate to the canonical owner or document a removal-bound exception.",
            }
        )
    for item in broad_handlers:
        if not (item["hot_path"] or item["pure_silent"]):
            continue
        warnings.append(
            {
                "code": "changed_surface_broad_exception",
                "path": item["path"],
                "line": item["line"],
                "exception_types": item["exception_types"],
                "hot_path": item["hot_path"],
                "pure_silent": item["pure_silent"],
                "acceptance_bearing": True,
                "message": "Touched hot-path or silent broad exception needs typed diagnostics, loss accounting, or a documented process-boundary reason.",
            }
        )
    for item in giant_functions:
        warnings.append(
            {
                "code": "changed_surface_giant_function",
                "path": item["path"],
                "line": item["line"],
                "function": item["function"],
                "line_count": item["line_count"],
                "acceptance_bearing": True,
                "message": "Touched giant runtime function; split or record a responsibility-map decision before growing it.",
            }
        )
    for item in compact_occurrences:
        warnings.append(
            {
                "code": "changed_surface_compact_debug_literal",
                "path": item["path"],
                "field": item["field"],
                "count": item["count"],
                "acceptance_bearing": True,
                "message": "Touched MCP file contains compact/debug field literals; prove compact profile output stays clean or move diagnostics behind detail/operator.",
            }
        )
    return {
        "changed_files": normalized,
        "status": "fail" if warnings else "pass",
        "acceptance_bearing_warning_count": len(warnings),
        "warnings": warnings,
        "policy": (
            "Changed-surface debt warnings are acceptance-bearing; do not treat "
            "readiness as passed until they are resolved or explicitly justified."
        ),
    }


def build_system_weight(
    rows: list[dict[str, object]],
    *,
    split_boundaries: dict[str, str],
) -> dict[str, object]:
    layers: dict[str, dict[str, object]] = {
        name: {
            "tracked_file_count": 0,
            "tracked_lines": 0,
            "guard_budget_total": 0,
            "over_budget_count": 0,
            "near_budget_count": 0,
        }
        for name in ("runtime", "tests", "benchmarks", "docs", "tools")
    }
    archive_or_split_targets: list[dict[str, object]] = []
    near_zero_runtime_split_queue: list[dict[str, object]] = []
    single_digit_guard_pressure: list[dict[str, object]] = []
    for row in rows:
        rel_path = str(row["path"])
        layer = layer_for_path(rel_path)
        if layer not in layers:
            continue
        current = int(row["current_count"])
        budget = int(row["guard_budget"])
        margin = int(row["margin"])
        bucket = layers[layer]
        bucket["tracked_file_count"] = int(bucket["tracked_file_count"]) + 1
        bucket["tracked_lines"] = int(bucket["tracked_lines"]) + current
        bucket["guard_budget_total"] = int(bucket["guard_budget_total"]) + budget
        if bool(row["over_budget"]):
            bucket["over_budget_count"] = int(bucket["over_budget_count"]) + 1
        if layer == "runtime" and margin <= 2:
            near_zero_runtime_split_queue.append(
                {
                    "path": rel_path,
                    "current_count": current,
                    "guard_budget": budget,
                    "margin": margin,
                    "status": (
                        "over_budget"
                        if margin < 0
                        else "exact_zero_guard"
                        if margin == 0
                        else "near_zero_margin"
                    ),
                    "next_split_boundary": split_boundaries.get(
                        rel_path,
                        "Add a focused split boundary to architecture-debt-register.md before growing this owner.",
                    ),
                }
            )
        low_margin_owner = LOW_MARGIN_OWNER_ISSUES.get(rel_path, "")
        if margin <= SINGLE_DIGIT_GUARD_MARGIN_LIMIT:
            single_digit_guard_pressure.append(
                {
                    "path": rel_path,
                    "layer": layer,
                    "current_count": current,
                    "guard_budget": budget,
                    "margin": margin,
                    "owner_issue": low_margin_owner,
                    "tracked_owner_issue": bool(low_margin_owner),
                    "next_split_boundary": split_boundaries.get(
                        rel_path,
                        "Open or assign a focused split owner before growing this file.",
                    ),
                    "recommendation": (
                        "split_trim_or_assign_owner_before_growing_low_margin_guard"
                    ),
                }
            )
        if margin <= max(25, int(budget * 0.08)):
            bucket["near_budget_count"] = int(bucket["near_budget_count"]) + 1
            target = {
                "path": rel_path,
                "layer": layer,
                "current_count": current,
                "guard_budget": budget,
                "margin": margin,
                "recommendation": "split_owner_or_archive_stale_supporting_material",
            }
            if margin <= SINGLE_DIGIT_GUARD_MARGIN_LIMIT:
                target["owner_issue"] = low_margin_owner
                target["tracked_owner_issue"] = bool(low_margin_owner)
            archive_or_split_targets.append(target)
    total_lines = sum(int(layer["tracked_lines"]) for layer in layers.values())
    archive_or_split_targets.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
    near_zero_runtime_split_queue.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
    single_digit_guard_pressure.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
    exact_zero_runtime_count = sum(
        1
        for row in near_zero_runtime_split_queue
        if int(row["margin"]) == 0
    )
    near_zero_runtime_count = sum(
        1
        for row in near_zero_runtime_split_queue
        if 0 < int(row["margin"]) <= 2
    )
    over_budget_runtime_count = sum(
        1
        for row in near_zero_runtime_split_queue
        if int(row["margin"]) < 0
    )
    return {
        "schema_version": "aippocampus-system-weight-v1",
        "total_tracked_lines": total_lines,
        "layers": layers,
        "fresh_agent_load": {
            "tracked_file_count": sum(int(layer["tracked_file_count"]) for layer in layers.values()),
            "tracked_lines": total_lines,
            "interpretation": "tracked large-file surface only; not whole repository LOC",
        },
        "product_proof_audit_research_split": {
            "runtime": "product_runtime",
            "tests": "proof_regression",
            "benchmarks": "proof_benchmark",
            "docs": "architecture_or_research_context",
            "tools": "operator_audit_or_maintenance",
        },
        "archive_or_split_targets": archive_or_split_targets[:20],
        "guard_headroom_summary": {
            "runtime_exact_zero_count": exact_zero_runtime_count,
            "runtime_near_zero_count": near_zero_runtime_count,
            "runtime_over_budget_count": over_budget_runtime_count,
            "runtime_split_queue_count": len(near_zero_runtime_split_queue),
            "single_digit_guard_pressure_count": len(single_digit_guard_pressure),
            "unowned_single_digit_guard_pressure_count": sum(
                1
                for row in single_digit_guard_pressure
                if not row.get("tracked_owner_issue")
            ),
        },
        "near_zero_runtime_split_queue": near_zero_runtime_split_queue,
        "single_digit_guard_pressure": single_digit_guard_pressure,
    }


def count_drift_entries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    current_by_path = {str(row["path"]): int(row["current_count"]) for row in rows}
    budget_by_path = {str(row["path"]): int(row["guard_budget"]) for row in rows}
    drifts: list[dict[str, object]] = []
    for rel_path, registered_count in registered_current_counts().items():
        current_count = current_by_path.get(rel_path)
        if current_count is None or current_count == registered_count:
            continue
        drifts.append(
            {
                "path": rel_path,
                "registered_current_count": registered_count,
                "current_count": current_count,
                "drift": current_count - registered_count,
                "drift_class": drift_class(
                    registered_count=registered_count,
                    current_count=current_count,
                    guard_budget=budget_by_path[rel_path],
                ),
                "recommended_action": drift_recommended_action(
                    registered_count=registered_count,
                    current_count=current_count,
                ),
            }
        )
    return sorted(drifts, key=lambda row: (str(row["path"])))


def refresh_register_count_rows(
    text: str,
    current_counts: dict[str, int],
) -> tuple[str, list[dict[str, object]]]:
    """Refresh only the human-written current-count column in the action register.

    Guard budgets and owner-boundary prose are still human decisions. This helper
    deliberately touches only the first numeric count in register table rows so
    agents do not hand-edit stale counts or accidentally rewrite budgets while
    trying to clear a drift warning.
    """

    changes: list[dict[str, object]] = []
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        newline = ""
        body = line
        if line.endswith("\r\n"):
            body = line[:-2]
            newline = "\r\n"
        elif line.endswith("\n"):
            body = line[:-1]
            newline = "\n"
        match = REGISTER_COUNT_ROW.match(body)
        if not match:
            lines.append(line)
            continue
        rel_path = match.group("path")
        current_count = current_counts.get(rel_path)
        if current_count is None:
            lines.append(line)
            continue
        old_count = int(match.group("count"))
        if old_count == current_count:
            lines.append(line)
            continue
        changes.append(
            {
                "path": rel_path,
                "old_current_count": old_count,
                "current_count": current_count,
                "drift": current_count - old_count,
            }
        )
        lines.append(f"{match.group('prefix')}{current_count}{match.group('suffix')}{newline}")
    return "".join(lines), changes


def refresh_register_counts(*, write: bool = False) -> dict[str, object]:
    report = build_report()
    current_counts = {
        str(row["path"]): int(row["current_count"])
        for row in report["rows"]
        if isinstance(row, dict)
    }
    original = ARCHITECTURE_DEBT_REGISTER.read_text(encoding="utf-8")
    refreshed, changes = refresh_register_count_rows(original, current_counts)
    if write and refreshed != original:
        ARCHITECTURE_DEBT_REGISTER.write_text(refreshed, encoding="utf-8")
    return {
        "ok": True,
        "write": write,
        "changed": bool(changes),
        "changed_count": len(changes),
        "changes": changes,
        "target": ARCHITECTURE_DEBT_REGISTER.relative_to(REPO_ROOT).as_posix(),
        "refresh_command": REFRESH_REGISTER_COUNTS_COMMAND,
    }


def drift_class(
    *,
    registered_count: int,
    current_count: int,
    guard_budget: int,
) -> str:
    drift = current_count - registered_count
    if abs(drift) <= SMALL_DRIFT_LIMIT:
        return "harmless_small_drift"
    if drift > 0:
        return "positive_drift"
    if is_stale_allowance(current_count=current_count, guard_budget=guard_budget):
        return "large_stale_allowance_after_shrink"
    return "negative_drift"


def drift_recommended_action(*, registered_count: int, current_count: int) -> str:
    drift = current_count - registered_count
    if abs(drift) <= SMALL_DRIFT_LIMIT:
        return "refresh_registered_count_when_touching_row"
    if drift > 0:
        return "refresh_current_count_or_split_before_raising_budget"
    return "refresh_current_count_and_check_for_stale_guard_allowance"


def is_stale_allowance(*, current_count: int, guard_budget: int) -> bool:
    if guard_budget < STALE_ALLOWANCE_MIN_BUDGET:
        return False
    return (
        current_count <= STALE_ALLOWANCE_MAX_CURRENT
        and current_count <= int(guard_budget * STALE_ALLOWANCE_MAX_RATIO)
    )


def stale_allowance_entries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    stale_rows: list[dict[str, object]] = []
    for row in rows:
        current = int(row["current_count"])
        budget = int(row["guard_budget"])
        if not is_stale_allowance(current_count=current, guard_budget=budget):
            continue
        stale_rows.append(
            {
                "path": str(row["path"]),
                "current_count": current,
                "guard_budget": budget,
                "margin": int(row["margin"]),
                "budget_to_current_ratio": round(budget / max(current, 1), 2),
                "drift_class": "large_stale_allowance_after_shrink",
                "recommended_action": (
                    "lower_guard_budget_or_archive_row_with_dated_owner_rationale"
                ),
            }
        )
    return sorted(stale_rows, key=lambda row: (str(row["path"])))


def count_drift_summary(count_drifts: list[dict[str, object]]) -> dict[str, int]:
    summary = {
        "harmless_small_drift": 0,
        "positive_drift": 0,
        "negative_drift": 0,
        "large_stale_allowance_after_shrink": 0,
    }
    for row in count_drifts:
        drift_type = str(row.get("drift_class") or "")
        if drift_type in summary:
            summary[drift_type] += 1
    return summary


def report_warnings(
    *,
    headroom_summary: dict[str, object],
    count_drifts: list[dict[str, object]],
    stale_allowances: list[dict[str, object]],
    single_digit_guard_pressure: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    exact_zero = int(headroom_summary.get("runtime_exact_zero_count") or 0)
    near_zero = int(headroom_summary.get("runtime_near_zero_count") or 0)
    if exact_zero:
        warnings.append(
            {
                "code": "runtime_exact_zero_headroom",
                "message": (
                    f"{exact_zero} runtime guard(s) have exact-zero headroom; split an owner before growing them."
                ),
                "count": exact_zero,
            }
        )
    if near_zero:
        warnings.append(
            {
                "code": "runtime_near_zero_headroom",
                "message": (
                    f"{near_zero} runtime guard(s) have only 1-2 lines of headroom; treat them as split-first."
                ),
                "count": near_zero,
            }
        )
    if count_drifts:
        drift_summary = count_drift_summary(count_drifts)
        warnings.append(
            {
                "code": "architecture_debt_register_count_drift",
                "message": (
                    f"{len(count_drifts)} architecture debt register current-count row(s) drift from script_line_count()."
                ),
                "count": len(count_drifts),
                "drift_summary": drift_summary,
                "refresh_command": REFRESH_REGISTER_COUNTS_COMMAND,
            }
        )
    if stale_allowances:
        warnings.append(
            {
                "code": "architecture_debt_stale_allowance",
                "message": (
                    f"{len(stale_allowances)} guard budget row(s) look stale after a split; "
                    "lower the budget or archive the row with a dated owner rationale."
                ),
                "count": len(stale_allowances),
            }
        )
    guard_pressure = list(single_digit_guard_pressure or [])
    if guard_pressure:
        unowned = [row for row in guard_pressure if not row.get("tracked_owner_issue")]
        warnings.append(
            {
                "code": "architecture_debt_single_digit_guard_pressure",
                "message": (
                    f"{len(guard_pressure)} guard budget row(s) have single-digit headroom. "
                    "Touching them should start with a split/trim plan, not late closeout cleanup."
                ),
                "count": len(guard_pressure),
                "unowned_count": len(unowned),
                "owned_count": len(guard_pressure) - len(unowned),
                "sample_paths": [str(row.get("path")) for row in guard_pressure[:5]],
            }
        )
    return warnings


def build_headroom_report(*, detail: str = "summary") -> dict[str, object]:
    entries = budget_entries()
    split_boundaries = split_boundary_entries()
    rows: list[dict[str, object]] = []
    missing_files: list[str] = []
    for rel_path, budget in entries.items():
        path = REPO_ROOT / rel_path
        if not path.exists():
            missing_files.append(rel_path)
            continue
        loc = script_line_count(path)
        rows.append(
            {
                "path": rel_path,
                "guard_budget": budget,
                "current_count": loc,
                "over_budget": loc > budget,
                "margin": budget - loc,
            }
        )
    over_budget = [row for row in rows if row["over_budget"]]
    system_weight = build_system_weight(rows, split_boundaries=split_boundaries)
    headroom_summary = dict(system_weight["guard_headroom_summary"])
    count_drifts = count_drift_entries(rows)
    stale_allowances = stale_allowance_entries(rows)
    warnings = report_warnings(
        headroom_summary=headroom_summary,
        count_drifts=count_drifts,
        stale_allowances=stale_allowances,
        single_digit_guard_pressure=list(
            system_weight["single_digit_guard_pressure"]
        ),
    )
    report = {
        "ok": not missing_files and not over_budget and not stale_allowances,
        "sources": [source.relative_to(REPO_ROOT).as_posix() for source in inventory_sources()],
        "entry_count": len(entries),
        "missing_files": missing_files,
        "over_budget": over_budget,
        "headroom_summary": headroom_summary,
        "count_drift": count_drifts,
        "count_drift_summary": count_drift_summary(count_drifts),
        "stale_allowances": stale_allowances,
        "warnings": warnings,
        "system_weight_summary": {
            "total_tracked_lines": system_weight["total_tracked_lines"],
            "layers": system_weight["layers"],
            "guard_headroom_summary": system_weight["guard_headroom_summary"],
        },
    }
    if detail == "full":
        report["system_weight"] = system_weight
        report["rows"] = rows
    return report


def build_report(
    changed_files: list[str] | None = None,
    *,
    detail: str = "summary",
) -> dict[str, object]:
    headroom = build_headroom_report(detail="full")
    full_detail = detail == "full"
    helper_duplication = helper_duplication_inventory(detail=full_detail)
    broad_exceptions = broad_exception_inventory(detail=full_detail)
    compact_debug_fields = compact_debug_field_inventory()
    giant_functions = giant_function_inventory()
    test_debt = test_debt_inventory(detail=full_detail)
    changed_surface = changed_surface_debt(changed_files)
    warnings = list(headroom["warnings"])
    if changed_surface["acceptance_bearing_warning_count"]:
        warnings.append(
            {
                "code": "changed_surface_debt_acceptance_bearing",
                "message": (
                    "Changed-surface debt warning(s) are acceptance-bearing; "
                    "resolve them or record an explicit owner decision before closeout."
                ),
                "count": changed_surface["acceptance_bearing_warning_count"],
            }
        )
    return {
        "ok": (
            bool(headroom["ok"])
            and not changed_surface["acceptance_bearing_warning_count"]
        ),
        "sources": headroom["sources"],
        "entry_count": headroom["entry_count"],
        "missing_files": headroom["missing_files"],
        "over_budget": headroom["over_budget"],
        "headroom_summary": headroom["headroom_summary"],
        "count_drift": headroom["count_drift"],
        "count_drift_summary": headroom["count_drift_summary"],
        "stale_allowances": headroom["stale_allowances"],
        "warnings": warnings,
        "detail": detail,
        "helper_duplication": helper_duplication,
        "broad_exception_debt": broad_exceptions,
        "compact_debug_field_leaks": compact_debug_fields,
        "giant_hot_path_functions": giant_functions,
        "test_debt_indicators": test_debt,
        "changed_surface": changed_surface,
        "system_weight": headroom["system_weight"],
        "rows": headroom["rows"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--refresh-register-counts",
        action="store_true",
        help=(
            "Refresh only the current script_line_count() column in "
            "docs/architecture/architecture-debt-register.md."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="With --refresh-register-counts, write the refreshed counts to disk.",
    )
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help=(
            "Mark a repo-relative file as part of the changed surface. Repeat to "
            "make helper, broad-exception, compact-field, and giant-function debt "
            "acceptance-bearing for touched files only."
        ),
    )
    parser.add_argument(
        "--detail",
        choices=("summary", "full"),
        default="summary",
        help="Use full only when an operator needs every helper/exception definition.",
    )
    parser.add_argument(
        "--changed-surface-only",
        action="store_true",
        help="Emit only the acceptance-bearing changed-surface debt gate.",
    )
    parser.add_argument(
        "--headroom-only",
        action="store_true",
        help="Emit only the architecture headroom/budget gate without helper scans.",
    )
    args = parser.parse_args()

    if args.refresh_register_counts:
        result = refresh_register_counts(write=bool(args.write))
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            mode = "updated" if args.write else "would update"
            print(f"{mode}: {result['changed_count']} architecture debt register count row(s)")
            if result["changed_count"] and not args.write:
                print(f"write with: {REFRESH_REGISTER_COUNTS_COMMAND}")
        return 0

    if args.changed_surface_only:
        changed_surface = changed_surface_debt(list(args.changed_file or []))
        result = {
            "ok": changed_surface["status"] == "pass",
            "kind": "aippocampus_changed_surface_debt_gate",
            "changed_surface": changed_surface,
        }
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                "changed-surface debt: "
                f"{changed_surface['status']} "
                f"({changed_surface['acceptance_bearing_warning_count']} warning(s))"
            )
        return 0 if result["ok"] else 1

    if args.headroom_only:
        report = build_headroom_report(detail=str(args.detail))
        if args.json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            summary = report["headroom_summary"]
            print(
                "runtime guard headroom: "
                f"exact_zero={summary['runtime_exact_zero_count']} "
                f"near_zero={summary['runtime_near_zero_count']} "
                f"over_budget={summary['runtime_over_budget_count']}"
            )
        return 0 if report["ok"] else 1

    report = build_report(changed_files=list(args.changed_file or []), detail=str(args.detail))
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["rows"]:
            print(
                f"{row['path']}: {row['current_count']}/{row['guard_budget']} "
                f"(margin {row['margin']})"
            )
        summary = report["headroom_summary"]
        print(
            "runtime guard headroom: "
            f"exact_zero={summary['runtime_exact_zero_count']} "
            f"near_zero={summary['runtime_near_zero_count']} "
            f"over_budget={summary['runtime_over_budget_count']}"
        )
        for warning in report["warnings"]:
            print(f"! {warning['code']}: {warning['message']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
