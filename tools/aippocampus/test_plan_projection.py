from __future__ import annotations

from typing import Any, Mapping, Sequence

from test_plan_commands import py_script, shell_arg

COMMAND_COMPACT_KEYS = (
    "command",
    "scope",
    "gate_class",
    "verification_owner",
    "guard_id",
    "cost_budget",
    "ci_owned",
    "default_local",
)


def _changed_file_args(changed_files: Sequence[str]) -> str:
    return " ".join(f"--changed-file {shell_arg(path)}" for path in changed_files)


def _detail_command(
    *,
    changed_files: Sequence[str],
    base: str,
    release_preflight: bool,
    local_executable: bool,
) -> str:
    args = ["--json", "--detail full"]
    if release_preflight:
        args.append("--release-preflight")
    if local_executable:
        args.append("--local-executable")
    if changed_files:
        args.append(_changed_file_args(changed_files))
    else:
        args.append(f"--base {shell_arg(base)}")
    return py_script("tools/aippocampus/test_plan.py", " ".join(args))


def _preflight_command(
    *,
    changed_files: Sequence[str],
    base: str,
    local_executable: bool,
) -> str:
    args = ["--json"]
    if local_executable:
        args.append("--local-executable")
    if changed_files:
        args.append(_changed_file_args(changed_files))
    else:
        args.append(f"--base {shell_arg(base)}")
    return py_script("tools/aippocampus/changed_surface_preflight.py", " ".join(args))


def _compact_command(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in COMMAND_COMPACT_KEYS
        if key in item and item[key] not in {None, ""}
    }


def _compact_next_commands(commands: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected = list(commands[:3])
    selected_commands = {str(item.get("command") or "") for item in selected}
    for item in commands[3:]:
        if str(item.get("scope") or "") != "packaged-runtime":
            continue
        command = str(item.get("command") or "")
        if command and command not in selected_commands:
            selected.append(item)
        break
    return [_compact_command(item) for item in selected]


def _first_warning(warnings: Sequence[Any]) -> dict[str, Any] | None:
    if not warnings:
        return None
    warning = warnings[0]
    if not isinstance(warning, Mapping):
        return {"message": str(warning)}
    return {
        key: warning[key]
        for key in ("kind", "severity", "message", "next_action")
        if key in warning
    }


def _compact_manual_claim(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("gate_class", "verification_owner", "guard_id", "reason")
        if key in item and item[key] not in {None, ""}
    }


def compact_changed_surface_plan(
    plan: Mapping[str, Any],
    *,
    changed_files: Sequence[str],
    base: str,
    local_executable: bool,
) -> dict[str, Any]:
    warnings = list(plan.get("warnings") or [])
    commands = list(plan.get("commands") or [])
    manual_required = [
        item for item in list(plan.get("manual_required_claims") or []) if isinstance(item, Mapping)
    ]
    has_manual_required = bool(manual_required)
    return {
        "kind": "aippocampus_changed_surface_test_plan_compact",
        "schema_version": 1,
        "ok": not has_manual_required,
        "status": "manual_required" if has_manual_required else "pass",
        "changed_surface": {
            "changed_file_count": len(changed_files),
            "changed_files": list(changed_files),
            "categories": list(plan.get("categories") or []),
        },
        "blockers": [],
        "warning_count": len(warnings),
        "first_warning": _first_warning(warnings),
        "preflight_command": _preflight_command(
            changed_files=changed_files,
            base=base,
            local_executable=local_executable,
        ),
        "planned_command_count": len(commands),
        "next_commands": _compact_next_commands(commands),
        "manual_required_claim_count": len(manual_required),
        "first_manual_required_claim": (
            _compact_manual_claim(manual_required[0]) if manual_required else None
        ),
        "detail_command": _detail_command(
            changed_files=changed_files,
            base=base,
            release_preflight=False,
            local_executable=local_executable,
        ),
    }


def compact_release_preflight_plan(
    plan: Mapping[str, Any],
    *,
    base: str,
    local_executable: bool,
) -> dict[str, Any]:
    local_required = list(plan.get("local_required") or [])
    return {
        "kind": "aippocampus_release_preflight_plan_compact",
        "schema_version": 1,
        "ok": True,
        "status": "pass",
        "changed_surface": {"changed_file_count": 0, "changed_files": []},
        "blockers": [],
        "preflight_command": None,
        "next_commands": [_compact_command(item) for item in local_required[:3]],
        "planned_command_count": len(local_required),
        "detail_command": _detail_command(
            changed_files=[],
            base=base,
            release_preflight=True,
            local_executable=local_executable,
        ),
    }
