#!/usr/bin/env python3
"""Live shadow A/B ledger for dream-hypothesis recall reminders.

The natural-prompt eval answers whether dream rows can improve route matching.
This module measures the sharper product question: after a real user prompt,
does the user later need to explicitly remind the agent to recall prior context?

Default operation is shadow-only. It records hashed prompt/session identifiers,
baseline-vs-dream route decisions, and later reminder outcomes; it does not
change foreground recall. A real treatment rollout can set delivered arms later,
but reports clearly separate delivered A/B from shadow-only observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import dream_real_history_eval as dream_eval
from aippocampuslib import now_utc
from memory_candidate_router import (
    DREAM_HYPOTHESIS_TYPE,
    default_jobs_path,
    default_working_memory_path,
    iter_jsonl,
    load_working_memory,
    match_working_memory,
)
from registry_store import load_registry, registry_paths, registry_root, thread_store_dir

SCHEMA_VERSION = 1
EVENT_KIND = "aippocampus_dream_shadow_ab_event"
ANALYSIS_KIND = "aippocampus_dream_live_shadow_ab_analysis"
CLAIM_LEVEL = "live_shadow_ab_reminder_frequency"
DEFAULT_EVENT_LOG_NAME = "dream_shadow_ab_events.jsonl"
DEFAULT_SALT = "aippocampus_dream_shadow_ab_v1"

POSITIVE_PATTERNS = (
    ("forgotten_constraint", re.compile(r"(你忘了|你没记住|忘记了|漏了我们之前)", re.IGNORECASE)),
    ("explicit_recall_zh", re.compile(r"(回忆一下|找回|翻一下旧|旧线程|之前.*(说过|聊过|提过|约定|要求|讲过)|上次.*(说过|聊过|提过)|还记得.*吗)", re.IGNORECASE)),
    ("explicit_recall_en", re.compile(r"\b(recall|remember|forgot|forgotten)\b.*\b(before|earlier|previous|last time|old thread|we discussed|we talked)\b", re.IGNORECASE)),
    ("as_said_before", re.compile(r"\b(as i said before|as we discussed|we talked about this before|you forgot)\b", re.IGNORECASE)),
)
TEMPORAL_NOISE_PATTERNS = (
    re.compile(r"\bbefore (calling|running|render|using|writing|returning)\b", re.IGNORECASE),
    re.compile(r"\bprevious (commit|version|function|call|line|diff|patch)\b", re.IGNORECASE),
    re.compile(r"(之前的代码|之前版本|上一段 diff|上一段代码|上一个 commit|上个版本|前一个函数)", re.IGNORECASE),
    re.compile(r"(不用查旧对话|不用回忆|不需要回忆|not asking you to remember)", re.IGNORECASE),
)


def stable_hash(value: object, *, prefix: str, salt: str = DEFAULT_SALT, length: int = 16) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(f"{salt}\n{raw}".encode("utf-8", errors="replace")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def prompt_sha1(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8", errors="replace")).hexdigest()[:16]


def ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def classify_recall_reminder(text: str) -> dict[str, Any]:
    lowered = str(text or "").strip()
    if not lowered:
        return {"is_reminder": False, "family": "", "strength": "none"}
    if any(pattern.search(lowered) for pattern in TEMPORAL_NOISE_PATTERNS):
        return {"is_reminder": False, "family": "temporal_or_code_noise", "strength": "none"}
    for family, pattern in POSITIVE_PATTERNS:
        if pattern.search(lowered):
            strength = "high" if family in {"forgotten_constraint", "as_said_before"} else "medium"
            return {"is_reminder": True, "family": family, "strength": strength}
    return {"is_reminder": False, "family": "", "strength": "none"}


def split_working_memory_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline: list[dict[str, Any]] = []
    dream: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        if copy.get("candidate_type") == DREAM_HYPOTHESIS_TYPE:
            dream.append(copy)
        else:
            baseline.append(copy)
    return baseline, dream


def source_finding_fanout(rows: Iterable[Mapping[str, Any]]) -> int:
    ids = {
        str(source_id)
        for row in rows
        for source_id in (row.get("source_finding_ids") or [])
        if source_id
    }
    return len(ids)


def dream_route_matches(
    prompt: str,
    dream_rows: list[dict[str, Any]],
    *,
    project_label: str | None,
) -> list[dict[str, Any]]:
    return [
        match
        for match in match_working_memory(prompt, dream_rows, project_label=project_label, limit=12)
        if match.get("candidate_type") == DREAM_HYPOTHESIS_TYPE
    ]


def assigned_arm_for(*parts: object, salt: str = DEFAULT_SALT) -> str:
    digest = hashlib.sha1(
        json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        + salt.encode("utf-8")
    ).hexdigest()
    return "dream" if int(digest[:2], 16) % 2 else "control"


def build_shadow_prompt_event(
    *,
    prompt: str,
    session_id: str,
    turn_id: str = "",
    user_turn_index: int | None = None,
    baseline_rows: Iterable[Mapping[str, Any]],
    dream_rows: Iterable[Mapping[str, Any]],
    project_label: str | None = "AIppocampus",
    salt: str = DEFAULT_SALT,
    timestamp: str | None = None,
    source: str = "prompt_hook_shadow",
    delivery_mode: str = "shadow_only",
    delivered_arm: str | None = None,
) -> dict[str, Any]:
    baseline_list = [dict(row) for row in baseline_rows]
    dream_list = [dict(row) for row in dream_rows]
    baseline_matches = match_working_memory(prompt, baseline_list, project_label=project_label, limit=12)
    dream_matches = dream_route_matches(prompt, dream_list, project_label=project_label)
    reminder = classify_recall_reminder(prompt)
    prompt_hash = prompt_sha1(prompt)
    assigned_arm = assigned_arm_for(session_id, turn_id, prompt_hash, salt=salt)
    eligible = (
        not reminder["is_reminder"]
        and not baseline_matches
        and bool(dream_matches)
    )
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "created_at": timestamp or now_utc(),
        "source": source,
        "delivery_mode": delivery_mode,
        "event_id": stable_hash([session_id, turn_id, prompt_hash], prefix="shadowevt", salt=salt),
        "thread_fingerprint": stable_hash(session_id or "unknown", prefix="threadfp", salt=salt, length=12),
        "turn_fingerprint": stable_hash(turn_id or user_turn_index or prompt_hash, prefix="turnfp", salt=salt, length=12),
        "user_turn_index": user_turn_index,
        "prompt_sha1": prompt_hash,
        "assigned_arm": assigned_arm,
        "delivered_arm": delivered_arm if delivered_arm in {"control", "dream"} else None,
        "eligible_exposure": eligible,
        "reminder": reminder,
        "baseline": {
            "match_count": len(baseline_matches),
            "decision": "match" if baseline_matches else "miss",
        },
        "dream": {
            "match_count": len(dream_matches),
            "decision": "match" if dream_matches else "miss",
            "source_finding_fanout": source_finding_fanout(dream_matches),
        },
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_thread_id_emitted": False,
            "raw_turn_id_emitted": False,
        },
    }
    return event


def append_event(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(dict(event), ensure_ascii=False) + "\n")


def load_events(path: Path) -> list[dict[str, Any]]:
    return [row for row in iter_jsonl(path) if row.get("kind") == EVENT_KIND]


def default_event_log(registry_dir: Path | None = None) -> Path:
    return registry_root(registry_dir) / DEFAULT_EVENT_LOG_NAME


def row_order(row: Mapping[str, Any], fallback: int) -> int:
    value = row.get("user_turn_index")
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def effective_arm(row: Mapping[str, Any]) -> str:
    delivered = str(row.get("delivered_arm") or "")
    if delivered in {"control", "dream"}:
        return delivered
    assigned = str(row.get("assigned_arm") or "")
    return assigned if assigned in {"control", "dream"} else "control"


def empty_arm_metrics() -> dict[str, Any]:
    return {
        "eligible_exposures": 0,
        "reminder_outcomes": 0,
        "reminder_rate": 0.0,
    }


def analyze_shadow_events(
    events: Iterable[Mapping[str, Any]],
    *,
    window_user_turns: int = 4,
) -> dict[str, Any]:
    rows = [dict(row) for row in events if row.get("kind") == EVENT_KIND]
    by_thread: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        thread = str(row.get("thread_fingerprint") or "thread_unknown")
        by_thread[thread].append((row_order(row, index), row))

    arms = {"control": empty_arm_metrics(), "dream": empty_arm_metrics()}
    total_reminders = 0
    attributed = 0
    unattributed = 0
    attributed_event_ids: set[str] = set()
    live_delivery_events = 0

    for items in by_thread.values():
        items.sort(key=lambda item: item[0])
        for _, row in items:
            if row.get("delivered_arm") in {"control", "dream"}:
                live_delivery_events += 1
            if row.get("eligible_exposure"):
                arms[effective_arm(row)]["eligible_exposures"] += 1

        for position, (order, row) in enumerate(items):
            reminder_value = row.get("reminder")
            reminder = reminder_value if isinstance(reminder_value, Mapping) else {}
            if not reminder.get("is_reminder"):
                continue
            total_reminders += 1
            winner: dict[str, Any] | None = None
            for prior_order, candidate in reversed(items[:position]):
                if order - prior_order > window_user_turns:
                    break
                event_id = str(candidate.get("event_id") or "")
                if not candidate.get("eligible_exposure") or event_id in attributed_event_ids:
                    continue
                winner = candidate
                break
            if winner is None:
                unattributed += 1
                continue
            attributed += 1
            attributed_event_ids.add(str(winner.get("event_id") or ""))
            arms[effective_arm(winner)]["reminder_outcomes"] += 1

    for arm in arms.values():
        arm["reminder_rate"] = ratio(arm["reminder_outcomes"], arm["eligible_exposures"])

    return {
        "event_count": len(rows),
        "thread_count": len(by_thread),
        "live_delivery_event_count": live_delivery_events,
        "overall_reminder_rate": ratio(total_reminders, len(rows)),
        "eligible_exposure_rate": ratio(
            arms["control"]["eligible_exposures"] + arms["dream"]["eligible_exposures"],
            len(rows),
        ),
        "arms": arms,
        "rate_delta_dream_minus_control": round(
            arms["dream"]["reminder_rate"] - arms["control"]["reminder_rate"],
            4,
        ),
        "direction": "lower_is_better",
        "attribution": {
            "window_user_turns": window_user_turns,
            "total_reminder_count": total_reminders,
            "attributed_reminder_count": attributed,
            "unattributed_reminder_count": unattributed,
            "nearest_prior_eligible_exposure_only": True,
        },
    }


def run_shadow_ab_analysis(
    *,
    event_log: Path,
    window_user_turns: int = 4,
) -> dict[str, Any]:
    metrics = analyze_shadow_events(load_events(event_log), window_user_turns=window_user_turns)
    live_delivery = int(metrics.get("live_delivery_event_count") or 0) > 0
    can_claim = [
        "explicit_recall_reminder_frequency_counted",
        "nearest_prior_exposure_attribution_used",
        "shadow_ab_log_is_sanitized",
    ]
    cannot_claim = [
        "general_dream_quality",
        "full_history_coverage",
    ]
    if live_delivery:
        can_claim.append("observed_delivered_arm_reminder_rates")
    else:
        cannot_claim.append("causal_real_user_behavior_lift_without_delivered_treatment")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "created_at": now_utc(),
        "status": "analyzed" if metrics["event_count"] else "no_events",
        "claim_level": CLAIM_LEVEL,
        "private_text_emitted": False,
        "metrics": metrics,
        "can_claim": can_claim,
        "cannot_claim": cannot_claim,
    }


def record_prompt_shadow_from_hook(
    *,
    prompt: str,
    hook_input: Mapping[str, Any],
    registry_dir: Path | None = None,
    registry_path: Path | None = None,
    working_memory_path: Path | None = None,
    event_log: Path | None = None,
    salt: str = DEFAULT_SALT,
    project_label: str | None = "AIppocampus",
) -> dict[str, Any]:
    resolved_registry_path = registry_path or registry_paths(registry_dir)[0]
    rows = load_working_memory(working_memory_path or default_working_memory_path(resolved_registry_path))
    baseline_rows, dream_rows = split_working_memory_rows(rows)
    event = build_shadow_prompt_event(
        prompt=prompt,
        session_id=str(hook_input.get("session_id") or hook_input.get("thread_id") or ""),
        turn_id=str(hook_input.get("turn_id") or ""),
        baseline_rows=baseline_rows,
        dream_rows=dream_rows,
        project_label=project_label,
        salt=salt,
        source="prompt_hook_shadow",
    )
    append_event(event_log or default_event_log(registry_dir), event)
    return event


def optional_path(value: object) -> Path | None:
    return Path(str(value)) if value else None


def record_prompt_shadow_from_hook_args(
    *,
    prompt: str,
    hook_input: Mapping[str, Any],
    args: Any,
) -> dict[str, Any]:
    return record_prompt_shadow_from_hook(
        prompt=prompt,
        hook_input=hook_input
        or {"session_id": getattr(args, "session_id", "") or "", "turn_id": getattr(args, "topic_epoch", "") or ""},
        registry_dir=optional_path(getattr(args, "registry_dir", None)),
        registry_path=optional_path(getattr(args, "registry", None)),
        working_memory_path=optional_path(getattr(args, "working_memory", None)),
        event_log=optional_path(getattr(args, "dream_shadow_log", None)),
        salt=getattr(args, "dream_shadow_salt", None) or DEFAULT_SALT,
    )


def clean_source_messages_path(entry: Mapping[str, Any], thread_key: str, registry_dir: Path | None) -> Path:
    paths = entry.get("paths") if isinstance(entry.get("paths"), Mapping) else {}
    explicit = paths.get("clean_source_messages_jsonl") if isinstance(paths, Mapping) else None
    if explicit:
        return Path(str(explicit))
    return thread_store_dir(thread_key, registry_dir) / "clean-source" / "messages.jsonl"


def replay_clean_source_events(
    *,
    registry_dir: Path | None = None,
    working_memory_path: Path | None = None,
    max_threads: int = 200,
    max_user_messages: int = 2000,
    salt: str = DEFAULT_SALT,
    project_label: str | None = "AIppocampus",
    generated_dream_max_packs: int = 0,
) -> list[dict[str, Any]]:
    registry_path, _ = registry_paths(registry_dir)
    registry = load_registry(registry_path)
    rows = load_working_memory(working_memory_path or default_working_memory_path(registry_path))
    if generated_dream_max_packs > 0:
        jobs = iter_jsonl(default_jobs_path(registry_path))
        packs = dream_eval.select_real_history_packs(
            job_rows=jobs,
            working_memory_rows=rows,
            max_packs=generated_dream_max_packs,
        )
        rows = [
            *rows,
            *[
                row
                for pack in packs
                for row in (dream_eval.run_pack_dream_worker(pack).get("dream_working_memory_rows") or [])
                if isinstance(row, dict)
            ],
        ]
    baseline_rows, dream_rows = split_working_memory_rows(rows)
    events: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        if len(events) >= max_user_messages or len({event["thread_fingerprint"] for event in events}) >= max_threads:
            break
        if not isinstance(entry, Mapping):
            continue
        thread_key = str(entry.get("thread_key") or "")
        if not thread_key:
            continue
        path = clean_source_messages_path(entry, thread_key, registry_dir)
        for message in iter_jsonl(path):
            if len(events) >= max_user_messages:
                break
            if str(message.get("role") or "") != "user":
                continue
            events.append(
                build_shadow_prompt_event(
                    prompt=str(message.get("text") or ""),
                    session_id=thread_key,
                    turn_id=str(message.get("turn_id") or message.get("message_id") or ""),
                    user_turn_index=int(message.get("turn_index") or len(events)),
                    baseline_rows=baseline_rows,
                    dream_rows=dream_rows,
                    project_label=project_label,
                    salt=salt,
                    timestamp=str(message.get("timestamp") or now_utc()),
                    source="clean_source_shadow_replay",
                    delivery_mode="historical_shadow_replay",
                )
            )
    return events


def run_clean_source_replay_analysis(
    *,
    registry_dir: Path | None = None,
    working_memory_path: Path | None = None,
    max_threads: int = 200,
    max_user_messages: int = 2000,
    window_user_turns: int = 4,
    salt: str = DEFAULT_SALT,
    generated_dream_max_packs: int = 0,
) -> dict[str, Any]:
    events = replay_clean_source_events(
        registry_dir=registry_dir,
        working_memory_path=working_memory_path,
        max_threads=max_threads,
        max_user_messages=max_user_messages,
        salt=salt,
        generated_dream_max_packs=generated_dream_max_packs,
    )
    metrics = analyze_shadow_events(events, window_user_turns=window_user_turns)
    metrics["generated_dream_max_packs"] = generated_dream_max_packs
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "created_at": now_utc(),
        "status": "analyzed" if events else "no_events",
        "claim_level": "historical_shadow_replay_reminder_frequency",
        "private_text_emitted": False,
        "metrics": metrics,
        "can_claim": [
            "historical_clean_source_replay_counted_explicit_recall_reminders",
            "shadow_assignment_and_nearest_prior_attribution_ran",
        ],
        "cannot_claim": [
            "causal_real_user_behavior_lift_without_delivered_treatment",
            "time_causal_dream_availability_without_live_event_log",
            "general_dream_quality",
            "full_history_coverage",
        ],
    }


def test_event(
    *,
    index: int,
    arm: str = "control",
    eligible: bool = True,
    reminder: bool = False,
    thread: str = "thread-a",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "created_at": f"2026-05-30T00:00:{index:02d}Z",
        "source": "unit_test",
        "event_id": f"event-{thread}-{index}",
        "thread_fingerprint": stable_hash(thread, prefix="threadfp", salt="unit-test"),
        "user_turn_index": index,
        "assigned_arm": arm,
        "delivered_arm": None,
        "eligible_exposure": eligible,
        "reminder": {"is_reminder": reminder, "family": "unit", "strength": "high" if reminder else "none"},
        "baseline": {"match_count": 0, "decision": "miss"},
        "dream": {"match_count": 1 if eligible else 0, "decision": "match" if eligible else "miss"},
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record or analyze dream live shadow A/B events.")
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--working-memory", type=Path)
    parser.add_argument("--event-log", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--window-user-turns", type=int, default=4)
    parser.add_argument("--salt", default=DEFAULT_SALT)
    sub = parser.add_mutually_exclusive_group()
    sub.add_argument("--analyze-log", action="store_true")
    sub.add_argument("--replay-clean-source", action="store_true")
    parser.add_argument("--max-threads", type=int, default=200)
    parser.add_argument("--max-user-messages", type=int, default=2000)
    parser.add_argument(
        "--generate-dream-rows",
        type=int,
        default=0,
        help="For clean-source replay only, generate this many selected dream packs in memory.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    event_log = args.event_log or default_event_log(args.registry_dir)
    if args.replay_clean_source:
        payload = run_clean_source_replay_analysis(
            registry_dir=args.registry_dir,
            working_memory_path=args.working_memory,
            max_threads=args.max_threads,
            max_user_messages=args.max_user_messages,
            window_user_turns=args.window_user_turns,
            salt=args.salt,
            generated_dream_max_packs=args.generate_dream_rows,
        )
    else:
        payload = run_shadow_ab_analysis(event_log=event_log, window_user_turns=args.window_user_turns)
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
