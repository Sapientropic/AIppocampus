from __future__ import annotations

import ast
from typing import Any

from guard_registry import classify_compact_field

SURFACE_PATH_TOKENS = (
    "agent_slop_guard.py",
    "changed_surface_preflight.py",
    "closeout_audit_followthrough.py",
    "debt_report_projection.py",
    "test_plan_projection.py",
    "/mcp/",
    "/cli/",
)
FUNCTION_TOKENS = ("compact", "foreground", "frontstage", "public_payload", "projection")


def _is_surface(path: str, function_name: str) -> bool:
    path_text = path.casefold()
    function_text = function_name.casefold()
    return any(token in path_text for token in SURFACE_PATH_TOKENS) and any(
        token in function_text for token in FUNCTION_TOKENS
    )


def _return_dict_string_keys(node: ast.AST) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, ast.Return) or not isinstance(child.value, ast.Dict):
            continue
        for key in child.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                line = int(getattr(key, "lineno", getattr(child, "lineno", 0)) or 0)
                keys.append((key.value, line))
    return keys


def compact_field_violations(tree: ast.AST, *, path: str) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_surface(path, node.name):
            continue
        for key, line in _return_dict_string_keys(node):
            field_class = classify_compact_field(key)
            if field_class is None:
                violations.append(
                    {
                        "rule_id": "public_compact_field_unclassified",
                        "line": line,
                        "message": f"compact foreground field {key!r} is not classified.",
                    }
                )
            elif field_class != "compact_contract":
                violations.append(
                    {
                        "rule_id": "public_compact_field_misplaced",
                        "line": line,
                        "message": (
                            f"compact foreground field {key!r} is classified as "
                            f"{field_class}; keep it behind detail/operator output."
                        ),
                    }
                )
    return violations
