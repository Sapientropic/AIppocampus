#!/usr/bin/env python3
"""Foreground-safe living cue cache packets for fresh-thread recall.

Living cue entries are produced by slower digestion layers and consumed by the
foreground hook as navigation only. They can bridge a user's remembered phrase
to source handles, but the packet deliberately withholds raw cue text and still
requires clean-source reopen before any specific memory claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import sanitize_external_model_text
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.source.io_kernel import source_ref_identity_key

LIVING_CUE_SCHEMA_VERSION = 1
LIVING_CUE_KIND = "aippocampus_living_cue_cache_entry"
LIVING_CUE_PACKET_KIND = "aippocampus_living_cue_packet"
DEFAULT_LIVING_CUES_NAME = "living_cue_cache.jsonl"

MAX_ALIASES = 12
MAX_SOURCE_REFS = 6
MAX_SELECTED = 3
MAX_CUE_LENGTH = 120
MIN_SELECT_CONFIDENCE = 0.55

SENSITIVITY_BUCKETS = {"safe", "caution", "suppress"}
FRESHNESS_BUCKETS = {"current", "possibly_stale", "stale", "superseded", "unknown"}
STATUS_BUCKETS = {"current", "staging", "temporary", "superseded", "rejected", "expired"}
STALE_FRESHNESS = {"stale", "superseded"}


def default_living_cues_path(registry_dir: Path) -> Path:
    return registry_dir.resolve() / DEFAULT_LIVING_CUES_NAME


def normalize_cue_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n\"'`.,;:!?，。；：！？、")
    if not text:
        return ""
    sanitized, policy = sanitize_external_model_text(text)
    if policy.get("hard_block"):
        return ""
    return sanitized[:MAX_CUE_LENGTH]


def _norm_match_text(value: Any) -> str:
    text = normalize_cue_text(value).casefold()
    text = re.sub(r"[\s\-_]+", " ", text)
    return text.strip()


def _float_bucket(value: Any, *, default: float = 0.0, min_value: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(max(min_value, min(1.0, number)), 4)


def _int_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _bucket(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key in (
        "source_id",
        "stable_source_id",
        "thread_key",
        "message_id",
        "turn_id",
        "turn_index",
        "source_line",
        "line",
        "phase",
    ):
        value = ref.get(key)
        if value in {None, ""}:
            continue
        out_key = "line" if key == "source_line" else key
        if out_key == "stable_source_id":
            out_key = "source_id"
        clean[out_key] = value
    return clean


def compact_source_refs(rows: list[Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = _source_ref(row)
        if not ref:
            continue
        key = source_ref_identity_key(ref)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= MAX_SOURCE_REFS:
            break
    return refs


def _entry_id(cue: str, aliases: list[str], source_refs: list[dict[str, Any]]) -> str:
    ref_material = [
        "|".join(str(part) for part in source_ref_identity_key(ref))
        for ref in source_refs[:MAX_SOURCE_REFS]
    ]
    material = json.dumps(
        {
            "cue": cue.casefold(),
            "aliases": [alias.casefold() for alias in aliases],
            "refs": ref_material,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "lc_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:18]


def normalize_living_cue_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Return one normalized living-cue cache row.

    This function preserves private cue text inside the cache entry because the
    hook needs it for local matching. Public packets and reports must call the
    selector/report helpers, which expose only ids, counts, and source handles.
    """

    cue = normalize_cue_text(row.get("cue"))
    aliases = unique_preserve(
        [normalize_cue_text(value) for value in row.get("aliases") or []],
        limit=MAX_ALIASES,
    )
    aliases = [alias for alias in aliases if alias and alias != cue]
    source_refs = compact_source_refs(list(row.get("source_refs") or []))
    confidence = _float_bucket(row.get("confidence"), default=0.0)
    sensitivity = _bucket(row.get("sensitivity"), SENSITIVITY_BUCKETS, "caution")
    freshness = _bucket(row.get("freshness"), FRESHNESS_BUCKETS, "unknown")
    status = _bucket(row.get("status") or row.get("currentness"), STATUS_BUCKETS, "staging")
    decay = _float_bucket(row.get("decay"), default=0.0)
    helpful = _int_count(row.get("last_helpful_count"))
    harmful = _int_count(row.get("last_harmful_count"))
    cue_id = str(row.get("cue_id") or "").strip() or _entry_id(cue, aliases, source_refs)
    return {
        "kind": LIVING_CUE_KIND,
        "schema_version": LIVING_CUE_SCHEMA_VERSION,
        "cue_id": cue_id,
        "cue": cue,
        "aliases": aliases,
        "source_refs": source_refs,
        "confidence": confidence,
        "sensitivity": sensitivity,
        "freshness": freshness,
        "status": status,
        "currentness": status,
        "decay": decay,
        "last_helpful_count": helpful,
        "last_harmful_count": harmful,
        "source_reopen_required": True,
        "source_boundary": {
            "living_cache_entries_are_navigation_only": True,
            "cue_and_alias_are_not_memory_truth": True,
            "source_refs_are_handles_not_claims": True,
        },
    }


