#!/usr/bin/env python3
"""Source-backed Journey Tracking core.

Journey tracking is a navigation layer for long-running multi-thread inquiry.
It does not model the user, does not turn every turn into a journey, and does
not make current_frontier a source of truth. Source truth remains attached to
append-only waypoints through clean-source refs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.source.io_kernel import (
    merge_source_refs as merge_source_ref_groups,
)
from aippocampus_runtime.source.io_kernel import normalize_source_refs
from aippocampus_runtime.source.texture_consumption import (
    select_texture_signals,
    texture_signal_summary,
)

SCHEMA_VERSION = 1
JOURNEY_KIND = "aippocampus_journey"
WAYPOINT_KIND = "journey_waypoint"
FRONTIER_KIND = "journey_current_frontier"
REPLAY_SMOKE_KIND = "aippocampus_journey_replay_fixture_smoke"
CONTENT_LIGHT_SIGNATURE_KIND = "aippocampus_content_light_journey_signature"
CONTENT_LIGHT_RESONANCE_KIND = "aippocampus_content_light_journey_resonance"

JourneyStatus = Literal["traveling", "camped", "arrived", "abandoned"]
FeedbackAction = Literal["confirm", "correct", "merge", "abandon", "revive"]

BASE_TTL_DAYS = 90
TTL_BONUS_PER_WAYPOINT_DAYS = 14
MAX_TTL_BONUS_DAYS = 180
CAMPED_AFTER_DAYS = 45
MIN_JOURNEY_THREADS = 3
MIN_JOURNEY_WAYPOINTS = 3
GENERIC_INQUIRIES = {
    "programming",
    "coding",
    "writing",
    "work",
    "project",
    "memory",
    "help",
    "general",
}
SAFE_STRUCTURE_LABEL_PREFIXES = ("dynamics:", "phase:", "transition:")
SAFE_RESONANCE_PATTERNS = (
    "stale_generated_artifact",
    "rejected_route",
)
PRIVATE_TOKEN_RE = re.compile(
    r"([A-Za-z]:[\\/])|([\\/][^\\/\s]+[\\/])|(\w+://)|(@)|(\bsecret\b)|(\bprivate\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Waypoint:
    waypoint_id: str
    moment: str
    thread_id: str
    timestamp: str
    source_refs: tuple[dict[str, Any], ...]
    arc: str = "unmapped"
    labels: tuple[str, ...] = ()
    frontier_hint: str = ""
    texture_signals: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Journey:
    journey_id: str
    path_label: str
    core_inquiry: str
    waypoints: tuple[Waypoint, ...]
    current_frontier: str
    current_frontier_kind: str
    current_frontier_source_refs: tuple[dict[str, Any], ...]
    source_refs: tuple[dict[str, Any], ...]
    active_questions: tuple[str, ...]
    first_seen: str
    last_seen: str
    expires_at: str
    status: JourneyStatus
    feedback_history: tuple[dict[str, Any], ...] = ()
    merged_into: str | None = None


@dataclass(frozen=True)
class JourneyFeedback:
    journey_id: str
    action: FeedbackAction
    timestamp: str
    correction: str | None = None
    merge_target: str | None = None


@dataclass(frozen=True)
class JourneyInstantiationResult:
    created: bool
    reason: str
    journey: Journey | None = None


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_digest(*parts: object, prefix: str, length: int = 16) -> str:
    raw = "\n".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def unique_preserve(values: Iterable[str], *, limit: int = 20) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = compact_text(str(value or ""), 120)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


def waypoint_thread_id(row: Mapping[str, Any], refs: tuple[dict[str, Any], ...]) -> str:
    for key in ("thread_id", "thread_key"):
        value = row.get(key)
        if value:
            return str(value)
    for ref in refs:
        value = ref.get("thread_key") or ref.get("thread_id")
        if value:
            return str(value)
    return ""


def frontier_hint_from_texture_signals(signals: Iterable[Mapping[str, Any]]) -> str:
    for signal in signals:
        signal_kind = str(signal.get("signal_kind") or "")
        detail = compact_text(str(signal.get("signal_detail") or ""), 120)
        if signal_kind in {"uncertainty_or_frontier_signal", "self_correction_signal"}:
            return compact_text(
                f"Resume from a texture-backed open frontier ({detail or signal_kind}); "
                "reopen source before treating it as a claim.",
                220,
            )
        if signal_kind in {"abandoned_direction", "rejected_route", "process_route_note"}:
            return compact_text(
                f"Review the texture-backed route boundary ({detail or signal_kind}) before continuing.",
                220,
            )
        if signal_kind == "tool_failure_texture":
            return compact_text(
                f"Continue after the texture-backed tool/verification failure ({detail or signal_kind}) is resolved.",
                220,
            )
    return ""


def waypoint_from_mapping(row: Mapping[str, Any]) -> Waypoint | None:
    refs = normalize_source_refs(
        row.get("source_refs") or row.get("source_ref"),
        thread_key=str(row.get("thread_id") or row.get("thread_key") or ""),
        require_thread=False,
        allow_string_ref=True,
    )
    if not refs:
        return None
    thread_id = waypoint_thread_id(row, refs)
    if not thread_id:
        return None
    timestamp = format_time(parse_time(str(row.get("timestamp") or row.get("created_at") or now_utc())))
    moment = compact_text(str(row.get("moment") or row.get("summary") or row.get("title") or ""), 260)
    if not moment:
        return None
    waypoint_id = str(
        row.get("waypoint_id")
        or stable_digest(moment, thread_id, timestamp, refs, prefix="wp", length=18)
    )
    texture_selection = select_texture_signals([row], consumer="journey", limit=4)
    texture_signals = tuple(
        dict(signal)
        for signal in texture_selection.get("signals") or []
        if isinstance(signal, Mapping)
    )
    texture_labels = [
        f"texture:{signal.get('signal_kind')}"
        for signal in texture_signals
        if signal.get("signal_kind")
    ]
    labels = unique_preserve(
        [
            *(str(value) for value in row.get("labels") or row.get("concepts") or []),
            *texture_labels,
        ]
    )
    raw_frontier_hint = compact_text(row.get("frontier_hint") or "", 220)
    if not raw_frontier_hint:
        raw_frontier_hint = frontier_hint_from_texture_signals(texture_signals)
    return Waypoint(
        waypoint_id=waypoint_id,
        moment=moment,
        thread_id=thread_id,
        timestamp=timestamp,
        source_refs=refs,
        arc=compact_text(row.get("arc") or "unmapped", 40),
        labels=labels,
        frontier_hint=raw_frontier_hint,
        texture_signals=texture_signals,
    )


def waypoint_to_dict(waypoint: Waypoint) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": WAYPOINT_KIND,
        "waypoint_id": waypoint.waypoint_id,
        "moment": waypoint.moment,
        "thread_id": waypoint.thread_id,
        "timestamp": waypoint.timestamp,
        "source_refs": list(waypoint.source_refs),
        "arc": waypoint.arc,
        "labels": list(waypoint.labels),
        "frontier_hint": waypoint.frontier_hint,
    }
    if waypoint.texture_signals:
        payload["texture_signals"] = list(waypoint.texture_signals)
        payload["source_texture_consumption"] = texture_signal_summary(
            waypoint.texture_signals,
            consumer="journey",
        )
    return payload


def journey_to_dict(journey: Journey) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": JOURNEY_KIND,
        "journey_id": journey.journey_id,
        "path_label": journey.path_label,
        "core_inquiry": journey.core_inquiry,
        "waypoints": [waypoint_to_dict(waypoint) for waypoint in journey.waypoints],
        "current_frontier": journey.current_frontier,
        "current_frontier_kind": journey.current_frontier_kind,
        "current_frontier_source_refs": list(journey.current_frontier_source_refs),
        "source_refs": list(journey.source_refs),
        "active_questions": list(journey.active_questions),
        "first_seen": journey.first_seen,
        "last_seen": journey.last_seen,
        "expires_at": journey.expires_at,
        "status": journey.status,
        "feedback_history": list(journey.feedback_history),
        "merged_into": journey.merged_into,
        "truth_boundary": (
            "Journey and current_frontier are navigation candidates; exact claims require "
            "the attached clean-source refs."
        ),
    }


def looks_like_private_payload(value: str) -> bool:
    text = str(value or "")
    return bool(PRIVATE_TOKEN_RE.search(text))


def safe_arc_token(value: object) -> str:
    text = compact_text(str(value or ""), 40)
    if not text or text == "unmapped" or looks_like_private_payload(text):
        return ""
    return text


def safe_structure_label(value: object) -> str:
    text = compact_text(str(value or ""), 80)
    if not text or looks_like_private_payload(text):
        return ""
    lowered = text.casefold()
    if not any(lowered.startswith(prefix) for prefix in SAFE_STRUCTURE_LABEL_PREFIXES):
        return ""
    return text


def safe_resonance_patterns(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    patterns: list[str] = []
    for value in values:
        text = str(value or "")
        if text not in SAFE_RESONANCE_PATTERNS or text in patterns:
            continue
        patterns.append(text)
    return patterns


def journey_mapping(value: Journey | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(value, Journey):
        return journey_to_dict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return None


def content_light_journey_signature(
    journey: Journey | Mapping[str, Any] | None,
    *,
    project_key: str,
) -> dict[str, Any] | None:
    """Return a cross-project-safe structural signature.

    Cross-project resonance must begin with source-free structure. This helper
    deliberately ignores path labels, moments, frontiers, source refs, thread
    ids, and raw project keys so callers cannot accidentally move private
    source text or local paths between projects while looking for a similar
    journey shape.
    """

    row = journey_mapping(journey)
    if not row:
        return None
    waypoints = row.get("waypoints")
    if not isinstance(waypoints, list) or not waypoints:
        return None

    arcs: list[str] = []
    dynamics: list[str] = []
    for waypoint in waypoints[:8]:
        if not isinstance(waypoint, Mapping):
            continue
        arc = safe_arc_token(waypoint.get("arc"))
        if arc:
            arcs.append(arc)
        labels = waypoint.get("labels") or []
        if isinstance(labels, (list, tuple)):
            dynamics.extend(label for label in (safe_structure_label(item) for item in labels) if label)
    dynamics = list(unique_preserve(dynamics, limit=12))
    if not arcs and not dynamics:
        return None

    project_hash = stable_digest(project_key or "unknown-project", prefix="project", length=14)
    signature_id = stable_digest(project_hash, arcs, dynamics, len(waypoints), prefix="jr_sig", length=18)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTENT_LIGHT_SIGNATURE_KIND,
        "signature_id": signature_id,
        "project_hash": project_hash,
        "arc_sequence": arcs,
        "dynamics_labels": dynamics,
        "waypoint_count": len(waypoints),
        "source_free": True,
        "source_boundary": {
            "raw_source_refs_included": False,
            "raw_source_text_included": False,
            "raw_project_key_included": False,
            "local_paths_included": False,
        },
    }


def shared_arc_sequence(current: list[str], candidate: list[str]) -> list[str]:
    shared: list[str] = []
    candidate_index = 0
    for arc in current:
        try:
            found = candidate.index(arc, candidate_index)
        except ValueError:
            continue
        shared.append(arc)
        candidate_index = found + 1
    return shared


def shared_dynamic_labels(current: list[str], candidate: list[str]) -> list[str]:
    candidate_set = set(candidate)
    return [label for label in current if label in candidate_set]


def build_content_light_resonance(
    *,
    current_journey: Journey | Mapping[str, Any] | None,
    candidate_journeys: Iterable[Mapping[str, Any]],
    current_project_key: str,
    min_shared_arcs: int = 2,
) -> dict[str, Any]:
    current_signature = content_light_journey_signature(
        current_journey,
        project_key=current_project_key,
    )
    base_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTENT_LIGHT_RESONANCE_KIND,
        "ok": True,
        "matches": [],
        "claim_boundary": {
            "hypothesis_not_fact": True,
            "not_evidence": True,
            "requires_source_reopen_before_use": True,
        },
        "privacy_boundary": {
            "content_light_only": True,
            "raw_source_refs_shared": False,
            "raw_source_text_shared": False,
            "raw_project_details_shared": False,
        },
        "cannot_claim": [
            "source_text_comparison",
            "same_constraint_still_applies",
            "project_fact",
            "route_should_be_reused",
        ],
    }
    if not current_signature:
        return {**base_payload, "status": "skipped_missing_journey_data"}

    matches: list[dict[str, Any]] = []
    for candidate in candidate_journeys:
        if not isinstance(candidate, Mapping):
            continue
        candidate_signature = content_light_journey_signature(
            candidate.get("journey") if "journey" in candidate else candidate,
            project_key=str(candidate.get("project_key") or candidate.get("project_id") or "unknown-project"),
        )
        if not candidate_signature:
            continue
        if candidate_signature["project_hash"] == current_signature["project_hash"]:
            continue
        shared_arcs = shared_arc_sequence(
            list(current_signature["arc_sequence"]),
            list(candidate_signature["arc_sequence"]),
        )
        shared_dynamics = shared_dynamic_labels(
            list(current_signature["dynamics_labels"]),
            list(candidate_signature["dynamics_labels"]),
        )
        if len(shared_arcs) < min_shared_arcs and not shared_dynamics:
            continue
        match_id = stable_digest(
            current_signature["signature_id"],
            candidate_signature["signature_id"],
            shared_arcs,
            shared_dynamics,
            prefix="jr_res",
            length=18,
        )
        matches.append(
            {
                "resonance_id": match_id,
                "match_kind": "content_light_cross_project_journey_resonance",
                "suggested_use": "source_refresh_cue",
                "hypothesis": (
                    "A source-free Journey shape resembles another project. "
                    "Reopen sources inside the appropriate project before treating any route as evidence."
                ),
                "source_refresh_cue": {
                    "action": "reopen_candidate_project_sources_before_comparison",
                    "reason": "similar_content_light_journey_structure",
                    "permission_required": True,
                },
                "shared_structure": {
                    "arc_sequence": shared_arcs,
                    "dynamics_labels": shared_dynamics,
                },
                "candidate_patterns": safe_resonance_patterns(candidate.get("source_free_patterns") or []),
                "current_signature": current_signature,
                "candidate_signature": candidate_signature,
                "claim_boundary": dict(base_payload["claim_boundary"]),
                "privacy_boundary": dict(base_payload["privacy_boundary"]),
            }
        )

    return {
        **base_payload,
        "status": "hypotheses_available" if matches else "no_content_light_resonance",
        "current_signature": current_signature,
        "matches": matches,
    }


def waypoint_source_refs(
    items: Iterable[Waypoint | Mapping[str, Any]],
    *,
    limit: int = 20,
) -> tuple[dict[str, Any], ...]:
    groups: list[Iterable[Mapping[str, Any]]] = []
    for item in items:
        groups.append(
            item.source_refs
            if isinstance(item, Waypoint)
            else normalize_source_refs(item, require_thread=False, allow_string_ref=True)
        )
    return tuple(merge_source_ref_groups(*groups, limit=limit, require_thread=False))


def compute_expiry(last_seen: str, waypoint_count: int) -> str:
    bonus = min(max(0, int(waypoint_count)) * TTL_BONUS_PER_WAYPOINT_DAYS, MAX_TTL_BONUS_DAYS)
    return format_time(parse_time(last_seen) + timedelta(days=BASE_TTL_DAYS + bonus))


def build_current_frontier(waypoints: Iterable[Waypoint]) -> tuple[str, tuple[dict[str, Any], ...]]:
    ordered = sorted(tuple(waypoints), key=lambda item: parse_time(item.timestamp))
    recent = ordered[-3:]
    refs = waypoint_source_refs(recent, limit=8)
    hint = next((item.frontier_hint for item in reversed(recent) if item.frontier_hint), "")
    if hint:
        return compact_text(hint, 360), refs
    moments = " -> ".join(item.moment for item in recent)
    frontier = (
        f"Continue from the latest source-backed waypoints: {moments}. "
        "Treat this as a resume boundary, not as resolved truth."
    )
    return compact_text(frontier, 360), refs


def inquiry_is_specific(core_inquiry: str) -> bool:
    text = re.sub(r"\s+", " ", core_inquiry).strip().casefold()
    if len(text) < 16:
        return False
    if text in GENERIC_INQUIRIES:
        return False
    tokens = {token for token in re.findall(r"[\w\u4e00-\u9fff]+", text) if len(token) >= 3}
    return len(tokens - GENERIC_INQUIRIES) >= 2


def create_journey(
    *,
    path_label: str,
    core_inquiry: str,
    waypoint_rows: Iterable[Mapping[str, Any]],
    active_questions: Iterable[str] = (),
    min_threads: int = MIN_JOURNEY_THREADS,
) -> JourneyInstantiationResult:
    waypoints = tuple(
        waypoint
        for waypoint in (waypoint_from_mapping(row) for row in waypoint_rows)
        if waypoint is not None
    )
    if len(waypoints) < MIN_JOURNEY_WAYPOINTS:
        return JourneyInstantiationResult(False, "not_enough_source_backed_waypoints")
    thread_count = len({waypoint.thread_id for waypoint in waypoints})
    if thread_count < min_threads:
        return JourneyInstantiationResult(False, "not_enough_distinct_threads")
    if not inquiry_is_specific(core_inquiry):
        return JourneyInstantiationResult(False, "core_inquiry_not_specific")

    ordered = tuple(sorted(waypoints, key=lambda item: parse_time(item.timestamp)))
    source_refs = waypoint_source_refs(ordered)
    current_frontier, frontier_refs = build_current_frontier(ordered)
    first_seen = ordered[0].timestamp
    last_seen = ordered[-1].timestamp
    journey = Journey(
        journey_id=stable_digest(path_label, core_inquiry, [item.waypoint_id for item in ordered], prefix="jr", length=18),
        path_label=compact_text(path_label, 120),
        core_inquiry=compact_text(core_inquiry, 260),
        waypoints=ordered,
        current_frontier=current_frontier,
        current_frontier_kind=FRONTIER_KIND,
        current_frontier_source_refs=frontier_refs,
        source_refs=source_refs,
        active_questions=unique_preserve(active_questions, limit=12),
        first_seen=first_seen,
        last_seen=last_seen,
        expires_at=compute_expiry(last_seen, len(ordered)),
        status="traveling",
    )
    return JourneyInstantiationResult(True, "created", journey)


def refresh_journey_state(journey: Journey, *, now: str | None = None) -> Journey:
    if journey.status in {"arrived", "abandoned"}:
        return journey
    current = parse_time(now or now_utc())
    if current >= parse_time(journey.expires_at):
        return Journey(**{**journey.__dict__, "status": "abandoned"})
    if current - parse_time(journey.last_seen) >= timedelta(days=CAMPED_AFTER_DAYS):
        return Journey(**{**journey.__dict__, "status": "camped"})
    return Journey(**{**journey.__dict__, "status": "traveling"})


def append_waypoint(journey: Journey, waypoint_row: Mapping[str, Any]) -> Journey:
    waypoint = waypoint_from_mapping(waypoint_row)
    if waypoint is None:
        raise ValueError("waypoint must carry source refs, thread id, timestamp, and moment")
    waypoints = tuple([*journey.waypoints, waypoint])
    frontier, frontier_refs = build_current_frontier(waypoints)
    return Journey(
        **{
            **journey.__dict__,
            "waypoints": waypoints,
            "current_frontier": frontier,
            "current_frontier_source_refs": frontier_refs,
            "source_refs": waypoint_source_refs(waypoints),
            "last_seen": waypoint.timestamp,
            "expires_at": compute_expiry(waypoint.timestamp, len(waypoints)),
            "status": "traveling",
        }
    )


def apply_feedback(journey: Journey, feedback: JourneyFeedback) -> Journey:
    if feedback.journey_id != journey.journey_id:
        raise ValueError("feedback journey_id does not match journey")
    event = {
        "action": feedback.action,
        "timestamp": feedback.timestamp,
        "correction": feedback.correction,
        "merge_target": feedback.merge_target,
    }
    history = tuple([*journey.feedback_history, {k: v for k, v in event.items() if v not in {None, ""}}])
    updates: dict[str, Any] = {"feedback_history": history}
    if feedback.action == "correct" and feedback.correction:
        updates["current_frontier"] = compact_text(feedback.correction, 360)
    elif feedback.action == "merge":
        if not feedback.merge_target:
            raise ValueError("merge feedback requires merge_target")
        updates.update({"status": "abandoned", "merged_into": feedback.merge_target})
    elif feedback.action == "abandon":
        updates.update({"status": "abandoned", "expires_at": feedback.timestamp})
    elif feedback.action == "revive":
        updates.update(
            {
                "status": "traveling",
                "expires_at": compute_expiry(feedback.timestamp, len(journey.waypoints)),
            }
        )
    elif feedback.action == "confirm":
        updates["status"] = journey.status
    return Journey(**{**journey.__dict__, **updates})


def mark_arrived(journey: Journey, *, timestamp: str | None = None, note: str = "") -> Journey:
    event = {
        "action": "arrive",
        "timestamp": timestamp or now_utc(),
        "note": compact_text(note, 220),
    }
    return Journey(
        **{
            **journey.__dict__,
            "status": "arrived",
            "feedback_history": tuple([*journey.feedback_history, event]),
        }
    )


def fixture_waypoints() -> list[dict[str, Any]]:
    return [
        {
            "moment": "Knowledge-transfer work raised the continuity-after-change question.",
            "thread_id": "session:journey-a",
            "timestamp": "2026-05-01T00:00:00Z",
            "arc": "unmapped",
            "source_refs": [{"thread_key": "session:journey-a", "message_id": "msg-a"}],
            "labels": ["continuity", "knowledge transfer"],
        },
        {
            "moment": "Architecture work hit compaction loss and source survival concerns.",
            "thread_id": "session:journey-b",
            "timestamp": "2026-05-10T00:00:00Z",
            "arc": "unmapped",
            "source_refs": [{"thread_key": "session:journey-b", "message_id": "msg-b"}],
            "labels": ["compaction", "source refs"],
        },
        {
            "moment": "The path stopped at a source-ref survival boundary.",
            "thread_id": "session:journey-c",
            "timestamp": "2026-05-20T00:00:00Z",
            "arc": "unmapped",
            "frontier_hint": "Resume only after source refs survive compaction at the boundary.",
            "source_refs": [{"thread_key": "session:journey-c", "message_id": "msg-c"}],
            "labels": ["resume boundary", "source refs"],
        },
    ]


def coverage_score(text: str, terms: Iterable[str]) -> tuple[int, list[str]]:
    lowered = text.casefold()
    expected = tuple(terms)
    missing = [term for term in expected if term.casefold() not in lowered]
    return len(expected) - len(missing), missing


def run_replay_fixture_smoke() -> dict[str, Any]:
    expected_terms = ("source refs", "compaction", "boundary", "resume")
    result = create_journey(
        path_label="continuity after change",
        core_inquiry="How can continuity survive change and compaction without false memory claims?",
        waypoint_rows=fixture_waypoints(),
        active_questions=["what survives compaction?"],
    )
    if not result.created or result.journey is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": REPLAY_SMOKE_KIND,
            "ok": False,
            "status": result.reason,
        }
    journey = result.journey
    journey_text = " ".join(
        [
            journey.path_label,
            journey.core_inquiry,
            journey.status,
            journey.current_frontier,
        ]
    )
    plain_summary = "The user cares about continuity and memory over time."
    journey_hits, journey_missing = coverage_score(journey_text, expected_terms)
    summary_hits, summary_missing = coverage_score(plain_summary, expected_terms)
    better_than_summary = journey_hits > summary_hits
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPLAY_SMOKE_KIND,
        "ok": better_than_summary,
        "status": "sufficient" if better_than_summary else "not_better_than_baseline",
        "metrics": {
            "expected_term_count": len(expected_terms),
            "journey_frontier_hits": journey_hits,
            "plain_summary_hits": summary_hits,
            "journey_better_than_summary": better_than_summary,
        },
        "missing": {
            "journey": journey_missing,
            "plain_summary": summary_missing,
        },
        "journey": journey_to_dict(journey),
        "baseline": {
            "kind": "plain_summary_baseline",
            "text_sha1": stable_digest(plain_summary, prefix="txt", length=16),
        },
        "cannot_claim": [
            "live_model_behavioral_equivalence",
            "private_real_history_journey_quality",
            "theme_emergence_runtime_quality",
            "predictive_replay_quality",
        ],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Journey Tracking deterministic helpers.")
    parser.add_argument(
        "--fixture-smoke",
        action="store_true",
        help="Run the source-backed journey replay fixture smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path, help="Optional output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_replay_fixture_smoke() if args.fixture_smoke else {"ok": True, "kind": "journey_tracking"}
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
