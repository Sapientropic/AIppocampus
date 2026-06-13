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
    "dream_obstruction_recheck",
    "dream_compensatory_probe_accepted",
    "dream_shadow_route_reopen",
    "dream_cut_point_stage_review",
    "avatar_shadowed",
    "decision_shadow_reopen",
    "local_global_obstruction",
    "parallel_derivation_tension",
    "continuity_domain_conflict_recheck",
    "continuity_domain_currentness_recheck",
    "continuity_domain_boundary_constraint",
    "continuity_domain_route_unavailable",
}
ACCEPTED_DREAM_REVIEW_STATES = {
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
}
ACCEPTED_ADJUDICATION_STATUSES = {"accepted", "approved"}


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


def _dream_finding_id(finding: Mapping[str, Any]) -> str:
    for key in ("dream_finding_id", "finding_id", "fingerprint", "id"):
        value = finding.get(key)
        if value:
            return _safe_text(value, 140)
    return _stable_id(finding.get("title"), finding.get("summary"), prefix="dream_finding")


def _dream_finding_adjudicated(finding: Mapping[str, Any]) -> bool:
    review_state = _safe_text(finding.get("review_state"), 80)
    adjudication = finding.get("adjudication_result")
    status = (
        _safe_text(adjudication.get("status"), 80)
        if isinstance(adjudication, Mapping)
        else ""
    )
    return review_state in ACCEPTED_DREAM_REVIEW_STATES or status in ACCEPTED_ADJUDICATION_STATUSES


def _dream_recheck_reason(finding: Mapping[str, Any]) -> str:
    values = " ".join(
        str(value or "")
        for value in (
            finding.get("reason_code"),
            finding.get("candidate_kind"),
            finding.get("dream_function"),
            finding.get("title"),
            finding.get("summary"),
            " ".join(str(item) for item in finding.get("recheck_on") or []),
            " ".join(str(item) for item in finding.get("diagnostics") or []),
            " ".join(str(item) for item in finding.get("downstream_use") or []),
        )
    ).casefold()
    if "shadow" in values or "reopen" in values:
        return "dream_shadow_route_reopen"
    if "cut_point" in values or "stage" in values or "line_topology" in values:
        return "dream_cut_point_stage_review"
    if "obstruction" in values or "blocked" in values or "missing support" in values:
        return "dream_obstruction_recheck"
    if "compensatory" in values:
        return "dream_compensatory_probe_accepted"
    return "dream_macro_recheck"


def runtime_recheck_event_from_dream_finding(
    finding: Mapping[str, Any],
    *,
    source_shape_id: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    finding_id = _dream_finding_id(finding)
    if not _dream_finding_adjudicated(finding):
        return {
            "kind": "runtime_recheck_event_rejection",
            "reason_code": "dream_not_adjudicated_for_macro_recheck",
            "finding_id": finding_id,
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
            "may_mutate_macro_state": False,
        }
    refs = safe_source_refs(finding.get("source_refs"))
    if not refs:
        return {
            "kind": "runtime_recheck_event_rejection",
            "reason_code": "dream_macro_recheck_requires_source_refs",
            "finding_id": finding_id,
            "authority_level": AUTHORITY_LEVEL,
            "claim_permission": CLAIM_PERMISSION,
            "may_mutate_macro_state": False,
        }
    reason = _dream_recheck_reason(finding)
    scope = {
        "kind": "dream_finding",
        "finding_id": finding_id,
        "dream_function": _safe_text(finding.get("dream_function"), 80),
        "candidate_kind": _safe_text(finding.get("candidate_kind"), 80),
        "review_state": _safe_text(finding.get("review_state"), 80),
        "trust_horizon": _safe_text(finding.get("trust_horizon") or finding.get("expires_at"), 120),
        "invalidation_triggers": ", ".join(_safe_text(item, 80) for item in finding.get("invalidation_triggers") or [])[:240],
    }
    event = build_runtime_recheck_event(
        producer="adjudicated_dream_finding",
        reason_code=reason,
        source_refs=refs,
        scope=scope,
        source_shape_id=source_shape_id or f"dream_finding:{finding_id}",
        target_surfaces=("macro_recheck", "source_shape_review", "stage_tracker_review"),
        created_at=created_at,
        degrade_to="macro_review_input",
    )
    event["macro_recheck_policy"] = {
        "may_mutate_macro_state": False,
        "may_update_hexagram": False,
        "may_update_momentum": False,
        "may_update_three_powers": False,
        "may_update_stage_tracker": False,
        "explicit_operator_write_required": True,
    }
    return event


def macro_review_input_from_runtime_recheck_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    if event.get("kind") != RUNTIME_RECHECK_EVENT_KIND:
        return None
    targets = {str(surface) for surface in event.get("target_surfaces") or []}
    if "macro_recheck" not in targets:
        return None
    refs = safe_source_refs(event.get("source_refs"))
    if not refs:
        return None
    reason = _safe_text(event.get("reason_code"), 100)
    payload = {
        "kind": "macro_recheck_review_input",
        "schema_version": RUNTIME_RECHECK_SCHEMA_VERSION,
        "event_id": _safe_text(event.get("event_id"), 140),
        "producer": _safe_text(event.get("producer"), 100),
        "reason_code": reason,
        "source_shape_id": _safe_text(event.get("source_shape_id"), 160),
        "source_refs": refs,
        "review_surfaces": sorted(targets & {"macro_recheck", "source_shape_review", "stage_tracker_review"}),
        "diagnostics": [reason, "runtime_recheck_event", "navigation_only_macro_review_input"],
        "write_effect": "none",
        "fact_claim_allowed": False,
        "foreground_eligible": False,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "source_reopen_required_before_claim": True,
    }
    redacted = redact_sensitive_values(redact_private_paths(payload))
    return redacted if isinstance(redacted, dict) else payload
