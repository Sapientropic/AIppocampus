#!/usr/bin/env python3
"""Shared navigation-only runtime recheck event contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

RUNTIME_RECHECK_EVENT_KIND = "runtime_recheck_event"
RUNTIME_RECHECK_SCHEMA_VERSION = 1
AUTHORITY_LEVEL = "direction_only"
CLAIM_PERMISSION = "none"
DEFAULT_DEGRADE_TO = "navigation_diagnostic"
TARGET_SURFACE_ALIASES = {
    "active_recall": "active_recall_priority",
    "dream": "dream_seed",
    "macro": "macro_recheck",
}
KNOWN_REASON_CODES = {
    "semantic_invalidation",
    "dream_macro_recheck",
    "avatar_shadowed",
    "decision_shadow_reopen",
    "local_global_obstruction",
    "parallel_derivation_tension",
    "continuity_domain_conflict_recheck",
    "continuity_domain_currentness_recheck",
    "continuity_domain_boundary_constraint",
    "continuity_domain_route_unavailable",
}


def _stable_id(*parts: Any, prefix: str, length: int = 20) -> str:
    raw = "\0".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _safe_text(value: Any, limit: int = 120) -> str:
    return compact_text(str(value or ""), limit)


def _safe_scope(scope: Mapping[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(scope, Mapping):
        payload = {
            _safe_text(key, 80): _safe_text(value, 180)
            for key, value in scope.items()
            if _safe_text(key, 80) and _safe_text(value, 180)
        }
    else:
        payload = {"kind": _safe_text(scope or "runtime", 80)}
    redacted = redact_sensitive_values(redact_private_paths(payload))
    return redacted if isinstance(redacted, dict) else payload


def _target_surfaces(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    surfaces: list[str] = []
    for value in values:
        surface = TARGET_SURFACE_ALIASES.get(str(value or "").strip(), str(value or "").strip())
        if not surface or surface in seen:
            continue
        seen.add(surface)
        surfaces.append(surface[:80])
    return surfaces or ["subconscious_review"]


def build_runtime_recheck_event(
    *,
    producer: str,
    reason_code: str,
    source_refs: Any,
    scope: Mapping[str, Any] | str | None,
    target_surfaces: Iterable[str],
    source_shape_id: str = "",
    created_at: str | None = None,
    degrade_to: str = DEFAULT_DEGRADE_TO,
    event_id: str | None = None,
) -> dict[str, Any]:
    refs = safe_source_refs(source_refs)
    if not refs:
        raise ValueError("runtime_recheck_event requires source refs")
    safe_reason = _safe_text(reason_code, 100)
    if safe_reason not in KNOWN_REASON_CODES:
        safe_reason = _safe_text(safe_reason, 80) or "runtime_recheck"
    safe_scope = _safe_scope(scope)
    safe_shape = _safe_text(source_shape_id, 160)
    surfaces = _target_surfaces(target_surfaces)
    dedupe_key = _stable_id(safe_reason, safe_shape, safe_scope, refs, prefix="rre_dedupe")
    payload = {
        "kind": RUNTIME_RECHECK_EVENT_KIND,
        "schema_version": RUNTIME_RECHECK_SCHEMA_VERSION,
        "event_id": event_id or _stable_id(producer, dedupe_key, prefix="rre"),
        "dedupe_key": dedupe_key,
        "producer": _safe_text(producer, 100),
        "reason_code": safe_reason,
        "reason_family": safe_reason.split("_", 1)[0],
        "source_refs": refs,
        "source_shape_id": safe_shape,
        "scope": safe_scope,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "degrade_to": _safe_text(degrade_to, 80) or DEFAULT_DEGRADE_TO,
        "target_surfaces": surfaces,
        "created_at": created_at or now_utc(),
        "consumer_policy": {
            "may_route_recheck": True,
            "may_seed_backstage_candidate": True,
            "may_mutate_source_truth": False,
            "may_raise_authority": False,
            "may_emit_foreground_fact": False,
            "requires_source_reopen_before_claim": True,
        },
    }
    redacted = redact_sensitive_values(redact_private_paths(payload))
    return redacted if isinstance(redacted, dict) else payload


def _domain_refs(domain: Mapping[str, Any], *groups: str) -> list[dict[str, Any]]:
    trail = domain.get("evidence_trail")
    evidence: Mapping[str, Any] = trail if isinstance(trail, Mapping) else {}
    refs: list[dict[str, Any]] = []
    for group in groups:
        refs.extend(safe_source_refs(evidence.get(group)))
    if not refs:
        refs.extend(safe_source_refs(evidence.get("representative_refs") or evidence.get("support_refs")))
    return refs


def runtime_recheck_events_from_continuity_domains_snapshot(
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw_domain in snapshot.get("domains") or []:
        if not isinstance(raw_domain, Mapping):
            continue
        domain_id = _safe_text(raw_domain.get("domain_id"), 120)
        if not domain_id:
            continue
        lifecycle = raw_domain.get("lifecycle")
        lifecycle_map: Mapping[str, Any] = lifecycle if isinstance(lifecycle, Mapping) else {}
        status = _safe_text(lifecycle_map.get("status") or "active", 80)
        scope = {"kind": "continuity_domain", "domain_id": domain_id, "lifecycle_status": status}
        shape_id = f"continuity_domain:{domain_id}"
        evidence = raw_domain.get("evidence_trail")
        trail: Mapping[str, Any] = evidence if isinstance(evidence, Mapping) else {}

        if status in {"superseded", "stale"}:
            events.append(
                build_runtime_recheck_event(
                    producer="continuity_domain_lifecycle",
                    reason_code="continuity_domain_currentness_recheck",
                    source_refs=_domain_refs(raw_domain, "representative_refs", "support_refs"),
                    scope=scope,
                    source_shape_id=shape_id,
                    target_surfaces=("macro_recheck", "dream_seed", "active_recall_priority"),
                )
            )
        if status in {"blocked", "retired"}:
            events.append(
                build_runtime_recheck_event(
                    producer="continuity_domain_lifecycle",
                    reason_code="continuity_domain_route_unavailable",
                    source_refs=_domain_refs(raw_domain, "boundary_refs", "representative_refs", "support_refs"),
                    scope=scope,
                    source_shape_id=shape_id,
                    target_surfaces=("macro_recheck", "active_recall_priority"),
                    degrade_to="ignore_or_blocked_diagnostic",
                )
            )
        if trail.get("counter_refs") or trail.get("correction_refs") or status == "contested":
            events.append(
                build_runtime_recheck_event(
                    producer="continuity_domain_evidence_trail",
                    reason_code="continuity_domain_conflict_recheck",
                    source_refs=_domain_refs(raw_domain, "counter_refs", "correction_refs"),
                    scope=scope,
                    source_shape_id=shape_id,
                    target_surfaces=("macro_recheck", "dream_seed", "active_recall_priority"),
                )
            )
        if raw_domain.get("pinned_boundary_conditions") or trail.get("boundary_refs"):
            events.append(
                build_runtime_recheck_event(
                    producer="continuity_domain_evidence_trail",
                    reason_code="continuity_domain_boundary_constraint",
                    source_refs=_domain_refs(raw_domain, "boundary_refs", "representative_refs"),
                    scope=scope,
                    source_shape_id=shape_id,
                    target_surfaces=("macro_recheck", "dream_seed", "active_recall_priority"),
                    degrade_to="restriction_diagnostic",
                )
            )
    return events
