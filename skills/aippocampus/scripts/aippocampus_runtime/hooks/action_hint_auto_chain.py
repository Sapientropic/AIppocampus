"""Shared low-risk auto-chain policy for action-hint foreground flows."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.hooks.action_hint_cache import refresh_action_hint_cache
from aippocampus_runtime.local_file_lock import (
    OwnerCheckedFileLease,
    OwnerCheckedLeaseBusyError,
    OwnerCheckedLeaseChangedError,
)
from aippocampus_runtime.privacy import redact_private_paths

AUTO_CHAIN_DISABLE_VALUES = {"0", "false", "no", "off", "disabled"}
DEFAULT_AUTO_CHAIN_MAX_ELAPSED_MS = 1500
AUTO_CHAIN_SURFACES = {"action_probe", "action_status", "first_run_frontdoor"}


def _elapsed_ms(started_at: float | None) -> float:
    if started_at is None:
        return 0.0
    return round((time.perf_counter() - started_at) * 1000, 2)


def _env_allows_auto_chain() -> bool:
    raw = os.environ.get("AIPPOCAMPUS_ACTION_HINT_AUTO_CHAIN", "")
    return raw.strip().casefold() not in AUTO_CHAIN_DISABLE_VALUES


def _public_refresh_action(report: Mapping[str, Any]) -> dict[str, Any] | None:
    action = report.get("foreground_action")
    if not isinstance(action, Mapping):
        return None
    return {
        key: value
        for key, value in dict(action).items()
        if key
        in {
            "id",
            "label",
            "command",
            "command_template",
            "requires",
            "mutation_risk",
            "claim_boundary",
            "why",
        }
    }


def action_hint_refresh_auto_chain(
    *,
    cache_jsonl: Path | None,
    cache_status: str,
    cwd: Path | None = None,
    surface: str,
    started_at: float | None = None,
    max_elapsed_ms: int | None = DEFAULT_AUTO_CHAIN_MAX_ELAPSED_MS,
    enabled: bool = True,
) -> dict[str, Any]:
    """Refresh the prepared action-hint cache for explicit foreground flows.

    The hot PreToolUse hook never calls this helper. It is reserved for
    user/agent-invoked setup, status, and probe paths where a small local cache
    refresh removes a pointless foreground handoff. The local lease prevents
    several foreground agents from refreshing the same cache at once; the actual
    write remains owned by ``refresh_action_hint_cache`` and its atomic writer.
    """

    base: dict[str, Any] = {
        "kind": "aippocampus_action_hint_auto_chain",
        "surface": surface,
        "cache_status_before": str(cache_status or "unknown"),
        "mutation_risk": "low_risk_local_cache_write",
        "claim_boundary": "action_hints_are_navigation_not_source_truth",
    }
    if surface not in AUTO_CHAIN_SURFACES:
        return {
            **base,
            "status": "not_applicable",
            "reason": "surface_not_auto_chainable",
        }
    if str(cache_status or "") == "with_fresh_records":
        return {**base, "status": "skipped", "reason": "cache_already_fresh"}
    if not enabled or not _env_allows_auto_chain():
        return {**base, "status": "deferred", "reason": "auto_chain_disabled"}
    if cache_jsonl is None:
        return {**base, "status": "deferred", "reason": "cache_path_unavailable"}
    if max_elapsed_ms is not None and max_elapsed_ms <= 0:
        return {**base, "status": "deferred", "reason": "latency_budget_exhausted"}
    if (
        max_elapsed_ms is not None
        and started_at is not None
        and _elapsed_ms(started_at) >= float(max_elapsed_ms)
    ):
        return {**base, "status": "deferred", "reason": "latency_budget_exhausted"}

    started = time.perf_counter()
    path = Path(cache_jsonl)
    lease_path = path.with_suffix(path.suffix + ".auto-chain.lock")
    try:
        with OwnerCheckedFileLease(
            lease_path,
            lock_kind="action_hint_auto_chain",
            stale_after_seconds=120.0,
            wait_timeout_seconds=0.0,
            payload_extra={"surface": surface},
            busy_message="action hint auto-chain refresh already running",
        ):
            if (
                max_elapsed_ms is not None
                and started_at is not None
                and _elapsed_ms(started_at) >= float(max_elapsed_ms)
            ):
                return {
                    **base,
                    "status": "deferred",
                    "reason": "latency_budget_exhausted",
                    "elapsed_ms": _elapsed_ms(started),
                }
            report = refresh_action_hint_cache(
                cwd=cwd or Path.cwd(),
                cache_jsonl=path,
                write=True,
            )
    except OwnerCheckedLeaseBusyError:
        return {
            **base,
            "status": "deferred",
            "reason": "refresh_lock_busy",
            "elapsed_ms": _elapsed_ms(started),
        }
    except OwnerCheckedLeaseChangedError:
        return {
            **base,
            "status": "deferred",
            "reason": "refresh_lock_changed",
            "elapsed_ms": _elapsed_ms(started),
        }
    except Exception as exc:  # pragma: no cover - exercised through CLI recovery.
        return {
            **base,
            "status": "failed",
            "reason": "refresh_failed",
            "error_summary": redact_private_paths(f"{type(exc).__name__}: {exc}"),
            "elapsed_ms": _elapsed_ms(started),
        }

    action = _public_refresh_action(report)
    return {
        **base,
        "status": "auto_chained",
        "reason": "refreshed_cache",
        "elapsed_ms": _elapsed_ms(started),
        "cache_status_after": str(report.get("cache_status") or ""),
        "record_count": int((report.get("cache") or {}).get("record_count") or 0)
        if isinstance(report.get("cache"), Mapping)
        else 0,
        "action_hints_ready": bool(report.get("action_hints_ready")),
        **({"foreground_action": action} if action else {}),
    }
