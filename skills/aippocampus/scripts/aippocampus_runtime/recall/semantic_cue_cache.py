#!/usr/bin/env python3
"""Local multilingual cue cache for semantic recall.

Model aliases and explicit recall terms are navigation metadata until
source-open or feedback promotes them.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, sanitize_external_model_text
from aippocampus_runtime.recall.semantic.confidence_policy import meets_active_cue_confidence
from aippocampus_runtime.registry.api import registry_paths, unique_preserve
from aippocampus_runtime.source.agent_trace_admission import learning_priority_for_signal
from aippocampus_runtime.source.io_kernel import (
    clean_source_refs,
    load_jsonl_dict_rows,
    write_jsonl_dict_rows,
)

SEMANTIC_CUE_SCHEMA_VERSION = 1
SEMANTIC_CUE_KIND = "aippocampus_semantic_cue"
RECALL_POSITION_SCHEMA_VERSION = 1
RECALL_POSITION_KIND = "aippocampus_recall_semantic_position"
DEFAULT_SEMANTIC_CUES_NAME = "semantic_cues.jsonl"
MIN_PROMOTION_HITS = 2
MAX_CUE_LENGTH = 96
MAX_SOURCE_REFS = 8
MAX_PROMPT_HASHES = 8
MAX_FALSE_POSITIVE_REASONS = 4
MAX_POSITION_TERMS = 18
MAX_POSITION_INTENTS = 6
MIN_ACTIVE_CUE_FEEDBACK_SCORE = 2
POSITIVE_RECALL_FEEDBACK_SIGNALS = {
    "source_reopen_success",
    "source_open",
    "user_confirmed",
    "explicit_useful",
    "prevented_failure",
}
HARD_NEGATIVE_RECALL_FEEDBACK_SIGNALS = {
    "wrong_route_drag",
    "wrong_route",
    "dismissed",
    "ignored",
    "manual_search_after_route",
    "context_suppressed",
    "blocked",
}
PARKED_RECALL_FEEDBACK_SIGNALS = {
    "parked",
    "park",
    "privacy_blocked",
    "stale",
    "off_phase",
    "needs_refine",
    "duplicate",
}
SENSITIVE_TERM_RE = re.compile(
    r"\b[A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|ACCESS_KEY)[A-Za-z0-9_]*\s*=\s*\S+",
    re.I,
)

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


def source_generation_hash(value: Any) -> str:
    if not value:
        return ""
    material = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def cue_key(cue: str, route: str) -> str:
    material = f"{route.strip().casefold()}\n{normalize_cue(cue).casefold()}"
    return "sc_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:18]


def recall_position_key(*, prompt_id: str, thread_key: str, workspace_key: str) -> str:
    material = f"{thread_key.strip().casefold()}\n{workspace_key.strip().casefold()}\n{prompt_id}"
    return "rsp_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:18]


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


def merge_semantic_source_refs(
    existing: list[Any],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return clean_source_refs(
        [*existing, *incoming],
        fields=(
            "thread_key",
            "title",
            "project_label",
            "message_id",
            "turn_id",
            "turn_index",
            "source_line",
            "line",
            "source",
        ),
        limit=MAX_SOURCE_REFS,
        require_thread=False,
    )


def all_semantic_cues(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for row in load_jsonl_dict_rows(path).rows
        if row.get("kind") == SEMANTIC_CUE_KIND
        and row.get("schema_version") == SEMANTIC_CUE_SCHEMA_VERSION
    ]


def all_recall_positions(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for row in load_jsonl_dict_rows(path).rows
        if row.get("kind") == RECALL_POSITION_KIND
        and row.get("schema_version") == RECALL_POSITION_SCHEMA_VERSION
    ]


def cue_is_active(row: dict[str, Any]) -> bool:
    hit_count = int(row.get("hit_count") or 0)
    explicit_useful_count = int(row.get("explicit_useful_feedback_count") or 0)
    confidence = float(row.get("confidence") or 0.0)
    return bool(
        row.get("status") == "active"
        and (hit_count >= MIN_PROMOTION_HITS or explicit_useful_count > 0)
        and cue_feedback_allows_foreground(row)
        and meets_active_cue_confidence(confidence)
        and row.get("source_refs")
    )


def cue_feedback_score(row: dict[str, Any]) -> int:
    hit_count = int(row.get("hit_count") or 0)
    explicit_useful_count = int(row.get("explicit_useful_feedback_count") or 0)
    false_positive_count = int(row.get("false_positive_count") or 0)
    return hit_count + explicit_useful_count * 2 - false_positive_count


def cue_feedback_allows_foreground(row: dict[str, Any]) -> bool:
    if int(row.get("false_positive_count") or 0) < 2:
        return cue_feedback_score(row) > 0
    return cue_feedback_score(row) >= MIN_ACTIVE_CUE_FEEDBACK_SCORE


def refresh_status(row: dict[str, Any]) -> dict[str, Any]:
    hit_count = int(row.get("hit_count") or 0)
    explicit_useful_count = int(row.get("explicit_useful_feedback_count") or 0)
    confidence = float(row.get("confidence") or 0.0)
    has_refs = bool(row.get("source_refs"))
    last_signal = str(row.get("last_feedback_signal") or "").casefold()
    feedback_score = cue_feedback_score(row)
    row["feedback_score"] = feedback_score
    row["active_feedback_score_threshold"] = MIN_ACTIVE_CUE_FEEDBACK_SCORE
    if last_signal in HARD_NEGATIVE_RECALL_FEEDBACK_SIGNALS:
        row["status"] = "suppressed_hard_negative"
        row["candidate_lifecycle_state"] = "rejected_hard_negative"
        return row
    if last_signal in PARKED_RECALL_FEEDBACK_SIGNALS:
        row["status"] = "parked_recheck"
        row["candidate_lifecycle_state"] = "parked_recheck"
        return row
    if last_signal == "expired":
        row["status"] = "expired_recheck"
        row["candidate_lifecycle_state"] = "expired_recheck"
        return row
    if (
        (hit_count >= MIN_PROMOTION_HITS or explicit_useful_count > 0)
        and cue_feedback_allows_foreground(row)
        and has_refs
        and meets_active_cue_confidence(confidence)
    ):
        row["status"] = "active"
        row["candidate_lifecycle_state"] = "actionable_reopenable_route"
    else:
        row["status"] = "staging"
        row["candidate_lifecycle_state"] = "draft_candidate_staging"
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


def rows_by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("cue_id") or ""): dict(row) for row in rows if row.get("cue_id")}


def _position_rows_by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("position_id") or ""): dict(row)
        for row in rows
        if row.get("position_id")
    }


def non_cue_rows(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for row in load_jsonl_dict_rows(path).rows
        if not (
            row.get("kind") == SEMANTIC_CUE_KIND
            and row.get("schema_version") == SEMANTIC_CUE_SCHEMA_VERSION
        )
    ]


def _non_position_rows(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for row in load_jsonl_dict_rows(path).rows
        if not (
            row.get("kind") == RECALL_POSITION_KIND
            and row.get("schema_version") == RECALL_POSITION_SCHEMA_VERSION
        )
    ]


def sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _sorted_position_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows.sort(
        key=lambda row: (
            str(row.get("last_seen_at") or ""),
            int(row.get("attempt_count") or 0),
            str(row.get("position_id") or ""),
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
    refs = merge_semantic_source_refs([], source_refs)
    aliases = semantic_aliases_from_result(semantic_result)
    if not refs or not aliases:
        return {"path": str(path), "updated_count": 0, "active_count": 0, "cues": []}

    now = now_utc()
    rows = rows_by_key(all_semantic_cues(path))
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
        row["source_refs"] = merge_semantic_source_refs(list(row.get("source_refs") or []), refs)
        row["prompt_hashes"] = unique_preserve(
            [str(value) for value in row.get("prompt_hashes") or []] + [prompt_id],
            limit=MAX_PROMPT_HASHES,
        )
        row["when_to_use"] = "multilingual_semantic_recall_cue_after_source_search"
        row["when_not_to_use"] = "cue_text_is_not_evidence_demote_on_false_positive_pressure"
        row["training_role"] = "positive_demo"
        row["trace_admission_level"] = "reopenable_route"
        row["source_reopen_required_before_claim"] = True
        row["candidate_lifecycle_state"] = (
            "actionable_reopenable_route"
            if int(row.get("hit_count") or 0) >= MIN_PROMOTION_HITS
            else "draft_candidate_staging"
        )
        row["learning_priority"] = learning_priority_for_signal(
            {
                "source_ref_count": len(row.get("source_refs") or []),
                "opened_anchor_hits": len(row.get("source_refs") or []),
                "cue_frequency": int(row.get("hit_count") or 0),
                "multilingual": script != "Latn" or len(aliases) > 1,
                "alias_like": route != "exact_text",
            }
        )
        rows[key] = refresh_status(row)
        updated_ids.append(key)

    all_rows = sorted_rows(list(rows.values()))
    write_jsonl_dict_rows(path, [*non_cue_rows(path), *all_rows], sort_keys=True)
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
    rows = rows_by_key(all_semantic_cues(path))
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
        write_jsonl_dict_rows(
            path,
            [*non_cue_rows(path), *sorted_rows(list(rows.values()))],
            sort_keys=True,
        )
    return {"path": str(path), "updated_count": updated}


def _intent_buckets(terms: list[str]) -> list[str]:
    buckets: list[str] = []
    folded = " ".join(terms).casefold()
    if any(value in folded for value in ("issue", "pr", "ci", "test", "merge", "close")):
        buckets.append("project_work")
    if any(value in folded for value in ("recall", "source", "anchor", "memory", "召回", "记忆", "锚点")):
        buckets.append("continuity_recall")
    if any(value in folded for value in ("mcp", "cli", "hook", "foreground", "前台")):
        buckets.append("agent_surface")
    if any(value in folded for value in ("ux", "用户", "体验", "noise", "noisy")):
        buckets.append("ux_feedback")
    if any(value in folded for value in ("graph", "semantic", "alias", "fuzzy", "语义")):
        buckets.append("semantic_navigation")
    return unique_preserve(buckets, limit=MAX_POSITION_INTENTS) or ["continuity_positioning"]


def safe_position_terms(terms: list[str]) -> list[str]:
    safe_terms: list[str] = []
    for term in terms:
        cue = normalize_cue(term)
        if not (2 <= len(cue) <= MAX_CUE_LENGTH):
            continue
        if SENSITIVE_TERM_RE.search(cue) or re.search(
            r"\b(token|secret|password|api[_-]?key|access[_-]?key)\b",
            cue,
            re.I,
        ):
            continue
        sanitized, policy = sanitize_external_model_text(cue)
        if policy.get("hard_block") or policy.get("redacted"):
            continue
        safe_terms.append(sanitized)
    return unique_preserve(safe_terms, limit=MAX_POSITION_TERMS)


def _thread_key_digest(thread_key: str) -> str:
    return hashlib.sha256(str(thread_key or "").encode("utf-8")).hexdigest()[:16]


def record_recall_semantic_position(
    path: Path,
    *,
    prompt: str,
    terms: list[str],
    cwd: str | Path | None = None,
    thread_key: str = "",
    source_generation: Any = None,
    source_refs: list[dict[str, Any]] | None = None,
    recall_status: str = "",
    route_count: int = 0,
) -> dict[str, Any]:
    """Write direction-only rows for explicit recall cue decomposition.

    Rows share semantic-cue storage but use a separate kind/status from
    source-backed alias promotion.
    """

    safe_terms = safe_position_terms(terms)
    prompt_id = prompt_hash(prompt)
    if not prompt_id or not safe_terms:
        return {"path": str(path), "updated_count": 0, "position_count": len(all_recall_positions(path))}
    workspace_key = str(cwd or "")
    thread_value = normalize_cue(thread_key) or "current_thread"
    position_id = recall_position_key(
        prompt_id=prompt_id,
        thread_key=thread_value,
        workspace_key=workspace_key,
    )
    now = now_utc()
    rows = _position_rows_by_key(all_recall_positions(path))
    existing = rows.get(position_id) or {
        "schema_version": RECALL_POSITION_SCHEMA_VERSION,
        "kind": RECALL_POSITION_KIND,
        "position_id": position_id,
        "created_at": now,
        "prompt_hashes": [],
        "attempt_count": 0,
        "source_refs": [],
    }
    refs = clean_source_refs(
        source_refs or [],
        fields=(
            "thread_key",
            "message_id",
            "turn_id",
            "turn_index",
            "source_line",
            "line",
            "source",
        ),
        limit=MAX_SOURCE_REFS,
        require_thread=False,
    )
    script_counts: dict[str, int] = {}
    for term in safe_terms:
        script = detect_script(term)
        script_counts[script] = script_counts.get(script, 0) + 1
    existing["updated_at"] = now
    existing["last_seen_at"] = now
    existing["last_seen_unix"] = time.time()
    existing["attempt_count"] = int(existing.get("attempt_count") or 0) + 1
    existing["status"] = "staging"
    existing["authority_level"] = "direction_only"
    existing["trace_admission_level"] = "direction_only"
    existing["source_reopen_required_before_claim"] = True
    existing["candidate_lifecycle_state"] = "draft_candidate_staging"
    existing["training_role"] = "replay_sample"
    existing["cue_decomposition_boundary"] = "prompt_hash_and_sanitized_terms_only"
    existing["prompt_hashes"] = unique_preserve(
        [str(value) for value in existing.get("prompt_hashes") or []] + [prompt_id],
        limit=MAX_PROMPT_HASHES,
    )
    existing["terms"] = unique_preserve(
        [str(value) for value in existing.get("terms") or []] + safe_terms,
        limit=MAX_POSITION_TERMS,
    )
    existing["script_counts"] = script_counts
    existing["language_buckets"] = unique_preserve(
        [language_hint_for_script(script) for script in script_counts],
        limit=MAX_POSITION_INTENTS,
    )
    existing["intent_buckets"] = _intent_buckets(existing["terms"])
    existing["recall_status_counts"] = {
        **dict(existing.get("recall_status_counts") or {}),
        str(recall_status or "unknown"): int(
            (existing.get("recall_status_counts") or {}).get(str(recall_status or "unknown")) or 0
        )
        + 1,
    }
    existing["last_route_count"] = max(0, int(route_count or 0))
    existing["route_count_bucket"] = (
        "no_hit" if int(route_count or 0) <= 0 else "one_hit" if int(route_count or 0) == 1 else "multi_hit"
    )
    existing["thread_key_digest"] = _thread_key_digest(thread_value)
    existing["thread_key"] = thread_value if not re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", thread_value) else None
    generation_hash = source_generation_hash(source_generation)
    if generation_hash:
        existing["source_generation_hash"] = generation_hash
    if refs:
        existing["source_refs"] = merge_semantic_source_refs(
            list(existing.get("source_refs") or []),
            refs,
        )
    rows[position_id] = existing
    position_rows = _sorted_position_rows(list(rows.values()))
    write_jsonl_dict_rows(path, [*_non_position_rows(path), *position_rows], sort_keys=True)
    return {
        "path": str(path),
        "updated_count": 1,
        "position_count": len(position_rows),
        "terms_recorded_count": len(existing.get("terms") or []),
        "status": existing["status"],
        "authority_level": existing["authority_level"],
    }


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
    position_rows = all_recall_positions(path) if path else []
    status_counts: dict[str, int] = {}
    position_status_counts: dict[str, int] = {}
    position_role_counts: dict[str, int] = {}
    net_hit_buckets: dict[str, int] = {}
    training_role_counts: dict[str, int] = {}
    learning_priority_counts: dict[str, int] = {}
    active_count = 0
    source_backed_count = 0
    false_positive_total = 0
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        training_role = str(row.get("training_role") or "none")
        training_role_counts[training_role] = training_role_counts.get(training_role, 0) + 1
        priority_bucket = str((row.get("learning_priority") or {}).get("bucket") or "low")
        learning_priority_counts[priority_bucket] = learning_priority_counts.get(priority_bucket, 0) + 1
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
    for row in position_rows:
        status = str(row.get("status") or "unknown")
        position_status_counts[status] = position_status_counts.get(status, 0) + 1
        role = str(row.get("training_role") or "none")
        position_role_counts[role] = position_role_counts.get(role, 0) + 1
    return {
        "kind": "aippocampus_semantic_cue_cache_report",
        "schema_version": SEMANTIC_CUE_SCHEMA_VERSION,
        "entry_count": len(rows),
        "recall_position_count": len(position_rows),
        "active_count": active_count,
        "staging_count": status_counts.get("staging", 0),
        "recall_position_status_counts": position_status_counts,
        "recall_position_training_role_counts": position_role_counts,
        "source_backed_count": source_backed_count,
        "false_positive_count": false_positive_total,
        "status_counts": status_counts,
        "training_role_counts": training_role_counts,
        "learning_priority_counts": learning_priority_counts,
        "net_hit_buckets": net_hit_buckets,
        "output_boundary": "semantic_cue_cache_report_counts_only",
    }


def semantic_position_matches(
    path: Path | None,
    *,
    terms: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not path:
        return []
    query_terms = [normalize_cue(term).casefold() for term in terms if normalize_cue(term)]
    if not query_terms:
        return []
    matches: list[dict[str, Any]] = []
    for row in all_recall_positions(path):
        row_terms = [str(term or "").casefold() for term in row.get("terms") or []]
        matched = [
            term
            for term in query_terms
            if any(term and (term == row_term or term in row_term or row_term in term) for row_term in row_terms)
        ]
        if not matched:
            continue
        matches.append(
            {
                "kind": "recall_semantic_position_match",
                "position_id": row.get("position_id"),
                "status": row.get("status"),
                "authority_level": row.get("authority_level") or "direction_only",
                "training_role": row.get("training_role") or "replay_sample",
                "candidate_lifecycle_state": row.get("candidate_lifecycle_state")
                or "draft_candidate_staging",
                "matched_term_count": len(unique_preserve(matched)),
                "term_count": len(row_terms),
                "intent_buckets": row.get("intent_buckets") or [],
                "thread_key": row.get("thread_key"),
                "source_refs": row.get("source_refs") or [],
                "source_reopen_required_before_claim": True,
                "claim_boundary": "semantic_positioning_navigation_only_no_claim",
            }
        )
    matches.sort(
        key=lambda item: (
            int(item.get("matched_term_count") or 0),
            int(item.get("term_count") or 0),
        ),
        reverse=True,
    )
    return matches[:limit]


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
                "cue_id": row.get("cue_id"),
                "source_refs": row.get("source_refs") or [],
            }
        )
    return triggers
