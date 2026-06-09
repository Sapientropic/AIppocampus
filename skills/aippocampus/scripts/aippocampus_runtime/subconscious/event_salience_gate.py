"""Deterministic event-salience gate for subconscious job intake.

The gate is deliberately cheaper and lower authority than subconscious findings:
it only prioritizes which clean-source turns deserve model-backed candidate
extraction. Clean source remains the truth, and a skipped event remains
available through audit/source search.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "aippocampus.event_salience.v1"
DEFAULT_SELECT_THRESHOLD = 0.55
MAX_SOURCE_REFS = 8

LOW_INFORMATION_NOISE_KEYS = {
    "ok",
    "okay",
    "thanks",
    "thankyou",
    "收到",
    "继续",
    "明白",
    "了解",
    "好",
    "好的",
    "好开干",
}

SIGNAL_RULES: tuple[dict[str, Any], ...] = (
    {
        "event_kind": "explicit_user_correction",
        "weight": 0.82,
        "reason_code": "explicit_correction_cue",
        "patterns": (
            r"\bcorrection\b",
            r"\bi meant\b",
            r"\bnot .{0,60}\buse\b",
            r"\bnot .{0,60}\bbut\b",
            r"\binstead of\b",
            r"纠正",
            r"不是.{0,40}是",
            r"改成",
        ),
    },
    {
        "event_kind": "rejected_route_or_failed_assumption",
        "weight": 0.76,
        "reason_code": "rejected_route_or_assumption_cue",
        "patterns": (
            r"\brejected route\b",
            r"\bwrong assumption\b",
            r"\bnot the right path\b",
            r"\bdo not take\b",
            r"\bdon't take\b",
            r"不要走",
            r"别走",
            r"路径不对",
            r"假设错",
        ),
    },
    {
        "event_kind": "unresolved_frontier_or_blocker",
        "weight": 0.74,
        "reason_code": "frontier_or_blocker_cue",
        "patterns": (
            r"\bblocked\b",
            r"\bblocker\b",
            r"\bunresolved\b",
            r"\bnot solved\b",
            r"\bbefore claiming\b",
            r"\bbefore closing\b",
            r"\bneed external evidence\b",
            r"\bneeds external evidence\b",
            r"外部证据",
            r"未解决",
            r"卡住",
            r"不能关闭",
        ),
    },
    {
        "event_kind": "durable_preference_or_style",
        "weight": 0.70,
        "reason_code": "preference_or_style_cue",
        "patterns": (
            r"\bi prefer\b",
            r"\bmy preference\b",
            r"\bdefault to\b",
            r"\balways\b",
            r"\bby default\b",
            r"偏好",
            r"默认",
            r"以后都",
            r"尽量",
        ),
    },
    {
        "event_kind": "scope_boundary_clarification",
        "weight": 0.66,
        "reason_code": "scope_boundary_cue",
        "patterns": (
            r"\bscope\b",
            r"\bnon-goal\b",
            r"\bnon goal\b",
            r"\bonly\b",
            r"\bdo not\b",
            r"\bdon't\b",
            r"\bboundary\b",
            r"边界",
            r"范围",
            r"只做",
            r"不要",
        ),
    },
    {
        "event_kind": "supersession_or_currentness",
        "weight": 0.70,
        "reason_code": "supersession_or_currentness_cue",
        "patterns": (
            r"\bsuperseded\b",
            r"\bcurrent\b",
            r"\blatest\b",
            r"\bnow use\b",
            r"\buse .{0,60}\bnow\b",
            r"\breplaced\b",
            r"\bold route\b",
            r"过时",
            r"现在用",
            r"改用",
            r"取代",
        ),
    },
    {
        "event_kind": "failed_command_or_test",
        "weight": 0.78,
        "reason_code": "failed_command_or_test_cue",
        "patterns": (
            r"\btest failed\b",
            r"\btests failed\b",
            r"\bfailed with exit code\b",
            r"\bred test\b",
            r"\btraceback\b",
            r"\bexception\b",
            r"\berror:\b",
            r"\brollback\b",
            r"测试失败",
            r"红测",
            r"回滚",
            r"报错",
        ),
    },
)


def normalized_noise_key(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold(), flags=re.UNICODE)


def token_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text, flags=re.UNICODE))


def _compile_patterns(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, flags=re.IGNORECASE | re.UNICODE) for pattern in patterns)


COMPILED_RULES = tuple(
    {
        **rule,
        "compiled": _compile_patterns(tuple(str(pattern) for pattern in rule["patterns"])),
    }
    for rule in SIGNAL_RULES
)


def stable_event_id(turn: Mapping[str, Any], event_kind: str) -> str:
    refs = compact_source_refs(turn)
    parts = [
        str(event_kind),
        str(turn.get("thread_key") or ""),
        str(turn.get("turn_id") or ""),
        str(turn.get("turn_index") or ""),
        str(turn.get("turn_ref") or ""),
        json.dumps(refs, sort_keys=True, ensure_ascii=True),
    ]
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"evt_sal_{digest}"


def compact_source_refs(turn: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in turn.get("source_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        compact_ref: dict[str, Any] = {}
        for key in (
            "turn_ref",
            "thread_key",
            "message_id",
            "turn_id",
            "turn_index",
            "source_line",
            "role",
            "phase",
        ):
            value = ref.get(key)
            if value is not None and str(value) != "":
                compact_ref[key] = value
        if compact_ref:
            refs.append(compact_ref)
    if not refs:
        fallback: dict[str, Any] = {}
        for key in ("turn_ref", "thread_key", "turn_id", "turn_index", "user_line"):
            value = turn.get(key)
            if value is not None and str(value) != "":
                fallback[key] = value
        if fallback:
            refs.append(fallback)
    for ref in refs:
        if turn.get("turn_ref") and "turn_ref" not in ref:
            ref["turn_ref"] = turn.get("turn_ref")
    return refs[:MAX_SOURCE_REFS]


def salience_bucket(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= DEFAULT_SELECT_THRESHOLD:
        return "medium"
    if score > 0:
        return "low"
    return "noise"


def _matched_signals(text: str) -> list[tuple[str, float, str]]:
    matches: list[tuple[str, float, str]] = []
    for rule in COMPILED_RULES:
        if any(pattern.search(text) for pattern in rule["compiled"]):
            matches.append(
                (
                    str(rule["event_kind"]),
                    float(rule["weight"]),
                    str(rule["reason_code"]),
                )
            )
    return matches


def classify_event_salience(turn: Mapping[str, Any]) -> dict[str, Any]:
    user_text = str(turn.get("user") or "").strip()
    assistant_text = str(turn.get("assistant") or "").strip()
    combined = f"{user_text}\n{assistant_text}".strip()
    refs = compact_source_refs(turn)
    signals = _matched_signals(combined.casefold())
    reason_codes = [reason for _, _, reason in signals]
    score = min(1.0, sum(weight for _, weight, _ in signals))
    low_information = (
        normalized_noise_key(user_text) in LOW_INFORMATION_NOISE_KEYS
        or (token_count(user_text) <= 2 and not signals)
    )

    if not signals:
        event_kind = "low_information_noise" if low_information else "ordinary_context"
    else:
        event_kind = max(signals, key=lambda item: item[1])[0]
    if low_information and not signals:
        reason_codes.append("low_information_noise")

    action = "select" if score >= DEFAULT_SELECT_THRESHOLD else "skip"
    if low_information and not signals:
        action = "skip"
    if not reason_codes:
        reason_codes.append("ordinary_context_no_salience_cue")
    skip_reason = "" if action == "select" else reason_codes[-1]

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": stable_event_id(turn, event_kind),
        "authority": "navigation_intake_metadata",
        "event_kind": event_kind,
        "candidate_action": action,
        "salience_score": round(score, 4),
        "salience_bucket": salience_bucket(score),
        "reason_codes": tuple(dict.fromkeys(reason_codes)),
        "skip_reason": skip_reason,
        "source_refs": refs,
    }


def public_event_salience_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(report.get("enabled")),
        "input_turn_count": int(report.get("input_turn_count") or 0),
        "selected_turn_count": int(report.get("selected_turn_count") or 0),
        "candidate_reduction_count": int(report.get("candidate_reduction_count") or 0),
        "missed_high_signal_count": int(report.get("missed_high_signal_count") or 0),
        "source_ref_coverage_rate": float(report.get("source_ref_coverage_rate") or 0.0),
        "selected_by_bucket": dict(report.get("selected_by_bucket") or {}),
        "selected_event_kind_counts": dict(report.get("selected_event_kind_counts") or {}),
        "skipped_by_reason": dict(report.get("skipped_by_reason") or {}),
        "output_boundary": "event_salience_is_navigation_intake_metadata_not_source_truth",
    }


def event_salience_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected_rows = [row for row in rows if row.get("candidate_action") == "select"]
    skipped_rows = [row for row in rows if row.get("candidate_action") != "select"]
    selected_by_bucket: dict[str, int] = {}
    selected_event_kind_counts: dict[str, int] = {}
    skipped_by_reason: dict[str, int] = {}
    for row in selected_rows:
        bucket = str(row.get("salience_bucket") or "unknown")
        selected_by_bucket[bucket] = selected_by_bucket.get(bucket, 0) + 1
        event_kind = str(row.get("event_kind") or "unknown")
        selected_event_kind_counts[event_kind] = selected_event_kind_counts.get(event_kind, 0) + 1
    for row in skipped_rows:
        reason = str(row.get("skip_reason") or "unknown")
        skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1
    source_ref_count = sum(1 for row in rows if row.get("source_refs"))
    missed_high_signal_count = sum(
        1
        for row in skipped_rows
        if float(row.get("salience_score") or 0.0) >= DEFAULT_SELECT_THRESHOLD
    )
    return {
        "enabled": True,
        "input_turn_count": len(rows),
        "selected_turn_count": len(selected_rows),
        "candidate_reduction_count": len(skipped_rows),
        "missed_high_signal_count": missed_high_signal_count,
        "source_ref_coverage_rate": round(source_ref_count / len(rows), 4) if rows else 1.0,
        "selected_by_bucket": selected_by_bucket,
        "selected_event_kind_counts": selected_event_kind_counts,
        "skipped_by_reason": skipped_by_reason,
        "sidecar_rows": rows,
        "public_summary": public_event_salience_summary(
            {
                "enabled": True,
                "input_turn_count": len(rows),
                "selected_turn_count": len(selected_rows),
                "candidate_reduction_count": len(skipped_rows),
                "missed_high_signal_count": missed_high_signal_count,
                "source_ref_coverage_rate": round(source_ref_count / len(rows), 4)
                if rows
                else 1.0,
                "selected_by_bucket": selected_by_bucket,
                "selected_event_kind_counts": selected_event_kind_counts,
                "skipped_by_reason": skipped_by_reason,
            }
        ),
    }


def filter_salient_turns(
    turns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [classify_event_salience(turn) for turn in turns]
    by_ref = {
        str(turn.get("turn_ref") or ""): turn
        for turn in turns
        if str(turn.get("turn_ref") or "").strip()
    }
    selected: list[dict[str, Any]] = []
    for row in rows:
        if row.get("candidate_action") != "select":
            continue
        source_refs = row.get("source_refs") or []
        turn_ref = ""
        if source_refs and isinstance(source_refs[0], Mapping):
            turn_ref = str(source_refs[0].get("turn_ref") or "")
        if turn_ref and turn_ref in by_ref:
            selected.append(by_ref[turn_ref])
    return selected, event_salience_report(rows)


def merge_event_salience_reports(reports: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows_by_id: dict[str, dict[str, Any]] = {}
    for report in reports:
        for row in report.get("sidecar_rows") or []:
            if not isinstance(row, dict):
                continue
            event_id = str(row.get("event_id") or "")
            if event_id:
                rows_by_id[event_id] = row
    if not rows_by_id:
        return {"enabled": False}
    return event_salience_report(list(rows_by_id.values()))


def write_event_salience_sidecar(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
