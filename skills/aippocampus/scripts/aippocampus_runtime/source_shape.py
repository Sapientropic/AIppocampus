#!/usr/bin/env python3
"""Shared source-shape descriptor spine and projection guards.

This module is deliberately an orchestrator, not a new recall system. It gives
existing producers one small place to normalize source-shape diagnostics before
active recall, Dream, Macro, avatar, or foreground surfaces see them.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, stable_json_join_id
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.runtime_recheck_events import RUNTIME_RECHECK_EVENT_KIND
from aippocampus_runtime.source.io_kernel import parse_jsonl_dict_rows_text

SOURCE_SHAPE_DESCRIPTOR_KIND = "source_shape_descriptor"
SOURCE_SHAPE_SCHEMA_VERSION = 1
AUTHORITY_LEVEL = "direction_only"
CLAIM_PERMISSION = "none"

DESCRIPTOR_STATES = {"complete", "incomplete", "diagnostic_only"}
GUARD_ORDER = (
    "privacy_boundary",
    "source_availability",
    "freshness_invalidation",
    "authority_claim_permission",
    "local_global_compatibility",
    "parallel_derivation_compatibility",
    "projection_permission",
)
BLOCKING_SEVERITIES = {"block", "degrade"}
SAFE_SOURCE_SNAPSHOT_KEYS = (
    "snapshot_id",
    "source_ids",
    "source_epoch",
    "topic_epoch",
    "section_ids",
    "coverage_scope",
)
TEMPORAL_FIELDS = (
    "source_coverage_time",
    "source_event_time",
    "materialized_at",
    "built_at",
    "valid_after",
    "valid_until",
    "review_after",
    "topic_epoch",
    "source_epoch",
    "invalidation_epoch",
    "invalidation_reasons",
    "recheck_on",
    "section_time_window",
)
RUNTIME_TERM_GLOSSARY = {
    "source_shape_descriptor": "The normalized, navigation-only runtime descriptor owned by this module.",
    "source_snapshot": "Safe ids, epochs, and coverage handles for the source basis; not raw source text.",
    "derivation_dag": "Producer-owned derivation structure summarized only as presence/count metadata here.",
    "compatibility_diagnostic": "Inspectable guard result that may block or degrade projection.",
    "invalidation_reason": "Freshness/currentness signal that asks for source reopen or recheck.",
    "projection_allowed": "Whether a consumer may project compact route guidance after all guards.",
    "degrade_to": "The lower-authority surface a blocked or suspect descriptor falls back to.",
    "runtime_recheck_event": "A direction-only event that asks consumers to reopen or recheck source.",
}


def _text(value: Any, limit: int = 120) -> str:
    return compact_text(str(value or ""), limit)


def _code(value: Any, *, fallback: str = "", limit: int = 80) -> str:
    text = _text(value, limit).casefold().replace(" ", "_").replace("-", "_")
    safe = "".join(ch for ch in text if ch.isalnum() or ch == "_").strip("_")
    return safe or fallback


def _codes(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        raw_items: Iterable[Any] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        raw_items = value
    else:
        raw_items = []
    result: list[str] = []
    for item in raw_items:
        code = _code(item)
        if code and code not in result:
            result.append(code)
        if len(result) >= limit:
            break
    return result


def _redact_public(value: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(value))


def _safe_mapping(value: Mapping[str, Any] | None, *, allowed: Sequence[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    payload: dict[str, Any] = {}
    for key in allowed:
        item = value.get(key)
        if item in (None, "", [], {}):
            continue
        payload[key] = item if isinstance(item, (list, tuple, dict)) else _text(item, 180)
    redacted = _redact_public(payload)
    return redacted if isinstance(redacted, dict) else payload


def _safe_temporal_semantics(value: Mapping[str, Any] | None, *, built_at: str) -> dict[str, Any]:
    temporal = _safe_mapping(value, allowed=TEMPORAL_FIELDS)
    if "source_coverage_time" not in temporal and temporal.get("section_time_window"):
        temporal["source_coverage_time"] = {
            "mapped_from": "section_time_window",
            "window": temporal["section_time_window"],
        }
    if not temporal.get("built_at"):
        temporal["built_at"] = built_at
    omitted = [field for field in TEMPORAL_FIELDS if field not in temporal]
    temporal["omitted_fields"] = omitted
    # Section-local windows remain producer-owned; source shape only records
    # their normalized presence so callers do not invent a second time model.
    temporal["section_time_window_maps_to"] = "source_coverage_time"
    return temporal


def _diagnostic(
    guard: str,
    reason_code: str,
    *,
    severity: str,
    degrade_to: str,
    detail: str = "",
) -> dict[str, Any]:
    return {
        "guard": guard,
        "reason_code": reason_code,
        "severity": severity,
        "degrade_to": degrade_to,
        "detail": _text(detail, 180),
    }


def _compatibility_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [row for row in value if isinstance(row, Mapping)]
    return []


def _derivation_summary(value: Any) -> dict[str, Any]:
    if not value:
        return {"present": False, "node_count": 0, "edge_count": 0}
    if isinstance(value, Mapping):
        nodes = value.get("nodes")
        edges = value.get("edges")
        node_count = len(nodes) if isinstance(nodes, Sequence) and not isinstance(nodes, (str, bytes)) else 0
        edge_count = len(edges) if isinstance(edges, Sequence) and not isinstance(edges, (str, bytes)) else 0
        return {
            "present": True,
            "node_count": node_count,
            "edge_count": edge_count,
            "producer": _text(value.get("producer"), 80),
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {"present": True, "node_count": len(value), "edge_count": 0}
    return {"present": True, "node_count": 1, "edge_count": 0}


def _safe_signals(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed_status_keys = ("status", "posture", "reason_code", "recheck_on", "adjudication")
    signals: dict[str, Any] = {}
    for surface in ("dream", "avatar", "macro", "compatibility", "familiarity"):
        raw = value.get(surface)
        if isinstance(raw, Mapping):
            compact = {
                key: _text(raw.get(key), 120)
                for key in allowed_status_keys
                if raw.get(key) not in (None, "", [], {})
            }
            if compact:
                signals[surface] = compact
    redacted = _redact_public(signals)
    return redacted if isinstance(redacted, dict) else signals


def _collect_guard_diagnostics(
    *,
    refs: list[dict[str, Any]],
    temporal: Mapping[str, Any],
    guard_inputs: Mapping[str, Any],
    compatibility_diagnostics: Any,
    derivation_summary: Mapping[str, Any],
    projection_intent: str,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []

    privacy_state = _code(
        guard_inputs.get("privacy_state")
        or guard_inputs.get("privacy")
        or ("blocked" if guard_inputs.get("privacy_blocked") else "allowed"),
        fallback="allowed",
    )
    if privacy_state in {"blocked", "private", "sensitive", "partition_blocked"}:
        diagnostics.append(
            _diagnostic(
                "privacy_boundary",
                f"privacy_{privacy_state}",
                severity="block",
                degrade_to="ignore_or_blocked",
            )
        )

    if not refs:
        diagnostics.append(
            _diagnostic(
                "source_availability",
                "missing_source_refs",
                severity="block",
                degrade_to="ignore_or_blocked",
            )
        )

    freshness = _code(
        guard_inputs.get("freshness")
        or guard_inputs.get("currentness")
        or guard_inputs.get("freshness_state"),
        fallback="current",
    )
    invalidation_reasons = _codes(temporal.get("invalidation_reasons") or guard_inputs.get("invalidation_reasons"))
    source_epoch = _text(temporal.get("source_epoch") or guard_inputs.get("source_epoch"), 120)
    invalidation_epoch = _text(temporal.get("invalidation_epoch") or guard_inputs.get("invalidation_epoch"), 120)
    if freshness in {"stale", "superseded", "invalidated", "conflicted", "unknown"} or invalidation_reasons:
        diagnostics.append(
            _diagnostic(
                "freshness_invalidation",
                invalidation_reasons[0] if invalidation_reasons else f"freshness_{freshness}",
                severity="degrade",
                degrade_to="recheck_required",
            )
        )
    elif invalidation_epoch and source_epoch and invalidation_epoch != source_epoch:
        diagnostics.append(
            _diagnostic(
                "freshness_invalidation",
                "source_epoch_mismatch",
                severity="degrade",
                degrade_to="recheck_required",
            )
        )
    if "source_coverage_time" not in temporal:
        diagnostics.append(
            _diagnostic(
                "freshness_invalidation",
                "missing_source_coverage_time",
                severity="degrade",
                degrade_to="reopenable_route",
            )
        )

    requested_claim = _code(guard_inputs.get("claim_permission"), fallback=CLAIM_PERMISSION)
    requested_authority = _code(guard_inputs.get("authority_level"), fallback=AUTHORITY_LEVEL)
    if requested_claim not in {CLAIM_PERMISSION, "no_claim", "no_claim_before_reopen"}:
        diagnostics.append(
            _diagnostic(
                "authority_claim_permission",
                "claim_permission_downgraded",
                severity="degrade",
                degrade_to="direction_only",
            )
        )
    if requested_authority not in {AUTHORITY_LEVEL, "navigation_only", "direction_with_ref"}:
        diagnostics.append(
            _diagnostic(
                "authority_claim_permission",
                "authority_downgraded",
                severity="degrade",
                degrade_to="direction_only",
            )
        )

    for row in _compatibility_rows(compatibility_diagnostics):
        result = _code(row.get("result") or row.get("status"), fallback="unknown")
        if result in {"obstruction", "blocked", "incompatible", "failed"}:
            diagnostics.append(
                _diagnostic(
                    "local_global_compatibility",
                    _codes(row.get("reason_codes"), limit=1)[0]
                    if _codes(row.get("reason_codes"), limit=1)
                    else "local_global_obstruction",
                    severity="degrade",
                    degrade_to="compatibility_diagnostic",
                )
            )
            break

    parallel_status = _code(
        guard_inputs.get("parallel_compatibility")
        or guard_inputs.get("source_shape_completeness")
        or ("complete" if derivation_summary.get("present") else "missing"),
        fallback="missing",
    )
    if parallel_status not in {"complete", "compatible", "ok", "ready"}:
        diagnostics.append(
            _diagnostic(
                "parallel_derivation_compatibility",
                "parallel_derivation_incomplete",
                severity="warn" if refs else "degrade",
                degrade_to="diagnostic_only",
            )
        )

    projection_policy = guard_inputs.get("projection_allowed")
    if projection_policy is False or projection_intent in {"debug_only", "diagnostic_only"}:
        diagnostics.append(
            _diagnostic(
                "projection_permission",
                "projection_policy_denied",
                severity="degrade",
                degrade_to="diagnostic_only",
            )
        )

    return diagnostics


def _dominant_guard(diagnostics: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    by_order = {name: index for index, name in enumerate(GUARD_ORDER)}
    blocking: list[Mapping[str, Any]] = [
        row
        for row in diagnostics
        if str(row.get("severity") or "") in BLOCKING_SEVERITIES
    ]
    if not blocking:
        return None

    best: Mapping[str, Any] | None = None
    best_index = len(GUARD_ORDER)
    for row in blocking:
        index = by_order.get(str(row.get("guard") or ""), len(GUARD_ORDER))
        if best is None or index < best_index:
            best = row
            best_index = index
    return dict(best or {})


def _descriptor_state(
    diagnostics: Sequence[Mapping[str, Any]],
    *,
    derivation_summary: Mapping[str, Any],
) -> str:
    dominant = _dominant_guard(diagnostics)
    if dominant and dominant.get("severity") == "block":
        return "diagnostic_only"
    if dominant:
        return "incomplete"
    if not derivation_summary.get("present"):
        return "incomplete"
    return "complete"


def build_source_shape_descriptor(
    *,
    producer: str,
    source_refs: Any,
    source_snapshot: Mapping[str, Any] | None = None,
    derivation_dag: Any = None,
    compatibility_diagnostics: Any = None,
    temporal: Mapping[str, Any] | None = None,
    guard_inputs: Mapping[str, Any] | None = None,
    signals: Mapping[str, Any] | None = None,
    projection_intent: str = "foreground_recall",
    target_surfaces: Iterable[str] = ("active_recall_priority",),
    source_shape_id: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a guarded source-shape descriptor from producer-owned inputs."""

    built_at = created_at or now_utc()
    refs = safe_source_refs(source_refs)
    safe_snapshot = _safe_mapping(source_snapshot, allowed=SAFE_SOURCE_SNAPSHOT_KEYS)
    safe_temporal = _safe_temporal_semantics(temporal, built_at=built_at)
    safe_guard_inputs = guard_inputs if isinstance(guard_inputs, Mapping) else {}
    derivation_summary = _derivation_summary(derivation_dag)
    diagnostics = _collect_guard_diagnostics(
        refs=refs,
        temporal=safe_temporal,
        guard_inputs=safe_guard_inputs,
        compatibility_diagnostics=compatibility_diagnostics,
        derivation_summary=derivation_summary,
        projection_intent=projection_intent,
    )
    state = _descriptor_state(diagnostics, derivation_summary=derivation_summary)
    dominant = _dominant_guard(diagnostics)
    safe_shape_id = _text(source_shape_id, 160) or stable_json_join_id(
        "source_shape",
        producer,
        refs,
        safe_snapshot,
        derivation_summary,
        sep="\0",
        length=20,
    )
    degrade_to = str(dominant.get("degrade_to")) if dominant else "reopenable_route"
    projection_allowed = state == "complete" and dominant is None
    payload = {
        "kind": SOURCE_SHAPE_DESCRIPTOR_KIND,
        "schema_version": SOURCE_SHAPE_SCHEMA_VERSION,
        "source_shape_id": safe_shape_id,
        "descriptor_state": state,
        "producer": _text(producer, 100),
        "created_at": built_at,
        "source_snapshot": safe_snapshot,
        "source_refs": refs,
        "source_ref_count": len(refs),
        "temporal_semantics": safe_temporal,
        "derivation_summary": derivation_summary,
        "compatibility_diagnostics_present": bool(_compatibility_rows(compatibility_diagnostics)),
        "guard_order": list(GUARD_ORDER),
        "dominant_guard": dict(dominant) if dominant else None,
        "guard_diagnostics": diagnostics,
        "signals": _safe_signals(signals),
        "projection": {
            "intent": _code(projection_intent, fallback="foreground_recall"),
            "projection_allowed": projection_allowed,
            "foreground_projection": "compact_route_posture_only",
            "explain_deepen_can_recover_diagnostics": True,
            "target_surfaces": [_text(surface, 80) for surface in target_surfaces if _text(surface, 80)],
        },
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "degrade_to": degrade_to,
        "source_reopen_required_before_claim": True,
        "consumer_policy": {
            "may_route_recheck": True,
            "may_raise_authority": False,
            "may_emit_foreground_fact": False,
            "requires_source_reopen_before_claim": True,
        },
    }
    redacted = _redact_public(payload)
    return redacted if isinstance(redacted, dict) else payload


