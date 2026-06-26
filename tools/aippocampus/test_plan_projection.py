from __future__ import annotations

from typing import Any, Mapping, Sequence

from test_plan_commands import py_script, shell_arg


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


def compact_changed_surface_plan(
    plan: Mapping[str, Any],
    *,
    changed_files: Sequence[str],
    base: str,
    local_executable: bool,
) -> dict[str, Any]:
    warnings = list(plan.get("warnings") or [])
    commands = list(plan.get("commands") or [])
    return {
        "kind": "aippocampus_changed_surface_test_plan_compact",
        "schema_version": 1,
        "ok": True,
        "status": "pass",
        "changed_surface": {
            "changed_file_count": len(changed_files),
            "changed_files": list(changed_files),
            "categories": list(plan.get("categories") or []),
        },
        "blockers": [],
        "warning_count": len(warnings),
        "warnings": warnings[:3],
        "preflight_command": _preflight_command(
            changed_files=changed_files,
            base=base,
            local_executable=local_executable,
        ),
        "planned_command_count": len(commands),
        "next_commands": [
            {
                "command": str(item.get("command") or ""),
                "scope": str(item.get("scope") or ""),
            }
            for item in commands[:3]
        ],
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
        "next_commands": [
            {
                "command": str(item.get("command") or ""),
                "scope": str(item.get("scope") or ""),
            }
            for item in local_required[:3]
        ],
        "planned_command_count": len(local_required),
        "detail_command": _detail_command(
            changed_files=[],
            base=base,
            release_preflight=True,
            local_executable=local_executable,
        ),
    }
