from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal, TypeAlias

from aippocampus_runtime.macro import momentum as momentum_runtime
from aippocampus_runtime.macro.hexagram import (
    Hexagram,
    HexagramRef,
    resolve_hexagram,
)
from aippocampus_runtime.macro.hexagram_navigation import king_wen_pair_relation
from aippocampus_runtime.macro.perturbation import AUTHORITY_LEVEL, CLAIM_PERMISSION
from aippocampus_runtime.macro.signal_scales import (
    is_project_level_signal,
    normalize_signal_scale,
    public_signal_scale_schema,
    signal_scale_diagnostic,
)

MovementState: TypeAlias = Literal["advanced", "stalled", "reversed", "jumped", "forked"]
ReviewState: TypeAlias = Literal["needs_review", "machine_checked", "stale"]

KIND = "macro_orientation_stage_update"
SCHEMA_VERSION = "macro-stage-tracker-v0"
DEFAULT_RECHECK_ON = (
    "roadmap_shift",
    "benchmark_result",
    "repeated_route_failure",
    "user_correction",
    "macro_orientation_state_recheck",
)
ALLOWED_REVIEW_STATES = {"needs_review", "machine_checked", "stale"}
SOURCE_REF_KEYS = ("source_id", "ref_id", "url", "kind", "line", "span_id")


