#!/usr/bin/env python3
"""Navigation-only query-pattern route sidecar.

Query-pattern routes are prepared by slower registry/import jobs and consumed by
the foreground hot path as scent. They deliberately keep alias text local to the
sidecar for matching, while public packets expose only ids, counts, and source
handles. A route hit is never source evidence; callers must reopen clean source
before making memory claims.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import artifact_lease
from aippocampus_runtime.core import sanitize_external_model_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.registry.api import unique_preserve

QUERY_PATTERN_ROUTE_KIND = "aippocampus_query_pattern_route"
QUERY_PATTERN_PACKET_KIND = "aippocampus_query_pattern_route_packet"
QUERY_PATTERN_PUBLISH_KIND = "aippocampus_query_pattern_route_publish_report"
QUERY_PATTERN_ROUTES_REPORT_KIND = "aippocampus_query_pattern_routes_report"
QUERY_PATTERN_ROUTE_SCHEMA_VERSION = 1
DEFAULT_QUERY_PATTERN_ROUTES_NAME = "query_pattern_routes.jsonl"

MAX_ALIASES = 12
MAX_SOURCE_REFS = 6
MAX_SELECTED = 3
MIN_SELECT_CONFIDENCE = 0.5
SECRETISH_MARKERS = ("secret", "token", "password", "credential", "api_key")
SUPPRESSED_SENSITIVITY = {"blocked", "private", "secret", "sensitive", "suppress"}
STALE_STATES = {"stale", "expired", "superseded", "rejected"}


def default_query_pattern_routes_path(registry_dir: Path) -> Path:
    return registry_dir.resolve() / DEFAULT_QUERY_PATTERN_ROUTES_NAME


def _sha(value: Any, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _looks_sensitive_text(text: str) -> bool:
    lowered = text.casefold()
    if any(marker in lowered for marker in SECRETISH_MARKERS):
        return True
    if "\\" in text or "/" in text or (len(text) > 2 and text[1:3] == ":\\"):
        return True
    return lowered.startswith("<redacted:")


def _normalize_alias(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n\"'`.,;:!?，。；：！？、")
    if not text:
        return ""
    sanitized, policy = sanitize_external_model_text(text)
    if policy.get("hard_block") or _looks_sensitive_text(sanitized):
        return ""
    return sanitized[:120]


def _aliases(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [
        alias
        for alias in unique_preserve([_normalize_alias(item) for item in value], limit=MAX_ALIASES)
        if alias
    ]


def _float_bucket(value: Any, *, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(max(0.0, min(1.0, number)), 4)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _thread_hash(row: Mapping[str, Any], refs: list[dict[str, Any]]) -> str:
    raw = row.get("thread_key_hash") or row.get("thread_hash")
    if raw:
        return str(raw)
    for ref in refs:
        if ref.get("thread_key"):
            return _sha(ref.get("thread_key"), prefix="thread")
    return _sha(row.get("source_generation_digest") or row.get("route_id"), prefix="thread")


def _route_id(row: Mapping[str, Any], aliases: list[str], refs: list[dict[str, Any]]) -> str:
    raw = str(row.get("query_pattern_route_id") or row.get("route_id") or "").strip()
    if raw:
        return raw
    material = json.dumps(
        {
            "aliases": [alias.casefold() for alias in aliases],
            "refs": refs,
            "source_generation_digest": row.get("source_generation_digest"),
            "thread_key_hash": row.get("thread_key_hash") or row.get("thread_hash"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return _sha(material, prefix="qpr")


def _state(row: Mapping[str, Any]) -> str:
    return str(row.get("state") or row.get("status") or row.get("freshness") or "current").casefold()


def _ttl_remaining(row: Mapping[str, Any], *, now_unix: float) -> int | None:
    if row.get("ttl_remaining_seconds") not in {None, ""}:
        return _int(row.get("ttl_remaining_seconds"))
    if row.get("expires_unix") not in {None, ""}:
        return int(_float(row.get("expires_unix")) - now_unix)
    if row.get("ttl_seconds") not in {None, ""}:
        created = _float(row.get("created_unix"), now_unix)
        return int(created + _float(row.get("ttl_seconds")) - now_unix)
    return None


def _privacy_blocked(row: Mapping[str, Any]) -> bool:
    if row.get("privacy_blocked") or row.get("blocked_by_privacy"):
        return True
    return str(row.get("sensitivity") or row.get("privacy_state") or "").casefold() in SUPPRESSED_SENSITIVITY


def normalize_query_pattern_route(row: Mapping[str, Any]) -> dict[str, Any]:
    refs = safe_source_refs(row.get("source_refs"))[:MAX_SOURCE_REFS]
    aliases = _aliases(row.get("query_aliases") or row.get("aliases") or row.get("query_alias_seeds") or [])
    route = {
        "kind": QUERY_PATTERN_ROUTE_KIND,
        "schema_version": QUERY_PATTERN_ROUTE_SCHEMA_VERSION,
        "query_pattern_route_id": _route_id(row, aliases, refs),
        "thread_key_hash": _thread_hash(row, refs),
        "source_generation_digest": str(row.get("source_generation_digest") or ""),
        "query_aliases": aliases,
        "source_refs": refs,
        "confidence": _float_bucket(row.get("confidence"), default=0.8),
        "state": _state(row),
        "sensitivity": str(row.get("sensitivity") or ""),
        "privacy_state": str(row.get("privacy_state") or row.get("privacy") or ""),
        "privacy_blocked": bool(row.get("privacy_blocked") or row.get("blocked_by_privacy")),
        "created_unix": row.get("created_unix"),
        "expires_unix": row.get("expires_unix"),
        "ttl_seconds": row.get("ttl_seconds"),
        "navigation_only": True,
        "output_authority": "navigation_only",
        "source_reopen_required": True,
        "source_boundary": {
            "query_pattern_routes_are_navigation_only": True,
            "query_alias_is_not_memory_truth": True,
            "query_pattern_routes_are_not_evidence": True,
            "source_reopen_required_before_claim": True,
        },
    }
    return route


def load_query_pattern_routes(path: Path) -> list[dict[str, Any]]:
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
            if isinstance(item, Mapping):
                route = normalize_query_pattern_route(item)
                if route["query_aliases"] and route["source_refs"]:
                    rows.append(route)
    return rows


def _canonical_jsonl(rows: list[dict[str, Any]]) -> str:
    ordered = sorted(rows, key=lambda row: str(row.get("query_pattern_route_id") or ""))
    if not ordered:
        return ""
    return "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in ordered) + "\n"


def _write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def publish_query_pattern_routes(
    path: Path,
    routes: Iterable[Mapping[str, Any]],
    *,
    current_generation_by_thread: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Publish a deterministic route sidecar, filtering stale generations.

    `current_generation_by_thread` is the registry/import freshness gate: if a
    row's thread hash points at a different source generation, the row is
    suppressed before publication so old aliases cannot keep waking foreground
    recall after the source changed.
    """

    current = {str(key): str(value) for key, value in (current_generation_by_thread or {}).items()}
    normalized: list[dict[str, Any]] = []
    stale_generation_suppressed_count = 0
    invalid_route_suppressed_count = 0
    privacy_suppressed_count = 0
    input_count = 0
    for row in routes:
        if not isinstance(row, Mapping):
            continue
        input_count += 1
        route = normalize_query_pattern_route(row)
        if not route["query_aliases"] or not route["source_refs"]:
            invalid_route_suppressed_count += 1
            continue
        if _privacy_blocked(row):
            privacy_suppressed_count += 1
            continue
        expected_generation = current.get(str(route["thread_key_hash"]))
        if expected_generation and route["source_generation_digest"] != expected_generation:
            stale_generation_suppressed_count += 1
            continue
        normalized.append(route)

    text = _canonical_jsonl(normalized)
    old_text = path.read_text(encoding="utf-8") if path.exists() else None
    changed = old_text != text
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_lease(path.parent, f".{path.name}.lease"):
            _write_text_atomic(path, text)
    return {
        "kind": QUERY_PATTERN_PUBLISH_KIND,
        "schema_version": QUERY_PATTERN_ROUTE_SCHEMA_VERSION,
        "ok": True,
        "changed": changed,
        "navigation_only": True,
        "routes": normalized,
        "metrics": {
            "route_input_count": input_count,
            "route_write_count": len(normalized),
            "stale_generation_suppressed_count": stale_generation_suppressed_count,
            "invalid_route_suppressed_count": invalid_route_suppressed_count,
            "privacy_suppressed_count": privacy_suppressed_count,
            "unchanged_publish_count": 0 if changed else 1,
            "live_llm_call_count": 0,
        },
        "contract": {
            "sidecar_write_allowed": True,
            "query_pattern_routes_are_navigation_only": True,
            "query_pattern_routes_are_not_evidence": True,
            "source_reopen_required_before_claim": True,
        },
    }


