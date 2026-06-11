#!/usr/bin/env python3
"""Progressive recall navigation helpers for the MCP surface.

These helpers intentionally return route handles, not remembered facts. A
handle can guide an agent from a fuzzy cue to a source reopen step, but the
handle itself must stay small, read-only, and invalidated when local source
artifacts change. This prevents a future "helpful" optimization from turning
MCP navigation into another long-lived memory cache.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.mcp.continuity_routes import continuity_routes_for_context
from aippocampus_runtime.mcp.source_ref_registry import (
    registry_source_fingerprint_invalidations,
    source_candidate_dirs_for_ref,
)
from aippocampus_runtime.recall.active_recall_lock import (
    default_active_recall_lock_path,
    reopen_lock_sources,
)
from aippocampus_runtime.recall.continuity_domains import (
    clean_source_fingerprint as continuity_clean_source_fingerprint,
)
from aippocampus_runtime.recall.continuity_domains import (
    continuity_domain_snapshot_fingerprint,
    continuity_domains_latest_path_for_clean_source,
    domain_brief_for_deepen,
    load_continuity_domains_snapshot,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry import api as registry
from aippocampus_runtime.registry.search import entry_search_score
from aippocampus_runtime.source.search import iter_clean_messages, search_clean_source

HANDLE_PREFIX = "aippo-nav:"
HANDLE_SCHEMA_VERSION = 1
NAVIGATION_SCHEMA_VERSION = 1
DEFAULT_MAX_ROUTES = 5
MAX_HANDLE_REFS = 3
MAX_SOURCE_WINDOW_MESSAGES = 8
MAX_INTENT_CHARS = 280
DEFAULT_TTL_SECONDS = 30 * 60
_ROUTE_TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "benchmark_claim_posture",
        (
            "benchmark",
            "quality gate",
            "quality_gate",
            "claim",
            "cannot_claim",
            "current claims",
            "evidence map",
            "readiness",
            "over-conservative",
            "overconservative",
        ),
    ),
    (
        "issue_backlog_interpretation",
        ("issue", "backlog", "project triage", "milestone", "roadmap", "planning"),
    ),
    (
        "developer_assessment",
        ("developer assessment", "evaluation", "review", "critique", "second-user"),
    ),
    (
        "competitor_comparison",
        ("competitor", "comparison", "baseline", "external", "amemgym", "longmemeval", "mem0", "zep"),
    ),
    (
        "route_usefulness_feedback",
        (
            "usefulness",
            "blind deepen",
            "manual search",
            "wrong route",
            "route label",
            "hint collision",
            "wasted motion",
        ),
    ),
    (
        "source_reopen_boundary",
        ("source reopen", "source-backed", "currentness", "conflict", "privacy", "mask"),
    ),
    (
        "agent_native_recall_facade",
        ("agent recall", "memorypacket", "memory packet", "deepen", "mcp", "facade"),
    ),
    (
        "workflow_contract",
        ("aippo", "working contract", "clause", "skill", "ficus"),
    ),
    (
        "coding_route_recovery",
        ("rejected route", "test failed", "failed route", "patch", "pr", "pull request"),
    ),
)


class RecallNavigationError(ValueError):
    """MCP-safe navigation error with a stable public code."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _stable_id(*parts: Any, prefix: str = "route") -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:18]}"


def _fingerprint_paths(paths: list[Path]) -> str:
    parts: list[str] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            parts.append(f"{path.name}:missing")
            continue
        parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return _stable_id(*parts, prefix="source")


def clean_source_fingerprint(source_dir: Path) -> str:
    return continuity_clean_source_fingerprint(source_dir)


