#!/usr/bin/env python3
"""Progressive activation state for fresh-thread recall.

This is a short-lived overlay for one thread/topic epoch. It is not formal
memory and not evidence. It records only privacy-safe fingerprints plus the
minimal state needed to avoid repeating a weak fresh-thread scent after the
conversation has ignored, rejected, or moved past it.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from aippocampus_runtime.core import compact_text, workspace_fingerprint

ACTIVATION_SCHEMA_VERSION = 1
DEFAULT_ACTIVATION_TTL_SECONDS = 2 * 60 * 60
CONFIRMED_ACTIVATION_TTL_SECONDS = 6 * 60 * 60
MAX_EVENT_COUNT = 99
MAX_ROUTE_REFS = 8

PENDING = "pending"
SCENT_EMITTED = "scent_emitted"
SOFT_HYPOTHESIS = "soft_hypothesis"
IGNORED = "ignored"
CONFIRMED = "confirmed"
REJECTED = "rejected"
SOURCE_BACKED = "source_backed"
RETIRED = "retired"
SUPPRESSED = "suppressed"

ACTIVATION_STATES = {
    PENDING,
    SCENT_EMITTED,
    SOFT_HYPOTHESIS,
    IGNORED,
    CONFIRMED,
    REJECTED,
    SOURCE_BACKED,
    RETIRED,
    SUPPRESSED,
}

EVENT_TO_STATE = {
    "scent_emitted": SCENT_EMITTED,
    "soft_hypothesis_shown": SOFT_HYPOTHESIS,
    "user_ignored": IGNORED,
    "user_confirmed": CONFIRMED,
    "user_rejected": REJECTED,
    "source_reopened": SOURCE_BACKED,
    "topic_shift_retired": RETIRED,
    "suppressed": SUPPRESSED,
    "expired": RETIRED,
}

_LOCK_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
_LOCK_STATES = {"ready", "pending", "expired", "failed"}


def _fingerprint(value: str, *, prefix: str) -> str:
    return prefix + "_" + hashlib.sha1(str(value or "").casefold().encode("utf-8")).hexdigest()[:16]


def _safe_unix(value: float | int | None) -> float:
    if value is None:
        return datetime.now(timezone.utc).timestamp()
    return float(value)


def _iso_from_unix(value: float) -> str:
    return (
        datetime.fromtimestamp(value, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _clean_lock_id(value: Any) -> str:
    text = str(value or "").strip()
    if _LOCK_ID_RE.fullmatch(text):
        return text
    return ""


def _lock_payload(active_recall_lock: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(active_recall_lock, dict):
        return {"state": "missing", "lock_id": ""}
    state = str(active_recall_lock.get("state") or active_recall_lock.get("lock_state") or "").strip()
    if state not in _LOCK_STATES:
        state = "missing"
    lock_id = _clean_lock_id(active_recall_lock.get("lock_id")) if state in {"ready", "pending"} else ""
    return {"state": state, "lock_id": lock_id}


def _registry_freshness_fingerprint(registry_fingerprint: Any) -> str:
    if isinstance(registry_fingerprint, dict):
        raw = json.dumps(registry_fingerprint, ensure_ascii=False, sort_keys=True)
    else:
        raw = compact_text(str(registry_fingerprint or ""), 240)
    return _fingerprint(raw, prefix="reg")


def _candidate_ref_key(ref: dict[str, Any]) -> str:
    parts = []
    for key in (
        "source_id",
        "stable_source_id",
        "thread_key",
        "message_id",
        "turn_id",
        "turn_index",
        "line",
        "source_line",
        "phase",
    ):
        value = ref.get(key)
        if value in {None, ""}:
            continue
        parts.append(f"{key}={value}")
    return "\n".join(parts)


def _route_fingerprint(packet: dict[str, Any] | None) -> str:
    if not isinstance(packet, dict):
        return _fingerprint("missing", prefix="far")
    refs = [ref for ref in packet.get("candidate_refs") or [] if isinstance(ref, dict)]
    ref_keys = [_candidate_ref_key(ref) for ref in refs[:MAX_ROUTE_REFS]]
    ref_keys = [key for key in ref_keys if key]
    if ref_keys:
        return _fingerprint("\n---\n".join(sorted(ref_keys)), prefix="far")
    support = str(packet.get("support_level") or "")
    route_reason = str(packet.get("route_reason") or "")
    return _fingerprint(f"{support}\n{route_reason}", prefix="far")


def _support_level(packet: dict[str, Any] | None) -> str:
    if not isinstance(packet, dict):
        return "unknown"
    return compact_text(str(packet.get("support_level") or "unknown"), 80)


def _next_state(event: str) -> str:
    return EVENT_TO_STATE.get(str(event or ""), PENDING)


def _ttl_for_state(state: str, ttl_seconds: int) -> int:
    if state in {CONFIRMED, SOURCE_BACKED, REJECTED, SUPPRESSED}:
        return max(ttl_seconds, CONFIRMED_ACTIVATION_TTL_SECONDS)
    if state == RETIRED:
        return 0
    return max(0, ttl_seconds)


def advance_fresh_thread_activation(
    prior_state: dict[str, Any] | None,
    *,
    event: str,
    packet: dict[str, Any] | None,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    registry_fingerprint: Any,
    active_recall_lock: dict[str, Any] | None = None,
    now_unix: float | int | None = None,
    ttl_seconds: int = DEFAULT_ACTIVATION_TTL_SECONDS,
) -> dict[str, Any]:
    """Return a compact activation snapshot after one fresh-thread event."""

    now_value = _safe_unix(now_unix)
    next_state = _next_state(event)
    prior = prior_state if isinstance(prior_state, dict) else {}
    surface_count = int(prior.get("surface_count") or 0)
    ignore_count = int(prior.get("ignore_count") or 0)
    if event in {"scent_emitted", "soft_hypothesis_shown"}:
        surface_count += 1
    if event == "user_ignored":
        ignore_count += 1
    event_count = min(MAX_EVENT_COUNT, int(prior.get("event_count") or 0) + 1)
    created_unix = float(prior.get("created_unix") or now_value)
    effective_ttl = _ttl_for_state(next_state, ttl_seconds)
    expires_at_unix = now_value + effective_ttl if effective_ttl > 0 else now_value
    registry_fp = _registry_freshness_fingerprint(registry_fingerprint)

    return {
        "kind": "aippocampus_fresh_thread_activation_state",
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "activation_id": _fingerprint(
            "\n".join(
                [
                    str(thread_id or ""),
                    workspace_fingerprint(workspace),
                    str(topic_epoch or ""),
                    _route_fingerprint(packet),
                ]
            ),
            prefix="fta",
        ),
        "state": next_state,
        "thread_fingerprint": _fingerprint(thread_id, prefix="thread"),
        "workspace_fingerprint": workspace_fingerprint(workspace),
        "topic_epoch": compact_text(str(topic_epoch or ""), 120),
        "route_fingerprint": _route_fingerprint(packet),
        "support_level": _support_level(packet),
        "source_reopen_required": True,
        "active_recall_lock": _lock_payload(active_recall_lock),
        "surface_count": surface_count,
        "ignore_count": ignore_count,
        "event_count": event_count,
        "last_event": compact_text(str(event or ""), 80),
        "registry_freshness_fingerprint": registry_fp,
        "created_unix": created_unix,
        "updated_unix": now_value,
        "expires_at_unix": expires_at_unix,
        "created_at": _iso_from_unix(created_unix),
        "updated_at": _iso_from_unix(now_value),
        "expires_at": _iso_from_unix(expires_at_unix),
        "privacy_boundary": {
            "stores_raw_prompt": False,
            "stores_raw_source": False,
            "stores_workspace_path": False,
            "state_is_not_formal_memory": True,
            "source_reopen_required_for_claims": True,
        },
    }


def _invalid_context(state: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "activation_state": str(state.get("state") or ""),
        "activation_update": "retired",
        "activation_invalidation": reason,
        "route_suppressed_by_activation": True,
        "activation_source_reopened": False,
    }


def fresh_thread_activation_context(
    state: dict[str, Any] | None,
    *,
    topic_epoch: str,
    registry_fingerprint: Any,
    now_unix: float | int | None = None,
    user_anchor: bool = False,
) -> dict[str, Any]:
    """Project an activation snapshot into `fresh_thread_action_from_packet` context."""

    if not isinstance(state, dict):
        return {"activation_state": "", "activation_update": "none"}
    now_value = _safe_unix(now_unix)
    state_name = str(state.get("state") or "")
    if state.get("topic_epoch") != topic_epoch:
        return _invalid_context(state, "topic_epoch_changed")
    if state.get("registry_freshness_fingerprint") != _registry_freshness_fingerprint(
        registry_fingerprint
    ):
        return _invalid_context(state, "registry_freshness_changed")
    if now_value > float(state.get("expires_at_unix") or 0.0):
        return _invalid_context(state, "expired")
    base = {
        "activation_state": state_name,
        "activation_update": "none",
        "activation_invalidation": "",
        "route_suppressed_by_activation": False,
        "prior_scent_without_new_anchor": False,
        "user_confirmed_memory_theme": False,
        "activation_source_reopened": False,
    }
    if state_name == CONFIRMED:
        return {**base, "activation_update": "confirmed", "user_confirmed_memory_theme": True}
    if state_name in {REJECTED, SUPPRESSED}:
        return {
            **base,
            "activation_update": "rejected",
            "route_suppressed_by_activation": True,
        }
    if state_name == RETIRED:
        return {
            **base,
            "activation_update": "retired",
            "route_suppressed_by_activation": True,
        }
    if state_name == SOURCE_BACKED:
        return {
            **base,
            "activation_update": "confirmed",
            "activation_source_reopened": True,
        }
    if state_name in {SCENT_EMITTED, SOFT_HYPOTHESIS, IGNORED} and not user_anchor:
        return {
            **base,
            "activation_update": "tentative",
            "prior_scent_without_new_anchor": True,
        }
    return base