def _risk_flags_from_reason(reason: str) -> list[str]:
    flags = ["source_shape_recheck_required", "source_reopen_required"]
    if "currentness" in reason or "freshness" in reason or "stale" in reason or "epoch" in reason:
        flags.append("check_currentness")
    if "conflict" in reason or "counter" in reason or "correction" in reason:
        flags.append("conflict_requires_deepen")
    if "boundary" in reason or "privacy" in reason or "blocked" in reason:
        flags.append("boundary_requires_review")
    if "obstruction" in reason or "compatibility" in reason:
        flags.append("compatibility_obstruction")
    return _codes(flags, limit=6)


def _reason_codes_from_descriptor(descriptor: Mapping[str, Any]) -> list[str]:
    diagnostics = descriptor.get("guard_diagnostics")
    codes: list[str] = []
    if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray)):
        for row in diagnostics:
            if not isinstance(row, Mapping):
                continue
            code = _code(row.get("reason_code"))
            if code and code not in codes:
                codes.append(code)
            if len(codes) >= 4:
                break
    if not codes:
        codes.append("source_shape_descriptor")
    return codes[:4]


def project_source_shape_for_foreground(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Return the tiny foreground-safe projection for one descriptor."""

    state = _code(descriptor.get("descriptor_state"), fallback="diagnostic_only")
    raw_dominant = descriptor.get("dominant_guard")
    dominant: Mapping[str, Any] = raw_dominant if isinstance(raw_dominant, Mapping) else {}
    dominant_reason = _code(dominant.get("reason_code"), fallback=state)
    source_ref_count = int(descriptor.get("source_ref_count") or 0)
    active = state == "complete" and bool((descriptor.get("projection") or {}).get("projection_allowed"))
    if active:
        route_posture = "active"
        action_grammar = "reopenable_route"
    elif source_ref_count and dominant_reason not in {"privacy_blocked", "privacy_private", "privacy_sensitive"}:
        route_posture = "shadowed"
        action_grammar = "direction_with_ref"
    else:
        route_posture = "blocked"
        action_grammar = "ignore_or_blocked"
    payload = {
        "kind": "source_shape_foreground_projection",
        "source_shape_id": _text(descriptor.get("source_shape_id"), 160),
        "route_posture": route_posture,
        "action_grammar": action_grammar,
        "projection_allowed": active,
        "source_ref_count": source_ref_count,
        "source_reopen_required_before_claim": True,
        "recommended_next": "reopen_source" if source_ref_count else "search_clean_source",
        "risk_flags": _risk_flags_from_reason(dominant_reason),
        "triage_rank_reason_codes": _reason_codes_from_descriptor(descriptor)[:2],
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "degrade_to": _text(descriptor.get("degrade_to"), 80),
        "foreground_omits_diagnostic_internals": True,
    }
    redacted = _redact_public(payload)
    return redacted if isinstance(redacted, dict) else payload


def explain_source_shape_descriptor(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Return public-safe explain/deepen details omitted from foreground."""

    payload = {
        "kind": "source_shape_explain_diagnostics",
        "source_shape_id": _text(descriptor.get("source_shape_id"), 160),
        "descriptor_state": _text(descriptor.get("descriptor_state"), 80),
        "guard_order": list(descriptor.get("guard_order") or GUARD_ORDER),
        "dominant_guard": descriptor.get("dominant_guard"),
        "guard_diagnostics": descriptor.get("guard_diagnostics") or [],
        "temporal_semantics": descriptor.get("temporal_semantics") or {},
        "derivation_summary": descriptor.get("derivation_summary") or {},
        "source_refs": safe_source_refs(descriptor.get("source_refs")),
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "source_reopen_required_before_claim": True,
    }
    redacted = _redact_public(payload)
    return redacted if isinstance(redacted, dict) else payload


def _priority_from_runtime_recheck_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    targets = {str(surface) for surface in event.get("target_surfaces") or []}
    if targets and "active_recall_priority" not in targets:
        return None
    refs = safe_source_refs(event.get("source_refs"))
    if not refs:
        return None
    reason = _code(event.get("reason_code"), fallback="runtime_recheck")
    return {
        "kind": "source_shape_active_recall_priority",
        "source_shape_id": _text(event.get("source_shape_id"), 160),
        "priority_class": "reopen_first",
        "producer": _text(event.get("producer"), 100),
        "source_refs": refs,
        "source_reopen_required_before_claim": True,
        "risk_flags": _risk_flags_from_reason(reason),
        "triage_rank_reason_codes": [reason, "runtime_recheck_event"][:4],
        "recheck_on": [reason],
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
    }


def _priority_from_descriptor(descriptor: Mapping[str, Any]) -> dict[str, Any] | None:
    refs = safe_source_refs(descriptor.get("source_refs"))
    if not refs:
        return None
    projection = project_source_shape_for_foreground(descriptor)
    reason_codes = _reason_codes_from_descriptor(descriptor)
    priority_class = "reopen_first" if projection["route_posture"] != "blocked" else "hold_back"
    return {
        "kind": "source_shape_active_recall_priority",
        "source_shape_id": _text(descriptor.get("source_shape_id"), 160),
        "priority_class": priority_class,
        "producer": _text(descriptor.get("producer"), 100),
        "source_refs": refs,
        "source_reopen_required_before_claim": True,
        "risk_flags": projection["risk_flags"],
        "triage_rank_reason_codes": [*reason_codes[:3], "source_shape_descriptor"][:4],
        "recheck_on": reason_codes[:4],
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
    }


def source_shape_active_recall_priorities(
    diagnostics: Iterable[Mapping[str, Any]] | None,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Normalize source-shape/recheck inputs into active-recall priorities."""

    priorities: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in diagnostics or []:
        if not isinstance(row, Mapping):
            continue
        kind = str(row.get("kind") or "")
        priority = (
            _priority_from_runtime_recheck_event(row)
            if kind == RUNTIME_RECHECK_EVENT_KIND
            else _priority_from_descriptor(row)
            if kind == SOURCE_SHAPE_DESCRIPTOR_KIND
            else None
        )
        if not priority:
            continue
        marker = tuple(
            sorted((key, str(value)) for key, value in priority.items() if key in {"source_shape_id", "recheck_on"})
        )
        if marker in seen:
            continue
        seen.add(marker)
        redacted = _redact_public(priority)
        priorities.append(redacted if isinstance(redacted, dict) else priority)
        if len(priorities) >= limit:
            break
    return priorities


def _route_marker(route: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in route.items()))


def _route_from_ref(ref: Mapping[str, Any], priority: Mapping[str, Any]) -> dict[str, Any]:
    route = dict(ref)
    route["source_reopen_required_before_claim"] = True
    route["source_shape_priority"] = True
    route["source_shape_id"] = priority.get("source_shape_id")
    route["risk_flags"] = list(priority.get("risk_flags") or [])[:4]
    route["triage_rank_reason_codes"] = list(priority.get("triage_rank_reason_codes") or [])[:4]
    return route


def apply_source_shape_priority_to_active_recall_context(
    context: Mapping[str, Any],
    diagnostics: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Attach navigation-only source-shape priority to an active recall result."""

    priorities = source_shape_active_recall_priorities(diagnostics)
    if not priorities:
        return dict(context)

    result = dict(context)
    existing_routes = [route for route in result.get("source_reopen_routes") or [] if isinstance(route, Mapping)]
    priority_routes: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for priority in priorities:
        if priority.get("priority_class") == "hold_back":
            continue
        for ref in safe_source_refs(priority.get("source_refs")):
            route = _route_from_ref(ref, priority)
            marker = _route_marker(route)
            if marker in seen:
                continue
            seen.add(marker)
            priority_routes.append(route)
    for existing_route in existing_routes:
        marker = _route_marker(existing_route)
        if marker in seen:
            continue
        seen.add(marker)
        priority_routes.append(dict(existing_route))

    result["decision"] = "context"
    result["source_shape_recheck_priority"] = priorities
    result["source_reopen_routes"] = priority_routes
    if priority_routes:
        result["suggested_next"] = "reopen_source"
    surface_counts = dict(result.get("surface_counts") or {})
    surface_counts["source_shape_diagnostics"] = len(priorities)
    result["surface_counts"] = surface_counts
    source_boundary = dict(result.get("source_boundary") or {})
    source_boundary["source_shape_diagnostics_are_navigation_only"] = True
    source_boundary["source_shape_cannot_raise_claim_authority"] = True
    result["source_boundary"] = source_boundary
    return result


def load_source_shape_diagnostics(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON object/list or JSONL file of source-shape diagnostics."""

    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    rows: list[Any]
    if input_path.suffix.lower() == ".jsonl":
        result = parse_jsonl_dict_rows_text(text, strict=True)
        if int(result.loss.get("total_loss_count") or 0):
            raise ValueError("source-shape diagnostics JSONL contains malformed rows")
        rows = result.rows
    else:
        parsed = json.loads(text)
        rows = parsed if isinstance(parsed, list) else [parsed]
    return [row for row in rows if isinstance(row, dict)]
