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
from search_clean_source import iter_clean_messages
from subconscious_runtime import add_usage, call_chat_json, compact_usage
from subconscious_worker import DEFAULT_BASE_URL, DEFAULT_MODEL, clamp_confidence, parse_model_json

PROMPT_VERSION = "aippocampus-warm-ambient-recall-v0"
SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = float(os.environ.get("AIPPOCAMPUS_WARM_RECALL_TIMEOUT", "1.8"))
DEFAULT_QUORUM = int(os.environ.get("AIPPOCAMPUS_WARM_RECALL_QUORUM", "3"))
DEFAULT_MAX_CARDS = 3
DEFAULT_MAX_CATALOG_ITEMS = int(os.environ.get("AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT", "64"))
DEFAULT_TEMPERATURE = float(os.environ.get("AIPPOCAMPUS_WARM_RECALL_TEMPERATURE", "0.2"))
DEFAULT_USER_ID_PREFIX = "aip-warm"
WARM_JOB_SCHEMA_VERSION = 1

SCOUT_FAMILIES = (
    "intent_mode_classifier",
    "privacy_boundary_guard",
    "deep_theme_matcher",
    "key_line_hunter",
    "evidence_gap_sentinel",
    "user_style_preference",
    "trajectory_matcher",
    "cross_domain_bridge",
    "nudge_writer",
    "semantic_expander",
)

SCOUT_VARIANTS = (
    "direct",
    "registry_window",
    "clean_source_window",
    "current_trace_window",
    "skeptic_window",
)

DEFAULT_SCOUTS = tuple(
    f"{family}:{variant}" for family in SCOUT_FAMILIES for variant in SCOUT_VARIANTS
)

SCOUT_PRIORITY = {
    "intent_mode_classifier": "P0",
    "privacy_boundary_guard": "P0",
    "deep_theme_matcher": "P0",
    "key_line_hunter": "P0",
    "evidence_gap_sentinel": "P0",
    "user_style_preference": "P1",
    "trajectory_matcher": "P1",
    "cross_domain_bridge": "P1",
    "nudge_writer": "P1",
    "semantic_expander": "P1",
}

LEGACY_SCOUT_ALIASES = {
    "query_expansion": "semantic_expander",
    "life_wide_cue_classifier": "intent_mode_classifier",
    "thread_matcher": "trajectory_matcher",
    "current_thread_filter": "evidence_gap_sentinel",
    "theme_matcher": "deep_theme_matcher",
    "evidence_judge": "evidence_gap_sentinel",
    "privacy_scope_guard": "privacy_boundary_guard",
    "failure_sentinel": "evidence_gap_sentinel",
}

VALID_DECISIONS = {"skip", "background_only", "scent", "candidate", "evidence"}
VALID_SUPPORT_LEVELS = {SCENT, CANDIDATE, EVIDENCE}
VALID_TOPIC_EPOCH_ACTIONS = {"reuse", "rotate", "suppress"}
SUPPORT_RANK = {SCENT: 1, CANDIDATE: 2, EVIDENCE: 3}

ChatFn = Callable[[list[dict[str, str]], str, str, str, int | None, float, float], dict[str, Any]]
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


def warm_deepseek_user_id(*, cwd: Path | str, thread_id: str | None = None, user_id: str | None = None) -> str:
    if user_id:
        if not re.fullmatch(r"[a-zA-Z0-9\-_]{1,512}", user_id):
            raise ValueError("user_id must match [a-zA-Z0-9\\-_]+ and be at most 512 chars")
        return user_id
    seed = f"{Path(cwd).resolve()}\n{thread_id or ''}\nwarm-ambient-recall"
    return f"{DEFAULT_USER_ID_PREFIX}-{hashlib.sha1(seed.casefold().encode('utf-8')).hexdigest()[:32]}"

