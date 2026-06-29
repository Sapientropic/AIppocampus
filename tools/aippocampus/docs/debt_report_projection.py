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


def _first_warning(warnings: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not warnings:
        return None
    warning = warnings[0]
    return {
        key: warning[key]
        for key in ("code", "message", "acceptance_bearing", "refresh_command")
        if key in warning
    }


def _queue_warning(report: Mapping[str, Any]) -> dict[str, Any] | None:
    queues = report.get("actionable_debt_queues")
    if not isinstance(queues, Mapping):
        return None
    top = queues.get("top_queue")
    if not isinstance(top, Mapping):
        return None
    return {
        "code": str(top.get("queue_id") or "actionable_debt_queue"),
        "message": str(top.get("next_action") or "Review the top actionable debt queue."),
        "count": int(top.get("count") or 0),
        "sample_paths": list(top.get("sample_paths") or [])[:5],
    }


def _changed_surface_summary(changed_files: Sequence[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {"changed_file_count": len(changed_files)}
    affected = list(changed_files)[:3]
    if affected:
        summary["affected_files"] = affected
    if len(changed_files) > len(affected):
        summary["affected_files_truncated"] = True
    return summary


def _status_with_advisory(*, ok: object, warnings: Sequence[Mapping[str, Any]]) -> str:
    if not ok:
        return "fail"
    if warnings:
        return "advisory_action_recommended"
    return "pass"


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
        "status": _status_with_advisory(ok=report.get("ok"), warnings=warnings),
        "blockers": blockers,
        "warning_count": len(warnings),
        "first_warning": _first_warning(warnings),
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
            **_changed_surface_summary(changed_files),
            "acceptance_bearing_warning_count": warning_count,
        },
        "blockers": warnings if warning_count else [],
        "warning_count": len(warnings),
        "first_warning": _first_warning(warnings),
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
    top_queue = _queue_warning(report)
    return {
        "kind": "aippocampus_debt_report_compact",
        "ok": report.get("ok"),
        "status": _status_with_advisory(ok=report.get("ok"), warnings=warnings),
        "changed_surface": _changed_surface_summary(changed_files),
        "blockers": warnings if not report.get("ok") else [],
        "warning_count": len(warnings),
        "first_warning": top_queue or _first_warning(warnings),
        "top_actionable_queue": top_queue,
        "refresh_command": _warning_refresh_command(warnings),
        "detail_command": _detail_command(mode="full", changed_files=changed_files),
    }
