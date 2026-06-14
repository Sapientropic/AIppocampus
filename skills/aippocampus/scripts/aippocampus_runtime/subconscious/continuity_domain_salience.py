#!/usr/bin/env python3
"""Subconscious-job bridge for opt-in continuity-domain salience production."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.recall.continuity_domain_salience_adapter import (
    REPORT_MODE as CONTINUITY_DOMAIN_SALIENCE_REPORT_MODE,
)
from aippocampus_runtime.recall.continuity_domain_salience_adapter import (
    WRITE_WHEN_ENABLED_MODE as CONTINUITY_DOMAIN_SALIENCE_WRITE_MODE,
)
from aippocampus_runtime.recall.continuity_domain_salience_adapter import (
    adapt_salience_rows_to_continuity_domains,
)


def continuity_domain_salience_write_enabled(mode: str) -> bool:
    return mode == CONTINUITY_DOMAIN_SALIENCE_WRITE_MODE


def continuity_domain_salience_kwargs(config: Any) -> dict[str, Any]:
    return {
        "continuity_domain_salience_mode": config.continuity_domain_salience_mode,
        "continuity_domain_events_path": config.continuity_domain_events_path,
        "continuity_domain_snapshot_dir": config.continuity_domain_snapshot_dir,
        "continuity_domain_clean_source_dir": config.continuity_domain_clean_source_dir,
        "continuity_domain_publish": config.continuity_domain_publish,
    }


def add_continuity_domain_salience_args(parser: Any) -> None:
    parser.add_argument(
        "--continuity-domain-salience-mode",
        choices=[
            "off",
            CONTINUITY_DOMAIN_SALIENCE_REPORT_MODE,
            CONTINUITY_DOMAIN_SALIENCE_WRITE_MODE,
        ],
        default=None,
    )
    parser.add_argument("--continuity-domain-events-output")
    parser.add_argument("--continuity-domain-snapshot-dir")
    parser.add_argument("--continuity-domain-clean-source-dir")
    parser.add_argument("--continuity-domain-publish", action="store_true")


def _public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def public_continuity_domain_salience_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _mapping(report.get("metrics"))
    write = _mapping(report.get("write_report"))
    candidate_kinds = _mapping(report.get("candidate_event_kinds"))
    deferred_reasons = _mapping(report.get("deferred_reason_counts"))
    return {
        "enabled": bool(report.get("enabled")),
        "mode": str(report.get("mode") or "off"),
        "candidate_event_count": _public_count(metrics.get("candidate_event_count")),
        "deferred_event_count": _public_count(metrics.get("deferred_event_count")),
        "provider_call_count": _public_count(metrics.get("provider_call_count")),
        "candidate_event_kinds": {
            str(key): _public_count(value) for key, value in candidate_kinds.items()
        },
        "deferred_reason_counts": {
            str(key): _public_count(value) for key, value in deferred_reasons.items()
        },
        "write_status": str(write.get("status") or ""),
        "appended_event_count": _public_count(write.get("appended_event_count")),
        "duplicate_event_count": _public_count(write.get("duplicate_event_count")),
        "rejected_event_count": _public_count(write.get("rejected_event_count")),
        "publish_requested": bool(write.get("publish_requested")),
        "output_boundary": "continuity_domain_salience_summary_omits_source_refs_and_raw_text",
    }


def _continuity_domain_salience_paths(
    *,
    registry_path: Path,
    event_salience_output_path: Path | None,
    events_path: Path | None,
    snapshot_dir: Path | None,
) -> tuple[Path, Path]:
    base_dir = (event_salience_output_path or registry_path).resolve().parent
    return (
        Path(events_path).resolve() if events_path else base_dir / "continuity-domain-events.jsonl",
        Path(snapshot_dir).resolve() if snapshot_dir else base_dir / "continuity-domain-snapshots",
    )


def run_continuity_domain_salience_adapter(
    *,
    salience_report: Mapping[str, Any],
    registry_path: Path,
    event_salience_output_path: Path | None,
    mode: str,
    enabled: bool,
    events_path: Path | None,
    snapshot_dir: Path | None,
    clean_source_dir: Path | None,
    publish: bool,
    dry_run: bool,
    no_write: bool,
) -> dict[str, Any]:
    if mode in {"", "off", "none", "disabled"}:
        return {}
    adapter_mode = (
        CONTINUITY_DOMAIN_SALIENCE_WRITE_MODE
        if mode == CONTINUITY_DOMAIN_SALIENCE_WRITE_MODE
        else CONTINUITY_DOMAIN_SALIENCE_REPORT_MODE
    )
    resolved_events_path, resolved_snapshot_dir = _continuity_domain_salience_paths(
        registry_path=registry_path,
        event_salience_output_path=event_salience_output_path,
        events_path=events_path,
        snapshot_dir=snapshot_dir,
    )
    write_enabled = (
        adapter_mode == CONTINUITY_DOMAIN_SALIENCE_WRITE_MODE
        and bool(enabled)
        and not dry_run
        and not no_write
    )
    try:
        return adapt_salience_rows_to_continuity_domains(
            salience_report.get("sidecar_rows") or [],
            events_path=resolved_events_path,
            snapshot_dir=resolved_snapshot_dir,
            clean_source_dir=clean_source_dir,
            mode=adapter_mode,
            enabled=write_enabled,
            publish=bool(publish),
        )
    except Exception as exc:
        return {
            "kind": "aippocampus_continuity_domain_salience_adapter_report",
            "schema_version": 1,
            "ok": False,
            "mode": adapter_mode,
            "enabled": write_enabled,
            "metrics": {
                "candidate_event_count": 0,
                "deferred_event_count": 0,
                "provider_call_count": 0,
            },
            "write_report": {
                "status": "adapter_error",
                "appended_event_count": 0,
                "duplicate_event_count": 0,
                "rejected_event_count": 0,
                "publish_requested": bool(publish),
            },
            "error": compact_text(f"{type(exc).__name__}: {exc}", 500),
        }