SYSTEM_PROMPT = """You are an AIppocampus warm ambient-recall scout.
Return strict JSON only. You are not memory truth and you are not answering the
user. Propose compact recall hints for deterministic local validation.

Rules:
- Do not claim facts without source refs.
- Only cite source_refs already present in the shared context; if no concrete
  source_ref is available, return an empty source_refs array.
- Do not include secrets, local file paths, API keys, cookies, or long quotes.
- Prefer small, useful signals over broad summaries.
- A source-backed card needs concrete source_refs. Otherwise use scent/candidate.
- Topic epoch is an LLM judgment: return topic_epoch_action
  "reuse|rotate|suppress", a short topic_epoch_label, and topic_epoch_reason
  when the current prompt trace suggests cache reuse or rotation.
- If the association is private, unrelated, current-thread echo, or too weak,
  return decision "skip" or "background_only".
"""

FAMILY_TASKS = {
    "intent_mode_classifier": "Classify task mode, visibility bias, collaboration posture, and cognitive load.",
    "privacy_boundary_guard": "Suppress credential leaks, personal/financial/relationship material, professional secrets, and over-personalized associations.",
    "deep_theme_matcher": "Match long-running themes, philosophical motives, emotional resonance, and recurring trade-offs.",
    "key_line_hunter": "Find memorable lines, visual images, metaphors, strong assertions, and unresolved questions.",
    "evidence_gap_sentinel": "Check source-ref support, hallucinated refs, missing premises, drift, single-source fragility, and timeliness gaps.",
    "user_style_preference": "Detect source-backed user expression habits, language preferences, pacing, and thinking style.",
    "trajectory_matcher": "Locate the current turn in project, life, or thread trajectory when source sidecars support it.",
    "cross_domain_bridge": "Map technical issues to non-technical ideas, and non-technical ideas back to concrete work.",
    "nudge_writer": "Draft one or two quiet private nudges for the foreground agent to adapt.",
    "semantic_expander": "Generate multilingual, metaphor, and query aliases for cold path and next-turn recall.",
}

VARIANT_TASKS = {
    "direct": "Use the direct sanitized prompt and its most literal cues.",
    "registry_window": "Focus on registry titles, summaries, anchors, and project labels.",
    "clean_source_window": "Focus on source-ref-backed candidate windows and exact support.",
    "current_trace_window": "Focus on recent sanitized prompt trace and detect current-thread echo.",
    "skeptic_window": "Act as a skeptical validator; prefer suppress, downgrade, or no-op when weak.",
}

FAMILY_LENS_TASKS = {
    "intent_mode_classifier": "Classify task type, collaboration posture, timeline, flow focus, and cognitive load.",
    "privacy_boundary_guard": "Guard privacy and boundaries before any recall card becomes visible.",
    "deep_theme_matcher": "Compare philosophical, product, emotional, obsession-level, and trade-off themes.",
    "key_line_hunter": "Hunt for compact key lines that can anchor useful recall.",
    "evidence_gap_sentinel": "Apply closed-book source-ref validation and gap detection.",
    "user_style_preference": "Infer only source-backed expression habits and user preferences.",
    "trajectory_matcher": "Match current position in project/thread/life trajectory from available sidecars.",
    "cross_domain_bridge": "Bridge technical and non-technical domains without upgrading unsupported resonance.",
    "nudge_writer": "Draft quiet private guidance only after the card is useful; keep wording tentative unless evidence-backed.",
    "semantic_expander": "Find query aliases, metaphors, and multilingual variants for next-turn/cold-path use.",
}

VARIANT_LENS_TASKS = {
    "direct": "Use the direct prompt terms first; keep aliases close to the user's wording.",
    "registry_window": "Use registry anchor titles, summaries, keywords, and project labels as the anchor surface.",
    "clean_source_window": "Use source-ref-backed windows and support terms; do not elevate evidence without dereferenceable refs.",
    "current_trace_window": "Use the sanitized recent trace to find drift and echo; penalize matches that only repeat this thread.",
    "skeptic_window": "Search for reasons to suppress, rotate topic epoch, or downgrade support when the association is weak.",
}

