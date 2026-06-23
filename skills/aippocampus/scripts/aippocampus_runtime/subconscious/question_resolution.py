#!/usr/bin/env python3
"""Deterministic resolution signals for tracked questions.

This runner only recognizes explicit user follow-up turns such as "solved" or
"不再需要". It intentionally avoids inferring resolution from assistant answers
or generic positive language: a resolution signal is a health/reporting hint,
not a durable memory fact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.question.source_refs import (
    SourceRefIndex,
    build_source_ref_index,
    compact_source_refs,
    source_ref_key,
)
from aippocampus_runtime.question.tracking import (
    FINDING_ROW_KIND,
    QUESTION_CANDIDATE_KIND,
    QUESTION_LINK_KIND,
    candidate_from_row,
    load_tracking_rows,
)
from aippocampus_runtime.question.tracking_types import (
    normalize_tokens,
    parse_timestamp,
    stable_digest,
)
from aippocampus_runtime.registry.api import load_registry, unique_preserve
from aippocampus_runtime.source.search import iter_clean_messages

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-question-resolution-v1"
QUESTION_RESOLUTION_KIND = "question_resolution_signal"

RESOLUTION_PHRASES = (
    ("已经解决", "explicit_user_resolution"),
    ("已解决", "explicit_user_resolution"),
    ("解决了", "explicit_user_resolution"),
    ("搞定了", "explicit_user_resolution"),
    ("明白了", "explicit_user_resolution"),
    ("找到答案了", "explicit_user_resolution"),
    ("不用再追", "explicit_user_no_longer_needed"),
    ("不用管了", "explicit_user_no_longer_needed"),
    ("不再需要", "explicit_user_no_longer_needed"),
    ("resolved", "explicit_user_resolution"),
    ("solved", "explicit_user_resolution"),
    ("figured it out", "explicit_user_resolution"),
    ("got my answer", "explicit_user_resolution"),
    ("answered now", "explicit_user_resolution"),
    ("no longer need", "explicit_user_no_longer_needed"),
    ("not needed anymore", "explicit_user_no_longer_needed"),
)

NEGATIVE_RESOLUTION_PHRASES = (
    "还没解决",
    "没有解决",
    "未解决",
    "仍未解决",
    "不是解决了",
    "not resolved",
    "not solved",
    "still unresolved",
    "still not resolved",
    "still need",
)


@dataclass(frozen=True)
class CleanMessage:
    thread_key: str
    role: str
    text: str
    source_ref: dict[str, Any]
    timestamp: str
    source_line: int | None
    turn_index: int | None


@dataclass(frozen=True)
class TrackedQuestion:
    subject_id: str
    unit_type: str
    title: str
    question_ids: tuple[str, ...]
    source_finding_ids: tuple[str, ...]
    terms: tuple[str, ...]
    source_refs: tuple[dict[str, Any], ...]
    last_seen: str


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_ref_from_message(thread: Mapping[str, Any], message: Mapping[str, Any]) -> dict[str, Any] | None:
    thread_key = str(thread.get("thread_key") or "")
    if not thread_key:
        return None
    ref = {
        "thread_key": thread_key,
        "title": thread.get("title"),
        "project_label": thread.get("project_label"),
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "turn_index": message.get("turn_index"),
        "source_line": message.get("source_line"),
        "timestamp": message.get("timestamp"),
    }
    refs = compact_source_refs([ref])
    return refs[0] if refs else None


def load_registry_clean_messages(registry_path: Path | None) -> list[CleanMessage]:
    if registry_path is None or not registry_path.exists():
        return []
    registry = load_registry(registry_path)
    messages: list[CleanMessage] = []
    for thread in registry.get("threads") or []:
        if not isinstance(thread, Mapping):
            continue
        messages_path_value = (thread.get("paths") or {}).get("clean_source_messages_jsonl")
        if not messages_path_value:
            continue
        messages_path = Path(str(messages_path_value))
        if not messages_path.exists():
            continue
        thread_key = str(thread.get("thread_key") or "")
        if not thread_key:
            continue
        for message in iter_clean_messages(messages_path):
            ref = _source_ref_from_message(thread, message)
            text = str(message.get("text") or "")
            if not ref or not text:
                continue
            messages.append(
                CleanMessage(
                    thread_key=thread_key,
                    role=str(message.get("role") or ""),
                    text=text,
                    source_ref=ref,
                    timestamp=str(message.get("timestamp") or ""),
                    source_line=_safe_int(message.get("source_line")),
                    turn_index=_safe_int(message.get("turn_index")),
                )
            )
    return messages


def _terms_from_values(*values: Any, limit: int = 18) -> tuple[str, ...]:
    chunks: list[str] = []
    for value in values:
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, Iterable):
            chunks.extend(str(item or "") for item in value)
    return tuple(unique_preserve(list(normalize_tokens(*chunks)), limit=limit))


def _date_bounds(refs: Iterable[Mapping[str, Any]]) -> tuple[str, str]:
    timestamps = [
        parsed
        for parsed in (parse_timestamp(str(ref.get("timestamp") or "")) for ref in refs)
        if parsed
    ]
    if not timestamps:
        return "", ""
    return (
        min(timestamps).isoformat().replace("+00:00", "Z"),
        max(timestamps).isoformat().replace("+00:00", "Z"),
    )


def _link_question_from_row(
    row: Mapping[str, Any], *, source_index: SourceRefIndex | None
) -> TrackedQuestion | None:
    refs = compact_source_refs(row.get("source_refs"), source_index=source_index)
    if not refs:
        return None
    linked = [item for item in row.get("linked_questions") or [] if isinstance(item, Mapping)]
    source_finding_ids = tuple(
        unique_preserve(
            [str(value) for value in row.get("question_source_finding_ids") or [] if str(value)]
            + [
                str(item.get("source_finding_id") or "")
                for item in linked
                if item.get("source_finding_id")
            ],
            limit=32,
        )
    )
    question_ids = tuple(
        unique_preserve(
            [str(item.get("question_id") or "") for item in linked if item.get("question_id")],
            limit=32,
        )
    )
    subject_id = compact_text(
        str(row.get("question_cluster_id") or row.get("fingerprint") or "")
        or stable_digest("|".join(question_ids + source_finding_ids), prefix="ql"),
        80,
    )
    title = compact_text(
        str(row.get("linked_question_short") or row.get("title") or "question link"),
        140,
    )
    _first_seen, last_seen = _date_bounds(refs)
    terms = _terms_from_values(
        title,
        row.get("summary"),
        row.get("concepts"),
        [
            item.get("question_text") or item.get("question_short") or ""
            for item in linked
            if isinstance(item, Mapping)
        ],
        [
            " ".join(str(value) for value in item.get("what_features") or [])
            for item in linked
            if isinstance(item, Mapping)
        ],
    )
    if not terms:
        return None
    return TrackedQuestion(
        subject_id=subject_id,
        unit_type=QUESTION_LINK_KIND,
        title=title,
        question_ids=question_ids,
        source_finding_ids=source_finding_ids,
        terms=terms,
        source_refs=refs,
        last_seen=compact_text(str(row.get("last_seen") or last_seen), 80),
    )


def tracked_questions_from_rows(
    rows: Iterable[Mapping[str, Any]], *, source_index: SourceRefIndex | None = None
) -> list[TrackedQuestion]:
    questions: list[TrackedQuestion] = []
    linked_source_ids: set[str] = set()
    candidates: list[TrackedQuestion] = []
    for row in rows:
        if row.get("kind") != FINDING_ROW_KIND:
            continue
        finding_kind = str(row.get("finding_kind") or "")
        if finding_kind == QUESTION_LINK_KIND:
            question = _link_question_from_row(row, source_index=source_index)
            if question:
                questions.append(question)
                linked_source_ids.update(question.source_finding_ids)
            continue
        if finding_kind == QUESTION_CANDIDATE_KIND:
            candidate = candidate_from_row(row, source_index=source_index)
            if not candidate:
                continue
            terms = _terms_from_values(
                candidate.question_text,
                candidate.question_short,
                candidate.title,
                candidate.summary,
                candidate.concepts,
                candidate.what_features,
                candidate.where_context,
            )
            if not terms:
                continue
            candidates.append(
                TrackedQuestion(
                    subject_id=candidate.question_id,
                    unit_type=QUESTION_CANDIDATE_KIND,
                    title=candidate.question_short or candidate.title,
                    question_ids=(candidate.question_id,),
                    source_finding_ids=(candidate.finding_id,),
                    terms=terms,
                    source_refs=candidate.source_refs,
                    last_seen=candidate.first_seen,
                )
            )
    questions.extend(
        candidate for candidate in candidates if candidate.source_finding_ids[0] not in linked_source_ids
    )
    questions.sort(key=lambda item: (item.last_seen, item.subject_id))
    return questions


def resolution_phrase(text: str) -> dict[str, str] | None:
    lowered = text.casefold()
    if any(phrase in lowered for phrase in NEGATIVE_RESOLUTION_PHRASES):
        return None
    for phrase, kind in RESOLUTION_PHRASES:
        if phrase.casefold() in lowered:
            return {"phrase": phrase, "kind": kind}
    return None


def _message_after_question(question: TrackedQuestion, message: CleanMessage) -> bool:
    refs = [ref for ref in question.source_refs if str(ref.get("thread_key") or "") == message.thread_key]
    if not refs:
        return False
    message_time = parse_timestamp(message.timestamp)
    ref_times = [
        parsed
        for parsed in (parse_timestamp(str(ref.get("timestamp") or "")) for ref in refs)
        if parsed
    ]
    if message_time and ref_times:
        return message_time > max(ref_times)
    ref_lines: list[int] = []
    for ref in refs:
        value = _safe_int(ref.get("source_line"))
        if value is not None:
            ref_lines.append(value)
    if message.source_line is not None and ref_lines:
        return message.source_line > max(ref_lines)
    ref_turns: list[int] = []
    for ref in refs:
        value = _safe_int(ref.get("turn_index"))
        if value is not None:
            ref_turns.append(value)
    if message.turn_index is not None and ref_turns:
        return message.turn_index > max(ref_turns)
    return False


def _matched_terms(question: TrackedQuestion, text: str) -> tuple[str, ...]:
    text_tokens = set(normalize_tokens(text))
    return tuple(term for term in question.terms if term in text_tokens)


def build_resolution_signal(
    question: TrackedQuestion, message: CleanMessage, phrase_match: Mapping[str, str], matched_terms: tuple[str, ...]
) -> dict[str, Any]:
    source_key = ":".join(source_ref_key(message.source_ref))
    phrase_kind = str(phrase_match.get("kind") or "explicit_user_resolution")
    fingerprint = stable_digest(
        question.subject_id,
        source_key,
        phrase_kind,
        prefix="qr",
        length=20,
    )
    resolved_at = message.timestamp or now_utc()
    return {
        "job": "question_resolution",
        "kind": QUESTION_RESOLUTION_KIND,
        "finding_kind": QUESTION_RESOLUTION_KIND,
        "title": compact_text(f"Question resolved: {question.title}", 140),
        "summary": "A later user clean-source turn explicitly resolved or dismissed the tracked question.",
        "confidence": 0.86,
        "source_refs": [message.source_ref],
        "resolution_source_refs": [message.source_ref],
        "resolution_kind": phrase_kind,
        "resolved_subject_id": question.subject_id,
        "resolved_unit_type": question.unit_type,
        "resolved_question_ids": list(question.question_ids),
        "resolved_source_finding_ids": list(question.source_finding_ids),
        "resolved_at": resolved_at,
        "match_evidence": {
            "method": "deterministic_explicit_followup_resolution_v1",
            "message_role": message.role,
            "matched_term_count": len(matched_terms),
            "resolution_phrase_kind": phrase_kind,
            "same_thread_followup": True,
            "raw_text_emitted": False,
        },
        "fingerprint": fingerprint,
        "quality": {
            "bucket": "usable",
            "promotion_readiness": 0.86,
            "signals": {
                "source_ref_count": 1,
                "matched_term_count": len(matched_terms),
            },
        },
    }


def build_resolution_signals(
    questions: Iterable[TrackedQuestion], messages: Iterable[CleanMessage]
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    user_messages = [message for message in messages if message.role.casefold() == "user"]
    for question in questions:
        for message in user_messages:
            phrase_match = resolution_phrase(message.text)
            if not phrase_match:
                continue
            if not _message_after_question(question, message):
                continue
            matched_terms = _matched_terms(question, message.text)
            if not matched_terms:
                continue
            signal = build_resolution_signal(question, message, phrase_match, matched_terms)
            fingerprint = str(signal.get("fingerprint") or "")
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            signals.append(signal)
            break
    return signals


def existing_resolution_fingerprints(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    fingerprints: set[str] = set()
    for row in rows:
        if row.get("kind") != FINDING_ROW_KIND:
            continue
        if str(row.get("finding_kind") or "") != QUESTION_RESOLUTION_KIND:
            continue
        fingerprint = str(row.get("fingerprint") or "")
        if fingerprint:
            fingerprints.add(fingerprint)
    return fingerprints


def append_resolution_signals(
    path: Path,
    signals: Iterable[Mapping[str, Any]],
    *,
    batch_id: str,
    source: str = "deterministic_question_resolution",
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for signal in signals:
            payload = dict(signal)
            payload.pop("kind", None)
            payload.pop("finding_kind", None)
            event = {
                "schema_version": SCHEMA_VERSION,
                "kind": FINDING_ROW_KIND,
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": "deterministic",
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": {"provider": "deterministic"},
                "usage": {},
                "finding_kind": QUESTION_RESOLUTION_KIND,
                **payload,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            count += 1
    return count


def run_question_resolution(
    *,
    jobs_path: Path,
    registry_path: Path | None,
    output_path: Path | None = None,
    no_write: bool = False,
) -> dict[str, Any]:
    output = output_path or jobs_path
    rows = load_tracking_rows(jobs_path)
    source_index = build_source_ref_index(registry_path)
    questions = tracked_questions_from_rows(rows, source_index=source_index)
    messages = load_registry_clean_messages(registry_path)
    signals = build_resolution_signals(questions, messages)
    existing_rows = rows if output == jobs_path else load_tracking_rows(output)
    existing = existing_resolution_fingerprints(existing_rows)
    fresh_signals = [
        signal for signal in signals if str(signal.get("fingerprint") or "") not in existing
    ]
    batch_id = f"question-resolution-{hashlib.sha1(now_utc().encode('utf-8')).hexdigest()[:12]}"
    wrote_count = 0
    if not no_write and fresh_signals:
        wrote_count = append_resolution_signals(output, fresh_signals, batch_id=batch_id)
    return {
        "ok": True,
        "job": "question_resolution",
        "jobs_input": str(jobs_path),
        "registry": str(registry_path) if registry_path else None,
        "output": str(output),
        "source_ref_resolution": "registry_clean_source" if source_index else "shape_only",
        "tracked_question_count": len(questions),
        "clean_message_count": len(messages),
        "candidate_signal_count": len(signals),
        "fresh_signal_count": len(fresh_signals),
        "duplicate_signal_count": len(signals) - len(fresh_signals),
        "wrote_count": wrote_count,
        "raw_text_emitted": False,
        "cannot_claim": [
            "does not infer resolution from assistant answers",
            "does not prove user-visible recall quality",
            "does not resolve questions without explicit user follow-up wording and source refs",
        ],
        "signals": fresh_signals if no_write else [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    payload = run_question_resolution(
        jobs_path=Path(args.jobs),
        registry_path=Path(args.registry),
        output_path=Path(args.output) if args.output else None,
        no_write=args.no_write,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "question resolution: "
            f"{payload['fresh_signal_count']} fresh signals, "
            f"{payload['wrote_count']} written"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