def _encode_handle(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return HANDLE_PREFIX + encoded


def _decode_handle(value: str) -> dict[str, Any]:
    if not value.startswith(HANDLE_PREFIX):
        if value.startswith("deepen:"):
            raise RecallNavigationError(
                "malformed_recall_handle",
                (
                    "This looks like a display route id, not a callable recall handle. "
                    "Use the opaque value from deepen_requests[].handle."
                ),
                received_handle_family="display_deepen_route_id",
                callable_handle_field="deepen_requests[].handle",
            )
        raise RecallNavigationError(
            "malformed_recall_handle",
            (
                "recall_deepen requires a recall_context handle or navigation seed. "
                "For agent recall output, use deepen_requests[].handle."
            ),
        )
    raw = value[len(HANDLE_PREFIX) :]
    try:
        padding = "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode((raw + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as exc:
        raise RecallNavigationError(
            "malformed_recall_handle",
            "The recall navigation handle could not be decoded.",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != HANDLE_SCHEMA_VERSION:
        raise RecallNavigationError(
            "malformed_recall_handle",
            "The recall navigation handle has an unsupported shape.",
        )
    return payload


def _clean_ref(item: dict[str, Any]) -> dict[str, Any]:
    clean = {
        "thread_key": item.get("thread_key"),
        "source_id": item.get("source_id"),
        "message_id": item.get("message_id") or item.get("id"),
        "turn_id": item.get("turn_id"),
        "turn_index": item.get("turn_index"),
        "line": item.get("line") or item.get("source_line"),
        "phase": item.get("phase") or "",
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def _query_terms(intent: str) -> list[str]:
    stop_terms = {
        "继续",
        "记忆",
        "回忆",
        "里的",
        "那个",
        "这个",
        "之前",
        "上次",
    }
    terms = split_query_terms([_safe_text(intent, MAX_INTENT_CHARS)])
    out: list[str] = []
    for term in terms:
        clean = _safe_text(term, 80)
        low = clean.casefold()
        if not clean or low in stop_terms:
            continue
        if any(marker in low for marker in ("secret", "token", "password", "credential")):
            continue
        if any(marker in clean for marker in (":", "\\", "/")):
            continue
        out.append(clean)
        if len(out) >= 12:
            break
    return out


def _safe_label_token(value: Any, *, fallback: str = "route") -> str:
    text = _safe_text(value, 48).casefold().replace("-", "_").replace(" ", "_")
    clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text).strip("_")
    if not clean or any(marker in clean for marker in ("secret", "token", "password", "credential")):
        return fallback
    return clean[:48].strip("_") or fallback


def _scope_bucket(hit: dict[str, Any]) -> str:
    labels = [
        str(label)
        for label in [*(hit.get("scope_labels") or []), *(hit.get("semantic_scope_labels") or [])]
        if isinstance(label, str) and label.strip()
    ]
    if labels:
        return _safe_label_token(labels[0], fallback="scoped")
    phase = _safe_label_token(hit.get("phase"), fallback="")
    return phase or _safe_label_token(hit.get("role"), fallback="source_window")


def _matched_cue_family(hit: dict[str, Any]) -> str:
    bucket = _scope_bucket(hit)
    if bucket in {"final_answer", "assistant", "user", "source_window"}:
        return "clean_source_hit"
    return f"scope_{bucket}"


def _route_label_for_clean_hit(hit: dict[str, Any]) -> str:
    bucket = _scope_bucket(hit)
    if bucket in {"final_answer", "assistant", "user", "source_window"}:
        return f"{bucket} source route"
    return f"{bucket} route"


def _route_topic_for_clean_hit(hit: dict[str, Any], *, intent: str) -> dict[str, Any]:
    local_text = " ".join(
        str(value or "")
        for value in (
            hit.get("phase"),
            hit.get("role"),
            hit.get("snippet"),
            " ".join(str(label) for label in hit.get("scope_labels") or []),
            " ".join(str(label) for label in hit.get("semantic_scope_labels") or []),
        )
    ).casefold()
    query_text = str(intent or "").casefold()
    matched: list[tuple[int, str]] = []
    for topic, cues in _ROUTE_TOPIC_RULES:
        score = sum(1 for cue in cues if cue.casefold() in local_text)
        if score:
            matched.append((score, topic))
    if not matched:
        for topic, cues in _ROUTE_TOPIC_RULES:
            score = sum(1 for cue in cues if cue.casefold() in query_text)
            if score:
                matched.append((score, topic))
    if matched:
        matched.sort(key=lambda item: (-item[0], item[1]))
        matched_topics = [topic for _, topic in matched]
        return {
            "route_topic": matched_topics[0],
            "label_granularity": "topic_label",
            "route_label_specificity_score": 1.0 if len(matched_topics) == 1 else 0.85,
            "topic_reason_codes": [f"topic_{topic}" for topic in matched_topics[:3]],
        }
    return {
        "route_topic": "",
        "label_granularity": "scope_bucket_only",
        "route_label_specificity_score": 0.35,
        "topic_reason_codes": ["no_safe_topic_label"],
    }


def _route_label_for_topic(hit: dict[str, Any], topic: Mapping[str, Any]) -> str:
    route_topic = str(topic.get("route_topic") or "").strip()
    if route_topic:
        return f"{route_topic} route"
    return _route_label_for_clean_hit(hit)


def _route_handle(
    *,
    source_dir: Path,
    route_id: str,
    source_refs: list[dict[str, Any]],
    evidence_level: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    now = int(time.time())
    return _encode_handle(
        {
            "schema_version": HANDLE_SCHEMA_VERSION,
            "kind": "source_ref",
            "route_id": route_id,
            "evidence_level": evidence_level,
            "source_refs": source_refs[:MAX_HANDLE_REFS],
            "source_fingerprint": clean_source_fingerprint(source_dir),
            "issued_unix": now,
            "expires_unix": now + max(1, ttl_seconds),
        }
    )


def _boundary() -> dict[str, Any]:
    return {
        "navigation_only_not_fact": True,
        "read_only": True,
        "source_reopen_required_for_strong_claims": True,
        "clean_source_is_authority": True,
        "handles_are_short_lived": True,
        "no_raw_prompt_text": True,
        "no_raw_private_paths": True,
    }


def _route_from_clean_hit(
    hit: dict[str, Any],
    *,
    source_dir: Path,
    intent: str,
) -> dict[str, Any]:
    source_refs = [_clean_ref(hit)]
    route_id = _stable_id("clean_source", source_refs[0], hit.get("score"))
    handle = _route_handle(
        source_dir=source_dir,
        route_id=route_id,
        source_refs=source_refs,
        evidence_level="needs_reopen",
    )
    scope_labels = [
        str(label)
        for label in [*(hit.get("scope_labels") or []), *(hit.get("semantic_scope_labels") or [])]
        if isinstance(label, str)
    ]
    scope_bucket = _scope_bucket(hit)
    matched_cue_family = _matched_cue_family(hit)
    route_topic = _route_topic_for_clean_hit(hit, intent=intent)
    return {
        "handle": handle,
        "route_id": route_id,
        "kind": "source_window",
        "title": _safe_text(
            hit.get("phase") or hit.get("role") or hit.get("turn_id") or "source window",
            90,
        ),
        "summary": _safe_text(hit.get("snippet"), 220),
        "evidence_level": "needs_reopen",
        "support_level": "navigation",
        "source_refs": source_refs,
        "scope_labels": list(dict.fromkeys(scope_labels))[:8],
        "scope_bucket": scope_bucket,
        "matched_cue_family": matched_cue_family,
        "route_topic": route_topic["route_topic"],
        "label_granularity": route_topic["label_granularity"],
        "route_label_specificity_score": route_topic["route_label_specificity_score"],
        "route_label": _route_label_for_topic(hit, route_topic),
        "triage_rank_reason_codes": [
            *route_topic["topic_reason_codes"],
            f"scope_bucket_{scope_bucket}",
            matched_cue_family,
            "clean_source_reopenable",
        ][:4],
        "reopenable": True,
        "why_this_may_matter": (
            f"A {route_topic['label_granularity']} clean-source route matched the cue; "
            "reopen before using exact claims."
        ),
        "suggested_next": {
            "tool": "recall_deepen",
            "arguments": {"handle": handle},
        },
        "source_reopen_path": {
            "tool": "get_turn_context",
            "arguments": {
                key: source_refs[0][key]
                for key in ("message_id", "turn_id", "turn_index")
                if key in source_refs[0]
            },
        },
    }


def _registry_routes(
    *,
    intent: str,
    registry_dir: Path | None,
    max_routes: int,
) -> list[dict[str, Any]]:
    json_path, _ = registry.registry_paths(registry_dir)
    if not json_path.exists():
        return []
    terms = _query_terms(intent)
    payload = registry.load_registry(json_path)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for entry in payload.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        score = entry_search_score(entry, terms)
        if score <= 0:
            continue
        candidates.append((score, entry))
    candidates.sort(key=lambda item: -item[0])
    routes: list[dict[str, Any]] = []
    for score, entry in candidates[:max_routes]:
        route_id = _stable_id("registry", entry.get("thread_key"), score)
        routes.append(
            {
                "handle": {
                    "kind": "thread_candidate",
                    "thread_key": entry.get("thread_key"),
                    "route_id": route_id,
                },
                "route_id": route_id,
                "kind": "thread_candidate",
                "title": _safe_text(entry.get("title") or entry.get("thread_key"), 120),
                "summary": _safe_text(entry.get("summary") or entry.get("workspace_name"), 180),
                "evidence_level": "candidate",
                "support_level": "navigation",
                "source_refs": [{"thread_key": entry.get("thread_key")}],
                "scope_labels": [
                    str(label)
                    for label in entry.get("scope_labels") or []
                    if isinstance(label, str)
                ][:8],
                "reopenable": False,
                "why_this_may_matter": "A registry thread matched the cue; search or reopen concrete source refs before relying on it.",
                "suggested_next": {"tool": "search_memory"},
            }
        )
    return routes


def recall_context_packet(
    *,
    intent: str,
    cwd: Path,
    clean_source_dir: Path,
    registry_dir: Path | None = None,
    continuity_domains_snapshot_path: Path | None = None,
    max_routes: int = DEFAULT_MAX_ROUTES,
) -> dict[str, Any]:
    clean_intent = _safe_text(intent, MAX_INTENT_CHARS)
    if not clean_intent:
        raise RecallNavigationError(
            "missing_intent",
            "recall_context requires a non-empty intent or query.",
        )
    limit = max(1, min(25, int(max_routes or DEFAULT_MAX_ROUTES)))
    search_result = search_clean_source(
        cwd,
        [clean_intent],
        clean_source_dir=clean_source_dir,
        limit=limit,
        snippet_chars=220,
    )
    routes = [
        _route_from_clean_hit(hit, source_dir=clean_source_dir, intent=clean_intent)
        for hit in search_result.get("matches") or []
        if isinstance(hit, dict)
    ]
    snapshot_path = continuity_domains_snapshot_path or continuity_domains_latest_path_for_clean_source(
        clean_source_dir
    )
    continuity_routes = continuity_routes_for_context(
        intent=clean_intent,
        clean_source_dir=clean_source_dir,
        snapshot_path=snapshot_path,
        registry_dir=registry_dir,
        max_routes=limit,
    )
    domain_routes = continuity_routes["domain_routes"]
    pathlet_routes = continuity_routes["pathlet_routes"]
    routes = [*domain_routes, *pathlet_routes, *routes]
    if len(routes) < limit:
        routes.extend(
            _registry_routes(
                intent=clean_intent,
                registry_dir=registry_dir,
                max_routes=limit - len(routes),
            )
        )
    continuity_status = continuity_routes["continuity_route_status"]
    suggested_next = (
        "recall_deepen"
        if routes
        else "publish_continuity_domains_snapshot"
        if continuity_status["snapshot_status"] in {"missing", "unreadable"}
        else "search_clean_source"
    )
    return {
        "kind": "aippocampus_recall_context",
        "schema_version": NAVIGATION_SCHEMA_VERSION,
        "support_level": "navigation",
        "status": "ok" if routes else "no_routes",
        "query_terms": _query_terms(clean_intent),
        "routes": routes[:limit],
        "route_count": len(routes[:limit]),
        "suggested_next": suggested_next,
        "continuity_route_status": continuity_status,
        "source_boundary": _boundary(),
        "metrics": {
            "funnel_stage": "context",
            "handle_count": len([route for route in routes[:limit] if route.get("handle")]),
            "continuity_domain_route_count": len(domain_routes),
            "continuity_pathlet_route_count": len(pathlet_routes),
            "source_reopen_success_rate_observed": None,
            "wrong_or_stale_handle_rate_observed": None,
        },
        "warnings": list(search_result.get("warnings") or []),
    }


def _unwrap_navigation_seed(handle: Any) -> Any:
    if isinstance(handle, dict) and handle.get("kind") == "recall_context_seed":
        return handle.get("handle")
    return handle


def normalize_handle(handle: Any) -> dict[str, Any]:
    current = _unwrap_navigation_seed(handle)
    if isinstance(current, str):
        return _decode_handle(current)
    if isinstance(current, dict):
        kind = str(current.get("kind") or "")
        if kind == "source_ref":
            refs = current.get("source_refs") or []
            if isinstance(refs, dict):
                refs = [refs]
            if not isinstance(refs, list) or not refs:
                raise RecallNavigationError(
                    "malformed_recall_handle",
                    "source_ref handles require at least one source ref.",
                )
            return {
                "schema_version": HANDLE_SCHEMA_VERSION,
                "kind": "source_ref",
                "route_id": current.get("route_id") or _stable_id("source_ref", refs),
                "source_refs": [_clean_ref(ref) for ref in refs if isinstance(ref, dict)],
                "source_fingerprint": current.get("source_fingerprint"),
            }
        if kind in {"active_recall_lock", "active_lock"}:
            lock_id = current.get("lock_id") or current.get("handle")
            if not lock_id:
                raise RecallNavigationError(
                    "malformed_recall_handle",
                    "active recall lock handles require lock_id.",
                )
            return {
                "schema_version": HANDLE_SCHEMA_VERSION,
                "kind": "active_recall_lock",
                "lock_id": str(lock_id),
                "topic_epoch": current.get("topic_epoch"),
                "expected_lock_version": current.get("expected_lock_version"),
            }
        if kind == "continuity_domain":
            domain_id = current.get("domain_id")
            if not domain_id:
                raise RecallNavigationError(
                    "malformed_recall_handle",
                    "continuity domain handles require domain_id.",
                )
            refs = [_clean_ref(ref) for ref in current.get("source_refs") or [] if isinstance(ref, dict)]
            if not refs:
                raise RecallNavigationError(
                    "malformed_recall_handle",
                    "continuity domain handles require source refs.",
                )
            if not current.get("snapshot_fingerprint") or not current.get("expires_unix"):
                raise RecallNavigationError(
                    "malformed_recall_handle",
                    "continuity domain handles require snapshot freshness fields.",
                )
            return {
                "schema_version": HANDLE_SCHEMA_VERSION,
                "kind": "continuity_domain",
                "domain_id": str(domain_id),
                "source_refs": refs,
                "source_fingerprint": current.get("source_fingerprint"),
                "snapshot_fingerprint": current.get("snapshot_fingerprint"),
                "registry_source_fingerprints": current.get("registry_source_fingerprints")
                if isinstance(current.get("registry_source_fingerprints"), dict)
                else {},
                "issued_unix": current.get("issued_unix"),
                "expires_unix": current.get("expires_unix"),
            }
    raise RecallNavigationError(
        "malformed_recall_handle",
        "recall_deepen requires a recall_context handle or navigation seed.",
    )


def _message_matches_ref(message: dict[str, Any], ref: dict[str, Any]) -> bool:
    if ref.get("message_id") and str(message.get("message_id") or message.get("id") or "") == str(
        ref.get("message_id")
    ):
        return True
    if ref.get("turn_id") and str(message.get("turn_id") or "") == str(ref.get("turn_id")):
        return True
    if ref.get("turn_index") and str(message.get("turn_index") or "") == str(
        ref.get("turn_index")
    ):
        return True
    if ref.get("line") and str(message.get("source_line") or "") == str(ref.get("line")):
        return True
    return False


def _turn_messages(messages: list[dict[str, Any]], selected: dict[str, Any]) -> list[dict[str, Any]]:
    turn_id = selected.get("turn_id")
    turn_index = selected.get("turn_index")
    if not turn_id and turn_index is None:
        return [selected]
    window = [
        message
        for message in messages
        if (turn_id and message.get("turn_id") == turn_id)
        or (turn_index is not None and message.get("turn_index") == turn_index)
    ]
    window.sort(key=lambda item: int(item.get("clean_ordinal") or item.get("source_line") or 0))
    return window[:MAX_SOURCE_WINDOW_MESSAGES]


def _public_source_message(message: dict[str, Any]) -> dict[str, Any]:
    clean = dict(message)
    if "text" in clean:
        clean["text"] = _safe_text(clean.get("text"), 1200)
    return clean


def _source_ref_deepen_payload(
    handle: dict[str, Any],
    *,
    clean_source_dir: Path,
    registry_dir: Path | None = None,
) -> dict[str, Any]:
    expected_fingerprint = handle.get("source_fingerprint")
    current_fingerprint = clean_source_fingerprint(clean_source_dir)
    if expected_fingerprint and expected_fingerprint != current_fingerprint:
        raise RecallNavigationError(
            "stale_recall_handle",
            "The recall navigation handle is stale; rerun recall_context before reopening source.",
            invalidated_by=["clean_source_fingerprint_changed"],
        )
    refs = [ref for ref in handle.get("source_refs") or [] if isinstance(ref, dict)]
    if not refs:
        raise RecallNavigationError(
            "malformed_recall_handle",
            "recall_deepen could not find source refs in the handle.",
        )
    selected = None
    selected_ref = None
    selected_messages: list[dict[str, Any]] = []
    for ref in refs:
        candidate_dirs = source_candidate_dirs_for_ref(
            ref,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
        )
        for candidate_dir in candidate_dirs:
            messages = iter_clean_messages(candidate_dir / "messages.jsonl")
            selected = next(
                (message for message in messages if _message_matches_ref(message, ref)),
                None,
            )
            if not selected:
                continue
            selected_messages = messages
            break
        if selected:
            selected_ref = _clean_ref({**selected, **ref})
            break
    if not selected:
        raise RecallNavigationError(
            "source_ref_not_found",
            "No clean-source message matched the recall navigation handle.",
        )
    source_window = [
        _public_source_message(item)
        for item in _turn_messages(selected_messages, selected)
    ]
    source_refs = [selected_ref or _clean_ref(selected)]
    source_ref = source_refs[0]
    reopen_args = {
        key: source_ref[key]
        for key in ("thread_key", "message_id", "turn_id", "turn_index")
        if key in source_ref
    }
    return {
        "kind": "aippocampus_recall_deepen",
        "schema_version": NAVIGATION_SCHEMA_VERSION,
        "status": "ok",
        "support_level": "evidence",
        "evidence_level": "source_backed",
        "route_id": handle.get("route_id"),
        "why_this_may_matter": "The handle reopened clean source. Use this window only for claims it directly supports.",
        "source_refs": source_refs,
        "source_window": {
            "messages": source_window,
            "message_count": len(source_window),
        },
        "source_reopen_path": {
            "tool": "get_turn_context",
            "arguments": reopen_args,
        },
        "adjacent_handles": [],
        "source_boundary": {
            **_boundary(),
            "clean_source_reopened": True,
            "handle_material_was_navigation_only": True,
        },
        "metrics": {
            "funnel_stage": "deepen",
            "source_reopen_success": True,
            "wrong_or_stale_handle": False,
        },
    }


def _active_lock_deepen_payload(
    handle: dict[str, Any],
    *,
    registry_path: Path | None,
    registry_dir: Path | None,
    lock_path: Path | None,
    max_matches: int,
) -> dict[str, Any]:
    target_lock_path = lock_path or default_active_recall_lock_path(
        registry_path=registry_path,
        registry_dir=registry_dir,
    )
    reopened = reopen_lock_sources(
        target_lock_path,
        lock_id=str(handle.get("lock_id") or ""),
        registry_path=registry_path,
        topic_epoch=handle.get("topic_epoch"),
        expected_lock_version=handle.get("expected_lock_version"),
        max_matches=max_matches,
    )
    if not reopened.get("ok"):
        raise RecallNavigationError(
            "active_recall_lock_not_reopenable",
            "The active recall lock did not reopen source-backed context.",
            state=reopened.get("state"),
            errors=reopened.get("errors") or [],
        )
    matches = [
        {
            "message_id": item.get("message_id"),
            "turn_id": item.get("turn_id"),
            "turn_index": item.get("turn_index"),
            "line": item.get("line"),
            "thread_key": item.get("thread_key"),
            "phase": item.get("phase") or "",
        }
        for item in reopened.get("matches") or []
        if isinstance(item, dict)
    ]
    return {
        "kind": "aippocampus_recall_deepen",
        "schema_version": NAVIGATION_SCHEMA_VERSION,
        "status": "ok",
        "support_level": "evidence",
        "evidence_level": "source_backed",
        "route_id": handle.get("lock_id"),
        "why_this_may_matter": "The active recall lock reopened clean source.",
        "source_refs": matches,
        "source_window": {
            "messages": [
                _public_source_message(item)
                for item in reopened.get("matches") or []
                if isinstance(item, dict)
            ]
        },
        "source_reopen_path": {
            "tool": "active_recall",
            "arguments": {"mode": "reopen", "lock_id": handle.get("lock_id")},
        },
        "adjacent_handles": [],
        "source_boundary": dict(reopened.get("source_boundary") or _boundary()),
        "metrics": {
            "funnel_stage": "deepen",
            "source_reopen_success": True,
            "wrong_or_stale_handle": False,
        },
    }


def _continuity_domain_deepen_payload(
    handle: dict[str, Any],
    *,
    clean_source_dir: Path,
    snapshot_path: Path | None,
    registry_dir: Path | None = None,
) -> dict[str, Any]:
    expected_source_fingerprint = handle.get("source_fingerprint")
    current_source_fingerprint = clean_source_fingerprint(clean_source_dir)
    if expected_source_fingerprint and expected_source_fingerprint != current_source_fingerprint:
        raise RecallNavigationError(
            "stale_recall_handle",
            "The continuity domain handle is stale; rerun recall_context before reopening source.",
            invalidated_by=["clean_source_fingerprint_changed"],
        )
    effective_snapshot_path = snapshot_path or continuity_domains_latest_path_for_clean_source(
        clean_source_dir
    )
    expected_snapshot_fingerprint = handle.get("snapshot_fingerprint")
    current_snapshot_fingerprint = continuity_domain_snapshot_fingerprint(
        snapshot_path=effective_snapshot_path,
        clean_source_dir=clean_source_dir,
    )
    if expected_snapshot_fingerprint and expected_snapshot_fingerprint != current_snapshot_fingerprint:
        raise RecallNavigationError(
            "stale_recall_handle",
            "The continuity domain snapshot changed; rerun recall_context before reopening source.",
            invalidated_by=["continuity_domain_snapshot_changed"],
        )
    snapshot = load_continuity_domains_snapshot(effective_snapshot_path)
    domain_id = str(handle.get("domain_id") or "")
    brief = domain_brief_for_deepen(domain_id=domain_id, snapshot=snapshot)
    if brief is None:
        raise RecallNavigationError(
            "continuity_domain_not_found",
            "The continuity domain handle no longer exists; rerun recall_context.",
            domain_id=domain_id,
        )
    raw_lifecycle = brief.get("lifecycle")
    lifecycle: dict[str, Any] = raw_lifecycle if isinstance(raw_lifecycle, dict) else {}
    raw_claim_contract = brief.get("claim_contract")
    claim_contract: dict[str, Any] = (
        raw_claim_contract if isinstance(raw_claim_contract, dict) else {}
    )
    status = str(lifecycle.get("status") or "active")
    action = str(claim_contract.get("action_grammar") or "")
    if status in {"blocked", "stale", "superseded", "retired"} or action == "ignore_or_blocked":
        raise RecallNavigationError(
            "continuity_domain_blocked",
            "The continuity domain is blocked, stale, superseded, or retired; rerun recall_context or reopen source manually.",
            domain_id=domain_id,
            invalidated_by=[f"continuity_domain_{status}"],
        )
    refs = [ref for ref in handle.get("source_refs") or [] if isinstance(ref, dict)]
    expected_registry_fingerprints = handle.get("registry_source_fingerprints")
    expected_registry_fingerprints = (
        expected_registry_fingerprints if isinstance(expected_registry_fingerprints, dict) else {}
    )
    registry_invalidations = registry_source_fingerprint_invalidations(
        refs,
        registry_dir=registry_dir,
        expected_fingerprints=expected_registry_fingerprints,
    )
    if registry_invalidations:
        raise RecallNavigationError(
            "stale_recall_handle",
            "The registry clean-source target changed; rerun recall_context before reopening source.",
            invalidated_by=registry_invalidations,
        )
    source_payload = None
    source_error_codes: list[str] = []
    for ref in refs:
        try:
            source_payload = _source_ref_deepen_payload(
                {
                    "kind": "source_ref",
                    "route_id": _stable_id("continuity_domain", domain_id, ref),
                    "source_refs": [ref],
                    "source_fingerprint": current_source_fingerprint,
                },
                clean_source_dir=clean_source_dir,
                registry_dir=registry_dir,
            )
            break
        except RecallNavigationError as exc:
            source_error_codes.append(exc.code)
            if exc.code == "stale_recall_handle":
                raise
            continue
    source_reopened = bool(source_payload)
    return {
        "kind": "aippocampus_recall_deepen",
        "schema_version": NAVIGATION_SCHEMA_VERSION,
        "status": "ok" if source_reopened else "domain_brief_opened_source_not_found",
        "support_level": "evidence" if source_reopened else "navigation",
        "evidence_level": "source_backed_domain_brief"
        if source_reopened
        else "domain_brief_requires_source_reopen",
        "route_id": domain_id,
        "why_this_may_matter": (
            "The continuity domain opened a source-trailed working conclusion; use the "
            "clean-source window for claims and the domain brief only as navigation."
        ),
        "domain_brief": brief,
        "source_refs": refs,
        "source_window": (source_payload or {}).get("source_window", {"messages": []}),
        "source_reopen_path": (source_payload or {}).get(
            "source_reopen_path",
            {
                "tool": "search_memory",
                "arguments": {"query": brief.get("title") or domain_id},
            },
        ),
        "adjacent_handles": [],
        "source_boundary": {
            **_boundary(),
            "clean_source_reopened": source_reopened,
            "domain_brief_opened": True,
            "domain_summary_not_source": True,
            "handle_material_was_navigation_only": True,
        },
        "metrics": {
            "funnel_stage": "deepen",
            "source_reopen_success": source_reopened,
            "wrong_or_stale_handle": False,
            "source_ref_error_codes": source_error_codes[:5],
        },
    }


def recall_deepen_packet(
    *,
    handle: Any,
    clean_source_dir: Path,
    registry_path: Path | None = None,
    registry_dir: Path | None = None,
    lock_path: Path | None = None,
    continuity_domains_snapshot_path: Path | None = None,
    max_matches: int = DEFAULT_MAX_ROUTES,
) -> dict[str, Any]:
    normalized = normalize_handle(handle)
    expires_unix = normalized.get("expires_unix")
    if isinstance(expires_unix, (int, float)) and time.time() > float(expires_unix):
        raise RecallNavigationError(
            "stale_recall_handle",
            "The recall navigation handle has expired; rerun recall_context.",
            invalidated_by=["ttl_expired"],
        )
    kind = str(normalized.get("kind") or "")
    if kind == "source_ref":
        return _source_ref_deepen_payload(
            normalized,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
        )
    if kind == "active_recall_lock":
        return _active_lock_deepen_payload(
            normalized,
            registry_path=registry_path,
            registry_dir=registry_dir,
            lock_path=lock_path,
            max_matches=max(1, min(25, int(max_matches or DEFAULT_MAX_ROUTES))),
        )
    if kind == "continuity_domain":
        return _continuity_domain_deepen_payload(
            normalized,
            clean_source_dir=clean_source_dir,
            snapshot_path=continuity_domains_snapshot_path,
            registry_dir=registry_dir,
        )
    raise RecallNavigationError(
        "malformed_recall_handle",
        "The recall navigation handle has an unsupported kind.",
    )


def navigation_error_payload(exc: RecallNavigationError) -> dict[str, Any]:
    error: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.details:
        error["details"] = exc.details
    return {
        "ok": False,
        "error": error,
        "source_boundary": _boundary(),
        "metrics": {
            "funnel_stage": "deepen",
            "source_reopen_success": False,
            "wrong_or_stale_handle": exc.code in {"stale_recall_handle", "source_ref_not_found"},
        },
    }