def _safe_source_refs(events: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    seen: set[str] = set()
    for event in events:
        raw_refs = event.get("source_refs")
        if not isinstance(raw_refs, Sequence) or isinstance(raw_refs, (str, bytes)):
            continue
        for raw_ref in raw_refs:
            if not isinstance(raw_ref, Mapping):
                continue
            ref = {key: raw_ref[key] for key in SOURCE_REF_KEYS if key in raw_ref}
            if not ref:
                continue
            encoded = json.dumps(ref, ensure_ascii=False, sort_keys=True)
            if encoded not in seen:
                seen.add(encoded)
                refs.append(ref)
    return refs


def _is_project_event(event: Mapping[str, Any]) -> bool:
    try:
        scale = normalize_signal_scale(str(event.get("signal_scale") or "project_event"))
    except ValueError:
        return False
    return is_project_level_signal(
        scale,
        promoted_to_project=bool(event.get("promoted_to_project")),
    )


def _eligible_events(events: Iterable[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], list[str]]:
    eligible: list[Mapping[str, Any]] = []
    diagnostics: list[str] = []
    for event in events:
        if _is_project_event(event):
            eligible.append(event)
        else:
            try:
                diagnostic = signal_scale_diagnostic(
                    str(event.get("signal_scale") or "unknown"),
                    promoted_to_project=bool(event.get("promoted_to_project")),
                )
            except ValueError:
                diagnostic = "invalid_signal_scale_ignored"
            diagnostics.append(diagnostic or "non_project_signal_ignored_without_project_promotion")
    return eligible, sorted(set(diagnostics))


def _event_target(event: Mapping[str, Any]) -> Hexagram | None:
    target = event.get("target_hexagram") or event.get("current_hexagram")
    if target is None:
        return None
    try:
        return resolve_hexagram(target)
    except ValueError:
        return None


def _numeric_event_sum(events: Iterable[Mapping[str, Any]], key: str) -> float:
    total = 0.0
    for event in events:
        value = event.get(key)
        if isinstance(value, int | float):
            total += float(value)
    return round(total, 3)


def _numeric_mapping_value(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _momentum_summary(events: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    basis = momentum_runtime.normalize_momentum_basis(
        {
            key: _numeric_event_sum(events, key)
            for key in momentum_runtime.MOMENTUM_BASIS_KEYS
        }
    )
    block = momentum_runtime.build_momentum_block(basis)
    raw_trend = block.get("trend")
    trend: Mapping[str, object] = raw_trend if isinstance(raw_trend, Mapping) else {}
    support = _numeric_mapping_value(trend, "supporting_delta")
    friction = _numeric_mapping_value(trend, "friction_delta")
    net = _numeric_mapping_value(trend, "net_delta")
    route_success = float(basis["route_success_delta"])
    if not events:
        phase = "hibernating"
    elif friction > support:
        phase = "declining"
    elif friction > 0 and support > 0:
        phase = "turning"
    elif support >= 2 and route_success > 0:
        phase = "peaking"
    elif support > 0:
        phase = "rising"
    else:
        phase = "hibernating"
    return {
        "phase_hint": phase,
        "basis": basis,
        "trend": {"supporting_delta": support, "friction_delta": friction, "net_delta": net},
        "momentum_phase": block.get("phase"),
        "authority_level": AUTHORITY_LEVEL,
        "status": "compact_trend_hint_not_full_xiaoxi_phase",
    }


def _movement_state(previous: Hexagram, current: Hexagram) -> MovementState:
    if current.number == previous.number:
        return "stalled"
    if previous.wen_next and current.number == previous.wen_next.number:
        return "advanced"
    if previous.wen_prev and current.number == previous.wen_prev.number:
        return "reversed"
    return "jumped"


def _pair_transition(previous: Hexagram, current: Hexagram) -> tuple[str, dict[str, object]]:
    relation = king_wen_pair_relation(previous)
    mate = relation.get("pair_mate")
    mate_number = mate.get("number") if isinstance(mate, Mapping) else None
    if current.number == previous.number:
        transition = "same_state"
    elif current.number == mate_number:
        transition = "pair_internal"
    else:
        transition = "cross_pair"
    return transition, relation


def _candidate_targets(events: Iterable[Mapping[str, Any]]) -> list[Hexagram]:
    by_number: dict[int, Hexagram] = {}
    for event in events:
        target = _event_target(event)
        if target is not None:
            by_number[target.number] = target
    return [by_number[number] for number in sorted(by_number)]


def _review_state(value: str, *, force_needs_review: bool = False) -> ReviewState:
    if value not in ALLOWED_REVIEW_STATES:
        raise ValueError(f"unknown stage review state: {value!r}")
    if force_needs_review:
        return "needs_review"
    return value  # type: ignore[return-value]


def _event_values(events: Iterable[Mapping[str, Any]], key: str) -> list[str]:
    values = {str(event.get(key)) for event in events if event.get(key)}
    return sorted(values)


def _recheck_on(momentum: Mapping[str, object], diagnostics: Sequence[str]) -> list[str]:
    values = list(DEFAULT_RECHECK_ON)
    if momentum.get("phase_hint") in {"declining", "turning"}:
        values.append("momentum_first_decay_recheck")
    if diagnostics:
        values.append("stage_tracker_diagnostic_recheck")
    return list(dict.fromkeys(values))


def build_stage_update(
    *,
    project: str,
    previous: HexagramRef,
    source_events: Sequence[Mapping[str, Any]],
    review_state: ReviewState = "needs_review",
    report_only: bool = True,
) -> dict[str, object]:
    if not project.strip():
        raise ValueError("project must be non-empty")
    previous_hexagram = resolve_hexagram(previous)
    eligible, diagnostics = _eligible_events(source_events)
    targets = _candidate_targets(eligible)
    forked = len(targets) > 1
    current = targets[0] if targets else previous_hexagram
    movement: MovementState = "forked" if forked else _movement_state(previous_hexagram, current)
    pair_transition, pair_relation = _pair_transition(previous_hexagram, current)
    if forked:
        diagnostics.append("stage_fork_requires_review")
    if movement == "jumped":
        diagnostics.append("non_adjacent_stage_jump_requires_review")
    if pair_transition == "pair_internal":
        diagnostics.append("king_wen_pair_internal_perspective_shift")
    elif pair_transition == "cross_pair":
        diagnostics.append("king_wen_cross_pair_transition")
    if not targets:
        diagnostics.append("no_project_level_stage_event")
    momentum = _momentum_summary(eligible)
    forced_review = forked or not targets
    state = _review_state(str(review_state), force_needs_review=forced_review)

    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {"kind": "project", "project": project},
        "sequence": {
            "track": "king_wen",
            "previous": previous_hexagram.name,
            "previous_number": previous_hexagram.number,
            "current": current.name,
            "current_number": current.number,
            "movement_state": movement,
            "pair_transition": pair_transition,
            "king_wen_pair": pair_relation,
            "fork_candidates": [
                {"name": target.name, "number": target.number} for target in targets
            ]
            if forked
            else [],
        },
        "source_refs": _safe_source_refs(eligible),
        "event_types": _event_values(eligible, "event_type"),
        "worker_lanes": _event_values(eligible, "source_lane"),
        "event_count": len(eligible),
        "review_state": state,
        "recheck_on": _recheck_on(momentum, diagnostics),
        "momentum": momentum,
        "diagnostics": sorted(set(diagnostics)),
        "report_only": report_only,
        "write_effect": "none" if report_only else "explicit_operator_write_required",
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_boundary": {
            "stage_tracker_is_navigation_only": True,
            "source_events_decide_movement": True,
            "king_wen_sequence_is_topology_candidate_not_project_law": True,
            "signal_scale_schema": public_signal_scale_schema(),
        },
    }


def recheck_stage_update(
    update: Mapping[str, Any],
    *,
    later_events: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    eligible, diagnostics = _eligible_events(later_events)
    current = str(update.get("sequence", {}).get("current") if isinstance(update.get("sequence"), Mapping) else "")
    later_targets = {target.name for target in _candidate_targets(eligible)}
    contradiction = bool(later_targets and (current not in later_targets))
    correction = any(str(event.get("event_type")) == "user_correction" for event in eligible)
    result = dict(update)
    merged_diagnostics = set(update.get("diagnostics", [])) if isinstance(update.get("diagnostics"), list) else set()
    merged_diagnostics.update(diagnostics)
    if contradiction or correction:
        result["review_state"] = "stale"
        result["diagnostic_only"] = True
        merged_diagnostics.add("later_source_contradicts_stage")
        recheck = list(update.get("recheck_on", [])) if isinstance(update.get("recheck_on"), list) else []
        recheck.append("source_contradiction_recheck")
        result["recheck_on"] = list(dict.fromkeys(str(item) for item in recheck))
    result["diagnostics"] = sorted(str(item) for item in merged_diagnostics)
    result["later_source_refs"] = _safe_source_refs(eligible)
    result["fact_claim_allowed"] = False
    return result


def _case_sequence_value(case: Mapping[str, object], key: str) -> str:
    sequence = case.get("sequence")
    if isinstance(sequence, Mapping):
        return str(sequence.get(key) or "")
    return ""


def _case_str_list(case: Mapping[str, object], key: str) -> list[str]:
    value = case.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def build_stage_tracker_fixture_report() -> dict[str, object]:
    def event(event_id: str, target: str, **updates: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": event_id,
            "event_type": "roadmap_shift",
            "target_hexagram": target,
            "source_lane": "integration_worker",
            "signal_scale": "project_event",
            "source_refs": [{"source_id": f"fixture-{event_id}"}],
            "support_delta": 1.0,
            "route_success_delta": 0.0,
        }
        payload.update(updates)
        return payload

    cases = [
        build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[event("advanced", "解", support_delta=2.0, route_success_delta=1.0)],
            review_state="machine_checked",
        ),
        build_stage_update(project="AIppocampus", previous="蹇", source_events=[event("stalled", "蹇")]),
        build_stage_update(project="AIppocampus", previous="解", source_events=[event("reversed", "蹇")]),
        build_stage_update(project="AIppocampus", previous="蹇", source_events=[event("jumped", "益")]),
        build_stage_update(
            project="AIppocampus",
            previous="蹇",
            source_events=[event("fork-a", "解"), event("fork-b", "损")],
        ),
    ]
    movement_states = {_case_sequence_value(case, "movement_state") for case in cases}
    worker_lanes = sorted({lane for case in cases for lane in _case_str_list(case, "worker_lanes")})
    metrics = {
        "movement_state_coverage_count": len(movement_states),
        "claim_ready_stage_updates": sum(1 for case in cases if case["fact_claim_allowed"]),
        "write_effect_count": sum(1 for case in cases if case["write_effect"] != "none"),
        "stale_or_review_needed_count": sum(
            1 for case in cases if case["review_state"] in {"needs_review", "stale"}
        ),
    }
    report = {
        "kind": "macro_stage_tracker_fixture_report",
        "schema_version": SCHEMA_VERSION,
        "ok": (
            metrics["movement_state_coverage_count"] == 5
            and metrics["claim_ready_stage_updates"] == 0
            and metrics["write_effect_count"] == 0
        ),
        "cases": cases,
        "worker_lanes": worker_lanes,
        "momentum_summary": cases[0]["momentum"],
        "metrics": metrics,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
    }
    return report


__all__ = [
    "DEFAULT_RECHECK_ON",
    "KIND",
    "MovementState",
    "ReviewState",
    "SCHEMA_VERSION",
    "build_stage_tracker_fixture_report",
    "build_stage_update",
    "recheck_stage_update",
]
