from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

GIANT_FUNCTION_LINE_LIMIT = 250
TEST_SCAFFOLD_HELPERS = {
    "run_cli",
    "write_jsonl",
    "source_ref",
    "fake_urlopen",
    "tearDown",
}


def repo_relative(path: Path, *, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def parse_python(path: Path, *, repo_root: Path) -> ast.AST | None:
    try:
        return ast.parse(
            path.read_text(encoding="utf-8"),
            filename=repo_relative(path, repo_root=repo_root),
        )
    except (OSError, SyntaxError):
        return None


def compact_debug_field_inventory(
    *,
    mcp_root: Path,
    repo_root: Path,
    compact_debug_field_literals: Sequence[str],
) -> dict[str, object]:
    occurrences: list[dict[str, object]] = []
    if mcp_root.exists():
        for path in sorted(mcp_root.rglob("*.py"), key=lambda item: repo_relative(item, repo_root=repo_root)):
            rel_path = repo_relative(path, repo_root=repo_root)
            text = path.read_text(encoding="utf-8")
            for field in compact_debug_field_literals:
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


def giant_function_inventory(
    paths: Iterable[Path],
    *,
    repo_root: Path,
) -> dict[str, object]:
    functions: list[dict[str, object]] = []
    for path in paths:
        rel_path = repo_relative(path, repo_root=repo_root)
        if not rel_path.startswith("skills/aippocampus/scripts/aippocampus_runtime/"):
            continue
        tree = parse_python(path, repo_root=repo_root)
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


def test_debt_inventory(
    paths: Iterable[Path],
    *,
    repo_root: Path,
    detail: bool = False,
) -> dict[str, object]:
    definitions: list[dict[str, object]] = []
    for path in paths:
        rel_path = repo_relative(path, repo_root=repo_root)
        if not rel_path.startswith("tests/aippocampus/"):
            continue
        tree = parse_python(path, repo_root=repo_root)
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
