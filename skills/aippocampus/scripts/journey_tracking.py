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

from aippocampuslib import compact_text, now_utc

SCHEMA_VERSION = 1
JOURNEY_KIND = "aippocampus_journey"
WAYPOINT_KIND = "journey_waypoint"
FRONTIER_KIND = "journey_current_frontier"
REPLAY_SMOKE_KIND = "aippocampus_journey_replay_fixture_smoke"

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


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(ref.get("source_id") or ref.get("source_line") or ref.get("line") or ""),
    )


def normalize_source_refs(value: object, *, thread_id: str | None = None) -> tuple[dict[str, Any], ...]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    elif isinstance(value, str) and value.strip():
        raw_items = [{"source_ref": value.strip()}]
    else:
        raw_items = []

    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        ref = dict(item)
        if thread_id and not ref.get("thread_key") and not ref.get("thread_id"):
            ref["thread_key"] = thread_id
        key = source_ref_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in ref.items() if v not in {None, ""}})
    return tuple(refs)


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


def waypoint_from_mapping(row: Mapping[str, Any]) -> Waypoint | None:
    refs = normalize_source_refs(row.get("source_refs") or row.get("source_ref"), thread_id=str(row.get("thread_id") or row.get("thread_key") or ""))
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
    labels = unique_preserve(str(value) for value in row.get("labels") or row.get("concepts") or [])
    return Waypoint(
        waypoint_id=waypoint_id,
        moment=moment,
        thread_id=thread_id,
        timestamp=timestamp,
        source_refs=refs,
        arc=compact_text(row.get("arc") or "unmapped", 40),
        labels=labels,
        frontier_hint=compact_text(row.get("frontier_hint") or "", 220),
    )


def waypoint_to_dict(waypoint: Waypoint) -> dict[str, Any]:
    return {
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


def merge_source_refs(items: Iterable[Waypoint | Mapping[str, Any]], *, limit: int = 20) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        item_refs = item.source_refs if isinstance(item, Waypoint) else normalize_source_refs(item)
        for ref in item_refs:
            key = source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
            if len(refs) >= limit:
                return tuple(refs)
    return tuple(refs)


def compute_expiry(last_seen: str, waypoint_count: int) -> str:
    bonus = min(max(0, int(waypoint_count)) * TTL_BONUS_PER_WAYPOINT_DAYS, MAX_TTL_BONUS_DAYS)
    return format_time(parse_time(last_seen) + timedelta(days=BASE_TTL_DAYS + bonus))


def build_current_frontier(waypoints: Iterable[Waypoint]) -> tuple[str, tuple[dict[str, Any], ...]]:
    ordered = sorted(tuple(waypoints), key=lambda item: parse_time(item.timestamp))
    recent = ordered[-3:]
    refs = merge_source_refs(recent, limit=8)
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
    source_refs = merge_source_refs(ordered)
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
            "source_refs": merge_source_refs(waypoints),
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
