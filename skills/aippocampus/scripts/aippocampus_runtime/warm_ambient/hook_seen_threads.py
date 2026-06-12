"""Private hook-seen thread ledger for registry reconciliation.

Prompt hooks can observe a fresh Codex thread before lifecycle registration has
materialized clean-source artifacts. This ledger is intentionally tiny: it
records only thread identity and hashed workspace metadata so a later health or
repair command can detect "hook saw it, registry missed it" without treating
the warm cache as source evidence.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc, stable_text_fingerprint, workspace_fingerprint

HOOK_SEEN_SCHEMA_VERSION = 1
DEFAULT_HOOK_SEEN_LEDGER_NAME = "hook_seen_threads.jsonl"
DEFAULT_HOOK_SEEN_STALE_AFTER_SECONDS = 24 * 60 * 60

HOOK_SEEN_STATE_REGISTERED = "registered"
HOOK_SEEN_STATE_PENDING_REPAIR = "pending_repair"
HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED = "blocked_or_unsupported"
HOOK_SEEN_STATE_STALE_LEDGER_ROW = "stale_ledger_row"

HOOK_SEEN_REGISTRATION_EXPECTATION = "registry_clean_source_or_blocked"
HOOK_SEEN_BLOCK_EXPECTATIONS = {
    "blocked_or_unsupported",
    "ignore_or_blocked",
    "unsupported",
    "private_or_unsupported",
}


def hook_seen_ledger_path_for_cache(cache_path: Path | str) -> Path:
    return Path(cache_path).resolve().with_name(DEFAULT_HOOK_SEEN_LEDGER_NAME)


def hook_seen_ledger_path_for_registry(registry_path: Path | str) -> Path:
    return Path(registry_path).resolve().parent / DEFAULT_HOOK_SEEN_LEDGER_NAME


def thread_key_from_hook_thread_id(thread_id: str | None) -> str | None:
    text = str(thread_id or "").strip()
    if not text:
        return None
    if ":" in text:
        return text
    return f"session:{text}"


def hook_seen_thread_ref(thread_key: str | None) -> str:
    text = str(thread_key or "").strip()
    if not text:
        return ""
    return stable_text_fingerprint(text, namespace="hook-seen-thread", prefix="hst")


def _topic_epoch_ref(topic_epoch: str | None) -> str:
    text = str(topic_epoch or "").strip()
    if not text:
        return ""
    return stable_text_fingerprint(text, namespace="hook-seen-topic", prefix="hstp")


def record_hook_seen_thread(
    ledger_path: Path | str,
    *,
    thread_id: str | None,
    workspace: str,
    current_thread_key: str | None = None,
    topic_epoch: str | None = None,
    event: str = "UserPromptSubmit",
) -> dict[str, Any]:
    thread_key = current_thread_key or thread_key_from_hook_thread_id(thread_id)
    if not thread_key:
        return {"status": "skipped", "reason": "missing_thread_id"}
    path = Path(ledger_path).resolve()
    row = {
        "kind": "aippocampus_hook_seen_thread",
        "schema_version": HOOK_SEEN_SCHEMA_VERSION,
        "recorded_at": now_utc(),
        "event": event,
        # This ledger is only a reconciliation queue. It must not become a
        # second source of raw thread identity, prompt text, or topic labels;
        # scan/health paths compare the same deterministic refs instead.
        "thread_ref": hook_seen_thread_ref(thread_key),
        "workspace_ref": workspace_fingerprint(workspace, prefix="workspace"),
        "topic_epoch_ref": _topic_epoch_ref(topic_epoch),
        "registration_expectation": HOOK_SEEN_REGISTRATION_EXPECTATION,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "status": "recorded",
        "thread_ref": row["thread_ref"],
        "ledger_private": True,
    }


def load_hook_seen_rows(path: Path | str, *, max_rows: int = 512) -> list[dict[str, Any]]:
    ledger = Path(path)
    if not ledger.exists():
        return []
    rows: list[dict[str, Any]] = []
    with ledger.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                row = dict(parsed)
                thread_ref = str(row.get("thread_ref") or "").strip()
                legacy_thread_key = str(row.get("thread_key") or "").strip()
                if not thread_ref and legacy_thread_key:
                    row["thread_ref"] = hook_seen_thread_ref(legacy_thread_key)
                if row.get("thread_ref"):
                    rows.append(row)
    if max_rows > 0 and len(rows) > max_rows:
        rows = rows[-max_rows:]
    return rows


def latest_hook_seen_by_ref(path: Path | str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in load_hook_seen_rows(path):
        thread_ref = str(row.get("thread_ref") or "")
        if thread_ref:
            latest[thread_ref] = row
    return latest


def latest_hook_seen_by_thread(path: Path | str) -> dict[str, dict[str, Any]]:
    return latest_hook_seen_by_ref(path)


def hook_seen_thread_refs(path: Path | str) -> set[str]:
    return set(latest_hook_seen_by_ref(path))


def hook_seen_thread_keys(path: Path | str) -> set[str]:
    return {
        str(row.get("thread_key") or "")
        for row in load_hook_seen_rows(path)
        if str(row.get("thread_key") or "").strip()
    }


def _parse_recorded_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(value: Any, *, now: datetime | None = None) -> int | None:
    parsed = _parse_recorded_at(value)
    if parsed is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, int((current - parsed).total_seconds()))


def _row_thread_ref(row: dict[str, Any]) -> str:
    thread_ref = str(row.get("thread_ref") or "").strip()
    if thread_ref:
        return thread_ref
    return hook_seen_thread_ref(str(row.get("thread_key") or ""))


def _row_is_blocked_or_unsupported(row: dict[str, Any]) -> bool:
    expectation = str(row.get("registration_expectation") or "").strip()
    if expectation in HOOK_SEEN_BLOCK_EXPECTATIONS:
        return True
    return bool(row.get("blocked_or_unsupported") or row.get("unsupported_reason"))


def project_hook_seen_state(
    row: dict[str, Any],
    *,
    registered_refs: set[str],
    discoverable_refs: set[str] | None = None,
    stale_after_seconds: int = DEFAULT_HOOK_SEEN_STALE_AFTER_SECONDS,
    now: datetime | None = None,
    include_private_keys: bool = False,
) -> dict[str, Any]:
    """Project one private ledger row into a privacy-safe repair state.

    Hook output is not source evidence. These states only steer the operator or
    repair command toward provider discovery and clean-source registration, and
    deliberately avoid re-emitting raw hook thread ids by default.
    """
    thread_ref = _row_thread_ref(row)
    age = _age_seconds(row.get("recorded_at"), now=now)
    candidate: dict[str, Any] = {
        "thread_ref": thread_ref,
        "age_seconds": age,
    }
    if include_private_keys and row.get("thread_key"):
        candidate["thread_key"] = row.get("thread_key")

    if _row_is_blocked_or_unsupported(row):
        candidate.update(
            {
                "state": HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED,
                "status": HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED,
                "diagnostic": "blocked_or_unsupported_boundary",
                "next_action": "inspect_hook_seen_support_boundary",
            }
        )
        if row.get("unsupported_reason"):
            candidate["reason"] = str(row.get("unsupported_reason"))
        return candidate

    if thread_ref in registered_refs:
        candidate.update(
            {
                "state": HOOK_SEEN_STATE_REGISTERED,
                "status": HOOK_SEEN_STATE_REGISTERED,
                "diagnostic": "registered_clean_source",
                "next_action": "none",
            }
        )
        return candidate

    if age is not None and age > stale_after_seconds and (
        discoverable_refs is None or thread_ref not in discoverable_refs
    ):
        candidate.update(
            {
                "state": HOOK_SEEN_STATE_STALE_LEDGER_ROW,
                "status": "hook_seen_but_not_registered",
                "diagnostic": "stale_ledger_row_possible_host_or_discovery_failure",
                "next_action": "inspect_provider_discovery_or_prune_stale_hook_seen_row",
            }
        )
        return candidate

    diagnostic = (
        "provider_session_discovered"
        if discoverable_refs is not None and thread_ref in discoverable_refs
        else "host_timing_or_cooldown_pending"
    )
    candidate.update(
        {
            "state": HOOK_SEEN_STATE_PENDING_REPAIR,
            "status": "hook_seen_but_not_registered",
            "diagnostic": diagnostic,
            "next_action": "run_registry_reconcile_hook_seen",
        }
    )
    return candidate


def hook_seen_registry_diagnostic(
    ledger_path: Path | str,
    *,
    registered_thread_keys: Iterable[str],
    discoverable_thread_refs: Iterable[str] | None = None,
    stale_after_seconds: int = DEFAULT_HOOK_SEEN_STALE_AFTER_SECONDS,
    include_private_keys: bool = False,
) -> dict[str, Any]:
    latest = latest_hook_seen_by_ref(ledger_path)
    registered = {
        hook_seen_thread_ref(str(key))
        for key in registered_thread_keys
        if str(key or "").strip()
    }
    discoverable = (
        set(discoverable_thread_refs or [])
        if discoverable_thread_refs is not None
        else None
    )
    states = [
        project_hook_seen_state(
            row,
            registered_refs=registered,
            discoverable_refs=discoverable,
            stale_after_seconds=stale_after_seconds,
            include_private_keys=include_private_keys,
        )
        for _thread_ref, row in sorted(latest.items())
    ]
    state_counts = {
        HOOK_SEEN_STATE_REGISTERED: 0,
        HOOK_SEEN_STATE_PENDING_REPAIR: 0,
        HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED: 0,
        HOOK_SEEN_STATE_STALE_LEDGER_ROW: 0,
    }
    for state in states:
        state_name = str(state.get("state") or "")
        if state_name in state_counts:
            state_counts[state_name] += 1
    actionable_states = {
        HOOK_SEEN_STATE_PENDING_REPAIR,
        HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED,
        HOOK_SEEN_STATE_STALE_LEDGER_ROW,
    }
    candidates = [
        state for state in states if str(state.get("state") or "") in actionable_states
    ][:20]
    missing_count = (
        state_counts[HOOK_SEEN_STATE_PENDING_REPAIR]
        + state_counts[HOOK_SEEN_STATE_STALE_LEDGER_ROW]
    )
    degraded_count = missing_count + state_counts[HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED]
    return {
        "kind": "aippocampus_hook_seen_registry_reconciliation",
        "schema_version": HOOK_SEEN_SCHEMA_VERSION,
        "status": "degraded" if degraded_count else "ok",
        "metrics": {
            "hook_seen_thread_count": len(latest),
            "registered_hook_seen_thread_count": state_counts[HOOK_SEEN_STATE_REGISTERED],
            "hook_seen_but_not_registered_count": missing_count,
            "pending_repair_count": state_counts[HOOK_SEEN_STATE_PENDING_REPAIR],
            "blocked_or_unsupported_count": state_counts[HOOK_SEEN_STATE_BLOCKED_OR_UNSUPPORTED],
            "stale_ledger_row_count": state_counts[HOOK_SEEN_STATE_STALE_LEDGER_ROW],
            "manual_thread_id_investigation_reduced_count": sum(
                1 for item in candidates if item.get("thread_ref")
            ),
            "state_counts": state_counts,
        },
        "candidates": candidates,
        "states": states[:20],
        "repair_command": (
            "python -m aippocampus_runtime.registry.api reconcile-hook-seen "
            "--dry-run --json"
        ),
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_thread_ids_emitted": any("thread_key" in item for item in candidates),
            "local_paths_emitted": False,
            "ledger_is_private_operator_state": True,
        },
    }
