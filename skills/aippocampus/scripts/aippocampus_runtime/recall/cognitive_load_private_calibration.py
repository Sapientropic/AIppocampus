#!/usr/bin/env python3
"""Public-safe private-history calibration for cognitive-load routing hints.

This runner reads clean-source messages/events as the source trail, but its
report is hash/count/enum only. It is intentionally diagnostic: a measured
private-history aggregate can reveal whether load signals exist, but it still
cannot prove live host timing, user-visible recall lift, or affect truth.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import stable_text_join_digest
from aippocampus_runtime.recall import cognitive_load_sidecar as sidecar
from aippocampus_runtime.registry.store import load_registry, registry_paths

SCHEMA_VERSION = 1
KIND = "aippocampus_cognitive_load_private_history_calibration"
PRIVACY_BOUNDARY = "aggregate_hash_only_no_text_no_paths_no_ids"

USER_CORRECTION_TERMS = (
    "不对",
    "不是这个意思",
    "你误解",
    "你搞错",
    "错了",
    "有问题",
    "没通过",
    "没有通过",
    "修一下",
    "incorrect",
    "wrong",
    "not what i meant",
    "you misunderstood",
    "does not pass",
    "did not pass",
)
EXPLICIT_PITFALL_TERMS = (
    "不要再",
    "别再",
    "禁止",
    "不能这样",
    "坑",
    "踩坑",
    "回退",
    "失败路线",
    "do not repeat",
    "don't repeat",
    "never again",
    "known-bad",
    "pitfall",
    "rollback",
)
REJECTED_ROUTE_TERMS = (
    "不要走",
    "别走",
    "这条路线",
    "换路线",
    "换成",
    "fallback",
    "rejected route",
    "bad route",
    "wrong route",
)
SOURCE_CONFLICT_TERMS = (
    "冲突",
    "以真实代码",
    "以真实文件",
    "真实输出为准",
    "source of truth",
    "conflict",
    "actual code",
    "actual file",
)
HUMAN_INTERVENTION_TERMS = (
    "我来",
    "我自己",
    "手动",
    "人工",
    "我放给你权限",
    "manual",
    "human",
    "i will fix",
)
HIGH_RISK_REPAIRED_TERMS = (
    "不能泄露",
    "脱敏",
    "权限",
    "高风险",
    "sensitive",
    "redact",
    "secret",
    "credential",
    "permission",
)
REOPEN_TERMS = (
    "重开",
    "重新打开",
    "重新查",
    "查 source",
    "查源码",
    "reopen source",
    "re-open source",
    "open the source",
)
REPEATED_TERMS = (
    "又",
    "再次",
    "再一次",
    "重复",
    "again",
    "repeated",
    "repeat",
)
FAILED_HARD_KINDS = {
    "tool_call_failed",
    "test_failed",
    "command_failed",
    "apply_patch_failed",
}

CALIBRATION_CANNOT_CLAIM = (
    "live_delivered_host_timing",
    "host_timing_quality",
    "user_visible_recall_improvement",
    "affect_or_personality_truth_from_load_signal",
    "source_truth_from_load_signal",
    "private_text_quality_review",
)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def _read_jsonl(path: Path | None) -> tuple[list[dict[str, Any]], int]:
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


def _source_ref_from_row(row: Mapping[str, Any], *, fallback_kind: str) -> dict[str, Any]:
    """Return only stable join fields or a one-way hash of a raw source ref.

    Clean-source rows sometimes carry provider-native `source_ref` values. Those
    are reopen handles for private use, not public report material, so this
    adapter hashes them before handing the ref to the sidecar.
    """

    raw_ref = row.get("source_ref")
    if isinstance(raw_ref, Mapping) and raw_ref.get("source_ref_hash"):
        return {"source_ref_hash": str(raw_ref.get("source_ref_hash"))}
    if row.get("source_ref_hash"):
        return {"source_ref_hash": str(row.get("source_ref_hash"))}

    stable_ref = {
        "source_id": row.get("source_id"),
        "thread_id": row.get("thread_id"),
        "turn_id": row.get("turn_id"),
        "message_id": row.get("message_id") or row.get("event_id") or row.get("id"),
        "line": row.get("line"),
        "source_line": row.get("source_line"),
    }
    if any(value not in (None, "") for value in stable_ref.values()):
        return {key: value for key, value in stable_ref.items() if value not in (None, "")}

    return {
        "source_ref_hash": "sha256:"
        + stable_text_join_digest(
            fallback_kind,
            raw_ref,
            row.get("message_id") or row.get("event_id") or row.get("id"),
            row.get("turn_index"),
            sep="\0",
            length=20,
        )
    }


def _message_signal_types(row: Mapping[str, Any]) -> list[str]:
    if str(row.get("role") or "").casefold() != "user":
        return []
    text = str(row.get("text") or "")
    signal_types: list[str] = []
    if _contains_any(text, USER_CORRECTION_TERMS):
        signal_types.append("user_correction")
    if _contains_any(text, EXPLICIT_PITFALL_TERMS):
        signal_types.append("explicit_pitfall_marker")
    if _contains_any(text, REJECTED_ROUTE_TERMS):
        signal_types.append("rejected_route_retry")
    if _contains_any(text, SOURCE_CONFLICT_TERMS):
        signal_types.append("source_conflict")
    if _contains_any(text, HUMAN_INTERVENTION_TERMS):
        signal_types.append("human_intervention")
    if _contains_any(text, HIGH_RISK_REPAIRED_TERMS):
        signal_types.append("high_risk_action_repaired")
    return signal_types


def _event_signal_type(row: Mapping[str, Any]) -> str:
    hard_kind = str(row.get("hard_event_kind") or row.get("event_kind") or "").casefold()
    status = str(row.get("status") or "").casefold()
    command_class = str(row.get("command_class") or "").casefold()
    failure_family = str(row.get("failure_family") or "").casefold()
    command_family = str(row.get("command_family") or "").casefold()
    if "revert" in hard_kind or "rollback" in failure_family or command_family == "git_revert":
        return "rollback_or_revert"
    if (
        hard_kind in FAILED_HARD_KINDS
        or status in {"failed", "error"}
        or bool(failure_family)
    ):
        if command_class in {"test", "check"} or "test" in hard_kind:
            return "failed_test"
        return "failed_command"
    return ""


def extract_cognitive_load_events_from_clean_source(
    messages: Iterable[Mapping[str, Any]],
    behavior_events: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert clean-source rows into sidecar events without exporting text."""

    load_events: list[dict[str, Any]] = []
    signal_counts: Counter[str] = Counter()
    source_reopen_count = 0
    repeated_pitfall_count = 0
    message_rows_scanned = 0
    event_rows_scanned = 0

    for ordinal, row in enumerate(messages):
        message_rows_scanned += 1
        text = str(row.get("text") or "")
        source_reopened = _contains_any(text, REOPEN_TERMS)
        repeated_pitfall = _contains_any(text, REPEATED_TERMS)
        for signal_type in _message_signal_types(row):
            signal_counts[signal_type] += 1
            source_reopen_count += int(source_reopened)
            repeated_pitfall_count += int(repeated_pitfall)
            load_events.append(
                {
                    "event_id": "sha256:"
                    + stable_text_join_digest(
                        "message",
                        ordinal,
                        signal_type,
                        row.get("message_id"),
                        sep="\0",
                        length=20,
                    ),
                    "event_type": signal_type,
                    "timestamp": row.get("timestamp"),
                    "source_refs": [_source_ref_from_row(row, fallback_kind="message")],
                    "source_reopened": source_reopened,
                    "pitfall_repeated_after_signal": repeated_pitfall,
                }
            )

    for ordinal, row in enumerate(behavior_events):
        event_rows_scanned += 1
        signal_type = _event_signal_type(row)
        if not signal_type:
            continue
        signal_counts[signal_type] += 1
        load_events.append(
            {
                "event_id": "sha256:"
                + stable_text_join_digest(
                    "behavior",
                    ordinal,
                    signal_type,
                    row.get("event_id"),
                    sep="\0",
                    length=20,
                ),
                "event_type": signal_type,
                "timestamp": row.get("timestamp"),
                "source_refs": [_source_ref_from_row(row, fallback_kind="event")],
            }
        )

    return load_events, {
        "message_rows_scanned": message_rows_scanned,
        "event_rows_scanned": event_rows_scanned,
        "signal_event_count": len(load_events),
        "message_signal_event_count": sum(
            count
            for key, count in signal_counts.items()
            if key
            in {
                "user_correction",
                "explicit_pitfall_marker",
                "rejected_route_retry",
                "source_conflict",
                "human_intervention",
                "high_risk_action_repaired",
            }
        ),
        "behavior_signal_event_count": sum(
            count
            for key, count in signal_counts.items()
            if key in {"failed_test", "failed_command", "rollback_or_revert"}
        ),
        "source_reopen_signal_count": source_reopen_count,
        "pitfall_repetition_signal_count": repeated_pitfall_count,
        "signal_kind_counts": dict(sorted(signal_counts.items())),
    }