def load_living_cue_entries(path: Path) -> list[dict[str, Any]]:
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
                rows.append(normalize_living_cue_entry(item))
    return rows


def _query_terms(prompt: str) -> list[str]:
    text = _norm_match_text(prompt)
    terms = [text] if text else []
    for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", text, flags=re.UNICODE):
        terms.append(token)
    return unique_preserve(terms, limit=32)


def _matched(entry: dict[str, Any], query_terms: list[str]) -> bool:
    if not query_terms:
        return False
    cue_terms = [_norm_match_text(entry.get("cue"))]
    cue_terms.extend(_norm_match_text(value) for value in entry.get("aliases") or [])
    cue_terms = [term for term in unique_preserve(cue_terms, limit=MAX_ALIASES + 1) if term]
    for query in query_terms:
        for cue in cue_terms:
            if not query or not cue:
                continue
            if cue in query:
                return True
    return False


def _score(entry: dict[str, Any]) -> float:
    helpful = _int_count(entry.get("last_helpful_count"))
    harmful = _int_count(entry.get("last_harmful_count"))
    score = float(entry.get("confidence") or 0.0) - float(entry.get("decay") or 0.0)
    score += min(helpful, 6) * 0.025
    score -= min(harmful, 6) * 0.05
    return round(score, 4)


def _is_stale(entry: dict[str, Any]) -> bool:
    return entry.get("status") in {"superseded", "rejected", "expired"} or (
        entry.get("freshness") in STALE_FRESHNESS
    )


def _is_temporary_or_overpersonalized(entry: dict[str, Any]) -> bool:
    return (
        entry.get("status") == "temporary"
        or entry.get("sensitivity") == "suppress"
        or _int_count(entry.get("last_harmful_count")) > _int_count(entry.get("last_helpful_count"))
    )


def _empty_packet(diagnostics: dict[str, Any]) -> dict[str, Any]:
    support = "suppressed" if diagnostics.get("cache_hit_count") else "silent_scent"
    return {
        "kind": LIVING_CUE_PACKET_KIND,
        "schema_version": LIVING_CUE_SCHEMA_VERSION,
        "decision": "skip",
        "support_level": support,
        "selected_count": 0,
        "candidate_refs": [],
        "matched_cue_ids": [],
        "diagnostics": diagnostics,
        "source_boundary": {
            "living_cache_entries_are_navigation_only": True,
            "source_reopen_required_before_claim": True,
            "packet_omits_raw_cue_text": True,
            "live_llm_not_required": True,
        },
    }


def _diagnostics() -> dict[str, Any]:
    return {
        "cache_hit_count": 0,
        "cache_miss_count": 0,
        "selected_count": 0,
        "stale_suppressed_count": 0,
        "temporary_suppressed_count": 0,
        "would_overpersonalize_count": 0,
        "low_confidence_suppressed_count": 0,
        "missing_source_ref_count": 0,
        "live_llm_call_count": 0,
        "output_boundary": "living_cue_packet_no_raw_cue_text",
    }


