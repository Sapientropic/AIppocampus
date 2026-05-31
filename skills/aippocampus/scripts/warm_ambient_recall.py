#!/usr/bin/env python3
"""Standalone warm-path ambient recall scouts.

This module is intentionally outside the foreground prompt hook. It can spend a
small warm budget on parallel DeepSeek-compatible scouts, then serially writes
compact recall cards through `ambient_thread_cache.py`. Model output remains a
proposal layer: source refs are required before anything is marked evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    resolve_model_route,
    route_cache_metrics,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampus_runtime.warm_ambient.prompting import OUTPUT_BUDGET_RULES as OUTPUT_BUDGET_RULES
from aippocampus_runtime.warm_ambient.prompting import SYSTEM_PROMPT, scout_prompt
from aippocampus_runtime.warm_ambient.scout_profiles import (
    DEFAULT_SCOUTS,
    SCOUT_CANDIDATE_LIMITS,
    SUPPORT_RANK,
    TOPIC_EPOCH_FAMILIES,
    VALID_DECISIONS,
    VALID_SUPPORT_LEVELS,
    VALID_TOPIC_EPOCH_ACTIONS,
    VALID_VISIBILITIES,
    expand_scout_lanes,
    output_profile_for_family,
    scout_lane_parts,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    FAMILY_LENS_TASKS as FAMILY_LENS_TASKS,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    FAMILY_TASKS as FAMILY_TASKS,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    FAMILY_VARIANT_LENS_TASKS as FAMILY_VARIANT_LENS_TASKS,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    LEGACY_SCOUT_ALIASES as LEGACY_SCOUT_ALIASES,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    SCOUT_FAMILIES as SCOUT_FAMILIES,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    SCOUT_OUTPUT_PROFILES as SCOUT_OUTPUT_PROFILES,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    SCOUT_PRIORITY as SCOUT_PRIORITY,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    SCOUT_VARIANTS as SCOUT_VARIANTS,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    VARIANT_LENS_TASKS as VARIANT_LENS_TASKS,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    VARIANT_TASKS as VARIANT_TASKS,
)
from aippocampus_runtime.warm_ambient.scout_profiles import (
    lens_task_for as lens_task_for,
)
from aippocampus_runtime.warm_ambient.source_validation import (
    _clean_source_ref,
    _stable_id,
    calibrate_cards,
    prompt_trace_fallback_cards,
    referenced_thread_keys,
    referenced_thread_keys_from_cards,
    source_index_from_registry,
)
from aippocampus_runtime.warm_ambient.source_validation import (
    validate_card_source_refs as validate_card_source_refs,
)
from aippocampuslib import (
    compact_text,
    now_utc,
    sanitize_external_model_payload,
    sanitize_external_model_text,
    workspace_thread_key,
)
from ambient_recall_cards import (
    ACTIVE_GENTLE_NUDGE,
    CANDIDATE,
    DEEP_ARCHIVAL_RECALL,
    EVIDENCE,
    SCENT,
    SILENT_TUNING,
    SOURCE_BACKED_RECALL_CARD,
)
from ambient_thread_cache import (
    default_ambient_cache_path,
    topic_epoch_from_terms,
    write_thread_cache,
)
from registry import load_registry, registry_paths, unique_preserve
from retrieval import split_query_terms
from subconscious_runtime import add_usage, call_chat_json, compact_usage
from subconscious_worker import DEFAULT_BASE_URL, DEFAULT_MODEL, clamp_confidence, parse_model_json

PROMPT_VERSION = "aippocampus-warm-ambient-recall-v0"
SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = float(os.environ.get("AIPPOCAMPUS_WARM_RECALL_TIMEOUT", "1.8"))
DEFAULT_QUORUM = int(os.environ.get("AIPPOCAMPUS_WARM_RECALL_QUORUM", "3"))
DEFAULT_MAX_CARDS = 3
DEFAULT_MAX_CATALOG_ITEMS = int(os.environ.get("AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT", "64"))
DEFAULT_TEMPERATURE = float(os.environ.get("AIPPOCAMPUS_WARM_RECALL_TEMPERATURE", "0.2"))
DEFAULT_THINKING = os.environ.get("AIPPOCAMPUS_WARM_RECALL_THINKING", "enabled")
DEFAULT_USER_ID_PREFIX = "aip-warm"
DEFAULT_PREFIX_CACHE_WARMUP_SCOUTS = int(os.environ.get("AIPPOCAMPUS_WARM_PREFIX_CACHE_WARMUP_SCOUTS", "0") or 0)
DEFAULT_DETACHED_PREFIX_CACHE_WARMUP_SCOUTS = int(
    os.environ.get("AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_SCOUTS", "2") or 0
)
DEFAULT_PREFIX_CACHE_WARMUP_DELAY = float(os.environ.get("AIPPOCAMPUS_WARM_PREFIX_CACHE_WARMUP_DELAY", "0") or 0)
DEFAULT_DETACHED_PREFIX_CACHE_WARMUP_DELAY = float(
    os.environ.get("AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_DELAY", "0.5") or 0
)
WARM_JOB_SCHEMA_VERSION = 1

ChatFn = Callable[..., dict[str, Any]]
ScoutFn = Callable[..., dict[str, Any]]


def env_positive_int(name: str) -> int | None:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def resolve_max_workers(max_workers: int | None) -> int | None:
    if max_workers and int(max_workers) > 0:
        return int(max_workers)
    return env_positive_int("AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS")


def resolve_thinking_mode(value: str | None = None) -> str | None:
    raw = str(DEFAULT_THINKING if value is None else value).strip().casefold()
    if raw in {"", "provider", "default", "none"}:
        return None
    if raw not in {"enabled", "disabled"}:
        raise ValueError("AIPPOCAMPUS_WARM_RECALL_THINKING must be enabled, disabled, or provider")
    return raw


def warm_deepseek_user_id(*, cwd: Path | str, thread_id: str | None = None, user_id: str | None = None) -> str:
    if user_id:
        if not re.fullmatch(r"[a-zA-Z0-9\-_]{1,512}", user_id):
            raise ValueError("user_id must match [a-zA-Z0-9\\-_]+ and be at most 512 chars")
        return user_id
    seed = f"{Path(cwd).resolve()}\n{thread_id or ''}\nwarm-ambient-recall"
    return f"{DEFAULT_USER_ID_PREFIX}-{hashlib.sha1(seed.casefold().encode('utf-8')).hexdigest()[:32]}"


THEME_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _clean_list(values: Any, *, limit: int, chars: int = 100) -> list[str]:
    if int(limit) <= 0:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    scalar_values = [
        item
        for item in values
        if isinstance(item, str | int | float | bool) and str(item).strip()
    ]
    return unique_preserve([_safe_text(item, chars) for item in scalar_values], limit)


def _split_theme_items(value: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Separate plain theme labels from model-returned card-like theme objects."""
    if isinstance(value, dict):
        return [], [value]
    items = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    themes: list[str] = []
    candidates: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            candidates.append(item)
        elif isinstance(item, str | int | float | bool) and str(item).strip():
            themes.append(_safe_text(item, 120))
    return unique_preserve(themes, 8), candidates


