#!/usr/bin/env python3
"""Privacy-safe recall and active-flow feedback contracts.

Feedback events are calibration and routing evidence only. They deliberately
record stable handles, signal families, route kinds, and outcome counts instead
of raw prompts, source excerpts, or local paths. Future score-fusion or pathlet
calibration can consume these reports, but source truth still belongs to clean
source and explicit source reopen.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

SCHEMA_VERSION = 1
RECALL_FEEDBACK_KIND = "aippocampus_recall_feedback_event"
RECALL_FEEDBACK_REPORT_KIND = "aippocampus_recall_feedback_report"
ACTIVE_FLOW_EVENT_KIND = "aippocampus_active_flow_event"
ACTIVE_FLOW_REPORT_KIND = "aippocampus_active_flow_activation_report"
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
ACTIVE_FLOW_SIGNALS = {
    "source_reopen_success",
    "user_confirmed",
    "prevented_failure",
    "candidate_delivered",
    "ignored",
    "wrong_route_drag",
    "blocked",
    "superseded",
    "expired",
}
DEFAULT_SIGNAL_DELTAS = {
    "source_reopen_success": 1.0,
    "user_confirmed": 0.75,
    "prevented_failure": 0.75,
    "candidate_delivered": 0.1,
    "ignored": -0.15,
    "wrong_route_drag": -1.0,
    "blocked": -1.0,
    "superseded": -0.8,
    "expired": -0.4,
}
NON_FOREGROUND_SIGNALS = {"blocked", "wrong_route_drag", "superseded", "expired"}
OUTCOME_ALIASES = {"wrong_route": "wrong_route_drag"}


class InvalidFeedbackValue(ValueError):
    """Raised when feedback would otherwise be silently misclassified."""

    def __init__(self, field: str, value: Any, accepted: set[str], aliases: Mapping[str, str] | None = None):
        self.field = field
        self.value = value
        self.accepted = set(accepted)
        self.aliases = dict(aliases or {})
        valid = sorted(self.accepted | set(self.aliases))
        super().__init__(f"unsupported {field}: {value!r}; expected one of {', '.join(valid)}")


def _stable_hash(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _safe_token(value: Any, *, fallback_prefix: str) -> str:
    text = str(value or "").strip()
    if not text:
        return _stable_hash(fallback_prefix, "")
    safe = redact_sensitive_values(redact_private_paths(text))
    if safe != text or "\\" in safe or "/" in safe:
        return _stable_hash(fallback_prefix, safe)
    return safe[:160]


def _safe_kind(value: Any, accepted: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in accepted else default


def _validated_kind(
    value: Any,
    accepted: set[str],
    *,
    field: str,
    aliases: Mapping[str, str] | None = None,
) -> str:
    text = str(value or "").strip()
    if aliases and text in aliases:
        return aliases[text]
    if text in accepted:
        return text
    raise InvalidFeedbackValue(field, text, accepted, aliases)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


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
    by_context: dict[str, dict[str, Any]] = {}
    outcome_counts: Counter[str] = Counter()
    event_count = 0
    for event in events:
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
            "automatic_calibration_enabled": False,
            "score_fusion_weights_changed": False,
        },
    }


def active_flow_event(
    *,
    route_id: str,
    route_kind: str,
    signal: str,
    source_id: str = "",
    source_ref: str = "",
    timestamp: str | None = None,
    weight_delta: float | None = None,
    reason: str = "",
) -> dict[str, Any]:
    safe_signal = _validated_kind(
        signal,
        ACTIVE_FLOW_SIGNALS,
        field="outcome",
        aliases=OUTCOME_ALIASES,
    )
    safe_route_kind = _validated_kind(route_kind, ROUTE_KINDS, field="route_kind")
    delta = DEFAULT_SIGNAL_DELTAS[safe_signal] if weight_delta is None else _safe_float(weight_delta)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTIVE_FLOW_EVENT_KIND,
        "created_at": timestamp or now_utc(),
        "route_id": _safe_token(route_id, fallback_prefix="route"),
        "route_kind": safe_route_kind,
        "signal": safe_signal,
        "source_id": _safe_token(source_id or source_ref, fallback_prefix="source"),
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


def _route_reason_codes(signals: Counter[str], score: float) -> list[str]:
    reasons: list[str] = []
    if signals.get("blocked"):
        reasons.append("blocked_route_not_foreground_eligible")
    if signals.get("wrong_route_drag"):
        reasons.append("wrong_route_drag_demoted")
    if signals.get("superseded"):
        reasons.append("superseded_route_demoted")
    if signals.get("expired"):
        reasons.append("expired_route_decay_applied")
    if signals.get("source_reopen_success"):
        reasons.append("source_reopen_success_promoted")
    if signals.get("user_confirmed"):
        reasons.append("user_confirmed_promoted")
    if score <= 0 and not reasons:
        reasons.append("non_positive_activation_score")
    return reasons


def active_flow_activation_report(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    metrics: Counter[str] = Counter()
    for event in events:
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
            },
        )
        row["activation_score"] += _safe_float(event.get("weight_delta"), DEFAULT_SIGNAL_DELTAS[signal])
        row["event_count"] += 1
        row["signals"][signal] += 1
        if event.get("source_id"):
            row["source_ids"].add(_safe_token(event.get("source_id"), fallback_prefix="source"))
        metrics[f"{signal}_count"] += 1
        if signal == "expired":
            metrics["decay_applied_count"] += 1

    routes: list[dict[str, Any]] = []
    for row in grouped.values():
        signals: Counter[str] = row["signals"]
        score = round(float(row["activation_score"]), 6)
        foreground_eligible = score > 0 and not any(signals.get(signal) for signal in NON_FOREGROUND_SIGNALS)
        routes.append(
            {
                "route_id": row["route_id"],
                "route_kind": row["route_kind"],
                "activation_score": score,
                "event_count": row["event_count"],
                "signal_counts": dict(sorted(signals.items())),
                "source_ids": sorted(row["source_ids"]),
                "foreground_eligible": foreground_eligible,
                "reason_codes": _route_reason_codes(signals, score),
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
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ACTIVE_FLOW_REPORT_KIND,
        "created_at": now_utc(),
        "routes": routes,
        "metrics": dict(sorted(metrics.items())),
        "policy_boundary": {
            "activation_weights_are_not_source_truth": True,
            "default_route_weighting_unchanged": True,
            "blocked_routes_do_not_shape_foreground_content": True,
        },
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
    }


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
