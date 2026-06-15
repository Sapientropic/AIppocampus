#!/usr/bin/env python3
"""Append-only consolidation-priority events for high-value awake moments.

This is the small deterministic substrate behind the SWR-inspired planning
track. It marks source-reachable moments for later review priority, but it does
not run consolidation, promote memories, inject foreground evidence, or claim
biological equivalence.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
    safe_path_name,
    sanitize_external_model_text,
    stable_text_fingerprint,
)
from aippocampus_runtime.question.source_refs import compact_source_refs, source_ref_key
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-consolidation-priority-v1"
EVENT_KIND = "consolidation_priority_event"

PRODUCERS = {
    "correction",
    "rejected_route",
    "failure",
    "source_conflict",
    "cognitive_load",
    "frontier_question",
}
SIGNAL_WEIGHTS = {
    "correction": 0.90,
    "superseding_decision": 0.86,
    "rejected_route": 0.85,
    "do_not_repeat": 0.82,
    "source_conflict": 0.82,
    "failed_test": 0.72,
    "failed_command": 0.65,
    "rollback_or_revert": 0.70,
    "cognitive_load": 0.55,
    "frontier_question": 0.50,
    "ordinary_turn": 0.10,
}
SOURCE_STATES = {
    "source_open",
    "bounded_evidence",
    "reopenable_route",
    "source_ref",
    "ok",
    "stale",
    "missing",
    "superseded",
    "blocked",
}
DEGRADED_SOURCE_STATES = {"stale", "missing", "superseded", "blocked"}
MIN_REVIEW_SCORE = 0.45
MAX_SIGNAL_COUNT = 8
DECAY_HALF_LIFE_DAYS = 14.0
STORAGE_STRING_KEYS = (
    "created_at",
    "prompt_version",
    "event_id",
    "thread_id",
    "workspace",
    "workspace_sha1",
    "workspace_privacy",
    "producer",
    "source_key",
    "source_state",
    "degradation_reason",
    "truth_status",
    "status",
    "source",
)
STORAGE_BOOL_KEYS = (
    "review_queue_eligible",
    "degraded",
    "append_only",
    "formal_memory_promoted",
    "working_memory_promoted",
    "foreground_evidence",
    "user_visible_memory",
    "clean_source_mutated",
    "raw_rollout_mutated",
    "review_required_before_consolidation",
)
STORAGE_NUMBER_KEYS = (
    "schema_version",
    "priority_score",
    "decay_multiplier",
    "effective_priority_score",
)

LOCAL_PATH_RE = re.compile(
    r"(?i)(^[a-z]:[\\/])|(^/(Users|home|root|tmp|var|mnt|Volumes|private)/)|(^~[\\/])"
)
FAKE_TEST_SECRET_RE = re.compile(r"FAKE_TEST_(SECRET|PASSWORD|TOKEN|KEY)_VALUE_[A-Za-z0-9_:-]+")


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return stable_text_fingerprint(
        raw,
        namespace="consolidation-priority-id",
        prefix=prefix,
        length=length,
    )


def _sanitize_text(
    value: Any,
    *,
    max_chars: int,
    policies: list[dict[str, Any]],
) -> str:
    sanitized, policy = sanitize_external_model_text(str(value or ""))
    sanitized = FAKE_TEST_SECRET_RE.sub("<redacted:test-secret>", sanitized)
    policies.append(policy)
    return compact_text(sanitized, max_chars)


def _privacy_scan(policies: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    redaction_types: list[str] = []
    redaction_count = 0
    hard_block = False
    for policy in policies:
        redaction_count += int(policy.get("redaction_count") or 0)
        hard_block = hard_block or bool(policy.get("hard_block"))
        redaction_types.extend(str(item) for item in policy.get("redaction_types") or [])
    return {
        "raw_text_stored": False,
        "raw_prompt_stored": False,
        "raw_source_text_stored": False,
        "raw_tool_payloads_stored": False,
        "local_paths_stored": False,
        "secrets_stored": False,
        "redacted": bool(redaction_count or hard_block),
        "redaction_count": redaction_count,
        "redaction_types": unique_preserve(redaction_types, limit=8),
        "hard_block": hard_block,
    }


def _storage_privacy_scan(
    existing: Any,
    policies: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    scan = _privacy_scan(policies)
    if not isinstance(existing, Mapping):
        return scan
    scan["redacted"] = bool(scan["redacted"] or existing.get("redacted"))
    scan["hard_block"] = bool(scan["hard_block"] or existing.get("hard_block"))
    scan["redaction_count"] = max(
        int(scan.get("redaction_count") or 0),
        int(existing.get("redaction_count") or 0),
    )
    scan["redaction_types"] = unique_preserve(
        [
            *(str(item) for item in existing.get("redaction_types") or []),
            *(str(item) for item in scan.get("redaction_types") or []),
        ],
        limit=8,
    )
    return scan


def _workspace_fields(workspace: str | None, policies: list[dict[str, Any]]) -> dict[str, Any]:
    raw = str(workspace or "").strip()
    if not raw:
        return {"workspace": ""}
    sanitized = _sanitize_text(raw, max_chars=160, policies=policies)
    path_like = bool(LOCAL_PATH_RE.search(raw) or "\\" in raw or "/" in raw)
    if not path_like:
        return {"workspace": sanitized}
    normalized = raw.replace("\\", "/").rstrip("/")
    label = safe_path_name(normalized.rsplit("/", 1)[-1] or "workspace", "workspace")
    return {
        "workspace": label,
        "workspace_sha1": stable_text_fingerprint(
            normalized.casefold(),
            namespace="consolidation-priority-workspace",
            length=16,
        ),
        "workspace_privacy": "local_path_redacted_to_label_and_hash",
    }


def sanitize_source_refs(
    values: Any,
    *,
    policies: list[dict[str, Any]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ref in compact_source_refs(values, limit=limit):
        clean: dict[str, Any] = {}
        for key, value in ref.items():
            if isinstance(value, str):
                clean[key] = _sanitize_text(value, max_chars=220, policies=policies)
            else:
                clean[key] = value
        out.append(clean)
    return out


def source_key_for_refs(
    refs: Sequence[Mapping[str, Any]] | None = None,
    *,
    behavior_event_ids: Sequence[str] | None = None,
) -> str:
    ref_keys = [source_ref_key(ref) for ref in refs or [] if isinstance(ref, Mapping)]
    behavior_keys = [str(item or "") for item in behavior_event_ids or [] if str(item or "")]
    payload: Any = ref_keys if ref_keys else behavior_keys
    if not payload:
        raise ValueError("consolidation priority events require source_refs or behavior_event_ids")
    return stable_text_fingerprint(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        namespace="consolidation-priority-source",
        prefix="source",
        length=18,
    )


def _clamp(value: Any, default: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _decay_multiplier(age_days: float | int | None) -> float:
    if age_days is None:
        return 1.0
    age = max(0.0, float(age_days))
    return round(0.5 ** (age / DECAY_HALF_LIFE_DAYS), 6)


def _normalize_signal(
    value: Mapping[str, Any],
    *,
    policies: list[dict[str, Any]],
) -> dict[str, Any]:
    signal_type = str(value.get("signal_type") or "ordinary_turn")
    if signal_type not in SIGNAL_WEIGHTS:
        signal_type = "ordinary_turn"
    strength = _clamp(value.get("strength"), default=_clamp(value.get("score"), default=1.0))
    weight = SIGNAL_WEIGHTS[signal_type]
    summary = _sanitize_text(value.get("summary") or "", max_chars=260, policies=policies)
    return {
        "signal_type": signal_type,
        "strength": round(strength, 3),
        "weight": weight,
        "contribution": round(strength * weight, 6),
        "summary": summary,
    }


def _score_signals(signals: Sequence[Mapping[str, Any]], decay_multiplier: float) -> tuple[float, float]:
    raw = min(1.0, sum(float(item.get("contribution") or 0.0) for item in signals))
    effective = round(min(1.0, raw * decay_multiplier), 6)
    return round(raw, 6), effective


def build_consolidation_priority_event(
    *,
    thread_id: str,
    workspace: str,
    producer: str,
    signals: Sequence[Mapping[str, Any]],
    source_refs: Sequence[Mapping[str, Any]] | None = None,
    behavior_event_ids: Sequence[str] | None = None,
    source_state: str = "source_ref",
    age_days: float | int | None = None,
    created_at: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    if producer not in PRODUCERS:
        raise ValueError(f"producer must be one of {', '.join(sorted(PRODUCERS))}")
    if source_state not in SOURCE_STATES:
        raise ValueError(f"source_state must be one of {', '.join(sorted(SOURCE_STATES))}")
    policies: list[dict[str, Any]] = []
    refs = sanitize_source_refs(source_refs or [], policies=policies)
    behavior_ids = [
        _sanitize_text(item, max_chars=160, policies=policies)
        for item in behavior_event_ids or []
        if str(item or "")
    ][:12]
    source_key = source_key_for_refs(refs, behavior_event_ids=behavior_ids)
    normalized_signals = [
        _normalize_signal(signal, policies=policies)
        for signal in signals[:MAX_SIGNAL_COUNT]
        if isinstance(signal, Mapping)
    ]
    if not normalized_signals:
        raise ValueError("consolidation priority events require at least one signal")
    decay = _decay_multiplier(age_days)
    raw_score, effective_score = _score_signals(normalized_signals, decay)
    degraded = source_state in DEGRADED_SOURCE_STATES
    if degraded:
        effective_score = 0.0
    priority_reasons = [
        str(item.get("signal_type"))
        for item in normalized_signals
        if str(item.get("signal_type")) != "ordinary_turn" and float(item.get("contribution") or 0.0) > 0
    ]
    eligible = bool(effective_score >= MIN_REVIEW_SCORE and not degraded)
    thread = _sanitize_text(thread_id, max_chars=140, policies=policies)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "created_at": created_at or now_utc(),
        "prompt_version": PROMPT_VERSION,
        "event_id": event_id
        or stable_id("cons_pri", thread, producer, source_key, normalized_signals, created_at or ""),
        "thread_id": thread,
        **_workspace_fields(workspace, policies),
        "producer": producer,
        "source_key": source_key,
        "source_refs": refs,
        "behavior_event_ids": behavior_ids,
        "source_state": source_state,
        "signals": normalized_signals,
        "priority_reasons": unique_preserve(priority_reasons, limit=8),
        "priority_score": raw_score,
        "decay_multiplier": decay,
        "effective_priority_score": effective_score,
        "review_queue_eligible": eligible,
        "degraded": degraded,
        "degradation_reason": f"source_{source_state}" if degraded else "",
        "truth_status": "priority_observation_not_memory_truth",
        "status": "diagnostic",
        "source": "deterministic_consolidation_priority",
        "append_only": True,
        "formal_memory_promoted": False,
        "working_memory_promoted": False,
        "foreground_evidence": False,
        "user_visible_memory": False,
        "clean_source_mutated": False,
        "raw_rollout_mutated": False,
        "review_required_before_consolidation": True,
    }
    payload["privacy_scan"] = _privacy_scan(policies)
    return payload


def append_events(path: Path, events: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for event in events:
            if event.get("kind") != EVENT_KIND:
                raise ValueError(f"unsupported consolidation priority event kind: {event.get('kind')}")
            fh.write(json.dumps(storage_event_payload(event), ensure_ascii=False) + "\n")
            count += 1
    return count


def _storage_strings(values: Any, *, policies: list[dict[str, Any]], max_chars: int = 160) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [
        _sanitize_text(item, max_chars=max_chars, policies=policies)
        for item in values
        if str(item or "")
    ][:12]


def storage_event_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return the narrow append-only representation allowed to touch disk.

    The builder already sanitizes generated events, but append-only diagnostics
    are an audit boundary: future callers may pass richer rows with raw prompts,
    tool payloads, or credential-like helper fields. Keep this allowlist narrow
    so a convenience field cannot quietly become persistent memory.
    """

    policies: list[dict[str, Any]] = []
    payload: dict[str, Any] = {"kind": EVENT_KIND}

    for key in STORAGE_STRING_KEYS:
        if key in event:
            payload[key] = _sanitize_text(event.get(key), max_chars=220, policies=policies)
    for key in STORAGE_BOOL_KEYS:
        if key in event:
            payload[key] = bool(event.get(key))
    for key in STORAGE_NUMBER_KEYS:
        if key not in event:
            continue
        if key == "schema_version":
            payload[key] = int(event.get(key) or SCHEMA_VERSION)
        else:
            payload[key] = round(float(event.get(key) or 0.0), 6)

    payload["source_refs"] = sanitize_source_refs(event.get("source_refs") or [], policies=policies)
    payload["behavior_event_ids"] = _storage_strings(
        event.get("behavior_event_ids") or [],
        policies=policies,
    )
    payload["signals"] = [
        _normalize_signal(signal, policies=policies)
        for signal in (event.get("signals") or [])[:MAX_SIGNAL_COUNT]
        if isinstance(signal, Mapping)
    ]
    payload["priority_reasons"] = unique_preserve(
        _storage_strings(event.get("priority_reasons") or [], policies=policies),
        limit=8,
    )
    payload["privacy_scan"] = _storage_privacy_scan(event.get("privacy_scan"), policies)
    return payload


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def priority_queue_projection(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid_events = [event for event in events if event.get("kind") == EVENT_KIND]
    producer_counts = Counter(str(event.get("producer") or "unknown") for event in valid_events)
    degraded_count = sum(1 for event in valid_events if event.get("degraded"))
    queue: list[dict[str, Any]] = []
    for event in valid_events:
        if not event.get("review_queue_eligible"):
            continue
        queue.append(
            {
                "event_id": event.get("event_id"),
                "source_key": event.get("source_key"),
                "producer": event.get("producer"),
                "effective_priority_score": event.get("effective_priority_score"),
                "priority_reasons": event.get("priority_reasons") or [],
                "source_state": event.get("source_state"),
                "created_at": event.get("created_at"),
            }
        )
    queue.sort(
        key=lambda item: (
            float(item.get("effective_priority_score") or 0.0),
            str(item.get("created_at") or ""),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "kind": "aippocampus_consolidation_priority_report",
        "schema_version": SCHEMA_VERSION,
        "event_count": len(valid_events),
        "eligible_count": len(queue),
        "degraded_count": degraded_count,
        "producer_counts": dict(sorted(producer_counts.items())),
        "review_queue": queue,
        "caps_and_decay": {
            "max_signal_count": MAX_SIGNAL_COUNT,
            "min_review_score": MIN_REVIEW_SCORE,
            "decay_half_life_days": DECAY_HALF_LIFE_DAYS,
            "score_cap": 1.0,
        },
        "privacy_boundary": {
            "public_projection_omits_source_refs": True,
            "public_projection_omits_raw_prompt": True,
            "public_projection_omits_source_text": True,
            "public_projection_omits_local_paths": True,
        },
        "cannot_claim": [
            "biological_swr_equivalence",
            "awake_swr_default_behavior",
            "priority_event_is_not_source_truth",
            "priority_event_is_not_user_visible_memory",
            "formal_memory_promotion",
            "user_visible_lift",
        ],
    }


def priority_report(*, events_path: Path) -> dict[str, Any]:
    return priority_queue_projection(iter_jsonl(events_path))


def _refs_from_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = row.get("source_refs") or []
    if isinstance(refs, Mapping):
        return [dict(refs)]
    if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
        return [dict(item) for item in refs if isinstance(item, Mapping)]
    return []


def _source_state_from_row(row: Mapping[str, Any]) -> str:
    state = str(row.get("source_state") or row.get("status") or "source_ref")
    return state if state in SOURCE_STATES else "source_ref"


def _event_from_row(
    row: Mapping[str, Any],
    *,
    thread_id: str,
    workspace: str,
    created_at: str | None,
) -> dict[str, Any] | None:
    event_type = str(row.get("event_type") or row.get("signal_type") or row.get("finding_kind") or "")
    kind = str(row.get("kind") or "")
    signal_type = ""
    producer = ""
    strength = 1.0
    if event_type in {"user_correction", "correction", "superseding_decision"}:
        producer = "correction"
        signal_type = "correction" if event_type != "superseding_decision" else event_type
    elif event_type in {"rejected_route", "do_not_repeat", "route_rejected"}:
        producer = "rejected_route"
        signal_type = "rejected_route" if event_type == "route_rejected" else event_type
    elif event_type in {"source_conflict", "conflict"}:
        producer = "source_conflict"
        signal_type = "source_conflict"
    elif event_type in {"failed_test", "failed_command", "tool_failure", "failed_check"}:
        producer = "failure"
        signal_type = "failed_test" if event_type == "failed_check" else event_type
        if signal_type == "tool_failure":
            signal_type = "failed_command"
    elif event_type in {"rollback", "rollback_or_revert"}:
        producer = "failure"
        signal_type = "rollback_or_revert"
    elif kind == "cognitive_load_signal" or event_type == "cognitive_load":
        raw_signal = str(row.get("signal_type") or "cognitive_load")
        if raw_signal in {"failed_test", "failed_command", "rollback_or_revert"}:
            producer = "failure"
            signal_type = raw_signal
        elif raw_signal in {"rejected_route_retry", "rejected_route"}:
            producer = "rejected_route"
            signal_type = "rejected_route"
        elif raw_signal == "source_conflict":
            producer = "source_conflict"
            signal_type = "source_conflict"
        else:
            producer = "cognitive_load"
            signal_type = "cognitive_load"
        strength = _clamp(row.get("load_score") or row.get("score") or row.get("strength"), default=1.0)
    elif event_type in {"frontier_marker", "question_candidate", "theme_candidate", "question_link"}:
        producer = "frontier_question"
        signal_type = "frontier_question"
        strength = _clamp(row.get("confidence"), default=0.7)
    elif kind == "aippocampus_semantic_learning_hypothesis" or event_type == "semantic_learning_hypothesis":
        refs = _refs_from_row(row)
        status = str(row.get("status") or "").casefold()
        privacy = str(row.get("privacy") or row.get("privacy_domain") or "").casefold()
        if status in {"review_only", "retired", "stale", "blocked"} or privacy in {"private", "restricted", "blocked"}:
            return None
        if not refs:
            return None
        producer = "frontier_question"
        signal_type = "frontier_question"
        strength = _clamp(row.get("confidence"), default=0.55)
    else:
        return None

    behavior_ids = [
        str(row.get("event_id") or row.get("behavior_event_id") or "")
    ] if kind == "behavior_event" or row.get("event_id") else []
    return build_consolidation_priority_event(
        thread_id=thread_id,
        workspace=workspace,
        producer=producer,
        source_refs=_refs_from_row(row),
        behavior_event_ids=behavior_ids,
        source_state=_source_state_from_row(row),
        signals=[
            {
                "signal_type": signal_type,
                "strength": strength,
                "summary": row.get("summary") or row.get("message") or row.get("text") or "",
            }
        ],
        created_at=created_at,
    )


def events_from_candidate_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    thread_id: str,
    workspace: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        event = _event_from_row(row, thread_id=thread_id, workspace=workspace, created_at=created_at)
        if event is not None:
            events.append(event)
    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-input", required=True)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        report = priority_report(events_path=Path(args.events_input).resolve())
    except Exception as exc:
        if not args.json_output:
            raise
        report = cli_error_payload(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(report["error"]["code"])
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"events: {report['event_count']}")
        print(f"eligible: {report['eligible_count']}")
        print(f"degraded: {report['degraded_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
