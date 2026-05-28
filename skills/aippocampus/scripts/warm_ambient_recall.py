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
import threading
import time
from pathlib import Path
from typing import Any, Callable

from aippocampuslib import (
    compact_text,
    deepseek_cache_metrics_from_usage,
    now_utc,
    sanitize_external_model_payload,
    sanitize_external_model_text,
    workspace_thread_key,
)
from ambient_recall_cards import (
    ACTIVE_GENTLE_NUDGE,
    CANDIDATE,
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

DEFAULT_SCOUTS = (
    "query_expansion",
    "life_wide_cue_classifier",
    "thread_matcher",
    "key_line_hunter",
    "current_thread_filter",
    "theme_matcher",
    "evidence_judge",
    "nudge_writer",
    "privacy_scope_guard",
    "failure_sentinel",
)

VALID_DECISIONS = {"skip", "background_only", "scent", "candidate", "evidence"}
VALID_SUPPORT_LEVELS = {SCENT, CANDIDATE, EVIDENCE}
SUPPORT_RANK = {SCENT: 1, CANDIDATE: 2, EVIDENCE: 3}

ChatFn = Callable[[list[dict[str, str]], str, str, str, int | None, float, float], dict[str, Any]]
ScoutFn = Callable[..., dict[str, Any]]

SYSTEM_PROMPT = """You are an AIppocampus warm ambient-recall scout.
Return strict JSON only. You are not memory truth and you are not answering the
user. Propose compact recall hints for deterministic local validation.

Rules:
- Do not claim facts without source refs.
- Do not include secrets, local file paths, API keys, cookies, or long quotes.
- Prefer small, useful signals over broad summaries.
- A source-backed card needs concrete source_refs. Otherwise use scent/candidate.
- If the association is private, unrelated, current-thread echo, or too weak,
  return decision "skip" or "background_only".
"""


def _stable_id(parts: list[Any]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "warc_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _clean_list(values: Any, *, limit: int, chars: int = 100) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return unique_preserve([_safe_text(item, chars) for item in values if str(item or "").strip()], limit)


def _clean_source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ref, dict):
        return {}
    line = ref.get("line", ref.get("source_line"))
    clean = {
        "thread_key": _safe_text(ref.get("thread_key"), 160),
        "title": _safe_text(ref.get("title"), 180),
        "line": line,
        "phase": _safe_text(ref.get("phase"), 80),
        "turn_index": ref.get("turn_index"),
        "message_id": _safe_text(ref.get("message_id"), 160),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def _confidence_label(value: float) -> str:
    if value >= 0.82:
        return "high"
    if value >= 0.45:
        return "medium"
    return "low"


def _mode_for_cards(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return SILENT_TUNING
    if any(card.get("support_level") == EVIDENCE for card in cards):
        return SOURCE_BACKED_RECALL_CARD
    return ACTIVE_GENTLE_NUDGE


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


def build_payload(
    prompt: str,
    *,
    cwd: Path | str,
    registry: dict[str, Any] | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    sanitized_prompt, secret_policy = sanitize_external_model_text(prompt)
    registry_obj = registry
    if registry_obj is None:
        path = (
            Path(registry_path).resolve()
            if registry_path
            else registry_paths(Path(registry_dir).resolve() if registry_dir else None)[0]
        )
        registry_obj = load_registry(path)
    prompt_terms = split_query_terms([sanitized_prompt])[:16]
    payload = {
        "prompt_version": PROMPT_VERSION,
        "task": "propose_warm_ambient_recall_hints",
        "memory_catalog": _catalog_from_registry(registry_obj),
        "workspace_name": _safe_text(Path(cwd).resolve().name, 120),
        "prompt": compact_text(sanitized_prompt, 1200),
        "prompt_terms": prompt_terms,
        "output_contract": {
            "decision": "skip|background_only|scent|candidate|evidence",
            "confidence": 0.0,
            "query_aliases": ["short search terms"],
            "themes": ["short theme labels"],
            "negative_contexts": ["when not to use this"],
            "candidates": [
                {
                    "theme": "short label",
                    "support_level": "scent|candidate|evidence",
                    "resonance": "low|medium|high",
                    "suggested_use": "private guidance for the agent",
                    "nudge": "optional active-gentle-nudge wording",
                    "key_line": "short sourced line only if available",
                    "matched_terms": ["terms"],
                    "source_refs": [
                        {
                            "thread_key": "session:...",
                            "title": "...",
                            "line": 1,
                            "message_id": "...",
                        }
                    ],
                }
            ],
            "block": False,
            "reason": "short reason",
        },
    }
    return sanitize_external_model_payload(payload), secret_policy


def scout_prompt(scout: str, payload: dict[str, Any]) -> str:
    tasks = {
        "query_expansion": "Find old question shapes, metaphors, and multilingual aliases.",
        "life_wide_cue_classifier": "Classify whether this is work, writing, philosophy, personal reflection, logistics, or routine technical flow.",
        "thread_matcher": "Match the prompt against registry summaries, titles, keywords, and route-like labels.",
        "key_line_hunter": "Find possible memorable old lines that could anchor an active nudge.",
        "current_thread_filter": "Penalize hits that look like only current-thread echo or status chatter.",
        "theme_matcher": "Compare against recurring themes, question clusters, and intuition markers.",
        "evidence_judge": "Check whether candidate source refs truly support the association.",
        "nudge_writer": "Draft one or two quiet private nudges for the foreground agent to adapt.",
        "privacy_scope_guard": "Suppress unrelated, private, or over-personalized associations.",
        "failure_sentinel": "Flag hallucinated refs, overconfident labels, or cases needing deeper archive recall.",
    }
    return json.dumps(
        {
            "input": payload,
            "scout": scout,
            "task": tasks.get(scout, "Analyze warm ambient recall relevance."),
        },
        ensure_ascii=False,
        indent=2,
    )


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
    chat_fn: ChatFn,
) -> dict[str, Any]:
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


def _clean_candidate(candidate: dict[str, Any], *, row: dict[str, Any]) -> dict[str, Any] | None:
    refs = [
        clean for clean in (_clean_source_ref(ref) for ref in candidate.get("source_refs") or []) if clean
    ][:3]
    support = str(candidate.get("support_level") or row.get("decision") or SCENT).strip().casefold()
    if support not in VALID_SUPPORT_LEVELS:
        support = CANDIDATE if row.get("decision") == "candidate" else SCENT
    if support == EVIDENCE and not refs:
        support = CANDIDATE
    theme = _safe_text(candidate.get("theme") or candidate.get("title"), 140)
    key_line = _safe_text(candidate.get("key_line") or candidate.get("snippet"), 220)
    if not theme and not key_line:
        return None
    if not theme:
        theme = compact_text(key_line, 100)
    card = {
        "card_id": _stable_id([support, theme, key_line, json.dumps(refs, sort_keys=True)]),
        "theme": theme,
        "resonance": _safe_text(candidate.get("resonance") or "medium", 40) or "medium",
        "support_level": support,
        "visibility": SOURCE_BACKED_RECALL_CARD if support == EVIDENCE else ACTIVE_GENTLE_NUDGE,
        "suggested_use": _safe_text(
            candidate.get("suggested_use")
            or ("Use only with the attached source refs." if support == EVIDENCE else "Treat as provisional resonance."),
            220,
        ),
        "nudge": _safe_text(candidate.get("nudge"), 220),
        "key_line": key_line,
        "matched_terms": _clean_list(
            candidate.get("matched_terms") or row.get("query_aliases") or [], limit=6, chars=80
        ),
        "source_refs": refs,
        "expand_if": _safe_text(
            candidate.get("expand_if")
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
    decision = str(parsed.get("decision") or "skip").strip().casefold()
    if decision not in VALID_DECISIONS:
        decision = "skip"
    confidence = clamp_confidence(parsed.get("confidence"))
    row = {
        "scout": scout,
        "ok": True,
        "decision": decision,
        "confidence": confidence,
        "query_aliases": _clean_list(
            parsed.get("query_aliases") or parsed.get("aliases") or [], limit=12, chars=80
        ),
        "themes": _clean_list(parsed.get("themes") or parsed.get("theme") or [], limit=8, chars=120),
        "negative_contexts": _clean_list(parsed.get("negative_contexts") or [], limit=8, chars=120),
        "block": bool(parsed.get("block")),
        "reason": _safe_text(parsed.get("reason"), 220),
        "usage": usage,
        "candidates": [],
    }
    candidates = [
        item for item in parsed.get("candidates") or [] if isinstance(item, dict)
    ]
    for theme in row["themes"]:
        if not any(str(item.get("theme") or "").casefold() == theme.casefold() for item in candidates):
            candidates.append(_candidate_from_theme(theme, row))
    row["candidates"] = [
        card for card in (_clean_candidate(candidate, row=row) for candidate in candidates) if card
    ][:5]
    row["useful"] = bool(
        row["decision"] in {"scent", "candidate", "evidence"}
        or row["query_aliases"]
        or row["themes"]
        or row["candidates"]
    )
    return row


def _error_row(scout: str, exc: BaseException) -> dict[str, Any]:
    return {
        "scout": scout,
        "ok": False,
        "decision": "skip",
        "confidence": 0.0,
        "query_aliases": [],
        "themes": [],
        "negative_contexts": [],
        "block": False,
        "reason": compact_text(f"{type(exc).__name__}: {exc}", 260),
        "usage": {},
        "candidates": [],
        "useful": False,
    }


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
    wait_all: bool,
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
    deadline = time.perf_counter() + max(0.01, timeout)
    tasks: queue.Queue[str] = queue.Queue()
    results: queue.Queue[dict[str, Any]] = queue.Queue()
    stop_event = threading.Event()
    for scout in scouts:
        tasks.put(scout)

    def worker_loop() -> None:
        while not stop_event.is_set():
            try:
                scout = tasks.get_nowait()
            except queue.Empty:
                return
            try:
                try:
                    row = run_scout(
                        scout,
                        payload=payload,
                        api_key=api_key,
                        model=model,
                        base_url=base_url,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        temperature=temperature,
                        chat_fn=chat_fn,
                        scout_fn=scout_fn,
                    )
                except Exception as exc:  # isolate malformed or failed scout output
                    row = _error_row(scout, exc)
                results.put(row)
            finally:
                tasks.task_done()

    # Use daemon threads so a quorum-first CLI run can return without the
    # interpreter waiting for every still-running network request. The parent
    # owns all writes, so abandoned late rows cannot mutate cache state.
    threads = [
        threading.Thread(target=worker_loop, name=f"aippocampus-warm-{idx}", daemon=True)
        for idx in range(min(worker_count, len(scouts)))
    ]
    for thread in threads:
        thread.start()

    received = 0
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


def merge_scouts(rows: list[dict[str, Any]], *, max_cards: int = DEFAULT_MAX_CARDS) -> dict[str, Any]:
    blockers = [
        row
        for row in rows
        if row.get("ok")
        and row.get("block")
        and row.get("scout") in {"privacy_scope_guard", "failure_sentinel"}
    ]
    negative_contexts: list[str] = []
    query_aliases: list[str] = []
    for row in rows:
        negative_contexts.extend(row.get("negative_contexts") or [])
        query_aliases.extend(row.get("query_aliases") or [])
    if blockers:
        return {
            "cards": [],
            "mode": SILENT_TUNING,
            "confidence": "low",
            "negative_contexts": unique_preserve(negative_contexts, limit=8),
            "query_aliases": unique_preserve(query_aliases, limit=16),
            "blocked_by": [row.get("scout") for row in blockers],
        }

    candidates: list[tuple[int, float, dict[str, Any]]] = []
    for row in rows:
        if not row.get("ok"):
            continue
        confidence = float(row.get("confidence") or 0.0)
        for card in row.get("candidates") or []:
            support = str(card.get("support_level") or SCENT)
            candidates.append((SUPPORT_RANK.get(support, 0), confidence, card))
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
        if len(cards) >= max(0, max_cards):
            break
    max_confidence = max([float(row.get("confidence") or 0.0) for row in rows if row.get("ok")] or [0.0])
    return {
        "cards": cards,
        "mode": _mode_for_cards(cards),
        "confidence": _confidence_label(max_confidence),
        "negative_contexts": unique_preserve(negative_contexts, limit=8),
        "query_aliases": unique_preserve(query_aliases, limit=16),
        "blocked_by": [],
    }


def unavailable_result(reason: str, *, secret_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "kind": "aippocampus_warm_ambient_recall",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ok": True,
        "available": False,
        "status": "unavailable",
        "reason": reason,
        "quorum_met": False,
        "accepted_scout_count": 0,
        "failed_scout_count": 0,
        "scouts": [],
        "cards": [],
        "cache_write": None,
        "secret_policy": secret_policy or None,
        "late_update_policy": "standalone_warm_path_only",
    }


def run_warm_ambient_recall(
    prompt: str,
    *,
    cwd: Path | str,
    thread_id: str | None = None,
    topic_epoch: str | None = None,
    registry: dict[str, Any] | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    cache_path: Path | str | None = None,
    residue_path: Path | str | None = None,
    residue_reason: str = "warm_scout",
    api_key: str | None = None,
    api_key_env: str = "DEEPSEEK_API_KEY",
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    max_tokens: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    temperature: float = DEFAULT_TEMPERATURE,
    scouts: tuple[str, ...] = DEFAULT_SCOUTS,
    quorum: int = DEFAULT_QUORUM,
    max_workers: int | None = None,
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
    key_value = api_key or os.environ.get(api_key_env)
    if not key_value:
        return unavailable_result("missing api key", secret_policy=secret_policy)
    payload, secret_policy = build_payload(
        prompt,
        cwd=cwd_path,
        registry=registry,
        registry_path=registry_path,
        registry_dir=registry_dir,
    )

    scout_names = tuple(name for name in scouts if name in set(DEFAULT_SCOUTS))
    rows, quorum_met = run_scout_batch(
        scouts=scout_names,
        payload=payload,
        api_key=str(key_value),
        model=model,
        base_url=base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        quorum=quorum,
        max_workers=max_workers,
        wait_all=wait_all,
        chat_fn=chat_fn,
        scout_fn=scout_fn,
    )
    merged = merge_scouts(rows)
    usage_total: dict[str, Any] = {}
    for row in rows:
        add_usage(usage_total, compact_usage(row.get("usage") or {}))
    terms_for_epoch = unique_preserve(
        [*payload.get("prompt_terms", []), *merged.get("query_aliases", [])], limit=16
    )
    resolved_epoch = topic_epoch or topic_epoch_from_terms(terms_for_epoch)
    resolved_thread = thread_id or workspace_thread_key(cwd_path)
    registry_path_obj = (
        Path(registry_path).resolve()
        if registry_path
        else registry_paths(Path(registry_dir).resolve() if registry_dir else None)[0]
    )
    resolved_cache_path = (
        Path(cache_path).resolve() if cache_path else default_ambient_cache_path(registry_path=registry_path_obj)
    )
    cache_write = None
    if merged["cards"] and not no_write:
        cache_write = write_thread_cache(
            resolved_cache_path,
            thread_id=resolved_thread,
            workspace=str(cwd_path),
            topic_epoch=resolved_epoch,
            cards=merged["cards"],
            mode=merged["mode"],
            confidence=merged["confidence"],
            negative_contexts=merged["negative_contexts"],
            residue_path=Path(residue_path).resolve() if residue_path else None,
            residue_reason=residue_reason,
        )
    accepted_count = len([row for row in rows if row.get("ok") and row.get("useful")])
    failed_count = len([row for row in rows if not row.get("ok")])
    status = "written" if cache_write and cache_write.get("status") == "written" else "ready"
    if not rows:
        status = "timeout"
    return {
        "kind": "aippocampus_warm_ambient_recall",
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "ok": True,
        "available": bool(rows and accepted_count),
        "status": status,
        "reason": "",
        "quorum_met": quorum_met,
        "scout_count": len(scout_names),
        "accepted_scout_count": accepted_count,
        "failed_scout_count": failed_count,
        "scouts": rows,
        "mode": merged["mode"],
        "confidence": merged["confidence"],
        "topic_epoch": resolved_epoch,
        "cards": merged["cards"],
        "negative_contexts": merged["negative_contexts"],
        "blocked_by": merged["blocked_by"],
        "cache_write": cache_write,
        "usage": usage_total,
        "cache": deepseek_cache_metrics_from_usage(usage_total),
        "secret_policy": secret_policy,
        "cached": False,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
        "created_at": now_utc(),
        "late_update_policy": "quorum_result_may_warm_thread_cache; foreground hook must not wait_all",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--thread-id")
    parser.add_argument("--topic-epoch")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--cache")
    parser.add_argument("--residue")
    parser.add_argument("--residue-reason", default="warm_scout")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--quorum", type=int, default=DEFAULT_QUORUM)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--wait-all", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_warm_ambient_recall(
        args.prompt,
        cwd=args.cwd,
        thread_id=args.thread_id,
        topic_epoch=args.topic_epoch,
        registry_path=args.registry,
        registry_dir=args.registry_dir,
        cache_path=args.cache,
        residue_path=args.residue,
        residue_reason=args.residue_reason,
        api_key=os.environ.get(args.api_key_env),
        api_key_env=args.api_key_env,
        model=args.model,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        temperature=args.temperature,
        quorum=args.quorum,
        max_workers=args.max_workers,
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
