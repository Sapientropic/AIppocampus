"""Static guard for external-model cache-contract call sites.

The runtime chat client already rejects DeepSeek calls without an explicit
cache contract, but that happens late. This audit catches drift earlier: a new
model-backed call site must either pass ``cache_contract=`` at the invocation
surface or appear in the public inventory with an explicit route-owned policy.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.model.routing import (
    model_call_site_cache_contract_inventory,
)

DEFAULT_SCAN_PATHS = (
    "skills/aippocampus/scripts/aippocampus_runtime",
    "benchmarks/aippocampus",
)
LIVE_MODEL_CALLS_REQUIRING_CACHE_CONTRACT = {
    "ChatClientConfig",
    "call_chat_json",
}
REQUIRED_INVENTORY_FIELDS = {
    "call_site",
    "path",
    "owner",
    "purpose",
    "route_source",
    "cache_contract",
    "usage_telemetry",
}
INVENTORY_OPT_OUT_MARKERS = (
    "none",
    "provider-derived",
    "route_cache_contract(route)",
    "deepseek_prefix_v1",
)


@dataclass(frozen=True)
class ModelCacheContractCallSite:
    path: str
    line: int
    call: str
    cache_contract: str
    inventory_call_site: str
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "call": self.call,
            "cache_contract": self.cache_contract,
            "inventory_call_site": self.inventory_call_site,
            "status": self.status,
        }


def _repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _iter_scan_files(repo_root: Path, scan_paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for item in scan_paths:
        path = repo_root / item
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if not path.is_dir():
            continue
        files.extend(
            candidate
            for candidate in path.rglob("*.py")
            if "__pycache__" not in candidate.parts
        )
    return sorted(files, key=lambda value: _repo_relative(value, repo_root))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _cache_contract_keyword(call: ast.Call) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == "cache_contract":
            return keyword.value
    return None


def _safe_contract_label(value: ast.AST | None) -> str:
    if value is None:
        return "missing"
    if isinstance(value, ast.Constant):
        return str(value.value)
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    if isinstance(value, ast.Call):
        return f"{_call_name(value.func) or 'call'}(...)"
    if isinstance(value, ast.IfExp):
        return "conditional_expression"
    return value.__class__.__name__


def _inventory_by_path() -> dict[str, list[dict[str, str]]]:
    by_path: dict[str, list[dict[str, str]]] = {}
    for item in model_call_site_cache_contract_inventory():
        path = str(item.get("path") or "").replace("\\", "/")
        if path:
            by_path.setdefault(path, []).append(dict(item))
    return by_path


def _inventory_item_is_justified(item: dict[str, str]) -> bool:
    if not REQUIRED_INVENTORY_FIELDS <= set(item):
        return False
    contract = str(item.get("cache_contract") or "").casefold()
    if not any(marker in contract for marker in INVENTORY_OPT_OUT_MARKERS):
        return False
    return bool(item.get("purpose") and item.get("route_source") and item.get("owner"))


def discover_model_cache_contract_call_sites(
    *,
    repo_root: Path | str,
    scan_paths: tuple[str, ...] = DEFAULT_SCAN_PATHS,
) -> tuple[ModelCacheContractCallSite, ...]:
    """Discover live model invocation surfaces and their cache-contract status."""

    root = Path(repo_root)
    inventory = _inventory_by_path()
    rows: list[ModelCacheContractCallSite] = []
    for path in _iter_scan_files(root, scan_paths):
        relative_path = _repo_relative(path, root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        except SyntaxError:
            continue
        inventory_items = inventory.get(relative_path, [])
        justified_inventory = [
            item for item in inventory_items if _inventory_item_is_justified(item)
        ]
        inventory_call_site = (
            str(justified_inventory[0].get("call_site") or "")
            if justified_inventory
            else ""
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = _call_name(node.func)
            if call not in LIVE_MODEL_CALLS_REQUIRING_CACHE_CONTRACT:
                continue
            keyword = _cache_contract_keyword(node)
            if keyword is not None:
                status = "explicit_cache_contract"
            elif justified_inventory:
                status = "inventory_opt_out"
            else:
                status = "missing_cache_contract"
            rows.append(
                ModelCacheContractCallSite(
                    path=relative_path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    call=call,
                    cache_contract=_safe_contract_label(keyword),
                    inventory_call_site=inventory_call_site,
                    status=status,
                )
            )
    return tuple(sorted(rows, key=lambda row: (row.path, row.line, row.call)))


def model_cache_contract_call_site_audit(
    *,
    repo_root: Path | str,
    scan_paths: tuple[str, ...] = DEFAULT_SCAN_PATHS,
) -> dict[str, Any]:
    call_sites = discover_model_cache_contract_call_sites(
        repo_root=repo_root,
        scan_paths=scan_paths,
    )
    missing = [row for row in call_sites if row.status == "missing_cache_contract"]
    explicit = [row for row in call_sites if row.status == "explicit_cache_contract"]
    opt_out = [row for row in call_sites if row.status == "inventory_opt_out"]
    return {
        "kind": "aippocampus_model_cache_contract_call_site_audit",
        "ok": not missing,
        "scan_paths": list(scan_paths),
        "call_sites": [row.as_dict() for row in call_sites],
        "missing_cache_contract": [row.as_dict() for row in missing],
        "metrics": {
            "call_site_count": len(call_sites),
            "explicit_cache_contract_count": len(explicit),
            "inventory_opt_out_count": len(opt_out),
            "missing_cache_contract_count": len(missing),
            "inventory_entry_count": len(model_call_site_cache_contract_inventory()),
        },
    }
