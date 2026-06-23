#!/usr/bin/env python3
"""Local multilingual cue cache for semantic recall.

Semantic model aliases are useful, but a one-off model phrase should not become
foreground policy. This module stores repeated, source-backed cue hits as a
small data layer that the semantic gate can reuse as trigger context. The cues
remain search hints only; clean source and source refs stay the truth surface.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, sanitize_external_model_text
from aippocampus_runtime.registry.api import registry_paths, unique_preserve
from aippocampus_runtime.source.io_kernel import (
    load_jsonl_dict_rows,
    source_ref_key,
    write_jsonl_dict_rows,
)

SEMANTIC_CUE_SCHEMA_VERSION = 1
SEMANTIC_CUE_KIND = "aippocampus_semantic_cue"
DEFAULT_SEMANTIC_CUES_NAME = "semantic_cues.jsonl"
MIN_PROMOTION_HITS = 2
MAX_CUE_LENGTH = 96
MAX_SOURCE_REFS = 8
MAX_PROMPT_HASHES = 8
MAX_FALSE_POSITIVE_REASONS = 4

SCRIPT_RANGES = (
    ("Hani", 0x4E00, 0x9FFF),
    ("Hira", 0x3040, 0x309F),
    ("Kana", 0x30A0, 0x30FF),
    ("Hang", 0xAC00, 0xD7AF),
    ("Arab", 0x0600, 0x06FF),
    ("Cyrl", 0x0400, 0x04FF),
    ("Thai", 0x0E00, 0x0E7F),
    ("Deva", 0x0900, 0x097F),
    ("Hebr", 0x0590, 0x05FF),
    ("Grek", 0x0370, 0x03FF),
)


def default_semantic_cues_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_SEMANTIC_CUES_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_SEMANTIC_CUES_NAME


def normalize_cue(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n\"'`.,;:!?，。；：！？、")


def prompt_hash(prompt: str) -> str:
    normalized = re.sub(r"\s+", " ", str(prompt or "")).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def cue_key(cue: str, route: str) -> str:
    material = f"{route.strip().casefold()}\n{normalize_cue(cue).casefold()}"
    return "sc_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:18]


def detect_script(text: str) -> str:
    scripts: set[str] = set()
    for ch in text:
        if ch.isspace() or unicodedata.category(ch).startswith(("P", "S", "N")):
            continue
        code = ord(ch)
        for script, start, end in SCRIPT_RANGES:
            if start <= code <= end:
                scripts.add(script)
                break
        else:
            name = unicodedata.name(ch, "")
            if "LATIN" in name:
                scripts.add("Latn")
    if not scripts:
        return "Zyyy"
    if len(scripts) == 1:
        return next(iter(scripts))
    return "Mixed"


def language_hint_for_script(script: str) -> str:
    return {
        "Arab": "und-Arab",
        "Cyrl": "und-Cyrl",
        "Deva": "und-Deva",
        "Grek": "und-Grek",
        "Hang": "ko",
        "Hani": "und-Hani",
        "Hebr": "und-Hebr",
        "Hira": "ja",
        "Kana": "ja",
        "Latn": "und-Latn",
        "Thai": "th",
    }.get(script, "und")


def compact_source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "thread_key",
        "title",
        "project_label",
        "message_id",
        "turn_id",
        "turn_index",
        "source_line",
        "line",
        "source",
    )
    return {key: ref.get(key) for key in allowed if ref.get(key) not in {None, ""}}


def merge_source_refs(existing: list[Any], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in [*existing, *incoming]:
        if not isinstance(raw, dict):
            continue
        ref = compact_source_ref(raw)
        if not ref:
            continue
        key = source_ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= MAX_SOURCE_REFS:
            break
    return refs


def all_semantic_cues(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for row in load_jsonl_dict_rows(path).rows
        if row.get("kind") == SEMANTIC_CUE_KIND
        and row.get("schema_version") == SEMANTIC_CUE_SCHEMA_VERSION
    ]


def cue_is_active(row: dict[str, Any]) -> bool:
    hit_count = int(row.get("hit_count") or 0)
    false_positive_count = int(row.get("false_positive_count") or 0)
    confidence = float(row.get("confidence") or 0.0)
    return bool(
        row.get("status") == "active"
        and hit_count >= MIN_PROMOTION_HITS
        and false_positive_count < hit_count
        and confidence >= 0.55
        and row.get("source_refs")
    )


def refresh_status(row: dict[str, Any]) -> dict[str, Any]:
    hit_count = int(row.get("hit_count") or 0)
    false_positive_count = int(row.get("false_positive_count") or 0)
    confidence = float(row.get("confidence") or 0.0)
    has_refs = bool(row.get("source_refs"))
    if hit_count >= MIN_PROMOTION_HITS and false_positive_count < hit_count and has_refs and confidence >= 0.55:
        row["status"] = "active"
    else:
        row["status"] = "staging"
    return row


def load_semantic_cues(path: Path) -> list[dict[str, Any]]:
    rows = [row for row in all_semantic_cues(path) if cue_is_active(row)]
    rows.sort(
        key=lambda row: (
            int(row.get("hit_count") or 0) - int(row.get("false_positive_count") or 0),
            float(row.get("confidence") or 0.0),
            str(row.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    return rows


def semantic_aliases_from_result(result: dict[str, Any]) -> list[str]:
    if not result or not result.get("available"):
        return []
    if str(result.get("decision") or "") not in {"background_only", "scent", "evidence"}:
        return []
    aliases: list[str] = []
    for value in result.get("query_aliases") or []:
        cue = normalize_cue(value)
        if not (2 <= len(cue) <= MAX_CUE_LENGTH):
            continue
        sanitized, policy = sanitize_external_model_text(cue)
        if policy.get("hard_block") or policy.get("redacted"):
            continue
        aliases.append(sanitized)
    return unique_preserve(aliases, limit=24)


def _rows_by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("cue_id") or ""): dict(row) for row in rows if row.get("cue_id")}


def _sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows.sort(
        key=lambda row: (
            row.get("status") == "active",
            int(row.get("hit_count") or 0) - int(row.get("false_positive_count") or 0),
            float(row.get("confidence") or 0.0),
            str(row.get("cue") or ""),
        ),
        reverse=True,
    )
    return rows


def record_semantic_cue_hits(
    path: Path,
    *,
    prompt: str,
    semantic_result: dict[str, Any],
    source_refs: list[dict[str, Any]],
    route: str = "semantic_gate",
) -> dict[str, Any]:
    refs = merge_source_refs([], source_refs)
    aliases = semantic_aliases_from_result(semantic_result)
    if not refs or not aliases:
        return {"path": str(path), "updated_count": 0, "active_count": 0, "cues": []}

    now = now_utc()
    rows = _rows_by_key(all_semantic_cues(path))
    confidence = float(semantic_result.get("confidence") or 0.0)
    prompt_id = prompt_hash(prompt)
    updated_ids: list[str] = []
    for alias in aliases:
        script = detect_script(alias)
        key = cue_key(alias, route)
        row = rows.get(key) or {
            "schema_version": SEMANTIC_CUE_SCHEMA_VERSION,
            "kind": SEMANTIC_CUE_KIND,
            "cue_id": key,
            "cue": alias,
            "route": route,
            "script": script,
            "language": language_hint_for_script(script),
            "status": "staging",
            "created_at": now,
            "hit_count": 0,
            "false_positive_count": 0,
            "source_refs": [],
            "prompt_hashes": [],
        }
        row["cue"] = alias
        row["script"] = script
        row["language"] = language_hint_for_script(script)
        row["updated_at"] = now
        row["last_seen_at"] = now
        row["last_seen_unix"] = time.time()
        row["hit_count"] = int(row.get("hit_count") or 0) + 1
        row["confidence"] = round(max(float(row.get("confidence") or 0.0), confidence), 4)
        row["source_refs"] = merge_source_refs(list(row.get("source_refs") or []), refs)
        row["prompt_hashes"] = unique_preserve(
            [str(value) for value in row.get("prompt_hashes") or []] + [prompt_id],
            limit=MAX_PROMPT_HASHES,
        )
        row["when_to_use"] = (
            "Use as a multilingual semantic recall cue only; search source before presenting facts."
        )
        row["when_not_to_use"] = (
            "Do not treat the cue itself as evidence, and demote it when false positives accumulate."
        )
        rows[key] = refresh_status(row)
        updated_ids.append(key)

    all_rows = _sorted_rows(list(rows.values()))
    write_jsonl_dict_rows(path, all_rows, sort_keys=True)
    active_count = sum(1 for row in all_rows if row.get("cue_id") in updated_ids and cue_is_active(row))
    return {
        "path": str(path),
        "updated_count": len(updated_ids),
        "active_count": active_count,
        "cues": [rows[key]["cue"] for key in updated_ids],
    }


def record_semantic_cue_misses(
    path: Path,
    *,
    cues: list[str],
    reason: str = "",
) -> dict[str, Any]:
    wanted = {normalize_cue(cue).casefold() for cue in cues if normalize_cue(cue)}
    rows = _rows_by_key(all_semantic_cues(path))
    updated = 0
    for row in rows.values():
        if str(row.get("cue") or "").casefold() not in wanted:
            continue
        row["false_positive_count"] = int(row.get("false_positive_count") or 0) + 1
        row["updated_at"] = now_utc()
        if reason:
            row["false_positive_reasons"] = unique_preserve(
                [str(value) for value in row.get("false_positive_reasons") or []]
                + [compact_text(reason, 120)],
                limit=MAX_FALSE_POSITIVE_REASONS,
            )
        refresh_status(row)
        updated += 1
    if updated:
        write_jsonl_dict_rows(path, _sorted_rows(list(rows.values())), sort_keys=True)
    return {"path": str(path), "updated_count": updated}


def _net_hit_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    if value <= 4:
        return "2_4"
    return "5_plus"


def semantic_cue_cache_report(path: Path | None) -> dict[str, Any]:
    rows = all_semantic_cues(path) if path else []
    status_counts: dict[str, int] = {}
    net_hit_buckets: dict[str, int] = {}
    active_count = 0
    source_backed_count = 0
    false_positive_total = 0
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        hit_count = int(row.get("hit_count") or 0)
        false_positive_count = int(row.get("false_positive_count") or 0)
        false_positive_total += false_positive_count
        net = hit_count - false_positive_count
        bucket = _net_hit_bucket(net)
        net_hit_buckets[bucket] = net_hit_buckets.get(bucket, 0) + 1
        if cue_is_active(row):
            active_count += 1
        if row.get("source_refs"):
            source_backed_count += 1
    return {
        "kind": "aippocampus_semantic_cue_cache_report",
        "schema_version": SEMANTIC_CUE_SCHEMA_VERSION,
        "entry_count": len(rows),
        "active_count": active_count,
        "staging_count": status_counts.get("staging", 0),
        "source_backed_count": source_backed_count,
        "false_positive_count": false_positive_total,
        "status_counts": status_counts,
        "net_hit_buckets": net_hit_buckets,
        "output_boundary": "semantic_cue_cache_report_counts_only",
    }


def semantic_cue_triggers(path: Path | None, *, limit: int = 64) -> list[dict[str, Any]]:
    if not path:
        return []
    triggers: list[dict[str, Any]] = []
    for row in load_semantic_cues(path)[:limit]:
        cue = str(row.get("cue") or "")
        triggers.append(
            {
                "source": "semantic_cue_cache",
                "title": cue,
                "aliases": unique_preserve([cue], limit=4),
                "when_to_use": row.get("when_to_use"),
                "when_not_to_use": row.get("when_not_to_use"),
                "confidence": row.get("confidence"),
                "route": row.get("route"),
                "language": row.get("language"),
                "script": row.get("script"),
                "hit_count": row.get("hit_count"),
                "false_positive_count": row.get("false_positive_count"),
                "source_refs": row.get("source_refs") or [],
            }
        )
    return triggers