def _confidence_label(value: float) -> str:
    if value >= 0.82:
        return "high"
    if value >= 0.45:
        return "medium"
    return "low"


def _mode_for_cards(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return SILENT_TUNING
    if any(card.get("visibility") == DEEP_ARCHIVAL_RECALL for card in cards):
        return DEEP_ARCHIVAL_RECALL
    if any(card.get("support_level") == EVIDENCE for card in cards):
        return SOURCE_BACKED_RECALL_CARD
    if any(card.get("visibility") == ACTIVE_GENTLE_NUDGE for card in cards):
        return ACTIVE_GENTLE_NUDGE
    return SILENT_TUNING


def _catalog_from_registry(registry: dict[str, Any], *, limit: int = DEFAULT_MAX_CATALOG_ITEMS) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "thread_key": _safe_text(entry.get("thread_key"), 160),
                "title": _safe_text(entry.get("title") or entry.get("workspace_name"), 180),
                "project_label": _safe_text(entry.get("project_label") or entry.get("workspace_name"), 120),
                "anchor_titles": _clean_list(entry.get("anchor_titles") or [], limit=8, chars=120),
                "keywords": _clean_list(entry.get("keywords") or entry.get("project_tags") or [], limit=16, chars=80),
                "summary": _safe_text(entry.get("summary"), 420),
                "updated_at": entry.get("updated_at"),
            }
        )
        if len(rows) >= max(1, limit):
            break
    return rows


def _registry_path_from_args(
    registry_path: Path | str | None = None, registry_dir: Path | str | None = None
) -> Path:
    return (
        Path(registry_path).resolve()
        if registry_path
        else registry_paths(Path(registry_dir).resolve() if registry_dir else None)[0]
    )


