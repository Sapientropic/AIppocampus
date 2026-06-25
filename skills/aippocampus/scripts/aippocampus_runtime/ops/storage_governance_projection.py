"""Bounded public projections for storage governance CLI output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.ops.storage_governance_actions import storage_gc_summary_actions


def _bounded_items(items: list[dict[str, Any]], *, limit: int) -> tuple[list[dict[str, Any]], bool]:
    safe_limit = max(0, int(limit))
    return (items[:safe_limit], len(items) > safe_limit)


def _candidate_handle(item: dict[str, Any]) -> str:
    return core.stable_text_fingerprint(
        str(item.get("id") or item.get("label") or item.get("kind") or "candidate"),
        namespace="storage-gc-candidate",
        length=12,
        prefix="candidate",
    )


def _identifier_handle(value: Any, *, prefix: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return core.stable_text_fingerprint(
        text,
        namespace=f"storage-gc-{prefix}",
        length=12,
        prefix=prefix,
    )


def _public_path_projection(path: Any, *, include_private_identifiers: bool) -> Any:
    if include_private_identifiers or not isinstance(path, dict):
        return path
    result = {
        "path_known": bool(path.get("path_known")),
        "relative_to": path.get("relative_to"),
    }
    private_path = path.get("path") or path.get("relative_path") or path.get("path_label")
    if private_path:
        result["path_handle"] = _identifier_handle(private_path, prefix="path")
        result["relative_path_omitted"] = True
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def _public_source_report(source_report: Any, *, include_private_identifiers: bool) -> Any:
    if include_private_identifiers or not isinstance(source_report, dict):
        return source_report
    private_keys = {
        "item_id",
        "thread_key",
        "thread_dir",
        "generation",
        "current_generation",
        "last_known_good_generation",
    }
    result: dict[str, Any] = {}
    for key, value in source_report.items():
        if key in private_keys:
            handle = _identifier_handle(value, prefix=key.replace("_", "-"))
            if handle:
                result[f"{key}_handle"] = handle
                result[f"{key}_omitted"] = True
            continue
        result[key] = value
    return result


def _public_preconditions(preconditions: Any, *, include_private_identifiers: bool) -> Any:
    if include_private_identifiers or not isinstance(preconditions, dict):
        return preconditions
    summary: dict[str, Any] = {}
    for key, value in preconditions.items():
        if not isinstance(value, dict):
            summary[key] = value
            continue
        summary[key] = {
            item_key: item_value
            for item_key, item_value in {
                "status": value.get("status"),
                "reason_code": value.get("reason_code"),
                "action": value.get("action"),
            }.items()
            if item_value not in (None, "", [])
        }
    return summary


def redact_report_sources(sources: dict[str, Any], *, include_paths: bool) -> dict[str, Any]:
    def short_path_label(value: str) -> str:
        parts = Path(value).parts
        return "/".join(parts[-3:]) if len(parts) >= 3 else Path(value).name

    if include_paths:
        return sources
    redacted: dict[str, Any] = {}
    for name, source in sources.items():
        redacted_source = dict(source)
        if "path" in redacted_source:
            redacted_source["path_label"] = Path(str(redacted_source.pop("path"))).name
        if "attempted" in redacted_source:
            redacted_source["attempted_labels"] = [
                short_path_label(str(item)) for item in redacted_source.pop("attempted")
            ]
        redacted[name] = redacted_source
    return redacted


def render_text(plan: dict[str, Any]) -> str:
    metrics = plan["metrics"]
    sources = plan["report_sources"]
    lines = [
        "AIppocampus storage governance dry-run",
        f"- Requested class: {plan['requested_class']}",
        f"- Protected source: {metrics['protected_source_human']}",
        f"- Reclaimable rebuildable cache: {metrics['reclaimable_rebuildable_human']}",
        f"- Reclaimable review artifacts: {metrics['reclaimable_review_artifact_human']}",
        f"- Generated index amplification: {metrics['generated_index_amplification_ratio']}x",
        f"- Candidates: {metrics['eviction_candidate_count']}",
        f"- Capacity report: {sources['capacity']['mode']}",
        f"- Retention report: {sources['retention']['mode']}",
        "",
        "Candidates:",
    ]
    if not plan["candidates"]:
        lines.append("- none")
    for candidate in plan["candidates"]:
        path = candidate.get("path") or {}
        path_hint = path.get("relative_path") or path.get("path_label") or "path not shown"
        lines.append(
            f"- [{candidate['class']}] {candidate['label']}: {candidate['human_bytes']} "
            f"({path_hint})"
        )
    if plan["warnings"]:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in plan["warnings"])
    lines.extend(["", "Next steps:"])
    lines.extend(f"- {step}" for step in plan["next_steps"])
    lines.append("")
    return "\n".join(lines)


def render_apply_text(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    lines = [
        "AIppocampus storage governance apply",
        f"- Requested class: {result['requested_class']}",
        f"- Applied: {metrics['eviction_applied_count']}",
        f"- Blocked: {metrics['eviction_blocked_count']}",
        f"- Reclaimed: {metrics['reclaimed_human']}",
        "",
        "Applied:",
    ]
    if not result["applied"]:
        lines.append("- none")
    for item in result["applied"]:
        manifest = item.get("manifest") or item.get("manifest_label")
        lines.append(f"- {item['candidate_id']}: {item['human_bytes']} (manifest: {manifest})")
    if result["blocked"]:
        lines.extend(["", "Blocked:"])
        for item in result["blocked"]:
            lines.append(f"- {item['candidate_id']}: {item['reason_code']}")
    if result.get("skipped"):
        lines.extend(["", "Skipped:"])
        for item in result["skipped"]:
            lines.append(f"- {item['candidate_id']}: {item['reason_code']}")
    if result["warnings"]:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in result["warnings"])
    lines.append("")
    return "\n".join(lines)


def _public_candidate(
    item: dict[str, Any],
    *,
    include_private_identifiers: bool,
    summary_only: bool,
) -> dict[str, Any]:
    if include_private_identifiers:
        return item
    handle = _candidate_handle(item)
    label_kind = str(item.get("kind") or item.get("class") or "storage_candidate")
    result = {
        "id": handle,
        "candidate_handle": handle,
        "class": item.get("class"),
        "tier": item.get("tier"),
        "label": label_kind.replace("_", " "),
        "kind": item.get("kind"),
        "bytes": item.get("bytes"),
        "human_bytes": item.get("human_bytes"),
        "path": _public_path_projection(
            item.get("path"),
            include_private_identifiers=include_private_identifiers,
        ),
        "source_report": _public_source_report(
            item.get("source_report"),
            include_private_identifiers=include_private_identifiers,
        ),
        "preconditions": _public_preconditions(
            item.get("preconditions"),
            include_private_identifiers=include_private_identifiers,
        ),
    }
    if not summary_only:
        result["actionability"] = item.get("actionability")
        result["plan_only_reason"] = item.get("plan_only_reason")
        result["rebuild_command"] = item.get("rebuild_command")
        result["rebuild_note"] = item.get("rebuild_note")
        result["expected_rebuild_cost"] = item.get("expected_rebuild_cost")
    return {key: value for key, value in result.items() if value not in (None, "", [])}


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
    raw_privacy = report.get("privacy")
    privacy: dict[str, Any] = raw_privacy if isinstance(raw_privacy, dict) else {}
    include_private_identifiers = bool(
        privacy.get("local_private_identifiers_included") or privacy.get("absolute_paths_included")
    )
    public_sample = [
        _public_candidate(
            item,
            include_private_identifiers=include_private_identifiers,
            summary_only=summary_only,
        )
        for item in sample
    ]
    projection = dict(report)
    projection["candidate_count_total"] = len(candidates)
    projection["candidates_returned"] = len(sample)
    projection["candidates_truncated"] = truncated
    projection["full_audit_available"] = True
    projection["full_audit_flag"] = "--full"
    projection["status"] = report.get("status") or "dry_run_ready"
    projection["ok"] = bool(report.get("ok", True))
    if isinstance(projection.get("privacy"), dict) and not include_private_identifiers:
        projection["privacy"] = {
            **projection["privacy"],
            "local_private_identifiers_included": False,
            "raw_session_like_ids_emitted": False,
        }
    if summary_only:
        metrics = report.get("metrics") or {}
        audit_command = (
            f"aippocampus storage gc --dry-run --json --top {max(1, int(limit))} --cwd ."
        )
        pressure_present = bool(candidates) or any(
            int(metrics.get(key) or 0) > 0
            for key in (
                "reclaimable_rebuildable_bytes",
                "reclaimable_review_artifact_bytes",
            )
        )
        apply_candidate_present = any(
            str(item.get("actionability") or "") != "plan_only_aggregate"
            for item in candidates
        )
        summary_actions = storage_gc_summary_actions(
            limit=limit,
            include_apply=apply_candidate_present and pressure_present,
        )
        action_fields = canonical_foreground_action_fields(
            summary_actions[0],
            safe_next_actions=summary_actions,
        )
        projection = {
            "kind": "aippocampus_storage_gc_summary",
            "schema_version": report.get("schema_version", schema_version),
            "ok": bool(report.get("ok", True)),
            "status": report.get("status") or ("dry_run_ready" if pressure_present else "no_pressure"),
            "created_at": report.get("created_at"),
            "mode": report.get("mode"),
            "read_only": report.get("mode") == "dry_run",
            "requested_class": report.get("requested_class"),
            "privacy": {
                "local_private_identifiers_included": include_private_identifiers,
                "raw_session_like_ids_emitted": include_private_identifiers,
            },
            "metrics": metrics,
            "metrics_status": "computed",
            "pressure_interpretation": "pressure_present" if pressure_present else "no_pressure",
            "candidate_count_total": len(candidates),
            "sample_candidate_count": 0,
            "candidate_detail_deferred": bool(candidates),
            "category_summary": {
                "rebuildable_cache": {
                    "reclaimable_bytes": metrics.get("reclaimable_rebuildable_bytes", 0),
                    "reclaimable_human": metrics.get("reclaimable_rebuildable_human"),
                    "apply_boundary": "explicit_apply_only",
                },
                "review_artifacts": {
                    "reclaimable_bytes": metrics.get("reclaimable_review_artifact_bytes", 0),
                    "reclaimable_human": metrics.get("reclaimable_review_artifact_human"),
                    "apply_boundary": "operator_review_only",
                },
            },
            "risk_boundary": {
                "apply_requires_explicit_flag": True,
                "summary_performs_writes": False,
                "source_history_protected": True,
                "full_candidate_preconditions_deferred": True,
            },
            **action_fields,
            "safe_next_action": {
                "decision": "continue without cleanup unless the user explicitly wants storage detail",
                "continue_without_command": True,
                "no_command_needed": True,
                "instruction": "Continue the user's foreground work without running storage cleanup.",
            },
            "comparable_metrics_command": audit_command,
            "warnings": list(report.get("warnings") or [])[:6],
            "next_steps": [
                "Continue normal work when cleanup was not the user goal.",
                "Use the bounded audit sample only if the reclaimable amount is worth inspecting.",
                "Use apply only for rebuildable cache candidates after deterministic checks pass.",
            ],
            "full_audit_available": True,
            "full_audit_flag": "--json --full",
            "operator_audit_command": "aippocampus storage gc --dry-run --json --full --cwd .",
        }
    else:
        projection["candidates"] = public_sample
    return projection
