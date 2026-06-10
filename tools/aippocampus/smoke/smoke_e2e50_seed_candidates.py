#!/usr/bin/env python3
"""Sanitized candidate-seed scanner for #279 E2E50 benchmark design.

This is not the E2E50 behavior benchmark runner. It only finds promising
private/local seed candidates for later human annotation. Output is hash/count
only: no clean-source text, rollout paths, local thread ids, or raw refs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.registry.store import registry_paths  # noqa: E402

SCHEMA_VERSION = 1
SMOKE_KIND = "aippocampus_e2e50_seed_candidate_scan"
PRIVACY_BOUNDARY = "hash_count_only_no_text_no_paths_no_ids_no_raw_refs"

DEFAULT_MIN_TURNS = 45
DEFAULT_MAX_TURNS = 70
DEFAULT_EARLY_TURNS = 15
DEFAULT_LATER_START_TURN = 40
DEFAULT_MAX_CANDIDATES = 12
DEFAULT_MIN_RETAINED_CASES = 20
DEFAULT_MIN_NEGATIVE_CONTROLS = 1

ANNOTATION_CATEGORIES = (
    "gold",
    "calibration",
    "negative_control",
    "source_visible_no_op",
    "duplicate",
    "rejected",
    "blocker",
    "unknown",
)
RETAINED_ANNOTATION_CATEGORIES = {
    "gold",
    "calibration",
    "negative_control",
    "source_visible_no_op",
}
ANNOTATION_LABEL_MAP = {
    "gold": "gold",
    "gold_seed": "gold",
    "gold_seed_candidate": "gold",
    "calibration": "calibration",
    "calibration_seed": "calibration",
    "weak_seed": "calibration",
    "negative": "negative_control",
    "negative_control": "negative_control",
    "no_remember_negative": "negative_control",
    "source_visible": "source_visible_no_op",
    "source_visible_candidate": "source_visible_no_op",
    "source_visible_no_op": "source_visible_no_op",
    "source-visible/no-op": "source_visible_no_op",
    "duplicate": "duplicate",
    "reject_duplicate": "duplicate",
    "duplicate_candidate": "duplicate",
    "reject": "rejected",
    "rejected": "rejected",
    "rejected_candidate": "rejected",
    "blocker": "blocker",
    "blocked": "blocker",
}
SAFE_REVIEW_STATUS_TOKENS = {
    "all_candidates_locally_reopened_and_agent_annotated",
    "local_annotation_summary",
    "manual_annotation_incomplete",
    "private_annotation_blocked",
    "private_annotation_retained",
}

BINDING_TERMS = (
    "do not",
    "don't",
    "never",
    "must not",
    "avoid",
    "forbidden",
    "known-bad",
    "不要",
    "别",
    "禁止",
    "不能",
)
REJECTED_ROUTE_TERMS = (
    "rejected route",
    "known-bad route",
    "bad route",
    "failed tests",
    "failed test",
    "do not repeat",
    "fallback",
    "失败",
    "不要再",
    "别再",
    "回退",
)
TEMPORARY_TERMS = (
    "temporary",
    "temporarily",
    "for now",
    "one-off",
    "briefly worried",
    "worry",
    "concern",
    "临时",
    "暂时",
    "担心",
)
SUPERSEDED_TERMS = (
    "superseded",
    "replaced by",
    "instead",
    "new rule",
    "current rule",
    "no longer",
    "改为",
    "替代",
    "取代",
)
BEHAVIOR_EVENT_KINDS = {
    "tool_call_failed",
    "test_failed",
    "command_failed",
    "apply_patch_failed",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: object, *, length: int = 16) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:length]


def list_value(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path | None) -> tuple[list[dict[str, Any]], int]:
    if path is None or not path.is_file():
        return [], 0
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                bad_rows += 1
                continue
            if isinstance(item, dict):
                rows.append(item)
            else:
                bad_rows += 1
    return rows, bad_rows


def registry_entry_paths(entry: dict[str, Any]) -> tuple[Path | None, Path | None]:
    paths = dict_value(entry.get("paths"))
    messages = paths.get("clean_source_messages_jsonl")
    events = paths.get("clean_source_events_jsonl")
    return (
        Path(str(messages)) if messages else None,
        Path(str(events)) if events else None,
    )


def turn_index(row: dict[str, Any]) -> int:
    try:
        return int(row.get("turn_index") or row.get("clean_ordinal") or 0)
    except (TypeError, ValueError):
        return 0


def row_text(row: dict[str, Any]) -> str:
    return str(row.get("text") or row.get("summary") or row.get("event_text") or "")


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    low = text.casefold()
    return any(term.casefold() in low for term in terms)


def signal_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        text = row_text(row)
        if contains_any(text, BINDING_TERMS):
            counts["binding_constraint"] += 1
        if contains_any(text, REJECTED_ROUTE_TERMS):
            counts["rejected_route"] += 1
        if contains_any(text, TEMPORARY_TERMS):
            counts["temporary_concern"] += 1
        if contains_any(text, SUPERSEDED_TERMS):
            counts["superseded_constraint"] += 1
    return {key: counts.get(key, 0) for key in sorted(counts)}


def behavior_event_is_candidate(event: dict[str, Any]) -> bool:
    hard_kind = str(event.get("hard_event_kind") or event.get("event_kind") or "").casefold()
    status = str(event.get("status") or "").casefold()
    command_class = str(event.get("command_class") or "").casefold()
    return (
        hard_kind in BEHAVIOR_EVENT_KINDS
        or status == "failed"
        or bool(event.get("failure_family"))
        or (command_class == "test" and status in {"failed", "error", ""})
        or bool(event.get("behavior_backed")) and bool(event.get("failure_family"))
    )


def compaction_evidence(events: list[dict[str, Any]], messages: list[dict[str, Any]]) -> dict[str, Any]:
    hook_counts: Counter[str] = Counter()
    compact_event_count = 0
    for event in events:
        hook = str(event.get("hook_stage") or event.get("hook") or "")
        if hook in {"PreCompact", "PostCompact"}:
            hook_counts[hook] += 1
        joined = " ".join(
            str(event.get(key) or "")
            for key in ("event_kind", "hard_event_kind", "hook_stage", "type")
        ).casefold()
        if "compact" in joined:
            compact_event_count += 1
    compact_message_marker_count = sum(
        1 for row in messages if "compact" in row_text(row).casefold()
    )
    observed = bool(
        hook_counts.get("PreCompact")
        or hook_counts.get("PostCompact")
        or compact_event_count
        or compact_message_marker_count
    )
    return {
        "observed": observed,
        "pre_compact_event_count": hook_counts.get("PreCompact", 0),
        "post_compact_event_count": hook_counts.get("PostCompact", 0),
        "compact_event_marker_count": compact_event_count,
        "compact_message_marker_count": compact_message_marker_count,
    }


def source_hashes(rows: list[dict[str, Any]], events: list[dict[str, Any]], *, limit: int = 6) -> list[str]:
    values: list[str] = []
    for row in rows:
        values.append(
            "|".join(
                str(row.get(key) or "")
                for key in ("message_id", "turn_id", "source_id", "source_line", "line")
            )
        )
    for event in events:
        values.append(
            "|".join(
                str(event.get(key) or "")
                for key in ("event_id", "source_ref", "observation_sha256")
            )
        )
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value.strip("|"):
            continue
        digest = "sha256:" + stable_hash(value, length=20)
        if digest in seen:
            continue
        seen.add(digest)
        out.append(digest)
        if len(out) >= limit:
            break
    return out


def case_family_guesses(
    early_counts: dict[str, int],
    later_counts: dict[str, int],
    behavior_count: int,
) -> list[str]:
    guesses: list[str] = []
    if early_counts.get("binding_constraint", 0) > 0:
        guesses.append("binding_constraint_survival")
    if early_counts.get("rejected_route", 0) > 0 or behavior_count > 0:
        guesses.append("behavior_backed_rejected_route")
    if early_counts.get("temporary_concern", 0) > 0 and sum(later_counts.values()) == 0:
        guesses.append("transient_concern_extinction")
    if early_counts.get("superseded_constraint", 0) > 0:
        guesses.append("superseded_constraint_handling")
    if sum(early_counts.values()) > 0 and sum(later_counts.values()) == 0:
        guesses.append("same_topic_drift_trap")
    return guesses


def annotation_category(label: object) -> str:
    key = str(label or "").strip().casefold().replace("-", "_").replace("/", "_")
    if key == "source_visible_no_op":
        return "source_visible_no_op"
    return ANNOTATION_LABEL_MAP.get(key, "unknown")


def annotation_blocker_class(category: str, reason: object) -> str:
    if category in {"gold", "calibration"}:
        return "retained_candidate"
    if category == "negative_control":
        return "negative_control"
    if category == "source_visible_no_op":
        return "source_visible_no_op"
    if category == "duplicate":
        return "duplicate_candidate"
    text = str(reason or "").casefold()
    if "subagent" in text or "goal_context" in text or "issue_intake" in text:
        return "subagent_or_goal_context_noise"
    if "duplicate" in text:
        return "duplicate_candidate"
    if "source_visible" in text or "browser_report" in text:
        return "source_visible_no_op"
    if "high_later_remention" in text or "rementioned" in text or "remention" in text:
        return "high_later_remention"
    if "conceptual" in text or "domain_drift" in text:
        return "conceptual_drift"
    if "staging" in text or "quality_iteration" in text:
        return "quality_iteration_staging_risk"
    return "other_rejection_or_blocker"


def safe_status_token(value: object, default: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "").strip())[:80].strip("_")
    return token if token in SAFE_REVIEW_STATUS_TOKENS else default


def summarize_annotation_pack(
    annotation: dict[str, Any],
    *,
    min_retained_cases: int = DEFAULT_MIN_RETAINED_CASES,
    min_negative_controls: int = DEFAULT_MIN_NEGATIVE_CONTROLS,
) -> dict[str, Any]:
    """Summarize local/manual E2E50 annotation without exposing row material.

    The input may live in ignored private-history folders. Only aggregate
    counts leave this function; case hashes, source hashes, reasons, thread ids,
    and raw refs are deliberately not copied into the output.
    """

    category_counts: Counter[str] = Counter({category: 0 for category in ANNOTATION_CATEGORIES})
    blocker_counts: Counter[str] = Counter()
    annotations = [row for row in list_value(annotation.get("annotations")) if isinstance(row, dict)]
    for row in annotations:
        category = annotation_category(row.get("label") or row.get("annotation_category"))
        category_counts[category] += 1
        blocker_counts[annotation_blocker_class(category, row.get("reason") or row.get("blocker_class"))] += 1
    retained_count = sum(category_counts[category] for category in RETAINED_ANNOTATION_CATEGORIES)
    behavior_seed_count = category_counts["gold"] + category_counts["calibration"]
    negative_control_count = category_counts["negative_control"]
    retained_shortfall = max(0, min_retained_cases - retained_count)
    negative_shortfall = max(0, min_negative_controls - negative_control_count)
    status = (
        "private_annotation_retained"
        if retained_shortfall == 0 and negative_shortfall == 0
        else "private_annotation_blocked"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_e2e50_private_annotation_summary",
        "created_at": now_utc(),
        "status": status,
        "privacy": PRIVACY_BOUNDARY,
        "review_status": safe_status_token(
            annotation.get("review_status"),
            "local_annotation_summary",
        ),
        "private_text_exported": bool(annotation.get("private_text_exported") or False),
        "reviewed_candidate_count": len(annotations),
        "retained_case_count": retained_count,
        "behavior_seed_count": behavior_seed_count,
        "annotation_category_counts": {
            category: category_counts.get(category, 0) for category in ANNOTATION_CATEGORIES
        },
        "blocker_class_counts": dict(sorted(blocker_counts.items())),
        "blocker_status": {
            "min_retained_cases": min_retained_cases,
            "retained_case_shortfall": retained_shortfall,
            "min_negative_controls": min_negative_controls,
            "negative_control_shortfall": negative_shortfall,
        },
        "can_claim": [
            "private_local_e2e50_annotation_reviewed_with_sanitized_category_counts"
        ],
        "cannot_claim": [
            "private_history_behavior_lift",
            "completed_private_history_20_case_pack"
            if retained_shortfall
            else "private_history_behavior_lift_from_seed_pack_alone",
            "completed_50_case_e2e50_sample",
            "representative_e2e50_sample_quality",
            "live_host_behavior_lift",
        ],
    }


def summarize_annotation_file(
    path: Path,
    *,
    min_retained_cases: int = DEFAULT_MIN_RETAINED_CASES,
    min_negative_controls: int = DEFAULT_MIN_NEGATIVE_CONTROLS,
) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return summarize_annotation_pack(
        dict(data) if isinstance(data, dict) else {},
        min_retained_cases=min_retained_cases,
        min_negative_controls=min_negative_controls,
    )


def reviewer_checklist_for(guesses: list[str]) -> list[str]:
    checklist = [
        "confirm compaction boundary evidence independently",
        "reopen hashed source refs before annotating gold behavior",
        "mark whether the early signal is binding, temporary, superseded, or scope-limited",
        "verify the later ordinary task does not explicitly restate the signal",
    ]
    if "behavior_backed_rejected_route" in guesses:
        checklist.append("prefer behavior-event evidence over assistant narrative")
    if "transient_concern_extinction" in guesses:
        checklist.append("check that the concern should expire instead of becoming durable preference")
    return checklist


def scan_entry(
    entry: dict[str, Any],
    *,
    min_turns: int,
    max_turns: int,
    early_turns: int,
    later_start_turn: int,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    messages_path, events_path = registry_entry_paths(entry)
    messages, bad_message_rows = read_jsonl(messages_path)
    events, bad_event_rows = read_jsonl(events_path)
    if not messages:
        return None, {"bad_message_rows": bad_message_rows, "bad_event_rows": bad_event_rows}

    turn_count = max([turn_index(row) for row in messages] or [len(messages)])
    evidence = compaction_evidence(events, messages)
    early_rows = [row for row in messages if turn_index(row) <= early_turns]
    later_rows = [row for row in messages if turn_index(row) >= later_start_turn]
    early_counts = signal_counts(early_rows)
    later_counts = signal_counts(later_rows)
    behavior_events = [event for event in events if behavior_event_is_candidate(event)]
    behavior_count = len(behavior_events)
    guesses = case_family_guesses(early_counts, later_counts, behavior_count)

    stats = {
        "bad_message_rows": bad_message_rows,
        "bad_event_rows": bad_event_rows,
        "message_count": len(messages),
        "event_count": len(events),
        "turn_count": turn_count,
        "has_compaction": int(evidence["observed"]),
        "has_signal": int(bool(guesses)),
    }
    if turn_count < min_turns or (max_turns > 0 and turn_count > max_turns):
        return None, stats
    if not evidence["observed"] or not guesses:
        return None, stats

    thread_key = str(entry.get("thread_key") or entry.get("id") or messages_path or "")
    score = sum(early_counts.values()) + (2 * behavior_count) + len(guesses)
    return (
        {
            "thread_hash": "sha256:" + stable_hash(thread_key, length=20),
            "score": score,
            "turn_count": turn_count,
            "message_count": len(messages),
            "event_count": len(events),
            "compaction_evidence": evidence,
            "early_window": {
                "max_turn": early_turns,
                "message_count": len(early_rows),
                "signal_counts": early_counts,
            },
            "later_window": {
                "start_turn": later_start_turn,
                "message_count": len(later_rows),
                "signal_remention_count": sum(later_counts.values()),
            },
            "behavior_evidence": {
                "behavior_event_count": behavior_count,
                "behavior_event_kind_counts": dict(
                    sorted(
                        Counter(
                            str(event.get("hard_event_kind") or event.get("event_kind") or "unknown")
                            for event in behavior_events
                        ).items()
                    )
                ),
            },
            "source_ref_hashes": source_hashes(early_rows, behavior_events),
            "case_family_guesses": guesses,
            "reviewer_checklist": reviewer_checklist_for(guesses),
        },
        stats,
    )


def load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "threads": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data) if isinstance(data, dict) else {"schema_version": 1, "threads": []}


def run_seed_scan(
    *,
    registry_path: Path,
    min_turns: int = DEFAULT_MIN_TURNS,
    max_turns: int = DEFAULT_MAX_TURNS,
    early_turns: int = DEFAULT_EARLY_TURNS,
    later_start_turn: int = DEFAULT_LATER_START_TURN,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    min_candidates: int = 2,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    candidates: list[dict[str, Any]] = []
    aggregate: Counter[str] = Counter()
    for entry in list_value(registry.get("threads")):
        if not isinstance(entry, dict):
            continue
        candidate, stats = scan_entry(
            entry,
            min_turns=min_turns,
            max_turns=max_turns,
            early_turns=early_turns,
            later_start_turn=later_start_turn,
        )
        aggregate["registry_thread_count"] += 1
        aggregate["message_count"] += stats.get("message_count", 0)
        aggregate["event_count"] += stats.get("event_count", 0)
        aggregate["bad_message_rows"] += stats.get("bad_message_rows", 0)
        aggregate["bad_event_rows"] += stats.get("bad_event_rows", 0)
        aggregate["long_thread_count"] += int(stats.get("turn_count", 0) >= min_turns)
        aggregate["compaction_observed_thread_count"] += stats.get("has_compaction", 0)
        aggregate["signal_thread_count"] += stats.get("has_signal", 0)
        if candidate is not None:
            candidates.append(candidate)

    candidates = sorted(
        candidates,
        key=lambda item: (int(item.get("score") or 0), str(item.get("thread_hash") or "")),
        reverse=True,
    )[: max(0, max_candidates)]
    status = (
        "sufficient_candidate_seeds"
        if len(candidates) >= max(0, min_candidates)
        else "insufficient_candidate_seeds"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SMOKE_KIND,
        "created_at": now_utc(),
        "ok": status == "sufficient_candidate_seeds",
        "status": status,
        "privacy": PRIVACY_BOUNDARY,
        "claim_level": "candidate_seed_discovery_only",
        "candidate_count": len(candidates),
        "scan_config": {
            "min_turns": min_turns,
            "max_turns": max_turns,
            "early_turns": early_turns,
            "later_start_turn": later_start_turn,
            "max_candidates": max_candidates,
            "min_candidates": min_candidates,
        },
        "stats": dict(sorted(aggregate.items())),
        "candidates": candidates,
        "can_claim": [
            "candidate_seed_scanner_reports_sanitized_long_thread_compaction_signal_candidates"
        ],
        "cannot_claim": [
            "e2e50_behavior_benchmark_result",
            "private_history_product_quality",
            "live_host_behavior_lift",
            "semantic_judge_quality",
            "representative_sample_without_manual_annotation",
        ],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan for sanitized #279 E2E50 candidate seeds.")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--annotation", type=Path)
    parser.add_argument("--min-turns", type=int, default=DEFAULT_MIN_TURNS)
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--early-turns", type=int, default=DEFAULT_EARLY_TURNS)
    parser.add_argument("--later-start-turn", type=int, default=DEFAULT_LATER_START_TURN)
    parser.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument("--min-candidates", type=int, default=2)
    parser.add_argument("--min-retained-cases", type=int, default=DEFAULT_MIN_RETAINED_CASES)
    parser.add_argument("--min-negative-controls", type=int, default=DEFAULT_MIN_NEGATIVE_CONTROLS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    registry_path = args.registry or registry_paths(args.registry_dir)[0]
    payload = run_seed_scan(
        registry_path=registry_path,
        min_turns=args.min_turns,
        max_turns=args.max_turns,
        early_turns=args.early_turns,
        later_start_turn=args.later_start_turn,
        max_candidates=args.max_candidates,
        min_candidates=args.min_candidates,
    )
    if args.annotation:
        payload["annotation_summary"] = summarize_annotation_file(
            args.annotation,
            min_retained_cases=args.min_retained_cases,
            min_negative_controls=args.min_negative_controls,
        )
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    if args.annotation:
        return 0
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
