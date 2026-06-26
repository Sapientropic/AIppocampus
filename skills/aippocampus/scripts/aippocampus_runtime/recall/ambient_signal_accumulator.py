"""Topic-signal accumulator for ambient recall thread caches."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    compact_text,
    now_utc,
    workspace_fingerprint,
    workspace_identity,
)
from aippocampus_runtime.io_integrity import atomic_write_json
from aippocampus_runtime.recall.cache_read_diagnostics import (
    CacheReadResult,
    read_json_cache,
)
from aippocampus_runtime.registry.api import unique_preserve

SIGNAL_ACCUMULATOR_SCHEMA_VERSION = 1
DEFAULT_SIGNAL_ACCUMULATOR_NAME = "ambient_signal_accumulator.json"
DEFAULT_MAX_SIGNAL_ENTRIES = 128
SIGNAL_ACCUMULATOR_NAME = "ambient_signal_accumulator"
SIGNAL_ACCUMULATOR_PATH_LABEL = DEFAULT_SIGNAL_ACCUMULATOR_NAME
POSITIVE_SIGNAL_OUTCOMES = {"weak_signal", "source_backed_hit", "candidate_backed_hit"}
NEGATIVE_SIGNAL_OUTCOMES = {"wrong_route", "stale_route", "ignored_route", "negative_roi"}


def _fingerprint(value: str, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").casefold().encode("utf-8")).hexdigest()
    return prefix + "_" + digest[:16]


def topic_signal_fingerprint(terms: list[str], *, limit: int = 8) -> str:
    cleaned: list[str] = []
    for term in terms:
        text = compact_text(str(term or "").strip(), 80)
        if len(text) < 2:
            continue
        cleaned.append(text.casefold())
    stable_terms = sorted(unique_preserve(cleaned, limit=limit))
    if not stable_terms:
        return "sig_empty"
    return _fingerprint("\n".join(stable_terms), prefix="sig")


def _empty_signal_accumulator() -> dict[str, Any]:
    return {
        "schema_version": SIGNAL_ACCUMULATOR_SCHEMA_VERSION,
        "updated_at": None,
        "entries": {},
    }


def _cache_diagnostic_detail(result: CacheReadResult) -> dict[str, Any] | None:
    return result.diagnostic.public_detail()


def _load_signal_accumulator_result(path: Path) -> CacheReadResult:
    result = read_json_cache(
        path,
        cache_name=SIGNAL_ACCUMULATOR_NAME,
        default_factory=_empty_signal_accumulator,
        path_label=SIGNAL_ACCUMULATOR_PATH_LABEL,
    )
    data = dict(result.data)
    entries = data.get("entries")
    if not isinstance(entries, dict):
        data["entries"] = {}
    data["schema_version"] = SIGNAL_ACCUMULATOR_SCHEMA_VERSION
    return CacheReadResult(data=data, diagnostic=result.diagnostic)


def _write_signal_accumulator(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data, indent=2)


def _signal_key(
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    topic_fingerprint: str,
) -> str:
    workspace_key = workspace_identity(workspace)
    return _fingerprint(
        f"{thread_id}\n{workspace_key}\n{topic_epoch}\n{topic_fingerprint}",
        prefix="sigkey",
    )


def _compact_reason_codes(values: list[str] | None) -> list[str]:
    return unique_preserve(
        [
            compact_text(str(value or "").strip().casefold(), 80)
            for value in values or []
            if str(value or "").strip()
        ],
        limit=8,
    )


def read_topic_signal_state(
    path: Path | str,
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    terms: list[str],
) -> dict[str, Any]:
    topic_fingerprint = topic_signal_fingerprint(terms)
    key = _signal_key(
        thread_id=thread_id,
        workspace=workspace,
        topic_epoch=topic_epoch,
        topic_fingerprint=topic_fingerprint,
    )
    result = _load_signal_accumulator_result(Path(path))
    data = result.data
    diagnostic = _cache_diagnostic_detail(result)
    if diagnostic:
        return {
            "status": "unavailable",
            "topic_epoch": topic_epoch,
            "topic_fingerprint": topic_fingerprint,
            "weak_signal_count": 0,
            "positive_strength": 0.0,
            "negative_strength": 0.0,
            "reason_codes": [],
            "cache_read_diagnostic": diagnostic,
        }
    entry = data.get("entries", {}).get(key)
    if not isinstance(entry, dict):
        return {
            "status": "miss",
            "topic_epoch": topic_epoch,
            "topic_fingerprint": topic_fingerprint,
            "weak_signal_count": 0,
            "positive_strength": 0.0,
            "negative_strength": 0.0,
            "reason_codes": [],
        }
    return {
        "status": "hit",
        "topic_epoch": topic_epoch,
        "topic_fingerprint": topic_fingerprint,
        "weak_signal_count": int(entry.get("weak_signal_count") or 0),
        "positive_strength": float(entry.get("positive_strength") or 0.0),
        "negative_strength": float(entry.get("negative_strength") or 0.0),
        "reason_codes": _compact_reason_codes(entry.get("reason_codes") or []),
        "updated_at": entry.get("updated_at"),
    }


def record_topic_signal(
    path: Path | str,
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    terms: list[str],
    outcome: str,
    reason_codes: list[str] | None = None,
    max_entries: int = DEFAULT_MAX_SIGNAL_ENTRIES,
) -> dict[str, Any]:
    topic_fingerprint = topic_signal_fingerprint(terms)
    if topic_fingerprint == "sig_empty":
        return {"status": "empty", "topic_epoch": topic_epoch, "topic_fingerprint": topic_fingerprint}
    target = Path(path)
    result = _load_signal_accumulator_result(target)
    data = result.data
    previous_diagnostic = _cache_diagnostic_detail(result)
    entries: dict[str, Any] = dict(data.get("entries") or {})
    key = _signal_key(
        thread_id=thread_id,
        workspace=workspace,
        topic_epoch=topic_epoch,
        topic_fingerprint=topic_fingerprint,
    )
    raw_prior = entries.get(key)
    prior: dict[str, Any] = raw_prior if isinstance(raw_prior, dict) else {}
    clean_outcome = compact_text(str(outcome or "").strip().casefold(), 80)
    positive_delta = 0.0
    negative_delta = 0.0
    weak_delta = 0
    if clean_outcome in POSITIVE_SIGNAL_OUTCOMES:
        positive_delta = 1.0 if clean_outcome == "weak_signal" else 1.5
        weak_delta = 1 if clean_outcome == "weak_signal" else 0
    elif clean_outcome in NEGATIVE_SIGNAL_OUTCOMES:
        negative_delta = 1.5 if clean_outcome in {"wrong_route", "stale_route"} else 1.0
    else:
        return {
            "status": "ignored_unknown_outcome",
            "topic_epoch": topic_epoch,
            "topic_fingerprint": topic_fingerprint,
        }
    updated = {
        "updated_at": now_utc(),
        "updated_unix": time.time(),
        "thread_fingerprint": _fingerprint(thread_id, prefix="thread"),
        "workspace_fingerprint": workspace_fingerprint(workspace),
        "topic_epoch": topic_epoch,
        "topic_fingerprint": topic_fingerprint,
        "weak_signal_count": int(prior.get("weak_signal_count") or 0) + weak_delta,
        "positive_strength": round(float(prior.get("positive_strength") or 0.0) + positive_delta, 3),
        "negative_strength": round(float(prior.get("negative_strength") or 0.0) + negative_delta, 3),
        "reason_codes": _compact_reason_codes(
            [*(prior.get("reason_codes") or []), clean_outcome, *(reason_codes or [])]
        ),
    }
    entries[key] = updated
    if len(entries) > max_entries:
        entries = dict(
            sorted(
                entries.items(),
                key=lambda item: float((item[1] or {}).get("updated_unix") or 0.0),
                reverse=True,
            )[:max_entries]
        )
    data = {
        "schema_version": SIGNAL_ACCUMULATOR_SCHEMA_VERSION,
        "updated_at": now_utc(),
        "entries": entries,
    }
    _write_signal_accumulator(target, data)
    return {
        "status": "written",
        "topic_epoch": topic_epoch,
        "topic_fingerprint": topic_fingerprint,
        "weak_signal_count": updated["weak_signal_count"],
        "positive_strength": updated["positive_strength"],
        "negative_strength": updated["negative_strength"],
        "reason_codes": updated["reason_codes"],
        **({"previous_cache_read_diagnostic": previous_diagnostic} if previous_diagnostic else {}),
    }
