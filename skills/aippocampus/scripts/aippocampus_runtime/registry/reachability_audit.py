"""Redacted reachability audit for registry-backed source routes."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION, redact_private_paths
from aippocampus_runtime.registry.store import load_registry, registry_paths


def _path_exists(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and Path(text).exists()


def _clean_source_messages_path(paths: Mapping[str, Any]) -> str:
    explicit = str(paths.get("clean_source_messages_jsonl") or "").strip()
    if explicit:
        return explicit
    clean_dir = str(paths.get("clean_source_dir") or "").strip()
    if clean_dir:
        return str(Path(clean_dir) / "messages.jsonl")
    return ""


def _row_state(entry: Mapping[str, Any]) -> dict[str, bool]:
    paths = entry.get("paths") if isinstance(entry.get("paths"), Mapping) else {}
    provider_known = bool(
        str(entry.get("source_provider") or "").strip()
        or (isinstance(entry.get("session_meta"), Mapping) and entry.get("session_meta"))
    )
    clean_messages = _clean_source_messages_path(paths)
    raw_reachable = _path_exists(paths.get("rollout"))
    clean_reachable = _path_exists(clean_messages)
    indexed = _path_exists(paths.get("sqlite")) or _path_exists(paths.get("messages_jsonl"))
    # Deepen/reopen route handles need a reachable clean-source row. SQLite may
    # help retrieval, but it is not by itself enough to quote or reopen source.
    deepenable = clean_reachable
    return {
        "provider_known": provider_known,
        "raw_source_reachable": raw_reachable,
        "clean_source_reachable": clean_reachable,
        "indexed": indexed,
        "deepenable": deepenable,
    }


def _count(rows: list[dict[str, bool]], key: str) -> int:
    return sum(1 for row in rows if row.get(key))


def render_reachability_audit(report: Mapping[str, Any]) -> str:
    counts = report.get("counts") if isinstance(report.get("counts"), Mapping) else {}
    action = report.get("foreground_action") if isinstance(report.get("foreground_action"), Mapping) else {}
    next_action = action.get("command") or action.get("command_template")
    lines = [
        f"registry source reachability: {report.get('status')}",
        f"registry rows: {counts.get('registry_rows', 0)}",
        f"clean-source reachable: {counts.get('clean_source_reachable_rows', 0)}",
        f"indexed: {counts.get('indexed_rows', 0)}",
        f"deepenable: {counts.get('deepenable_rows', 0)}",
    ]
    if next_action:
        lines.append(f"next: {next_action}")
    lines.append("boundary: local reachability counts are environment-specific.")
    return "\n".join(lines)


def _actions(*, degraded: bool) -> list[dict[str, Any]]:
    if degraded:
        return [
            foreground_shell_action(
                action_id="reconcile_registry_sources",
                label="Reconcile registered source rows",
                command="aippocampus registry reconcile-hook-seen --dry-run --json",
                why=(
                    "Some registry rows are not source-reachable; inspect a dry-run "
                    "reconciliation before claiming registry route health."
                ),
                mutation_risk="read_only",
                claim_boundary="local_reachability_audit_not_global_health",
            ),
            foreground_template_action(
                action_id="search_registered_sources",
                label="Search registered sources",
                command_template='aippocampus search --all "{distinctive_phrase}" --json',
                requires=["distinctive_phrase"],
                why="Use exact search after checking which registered source rows are reachable.",
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claim",
            ),
        ]
    return [
        foreground_template_action(
            action_id="search_registered_sources",
            label="Search registered sources",
            command_template='aippocampus search --all "{distinctive_phrase}" --json',
            requires=["distinctive_phrase"],
            why="The registry has reachable clean-source rows; search exact wording, then reopen before claims.",
            mutation_risk="read_only",
            claim_boundary="source_reopen_required_before_claim",
        )
    ]


def registry_source_reachability_audit(
    *,
    registry_dir: str | Path | None = None,
    include_paths: bool = False,
) -> dict[str, Any]:
    registry_root = Path(registry_dir).resolve() if registry_dir else None
    registry_json, _ = registry_paths(registry_root)
    payload = load_registry(registry_json)
    entries = [entry for entry in payload.get("threads") or [] if isinstance(entry, Mapping)]
    row_states = [_row_state(entry) for entry in entries]
    counts = {
        "registry_rows": len(entries),
        "provider_known_rows": _count(row_states, "provider_known"),
        "raw_source_reachable_rows": _count(row_states, "raw_source_reachable"),
        "clean_source_reachable_rows": _count(row_states, "clean_source_reachable"),
        "indexed_rows": _count(row_states, "indexed"),
        "deepenable_rows": _count(row_states, "deepenable"),
    }
    degraded = bool(entries) and counts["deepenable_rows"] < counts["registry_rows"]
    actions = _actions(degraded=degraded)
    report: dict[str, Any] = {
        "kind": "aippocampus_registry_source_reachability_audit",
        "ok": not degraded,
        "status": "empty" if not entries else "degraded" if degraded else "ok",
        "registry": str(registry_json),
        "counts": counts,
        "claim_boundary": (
            "local registry reachability audit; counts are environment-specific "
            "and do not prove global memory health"
        ),
        "source_boundary": {
            "registry_counts_are_not_source_reopen_proof": True,
            "clean_source_required_for_deepen_claim": True,
            "source_reopen_required_before_claim": True,
            "local_environment_specific": True,
        },
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_source_text_emitted": False,
            "capped_source_snippets_emitted": False,
        },
    }
    if include_paths:
        report["entries"] = [
            {
                "thread_key": entry.get("thread_key"),
                "paths": entry.get("paths") if isinstance(entry.get("paths"), Mapping) else {},
                "reachability": state,
            }
            for entry, state in zip(entries, row_states, strict=True)
        ]
    report.update(
        canonical_foreground_action_fields(
            actions[0] if actions else None,
            safe_next_actions=actions,
        )
    )
    return report if include_paths else redact_private_paths(report)


__all__ = ["registry_source_reachability_audit", "render_reachability_audit"]