FAMILY_VARIANT_LENS_TASKS = {
    ("intent_mode_classifier", "direct"): "Task type lens: coding, writing, philosophy, planning, repair, logistics, or reflection.",
    ("intent_mode_classifier", "registry_window"): "Flow-focus lens: whether the turn wants fast execution, careful research, design thinking, or quiet support.",
    ("intent_mode_classifier", "clean_source_window"): "Timeline lens: planning, implementation, debugging, calibration, cleanup, or handoff.",
    ("intent_mode_classifier", "current_trace_window"): "Collaboration posture lens: asking, approving, correcting, steering, or asking the agent to continue.",
    ("intent_mode_classifier", "skeptic_window"): "Cognitive-load lens: suppress verbose recall when the user is in a high-load execution moment.",
    ("privacy_boundary_guard", "direct"): "Credential leak lens: block tokens, cookies, connection strings, private paths, and auth-like material.",
    ("privacy_boundary_guard", "registry_window"): "Personal-health lens: downgrade health, body, medical, or intimate wellbeing associations unless explicitly requested.",
    ("privacy_boundary_guard", "clean_source_window"): "Financial lens: suppress private finances, contracts, invoices, accounts, or purchase-sensitive material.",
    ("privacy_boundary_guard", "current_trace_window"): "Relationship privacy lens: suppress family, romantic, friendship, or interpersonal conflict unless directly in scope.",
    ("privacy_boundary_guard", "skeptic_window"): "Professional secret and over-personalization lens: suppress confidential work details and unsolicited intimacy.",
    ("deep_theme_matcher", "direct"): "Philosophical abstraction lens: look for the underlying question or worldview pattern.",
    ("deep_theme_matcher", "registry_window"): "Product-specific lens: match concrete project/product decisions and long-running implementation themes.",
    ("deep_theme_matcher", "clean_source_window"): "Emotional resonance lens: detect repeated felt stakes without treating resonance as fact.",
    ("deep_theme_matcher", "current_trace_window"): "Long-term obsession lens: match durable motifs that recur across prompts and threads.",
    ("deep_theme_matcher", "skeptic_window"): "Contradiction and trade-off lens: prefer candidates that clarify a real tension, not generic similarity.",
    ("key_line_hunter", "direct"): "Visual image lens: find a concrete image or scene-like phrasing that can anchor memory.",
    ("key_line_hunter", "registry_window"): "Structural metaphor lens: find metaphors, names, or frames that organize the work.",
    ("key_line_hunter", "clean_source_window"): "Chinese-English mixing lens: preserve bilingual phrasing when the source used it.",
    ("key_line_hunter", "current_trace_window"): "Strong assertion lens: find compact, emotionally forceful lines worth recalling quietly.",
    ("key_line_hunter", "skeptic_window"): "Unanswered mystery lens: find old unresolved questions without pretending they were answered.",
    ("evidence_gap_sentinel", "direct"): "Hallucinated-ref lens: downgrade source_refs that are absent from shared context or malformed.",
    ("evidence_gap_sentinel", "registry_window"): "Single-source fragility lens: keep solitary weak hits provisional until corroborated.",
    ("evidence_gap_sentinel", "clean_source_window"): "Context-drift lens: verify the cited source supports the present hypothesis, not only a shared term.",
    ("evidence_gap_sentinel", "current_trace_window"): "Missing-premise lens: flag leaps where the current prompt lacks the prerequisite context.",
    ("evidence_gap_sentinel", "skeptic_window"): "Timeliness lens: mark potentially stale decisions, prices, people, rules, or project state as needing fresh checks.",
}

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
        "prompt": compact_text(sanitized_prompt, 1200),
        "prompt_trace": _clean_prompt_trace(prompt_trace or []),
        "prompt_terms": prompt_terms,
        "output_contract": {
            "decision": "skip|background_only|scent|candidate|evidence",
            "confidence": 0.0,
            "topic_epoch_action": "reuse|rotate|suppress",
            "topic_epoch_label": "short cache topic label",
            "topic_epoch_reason": "why to reuse, rotate, or suppress this topic epoch",
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


def scout_lane_parts(scout: str) -> tuple[str, str]:
    raw = str(scout or "").strip()
    if ":" in raw:
        family, variant = raw.split(":", 1)
    else:
        family, variant = raw, "direct"
    family = LEGACY_SCOUT_ALIASES.get(family, family)
    if family not in SCOUT_FAMILIES:
        return "", ""
    if variant not in SCOUT_VARIANTS:
        variant = "direct"
    return family, variant


def expand_scout_lanes(scouts: tuple[str, ...]) -> tuple[str, ...]:
    lanes: list[str] = []
    for scout in scouts:
        family, variant = scout_lane_parts(scout)
        if not family:
            continue
        lane = f"{family}:{variant}"
        if lane not in lanes:
            lanes.append(lane)
    return tuple(lanes)


def lens_task_for(family: str, variant: str) -> str:
    specific = FAMILY_VARIANT_LENS_TASKS.get((family, variant))
    if specific:
        return specific
    family_task = FAMILY_LENS_TASKS.get(family, "Analyze warm ambient recall relevance.")
    variant_task = VARIANT_LENS_TASKS.get(variant, "Use this candidate/query variant carefully.")
    return f"{family_task} {variant_task}"


def scout_prompt(scout: str, payload: dict[str, Any]) -> str:
    family, variant = scout_lane_parts(scout)
    return json.dumps(
        {
            "shared_context": payload,
            "scout_task": {
                "scout": f"{family}:{variant}",
                "scout_family": family,
                "scout_variant": variant,
                "family_task": FAMILY_TASKS.get(family, "Analyze warm ambient recall relevance."),
                "variant_task": VARIANT_TASKS.get(variant, "Use this candidate/query variant carefully."),
                "lens_task": lens_task_for(family, variant),
            },
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
    user_id: str | None,
    chat_fn: ChatFn,
) -> dict[str, Any]:
    kwargs = {"user_id": user_id} if user_id else {}
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
    family, variant = scout_lane_parts(scout)
    scout_id = f"{family}:{variant}" if family else str(scout or "")
    decision = str(parsed.get("decision") or "skip").strip().casefold()
    if decision not in VALID_DECISIONS:
        decision = "skip"
    epoch_action = str(parsed.get("topic_epoch_action") or "").strip().casefold()
    if epoch_action not in VALID_TOPIC_EPOCH_ACTIONS:
        epoch_action = ""
    confidence = clamp_confidence(parsed.get("confidence"))
    row = {
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
                        user_id=user_id,
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


def source_index_from_registry(
    registry: dict[str, Any] | None, *, thread_keys: set[str] | None = None
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in (registry or {}).get("threads") or []:
        if not isinstance(entry, dict):
            continue
        thread_key = str(entry.get("thread_key") or "")
        if thread_keys is not None and thread_key not in thread_keys:
            continue
        messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
        if not thread_key or not messages_path_value:
            continue
        messages = iter_clean_messages(Path(messages_path_value))
        by_id: dict[str, dict[str, Any]] = {}
        by_line: dict[str, dict[str, Any]] = {}
        for message in messages:
            message_id = str(message.get("message_id") or message.get("id") or "")
            if message_id:
                by_id[message_id] = message
            for key in ("source_line", "line", "clean_ordinal"):
                value = message.get(key)
                if value is not None:
                    by_line[str(value)] = message
        index[thread_key] = {"by_id": by_id, "by_line": by_line}
    return index


def referenced_thread_keys(rows: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        for card in row.get("candidates") or []:
            for ref in card.get("source_refs") or []:
                if isinstance(ref, dict) and ref.get("thread_key"):
                    keys.add(str(ref.get("thread_key")))
    return keys


def _message_for_ref(source_index: dict[str, dict[str, Any]], ref: dict[str, Any]) -> dict[str, Any] | None:
    thread_key = str(ref.get("thread_key") or "")
    thread_index = source_index.get(thread_key) or {}
    message_id = str(ref.get("message_id") or ref.get("id") or "")
    if message_id and message_id in (thread_index.get("by_id") or {}):
        return thread_index["by_id"][message_id]
    line = ref.get("line", ref.get("source_line"))
    if line is not None and str(line) in (thread_index.get("by_line") or {}):
        return thread_index["by_line"][str(line)]
    return None


def _message_supports_card(message: dict[str, Any], card: dict[str, Any]) -> bool:
    text = str(message.get("text") or "").casefold()
    key_line = str(card.get("key_line") or "").strip().casefold()
    if key_line and len(key_line) >= 12 and key_line in text:
        return True
    for term in card.get("matched_terms") or []:
        needle = str(term or "").strip().casefold()
        if len(needle) >= 2 and needle in text:
            return True
    return False


def validate_card_source_refs(
    card: dict[str, Any], source_index: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    refs = [ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)]
    if not refs:
        return {"status": "missing_source_refs", "checked_ref_count": 0, "supported_ref_count": 0}
    if not source_index:
        return {
            "status": "unverified_no_source_index",
            "checked_ref_count": 0,
            "supported_ref_count": 0,
        }
    checked = 0
    supported = 0
    missing = 0
    for ref in refs:
        message = _message_for_ref(source_index, ref)
        if not message:
            missing += 1
            continue
        checked += 1
        if _message_supports_card(message, card):
            supported += 1
    if supported:
        return {
            "status": "supported",
            "checked_ref_count": checked,
            "supported_ref_count": supported,
        }
    return {
        "status": "unsupported" if checked else "missing_source_ref",
        "checked_ref_count": checked,
        "supported_ref_count": 0,
        "missing_ref_count": missing,
    }


def calibrate_cards(
    cards: list[dict[str, Any]],
    *,
    source_index: dict[str, dict[str, Any]] | None = None,
    current_thread_key: str | None = None,
    allow_current_thread_echo: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    calibrated: list[dict[str, Any]] = []
    echo_count = 0
    for card in cards:
        refs = [ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)]
        if (
            current_thread_key
            and refs
            and all(str(ref.get("thread_key") or "") == current_thread_key for ref in refs)
        ):
            echo_count += 1
            if not allow_current_thread_echo:
                continue
        clean = dict(card)
        validation = validate_card_source_refs(clean, source_index or {})
        clean["source_validation"] = validation
        if clean.get("support_level") == EVIDENCE and validation.get("status") != "supported":
            clean["support_level"] = CANDIDATE
            clean["visibility"] = ACTIVE_GENTLE_NUDGE
            clean["suggested_use"] = "Treat as provisional resonance until clean source support is verified."
        calibrated.append(clean)
    return calibrated, {"current_thread_echo_count": echo_count}


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
    max_confidence = max([float(row.get("confidence") or 0.0) for row in rows if row.get("ok")] or [0.0])
    return {
        "cards": cards,
        "mode": _mode_for_cards(cards),
        "confidence": _confidence_label(max_confidence),
        "negative_contexts": unique_preserve(negative_contexts, limit=8),
        "query_aliases": unique_preserve(query_aliases, limit=16),
        "blocked_by": [],
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
        "accepted_scout_count": int(result.get("accepted_scout_count") or 0),
        "failed_scout_count": int(result.get("failed_scout_count") or 0),
        "scout_error_kinds": error_kinds,
        "card_count": len(result.get("cards") or []),
        "topic_epoch": result.get("topic_epoch"),
        "topic_epoch_action": (result.get("topic_epoch_decision") or {}).get("action"),
        "current_thread_echo_count": int(result.get("current_thread_echo_count") or 0),
        "cache_write": _cache_write_summary(result.get("cache_write")),
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
        api_key_env=str(job.get("api_key_env") or "DEEPSEEK_API_KEY"),
        user_id=str(job.get("user_id") or "") or None,
        timeout=float(job.get("timeout") or DEFAULT_TIMEOUT),
        quorum=int(job.get("quorum") or DEFAULT_QUORUM),
        max_workers=int(job.get("max_workers") or 0) or None,
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
    api_key_env: str = "DEEPSEEK_API_KEY",
    user_id: str | None = None,
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
    resolved_user_id = warm_deepseek_user_id(cwd=cwd_path, thread_id=thread_id, user_id=user_id)
    resolved_max_workers = resolve_max_workers(max_workers)
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
        model=model,
        base_url=base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        quorum=quorum,
        max_workers=resolved_max_workers,
        user_id=resolved_user_id,
        wait_all=wait_all,
        chat_fn=chat_fn,
        scout_fn=scout_fn,
    )
    merged = merge_scouts(
        rows,
        source_index=source_index_from_registry(
            registry_obj, thread_keys=referenced_thread_keys(rows)
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
        "user_id": resolved_user_id,
        "accepted_scout_count": accepted_count,
        "failed_scout_count": failed_count,
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
        "cache": deepseek_cache_metrics_from_usage(usage_total),
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
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--user-id", help="Optional DeepSeek user_id; omit to send a stable sanitized hash.")
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
        api_key=os.environ.get(args.api_key_env),
        api_key_env=args.api_key_env,
        user_id=args.user_id,
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
