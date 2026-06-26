from __future__ import annotations

from typing import Any, Mapping, Sequence

SCRIPT = "python tools/aippocampus/docs/debt_report.py"


def _changed_args(changed_files: Sequence[str]) -> str:
    return " ".join(f"--changed-file {path}" for path in changed_files)


def _detail_command(*, mode: str, changed_files: Sequence[str]) -> str:
    parts = [SCRIPT, "--json", "--detail full"]
    if mode == "headroom":
        parts.append("--headroom-only")
    elif mode == "changed_surface":
        parts.append("--changed-surface-only")
    if changed_files:
        parts.append(_changed_args(changed_files))
    return " ".join(parts)


def _warning_refresh_command(warnings: Sequence[Mapping[str, Any]]) -> str | None:
    for warning in warnings:
        command = warning.get("refresh_command")
        if command:
            return str(command)
    return None


def compact_headroom_report(report: Mapping[str, Any]) -> dict[str, Any]:
    warnings = list(report.get("warnings") or [])
    blockers: list[dict[str, Any]] = []
    for path in report.get("missing_files") or []:
        blockers.append({"kind": "missing_file", "path": path})
    for row in report.get("over_budget") or []:
        blockers.append(
            {
                "kind": "over_budget",
                "path": row.get("path"),
                "current_count": row.get("current_count"),
                "guard_budget": row.get("guard_budget"),
                "margin": row.get("margin"),
            }
        )
    for row in report.get("stale_allowances") or []:
        blockers.append({"kind": "stale_allowance", "path": row.get("path")})
    return {
        "kind": "aippocampus_debt_headroom_compact",
        "ok": report.get("ok"),
        "status": "pass" if report.get("ok") else "fail",
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings[:3],
        "refresh_command": _warning_refresh_command(warnings),
        "detail_command": _detail_command(mode="headroom", changed_files=[]),
    }


def compact_changed_surface_report(
    report: Mapping[str, Any],
    *,
    changed_files: Sequence[str],
) -> dict[str, Any]:
    changed_surface = dict(report.get("changed_surface") or {})
    warnings = list(changed_surface.get("warnings") or [])
    warning_count = int(changed_surface.get("acceptance_bearing_warning_count") or 0)
    return {
        "kind": "aippocampus_changed_surface_debt_gate_compact",
        "ok": report.get("ok"),
        "status": changed_surface.get("status") or ("pass" if report.get("ok") else "fail"),
        "changed_surface": {
            "changed_file_count": len(changed_files),
            "changed_files": list(changed_files),
            "acceptance_bearing_warning_count": warning_count,
        },
        "blockers": warnings if warning_count else [],
        "warning_count": len(warnings),
        "detail_command": _detail_command(
            mode="changed_surface",
            changed_files=changed_files,
        ),
    }


def compact_debt_report(
    report: Mapping[str, Any],
    *,
    changed_files: Sequence[str],
) -> dict[str, Any]:
    warnings = list(report.get("warnings") or [])
    return {
        "kind": "aippocampus_debt_report_compact",
        "ok": report.get("ok"),
        "status": "pass" if report.get("ok") else "fail",
        "changed_surface": {
            "changed_file_count": len(changed_files),
            "changed_files": list(changed_files),
        },
        "blockers": warnings if not report.get("ok") else [],
        "warning_count": len(warnings),
        "warnings": warnings[:3],
        "refresh_command": _warning_refresh_command(warnings),
        "detail_command": _detail_command(mode="full", changed_files=changed_files),
    }
