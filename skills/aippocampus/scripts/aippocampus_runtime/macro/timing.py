"""Source-epoch timing diagnostics for macro-orientation experiments."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from aippocampus_runtime.macro import line_topology, momentum

AUTHORITY_LEVEL = "navigation_only"
ACTION_GRAMMAR = "direction_only"
CLAIM_PERMISSION = "no_claim_before_reopen"

ProjectActivityLevel = Literal["normal", "slow_quiet", "high_activity"]

_CADENCE_THRESHOLDS: dict[ProjectActivityLevel, int] = {
    "high_activity": 3,
    "normal": 5,
    "slow_quiet": 8,
}


def _float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _line(value: Any) -> int:
    line = _int(value, default=0)
    if line < 1 or line > 6:
        raise ValueError("macro timing source event line must be in 1..6")
    return line


def _basis_for_event(event: Mapping[str, Any]) -> dict[str, float]:
    return {
        key: _float(event.get(key))
        for key in momentum.MOMENTUM_BASIS_KEYS
    }


def _recency_boost(event: Mapping[str, Any]) -> float:
    rank = _int(event.get("recency_rank"), default=0)
    if rank <= 0:
        return 0.0
    return max(0.0, 0.18 - ((rank - 1) * 0.04))


def _source_epoch_boost(event: Mapping[str, Any], max_epoch: int) -> float:
    epoch = _int(event.get("source_epoch"), default=0)
    if epoch <= 0 or max_epoch <= 0:
        return 0.0
    return min(0.12, max(0.0, epoch / max_epoch) * 0.12)


def _empty_line_weight(axis: Mapping[str, object]) -> dict[str, Any]:
    return {
        "line": _int(axis.get("line"), default=0),
        "axis_id": str(axis["axis_id"]),
        "layer": str(axis["layer"]),
        "event_count": 0,
        "source_epoch_max": 0,
        "attention_weight": 0.0,
        "supporting_delta": 0.0,
        "friction_delta": 0.0,
        "net_delta": 0.0,
        "recheck_on": [],
        "reason_codes": ["no_source_epoch_delta"],
        "currentness_status": "unchanged",
        "temporal_status": "unchanged",
    }


def line_time_weights(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    max_epoch = max((_int(event.get("source_epoch"), default=0) for event in events), default=0)
    axes = {_int(axis.get("line"), default=0): axis for axis in line_topology.axis_mapping()}
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[_line(event.get("line"))].append(event)

    rows: list[dict[str, Any]] = []
    for line in range(1, 7):
        axis = axes[line]
        line_events = grouped.get(line, [])
        if not line_events:
            rows.append(_empty_line_weight(axis))
            continue
        supporting = 0.0
        friction = 0.0
        reason_codes: set[str] = set()
        source_epoch_max = 0
        for event in line_events:
            basis = _basis_for_event(event)
            event_support = basis["support_delta"] + basis["route_success_delta"]
            event_friction = (
                basis["counter_evidence_delta"]
                + basis["staleness_delta"]
                + basis["user_correction_delta"]
            )
            supporting += event_support
            friction += event_friction
            source_epoch_max = max(source_epoch_max, _int(event.get("source_epoch"), default=0))
            if basis["route_success_delta"] > 0:
                reason_codes.add("route_success_delta")
            if basis["support_delta"] > 0:
                reason_codes.add("support_delta")
            if basis["counter_evidence_delta"] > 0:
                reason_codes.add("counter_evidence_pressure")
            if basis["staleness_delta"] > 0:
                reason_codes.add("staleness_pressure")
            if basis["user_correction_delta"] > 0:
                reason_codes.add("user_correction_pressure")
        net_delta = supporting - friction
        recency = sum(_recency_boost(event) for event in line_events)
        epoch = sum(_source_epoch_boost(event, max_epoch) for event in line_events)
        attention_weight = max(0.0, supporting + recency + epoch - (friction * 0.35))
        recheck_on: list[str] = []
        if friction > 0 and friction >= supporting:
            recheck_on.append("axis_currentness_recheck")
        if net_delta < -0.15:
            recheck_on.append("axis_momentum_recheck")
        if not reason_codes:
            reason_codes.add("source_epoch_delta_seen")
        rows.append(
            {
                "line": line,
                "axis_id": str(axis["axis_id"]),
                "layer": str(axis["layer"]),
                "event_count": len(line_events),
                "source_epoch_max": source_epoch_max,
                "attention_weight": round(attention_weight, 6),
                "supporting_delta": round(supporting, 6),
                "friction_delta": round(friction, 6),
                "net_delta": round(net_delta, 6),
                "recheck_on": recheck_on,
                "reason_codes": sorted(reason_codes),
                # Currentness and temporal heads own fact/freshness decisions; this
                # report only chooses which axis deserves a source-backed recheck.
                "currentness_status": "unchanged",
                "temporal_status": "unchanged",
            }
        )
    return rows


def _active_axis(weights: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = max(
        weights,
        key=lambda row: (
            _float(row.get("attention_weight")),
            _int(row.get("source_epoch_max"), default=0),
            -_int(row.get("line"), default=0),
        ),
    )
    return {
        "line": selected["line"],
        "axis_id": selected["axis_id"],
        "layer": selected["layer"],
        "attention_weight": selected["attention_weight"],
        "reason_codes": selected["reason_codes"],
        "recheck_on": selected["recheck_on"],
        "currentness_status": "unchanged",
        "temporal_status": "unchanged",
    }


def source_epoch_cadence(
    events: Sequence[Mapping[str, Any]],
    *,
    quiet_source_event_count: int,
    project_activity_level: ProjectActivityLevel = "normal",
) -> dict[str, Any]:
    threshold = _CADENCE_THRESHOLDS.get(project_activity_level, _CADENCE_THRESHOLDS["normal"])
    epochs = [_int(event.get("source_epoch"), default=0) for event in events]
    latest_epoch = max(epochs, default=0)
    earliest_epoch = min((epoch for epoch in epochs if epoch > 0), default=0)
    epoch_span = latest_epoch - earliest_epoch + 1 if latest_epoch and earliest_epoch else 0
    recheck_due = quiet_source_event_count >= threshold
    return {
        "kind": "macro_source_epoch_cadence",
        "timing_basis": "source_epoch",
        "project_activity_level": project_activity_level,
        "quiet_source_event_count": quiet_source_event_count,
        "quiet_threshold": threshold,
        "source_epoch_span": epoch_span,
        "latest_source_epoch": latest_epoch,
        "recheck_due": recheck_due,
        "recheck_on": ["macro_cadence_recheck"] if recheck_due else [],
        "calendar_cycle_used": False,
        "literal_solar_term_used": False,
    }


def build_macro_timing_report(
    events: Sequence[Mapping[str, Any]],
    *,
    quiet_source_event_count: int,
    project_activity_level: ProjectActivityLevel = "normal",
) -> dict[str, Any]:
    weights = line_time_weights(events)
    active_axis = _active_axis(weights)
    cadence = source_epoch_cadence(
        events,
        quiet_source_event_count=quiet_source_event_count,
        project_activity_level=project_activity_level,
    )
    distinct_signal = bool(active_axis["attention_weight"]) or bool(cadence["recheck_due"])
    return {
        "kind": "macro_timing_recheck_report",
        "source_event_count": len(events),
        "line_time_weights": weights,
        "active_axis": active_axis,
        "cadence": cadence,
        "distinct_signal": distinct_signal,
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "foreground_emitted": False,
        "default_ranking_effect": "none",
        "boundary": {
            "active_axis_is_attention_not_truth": True,
            "source_epoch_not_calendar": True,
            "does_not_replace_currentness_head": True,
            "does_not_replace_temporal_head": True,
            "source_reopen_required_for_claims": True,
            "no_default_foreground_prose": True,
        },
    }


__all__ = [
    "ACTION_GRAMMAR",
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "ProjectActivityLevel",
    "build_macro_timing_report",
    "line_time_weights",
    "source_epoch_cadence",
]
