from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SMOKE_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "smoke"
DOC_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "docs"
RELEASE_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "release"
GITHUB_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "github"
TOOL_ROOT = REPO_ROOT / "tools" / "aippocampus"

def _prepend_once(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

def _import_from_roots(module_name: str, *roots: Path) -> ModuleType:
    """Load legacy repo-local tool modules through one audited test exception.

    Ordinary tests should import package owners directly. These helpers are only
    for benchmark/smoke/docs/release scripts that still run as repo-local
    entrypoints and need their sibling `_paths.py` or `shared/` imports intact.
    """

    for root in reversed(roots):
        _prepend_once(root)
    return importlib.import_module(module_name)

def import_benchmark_module(module_name: str) -> ModuleType:
    return _import_from_roots(module_name, RUNTIME_SCRIPTS, BENCHMARKS)

def import_smoke_module(module_name: str) -> ModuleType:
    return _import_from_roots(module_name, RUNTIME_SCRIPTS, SMOKE_TOOLS)

def import_doc_tool_module(module_name: str) -> ModuleType:
    return _import_from_roots(module_name, RUNTIME_SCRIPTS, BENCHMARKS, SMOKE_TOOLS, DOC_TOOLS)

def import_release_tool_module(module_name: str) -> ModuleType:
    return _import_from_roots(module_name, RELEASE_TOOLS)

def import_github_tool_module(module_name: str) -> ModuleType:
    return _import_from_roots(module_name, GITHUB_TOOLS, DOC_TOOLS)

def import_tool_root_module(module_name: str) -> ModuleType:
    return _import_from_roots(module_name, TOOL_ROOT, DOC_TOOLS)

def import_repo_root_module(module_name: str) -> ModuleType:
    return _import_from_roots(module_name, REPO_ROOT)