def select_living_cue_packet(
    prompt: str,
    entries: list[dict[str, Any]],
    *,
    max_entries: int = MAX_SELECTED,
    min_confidence: float = MIN_SELECT_CONFIDENCE,
) -> dict[str, Any]:
    """Select source-handle scent material from a local living cue cache."""

    normalized_entries = [normalize_living_cue_entry(entry) for entry in entries]
    query_terms = _query_terms(prompt)
    diagnostics = _diagnostics()
    scored: list[tuple[float, dict[str, Any]]] = []

    for entry in normalized_entries:
        if not _matched(entry, query_terms):
            continue
        diagnostics["cache_hit_count"] += 1
        if _is_stale(entry):
            diagnostics["stale_suppressed_count"] += 1
            continue
        if _is_temporary_or_overpersonalized(entry):
            if entry.get("status") == "temporary":
                diagnostics["temporary_suppressed_count"] += 1
            diagnostics["would_overpersonalize_count"] += 1
            continue
        if not entry.get("source_refs"):
            diagnostics["missing_source_ref_count"] += 1
            continue
        score = _score(entry)
        if score < min_confidence:
            diagnostics["low_confidence_suppressed_count"] += 1
            continue
        scored.append((score, entry))

    if diagnostics["cache_hit_count"] == 0:
        diagnostics["cache_miss_count"] = 1
    scored.sort(
        key=lambda item: (
            item[0],
            _int_count(item[1].get("last_helpful_count")),
            str(item[1].get("cue_id") or ""),
        ),
        reverse=True,
    )
    selected = [entry for _, entry in scored[: max(0, int(max_entries))]]
    if not selected:
        return _empty_packet(diagnostics)

    refs: list[dict[str, Any]] = []
    for entry in selected:
        refs.extend(entry.get("source_refs") or [])
    candidate_refs = compact_source_refs(refs)
    matched_cue_ids = [str(entry.get("cue_id") or "") for entry in selected if entry.get("cue_id")]
    diagnostics["selected_count"] = len(selected)
    return {
        "kind": LIVING_CUE_PACKET_KIND,
        "schema_version": LIVING_CUE_SCHEMA_VERSION,
        "decision": "scent",
        "support_level": "source_required" if candidate_refs else "soft_hypothesis",
        "selected_count": len(selected),
        "candidate_refs": candidate_refs,
        "matched_cue_ids": matched_cue_ids,
        "diagnostics": diagnostics,
        "source_boundary": {
            "living_cache_entries_are_navigation_only": True,
            "source_reopen_required_before_claim": True,
            "packet_omits_raw_cue_text": True,
            "live_llm_not_required": True,
        },
    }


def living_cue_cache_report(entries: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_entries = [normalize_living_cue_entry(entry) for entry in entries]
    status_counts: dict[str, int] = {}
    freshness_counts: dict[str, int] = {}
    sensitivity_counts: dict[str, int] = {}
    source_backed_count = 0
    for entry in normalized_entries:
        status = str(entry.get("status") or "unknown")
        freshness = str(entry.get("freshness") or "unknown")
        sensitivity = str(entry.get("sensitivity") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        freshness_counts[freshness] = freshness_counts.get(freshness, 0) + 1
        sensitivity_counts[sensitivity] = sensitivity_counts.get(sensitivity, 0) + 1
        if entry.get("source_refs"):
            source_backed_count += 1
    return {
        "kind": "aippocampus_living_cue_cache_report",
        "schema_version": LIVING_CUE_SCHEMA_VERSION,
        "entry_count": len(normalized_entries),
        "source_backed_count": source_backed_count,
        "status_counts": status_counts,
        "freshness_counts": freshness_counts,
        "sensitivity_counts": sensitivity_counts,
        "output_boundary": "living_cue_cache_report_counts_only",
    }


def demo_living_cue_entries() -> list[dict[str, Any]]:
    """Return public-safe fixtures for smoke tests and docs examples."""

    return [
        normalize_living_cue_entry(
            {
                "cue": "learned phrase alpha",
                "aliases": ["tree problem"],
                "source_refs": [
                    {
                        "source_id": "clean:demo:tree",
                        "thread_key": "session:demo-tree",
                        "message_id": "m7",
                        "line": 14,
                    }
                ],
                "confidence": 0.92,
                "sensitivity": "safe",
                "freshness": "current",
                "status": "current",
                "last_helpful_count": 2,
            }
        ),
        normalize_living_cue_entry(
            {
                "cue": "temporary mood beta",
                "aliases": ["stressed tonight"],
                "source_refs": [{"source_id": "clean:demo:mood", "thread_key": "session:mood"}],
                "confidence": 0.86,
                "sensitivity": "caution",
                "freshness": "current",
                "status": "temporary",
                "last_harmful_count": 1,
            }
        ),
    ]