def query_pattern_routes_report(
    routes: Iterable[Mapping[str, Any]],
    *,
    now_unix: float | None = None,
) -> dict[str, Any]:
    """Summarize query-pattern routes without exposing alias text."""

    now_value = time.time() if now_unix is None else now_unix
    rows: list[dict[str, Any]] = []
    metrics = {
        "route_count": 0,
        "active_route_count": 0,
        "suppressed_route_count": 0,
        "stale_suppressed_count": 0,
        "privacy_suppressed_count": 0,
        "missing_source_ref_count": 0,
        "low_confidence_suppressed_count": 0,
        "live_llm_call_count": 0,
    }
    for raw in routes:
        if not isinstance(raw, Mapping):
            continue
        route = normalize_query_pattern_route(raw)
        metrics["route_count"] += 1
        reason_codes: list[str] = []
        ttl_remaining = _ttl_remaining(route, now_unix=now_value)
        if route.get("state") in STALE_STATES or (ttl_remaining is not None and ttl_remaining <= 0):
            reason_codes.append("stale_or_expired")
            metrics["stale_suppressed_count"] += 1
        if _privacy_blocked(route):
            reason_codes.append("privacy_blocked")
            metrics["privacy_suppressed_count"] += 1
        if not route.get("source_refs"):
            reason_codes.append("missing_source_refs")
            metrics["missing_source_ref_count"] += 1
        if _float_bucket(route.get("confidence"), default=0.0) < MIN_SELECT_CONFIDENCE:
            reason_codes.append("low_confidence")
            metrics["low_confidence_suppressed_count"] += 1
        status = "suppressed" if reason_codes else "active"
        metrics["active_route_count" if status == "active" else "suppressed_route_count"] += 1
        rows.append(
            {
                "query_pattern_route_id": route["query_pattern_route_id"],
                "thread_key_hash": route["thread_key_hash"],
                "source_generation_digest": route["source_generation_digest"],
                "status": status,
                "reason_codes": reason_codes,
                "source_ref_count": len(route.get("source_refs") or []),
                "ttl_remaining_seconds": ttl_remaining,
                "confidence": route["confidence"],
                "navigation_only": True,
                "source_reopen_required_before_claim": True,
            }
        )
    return {
        "kind": QUERY_PATTERN_ROUTES_REPORT_KIND,
        "schema_version": QUERY_PATTERN_ROUTE_SCHEMA_VERSION,
        "ok": True,
        "navigation_only": True,
        "rows": rows,
        "metrics": metrics,
        "contract": {
            "query_aliases_omitted": True,
            "query_pattern_routes_are_navigation_only": True,
            "query_pattern_routes_are_not_evidence": True,
            "source_reopen_required_before_claim": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "query_alias_text_serialized": False,
        },
        "cannot_claim": [
            "query_pattern_route_is_source_truth",
            "query_pattern_alias_quality_is_proven",
            "foreground_latency_savings_are_proven",
        ],
    }


