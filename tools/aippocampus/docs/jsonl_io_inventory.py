from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Iterable

DIRECT_JSONL_APPROVED_OWNER_PATHS = {
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/claude_code_events.py",
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py",
    "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py",
    "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py",
}
DIRECT_JSONL_APPROVED_OWNER_REASONS = {
    # Claude Code hook logs are host-emitted event records. This module owns the
    # event-log protocol boundary; rows here are not source-backed recall JSONL.
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/claude_code_events.py": (
        "claude_code_host_event_jsonl_protocol_owner"
    ),
    # MCP stdio is JSON-RPC NDJSON. The server owns request parsing and JSON-RPC
    # error responses for malformed protocol frames; this is not source JSONL.
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py": (
        "mcp_json_rpc_stdio_ndjson_protocol_owner"
    ),
    "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py": (
        "source_jsonl_loss_accounting_owner"
    ),
    # Codex app-server stdio is a request/response NDJSON protocol, not
    # source JSONL. The installer owns request-id matching, protocol noise,
    # and timeout accounting for this host boundary.
    "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py": (
        "codex_app_server_ndjson_protocol_owner"
    ),
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


def qualified_call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        owner = qualified_call_name(func.value)
        return f"{owner}.{func.attr}" if owner else func.attr
    return ""


def is_line_like_json_arg(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return "line" in node.id.casefold()
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in {"strip", "rstrip", "lstrip"}:
            return is_line_like_json_arg(node.func.value)
    return False


def is_runtime_path(rel_path: str) -> bool:
    return rel_path.startswith("skills/aippocampus/scripts/aippocampus_runtime/")


def is_approved_direct_jsonl_owner(rel_path: str) -> bool:
    return rel_path in DIRECT_JSONL_APPROVED_OWNER_PATHS


def direct_jsonl_owner_classification(rel_path: str) -> str | None:
    return DIRECT_JSONL_APPROVED_OWNER_REASONS.get(rel_path)


def direct_jsonl_parse_sites_for_path(
    path: Path,
    *,
    repo_root: Path,
) -> list[dict[str, object]]:
    rel_path = repo_relative(path, repo_root=repo_root)
    tree = parse_python(path, repo_root=repo_root)
    if tree is None:
        return []
    sites: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if qualified_call_name(node.func) not in {"json.loads", "loads"}:
            continue
        if not node.args or not is_line_like_json_arg(node.args[0]):
            continue
        approved = is_approved_direct_jsonl_owner(rel_path)
        runtime = is_runtime_path(rel_path)
        owner_classification = direct_jsonl_owner_classification(rel_path)
        sites.append(
            {
                "path": rel_path,
                "line": int(getattr(node, "lineno", 0) or 0),
                "call": qualified_call_name(node.func),
                "approved_owner": approved,
                "runtime_path": runtime,
                "classification": (
                    owner_classification
                    if approved
                    else "unapproved_runtime"
                    if runtime
                    else "non_runtime_line_json"
                ),
                "approved_owner_reason": owner_classification,
            }
        )
    return sites


def direct_jsonl_io_inventory(
    paths: Iterable[Path],
    *,
    repo_root: Path,
    detail: bool = False,
) -> dict[str, object]:
    sites: list[dict[str, object]] = []
    for path in paths:
        sites.extend(direct_jsonl_parse_sites_for_path(path, repo_root=repo_root))
    unapproved_runtime = [
        item
        for item in sites
        if bool(item.get("runtime_path")) and not bool(item.get("approved_owner"))
    ]
    by_class = Counter(str(item["classification"]) for item in sites)
    return {
        "summary": {
            "line_json_parse_site_count": len(sites),
            "approved_owner_count": sum(1 for item in sites if item["approved_owner"]),
            "unapproved_runtime_count": len(unapproved_runtime),
            "non_runtime_line_json_count": by_class.get("non_runtime_line_json", 0),
        },
        "approved_owner_paths": sorted(DIRECT_JSONL_APPROVED_OWNER_PATHS),
        "classification_counts": dict(sorted(by_class.items())),
        "ordinary_json_object_reads": "excluded",
        "warning_policy": (
            "Line-oriented runtime JSON parsing should go through source.io_kernel "
            "or a documented approved owner so malformed rows get counted."
        ),
        "site_sample": sites[:80],
        **({"sites": sites} if detail else {}),
    }
