#!/usr/bin/env python3
"""No-write live Journey instantiation and foreground hint timing helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.journey import tracking

LIVE_REPLAY_KIND = "aippocampus_live_journey_time_sliced_replay"
PUBLIC_TIME_SLICED_REPLAY_KIND = "aippocampus_public_journey_time_sliced_replay"
FOREGROUND_HINT_KIND = "aippocampus_foreground_journey_hint"
LIVE_ROW_KINDS = {"theme_candidate", "question_candidate", "frontier_marker"}


def _tokens(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[\w\u4e00-\u9fff]+", str(text or ""))
        if len(token) >= 3
    }


def _row_time(row: Mapping[str, Any]) -> str:
    return str(row.get("timestamp") or row.get("created_at") or "")


def _row_is_visible_at(row: Mapping[str, Any], *, as_of: str | None) -> bool:
    if not as_of:
        return True
    return tracking.parse_time(_row_time(row)) <= tracking.parse_time(as_of)


def _live_row_kind(row: Mapping[str, Any]) -> str:
    return str(row.get("kind") or row.get("row_kind") or "").strip()


def _live_row_source_refs(row: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    return tracking.normalize_source_refs(
        row.get("source_refs") or row.get("source_ref"),
        thread_id=str(row.get("thread_id") or row.get("thread_key") or ""),
    )


def live_navigation_row_to_waypoint(row: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = _live_row_kind(row)
    if kind not in LIVE_ROW_KINDS:
        return None
    refs = _live_row_source_refs(row)
    if not refs:
        return None
    moment = compact_text(
        str(
            row.get("moment")
            or row.get("summary")
            or row.get("theme")
            or row.get("question")
            or row.get("frontier")
            or row.get("title")
            or ""
        ),
        260,
    )
    if not moment:
        return None
    thread_id = str(row.get("thread_id") or row.get("thread_key") or refs[0].get("thread_key") or refs[0].get("thread_id") or "")
    if not thread_id:
        return None
    labels = [kind]
    if row.get("theme"):
        labels.append(f"theme:{compact_text(str(row.get('theme') or ''), 60)}")
    if row.get("question"):
        labels.append("question_signal")
    return {
        "moment": moment,
        "thread_id": thread_id,
        "timestamp": _row_time(row),
        "source_refs": refs,
        "arc": row.get("arc") or "unmapped",
        "labels": labels,
        "frontier_hint": compact_text(row.get("frontier_hint") or row.get("frontier") or "", 220),
    }


def create_journey_from_live_navigation_rows(
    *,
    path_label: str,
    core_inquiry: str,
    rows: Iterable[Mapping[str, Any]],
    as_of: str | None = None,
    min_threads: int = tracking.MIN_JOURNEY_THREADS,
) -> dict[str, Any]:
    row_list = [row for row in rows if isinstance(row, Mapping)]
    visible_rows = [
        row
        for row in row_list
        if _live_row_kind(row) in LIVE_ROW_KINDS and _row_is_visible_at(row, as_of=as_of)
    ]
    future_excluded = [
        row
        for row in row_list
        if _live_row_kind(row) in LIVE_ROW_KINDS and not _row_is_visible_at(row, as_of=as_of)
    ]
    waypoint_rows = [
        waypoint
        for waypoint in (live_navigation_row_to_waypoint(row) for row in visible_rows)
        if waypoint is not None
    ]
    active_questions = [
        str(row.get("question"))
        for row in visible_rows
        if _live_row_kind(row) == "question_candidate" and row.get("question")
    ]
    result = tracking.create_journey(
        path_label=path_label,
        core_inquiry=core_inquiry,
        waypoint_rows=waypoint_rows,
        active_questions=active_questions,
        min_threads=min_threads,
    )
    journey_payload = tracking.journey_to_dict(result.journey) if result.journey else None
    return {
        "created": result.created,
        "reason": result.reason,
        "journey": journey_payload,
        "metrics": {
            "visible_live_row_count": len(visible_rows),
            "included_live_row_count": len(waypoint_rows),
            "future_row_excluded_count": len(future_excluded),
            "source_backed_waypoint_count": len(waypoint_rows),
            "distinct_thread_count": len(
                {
                    str(row.get("thread_id") or row.get("thread_key") or "")
                    for row in waypoint_rows
                }
            ),
        },
    }


def _route_handle(journey_row: Mapping[str, Any]) -> str:
    refs = journey_row.get("source_refs") or []
    return "journey_route:" + tracking.stable_digest(
        journey_row.get("journey_id"),
        [tracking.source_ref_key(ref) for ref in refs if isinstance(ref, Mapping)],
        prefix="route",
        length=18,
    ).removeprefix("route_")


def _prompt_overlaps_journey(prompt: str, journey_row: Mapping[str, Any]) -> bool:
    prompt_terms = _tokens(prompt)
    if not prompt_terms:
        return False
    journey_text = " ".join(
        str(journey_row.get(key) or "")
        for key in ("path_label", "core_inquiry", "current_frontier", "status")
    )
    journey_text += " " + " ".join(str(item) for item in journey_row.get("active_questions") or [])
    return bool(prompt_terms & _tokens(journey_text))


def build_foreground_journey_hint(
    *,
    journey: Mapping[str, Any] | tracking.Journey | None,
    prompt: str,
    source_visible: bool = False,
    high_risk_claim: bool = False,
) -> dict[str, Any]:
    journey_row = tracking.journey_to_dict(journey) if isinstance(journey, tracking.Journey) else dict(journey or {})
    base = {
        "schema_version": tracking.SCHEMA_VERSION,
        "kind": FOREGROUND_HINT_KIND,
        "private_route_handle": _route_handle(journey_row) if journey_row else "",
        "claim_boundary": {
            "journey_hint_is_navigation": True,
            "not_source_evidence": True,
            "not_user_or_persona_model": True,
            "source_reopen_required_for_exact_claims": True,
        },
    }
    if not journey_row:
        return {**base, "decision": "backstage_only", "reason": "missing_journey"}
    if journey_row.get("status") in {"arrived", "abandoned"}:
        return {**base, "decision": "backstage_only", "reason": "terminal_journey_status"}
    if not journey_row.get("source_refs"):
        return {**base, "decision": "source_reopen_required", "reason": "missing_source_refs"}
    if high_risk_claim:
        return {**base, "decision": "source_reopen_required", "reason": "high_risk_claim"}
    if source_visible:
        return {**base, "decision": "silent", "reason": "source_or_equivalent_hint_already_visible"}
    if not _prompt_overlaps_journey(prompt, journey_row):
        return {**base, "decision": "backstage_only", "reason": "prompt_not_journey_relevant"}
    return {
        **base,
        "decision": "agent_visible_hint",
        "reason": "relevant_camped_or_traveling_journey",
        "agent_visible": {
            "visibility": "gentle_nudge",
            "path_label": compact_text(journey_row.get("path_label") or "", 100),
            "status": journey_row.get("status"),
            "frontier": compact_text(journey_row.get("current_frontier") or "", 280),
            "source_ref_count": len(journey_row.get("source_refs") or []),
            "suggested_use": "mention only as a route cue; reopen source before exact claims",
            "truth_boundary": (
                "Journey hints are navigation candidates, not source evidence or user/persona truth."
            ),
        },
    }


def fixture_live_navigation_rows() -> list[dict[str, Any]]:
    return [
        {
            "kind": "theme_candidate",
            "theme": "continuity after change",
            "moment": "Theme recurred around continuity surviving major context shifts.",
            "thread_id": "session:live-a",
            "timestamp": "2026-06-01T00:00:00Z",
            "source_refs": [{"thread_key": "session:live-a", "message_id": "msg-live-a"}],
            "frontier_hint": "Follow the continuity-after-change route only with source refs attached.",
        },
        {
            "kind": "question_candidate",
            "question": "How can continuity survive compaction without becoming false memory?",
            "moment": "Question row narrowed the route to compaction and source survival.",
            "thread_id": "session:live-b",
            "timestamp": "2026-06-02T00:00:00Z",
            "source_refs": [{"thread_key": "session:live-b", "message_id": "msg-live-b"}],
        },
        {
            "kind": "frontier_marker",
            "frontier": "Resume at the boundary where source refs survive compaction.",
            "moment": "Frontier marker paused the route at source-ref survival.",
            "thread_id": "session:live-c",
            "timestamp": "2026-06-03T00:00:00Z",
            "source_refs": [{"thread_key": "session:live-c", "message_id": "msg-live-c"}],
            "frontier_hint": "Resume only after reopening the attached source refs.",
        },
        {
            "kind": "theme_candidate",
            "theme": "FUTURE_LEAK_SENTINEL",
            "moment": "FUTURE_LEAK_SENTINEL should not appear before the replay horizon.",
            "thread_id": "session:live-future",
            "timestamp": "2026-06-05T00:00:00Z",
            "source_refs": [
                {
                    "thread_key": "session:live-future",
                    "message_id": "FUTURE_LEAK_SENTINEL",
                }
            ],
        },
    ]


def run_live_journey_time_sliced_replay_fixture(
    *,
    as_of: str = "2026-06-03T23:59:00Z",
) -> dict[str, Any]:
    rows = fixture_live_navigation_rows()
    result = create_journey_from_live_navigation_rows(
        path_label="continuity after change",
        core_inquiry="How can continuity survive compaction without becoming false memory?",
        rows=rows,
        as_of=as_of,
    )
    journey_row = result.get("journey") or {}
    encoded_journey = json.dumps(journey_row, ensure_ascii=False, sort_keys=True)
    future_leakage_detected = "FUTURE_LEAK_SENTINEL" in encoded_journey
    positive = build_foreground_journey_hint(
        journey=journey_row,
        prompt="Can we resume the continuity route after compaction?",
    )
    source_visible_negative = build_foreground_journey_hint(
        journey=journey_row,
        prompt="Can we resume the continuity route after compaction?",
        source_visible=True,
    )
    unrelated_negative = build_foreground_journey_hint(
        journey=journey_row,
        prompt="Please format this unrelated spreadsheet.",
    )
    high_risk_negative = build_foreground_journey_hint(
        journey=journey_row,
        prompt="State the exact old claim from the continuity route.",
        high_risk_claim=True,
    )
    metrics = {
        **dict(result.get("metrics") or {}),
        "future_leakage_detected": future_leakage_detected,
        "foreground_positive_visible": positive.get("decision") == "agent_visible_hint",
        "foreground_negative_control_count": sum(
            1
            for item in (source_visible_negative, unrelated_negative, high_risk_negative)
            if item.get("decision") != "agent_visible_hint"
        ),
    }
    ok = bool(result.get("created")) and not future_leakage_detected and metrics["foreground_positive_visible"]
    return {
        "schema_version": tracking.SCHEMA_VERSION,
        "kind": LIVE_REPLAY_KIND,
        "ok": ok,
        "status": "journey_candidate_created" if ok else str(result.get("reason") or "failed"),
        "as_of": as_of,
        "metrics": metrics,
        "journey": journey_row,
        "foreground_hint_replay": {
            "positive": positive,
            "source_visible_negative": source_visible_negative,
            "unrelated_negative": unrelated_negative,
            "high_risk_negative": high_risk_negative,
        },
        "privacy_boundary": {
            "raw_private_rows_emitted": False,
            "future_rows_emitted": False,
            "agent_visible_source_refs_emitted": False,
            "private_route_handles_are_hashed": True,
        },
        "cannot_claim": [
            "private_real_history_journey_quality",
            "default_foreground_journey_hint_quality",
            "journey_as_user_or_persona_truth",
            "source_evidence_without_reopen",
        ],
    }


def fixture_public_time_sliced_journey_replay_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "public_vcs_workaround_supersession",
            "source_family": "public_vcs_hard_event_window",
            "path_label": "workaround supersession route",
            "core_inquiry": (
                "When should a workaround route be reopened after a later source changes?"
            ),
            "as_of": "2026-06-03T23:59:00Z",
            "relevant_prompt": "Should we reopen the workaround supersession route?",
            "unrelated_prompt": "Please summarize this unrelated formatting request.",
            "rows": [
                {
                    "kind": "theme_candidate",
                    "theme": "workaround supersession",
                    "moment": (
                        "PUBLIC_RAW_ROW_SENTINEL workaround stayed local while the "
                        "upstream route was still failing."
                    ),
                    "thread_id": "public-journey-310-a",
                    "timestamp": "2026-06-01T00:00:00Z",
                    "source_refs": [
                        {
                            "thread_key": "public-journey-310-a",
                            "message_id": "public-msg-310-a",
                        }
                    ],
                    "frontier_hint": "Treat the workaround as local until later source changes.",
                },
                {
                    "kind": "question_candidate",
                    "question": "When does the old workaround stop being the right route?",
                    "moment": (
                        "PUBLIC_RAW_ROW_SENTINEL question narrowed the replay to "
                        "stale workaround currentness."
                    ),
                    "thread_id": "public-journey-310-b",
                    "timestamp": "2026-06-02T00:00:00Z",
                    "source_refs": [
                        {
                            "thread_key": "public-journey-310-b",
                            "message_id": "public-msg-310-b",
                        }
                    ],
                },
                {
                    "kind": "frontier_marker",
                    "frontier": "Reopen source before reviving the workaround route.",
                    "moment": (
                        "PUBLIC_RAW_ROW_SENTINEL frontier paused at source reopen, "
                        "not foreground warning."
                    ),
                    "thread_id": "public-journey-310-c",
                    "timestamp": "2026-06-03T00:00:00Z",
                    "source_refs": [
                        {
                            "thread_key": "public-journey-310-c",
                            "message_id": "public-msg-310-c",
                        }
                    ],
                },
                {
                    "kind": "theme_candidate",
                    "theme": "FUTURE_PUBLIC_JOURNEY_SENTINEL",
                    "moment": (
                        "FUTURE_PUBLIC_JOURNEY_SENTINEL later reland outcome must "
                        "not shape the earlier replay."
                    ),
                    "thread_id": "public-journey-310-future",
                    "timestamp": "2026-06-05T00:00:00Z",
                    "source_refs": [
                        {
                            "thread_key": "public-journey-310-future",
                            "message_id": "public-msg-310-future",
                        }
                    ],
                },
            ],
        }
    ]


def _public_replay_case_result(case: Mapping[str, Any]) -> dict[str, Any]:
    result = create_journey_from_live_navigation_rows(
        path_label=str(case.get("path_label") or ""),
        core_inquiry=str(case.get("core_inquiry") or ""),
        rows=case.get("rows") or [],
        as_of=str(case.get("as_of") or ""),
    )
    journey_row = result.get("journey") or {}
    material = json.dumps(journey_row, ensure_ascii=False, sort_keys=True)
    future_leakage = "FUTURE_PUBLIC_JOURNEY_SENTINEL" in material
    positive = build_foreground_journey_hint(
        journey=journey_row,
        prompt=str(case.get("relevant_prompt") or ""),
    )
    source_visible = build_foreground_journey_hint(
        journey=journey_row,
        prompt=str(case.get("relevant_prompt") or ""),
        source_visible=True,
    )
    unrelated = build_foreground_journey_hint(
        journey=journey_row,
        prompt=str(case.get("unrelated_prompt") or ""),
    )
    status = "journey_candidate_created" if result.get("created") and not future_leakage else str(
        result.get("reason") or "failed"
    )
    return {
        "case_id": compact_text(case.get("case_id") or "", 80),
        "source_family": compact_text(case.get("source_family") or "", 80),
        "status": status,
        "as_of": str(case.get("as_of") or ""),
        "metrics": {
            "visible_live_row_count": int((result.get("metrics") or {}).get("visible_live_row_count") or 0),
            "included_live_row_count": int((result.get("metrics") or {}).get("included_live_row_count") or 0),
            "future_row_excluded_count": int((result.get("metrics") or {}).get("future_row_excluded_count") or 0),
            "source_backed_waypoint_count": int(
                (result.get("metrics") or {}).get("source_backed_waypoint_count") or 0
            ),
            "future_leakage_detected": future_leakage,
        },
        "hint_timing": {
            "relevant_prompt": positive.get("decision"),
            "source_visible_control": source_visible.get("decision"),
            "unrelated_prompt_control": unrelated.get("decision"),
        },
        "claim_boundary": {
            "journey_hint_is_navigation": True,
            "not_source_evidence": True,
            "source_reopen_required_for_claims": True,
            "public_fixture_not_live_quality": True,
        },
    }


def build_public_time_sliced_journey_replay_report(
    cases: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a public-safe #310 replay report without serializing raw rows."""

    case_results = [
        _public_replay_case_result(case)
        for case in (cases if cases is not None else fixture_public_time_sliced_journey_replay_cases())
    ]
    future_excluded = sum(
        int((case.get("metrics") or {}).get("future_row_excluded_count") or 0)
        for case in case_results
    )
    positive_hint_count = sum(
        1
        for case in case_results
        if (case.get("hint_timing") or {}).get("relevant_prompt") == "agent_visible_hint"
    )
    negative_control_suppressed_count = sum(
        1
        for case in case_results
        for key in ("source_visible_control", "unrelated_prompt_control")
        if (case.get("hint_timing") or {}).get(key) != "agent_visible_hint"
    )
    future_leakage_count = sum(
        1
        for case in case_results
        if bool((case.get("metrics") or {}).get("future_leakage_detected"))
    )
    journey_created_count = sum(
        1 for case in case_results if case.get("status") == "journey_candidate_created"
    )
    ok = bool(case_results) and journey_created_count == len(case_results) and future_leakage_count == 0
    return {
        "schema_version": tracking.SCHEMA_VERSION,
        "kind": PUBLIC_TIME_SLICED_REPLAY_KIND,
        "ok": ok,
        "fixture": "public_replayable_time_sliced_journey_rows",
        "cases": case_results,
        "metrics": {
            "case_count": len(case_results),
            "journey_created_count": journey_created_count,
            "future_row_excluded_count": future_excluded,
            "positive_hint_count": positive_hint_count,
            "negative_control_suppressed_count": negative_control_suppressed_count,
            "future_leakage_count": future_leakage_count,
        },
        "issue_readouts": {
            "github_310": "public_time_sliced_replay_fixture",
            "closeout_eligible": False,
        },
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "source_refs_emitted": False,
            "private_route_handles_emitted": False,
            "future_rows_emitted": False,
        },
        "cannot_claim": [
            "private_real_history_journey_quality",
            "default_foreground_journey_hint_quality",
            "live_host_timing_quality",
            "user_visible_recall_lift",
            "journey_as_user_or_persona_truth",
            "source_evidence_without_reopen",
        ],
    }