def _query_terms(prompt: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(prompt or "")).casefold().strip()
    terms = [text] if text else []
    for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", text, flags=re.UNICODE):
        terms.append(token)
    return unique_preserve(terms, limit=32)


def _matched(route: dict[str, Any], query_terms: list[str]) -> bool:
    aliases = [
        re.sub(r"[\s\-_]+", " ", str(alias or "").casefold()).strip()
        for alias in route.get("query_aliases") or []
    ]
    aliases = [alias for alias in aliases if alias]
    for term in query_terms:
        query = re.sub(r"[\s\-_]+", " ", term).strip()
        if not query:
            continue
        for alias in aliases:
            if alias in query or query in alias:
                return True
    return False


def _empty_packet(diagnostics: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": QUERY_PATTERN_PACKET_KIND,
        "schema_version": QUERY_PATTERN_ROUTE_SCHEMA_VERSION,
        "decision": "skip",
        "support_level": "suppressed" if diagnostics.get("cache_hit_count") else "silent_scent",
        "selected_count": 0,
        "candidate_refs": [],
        "matched_route_ids": [],
        "diagnostics": diagnostics,
        "source_boundary": {
            "query_pattern_routes_are_navigation_only": True,
            "query_pattern_routes_are_not_evidence": True,
            "source_reopen_required_before_claim": True,
            "packet_omits_raw_alias_text": True,
            "live_llm_not_required": True,
        },
    }


