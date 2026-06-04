#!/usr/bin/env python3
"""Inventory accidental top-level runtime compatibility surfaces.

The supported runtime now lives under package owners plus the public
``aippocampus`` console facade. Any ``skills/aippocampus/scripts/*.py`` file is
treated as residual shim debt unless a future migration deliberately reopens a
flat entrypoint.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import tomllib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

KEEP_CLI_SCRIPTS = {
    "aippocampus_cli.py",
    "aippocampus_health.py",
    "aippocampus_lifecycle_hook.py",
    "aippocampus_maintenance.py",
    "aippocampus_mcp_server.py",
    "aippocampus_prompt_hook.py",
    "build_clean_source.py",
    "build_index.py",
    "build_segments.py",
    "encrypted_sync_admin.py",
    "export_bundle.py",
    "import_bundle.py",
    "install_aippocampus_lifecycle_hook.py",
    "install_aippocampus_prompt_hook.py",
    "onboard.py",
    "onboard_codex.py",
    "onboard_frontier.py",
    "onboard_status.py",
    "registry.py",
    "search_clean_source.py",
    "sync_bundle.py",
    "sync_object_storage.py",
    "sync_vault.py",
}

LEGACY_BRIDGES: set[str] = set()
LOCAL_LOGIC_COMPAT_EXCEPTIONS = {
    "aippocampuslib.py",
}
FACADE_SHIMS = {
    "aippocampus_cli.py",
    "onboard.py",
}
MANUAL_EXPORT_LINE_LIMIT = 20

KEEP_CLI_REMOVAL_CONDITION = (
    "Keep while README, SKILL.md, install hooks, MCP/binary entrypoints, or "
    "operator docs advertise this direct script path; remove only with a "
    "documented migration note."
)
TEMPORARY_COMPAT_REMOVAL_CONDITION = (
    "Remove after first-party imports and runtime docs point at the "
    "aippocampus_runtime package owner and no install/hook/binary path calls "
    "this flat module."
)
DELETE_NOW_REMOVAL_CONDITION = (
    "Delete in a small batch with its py-modules entry when present, then run "
    "import-coupling and direct-help smokes."
)
PYTHON_REFERENCE_ROOTS = (
    "skills",
    "tools",
    "tests",
    "benchmarks",
    "plugins",
)
DOC_REFERENCE_ROOTS = (
    "docs",
    "skills/aippocampus/SKILL.md",
    "skills/aippocampus/references",
)
ARCHIVED_DOC_PREFIXES = (
    "docs/archive/",
)
DIRECT_PATH_REFERENCE_ROOTS = (
    ".github",
    "skills",
    "tools",
)
SHIM_IDENTITY_TESTS = {
    "tests/aippocampus/test_import_coupling.py",
    "tests/aippocampus/test_compat_shim_inventory.py",
}


@dataclass(frozen=True)
class InventoryItem:
    script: str
    bucket: str
    reason: str
    removal_condition: str
    shim_style: str
    style_reason: str
    style_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InventoryReport:
    top_level_script_count: int
    top_level_scripts: list[str]
    keep_cli: list[InventoryItem]
    temporary_compat: list[InventoryItem]
    delete_now: list[InventoryItem]
    legacy_bridge: list[InventoryItem]
    shim_style_counts: dict[str, int]
    unknown_shim_styles: list[InventoryItem]
    reexport_blocks: list[InventoryItem]
    manual_export_surfaces: list[InventoryItem]
    unbucketed: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReferenceIndex:
    py_modules: set[str]
    project_entrypoints: dict[str, list[str]]
    first_party_imports: dict[str, list[str]]
    non_identity_test_imports: dict[str, list[str]]
    direct_path_dependencies: dict[str, list[str]]
    documented_direct_invocations: dict[str, list[str]]


def _scripts_dir(repo_root: Path) -> Path:
    return repo_root / "skills" / "aippocampus" / "scripts"


def _is_compat_shim(source: str) -> bool:
    return "Compatibility shim" in source or "module alias compatibility shim" in source


def _non_comment_line_count(source: str) -> int:
    return sum(1 for line in source.splitlines() if line.strip() and not line.strip().startswith("#"))


def _is_alias_or_dynamic_mirror(source: str) -> bool:
    return "sys.modules[__name__]" in source or "globals().update(" in source


def _shim_style(path: Path, source: str) -> tuple[str, str, tuple[str, ...]]:
    if path.name in LOCAL_LOGIC_COMPAT_EXCEPTIONS:
        return (
            "local_fallback_shim",
            "documented compatibility shim with a tiny half-installed fallback",
            (),
        )
    if path.name in FACADE_SHIMS or "aippocampus_runtime.cli.facade" in source:
        return (
            "facade_shim",
            "public command or provider-aware facade keeps a curated flat surface",
            (),
        )
    if not _is_compat_shim(source):
        return (
            "non_shim_script",
            "top-level file does not carry a compatibility-shim marker",
            ("top-level file is not an explained compatibility shim",),
        )

    signals: list[tuple[str, str]] = []
    if "sys.modules[__name__]" in source:
        signals.append(
            (
                "module_alias_shim",
                "imports the package owner and aliases the flat module identity",
            )
        )
    if "globals().update(" in source:
        signals.append(
            (
                "export_mirror_shim",
                "mirrors package-owner exports through a small generated globals update",
            )
        )

    if len(signals) > 1:
        return (
            "mixed_shim_style",
            "shim mixes multiple compatibility export mechanisms",
            ("choose one documented shim style unless this path has an explicit exception",),
        )
    if signals:
        return (*signals[0], ())
    if "aippocampus_runtime" in source and "if __name__ == \"__main__\"" in source:
        return (
            "direct_cli_wrapper",
            "thin direct-script wrapper delegates CLI execution to the package owner",
            (),
        )
    if "aippocampus_runtime" in source and _non_comment_line_count(source) <= MANUAL_EXPORT_LINE_LIMIT:
        return (
            "export_mirror_shim",
            "mirrors selected package-owner exports through a small explicit export list",
            (),
        )
    return (
        "unknown_shim_style",
        "compatibility shim marker exists but the export/import style is not recognized",
        ("document the style or convert it to a known shim pattern",),
    )


def _is_pure_package_owner_reexport(source: str) -> bool:
    if not _is_compat_shim(source):
        return False
    if "aippocampus_runtime" not in source:
        return False
    if _is_alias_or_dynamic_mirror(source):
        return True
    return _non_comment_line_count(source) <= MANUAL_EXPORT_LINE_LIMIT


def _relative_posix(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_archived_doc_reference(rel_path: str) -> bool:
    # Archived plans preserve provenance for humans; they should not keep
    # legacy direct script shims alive after active docs and code have migrated.
    return any(rel_path.startswith(prefix) for prefix in ARCHIVED_DOC_PREFIXES)


def _iter_existing_files(repo_root: Path, roots: tuple[str, ...], pattern: str) -> list[Path]:
    files: list[Path] = []
    for rel_root in roots:
        root = repo_root / Path(rel_root)
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        files.extend(
            path
            for path in root.rglob(pattern)
            if "__pycache__" not in path.parts and ".venv" not in path.parts
        )
    return sorted(files)


def _pyproject_metadata(repo_root: Path, flat_modules: set[str]) -> tuple[set[str], dict[str, list[str]]]:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        return set(), {}
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return set(), {}

    setuptools = data.get("tool", {}).get("setuptools", {})
    py_modules = {
        module
        for module in setuptools.get("py-modules", [])
        if isinstance(module, str)
    }
    project_entrypoints: dict[str, list[str]] = defaultdict(list)
    scripts = data.get("project", {}).get("scripts", {})
    for command, target in scripts.items():
        if not isinstance(command, str) or not isinstance(target, str):
            continue
        module = target.split(":", maxsplit=1)[0].split(".", maxsplit=1)[0]
        if module in flat_modules:
            project_entrypoints[module].append(f"pyproject.toml:[project.scripts].{command}")
    return py_modules, dict(project_entrypoints)


def _flat_import_targets(source: str, flat_modules: set[str]) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".", maxsplit=1)[0]
                if top_level in flat_modules:
                    targets.add(top_level)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top_level = node.module.split(".", maxsplit=1)[0]
            if top_level in flat_modules:
                targets.add(top_level)
        elif isinstance(node, ast.Call) and node.args:
            first_arg = node.args[0]
            if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
                continue
            module_name = first_arg.value.split(".", maxsplit=1)[0]
            if module_name not in flat_modules:
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "import_module":
                targets.add(module_name)
            elif isinstance(func, ast.Name) and func.id == "import_module":
                targets.add(module_name)
    return targets


def _doc_line_is_direct_invocation(line: str, script_name: str) -> bool:
    if script_name not in line:
        return False
    normalized = line.replace("\\", "/")
    escaped = re.escape(script_name)
    if f"skills/aippocampus/scripts/{script_name}" in normalized:
        return True
    if re.search(rf"\bpython(?:\s+-m)?\b[^\n`]*{escaped}", line):
        return True
    if re.search(rf"\b(?:Use|Run|Call|Invoke)\s+`?{escaped}`?\b", line, re.IGNORECASE):
        return True
    return bool(re.search(rf"`[^`]*{escaped}\s+--", line))


def _code_line_is_direct_path_dependency(line: str, script_name: str) -> bool:
    if script_name not in line:
        return False
    normalized = line.replace("\\", "/")
    escaped = re.escape(script_name)
    if f"skills/aippocampus/scripts/{script_name}" in normalized:
        return True
    if f"scripts/{script_name}" in normalized:
        return True
    return bool(
        re.search(
            rf"\b(?:SCRIPT_DIR|SCRIPTS|scripts_dir|script_dir|script_path)\b[^\n]*{escaped}",
            line,
        )
    )


def _build_reference_index(repo_root: Path, top_level_paths: list[Path]) -> ReferenceIndex:
    flat_modules = {path.stem for path in top_level_paths}
    script_names = {path.name for path in top_level_paths}
    top_level_by_module = {path.stem: path.resolve() for path in top_level_paths}
    py_modules, project_entrypoints = _pyproject_metadata(repo_root, flat_modules)

    first_party_imports: dict[str, list[str]] = defaultdict(list)
    non_identity_test_imports: dict[str, list[str]] = defaultdict(list)
    for path in _iter_existing_files(repo_root, PYTHON_REFERENCE_ROOTS, "*.py"):
        rel = _relative_posix(repo_root, path)
        if rel in SHIM_IDENTITY_TESTS:
            continue
        source = path.read_text(encoding="utf-8")
        for module in _flat_import_targets(source, flat_modules):
            if path.resolve() == top_level_by_module.get(module):
                continue
            if rel.startswith("tests/"):
                non_identity_test_imports[module].append(rel)
            else:
                first_party_imports[module].append(rel)

    documented_direct_invocations: dict[str, list[str]] = defaultdict(list)
    doc_files = [
        *(repo_root / name for name in ("README.md", "AGENTS.md") if (repo_root / name).exists()),
        *_iter_existing_files(repo_root, DOC_REFERENCE_ROOTS, "*.md"),
    ]
    for path in sorted(doc_files):
        rel = _relative_posix(repo_root, path)
        if _is_archived_doc_reference(rel):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for script_name in script_names:
                if _doc_line_is_direct_invocation(line, script_name):
                    documented_direct_invocations[script_name].append(f"{rel}:{line_no}")

    direct_path_dependencies: dict[str, list[str]] = defaultdict(list)
    for suffix in ("*.py", "*.ps1", "*.yml", "*.yaml"):
        for path in _iter_existing_files(repo_root, DIRECT_PATH_REFERENCE_ROOTS, suffix):
            rel = _relative_posix(repo_root, path)
            if rel in SHIM_IDENTITY_TESTS or path.resolve() in top_level_by_module.values():
                continue
            source = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(source.splitlines(), start=1):
                for script_name in script_names:
                    if _code_line_is_direct_path_dependency(line, script_name):
                        direct_path_dependencies[script_name].append(f"{rel}:{line_no}")

    return ReferenceIndex(
        py_modules=py_modules,
        project_entrypoints=project_entrypoints,
        first_party_imports=dict(first_party_imports),
        non_identity_test_imports=dict(non_identity_test_imports),
        direct_path_dependencies=dict(direct_path_dependencies),
        documented_direct_invocations=dict(documented_direct_invocations),
    )


def _temporary_item(
    script: str,
    reason: str,
    *,
    shim_style: str = "not_applicable",
    style_reason: str = "synthetic non-top-level compatibility item",
    style_warnings: tuple[str, ...] = (),
) -> InventoryItem:
    return InventoryItem(
        script=script,
        bucket="temporary_compat",
        reason=reason,
        removal_condition=TEMPORARY_COMPAT_REMOVAL_CONDITION,
        shim_style=shim_style,
        style_reason=style_reason,
        style_warnings=style_warnings,
    )


def _classify_top_level_script(path: Path, references: ReferenceIndex) -> InventoryItem:
    source = path.read_text(encoding="utf-8")
    module_name = path.stem
    shim_style, style_reason, style_warnings = _shim_style(path, source)

    def temporary(reason: str) -> InventoryItem:
        return _temporary_item(
            path.name,
            reason,
            shim_style=shim_style,
            style_reason=style_reason,
            style_warnings=style_warnings,
        )

    if path.name in LEGACY_BRIDGES:
        return InventoryItem(
            script=path.name,
            bucket="legacy_bridge",
            reason="single implementation is intentionally still at a legacy direct path",
            removal_condition="No legacy direct-path implementation exceptions should remain.",
            shim_style=shim_style,
            style_reason=style_reason,
            style_warnings=style_warnings,
        )
    if path.name in KEEP_CLI_SCRIPTS:
        return InventoryItem(
            script=path.name,
            bucket="keep_cli",
            reason="documented CLI, hook, MCP, install, sync, onboarding, or operator path",
            removal_condition=KEEP_CLI_REMOVAL_CONDITION,
            shim_style=shim_style,
            style_reason=style_reason,
            style_warnings=style_warnings,
        )
    if _is_compat_shim(source):
        if path.name in LOCAL_LOGIC_COMPAT_EXCEPTIONS:
            return temporary(
                "compatibility shim still carries a documented local-logic exception",
            )
        if not _is_pure_package_owner_reexport(source):
            return temporary(
                "compatibility shim is not yet a pure aippocampus_runtime owner re-export",
            )
        if references.project_entrypoints.get(module_name):
            return temporary(
                "project script entrypoint still targets flat module: "
                + references.project_entrypoints[module_name][0],
            )
        if references.first_party_imports.get(module_name):
            return temporary(
                "first-party import still references flat module: "
                + references.first_party_imports[module_name][0],
            )
        if references.non_identity_test_imports.get(module_name):
            return temporary(
                "non-identity test still imports flat module: "
                + references.non_identity_test_imports[module_name][0],
            )
        if references.direct_path_dependencies.get(path.name):
            return temporary(
                "install/hook/binary path still references direct script path: "
                + references.direct_path_dependencies[path.name][0],
            )
        if references.documented_direct_invocations.get(path.name):
            return temporary(
                "documented direct invocation still references flat script path: "
                + references.documented_direct_invocations[path.name][0],
            )
        if module_name in references.py_modules:
            reason = (
                "only remaining flat-module exposure is pyproject py-modules; "
                "drop that entry with the shim in the deletion batch"
            )
        else:
            reason = (
                "pure package-owner re-export with no first-party imports, "
                "direct docs, or install/hook/binary path dependency"
            )
        return InventoryItem(
            script=path.name,
            bucket="delete_now",
            reason=reason,
            removal_condition=DELETE_NOW_REMOVAL_CONDITION,
            shim_style=shim_style,
            style_reason=style_reason,
            style_warnings=style_warnings,
        )
    return InventoryItem(
        script=path.name,
        bucket="delete_now",
        reason="no compatibility shim marker or legacy bridge classification",
        removal_condition="Delete once import-coupling and direct help smokes pass.",
        shim_style=shim_style,
        style_reason=style_reason,
        style_warnings=style_warnings,
    )


def _reexport_blocks(repo_root: Path) -> list[InventoryItem]:
    scripts_dir = _scripts_dir(repo_root)
    blocks: list[InventoryItem] = []
    for path in sorted((scripts_dir / "aippocampus_runtime").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "COMPAT_EXPORTS" not in source:
            continue
        blocks.append(
            InventoryItem(
                script=path.relative_to(scripts_dir).as_posix(),
                bucket="temporary_compat",
                reason="mechanical package-level re-export block",
                removal_condition=(
                    "Remove after first-party imports use the true owner module "
                    "and old installed-hook migration is complete."
                ),
                shim_style="package_reexport_block",
                style_reason="package-level mechanical compatibility export block",
            )
        )
    return blocks


def _manual_export_surfaces(repo_root: Path, items: list[InventoryItem]) -> list[InventoryItem]:
    scripts_dir = _scripts_dir(repo_root)
    surfaces: list[InventoryItem] = []
    for item in items:
        if item.bucket != "temporary_compat":
            continue
        if item.script in LOCAL_LOGIC_COMPAT_EXCEPTIONS:
            continue
        path = scripts_dir / item.script
        source = path.read_text(encoding="utf-8")
        if _is_alias_or_dynamic_mirror(source):
            continue
        if _non_comment_line_count(source) <= MANUAL_EXPORT_LINE_LIMIT:
            continue
        surfaces.append(
            InventoryItem(
                script=item.script,
                bucket="temporary_compat",
                reason="long manual export shim can become a second API surface",
                removal_condition=(
                    "Collapse to a module-alias shim or tiny globals mirror unless "
                    "a documented installer/hook fallback needs explicit local logic."
                ),
                shim_style=item.shim_style,
                style_reason=item.style_reason,
                style_warnings=item.style_warnings,
            )
        )
    return surfaces


def build_inventory(repo_root: Path) -> InventoryReport:
    repo_root = repo_root.resolve()
    top_level_paths = sorted(_scripts_dir(repo_root).glob("*.py"))
    references = _build_reference_index(repo_root, top_level_paths)
    items = [
        _classify_top_level_script(path, references)
        for path in top_level_paths
    ]
    bucketed_names = {item.script for item in items}
    top_level_scripts = [item.script for item in items]
    buckets = {
        "keep_cli": [item for item in items if item.bucket == "keep_cli"],
        "temporary_compat": [item for item in items if item.bucket == "temporary_compat"],
        "delete_now": [item for item in items if item.bucket == "delete_now"],
        "legacy_bridge": [item for item in items if item.bucket == "legacy_bridge"],
    }
    style_counts = Counter(item.shim_style for item in items)
    unknown_styles = [
        item
        for item in items
        if item.shim_style in {"unknown_shim_style", "mixed_shim_style"}
    ]
    return InventoryReport(
        top_level_script_count=len(top_level_scripts),
        top_level_scripts=top_level_scripts,
        keep_cli=buckets["keep_cli"],
        temporary_compat=buckets["temporary_compat"],
        delete_now=buckets["delete_now"],
        legacy_bridge=buckets["legacy_bridge"],
        shim_style_counts=dict(sorted(style_counts.items())),
        unknown_shim_styles=unknown_styles,
        reexport_blocks=_reexport_blocks(repo_root),
        manual_export_surfaces=_manual_export_surfaces(repo_root, items),
        unbucketed=sorted(set(top_level_scripts) - bucketed_names),
    )


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_repo_root_from_script())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_inventory(args.repo_root)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"top_level_script_count: {report.top_level_script_count}")
        for bucket_name in ("keep_cli", "temporary_compat", "delete_now", "legacy_bridge"):
            bucket = getattr(report, bucket_name)
            print(f"{bucket_name}: {len(bucket)}")
        print(f"reexport_blocks: {len(report.reexport_blocks)}")
        print(f"manual_export_surfaces: {len(report.manual_export_surfaces)}")
        print("shim_style_counts:")
        for style, count in report.shim_style_counts.items():
            print(f"  {style}: {count}")
        print(f"unknown_shim_styles: {len(report.unknown_shim_styles)}")
        for item in report.unknown_shim_styles:
            print(f"  {item.script}: {item.shim_style} - {item.style_reason}")
        if report.unbucketed:
            print("unbucketed: " + ", ".join(report.unbucketed))
    return 1 if report.unbucketed or report.unknown_shim_styles else 0


if __name__ == "__main__":
    raise SystemExit(main())
