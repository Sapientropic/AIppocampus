from __future__ import annotations

from typing import Any, Mapping, Sequence

from test_plan_commands import py_script, shell_arg

COMMAND_COMPACT_KEYS = (
    "command",
    "command_preview",
    "command_truncated",
    "scope",
    "gate_class",
    "verification_owner",
    "guard_id",
    "cost_budget",
    "ci_owned",
    "default_local",
)
COMPACT_CHANGED_FILE_SAMPLE_LIMIT = 3
COMPACT_CATEGORY_SAMPLE_LIMIT = 8
COMPACT_COMMAND_CHAR_LIMIT = 360


def _changed_file_args(changed_files: Sequence[str]) -> str:
    return " ".join(f"--changed-file {shell_arg(path)}" for path in changed_files)


def _changed_surface_args(
    *,
    changed_files: Sequence[str],
    base: str,
    changed_files_from_base: bool,
) -> str:
    if changed_files and not changed_files_from_base:
        return _changed_file_args(changed_files)
    return f"--base {shell_arg(base)}"


def _detail_command(
    *,
    changed_files: Sequence[str],
    base: str,
    release_preflight: bool,
    local_executable: bool,
    changed_files_from_base: bool = False,
) -> str:
    args = ["--json", "--detail full"]
    if release_preflight:
        args.append("--release-preflight")
    if local_executable:
        args.append("--local-executable")
    args.append(
        _changed_surface_args(
            changed_files=changed_files,
            base=base,
            changed_files_from_base=changed_files_from_base,
        )
    )
    return py_script("tools/aippocampus/test_plan.py", " ".join(args))


def _preflight_command(
    *,
    changed_files: Sequence[str],
    base: str,
    local_executable: bool,
    changed_files_from_base: bool = False,
) -> str:
    args = ["--json"]
    if local_executable:
        args.append("--local-executable")
    args.append(
        _changed_surface_args(
            changed_files=changed_files,
            base=base,
            changed_files_from_base=changed_files_from_base,
        )
    )
    return py_script("tools/aippocampus/changed_surface_preflight.py", " ".join(args))


def _compact_command(item: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key in COMMAND_COMPACT_KEYS:
        if key not in item or item[key] in {None, ""}:
            continue
        if key == "command":
            command = str(item[key])
            if len(command) > COMPACT_COMMAND_CHAR_LIMIT:
                row["command_preview"] = command[:COMPACT_COMMAND_CHAR_LIMIT].rstrip()
                row["command_truncated"] = True
                continue
        row[key] = item[key]
    return row


def _changed_surface_summary(
    *,
    changed_files: Sequence[str],
    categories: Sequence[Any],
    changed_files_from_base: bool,
) -> dict[str, Any]:
    sample = list(changed_files[:COMPACT_CHANGED_FILE_SAMPLE_LIMIT])
    category_sample = [str(item) for item in categories[:COMPACT_CATEGORY_SAMPLE_LIMIT]]
    return {
        "changed_file_count": len(changed_files),
        "affected_files": sample,
        "affected_files_truncated": len(changed_files) > len(sample),
        "category_summary": category_sample,
        "category_summary_truncated": len(categories) > len(category_sample),
        "input_source": "base_diff" if changed_files_from_base else "explicit_changed_files",
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
    changed_files_from_base: bool = False,
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
        "changed_surface": _changed_surface_summary(
            changed_files=changed_files,
            categories=list(plan.get("categories") or []),
            changed_files_from_base=changed_files_from_base,
        ),
        "blockers": [],
        "warning_count": len(warnings),
        "first_warning": _first_warning(warnings),
        "preflight_command": _preflight_command(
            changed_files=changed_files,
            base=base,
            local_executable=local_executable,
            changed_files_from_base=changed_files_from_base,
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
            changed_files_from_base=changed_files_from_base,
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
