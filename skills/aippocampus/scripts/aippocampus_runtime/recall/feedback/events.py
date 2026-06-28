#!/usr/bin/env python3
"""Privacy-safe recall and active-flow feedback contracts.

Feedback events are calibration and routing evidence only. They deliberately
record stable handles, signal families, route kinds, and outcome counts instead
of raw prompts, source excerpts, or local paths. Future score-fusion or pathlet
calibration can consume these reports, but source truth still belongs to clean
source and explicit source reopen.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc, stable_json_join_id
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.feedback.suppression_lifecycle import (
    current_feedback_state,
    feedback_trace_family,
    foreground_eligible,
    route_reason_codes,
    suppression_lifecycle_report,
)
from aippocampus_runtime.recall.feedback.vocabulary import (
    ACTIVE_FLOW_SIGNALS,
    DEFAULT_SIGNAL_DELTAS,
    OUTCOME_ALIASES,
    normalize_feedback_signal,
)
from aippocampus_runtime.source.agent_trace_admission import (
    behavior_training_signal_from_trace,
    project_behavior_training_ledger,
)
from aippocampus_runtime.source.io_kernel import normalize_source_refs, safe_float

SCHEMA_VERSION = 1
RECALL_FEEDBACK_KIND = "aippocampus_recall_feedback_event"
RECALL_FEEDBACK_REPORT_KIND = "aippocampus_recall_feedback_report"
ACTIVE_FLOW_EVENT_KIND = "aippocampus_active_flow_event"
ALIAS_MERGE_EVENT_KIND = "aippocampus_alias_merge_feedback_event"
CONTEXT_SUPPRESSION_EVENT_KIND = "aippocampus_context_suppression_feedback_event"
ACTIVE_FLOW_REPORT_KIND = "aippocampus_active_flow_activation_report"
FEEDBACK_CALIBRATION_REPORT_KIND = "aippocampus_feedback_calibration_report"
PUBLIC_FIXTURE_KIND = "public_route_feedback_fixture"

RECALL_OUTCOMES = {
    "candidate_delivered",
    "source_reopen_success",
    "reopened_deepened",
    "ignored",
    "corrected",
    "superseded",
    "blocked",
    "expired",
}
SIGNAL_FAMILIES = {"text", "vector", "graph", "source_richness", "route_context"}
BLEND_CONTEXT_FALLBACK = "normal_recall"

ROUTE_KINDS = {"pathlet", "continuity_domain", "sequence_packet", "active_path"}


class InvalidFeedbackValue(ValueError):
    """Raised when feedback would otherwise be silently misclassified."""

    def __init__(
        self,
        field: str,
        value: Any,
        accepted: Collection[str],
        aliases: Mapping[str, str] | None = None,
    ):
        self.field = field
        self.value = value
        self.accepted = set(accepted)
        self.aliases = dict(aliases or {})
        valid = sorted(self.accepted | set(self.aliases))
        super().__init__(f"unsupported {field}: {value!r}; expected one of {', '.join(valid)}")


def _safe_token(value: Any, *, fallback_prefix: str) -> str:
    text = str(value or "").strip()
    if not text:
        return stable_json_join_id(
            fallback_prefix,
            "",
            ensure_ascii=False,
            default_str=False,
        )
    safe = redact_sensitive_values(redact_private_paths(text))
    if safe != text or "\\" in safe or "/" in safe:
        return stable_json_join_id(
            fallback_prefix,
            safe,
            ensure_ascii=False,
            default_str=False,
        )
    return safe[:160]


def _safe_alias_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    safe = redact_sensitive_values(redact_private_paths(text)).strip()
    if safe != text or "\\" in safe or "/" in safe:
        return ""
    return safe[:72]


def _safe_kind(value: Any, accepted: Collection[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in accepted else default


def _validated_kind(
    value: Any,
    accepted: Collection[str],
    *,
    field: str,
    aliases: Mapping[str, str] | None = None,
) -> str:
    text = str(value or "").strip()
    if text in accepted:
        return text
    if aliases and text in aliases:
        return aliases[text]
    raise InvalidFeedbackValue(field, text, accepted, aliases)


def recall_feedback_event(
    *,
    candidate_id: str,
    source_id: str,
    blend_context: str = BLEND_CONTEXT_FALLBACK,
    signal_family: str = "route_context",
    outcome: str = "candidate_delivered",
    route_kind: str = "active_path",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Return one public-safe recall interaction row.

    The row is intentionally small: it can explain which signal family and
    blend context led to a later outcome, but it cannot be used as a claim about
    the source content itself.
    """

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RECALL_FEEDBACK_KIND,
        "created_at": timestamp or now_utc(),
        "candidate_id": _safe_token(candidate_id, fallback_prefix="candidate"),
        "source_id": _safe_token(source_id, fallback_prefix="source"),
        "blend_context": str(blend_context or BLEND_CONTEXT_FALLBACK),
        "signal_family": _safe_kind(signal_family, SIGNAL_FAMILIES, "route_context"),
        "outcome": _safe_kind(outcome, RECALL_OUTCOMES, "candidate_delivered"),
        "route_kind": _safe_kind(route_kind, ROUTE_KINDS, "active_path"),
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
        "policy_boundary": {
            "telemetry_is_calibration_evidence": True,
            "does_not_update_score_weights": True,
            "source_reopen_required_for_claims": True,
        },
    }