def _diagnostic_candidates(sidecar_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in sidecar_payload.get("entries") or []:
        entry = _as_mapping(row)
        key = str(entry.get("source_ref_key") or "")
        if not key:
            continue
        candidates.append(
            {
                "candidate_id": "private-load-" + key.replace("sha256:", "")[:12],
                "source_ref_key": key,
                "semantic_score": 0.5,
                "source_authority": 0.9,
                "source_status": "current",
            }
        )
    return candidates


def _bucket_counts(entries: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entry in entries:
        counts[str(entry.get("load_bucket") or "none")] += 1
    return dict(sorted(counts.items()))


def _reason_counts(entries: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for entry in entries:
        for reason in entry.get("reason_codes") or []:
            counts[str(reason)] += 1
    return dict(sorted(counts.items()))


def build_private_history_cognitive_load_calibration(
    messages: Iterable[Mapping[str, Any]],
    behavior_events: Iterable[Mapping[str, Any]],
    *,
    now: str | None = None,
    input_surface: str = "clean_source_messages_and_events",
    registry_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    registry_metrics = _as_mapping(registry_metrics)
    load_events, extraction = extract_cognitive_load_events_from_clean_source(
        messages,
        behavior_events,
    )
    status = "measured_public_safe_aggregate" if load_events else "measured_no_signals"
    sidecar_payload = sidecar.build_cognitive_load_sidecar(load_events, now=now)
    ranked = sidecar.apply_cognitive_load_boosts(
        _diagnostic_candidates(sidecar_payload),
        sidecar_payload,
    )
    calibration_report = sidecar.build_cognitive_load_calibration_report(
        sidecar_payload,
        ranked,
        private_history_calibration={
            "status": status,
            "input_surface": input_surface,
            "thread_count_scanned": registry_metrics.get("thread_count_scanned") or 0,
            "message_rows_scanned": extraction["message_rows_scanned"],
            "event_rows_scanned": extraction["event_rows_scanned"],
            "signal_event_count": extraction["signal_event_count"],
        },
    )
    entries = [_as_mapping(row) for row in sidecar_payload.get("entries") or []]
    boosted_candidate_count = sum(
        1
        for row in ranked
        if float(_as_mapping(row.get("score_breakdown")).get("cognitive_load_boost") or 0.0) > 0
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": status,
        "mode": "private_history_public_safe_aggregate",
        "projection_boundary": sidecar.PROJECTION_BOUNDARY,
        "privacy_boundary": {
            "boundary": PRIVACY_BOUNDARY,
            "raw_private_text_emitted": False,
            "raw_source_refs_emitted": False,
            "local_paths_emitted": False,
            "raw_feedback_text_emitted": False,
            "source_ref_keys_only": True,
        },
        "input_surface": {
            "source": input_surface,
            "thread_count_scanned": int(registry_metrics.get("thread_count_scanned") or 0),
            "threads_with_signal_count": int(registry_metrics.get("threads_with_signal_count") or 0),
            "missing_clean_source_count": int(registry_metrics.get("missing_clean_source_count") or 0),
            "bad_jsonl_row_count": int(registry_metrics.get("bad_jsonl_row_count") or 0),
            "message_rows_scanned": extraction["message_rows_scanned"],
            "event_rows_scanned": extraction["event_rows_scanned"],
        },
        "extraction_metrics": extraction,
        "sidecar_metrics": sidecar_payload["metrics"],
        "sidecar_projection": {
            "entry_count": len(entries),
            "load_bucket_counts": _bucket_counts(entries),
            "reason_code_counts": _reason_counts(entries),
            "source_ref_key_sample": [
                str(entry.get("source_ref_key") or "")
                for entry in entries[:10]
                if entry.get("source_ref_key")
            ],
        },
        "ranked_candidate_summary": {
            "candidate_count": len(ranked),
            "boosted_candidate_count": boosted_candidate_count,
            "source_reopen_recommended_count": calibration_report["metrics"][
                "source_reopen_recommended_count"
            ],
            "refresh_recommended_count": calibration_report["metrics"][
                "refresh_recommended_count"
            ],
        },
        "calibration_report": calibration_report,
        "issue_readouts": calibration_report["issue_readouts"],
        "cannot_claim": sorted(CALIBRATION_CANNOT_CLAIM),
    }


def _paths_from_clean_source_dir(clean_source_dir: Path | None) -> tuple[Path | None, Path | None]:
    if clean_source_dir is None:
        return None, None
    return clean_source_dir / "messages.jsonl", clean_source_dir / "events.jsonl"


def run_private_history_calibration(
    *,
    registry_json: Path | None = None,
    clean_source_dir: Path | None = None,
    messages_jsonl: Path | None = None,
    events_jsonl: Path | None = None,
    max_threads: int = 100,
    now: str | None = None,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    behavior_events: list[dict[str, Any]] = []
    bad_jsonl_rows = 0
    missing_clean_source_count = 0
    thread_count_scanned = 0
    thread_signal_flags: list[bool] = []

    dir_messages, dir_events = _paths_from_clean_source_dir(clean_source_dir)
    if messages_jsonl or events_jsonl or dir_messages or dir_events:
        msg_rows, msg_bad = _read_jsonl(messages_jsonl or dir_messages)
        evt_rows, evt_bad = _read_jsonl(events_jsonl or dir_events)
        messages.extend(msg_rows)
        behavior_events.extend(evt_rows)
        bad_jsonl_rows += msg_bad + evt_bad
        thread_count_scanned = 1
        preview_events, _ = extract_cognitive_load_events_from_clean_source(msg_rows, evt_rows)
        thread_signal_flags.append(bool(preview_events))
        input_surface = "single_clean_source"
    else:
        resolved_registry = registry_json or registry_paths()[0]
        registry = load_registry(resolved_registry)
        input_surface = "thread_registry_clean_source"
        for entry in registry.get("threads") or []:
            if thread_count_scanned >= max_threads:
                break
            paths = _as_mapping(_as_mapping(entry).get("paths"))
            msg_path = _as_path(paths.get("clean_source_messages_jsonl"))
            evt_path = _as_path(paths.get("clean_source_events_jsonl"))
            if msg_path is None and evt_path is None:
                missing_clean_source_count += 1
                continue
            msg_rows, msg_bad = _read_jsonl(msg_path)
            evt_rows, evt_bad = _read_jsonl(evt_path)
            bad_jsonl_rows += msg_bad + evt_bad
            if not msg_rows and not evt_rows:
                missing_clean_source_count += 1
                continue
            thread_count_scanned += 1
            preview_events, _ = extract_cognitive_load_events_from_clean_source(msg_rows, evt_rows)
            thread_signal_flags.append(bool(preview_events))
            messages.extend(msg_rows)
            behavior_events.extend(evt_rows)

    return build_private_history_cognitive_load_calibration(
        messages,
        behavior_events,
        now=now,
        input_surface=input_surface,
        registry_metrics={
            "thread_count_scanned": thread_count_scanned,
            "threads_with_signal_count": sum(1 for value in thread_signal_flags if value),
            "missing_clean_source_count": missing_clean_source_count,
            "bad_jsonl_row_count": bad_jsonl_rows,
        },
    )


def _render_text(payload: Mapping[str, Any]) -> str:
    metrics = _as_mapping(payload.get("extraction_metrics"))
    input_surface = _as_mapping(payload.get("input_surface"))
    return "\n".join(
        [
            f"Status: {payload.get('status')}",
            f"Threads scanned: {input_surface.get('thread_count_scanned')}",
            f"Messages scanned: {input_surface.get('message_rows_scanned')}",
            f"Events scanned: {input_surface.get('event_rows_scanned')}",
            f"Load signals: {metrics.get('signal_event_count')}",
            "Privacy: no raw text, raw source refs, or local paths emitted.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a public-safe private-history cognitive-load calibration scan."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--registry-json", type=Path, help="Thread registry JSON path.")
    parser.add_argument("--clean-source-dir", type=Path, help="Directory with messages/events JSONL.")
    parser.add_argument("--messages-jsonl", type=Path, help="Clean-source messages JSONL.")
    parser.add_argument("--events-jsonl", type=Path, help="Clean-source events JSONL.")
    parser.add_argument("--max-threads", type=int, default=100)
    parser.add_argument("--now", help="UTC ISO timestamp for deterministic decay.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    payload = run_private_history_calibration(
        registry_json=args.registry_json,
        clean_source_dir=args.clean_source_dir,
        messages_jsonl=args.messages_jsonl,
        events_jsonl=args.events_jsonl,
        max_threads=max(0, args.max_threads),
        now=args.now,
    )
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8", newline="\n")
    if args.json:
        print(encoded)
    else:
        print(_render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
