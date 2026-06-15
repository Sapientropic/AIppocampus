"""Bounded public projections for storage governance CLI output."""

from __future__ import annotations

from typing import Any


def _bounded_items(items: list[dict[str, Any]], *, limit: int) -> tuple[list[dict[str, Any]], bool]:
    safe_limit = max(0, int(limit))
    return (items[:safe_limit], len(items) > safe_limit)


def bounded_cli_projection(
    report: dict[str, Any],
    *,
    limit: int,
    summary_only: bool,
    schema_version: int,
) -> dict[str, Any]:
    """Return the foreground JSON shape for storage GC.

    Full storage plans can carry many candidate preconditions. Agent-facing JSON
    stays bounded by default; `--full` remains the operator audit path.
    """

    candidates = list(report.get("candidates") or [])
    sample, truncated = _bounded_items(candidates, limit=limit)
    projection = dict(report)
    projection["candidate_count_total"] = len(candidates)
    projection["candidates_returned"] = len(sample)
    projection["candidates_truncated"] = truncated
    projection["full_audit_available"] = True
    projection["full_audit_flag"] = "--full"
    if summary_only:
        projection = {
            "schema_version": report.get("schema_version", schema_version),
            "created_at": report.get("created_at"),
            "mode": report.get("mode"),
            "requested_class": report.get("requested_class"),
            "ok": report.get("ok", True),
            "metrics": report.get("metrics") or {},
            "candidate_count_total": len(candidates),
            "candidates_returned": len(sample),
            "candidates_truncated": truncated,
            "candidate_samples": [
                {
                    "id": item.get("id"),
                    "class": item.get("class"),
                    "tier": item.get("tier"),
                    "label": item.get("label"),
                    "human_bytes": item.get("human_bytes"),
                    "path": item.get("path"),
                }
                for item in sample
            ],
            "warnings": list(report.get("warnings") or [])[:6],
            "next_steps": list(report.get("next_steps") or [])[:4],
            "full_audit_available": True,
            "full_audit_flag": "--full",
        }
    else:
        projection["candidates"] = sample
    return projection
