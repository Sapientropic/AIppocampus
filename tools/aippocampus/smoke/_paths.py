from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_repo_paths() -> ModuleType:
    helper_path = Path(__file__).resolve().parents[1] / "repo_paths.py"
    spec = importlib.util.spec_from_file_location(
        "_aippocampus_repo_paths",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load repo import helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_repo_paths = _load_repo_paths()
_paths = _repo_paths.ensure_repo_imports(
    Path(__file__).resolve(),
    include_benchmark_tools=True,
)

REPO_ROOT = _paths.repo_root
SKILL_ROOT = _paths.skill_root
SKILL_SCRIPTS = _paths.skill_scripts


def ensure_paths() -> None:
    _repo_paths.ensure_repo_imports(
        Path(__file__).resolve(),
        include_benchmark_tools=True,
    )
