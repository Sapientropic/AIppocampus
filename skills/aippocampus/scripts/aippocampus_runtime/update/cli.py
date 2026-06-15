#!/usr/bin/env python3
"""One-command local update status, planning, and explicit apply flow."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home
from aippocampus_runtime.hooks import install_action_hint, install_lifecycle, install_prompt
from aippocampus_runtime.ops.provider_doctor import build_provider_doctor_report
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.update import status_actions as update_actions
from aippocampus_runtime.update.agent_callable import (
    command_availability,
    default_host_probe_report_path,
    load_json_file,
    mcp_command_repair_options,
    status_agent_callable,
)
from aippocampus_runtime.update.agent_status_summary import (
    agent_callable_host_probe_ok,
    compact_agent_status_report,
)
from aippocampus_runtime.update.capability_ladder import build_capability_ladder
from aippocampus_runtime.update.plugin_cache import (
    build_plugin_cache_status,
    installed_cache_auto_resolution,
    installed_cache_version_resolution,
    refresh_plugin_cache_layers,
    unique_installed_cache_root,
)
from aippocampus_runtime.update.plugin_marketplace import configured_marketplace_root
from aippocampus_runtime.update.plugin_status import enrich_plugin_cache_status
from aippocampus_runtime.update.status_readiness import (
    CORE_SURFACES,
    MAGIC_SURFACES,
    OPERATOR_SURFACES,
    OPTIONAL_SURFACES,
    surface_summary_blocker,
    unready_surfaces,
)

SCHEMA_VERSION = 1
PLUGIN_BUILD_SCRIPT = "build_plugin_package.py"
DEFAULT_PLUGIN_OUTPUT = Path("dist") / "aippocampus-plugin"
HOOK_EVENTS = ("SessionStart", "Stop", "PreCompact", "PostCompact")
IGNORED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    ".aippocampus",
    "aippocampus-registry",
    "clean-source",
    "raw-rollouts",
    "graphify-out",
    "exports",
    "exported-bundles",
    "sync-bundles",
    "build",
    "dist",
}
IGNORED_SUFFIXES = (".pyc", ".pyo")
OLD_HOOK_SCRIPT_NAMES = (
    "aippocampus_prompt_hook.py",
    "aippocampus_lifecycle_hook.py",
    "ambient_recall_hook.py",
    "memory_maintenance_hook.py",
)
PROVIDER_KEY_BRIDGE_MARKERS = (
    "aippocampus_provider_bridge_hook.py",
    "aippocampus_runtime.hooks.provider_bridge",
)
OLD_MCP_SCRIPT_NAMES = ("aippocampus_mcp_server.py",)
CURRENT_MCP_MARKERS = ("aippocampus_runtime.mcp.server", "aippocampus mcp")
RESOLVED_INSTALLED_CACHE_AUTO_STATUSES = {"unique", "unique_version_match"}


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _plugin_manifest_version(root: Path) -> str | None:
    manifest = root / ".codex-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return str(version) if version else None


def _safe_path_text(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def _optional_path_or_auto(value: str | None) -> Path | str | None:
    if not value:
        return None
    if value.strip().casefold() == "auto":
        return "auto"
    return Path(value).resolve()


def _path_is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def find_repo_root(start: Path | None = None) -> Path:
    candidates = []
    if start is not None:
        candidates.append(start.resolve())
    candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve())
    for candidate in candidates:
        path = candidate if candidate.is_dir() else candidate.parent
        for parent in (path, *path.parents):
            if (parent / "pyproject.toml").exists() and (
                parent / "skills" / "aippocampus" / "SKILL.md"
            ).exists():
                return parent
    return Path.cwd().resolve()


def _ignored_name(name: str) -> bool:
    return (
        name in IGNORED_DIR_NAMES
        or name.endswith(".egg-info")
        or name.endswith(IGNORED_SUFFIXES)
    )


def distribution_ignore(root: Path, *, root_exclusions: set[str] | None = None):
    exclusions = root_exclusions or set()
    root = root.resolve()

    def ignore(directory: str, names: list[str]) -> set[str]:
        directory_path = Path(directory).resolve()
        ignored: set[str] = set()
        for name in names:
            candidate = directory_path / name
            rel_parts: tuple[str, ...] = ()
            try:
                rel_parts = candidate.relative_to(root).parts
            except ValueError:
                rel_parts = (name,)
            if _ignored_name(name) or any(_ignored_name(part) for part in rel_parts):
                ignored.add(name)
            if directory_path == root and name in exclusions:
                ignored.add(name)
        return ignored

    return ignore


def collect_ignored_entries(root: Path, *, root_exclusions: set[str] | None = None) -> list[str]:
    if not root.exists():
        return []
    exclusions = root_exclusions or set()
    ignored: list[str] = []
    for path in root.rglob("*"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(_ignored_name(part) for part in rel.parts) or (
            len(rel.parts) == 1 and rel.name in exclusions
        ):
            ignored.append(rel.as_posix())
    return sorted(ignored)


def ignored_artifacts_report(entries: list[str], *, sample_size: int = 40) -> dict[str, Any]:
    return {
        "count": len(entries),
        "sample": entries[:sample_size],
        "truncated": len(entries) > sample_size,
    }


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_map(
    root: Path,
    *,
    prefix: str = "",
    root_exclusions: set[str] | None = None,
) -> dict[str, str]:
    if not root.exists():
        return {}
    ignore_root = root.resolve()
    excluded = root_exclusions or set()
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ignore_root)
        if len(rel.parts) == 1 and rel.name in excluded:
            continue
        if any(_ignored_name(part) for part in rel.parts):
            continue
        rel_text = rel.as_posix()
        key = f"{prefix.rstrip('/')}/{rel_text}" if prefix else rel_text
        result[key] = _file_hash(path)
    return result


def diff_maps(source: dict[str, str], target: dict[str, str]) -> dict[str, Any]:
    missing = sorted(set(source) - set(target))
    extra = sorted(set(target) - set(source))
    stale = sorted(path for path in set(source) & set(target) if source[path] != target[path])
    return {
        "missing": missing,
        "stale": stale,
        "extra": extra,
        "counts": {
            "source_files": len(source),
            "target_files": len(target),
            "missing": len(missing),
            "stale": len(stale),
            "extra": len(extra),
        },
        "current": not missing and not stale and not extra,
    }


def _surface_status_from_diff(diff: dict[str, Any], *, source_exists: bool, target_exists: bool) -> str:
    if not source_exists:
        return "unsupported"
    if not target_exists:
        return "missing"
    return "current" if diff.get("current") else "stale"


def compare_skill(
    *,
    repo_root: Path,
    codex_home_path: Path,
    skill_target: Path | None = None,
) -> dict[str, Any]:
    source = repo_root / "skills" / "aippocampus"
    target = skill_target or codex_home_path / "skills" / "aippocampus"
    source_map = file_map(source)
    target_map = file_map(target)
    diff = diff_maps(source_map, target_map)
    ignored = collect_ignored_entries(source)
    return {
        "surface": "skill",
        "status": _surface_status_from_diff(
            diff, source_exists=source.exists(), target_exists=target.exists()
        ),
        "source_path": str(source),
        "target_path": str(target),
        "ignored_artifacts": ignored_artifacts_report(ignored),
        "diff": diff,
        "safety_notes": [
            "apply replaces only the installable skill package directory",
            "generated memory registries, raw rollouts, caches, and package metadata are excluded",
        ],
    }


def _plugin_source_map(repo_root: Path) -> dict[str, str]:
    plugin_source = repo_root / "plugins" / "aippocampus"
    skill_source = repo_root / "skills" / "aippocampus"
    result = file_map(plugin_source, root_exclusions={PLUGIN_BUILD_SCRIPT})
    result.update(file_map(skill_source, prefix="skills/aippocampus"))
    return result


def compare_plugin(*, repo_root: Path, plugin_output: Path | None = None) -> dict[str, Any]:
    plugin_source = repo_root / "plugins" / "aippocampus"
    output = plugin_output or repo_root / DEFAULT_PLUGIN_OUTPUT
    source = _plugin_source_map(repo_root)
    target = file_map(output)
    diff = diff_maps(source, target)
    ignored = collect_ignored_entries(plugin_source, root_exclusions={PLUGIN_BUILD_SCRIPT})
    ignored.extend(
        f"skills/aippocampus/{item}"
        for item in collect_ignored_entries(repo_root / "skills" / "aippocampus")
    )
    status = _surface_status_from_diff(
        diff, source_exists=plugin_source.exists(), target_exists=output.exists()
    )
    return {
        "surface": "plugin",
        "status": status,
        "package_artifact_current": status == "current",
        "source_path": str(plugin_source),
        "target_path": str(output),
        "ignored_artifacts": ignored_artifacts_report(sorted(ignored)),
        "diff": diff,
        "safety_notes": [
            "apply rebuilds the repo-local plugin package under dist/",
            "host plugin installation, hooks, and user environment values are not changed",
        ],
    }


def status_cli(repo_root: Path) -> dict[str, Any]:
    scripts = repo_root / "skills" / "aippocampus" / "scripts"
    spec = importlib.util.find_spec("aippocampus_runtime")
    active_path = Path(spec.origin).resolve() if spec and spec.origin else None
    console_script = shutil.which("aippocampus")
    try:
        version = importlib.metadata.version("aippocampus")
    except importlib.metadata.PackageNotFoundError:
        version = None
    source_active = bool(active_path and _path_is_under(active_path, scripts))
    sys_path_ready = any(
        str(scripts.resolve()) == str(Path(item or ".").resolve())
        for item in sys.path
        if item
    )
    status = "current" if source_active or version else "missing"
    if version and not source_active:
        status = "installed_package"
    recommended_actions: list[str] = []
    if not console_script:
        recommended_actions.append(
            "install or repair the console script with the documented install command"
        )
        recommended_actions.append(
            "or add the Python Scripts/bin directory containing `aippocampus` to PATH"
        )
    return {
        "surface": "cli",
        "status": status,
        "source_path": str(scripts),
        "active_package_path": _safe_path_text(active_path),
        "console_script": console_script,
        "console_script_available_on_path": bool(console_script),
        "installed_version": version,
        "source_checkout_import_ready": bool(source_active or sys_path_ready),
        "module_entrypoint_available": bool(source_active or sys_path_ready or version),
        "documented_install_command": f"{Path(sys.executable).name} -m pip install -e {repo_root}",
        "recommended_actions": recommended_actions,
        "safety_notes": [
            "CLI refresh is reported as a package install command; update does not run pip implicitly"
        ],
    }


def status_mcp(repo_root: Path, mcp_config: Path | None = None) -> dict[str, Any]:
    path = mcp_config or repo_root / "plugins" / "aippocampus" / ".mcp.json"
    if not path.exists():
        return {
            "surface": "mcp",
            "status": "missing",
            "source_path": str(path),
            "target_path": str(path),
            "stale_flat_script": False,
            "manual_review_needed": True,
            "safety_notes": ["MCP config is inspected read-only; apply does not rewrite host configs"],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "surface": "mcp",
            "status": "invalid",
            "source_path": str(path),
            "target_path": str(path),
            "error": str(exc),
            "manual_review_needed": True,
            "safety_notes": ["MCP config parse failed; no mutation attempted"],
        }
    server = ((data.get("mcpServers") or {}).get("aippocampus") or {}) if isinstance(data, dict) else {}
    serialized = json.dumps(server, ensure_ascii=False)
    command = str(server.get("command") or "")
    args = [str(item) for item in server.get("args") or []]
    stale = any(name in serialized for name in OLD_MCP_SCRIPT_NAMES)
    current = any(marker in serialized for marker in CURRENT_MCP_MARKERS) or (
        command == "aippocampus" and args[:1] == ["mcp"]
    )
    if stale:
        status = "stale"
    elif current:
        status = "current"
    else:
        status = "detect_only"
    availability = command_availability(command)
    repair_options = mcp_command_repair_options(command)
    return {
        "surface": "mcp",
        "status": status,
        "package_artifact_current": status == "current",
        "source_path": str(path),
        "target_path": str(path),
        "stale_flat_script": stale,
        "current_module_entrypoint": current,
        "manual_review_needed": status != "current",
        "server_command_present": bool(server),
        "mcp_command": command or None,
        "mcp_args": args,
        "mcp_command_resolves": availability["resolves"],
        "mcp_command_resolved_path": availability["resolved_path"],
        "mcp_command_uses_ambiguous_python": Path(command).name.casefold()
        in {"python", "python.exe"},
        "mcp_command_uses_console_script": command == "aippocampus",
        "python_available": availability["python_available"],
        "python3_available": availability["python3_available"],
        "aippocampus_console_script_available": availability["console_script_available"],
        "mcp_command_repair_options": repair_options if not availability["resolves"] else [],
        "recommended_actions": [
            "put the aippocampus console script on PATH, or register one of mcp_command_repair_options in the host"
        ]
        if not availability["resolves"]
        else [],
        "portable_module_command": f"{Path(sys.executable).name} -m aippocampus_runtime.mcp.server",
        "safety_notes": [
            "MCP package artifacts are not the same as foreground host tool visibility",
            "MCP host/user config is preserved; update reports stale commands instead of rewriting it",
        ],
    }


def _hook_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_hooks = data.get("hooks")
    hooks = raw_hooks if isinstance(raw_hooks, dict) else {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                continue
            for handler_index, handler in enumerate(handlers):
                if isinstance(handler, dict):
                    rows.append(
                        {
                            "event": event,
                            "group_index": group_index,
                            "handler_index": handler_index,
                            "command": str(handler.get("command") or ""),
                            "timeout": handler.get("timeout"),
                        }
                    )
    return rows


def _effective_aippocampus_hook_kind(row: dict[str, Any]) -> str:
    command = str(row.get("command") or "")
    event = str(row.get("event") or "")
    if any(marker in command for marker in PROVIDER_KEY_BRIDGE_MARKERS):
        return "bridge"
    if event == "UserPromptSubmit" and "aippocampus_runtime.hooks.prompt" in command:
        return "direct"
    if event in HOOK_EVENTS and "aippocampus_runtime.hooks.lifecycle" in command:
        return "direct"
    return ""


def _duplicate_effective_hooks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Count only AIppocampus handlers that would run the same logical hook.
    # Third-party hooks can share an event; bridge+direct AIppocampus handlers cannot.
    by_event: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        kind = _effective_aippocampus_hook_kind(row)
        if not kind:
            continue
        item = {
            "kind": kind,
            "group_index": row.get("group_index"),
            "handler_index": row.get("handler_index"),
        }
        by_event.setdefault(str(row.get("event") or ""), []).append(item)
    duplicates: list[dict[str, Any]] = []
    for event, handlers in sorted(by_event.items()):
        if len(handlers) <= 1:
            continue
        kinds = sorted({str(handler.get("kind") or "") for handler in handlers})
        duplicates.append(
            {
                "event": event,
                "handler_count": len(handlers),
                "handler_kinds": kinds,
                "reason_code": "provider_bridge_and_direct_hook"
                if {"bridge", "direct"}.issubset(set(kinds))
                else "duplicate_aippocampus_hook_handler",
                "handlers": handlers,
            }
        )
    return duplicates


def status_hooks(codex_home_path: Path, hooks_json: Path | None = None) -> dict[str, Any]:
    path = hooks_json or install_prompt.hooks_json_path(codex_home_path)
    data = install_prompt.load_hooks(path)
    rows = _hook_rows(data)
    action_hint_status = install_action_hint.status(path, include_private_paths=False)
    provider_key_bridge_rows = [
        {"event": row["event"], "handler_index": row["handler_index"]}
        for row in rows
        if any(marker in row["command"] for marker in PROVIDER_KEY_BRIDGE_MARKERS)
    ]
    stale_commands = [
        {
            "event": row["event"],
            "command_marker": next(
                (name for name in OLD_HOOK_SCRIPT_NAMES if name in row["command"]),
                "old_flat_script",
            ),
        }
        for row in rows
        if any(name in row["command"] for name in OLD_HOOK_SCRIPT_NAMES)
    ]
    duplicate_effective_hooks = _duplicate_effective_hooks(rows)
    prompt_current = any(
        row["event"] == "UserPromptSubmit"
        and (
            "aippocampus_runtime.hooks.prompt" in row["command"]
            or any(marker in row["command"] for marker in PROVIDER_KEY_BRIDGE_MARKERS)
        )
        for row in rows
    )
    lifecycle_current_events = {
        row["event"]
        for row in rows
        if row["event"] in HOOK_EVENTS
        and (
            "aippocampus_runtime.hooks.lifecycle" in row["command"]
            or any(marker in row["command"] for marker in PROVIDER_KEY_BRIDGE_MARKERS)
        )
    }
    lifecycle_current = set(lifecycle_current_events) == set(HOOK_EVENTS)
    prompt_any = prompt_current or any(
        row["event"] == "UserPromptSubmit"
        and any(name in row["command"] for name in ("aippocampus_prompt_hook.py", "ambient_recall_hook.py"))
        for row in rows
    )
    lifecycle_any_events = {
        row["event"]
        for row in rows
        if row["event"] in HOOK_EVENTS
        and any(
            marker in row["command"]
            for marker in (
                "aippocampus_runtime.hooks.lifecycle",
                "aippocampus_lifecycle_hook.py",
                "memory_maintenance_hook.py",
            )
        )
    }
    if stale_commands:
        status = "stale"
    elif duplicate_effective_hooks:
        status = "duplicate_effective_hook_execution"
    elif prompt_current and lifecycle_current:
        status = "current"
    elif prompt_any or lifecycle_any_events:
        status = "partial"
    else:
        status = "missing"
    reason_codes = []
    if stale_commands:
        reason_codes.append("stale_flat_script_commands")
    if duplicate_effective_hooks:
        reason_codes.append("duplicate_effective_hook_execution")
    return {
        "surface": "hooks",
        "status": status,
        "target_path": str(path),
        "prompt_installed": prompt_current,
        "lifecycle_installed": lifecycle_current,
        "lifecycle_events": sorted(lifecycle_current_events),
        "action_hints": action_hint_status,
        "action_hints_installed": bool(action_hint_status.get("installed")),
        "action_hints_ready": action_hint_status.get("cache_status") == "with_fresh_records",
        "action_hints_status": action_hint_status.get("cache_status") or "not_installed",
        "provider_key_bridge_installed": bool(provider_key_bridge_rows),
        "provider_key_bridge_handlers": provider_key_bridge_rows,
        "duplicate_effective_hook_execution": duplicate_effective_hooks,
        "reason_codes": reason_codes,
        "stale_flat_script_commands": stale_commands,
        "recommended_actions": [
            "aippocampus update apply --surface hooks",
            "aippocampus hooks prompt install",
            "aippocampus hooks lifecycle install",
        ]
        if status != "current"
        else [],
        "safety_notes": [
            "hook apply rewrites only AIppocampus-owned Codex hook handlers and preserves other hooks",
            "old flat-script hook commands are replaced by module entrypoints",
            "provider-key bridge wrappers are explicit onboarding artifacts and do not store key values in hooks.json",
        ],
    }


def status_llm(
    *,
    model_route: str | None = "default",
    provider_env_var: str | None = None,
    check_child_process: bool = True,
) -> dict[str, Any]:
    report = build_provider_doctor_report(
        model_route=model_route,
        provider_env_var=provider_env_var,
        check_child_process=check_child_process,
    )
    raw_provider_env = report.get("provider_env")
    provider_env: dict[str, Any] = raw_provider_env if isinstance(raw_provider_env, dict) else {}
    raw_route = report.get("route")
    route: dict[str, Any] = raw_route if isinstance(raw_route, dict) else {}
    return {
        "surface": "llm",
        "status": report.get("status"),
        "ready": bool(report.get("ok")),
        "provider": route.get("provider"),
        "model": route.get("model"),
        "provider_env_var": provider_env.get("env_var"),
        "visible_in_current_process": provider_env.get("visible_in_current_process"),
        "visible_in_child_process": provider_env.get("visible_in_child_process"),
        "cognitive_worker": report.get("cognitive_worker") or {},
        "recommended_actions": report.get("recommended_actions") or [],
        "privacy": report.get("privacy") or {},
        "safety_notes": [
            "LLM key setup is presence-only and redacted; update never prints or guesses key values",
            "set the provider key in the environment that launches Codex or the hook process",
        ],
    }


def build_status(args: argparse.Namespace, *, mode: str) -> dict[str, Any]:
    repo_root = find_repo_root(Path(args.repo_root).resolve() if args.repo_root else None)
    codex_home_path = Path(args.codex_home).resolve() if args.codex_home else codex_home()
    skill = compare_skill(
        repo_root=repo_root,
        codex_home_path=codex_home_path,
        skill_target=Path(args.skill_target).resolve() if args.skill_target else None,
    )
    plugin = compare_plugin(
        repo_root=repo_root,
        plugin_output=Path(args.plugin_output).resolve() if args.plugin_output else None,
    )
    plugin = enrich_plugin_cache_status(
        plugin,
        repo_root=repo_root,
        codex_home_path=codex_home_path,
        default_plugin_output=DEFAULT_PLUGIN_OUTPUT,
        plugin_output=Path(args.plugin_output).resolve() if args.plugin_output else None,
        plugin_marketplace_dir=Path(args.plugin_marketplace_dir).resolve()
        if args.plugin_marketplace_dir
        else None,
        plugin_installed_dir=_optional_path_or_auto(args.plugin_installed_dir),
    )
    hooks = status_hooks(
        codex_home_path,
        hooks_json=Path(args.hooks_json).resolve() if args.hooks_json else None,
    )
    llm = status_llm(
        model_route=args.model_route,
        provider_env_var=args.provider_env_var,
        check_child_process=not bool(args.no_child_check),
    )
    surfaces = {
        "cli": status_cli(repo_root),
        "skill": skill,
        "mcp": status_mcp(
            repo_root, Path(args.mcp_config).resolve() if args.mcp_config else None
        ),
        "plugin": plugin,
        "hooks": hooks,
        "llm": llm,
    }
    host_probe_path = (
        Path(args.host_probe_report).resolve()
        if args.host_probe_report
        else default_host_probe_report_path(codex_home_path)
    )
    host_probe = load_json_file(host_probe_path)
    surfaces["agent_callable"] = status_agent_callable(
        codex_home_path,
        surfaces,
        host_probe=host_probe,
        foreground_tools_visible_asserted=bool(args.foreground_tools_visible),
    )
    actionable = [
        name for name, item in surfaces.items() if surface_summary_blocker(name, item)
    ]
    plugin_cache_action = update_actions.plugin_cache_needs_action(surfaces["plugin"])
    if plugin_cache_action:
        actionable.append("plugin_cache")
    actionable = update_actions.unique_names(actionable)
    core_blockers = unready_surfaces(surfaces, CORE_SURFACES)
    magic_blockers = unready_surfaces(surfaces, MAGIC_SURFACES)
    optional_surfaces = unready_surfaces(surfaces, OPTIONAL_SURFACES)
    operator_blockers = [
        name
        for name in OPERATOR_SURFACES
        if surface_summary_blocker(name, surfaces.get(name) or {})
    ]
    core_ready = not core_blockers
    magic_ready = not magic_blockers
    capability_ladder = build_capability_ladder(surfaces, core_ready=core_ready)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": f"aippocampus_update_{mode}",
        "mode": mode,
        "ok": True,
        "repo_root": str(repo_root),
        "codex_home": str(codex_home_path),
        "summary": {
            "core_ready": core_ready,
            "core_blockers": core_blockers,
            "magic_ready": magic_ready,
            "magic_blockers": magic_blockers,
            "optional_surfaces": optional_surfaces,
            "operator_surfaces": list(OPERATOR_SURFACES),
            "operator_blockers": operator_blockers,
            "agent_callable_ready": surfaces["agent_callable"]["ready"],
            "agent_callable_status": surfaces["agent_callable"]["status"],
            "agent_callable_host_ready": agent_callable_host_probe_ok(
                surfaces["agent_callable"]
            ),
            "agent_callable_current_thread_visible": surfaces["agent_callable"]["ready"],
            "capability_ladder": capability_ladder,
            "needs_action": actionable,
            "stale_or_missing_surfaces": actionable,
            "nested_action_surfaces": ["plugin"] if plugin_cache_action else [],
            "plugin_cache_needs_action": plugin_cache_action,
            "plugin_cache_recommended_actions": surfaces["plugin"].get(
                "plugin_cache_recommended_actions"
            )
            or [],
        },
        "surfaces": surfaces,
        "safety_notes": [
            "status and plan are read-only",
            "apply changes only explicitly requested local surfaces",
            "private memory data, registries, raw rollouts, indexes, and sync bundles are not copied",
            "API key values are never read, printed, or stored by this command",
        ],
    }


def _require_replace_safe(target: Path, *, source: Path, repo_root: Path, expected_name: str) -> None:
    resolved = target.resolve()
    source_resolved = source.resolve()
    forbidden = {repo_root.resolve(), source_resolved, source_resolved.parent}
    if resolved in forbidden or _path_is_under(source_resolved, resolved):
        raise ValueError(f"refusing to replace unsafe directory: {resolved}")
    if resolved.name != expected_name:
        raise ValueError(f"refusing to replace unexpected target name: {resolved}")
    if len(resolved.parts) <= 2:
        raise ValueError(f"refusing to replace shallow filesystem path: {resolved}")


def apply_skill(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = find_repo_root(Path(args.repo_root).resolve() if args.repo_root else None)
    codex_home_path = Path(args.codex_home).resolve() if args.codex_home else codex_home()
    source = repo_root / "skills" / "aippocampus"
    target = (
        Path(args.skill_target).resolve()
        if args.skill_target
        else codex_home_path / "skills" / "aippocampus"
    )
    if not source.exists():
        raise FileNotFoundError(f"missing skill source: {source}")
    _require_replace_safe(target, source=source, repo_root=repo_root, expected_name="aippocampus")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.tmp-update"
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(source, tmp, ignore=distribution_ignore(source))
    verify_before_replace = diff_maps(file_map(source), file_map(tmp))
    if not verify_before_replace.get("current"):
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("copied skill package did not match source hashes before replace")
    if target.exists():
        shutil.rmtree(target)
    tmp.replace(target)
    verification = compare_skill(
        repo_root=repo_root,
        codex_home_path=codex_home_path,
        skill_target=target,
    )
    return {
        "surface": "skill",
        "applied": True,
        "ok": verification["status"] == "current",
        "source_path": str(source),
        "target_path": str(target),
        "verification": verification["diff"]["counts"],
    }


def _load_plugin_builder(repo_root: Path):
    path = repo_root / "plugins" / "aippocampus" / PLUGIN_BUILD_SCRIPT
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("_aippocampus_plugin_builder", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_plugin(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = find_repo_root(Path(args.repo_root).resolve() if args.repo_root else None)
    codex_home_path = Path(args.codex_home).resolve() if args.codex_home else codex_home()
    output = Path(args.plugin_output).resolve() if args.plugin_output else repo_root / DEFAULT_PLUGIN_OUTPUT
    builder = _load_plugin_builder(repo_root)
    if builder is None or not hasattr(builder, "build_package"):
        return {
            "surface": "plugin",
            "applied": False,
            "ok": True,
            "status": "detect_only",
            "message": "plugin package builder is not available in this installation",
        }
    result = builder.build_package(repo_root, output)
    installed_arg = _optional_path_or_auto(args.plugin_installed_dir)
    marketplace_arg = (
        Path(args.plugin_marketplace_dir).resolve()
        if args.plugin_marketplace_dir
        else None
    )
    if marketplace_arg is None and bool(getattr(args, "all_local", False)):
        # `--all-local` is the release/dogfood path. If Codex already points at
        # a local AIppocampus marketplace, refreshing that configured local copy
        # keeps status actionable without asking the operator to paste the same
        # path again. Unconfigured marketplaces still require an explicit path.
        marketplace_arg = configured_marketplace_root(codex_home_path)
    installed_auto_resolution = None
    all_local_auto_cache = bool(getattr(args, "all_local", False)) and installed_arg is None
    if installed_arg == "auto" or all_local_auto_cache:
        installed_auto_resolution = installed_cache_auto_resolution(codex_home_path)
        installed_arg = unique_installed_cache_root(codex_home_path)
        if installed_arg is None and installed_auto_resolution.get("status") == "multiple_candidates":
            expected_version = _plugin_manifest_version(output)
            if expected_version:
                version_resolution = installed_cache_version_resolution(
                    codex_home_path,
                    expected_version=expected_version,
                )
                installed_auto_resolution = {
                    **installed_auto_resolution,
                    "version_resolution": version_resolution,
                }
                if version_resolution.get("status") == "unique_version_match":
                    selected_root = version_resolution.get("root_path")
                    installed_arg = Path(str(selected_root)) if selected_root else None
                    installed_auto_resolution = {
                        **installed_auto_resolution,
                        "status": "unique_version_match",
                        "root_path": str(installed_arg) if installed_arg else None,
                        "selection_basis": "matching_plugin_version",
                    }
        if all_local_auto_cache and installed_auto_resolution.get("status") == "none":
            installed_auto_resolution = None
    cache_refresh = refresh_plugin_cache_layers(
        package_root=output,
        marketplace_dir=marketplace_arg,
        installed_dir=installed_arg if isinstance(installed_arg, Path) else None,
    )
    cache_status_after_refresh = build_plugin_cache_status(
        source_root=repo_root / "plugins" / "aippocampus",
        package_root=output,
        codex_home_path=codex_home_path,
        marketplace_dir=marketplace_arg,
        installed_dir=installed_arg if isinstance(installed_arg, Path) else None,
    )
    if installed_auto_resolution is not None:
        cache_refresh["installed_cache_auto_resolution"] = installed_auto_resolution
        installed_cache_status = str(
            (cache_status_after_refresh.get("installed_cache") or {}).get("status") or ""
        )
        cache_refresh["installed_cache_status"] = installed_cache_status
        auto_resolution_status = str(installed_auto_resolution.get("status") or "")
        if (
            auto_resolution_status not in RESOLVED_INSTALLED_CACHE_AUTO_STATUSES
            and installed_cache_status == "current"
        ):
            # Multiple cache generations are common after local dogfood installs.
            # If status can prove the active/default installed cache is already
            # current, `--all-local` should not turn a successful sync into a
            # path-selection chore. Only block when a refresh is actually needed.
            cache_refresh["auto_refresh_blocked"] = False
            cache_refresh["auto_refresh_skipped"] = True
            cache_refresh["skip_reason"] = "installed_cache_already_current"
            cache_refresh["requested_kind"] = "installed_cache_auto"
        elif auto_resolution_status not in RESOLVED_INSTALLED_CACHE_AUTO_STATUSES:
            cache_refresh["ok"] = False
            cache_refresh["requested"] = True
            cache_refresh["requested_kind"] = "installed_cache_auto"
            cache_refresh["auto_refresh_blocked"] = True
            cache_refresh["blocked_reason"] = str(
                installed_auto_resolution.get("status") or "installed_cache_auto_unresolved"
            )
            cache_refresh["next_command"] = (
                "aippocampus plugin install --codex --verify --compact-json"
            )
            cache_refresh["manual_selection_command"] = (
                "aippocampus update apply --surface plugin --plugin-installed-dir <path>"
            )
            cache_refresh["candidate_count"] = int(installed_auto_resolution.get("count") or 0)
    verification = compare_plugin(repo_root=repo_root, plugin_output=output)
    return {
        "surface": "plugin",
        "applied": True,
        "ok": verification["status"] == "current" and cache_refresh.get("ok", True),
        "builder": result,
        "verification": verification["diff"]["counts"],
        "cache_refresh": cache_refresh,
    }


def apply_hooks(args: argparse.Namespace) -> dict[str, Any]:
    codex_home_path = Path(args.codex_home).resolve() if args.codex_home else codex_home()
    hooks_path = (
        Path(args.hooks_json).resolve()
        if args.hooks_json
        else install_prompt.hooks_json_path(codex_home_path)
    )
    prompt = install_prompt.install(hooks_path)
    lifecycle = install_lifecycle.install(hooks_path)
    verification = status_hooks(codex_home_path, hooks_json=hooks_path)
    return {
        "surface": "hooks",
        "applied": True,
        "ok": verification["status"] == "current",
        "target_path": str(hooks_path),
        "prompt_changed": prompt.get("changed"),
        "lifecycle_changed": lifecycle.get("changed"),
        "verification": {
            "status": verification["status"],
            "prompt_installed": verification["prompt_installed"],
            "lifecycle_installed": verification["lifecycle_installed"],
        },
    }


def detect_only_apply(surface: str, args: argparse.Namespace) -> dict[str, Any]:
    status = build_status(args, mode="status")["surfaces"].get(surface, {})
    recommended_actions = status.get("recommended_actions") or []
    documented = status.get("documented_install_command")
    if documented:
        recommended_actions = [*recommended_actions, documented]
    return {
        "surface": surface,
        "applied": False,
        "ok": True,
        "status": status.get("status") or "detect_only",
        "message": (
            "this surface needs manual review; update status/plan reports the active path "
            "and recommended action without mutating user config"
        ),
        "recommended_actions": recommended_actions,
    }


def apply_update(args: argparse.Namespace) -> dict[str, Any]:
    surfaces = list(args.surface or [])
    if args.all_local:
        for surface in ("skill", "plugin", "hooks"):
            if surface not in surfaces:
                surfaces.append(surface)
    if not surfaces:
        raise ValueError("apply requires --surface <name> or --all-local")
    results: list[dict[str, Any]] = []
    for surface in surfaces:
        if surface == "skill":
            results.append(apply_skill(args))
        elif surface == "plugin":
            results.append(apply_plugin(args))
        elif surface == "hooks":
            results.append(apply_hooks(args))
        elif surface in {"cli", "mcp", "llm"}:
            results.append(detect_only_apply(surface, args))
        else:
            results.append(
                {
                    "surface": surface,
                    "applied": False,
                    "ok": True,
                    "status": "unsupported",
                }
            )
    post_status = build_status(args, mode="status")
    next_actions = update_actions.post_apply_next_actions(results)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_update_apply",
        "mode": "apply",
        "ok": all(bool(item.get("ok")) for item in results),
        "applied_surfaces": results,
        "post_status": post_status["summary"],
        "next_actions": next_actions,
        "safety_notes": post_status["safety_notes"],
    }


def render_text(report: dict[str, Any]) -> str:
    mode = report.get("mode")
    if mode == "apply":
        lines = ["AIppocampus update apply"]
        for item in report.get("applied_surfaces") or []:
            marker = "applied" if item.get("applied") else "detect-only"
            lines.append(f"- {item.get('surface')}: {marker}, status={item.get('status') or item.get('ok')}")
        post = report.get("post_status") or {}
        lines.append(f"- Magic ready: {str(post.get('magic_ready')).lower()}")
        if post.get("needs_action"):
            lines.append("- Still needs action: " + ", ".join(post.get("needs_action") or []))
        lines.extend(update_actions.apply_next_action_lines(report))
        return "\n".join(lines) + "\n"

    summary = report.get("summary") or {}
    surfaces = report.get("surfaces") or {}
    label = "plan" if mode == "plan" else "status"
    lines = [f"AIppocampus update {label}"]
    lines.extend(update_actions.foreground_status_lines(report))
    lines.append(f"- Core ready: {str(summary.get('core_ready')).lower()}")
    if summary.get("core_blockers"):
        lines.append("- Core blockers: " + ", ".join(summary.get("core_blockers") or []))
    lines.append(f"- Magic ready: {str(summary.get('magic_ready')).lower()}")
    if summary.get("magic_blockers"):
        lines.append("- Magic blockers: " + ", ".join(summary.get("magic_blockers") or []))
    if summary.get("optional_surfaces"):
        lines.append("- Optional surfaces: " + ", ".join(summary.get("optional_surfaces") or []))
    if summary.get("operator_surfaces"):
        lines.append("- Operator surfaces: " + ", ".join(summary.get("operator_surfaces") or []))
    lines.append(
        "- Agent-callable surfaces: "
        + str(summary.get("agent_callable_status") or "unknown")
    )
    if summary.get("capability_ladder"):
        lines.append("- First-run readiness:")
        for item in summary.get("capability_ladder") or []:
            lines.append(f"  {item.get('id')}: {item.get('status')}")
    for name in ("skill", "hooks", "llm", "cli", "mcp", "plugin", "agent_callable"):
        item = surfaces.get(name) or {}
        lines.append(f"- {name}: {item.get('status')}")
        if name == "llm" and not item.get("ready"):
            env_name = item.get("provider_env_var") or "DEEPSEEK_API_KEY"
            lines.append(f"  next: set {env_name} in the environment that launches the hook")
        if name == "hooks" and item.get("status") != "current":
            lines.append("  next: aippocampus update apply --surface hooks")
        if name == "cli" and not item.get("console_script_available_on_path"):
            lines.append("  warn: console script is not available on PATH")
        if name == "mcp":
            if item.get("package_artifact_current") and not item.get("mcp_command_resolves"):
                lines.append("  warn: MCP artifact is current but its command does not resolve")
                repairs = item.get("mcp_command_repair_options") or []
                if repairs:
                    lines.append("  next: " + str(repairs[0]))
            if item.get("mcp_command_uses_ambiguous_python"):
                lines.append("  warn: MCP command uses python; verify python vs python3 on this host")
        if name == "plugin":
            lines.extend(update_actions.plugin_cache_action_lines(item))
        if name == "agent_callable":
            lines.extend(update_actions.agent_callable_probe_lines(item))
    if mode == "plan":
        lines.append(
            "- Apply local package/effect surfaces together when that is really the goal: "
            "aippocampus update apply --all-local"
        )
        lines.append("- API key values are never read or written by update; configure the env var explicitly.")
    return "\n".join(lines) + "\n"


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root")
    parser.add_argument("--codex-home")
    parser.add_argument("--skill-target")
    parser.add_argument("--plugin-output")
    parser.add_argument("--plugin-marketplace-dir")
    parser.add_argument("--plugin-installed-dir")
    parser.add_argument("--mcp-config")
    parser.add_argument("--host-probe-report")
    parser.add_argument("--hooks-json")
    parser.add_argument("--model-route", default="default")
    parser.add_argument("--provider-env-var")
    parser.add_argument("--no-child-check", action="store_true")
    parser.add_argument(
        "--foreground-tools-visible",
        action="store_true",
        help="Assert that this foreground agent can see/call AIppocampus tools after a host probe.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--agent-json",
        action="store_true",
        help="Emit compact agent-facing JSON with readiness tiers and next actions.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aippocampus update")
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("status", "plan"):
        child = subparsers.add_parser(action)
        _add_common_options(child)
    apply_parser = subparsers.add_parser("apply")
    _add_common_options(apply_parser)
    apply_parser.add_argument(
        "--surface",
        action="append",
        choices=("skill", "cli", "mcp", "plugin", "hooks", "llm"),
        help="Local surface to apply. Repeat for multiple surfaces.",
    )
    apply_parser.add_argument(
        "--all-local",
        action="store_true",
        help="Apply local package/effect surfaces: skill, plugin package, and Codex hooks.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "apply":
            report = apply_update(args)
        else:
            report = build_status(args, mode=args.action)
    except Exception as exc:
        # Public CLI output must not echo raw exception text; install/update
        # failures can include local paths or environment-derived diagnostics.
        del exc
        if getattr(args, "json_output", False) or getattr(args, "agent_json", False):
            emit_public_text(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "kind": "aippocampus_update_error",
                        "ok": False,
                        "error": {
                            "code": "update_failed",
                            "message": "Update failed; rerun from a trusted shell for local diagnostics.",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            emit_public_text("AIppocampus update failed: update_failed", stream=sys.stderr)
        return 1

    if args.agent_json:
        emit_public_text(
            json.dumps(
                compact_agent_status_report(report, schema_version=SCHEMA_VERSION),
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
        )
    elif args.json_output:
        emit_public_text(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default))
    else:
        emit_public_text(render_text(report), end="")
    return 0 if report.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
