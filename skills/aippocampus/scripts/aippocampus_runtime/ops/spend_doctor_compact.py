"""Bounded foreground spend-doctor builder."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime import core as runtime_core
from aippocampus_runtime.recall.semantic_recall_gate import semantic_gate_mode
from aippocampus_runtime.warm_ambient.scheduler import warm_background_enabled, warm_status_payload

__all__ = ["build_compact_spend_doctor_report"]

DEFAULT_DAYS = 7


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now(value: str | datetime | None) -> datetime:
    parsed: datetime | None = value if isinstance(value, datetime) else _parse_time(value)
    if parsed is None:
        parsed = _parse_time(runtime_core.now_utc())
    if parsed is None:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _subconscious_hook_enabled() -> bool:
    raw = os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_HOOK")
    return str(raw or "").strip().casefold() in {"1", "true", "on", "yes", "enabled"}


def _dream_delivery_mode() -> str:
    raw = str(os.environ.get("AIPPOCAMPUS_DREAM_DELIVERY_MODE") or "off").strip().casefold()
    return raw if raw in {"off", "shadow", "delivered"} else "custom"


def _reporting_boundary() -> dict[str, Any]:
    return {
        "registry_location_printed": False,
        "price_table_configured": False,
        "estimated_cost_supported": False,
        "cost_basis": "tokens_only_no_provider_billing_scrape",
    }


def _warm_queue_health(root: Path, *, now: datetime) -> dict[str, Any]:
    status = warm_status_payload(job_dir=root / "ambient_warm_jobs", now=now)
    activity = status.get("job_activity") if isinstance(status.get("job_activity"), Mapping) else {}
    return runtime_core.sanitize_external_model_payload(
        {
            "status": status.get("status"),
            "enabled": bool(status.get("enabled")),
            "action_code": status.get("action_code"),
            "next_command": status.get("next_command"),
            "status_command": activity.get("status_command") or "aippocampus warm status --json",
            "queue_state": activity.get("queue_state"),
            "pending_stale_count": _safe_int(activity.get("pending_stale_count")),
            "pending_recent_count": _safe_int(activity.get("pending_recent_count")),
            "completed_count": _safe_int(activity.get("completed_count")),
            "worker_process_active": bool(activity.get("worker_process_active")),
            "ordinary_recall_usable": bool(status.get("ordinary_recall_usable")),
            "boundary": "warm ambient queue health is optional; source-backed recall can continue",
        }
    )


def _compact_route_artifact_scan() -> dict[str, Any]:
    return {
        "status": "deferred",
        "reason": (
            "Compact foreground spend doctor avoids route artifact scans; open "
            "the full operator report when route-level token/yield telemetry is needed."
        ),
        "bounded_checks_completed": ["warm_queue_health"],
        "effective_tokens_known": False,
        "full_report_command": "aippocampus doctor spend --detail full --json",
    }


def _compact_spend_decision(
    *,
    warm_queue_health: Mapping[str, Any],
    reporting_boundary: Mapping[str, Any],
    route_artifact_scan: Mapping[str, Any],
) -> dict[str, Any]:
    warm_blocked = bool(
        warm_queue_health.get("status") == "blocked"
        and (
            warm_queue_health.get("queue_state") == "blocked_stale_pending"
            or _safe_int(warm_queue_health.get("pending_stale_count")) > 0
        )
    )
    if warm_blocked:
        action = "inspect"
        reason = (
            "Warm ambient has a blocked stale queue; reconcile warm status before "
            "launching more optional background work."
        )
        inspect_routes = ["warm_ambient"]
    else:
        action = "continue"
        reason = (
            "Route-level spend/yield scan is deferred in the compact foreground card; "
            "continue current work unless the user explicitly needs operator telemetry."
        )
        inspect_routes = []
    return {
        "action": action,
        "reason": reason,
        "highest_spend_route": {},
        "lowest_yield_route": {},
        "routes_to_pause_or_inspect": inspect_routes,
        "usage_telemetry_gaps": [],
        "warm_queue_health": dict(warm_queue_health),
        "route_artifact_scan": dict(route_artifact_scan),
        "estimated_cost_supported": bool(reporting_boundary.get("estimated_cost_supported")),
        "cost_basis": reporting_boundary.get("cost_basis"),
        "cost_explanation": "token volume only; provider billing dashboards are not scraped",
        "safe_next_command": "aippocampus doctor spend --detail full --json",
    }


def build_compact_spend_doctor_report(
    *,
    registry_dir: Path | str | None = None,
    days: int = DEFAULT_DAYS,
    now: str | datetime | None = None,
    warn_effective_tokens: int = 0,
    warn_min_foreground_value_rate: float = 0.0,
) -> dict[str, Any]:
    """Build the bounded default spend-doctor report used by foreground JSON.

    Full spend doctor scans route artifacts and JSONL history. This compact
    builder keeps bounded checks that affect immediate UX, then marks route
    spend/yield telemetry as deferred instead of fabricating "0 tokens" claims.
    """

    del warn_effective_tokens, warn_min_foreground_value_rate
    root = Path(registry_dir).resolve() if registry_dir else runtime_core.aippocampus_registry_dir()
    window_days = max(1, int(days or DEFAULT_DAYS))
    now_dt = _now(now)
    since = now_dt - timedelta(days=window_days)
    route_artifact_scan = _compact_route_artifact_scan()
    warm_queue_health = _warm_queue_health(root, now=now_dt)
    warm_queue_blocked = bool(warm_queue_health.get("status") == "blocked")
    reporting_boundary = _reporting_boundary()
    decision = _compact_spend_decision(
        warm_queue_health=warm_queue_health,
        reporting_boundary=reporting_boundary,
        route_artifact_scan=route_artifact_scan,
    )
    report = {
        "schema_version": 1,
        "kind": "aippocampus_spend_doctor",
        "ok": True,
        "status": "warning" if warm_queue_blocked else "partial",
        "generated_at": now_dt.isoformat().replace("+00:00", "Z"),
        "window": {
            "days": window_days,
            "since": since.isoformat().replace("+00:00", "Z"),
            "until": now_dt.isoformat().replace("+00:00", "Z"),
        },
        "privacy_boundary": {
            "raw_prompts_included": False,
            "raw_source_text_included": False,
            "api_keys_included": False,
            "local_paths_included": False,
            "provider_billing_credentials_included": False,
            "artifact_paths_included": False,
        },
        "totals": {"spend": {"effective_tokens": 0, "request_count": 0, "known_usage": False}, "yield": {}},
        "warnings": [],
        "warning_codes": ["blocked_warm_queue:warm_ambient"] if warm_queue_blocked else [],
        "warm_queue_health": warm_queue_health,
        "route_artifact_scan": route_artifact_scan,
        "budget_guardrails": {
            "routes_to_pause_or_inspect": decision["routes_to_pause_or_inspect"],
            "runtime_policy": {
                "prompt_hook_fail_open": True,
                "doctor_only_no_model_calls": True,
                "provider_billing_dashboard_scraped": False,
            },
            "operator_switches": {
                "warm_ambient": {
                    "env": "AIPPOCAMPUS_WARM_RECALL_BACKGROUND",
                    "enabled": warm_background_enabled(),
                },
                "semantic_gate": {"env": "AIPPOCAMPUS_SEMANTIC_GATE", "mode": semantic_gate_mode()},
                "subconscious": {
                    "env": "AIPPOCAMPUS_SUBCONSCIOUS_HOOK",
                    "enabled": _subconscious_hook_enabled(),
                },
                "dream_delivery": {
                    "env": "AIPPOCAMPUS_DREAM_DELIVERY_MODE",
                    "mode": _dream_delivery_mode(),
                },
            },
        },
        "reporting_boundary": reporting_boundary,
        "decision": decision,
    }
    return runtime_core.sanitize_external_model_payload(report)
