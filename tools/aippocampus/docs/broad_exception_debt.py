"""Broad-exception debt inventory helpers."""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

TreeParser = Callable[[Path], ast.AST | None]
PathLabeler = Callable[[Path], str]
ExceptionTyper = Callable[[ast.expr | None], set[str]]
HotPathPredicate = Callable[[str], bool]
DiagnosticPredicate = Callable[[ast.ExceptHandler], bool]
MarkerPredicate = Callable[[Path, int, str], bool]


def broad_exception_handlers(
    files: Iterable[Path],
    *,
    parse_python: TreeParser,
    repo_relative: PathLabeler,
    exception_type_names: ExceptionTyper,
    is_hot_path: HotPathPredicate,
    except_handler_has_diagnostic_boundary: DiagnosticPredicate,
    source_window_has_marker: MarkerPredicate,
    boundary_marker: str,
) -> tuple[dict[str, object], ...]:
    handlers: list[dict[str, object]] = []
    for path in files:
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
            line = int(getattr(node, "lineno", 0) or 0)
            handlers.append(
                {
                    "path": rel_path,
                    "line": line,
                    "exception_types": sorted(names),
                    "hot_path": is_hot_path(rel_path),
                    "pure_silent": all(
                        isinstance(stmt, (ast.Pass, ast.Continue)) for stmt in node.body
                    ),
                    "diagnostic_boundary": except_handler_has_diagnostic_boundary(node),
                    "documented_boundary": source_window_has_marker(
                        path,
                        line,
                        boundary_marker,
                    ),
                }
            )
    return tuple(handlers)


def broad_exception_inventory(
    handlers: Iterable[dict[str, object]],
    *,
    detail: bool = False,
) -> dict[str, Any]:
    rows = list(handlers)
    by_file = Counter(str(item["path"]) for item in rows)
    return {
        "summary": {
            "broad_total": len(rows),
            "hot_path_broad_total": sum(1 for item in rows if item["hot_path"]),
            "pure_silent_broad_except_total": sum(1 for item in rows if item["pure_silent"]),
            "hot_path_pure_silent_total": sum(
                1 for item in rows if item["hot_path"] and item["pure_silent"]
            ),
        },
        "top_files": [
            {"path": path, "count": count}
            for path, count in by_file.most_common(20)
        ],
        "handler_sample": rows[:80],
        **({"handlers": rows} if detail else {}),
    }