def _diagnostics() -> dict[str, Any]:
    return {
        "route_seen_count": 0,
        "cache_hit_count": 0,
        "cache_miss_count": 0,
        "selected_count": 0,
        "stale_suppressed_count": 0,
        "privacy_suppressed_count": 0,
        "low_confidence_suppressed_count": 0,
        "missing_source_ref_count": 0,
        "live_llm_call_count": 0,
        "output_boundary": "query_pattern_packet_no_raw_alias_text",
    }


def select_query_pattern_packet(
    prompt: str,
    routes: list[dict[str, Any]],
    *,
    now_unix: float | None = None,
    max_routes: int = MAX_SELECTED,
    min_confidence: float = MIN_SELECT_CONFIDENCE,
) -> dict[str, Any]:
    normalized_routes = [normalize_query_pattern_route(route) for route in routes]
    now_value = time.time() if now_unix is None else now_unix
    terms = _query_terms(prompt)
    diagnostics = _diagnostics()
    scored: list[tuple[float, dict[str, Any]]] = []

    for route in normalized_routes:
        diagnostics["route_seen_count"] += 1
        if not _matched(route, terms):
            continue
        diagnostics["cache_hit_count"] += 1
        ttl_remaining = _ttl_remaining(route, now_unix=now_value)
        if route.get("state") in STALE_STATES or (ttl_remaining is not None and ttl_remaining <= 0):
            diagnostics["stale_suppressed_count"] += 1
            continue
        if _privacy_blocked(route):
            diagnostics["privacy_suppressed_count"] += 1
            continue
        if not route.get("source_refs"):
            diagnostics["missing_source_ref_count"] += 1
            continue
        confidence = _float_bucket(route.get("confidence"), default=0.0)
        if confidence < min_confidence:
            diagnostics["low_confidence_suppressed_count"] += 1
            continue
        scored.append((confidence, route))

    if diagnostics["cache_hit_count"] == 0:
        diagnostics["cache_miss_count"] = 1
    if not scored:
        return _empty_packet(diagnostics)

    scored.sort(key=lambda item: (item[0], str(item[1].get("query_pattern_route_id"))), reverse=True)
    selected = [route for _, route in scored[: max(0, int(max_routes))]]
    refs: list[dict[str, Any]] = []
    for route in selected:
        refs.extend(route.get("source_refs") or [])
    diagnostics["selected_count"] = len(selected)
    return {
        "kind": QUERY_PATTERN_PACKET_KIND,
        "schema_version": QUERY_PATTERN_ROUTE_SCHEMA_VERSION,
        "decision": "scent",
        "support_level": "source_required",
        "selected_count": len(selected),
        "candidate_refs": safe_source_refs(refs)[:MAX_SOURCE_REFS],
        "matched_route_ids": [
            str(route.get("query_pattern_route_id") or "") for route in selected if route.get("query_pattern_route_id")
        ],
        "diagnostics": diagnostics,
        "source_boundary": {
            "query_pattern_routes_are_navigation_only": True,
            "query_pattern_routes_are_not_evidence": True,
            "source_reopen_required_before_claim": True,
            "packet_omits_raw_alias_text": True,
            "live_llm_not_required": True,
        },
    }
