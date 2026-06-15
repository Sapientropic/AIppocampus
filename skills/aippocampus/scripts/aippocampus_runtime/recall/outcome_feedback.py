"""Privacy-safe local recall outcome feedback.

These events guide retrieval tuning only. They are not source evidence, do not
mutate ranking weights online, and must not store raw prompts or source text.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
AUTHORITY = "retrieval_tuning_only_not_source_truth"
PRIVACY_BOUNDARY = "local_counts_and_route_ids_no_raw_prompt_or_source_text"
ALLOWED_OUTCOMES = {
    "source_reopen_success",
    "wrong_route_drag",
    "ignored",
    "requery_after_miss",
    "blocked_boundary",
    "user_correction",
    "deepened",
    "superseded",
    "accepted_route",
    "dismissed_anti_nag",
    "prevented_failure",
    "stale_route_revival",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _shape_for_query(raw_query: str) -> dict[str, Any]:
    text = str(raw_query or "")
    latin = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", text)
    cjk_chars = re.findall(r"[\u3400-\u9fff]", text)
    digits = re.findall(r"\d", text)
    length = len(text)
    bucket = "empty" if length == 0 else "short" if length <= 80 else "medium" if length <= 240 else "long"
    return {
        "length_bucket": bucket,
        "latin_token_count": min(len(latin), 99),
        "cjk_char_count": min(len(cjk_chars), 999),
        "digit_count": min(len(digits), 99),
        "has_question": bool(re.search(r"[?？]|\b(where|what|when|how|why|which)\b", text, re.I)),
        "has_source_ref_shape": bool(re.search(r"\bmsg[-_:]?\d+\b|#L\d+\b|\bline\s+\d+\b", text, re.I)),
    }


def _fingerprint(value: Any, *, length: int = 16) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:length]


def _candidate_refs(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for candidate in candidates:
        ref: dict[str, Any] = {}
        for key in ("route_id", "source_ref_id", "segment_id", "route_family"):
            value = candidate.get(key)
            if value not in (None, "", []):
                ref[key] = str(value)
        if ref:
            refs.append(ref)
    return refs[:24]


def build_recall_outcome_event(
    *,
    raw_query: str,
    run_id: str,
    route_family: str,
    scoring_policy: str,
    delivered_candidates: Iterable[Mapping[str, Any]],
    outcome_signal: str,
    selected_route_id: str | None = None,
    currentness: str | None = None,
    reopened: bool | None = None,
    deepened: bool | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    shape = _shape_for_query(raw_query)
    signal = outcome_signal if outcome_signal in ALLOWED_OUTCOMES else "ignored"
    candidate_refs = _candidate_refs(delivered_candidates)
    return {
        "kind": "aippocampus_recall_outcome_feedback",
        "schema_version": SCHEMA_VERSION,
        "event_id": "rof_" + _fingerprint([run_id, route_family, scoring_policy, shape, signal], length=20),
        "created_at": timestamp or _now_utc(),
        "run_id": str(run_id or ""),
        "query_shape": shape,
        "query_shape_hash": "sha256:" + _fingerprint(shape, length=20),
        "route_family": str(route_family or "unknown"),
        "scoring_policy": str(scoring_policy or "unknown"),
        "currentness": str(currentness or "unknown"),
        "delivered_candidates": candidate_refs,
        "delivered_candidate_count": len(candidate_refs),
        "selected_route_id": str(selected_route_id or ""),
        "reopened": bool(reopened) if reopened is not None else signal == "source_reopen_success",
        "deepened": bool(deepened) if deepened is not None else signal == "deepened",
        "outcome_signal": signal,
        "authority": AUTHORITY,
        "privacy_boundary": PRIVACY_BOUNDARY,
        "source_truth": False,
        "online_weight_mutation": False,
    }


def _assert_event_safe(event: Mapping[str, Any]) -> None:
    raw = json.dumps(event, ensure_ascii=False, sort_keys=True)
    forbidden = ("raw_query", "prompt", "snippet", "source_text", "provider_output")
    if any(key in event for key in forbidden):
        raise ValueError("recall outcome feedback cannot store raw prompt/source fields")
    if re.search(r"\bsk-[A-Za-z0-9_-]{6,}\b|api[_-]?key|token=", raw, re.I):
        raise ValueError("recall outcome feedback contains secret-shaped material")


def write_recall_outcome_event(path: str | Path, event: Mapping[str, Any]) -> None:
    _assert_event_safe(event)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(event), ensure_ascii=False, sort_keys=True) + "\n")


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except OSError:
        return []
    return rows


def _increment(group: dict[str, Counter[str]], key: str, outcome: str) -> None:
    group[str(key or "unknown")][str(outcome or "unknown")] += 1


def recall_outcome_report(path: str | Path) -> dict[str, Any]:
    events = _read_events(Path(path))
    by_route_family: dict[str, Counter[str]] = defaultdict(Counter)
    by_scoring_policy: dict[str, Counter[str]] = defaultdict(Counter)
    by_currentness: dict[str, Counter[str]] = defaultdict(Counter)
    by_query_shape: Counter[str] = Counter()
    for event in events:
        outcome = str(event.get("outcome_signal") or "unknown")
        _increment(by_route_family, str(event.get("route_family") or "unknown"), outcome)
        _increment(by_scoring_policy, str(event.get("scoring_policy") or "unknown"), outcome)
        _increment(by_currentness, str(event.get("currentness") or "unknown"), outcome)
        by_query_shape[str(event.get("query_shape_hash") or "unknown")] += 1
    repeated = [
        {"query_shape": shape, "count": count}
        for shape, count in by_query_shape.most_common()
    ]
    return {
        "kind": "aippocampus_recall_outcome_report",
        "schema_version": SCHEMA_VERSION,
        "total_events": len(events),
        "by_route_family": {key: dict(counter) for key, counter in by_route_family.items()},
        "by_scoring_policy": {key: dict(counter) for key, counter in by_scoring_policy.items()},
        "by_currentness": {key: dict(counter) for key, counter in by_currentness.items()},
        "repeated_query_shapes": repeated,
        "authority": AUTHORITY,
        "privacy_boundary": PRIVACY_BOUNDARY,
    }