def _empty_signal_group() -> dict[str, Any]:
    row: dict[str, Any] = {f"{outcome}_count": 0 for outcome in sorted(RECALL_OUTCOMES)}
    row["event_count"] = 0
    row["route_kinds"] = {}
    return row


def recall_feedback_report(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    event_rows = [event for event in events if isinstance(event, Mapping)]
    by_context: dict[str, dict[str, Any]] = {}
    outcome_counts: Counter[str] = Counter()
    event_count = 0
    for event in event_rows:
        if event.get("kind") not in {RECALL_FEEDBACK_KIND, ACTIVE_FLOW_EVENT_KIND}:
            continue
        event_count += 1
        context = str(event.get("blend_context") or BLEND_CONTEXT_FALLBACK)
        family = _safe_kind(event.get("signal_family"), SIGNAL_FAMILIES, "route_context")
        outcome = str(event.get("outcome") or event.get("signal") or "candidate_delivered")
        outcome = _safe_kind(outcome, RECALL_OUTCOMES | ACTIVE_FLOW_SIGNALS, "candidate_delivered")
        route_kind = _safe_kind(event.get("route_kind"), ROUTE_KINDS, "active_path")
        context_row = by_context.setdefault(context, {"signal_families": {}})
        family_row = context_row["signal_families"].setdefault(family, _empty_signal_group())
        key = f"{outcome}_count"
        if key not in family_row:
            family_row[key] = 0
        family_row[key] += 1
        family_row["event_count"] += 1
        routes = Counter(family_row.get("route_kinds") or {})
        routes[route_kind] += 1
        family_row["route_kinds"] = dict(sorted(routes.items()))
        outcome_counts[outcome] += 1

    calibration = recall_feedback_calibration_report(event_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RECALL_FEEDBACK_REPORT_KIND,
        "created_at": now_utc(),
        "event_count": event_count,
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "by_blend_context": by_context,
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
        "policy_boundary": {
            "telemetry_is_calibration_evidence": True,
            "automatic_calibration_enabled": True,
            "calibration_report_is_no_write": True,
            "score_fusion_weights_changed": False,
        },
        "calibration": calibration,
    }


def active_flow_event(
    *,
    route_id: str,
    route_kind: str,
    signal: str,
    source_id: str = "",
    source_ref: Any = "",
    source_refs: Iterable[Mapping[str, Any]] | None = None,
    timestamp: str | None = None,
    weight_delta: float | None = None,
    reason: str = "",
) -> dict[str, Any]:
    safe_signal = normalize_feedback_signal(signal, default="")
    if safe_signal not in ACTIVE_FLOW_SIGNALS:
        raise InvalidFeedbackValue("outcome", signal, ACTIVE_FLOW_SIGNALS, OUTCOME_ALIASES)
    safe_route_kind = _validated_kind(route_kind, ROUTE_KINDS, field="route_kind")
    delta = DEFAULT_SIGNAL_DELTAS[safe_signal] if weight_delta is None else safe_float(weight_delta)
    normalized_refs = _canonical_source_refs(source_ref=source_ref, source_refs=source_refs)
    row = {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTIVE_FLOW_EVENT_KIND,
        "created_at": timestamp or now_utc(),
        "route_id": _safe_token(route_id, fallback_prefix="route"),
        "route_kind": safe_route_kind,
        "signal": safe_signal,
        "source_id": _source_id_from_inputs(source_id, source_ref),
        "weight_delta": round(delta, 6),
        "reason": _safe_token(reason, fallback_prefix="reason") if reason else "",
        "signal_family": "route_context",
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
        "policy_boundary": {
            "activation_weight_is_route_context": True,
            "activation_weight_is_not_source_truth": True,
            "does_not_delete_source_refs": True,
        },
    }
    if normalized_refs:
        row["source_refs"] = normalized_refs
        row["source_ref_count"] = len(normalized_refs)
    return row


def _canonical_source_refs(
    *,
    source_ref: Any = "",
    source_refs: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    raw_refs: Any = source_refs if source_refs is not None else source_ref
    refs = normalize_source_refs(
        raw_refs,
        limit=4,
        require_anchor=True,
        require_thread=False,
        identity_key=True,
        allow_string_ref=False,
    )
    return [dict(ref) for ref in refs]


def _source_id_from_inputs(source_id: Any, source_ref: Any) -> str:
    if source_id:
        return _safe_token(source_id, fallback_prefix="source")
    if isinstance(source_ref, Mapping):
        for key in ("source_id", "source_ref", "thread_key", "message_id"):
            if source_ref.get(key):
                return _safe_token(source_ref.get(key), fallback_prefix="source")
        return _safe_token("", fallback_prefix="source")
    return _safe_token(source_ref, fallback_prefix="source")


def alias_merge_event(
    *,
    route_id: str,
    aliases: list[str],
    route_kind: str = "active_path",
    source_id: str = "",
    timestamp: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Return route-local alias feedback without mutating source truth."""

    safe_route_kind = _validated_kind(route_kind, ROUTE_KINDS, field="route_kind")
    safe_aliases = [alias for alias in (_safe_alias_value(alias) for alias in aliases) if alias][:12]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ALIAS_MERGE_EVENT_KIND,
        "created_at": timestamp or now_utc(),
        "route_id": _safe_token(route_id, fallback_prefix="route"),
        "route_kind": safe_route_kind,
        "aliases": safe_aliases,
        "source_id": _safe_token(source_id, fallback_prefix="source") if source_id else "",
        "reason": _safe_token(reason, fallback_prefix="reason") if reason else "",
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
        "policy_boundary": {
            "alias_feedback_is_navigation_only": True,
            "activation_weight_is_not_source_truth": True,
            "does_not_delete_source_refs": True,
        },
    }


def suppress_context_event(
    *,
    route_id: str,
    context_cues: list[str],
    route_kind: str = "active_path",
    source_id: str = "",
    timestamp: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Return route-local context suppression without adding static blacklists."""

    safe_route_kind = _validated_kind(route_kind, ROUTE_KINDS, field="route_kind")
    safe_context_cues = [
        cue for cue in (_safe_alias_value(cue) for cue in context_cues) if cue
    ][:12]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTEXT_SUPPRESSION_EVENT_KIND,
        "created_at": timestamp or now_utc(),
        "route_id": _safe_token(route_id, fallback_prefix="route"),
        "route_kind": safe_route_kind,
        "context_cues": safe_context_cues,
        "source_id": _safe_token(source_id, fallback_prefix="source") if source_id else "",
        "reason": _safe_token(reason, fallback_prefix="reason") if reason else "",
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
        "policy_boundary": {
            "context_feedback_is_navigation_only": True,
            "activation_weight_is_not_source_truth": True,
            "does_not_delete_source_refs": True,
            "does_not_add_static_blacklist": True,
        },
    }


def active_flow_activation_report(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    event_rows = [event for event in events if isinstance(event, Mapping)]
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    metrics: Counter[str] = Counter()
    for event in event_rows:
        if event.get("kind") != ACTIVE_FLOW_EVENT_KIND:
            continue
        route_id = _safe_token(event.get("route_id"), fallback_prefix="route")
        route_kind = _safe_kind(event.get("route_kind"), ROUTE_KINDS, "active_path")
        signal = _safe_kind(event.get("signal"), ACTIVE_FLOW_SIGNALS, "candidate_delivered")
        row = grouped.setdefault(
            (route_id, route_kind),
            {
                "route_id": route_id,
                "route_kind": route_kind,
                "activation_score": 0.0,
                "event_count": 0,
                "signals": Counter(),
                "source_ids": set(),
                "last_signal": "",
            },
        )
        row["activation_score"] += safe_float(event.get("weight_delta"), DEFAULT_SIGNAL_DELTAS[signal])
        row["event_count"] += 1
        row["signals"][signal] += 1
        row["last_signal"] = signal
        if event.get("source_id"):
            row["source_ids"].add(_safe_token(event.get("source_id"), fallback_prefix="source"))
        metrics[f"{signal}_count"] += 1
        if signal == "expired":
            metrics["decay_applied_count"] += 1

    routes: list[dict[str, Any]] = []
    for row in grouped.values():
        signals: Counter[str] = row["signals"]
        score = round(float(row["activation_score"]), 6)
        last_signal = str(row.get("last_signal") or "")
        routes.append(
            {
                "route_id": row["route_id"],
                "route_kind": row["route_kind"],
                "activation_score": score,
                "event_count": row["event_count"],
                "current_feedback_state": current_feedback_state(last_signal),
                "signal_counts": dict(sorted(signals.items())),
                "source_ids": sorted(row["source_ids"]),
                "foreground_eligible": foreground_eligible(signals, last_signal, score),
                "reason_codes": route_reason_codes(signals, score),
                "source_boundary": {
                    "activation_metadata_is_ranking_context_only": True,
                    "source_refs_preserved": True,
                    "source_reopen_required_for_claims": True,
                },
            }
        )

    routes.sort(key=lambda row: (-float(row["activation_score"]), str(row["route_id"])))
    for key in (
        "source_reopen_success_count",
        "wrong_route_drag_count",
        "blocked_count",
        "decay_applied_count",
    ):
        metrics.setdefault(key, 0)
    calibration = recall_feedback_calibration_report(event_rows)
    training_signals = feedback_training_signal_rows(event_rows)
    suppression = suppression_lifecycle_report(event_rows, detail="operator")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTIVE_FLOW_REPORT_KIND,
        "created_at": now_utc(),
        "routes": routes,
        "metrics": dict(sorted(metrics.items())),
        "policy_boundary": {
            "activation_weights_are_not_source_truth": True,
            "default_route_weighting_unchanged": False,
            "default_route_weighting_consumer": "bounded_route_activation_metadata",
            "blocked_routes_do_not_shape_foreground_content": True,
        },
        "calibration": calibration,
        "training_signal_summary": project_behavior_training_ledger(
            training_signals,
            detail="operator",
        ),
        "suppression_lifecycle": {
            "status_counts": suppression["status_counts"],
            "hard_negative_count": suppression["hard_negative_count"],
            "overridden_by_positive_count": suppression["overridden_by_positive_count"],
        },
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
    }


def feedback_training_signal_rows(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project route feedback into shared behavior-derived training signals."""

    rows: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        kind = event.get("kind")
        if kind == ACTIVE_FLOW_EVENT_KIND:
            outcome = _safe_kind(event.get("signal"), ACTIVE_FLOW_SIGNALS, "candidate_delivered")
            route_id = event.get("route_id")
        elif kind == RECALL_FEEDBACK_KIND:
            outcome = _safe_kind(event.get("outcome"), RECALL_OUTCOMES, "candidate_delivered")
            route_id = event.get("candidate_id")
        else:
            continue
        trace = {
            "trace_id": stable_json_join_id(
                "feedback_training_signal",
                event.get("created_at"),
                route_id,
                outcome,
                ensure_ascii=False,
                default_str=False,
            ),
            "trace_family": feedback_trace_family(outcome),
            "outcome": outcome,
            "route_id": route_id,
            "cue_hash": event.get("cue_hash"),
            "preferred_route_id": event.get("preferred_route_id"),
            "rejected_route_ids": event.get("rejected_route_ids") or [],
            "scope": event.get("blend_context") or event.get("scope") or "",
            "safe_repo_relative": True,
        }
        if isinstance(event.get("source_refs"), list):
            source_refs = [
                dict(ref) for ref in event.get("source_refs") or [] if isinstance(ref, Mapping)
            ]
            trace["source_refs"] = source_refs
            trace["source_ref_count"] = len(source_refs)
        rows.append(behavior_training_signal_from_trace(trace))
    return rows


def recall_feedback_calibration_report(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate feedback into reversible route calibration deltas.

    The deltas are navigation metadata only. They can lift or demote route
    handles for future reopening, but they cannot emit facts, mutate source
    truth, or bypass source reopen.
    """

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    totals: Counter[str] = Counter()
    for event in events:
        kind = event.get("kind")
        if kind == ACTIVE_FLOW_EVENT_KIND:
            route_id = _safe_token(event.get("route_id"), fallback_prefix="route")
            route_kind = _safe_kind(event.get("route_kind"), ROUTE_KINDS, "active_path")
            outcome = _safe_kind(event.get("signal"), ACTIVE_FLOW_SIGNALS, "candidate_delivered")
            event_delta = safe_float(event.get("weight_delta"), DEFAULT_SIGNAL_DELTAS[outcome])
        elif kind == RECALL_FEEDBACK_KIND:
            route_id = _safe_token(event.get("candidate_id"), fallback_prefix="candidate")
            route_kind = _safe_kind(event.get("route_kind"), ROUTE_KINDS, "active_path")
            outcome = _safe_kind(event.get("outcome"), RECALL_OUTCOMES, "candidate_delivered")
            event_delta = DEFAULT_SIGNAL_DELTAS.get(outcome, 0.0)
        else:
            continue
        key = (route_id, route_kind)
        row = grouped.setdefault(
            key,
            {
                "route_id": route_id,
                "route_kind": route_kind,
                "event_count": 0,
                "delta": 0.0,
                "signals": Counter(),
            },
        )
        row["event_count"] += 1
        row["delta"] += event_delta
        row["signals"][outcome] += 1
        totals[outcome] += 1

    deltas: list[dict[str, Any]] = []
    for row in grouped.values():
        signals: Counter[str] = row["signals"]
        sparse = row["event_count"] < 2
        conflicting = bool(signals.get("source_reopen_success")) and bool(
            signals.get("wrong_route_drag") or signals.get("blocked") or signals.get("superseded")
        )
        bounded_delta = max(-1.0, min(1.0, float(row["delta"]) / max(1, row["event_count"])))
        if sparse or conflicting:
            bounded_delta = 0.0
        deltas.append(
            {
                "route_id": row["route_id"],
                "route_kind": row["route_kind"],
                "event_count": row["event_count"],
                "signal_counts": dict(sorted(signals.items())),
                "route_weight_delta": round(bounded_delta, 6),
                "foreground_eligible": bounded_delta > 0 and not sparse and not conflicting,
                "sparse_feedback_fallback": sparse,
                "conflicting_feedback_fallback": conflicting,
                "reason_codes": [
                    *(["source_reopen_success_lift"] if signals.get("source_reopen_success") else []),
                    *(["wrong_route_drag_demote"] if signals.get("wrong_route_drag") else []),
                    *(["blocked_or_superseded_demote"] if signals.get("blocked") or signals.get("superseded") else []),
                    *(["sparse_feedback_no_delta"] if sparse else []),
                    *(["conflicting_feedback_no_delta"] if conflicting else []),
                ],
            }
        )
    deltas.sort(key=lambda item: (-float(item["route_weight_delta"]), str(item["route_id"])))
    return {
        "kind": FEEDBACK_CALIBRATION_REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "no_write": True,
        "delta_count": len(deltas),
        "deltas": deltas,
        "outcome_counts": dict(sorted(totals.items())),
        "consumer": "bounded_route_activation_metadata",
        "policy_boundary": {
            "calibration_evidence_not_source_truth": True,
            "clean_source_mutation_allowed": False,
            "source_open_claim_allowed": False,
            "reversible_and_inspectable": True,
        },
        "cannot_claim": [
            "feedback_event_is_source_truth",
            "feedback_calibration_can_emit_source_open",
            "feedback_calibration_mutates_clean_source",
        ],
    }


def load_feedback_calibration_report(feedback_path: str | Path | None) -> dict[str, Any] | None:
    if not feedback_path:
        return None
    path = Path(feedback_path).expanduser().resolve()
    if not path.exists():
        report = recall_feedback_calibration_report([])
        report["load_status"] = "missing"
        report["event_count_loaded"] = 0
        return report
    events: list[Mapping[str, Any]] = []
    invalid_line_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                invalid_line_count += 1
                continue
            if isinstance(row, Mapping):
                events.append(row)
            else:
                invalid_line_count += 1
    report = recall_feedback_calibration_report(events)
    report["load_status"] = "loaded"
    report["event_count_loaded"] = len(events)
    report["invalid_line_count"] = invalid_line_count
    return report


def public_route_feedback_fixture_report() -> dict[str, Any]:
    events = [
        active_flow_event(
            route_id="public-fixture:pathlet:reopen-success",
            route_kind="pathlet",
            signal="source_reopen_success",
            source_id="public-fixture:source:expected-route",
        ),
        active_flow_event(
            route_id="public-fixture:domain:blocked-route",
            route_kind="continuity_domain",
            signal="blocked",
            source_id="public-fixture:source:blocked",
            reason="public fixture route intentionally blocked",
        ),
        active_flow_event(
            route_id="public-fixture:domain:blocked-route",
            route_kind="continuity_domain",
            signal="wrong_route_drag",
            source_id="public-fixture:source:blocked",
        ),
    ]
    report = active_flow_activation_report(events)
    report["fixture"] = {
        "kind": PUBLIC_FIXTURE_KIND,
        "source_family": "synthetic_public_safe",
        "event_count": len(events),
        "positive_signal": "source_reopen_success",
        "negative_signals": ["blocked", "wrong_route_drag"],
    }
    report["privacy_boundary"]["public_replayable_events_only"] = True
    return report