def resolve_registry(
    *,
    registry: dict[str, Any] | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    path = _registry_path_from_args(registry_path, registry_dir)
    return (registry if isinstance(registry, dict) else load_registry(path), path)


def _clean_prompt_trace(trace: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(trace, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in trace[:limit]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "thread_key": _safe_text(item.get("thread_key"), 160),
                "role": _safe_text(item.get("role"), 40),
                "phase": _safe_text(item.get("phase"), 80),
                "turn_index": item.get("turn_index"),
                "text": _safe_text(item.get("text") or item.get("prompt") or item.get("summary"), 420),
                "source_refs": [
                    ref for ref in (_clean_source_ref(ref) for ref in item.get("source_refs") or []) if ref
                ][:3],
            }
        )
    return rows


def build_payload(
    prompt: str,
    *,
    cwd: Path | str,
    registry: dict[str, Any] | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    prompt_trace: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sanitized_prompt, secret_policy = sanitize_external_model_text(prompt)
    registry_obj = registry
    if registry_obj is None:
        path = _registry_path_from_args(registry_path, registry_dir)
        registry_obj = load_registry(path)
    prompt_terms = split_query_terms([sanitized_prompt])[:16]
    payload = {
        "prompt_version": PROMPT_VERSION,
        "task": "propose_warm_ambient_recall_hints",
        "memory_catalog": _catalog_from_registry(registry_obj),
        "workspace_name": _safe_text(Path(cwd).resolve().name, 120),
        "output_contract": {
            "decision": "skip|background_only|scent|candidate|evidence",
            "confidence": 0.0,
            "field_budget": "Use only scout_task.output_profile fields; omit disallowed or empty fields.",
            "source_ref_rule": "Only cite source_refs already present in context.",
        },
        "prompt": compact_text(sanitized_prompt, 1200),
        "prompt_trace": _clean_prompt_trace(prompt_trace or []),
        "prompt_terms": prompt_terms,
    }
    return sanitize_external_model_payload(payload), secret_policy


def model_scout_fn(
    scout: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: float,
    temperature: float,
    user_id: str | None,
    thinking: str | None,
    service_name: str,
    response_format_json: bool,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"thinking": thinking} if thinking else {}
    if user_id:
        kwargs["user_id"] = user_id
    if chat_fn is call_chat_json:
        kwargs["service_name"] = service_name
        kwargs["response_format_json"] = response_format_json
    return chat_fn(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": scout_prompt(scout, payload)},
        ],
        api_key,
        model,
        base_url,
        max_tokens,
        timeout,
        temperature,
        **kwargs,
    )


def _candidate_from_theme(theme: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "theme": theme,
        "support_level": SCENT if row.get("decision") in {"scent", "background_only"} else CANDIDATE,
        "resonance": "medium",
        "suggested_use": "Treat this as provisional warm recall only.",
        "matched_terms": row.get("query_aliases") or [],
        "source_refs": [],
    }


def _clean_candidate(
    candidate: dict[str, Any],
    *,
    row: dict[str, Any],
    candidate_fields: set[str] | None = None,
) -> dict[str, Any] | None:
    candidate_fields = candidate_fields or {
        "theme",
        "support_level",
        "visibility",
        "resonance",
        "suggested_use",
        "nudge",
        "key_line",
        "matched_terms",
        "source_refs",
        "expand_if",
    }
    refs = [
        clean for clean in (_clean_source_ref(ref) for ref in candidate.get("source_refs") or []) if clean
    ][:3] if "source_refs" in candidate_fields else []
    support = str(candidate.get("support_level") or row.get("decision") or SCENT).strip().casefold()
    if support not in VALID_SUPPORT_LEVELS:
        support = CANDIDATE if row.get("decision") == "candidate" else SCENT
    if support == EVIDENCE and not refs:
        support = CANDIDATE
    requested_visibility = str(candidate.get("visibility") or "").strip().casefold()
    if requested_visibility not in VALID_VISIBILITIES:
        requested_visibility = ""
    if support == EVIDENCE:
        visibility = requested_visibility if requested_visibility in {SOURCE_BACKED_RECALL_CARD, DEEP_ARCHIVAL_RECALL} else SOURCE_BACKED_RECALL_CARD
    else:
        visibility = requested_visibility if requested_visibility in {SILENT_TUNING, ACTIVE_GENTLE_NUDGE} else ACTIVE_GENTLE_NUDGE
    theme = _safe_text(candidate.get("theme") or candidate.get("title"), 140)
    key_line = (
        _safe_text(candidate.get("key_line") or candidate.get("snippet"), 220)
        if "key_line" in candidate_fields
        else ""
    )
    if not theme and not key_line:
        return None
    if not theme:
        theme = compact_text(key_line, 100)
    card = {
        "card_id": _stable_id([support, theme, key_line, json.dumps(refs, sort_keys=True)]),
        "theme": theme,
        "resonance": _safe_text(candidate.get("resonance") or "medium", 40) or "medium",
        "support_level": support,
        "visibility": visibility,
        "suggested_use": _safe_text(
            (candidate.get("suggested_use") if "suggested_use" in candidate_fields else "")
            or ("Use only with the attached source refs." if support == EVIDENCE else "Treat as provisional resonance."),
            220,
        ),
        "nudge": _safe_text(candidate.get("nudge"), 220) if "nudge" in candidate_fields else "",
        "key_line": key_line,
        "matched_terms": _clean_list(
            (candidate.get("matched_terms") if "matched_terms" in candidate_fields else [])
            or row.get("query_aliases")
            or [],
            limit=6,
            chars=80,
        ),
        "source_refs": refs,
        "expand_if": _safe_text(
            (candidate.get("expand_if") if "expand_if" in candidate_fields else "")
            or "Search clean source before presenting exact claims as facts.",
            160,
        ),
    }
    return card


def parse_scout_output(raw: dict[str, Any], scout: str) -> dict[str, Any]:
    usage = raw.get("usage") or {}
    parsed = parse_model_json(raw) if raw.get("choices") else raw
    if not isinstance(parsed, dict):
        parsed = {}
    family, variant = scout_lane_parts(scout)
    scout_id = f"{family}:{variant}" if family else str(scout or "")
    profile = output_profile_for_family(family)
    allowed_fields = set(profile["allowed_fields"])
    candidate_fields = set(profile["candidate_fields"])
    decision = str(parsed.get("decision") or "skip").strip().casefold()
    if decision not in VALID_DECISIONS:
        decision = "skip"
    epoch_action = (
        str(parsed.get("topic_epoch_action") or "").strip().casefold()
        if family in TOPIC_EPOCH_FAMILIES and "topic_epoch_action" in allowed_fields
        else ""
    )
    if epoch_action not in VALID_TOPIC_EPOCH_ACTIONS:
        epoch_action = ""
    confidence = clamp_confidence(parsed.get("confidence"))
    row: dict[str, Any] = {
        "scout": scout_id,
        "scout_family": family,
        "scout_variant": variant,
        "ok": True,
        "decision": decision,
        "confidence": confidence,
        "topic_epoch": {
            "action": epoch_action,
            "label": _safe_text(parsed.get("topic_epoch_label"), 120),
            "reason": _safe_text(parsed.get("topic_epoch_reason"), 220),
            "confidence": confidence,
        }
        if epoch_action
        else None,
        "query_aliases": _clean_list(
            parsed.get("query_aliases") or parsed.get("aliases") or [],
            limit=int(profile["max_query_aliases"]),
            chars=80,
        ),
        "themes": [],
        "negative_contexts": _clean_list(
            parsed.get("negative_contexts") or [],
            limit=int(profile["max_negative_contexts"]),
            chars=120,
        ),
        "block": bool(parsed.get("block")) if "block" in allowed_fields else False,
        "reason": _safe_text(parsed.get("reason"), 120) if "reason" in allowed_fields else "",
        "usage": usage,
        "candidates": [],
    }
    if "themes" in allowed_fields:
        themes, theme_candidates = _split_theme_items(
            parsed.get("themes") if "themes" in parsed else parsed.get("theme")
        )
        row["themes"] = themes[: _safe_int(profile["max_themes"])]
    else:
        theme_candidates = []
    candidates = [
        item for item in parsed.get("candidates") or [] if isinstance(item, dict)
    ] if "candidates" in allowed_fields else []
    candidates.extend(theme_candidates)
    for theme in row["themes"]:
        if not any(str(item.get("theme") or "").casefold() == theme.casefold() for item in candidates):
            candidates.append(_candidate_from_theme(theme, row))
    candidate_limit = SCOUT_CANDIDATE_LIMITS.get(family, 1)
    row["candidates"] = [
        card
        for card in (
            _clean_candidate(candidate, row=row, candidate_fields=candidate_fields)
            for candidate in candidates
        )
        if card
    ][:candidate_limit]
    row["useful"] = bool(
        row["decision"] in {"scent", "candidate", "evidence"}
        or row["query_aliases"]
        or row["themes"]
        or row["candidates"]
    )
    return row


def _error_row(scout: str, exc: BaseException) -> dict[str, Any]:
    family, variant = scout_lane_parts(scout)
    reason = compact_text(f"{type(exc).__name__}: {exc}", 260)
    return {
        "scout": scout,
        "scout_family": family,
        "scout_variant": variant,
        "ok": False,
        "decision": "skip",
        "confidence": 0.0,
        "topic_epoch": None,
        "query_aliases": [],
        "themes": [],
        "negative_contexts": [],
        "block": False,
        "reason": reason,
        "error_kind": scout_error_kind(reason),
        "usage": {},
        "candidates": [],
        "useful": False,
    }


def scout_error_kind(reason: Any) -> str:
    text = str(reason or "").casefold()
    if "429" in text or "rate limit" in text or "rate_limited" in text:
        return "rate_limited_429"
    if "503" in text or "service_unavailable" in text or "too busy" in text:
        return "service_unavailable_503"
    if "502" in text or "504" in text or "bad gateway" in text or "gateway timeout" in text:
        return "provider_5xx"
    if "timeout" in text or "timed out" in text:
        return "read_timeout"
    if "json" in text or "parse" in text or "decode" in text:
        return "invalid_json"
    if "401" in text or "403" in text or "auth" in text or "api key" in text:
        return "auth_error"
    if "connect" in text or "connection" in text or "network" in text or "urlerror" in text:
        return "connection_error"
    return "scout_error"


def run_scout(
    scout: str,
    *,
    payload: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: float,
    temperature: float,
    user_id: str | None,
    thinking: str | None,
    service_name: str,
    response_format_json: bool,
    chat_fn: ChatFn,
    scout_fn: ScoutFn,
) -> dict[str, Any]:
    raw = scout_fn(
        scout,
        payload,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        user_id=user_id,
        thinking=thinking,
        service_name=service_name,
        response_format_json=response_format_json,
        chat_fn=chat_fn,
    )
    return parse_scout_output(raw, scout)


def run_scout_batch(
    *,
    scouts: tuple[str, ...],
    payload: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: float,
    temperature: float,
    quorum: int,
    max_workers: int | None,
    user_id: str | None,
    thinking: str | None,
    service_name: str,
    response_format_json: bool,
    wait_all: bool,
    prefix_cache_warmup_scouts: int = 0,
    prefix_cache_warmup_delay: float = 0.0,
    chat_fn: ChatFn,
    scout_fn: ScoutFn,
) -> tuple[list[dict[str, Any]], bool]:
    if not scouts:
        return [], False
    worker_count = max(1, max_workers or len(scouts))
    scout_order = {name: idx for idx, name in enumerate(scouts)}
    rows: list[dict[str, Any]] = []
    useful_count = 0
    quorum_met = False
    received = 0
    deadline = time.perf_counter() + max(0.01, timeout)
    tasks: queue.Queue[str] = queue.Queue()
    results: queue.Queue[dict[str, Any]] = queue.Queue()
    stop_event = threading.Event()
    warmup_count = max(0, min(int(prefix_cache_warmup_scouts or 0), len(scouts)))
    warmup_scouts = scouts[:warmup_count]
    remaining_scouts = scouts[warmup_count:]
    for scout in remaining_scouts:
        tasks.put(scout)

    def execute_scout(scout: str) -> dict[str, Any]:
        try:
            return run_scout(
                scout,
                payload=payload,
                api_key=api_key,
                model=model,
                base_url=base_url,
                max_tokens=max_tokens,
                timeout=timeout,
                temperature=temperature,
                user_id=user_id,
                thinking=thinking,
                service_name=service_name,
                response_format_json=response_format_json,
                chat_fn=chat_fn,
                scout_fn=scout_fn,
            )
        except Exception as exc:  # isolate malformed or failed scout output
            return _error_row(scout, exc)

    # DeepSeek persists cache prefix units only after prior requests complete.
    # For a 50-lane same-prefix scout batch, launching every lane at once often
    # makes the whole wave cold. A small warm-up wave lets detached/evaluation
    # runs pay one or two scout calls first, then the remaining thin suffixes can
    # reuse the now-persisted shared context. Foreground callers keep this at 0.
    for scout in warmup_scouts:
        row = execute_scout(scout)
        rows.append(row)
        received += 1
        if row.get("ok") and row.get("useful"):
            useful_count += 1
        if not wait_all and useful_count >= max(1, quorum):
            return sorted(rows, key=lambda row: scout_order.get(str(row.get("scout") or ""), 999)), True
    if warmup_scouts and remaining_scouts and prefix_cache_warmup_delay > 0:
        time.sleep(max(0.0, float(prefix_cache_warmup_delay)))

    def worker_loop() -> None:
        while not stop_event.is_set():
            try:
                scout = tasks.get_nowait()
            except queue.Empty:
                return
            try:
                results.put(execute_scout(scout))
            finally:
                tasks.task_done()

    # Use daemon threads so a quorum-first CLI run can return without the
    # interpreter waiting for every still-running network request. The parent
    # owns all writes, so abandoned late rows cannot mutate cache state.
    threads = [
        threading.Thread(target=worker_loop, name=f"aippocampus-warm-{idx}", daemon=True)
        for idx in range(min(worker_count, len(remaining_scouts)))
    ]
    for thread in threads:
        thread.start()

    try:
        while received < len(scouts):
            remaining = None if wait_all else max(0.0, deadline - time.perf_counter())
            if remaining == 0.0:
                break
            try:
                row = results.get(timeout=remaining)
            except queue.Empty:
                break
            received += 1
            rows.append(row)
            if row.get("ok") and row.get("useful"):
                useful_count += 1
            if not wait_all and useful_count >= max(1, quorum):
                quorum_met = True
                break
    finally:
        stop_event.set()
        if wait_all:
            for thread in threads:
                thread.join(timeout=0.1)
    rows.sort(key=lambda row: scout_order.get(str(row.get("scout") or ""), 999))
    return rows, quorum_met or (useful_count >= max(1, quorum))


def _theme_terms(card: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(card.get("theme") or ""),
            " ".join(str(term or "") for term in card.get("matched_terms") or []),
        ]
    )
    terms: set[str] = set()
    for term in re.findall(r"[\w\u4e00-\u9fff]+", text.casefold()):
        clean = term.strip("_")
        if not clean or clean in THEME_STOPWORDS:
            continue
        if clean.isascii() and len(clean) < 2:
            continue
        terms.add(clean)
    return terms


