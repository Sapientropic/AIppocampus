#!/usr/bin/env python3
"""Inventory top-level runtime compatibility surfaces.

This is intentionally a lightweight maintainer report, not a deletion bot.
AIppocampus still supports direct script paths in installed skills, so a shim
only becomes deletable after docs, installer paths, and first-party imports have
moved to the package owner.
"""

from __future__ import annotations

import argparse
import json
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

@dataclass(frozen=True)
class InventoryItem:
    script: str
    bucket: str
    reason: str
    removal_condition: str


@dataclass(frozen=True)
class InventoryReport:
    top_level_script_count: int
    top_level_scripts: list[str]
    keep_cli: list[InventoryItem]
    temporary_compat: list[InventoryItem]
    delete_now: list[InventoryItem]
    legacy_bridge: list[InventoryItem]
    reexport_blocks: list[InventoryItem]
    manual_export_surfaces: list[InventoryItem]
    unbucketed: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _scripts_dir(repo_root: Path) -> Path:
    return repo_root / "skills" / "aippocampus" / "scripts"


def _is_compat_shim(source: str) -> bool:
    return "Compatibility shim" in source or "module alias compatibility shim" in source


def _non_comment_line_count(source: str) -> int:
    return sum(1 for line in source.splitlines() if line.strip() and not line.strip().startswith("#"))


def _is_alias_or_dynamic_mirror(source: str) -> bool:
    return "sys.modules[__name__]" in source or "globals().update(" in source


def _classify_top_level_script(path: Path) -> InventoryItem:
    source = path.read_text(encoding="utf-8")
    if path.name in LEGACY_BRIDGES:
        return InventoryItem(
            script=path.name,
            bucket="legacy_bridge",
            reason="single implementation is intentionally still at a legacy direct path",
            removal_condition="No legacy direct-path implementation exceptions should remain.",
        )
    if path.name in KEEP_CLI_SCRIPTS:
        return InventoryItem(
            script=path.name,
            bucket="keep_cli",
            reason="documented CLI, hook, MCP, install, sync, onboarding, or operator path",
            removal_condition=KEEP_CLI_REMOVAL_CONDITION,
        )
    if _is_compat_shim(source):
        return InventoryItem(
            script=path.name,
            bucket="temporary_compat",
            reason="flat import shim for an aippocampus_runtime package owner",
            removal_condition=TEMPORARY_COMPAT_REMOVAL_CONDITION,
        )
    return InventoryItem(
        script=path.name,
        bucket="delete_now",
        reason="no compatibility shim marker or legacy bridge classification",
        removal_condition="Delete once import-coupling and direct help smokes pass.",
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
            )
        )
    return surfaces


def build_inventory(repo_root: Path) -> InventoryReport:
    repo_root = repo_root.resolve()
    items = [
        _classify_top_level_script(path)
        for path in sorted(_scripts_dir(repo_root).glob("*.py"))
    ]
    bucketed_names = {item.script for item in items}
    top_level_scripts = [item.script for item in items]
    buckets = {
        "keep_cli": [item for item in items if item.bucket == "keep_cli"],
        "temporary_compat": [item for item in items if item.bucket == "temporary_compat"],
        "delete_now": [item for item in items if item.bucket == "delete_now"],
        "legacy_bridge": [item for item in items if item.bucket == "legacy_bridge"],
    }
    return InventoryReport(
        top_level_script_count=len(top_level_scripts),
        top_level_scripts=top_level_scripts,
        keep_cli=buckets["keep_cli"],
        temporary_compat=buckets["temporary_compat"],
        delete_now=buckets["delete_now"],
        legacy_bridge=buckets["legacy_bridge"],
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
        if report.unbucketed:
            print("unbucketed: " + ", ".join(report.unbucketed))
    return 1 if report.unbucketed else 0


if __name__ == "__main__":
    raise SystemExit(main())