def _similar_theme(a: dict[str, Any], b: dict[str, Any]) -> bool:
    theme_a = str(a.get("theme") or "").strip().casefold()
    theme_b = str(b.get("theme") or "").strip().casefold()
    if theme_a and theme_a == theme_b:
        return True
    if min(len(theme_a), len(theme_b)) >= 12 and (theme_a in theme_b or theme_b in theme_a):
        return True
    terms_a = _theme_terms(a)
    terms_b = _theme_terms(b)
    if not terms_a or not terms_b:
        return False
    shared = terms_a & terms_b
    return len(shared) >= 2 and (len(shared) / min(len(terms_a), len(terms_b))) >= 0.5


def _merge_source_refs(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in [*left, *right]:
        key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
    return merged[:3]


def _merge_card(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    if SUPPORT_RANK.get(str(incoming.get("support_level") or ""), 0) > SUPPORT_RANK.get(
        str(existing.get("support_level") or ""), 0
    ):
        existing["support_level"] = incoming.get("support_level")
        existing["visibility"] = incoming.get("visibility")
        existing["suggested_use"] = incoming.get("suggested_use") or existing.get("suggested_use")
    elif (
        incoming.get("visibility") == DEEP_ARCHIVAL_RECALL
        and existing.get("support_level") == EVIDENCE
    ):
        existing["visibility"] = DEEP_ARCHIVAL_RECALL

    existing["matched_terms"] = unique_preserve(
        [*existing.get("matched_terms", []), *incoming.get("matched_terms", [])],
        limit=8,
    )
    existing["source_refs"] = _merge_source_refs(
        existing.get("source_refs") or [], incoming.get("source_refs") or []
    )
    for field in ("key_line", "nudge", "expand_if"):
        if not existing.get(field) and incoming.get(field):
            existing[field] = incoming[field]


def merge_scouts(
    rows: list[dict[str, Any]],
    *,
    max_cards: int = DEFAULT_MAX_CARDS,
    fallback_cards: list[dict[str, Any]] | None = None,
    source_index: dict[str, dict[str, Any]] | None = None,
    current_thread_key: str | None = None,
    allow_current_thread_echo: bool = False,
) -> dict[str, Any]:
    blockers = [
        row
        for row in rows
        if row.get("ok")
        and row.get("block")
        and row.get("scout_family") in {"privacy_boundary_guard", "evidence_gap_sentinel"}
    ]
    privacy_blockers = [
        row for row in blockers if row.get("scout_family") == "privacy_boundary_guard"
    ]
    evidence_blockers = [
        row for row in blockers if row.get("scout_family") == "evidence_gap_sentinel"
    ]
    negative_contexts: list[str] = []
    query_aliases: list[str] = []
    for row in rows:
        negative_contexts.extend(row.get("negative_contexts") or [])
        query_aliases.extend(row.get("query_aliases") or [])
    if privacy_blockers:
        _, calibration = calibrate_cards(
            fallback_cards or [],
            source_index=source_index,
            current_thread_key=current_thread_key,
            allow_current_thread_echo=allow_current_thread_echo,
        )
        return {
            "cards": [],
            "mode": SILENT_TUNING,
            "confidence": "low",
            "negative_contexts": unique_preserve(negative_contexts, limit=8),
            "query_aliases": unique_preserve(query_aliases, limit=16),
            "blocked_by": [row.get("scout") for row in privacy_blockers],
            **calibration,
        }

    candidates: list[tuple[int, float, dict[str, Any]]] = []
    if not evidence_blockers:
        for row in rows:
            if not row.get("ok"):
                continue
            confidence = float(row.get("confidence") or 0.0)
            for card in row.get("candidates") or []:
                support = str(card.get("support_level") or SCENT)
                candidates.append((SUPPORT_RANK.get(support, 0), confidence, card))
    for card in fallback_cards or []:
        support = str(card.get("support_level") or SCENT)
        candidates.append((SUPPORT_RANK.get(support, 0), 0.62, card))
    candidates.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            str(item[2].get("theme") or "").casefold(),
        )
    )
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, _, card in candidates:
        similar = next((existing for existing in cards if _similar_theme(existing, card)), None)
        if similar:
            _merge_card(similar, card)
            continue

        key = "|".join(
            [
                str(card.get("theme") or "").casefold(),
                str(card.get("support_level") or ""),
                str((card.get("source_refs") or [{}])[0].get("thread_key") if card.get("source_refs") else ""),
                str(card.get("key_line") or "").casefold(),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        cards.append(card)
    cards, calibration = calibrate_cards(
        cards,
        source_index=source_index,
        current_thread_key=current_thread_key,
        allow_current_thread_echo=allow_current_thread_echo,
    )
    cards = cards[: max(0, max_cards)]
    if evidence_blockers and not cards:
        # Evidence sentinels are allowed to veto model-generated cards, but not
        # source-index-validated prompt-trace fallback cards. This preserves the
        # closed-book anti-hallucination guard without losing the deterministic
        # current-trace recall path that exists specifically for sparse live
        # scout failures and over-cautious sentinel blocks.
        return {
            "cards": [],
            "mode": SILENT_TUNING,
            "confidence": "low",
            "negative_contexts": unique_preserve(negative_contexts, limit=8),
            "query_aliases": unique_preserve(query_aliases, limit=16),
            "blocked_by": [row.get("scout") for row in evidence_blockers],
            **calibration,
        }
    max_confidence = max([float(row.get("confidence") or 0.0) for row in rows if row.get("ok")] or [0.0])
    return {
        "cards": cards,
        "mode": _mode_for_cards(cards),
        "confidence": _confidence_label(max_confidence),
        "negative_contexts": unique_preserve(negative_contexts, limit=8),
        "query_aliases": unique_preserve(query_aliases, limit=16),
        "blocked_by": [row.get("scout") for row in evidence_blockers],
        **calibration,
    }


def resolve_topic_epoch(
    *,
    rows: list[dict[str, Any]],
    prior_topic_epoch: str | None,
    fallback_terms: list[str],
) -> tuple[str, dict[str, Any]]:
    votes: list[dict[str, Any]] = []
    for row in rows:
        vote = row.get("topic_epoch")
        if not isinstance(vote, dict):
            continue
        action = str(vote.get("action") or "").strip().casefold()
        if action not in VALID_TOPIC_EPOCH_ACTIONS:
            continue
        votes.append(
            {
                "action": action,
                "label": _safe_text(vote.get("label"), 120),
                "reason": _safe_text(vote.get("reason"), 220),
                "confidence": clamp_confidence(vote.get("confidence")),
                "scout": row.get("scout"),
            }
        )
    if not votes:
        epoch = prior_topic_epoch or topic_epoch_from_terms(fallback_terms)
        return epoch, {
            "action": "fallback",
            "label": "",
            "reason": "no scout topic-epoch vote",
            "confidence": 0.0,
            "source_scout": None,
            "suppress_write": False,
        }

    action_priority = {"suppress": 3, "rotate": 2, "reuse": 1}
    votes.sort(key=lambda item: (-action_priority[item["action"]], -float(item["confidence"])))
    chosen = votes[0]
    action = chosen["action"]
    label = chosen.get("label") or ""
    if action == "reuse" and prior_topic_epoch:
        epoch = prior_topic_epoch
    elif label:
        epoch = topic_epoch_from_terms([label])
    else:
        epoch = prior_topic_epoch or topic_epoch_from_terms(fallback_terms)
    return epoch, {
        "action": action,
        "label": label,
        "reason": chosen.get("reason") or "",
        "confidence": chosen.get("confidence") or 0.0,
        "source_scout": chosen.get("scout"),
        "suppress_write": action == "suppress",
    }


def unavailable_result(
    reason: str,
    *,
    secret_policy: dict[str, Any] | None = None,
    model_route: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": "aippocampus_warm_ambient_recall",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ok": True,
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "quorum_met": False,
        "timeout": None,
        "temperature": None,
        "accepted_scout_count": 0,
        "failed_scout_count": 0,
        "scouts": [],
        "cards": [],
        "model_route": model_route or {},
        "cache": cache or {},
        "cache_write": None,
        "secret_policy": secret_policy or None,
        "late_update_policy": "standalone_warm_path_only",
    }


def _cache_write_summary(cache_write: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(cache_write, dict):
        return None
    summary = {
        "status": cache_write.get("status"),
        "topic_epoch": cache_write.get("topic_epoch"),
        "card_count": cache_write.get("card_count"),
        "source_ref_fingerprint_count": len(cache_write.get("source_ref_fingerprints") or []),
    }
    residue = cache_write.get("residue_export")
    if isinstance(residue, dict):
        summary["residue_export"] = {
            "status": residue.get("status"),
            "topic_epoch": residue.get("topic_epoch"),
            "residue_count": residue.get("residue_count"),
            "residue_id": residue.get("residue_id"),
        }
    return {key: value for key, value in summary.items() if value is not None}


def warm_job_result_summary(job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    error_kinds: dict[str, int] = {}
    for row in result.get("scouts") or []:
        if row.get("ok"):
            continue
        kind = str(row.get("error_kind") or scout_error_kind(row.get("reason")))
        error_kinds[kind] = error_kinds.get(kind, 0) + 1
    return {
        "kind": "aippocampus_warm_ambient_recall_job_result",
        "schema_version": WARM_JOB_SCHEMA_VERSION,
        "job_id": job.get("job_id"),
        "prompt_sha1": job.get("prompt_sha1"),
        "created_at": now_utc(),
        "ok": bool(result.get("ok")),
        "available": bool(result.get("available")),
        "status": result.get("status"),
        "reason": result.get("reason") or "",
        "quorum_met": bool(result.get("quorum_met")),
        "configured_scout_count": int(result.get("scout_count") or 0),
        "observed_scout_result_count": len(result.get("scouts") or []),
        "prefix_cache_warmup_scout_count": int(result.get("prefix_cache_warmup_scout_count") or 0),
        "accepted_scout_count": int(result.get("accepted_scout_count") or 0),
        "failed_scout_count": int(result.get("failed_scout_count") or 0),
        "scout_error_kinds": error_kinds,
        "card_count": len(result.get("cards") or []),
        "topic_epoch": result.get("topic_epoch"),
        "topic_epoch_action": (result.get("topic_epoch_decision") or {}).get("action"),
        "current_thread_echo_count": int(result.get("current_thread_echo_count") or 0),
        "cache_write": _cache_write_summary(result.get("cache_write")),
        "cache": result.get("cache") or {},
        "model_route": result.get("model_route") or {},
        "elapsed_ms": float(result.get("elapsed_ms") or 0.0),
        "late_update_policy": "detached_wait_all_writes_thread_cache",
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_prompt_trace_emitted": False,
            "raw_cards_emitted": False,
            "absolute_paths_emitted": False,
        },
    }


def run_warm_job_file(
    job_file: Path | str,
    *,
    api_key: str | None = None,
    chat_fn: ChatFn = call_chat_json,
    scout_fn: ScoutFn = model_scout_fn,
) -> dict[str, Any]:
    job_path = Path(job_file).resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    if not isinstance(job, dict):
        raise ValueError("warm job file must contain a JSON object")
    if job.get("kind") != "aippocampus_warm_ambient_recall_job":
        raise ValueError("unsupported warm job kind")

    scouts_value = job.get("scouts") or DEFAULT_SCOUTS
    scouts = tuple(str(item) for item in scouts_value if str(item or "").strip())
    result = run_warm_ambient_recall(
        str(job.get("prompt") or ""),
        cwd=Path(str(job.get("cwd") or ".")).resolve(),
        thread_id=str(job.get("thread_id") or "") or None,
        current_thread_key=str(job.get("current_thread_key") or "") or None,
        prompt_trace=job.get("prompt_trace") if isinstance(job.get("prompt_trace"), list) else None,
        topic_epoch=str(job.get("topic_epoch") or "") or None,
        registry_path=Path(str(job.get("registry_path"))).resolve() if job.get("registry_path") else None,
        registry_dir=Path(str(job.get("registry_dir"))).resolve() if job.get("registry_dir") else None,
        cache_path=Path(str(job.get("cache_path"))).resolve() if job.get("cache_path") else None,
        residue_path=Path(str(job.get("residue_path"))).resolve() if job.get("residue_path") else None,
        residue_reason="detached_warm_scout",
        api_key=api_key,
        api_key_env=str(job.get("api_key_env") or DEFAULT_DEEPSEEK_API_KEY_ENV),
        user_id=str(job.get("user_id") or "") or None,
        model_route=str(job.get("model_route") or "") or None,
        timeout=float(job.get("timeout") or DEFAULT_TIMEOUT),
        quorum=int(job.get("quorum") or DEFAULT_QUORUM),
        max_workers=int(job.get("max_workers") or 0) or None,
        prefix_cache_warmup_scouts=int(
            job.get("prefix_cache_warmup_scouts") or DEFAULT_DETACHED_PREFIX_CACHE_WARMUP_SCOUTS
        ),
        prefix_cache_warmup_delay=float(
            job.get("prefix_cache_warmup_delay") or DEFAULT_DETACHED_PREFIX_CACHE_WARMUP_DELAY
        ),
        wait_all=bool(job.get("wait_all", True)),
        no_write=bool(job.get("no_write", False)),
        scouts=scouts or DEFAULT_SCOUTS,
        chat_fn=chat_fn,
        scout_fn=scout_fn,
    )
    summary = warm_job_result_summary(job, result)
    result_path_value = job.get("result_path")
    if result_path_value:
        result_path = Path(str(result_path_value)).resolve()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = result_path.with_suffix(result_path.suffix + ".tmp")
        tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        tmp.replace(result_path)
    return summary


def run_warm_ambient_recall(
    prompt: str,
    *,
    cwd: Path | str,
    thread_id: str | None = None,
    current_thread_key: str | None = None,
    allow_current_thread_echo: bool = False,
    prompt_trace: list[dict[str, Any]] | None = None,
    topic_epoch: str | None = None,
    registry: dict[str, Any] | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    cache_path: Path | str | None = None,
    residue_path: Path | str | None = None,
    residue_reason: str = "warm_scout",
    api_key: str | None = None,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    user_id: str | None = None,
    model_route: str | None = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    max_tokens: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    temperature: float = DEFAULT_TEMPERATURE,
    scouts: tuple[str, ...] = DEFAULT_SCOUTS,
    quorum: int = DEFAULT_QUORUM,
    max_workers: int | None = None,
    prefix_cache_warmup_scouts: int = DEFAULT_PREFIX_CACHE_WARMUP_SCOUTS,
    prefix_cache_warmup_delay: float = DEFAULT_PREFIX_CACHE_WARMUP_DELAY,
    wait_all: bool = False,
    no_write: bool = False,
    chat_fn: ChatFn = call_chat_json,
    scout_fn: ScoutFn = model_scout_fn,
) -> dict[str, Any]:
    start = time.perf_counter()
    prompt = str(prompt or "").strip()
    cwd_path = Path(cwd).resolve()
    _, secret_policy = sanitize_external_model_text(prompt)
    if not prompt:
        return unavailable_result("empty prompt", secret_policy=secret_policy)
    if secret_policy.get("hard_block"):
        return unavailable_result(
            str(secret_policy.get("reason") or "sensitive prompt hard-blocked"),
            secret_policy=secret_policy,
        )
    route = resolve_model_route(
        model_route,
        explicit_model=model if model != DEFAULT_MODEL and not model_route else None,
        explicit_base_url=base_url if base_url != DEFAULT_BASE_URL and not model_route else None,
        explicit_api_key_env=(
            api_key_env
            if api_key_env != DEFAULT_DEEPSEEK_API_KEY_ENV and not model_route
            else None
        ),
    )
    capabilities = route.capabilities
    resolved_model = route.model if model == DEFAULT_MODEL else model
    resolved_base_url = route.base_url if base_url == DEFAULT_BASE_URL else base_url
    resolved_api_key_env = (
        route.api_key_env
        if api_key_env == DEFAULT_DEEPSEEK_API_KEY_ENV
        else api_key_env
    )
    route_payload = route_payload_with_effective_values(
        route,
        model=resolved_model,
        base_url=resolved_base_url,
        api_key_env=resolved_api_key_env,
    )
    key_value = api_key or os.environ.get(resolved_api_key_env)
    if not key_value:
        return unavailable_result(
            "missing api key",
            secret_policy=secret_policy,
            model_route=route_payload,
            cache=route_cache_metrics(route, {}),
        )
    supports_user_id = bool(capabilities.supports_user_id if capabilities else True)
    supports_thinking = bool(capabilities.supports_thinking if capabilities else True)
    resolved_user_id = (
        warm_deepseek_user_id(cwd=cwd_path, thread_id=thread_id, user_id=user_id)
        if supports_user_id
        else None
    )
    resolved_thinking = resolve_thinking_mode() if supports_thinking else None
    resolved_max_workers = resolve_max_workers(max_workers)
    if resolved_max_workers is None and route.provider != "deepseek" and capabilities:
        resolved_max_workers = capabilities.safe_default_concurrency
    registry_obj, registry_path_obj = resolve_registry(
        registry=registry, registry_path=registry_path, registry_dir=registry_dir
    )
    payload, secret_policy = build_payload(
        prompt,
        cwd=cwd_path,
        registry=registry_obj,
        prompt_trace=prompt_trace,
    )

    scout_names = expand_scout_lanes(scouts)
    rows, quorum_met = run_scout_batch(
        scouts=scout_names,
        payload=payload,
        api_key=str(key_value),
        model=resolved_model,
        base_url=resolved_base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        quorum=quorum,
        max_workers=resolved_max_workers,
        user_id=resolved_user_id,
        thinking=resolved_thinking,
        service_name=route_service_name(route),
        response_format_json=bool(capabilities.supports_json_response if capabilities else True),
        wait_all=wait_all,
        prefix_cache_warmup_scouts=prefix_cache_warmup_scouts,
        prefix_cache_warmup_delay=prefix_cache_warmup_delay,
        chat_fn=chat_fn,
        scout_fn=scout_fn,
    )
    fallback_cards = prompt_trace_fallback_cards(prompt, payload.get("prompt_trace") or [])
    source_thread_keys = referenced_thread_keys(rows) | referenced_thread_keys_from_cards(fallback_cards)
    merged = merge_scouts(
        rows,
        fallback_cards=fallback_cards,
        source_index=source_index_from_registry(
            registry_obj, thread_keys=source_thread_keys
        ),
        current_thread_key=current_thread_key,
        allow_current_thread_echo=allow_current_thread_echo,
    )
    usage_total: dict[str, Any] = {}
    for row in rows:
        add_usage(usage_total, compact_usage(row.get("usage") or {}))
    terms_for_epoch = unique_preserve(
        [*payload.get("prompt_terms", []), *merged.get("query_aliases", [])], limit=16
    )
    resolved_epoch, topic_epoch_decision = resolve_topic_epoch(
        rows=rows, prior_topic_epoch=topic_epoch, fallback_terms=terms_for_epoch
    )
    resolved_thread = thread_id or workspace_thread_key(cwd_path)
    resolved_cache_path = (
        Path(cache_path).resolve() if cache_path else default_ambient_cache_path(registry_path=registry_path_obj)
    )
    accepted_count = len([row for row in rows if row.get("ok") and row.get("useful")])
    failed_count = len([row for row in rows if not row.get("ok")])
    cache_write = None
    # A single enthusiastic scout should not poison the soft thread cache. Both
    # foreground-style quorum runs and detached wait-all runs must meet the
    # configured quorum before their merged cards become next-turn ambient state.
    if (
        merged["cards"]
        and quorum_met
        and not no_write
        and not topic_epoch_decision.get("suppress_write")
    ):
        cache_write = write_thread_cache(
            resolved_cache_path,
            thread_id=resolved_thread,
            workspace=str(cwd_path),
            topic_epoch=resolved_epoch,
            cards=merged["cards"],
            mode=merged["mode"],
            confidence=merged["confidence"],
            negative_contexts=merged["negative_contexts"],
            query_aliases=merged.get("query_aliases") or [],
            topic_epoch_decision=topic_epoch_decision,
            visibility_bias=merged["mode"],
            residue_path=Path(residue_path).resolve() if residue_path else None,
            residue_reason=residue_reason,
        )
    status = "written" if cache_write and cache_write.get("status") == "written" else "ready"
    if not rows:
        status = "timeout"
    elif merged["cards"] and not quorum_met and not no_write:
        status = "quorum_not_met"
    if topic_epoch_decision.get("suppress_write"):
        status = "suppressed"
    return {
        "kind": "aippocampus_warm_ambient_recall",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ok": True,
        "available": bool(merged["cards"]),
        "status": status,
        "reason": "",
        "quorum_met": quorum_met,
        "scout_count": len(scout_names),
        "max_workers": resolved_max_workers or len(scout_names),
        "prefix_cache_warmup_scout_count": max(0, min(int(prefix_cache_warmup_scouts or 0), len(scout_names))),
        "prefix_cache_warmup_delay": max(0.0, float(prefix_cache_warmup_delay or 0.0)),
        "timeout": timeout,
        "temperature": temperature,
        "user_id": resolved_user_id,
        "model_route": route_payload,
        "accepted_scout_count": accepted_count,
        "failed_scout_count": failed_count,
        "trace_fallback_card_count": len(fallback_cards),
        "scouts": rows,
        "mode": merged["mode"],
        "confidence": merged["confidence"],
        "topic_epoch": resolved_epoch,
        "topic_epoch_decision": topic_epoch_decision,
        "cards": merged["cards"],
        "negative_contexts": merged["negative_contexts"],
        "blocked_by": merged["blocked_by"],
        "current_thread_echo_count": merged.get("current_thread_echo_count", 0),
        "cache_write": cache_write,
        "usage": usage_total,
        "cache": route_cache_metrics(route, usage_total),
        "secret_policy": secret_policy,
        "cached": False,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
        "created_at": now_utc(),
        "late_update_policy": "quorum_result_may_warm_thread_cache; foreground hook must not wait_all",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt")
    parser.add_argument("--job-file")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--thread-id")
    parser.add_argument("--current-thread-key")
    parser.add_argument("--allow-current-thread-echo", action="store_true")
    parser.add_argument(
        "--prompt-trace-json",
        help="Optional sanitized prompt trace JSON array for warm calibration.",
    )
    parser.add_argument("--topic-epoch")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--cache")
    parser.add_argument("--residue")
    parser.add_argument("--residue-reason", default="warm_scout")
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--user-id", help="Optional DeepSeek user_id; omit to send a stable sanitized hash.")
    parser.add_argument("--model-route")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--quorum", type=int, default=DEFAULT_QUORUM)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--prefix-cache-warmup-scouts", type=int, default=DEFAULT_PREFIX_CACHE_WARMUP_SCOUTS)
    parser.add_argument("--prefix-cache-warmup-delay", type=float, default=DEFAULT_PREFIX_CACHE_WARMUP_DELAY)
    parser.add_argument("--wait-all", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    if args.job_file:
        summary = run_warm_job_file(args.job_file)
        if args.json_output:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(
                "warm ambient recall job: "
                f"status={summary.get('status')} "
                f"scout_results={summary.get('observed_scout_result_count', 0)}"
            )
        return 0 if summary.get("ok") else 2
    if not args.prompt:
        parser.error("--prompt is required unless --job-file is provided")

    result = run_warm_ambient_recall(
        args.prompt,
        cwd=args.cwd,
        thread_id=args.thread_id,
        current_thread_key=args.current_thread_key,
        allow_current_thread_echo=args.allow_current_thread_echo,
        prompt_trace=json.loads(args.prompt_trace_json) if args.prompt_trace_json else None,
        topic_epoch=args.topic_epoch,
        registry_path=args.registry,
        registry_dir=args.registry_dir,
        cache_path=args.cache,
        residue_path=args.residue,
        residue_reason=args.residue_reason,
        api_key=None,
        api_key_env=args.api_key_env,
        user_id=args.user_id,
        model_route=args.model_route,
        model=args.model,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        temperature=args.temperature,
        quorum=args.quorum,
        max_workers=args.max_workers,
        prefix_cache_warmup_scouts=args.prefix_cache_warmup_scouts,
        prefix_cache_warmup_delay=args.prefix_cache_warmup_delay,
        wait_all=args.wait_all,
        no_write=args.no_write,
    )
    if args.strict and not result.get("available"):
        result["ok"] = False
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result.get("available"):
            print(f"warm ambient recall unavailable: {result.get('reason') or result.get('status')}")
        else:
            print(
                "warm ambient recall: "
                f"{result.get('accepted_scout_count')} scout(s), "
                f"{len(result.get('cards') or [])} card(s), "
                f"status={result.get('status')}"
            )
    return 2 if args.strict and not result.get("available") else 0


if __name__ == "__main__":
    raise SystemExit(main())
