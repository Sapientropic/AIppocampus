"""Duplicate/noise helpers for foreground registry search projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.core import stable_text_fingerprint
from aippocampus_runtime.source.query_match_gate import normalize_anchor

PROCESS_NOISE_PREFIXES = (
    ("<subagent_notification>", "process_notification"),
    ("<tool", "tool_process"),
)


def process_noise_reason(text: str) -> str:
    snippet = str(text or "").lstrip().casefold()
    for prefix, reason in PROCESS_NOISE_PREFIXES:
        if snippet.startswith(prefix):
            return reason
    return ""


def match_haystack(match: Mapping[str, Any]) -> str:
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    return " ".join(
        str(value or "")
        for value in (
            match.get("snippet"),
            thread_map.get("thread_key"),
            thread_map.get("title"),
            thread_map.get("workspace_name"),
            match.get("source"),
        )
    )


def compact_registry_match(match: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in match.items()
        if key not in {"score", "query_match_profile"}
    }


def _duplicate_fingerprint(match: Mapping[str, Any]) -> str:
    snippet = normalize_anchor(str(match.get("snippet") or ""))
    if len(snippet) < 32:
        return ""
    return stable_text_fingerprint(
        f"{match.get('role') or ''}\n{match.get('phase') or ''}\n{snippet}",
        namespace="registry-search-duplicate-snippet",
        prefix="rsdup",
        length=18,
    )


def _duplicate_source_ref(match: Mapping[str, Any]) -> dict[str, Any]:
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    return {
        key: value
        for key, value in {
            "thread_key": thread_map.get("thread_key"),
            "title": thread_map.get("title"),
            "message_id": match.get("message_id"),
            "line": match.get("line"),
            "role": match.get("role"),
            "phase": match.get("phase"),
        }.items()
        if value not in (None, "", [], {})
    }


def collapse_duplicate_matches(
    matches: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    collapsed: list[dict[str, Any]] = []
    by_fingerprint: dict[str, dict[str, Any]] = {}
    duplicate_cluster_count = 0
    duplicate_hit_count = 0
    for match in matches:
        fingerprint = _duplicate_fingerprint(match)
        if fingerprint and fingerprint in by_fingerprint:
            representative = by_fingerprint[fingerprint]
            refs = representative.setdefault("duplicate_source_refs", [])
            if isinstance(refs, list):
                refs.append(_duplicate_source_ref(match))
            representative["duplicate_count"] = int(representative.get("duplicate_count") or 0) + 1
            representative["duplicate_thread_count"] = len(
                {
                    str(ref.get("thread_key") or "")
                    for ref in refs
                    if isinstance(ref, Mapping) and ref.get("thread_key")
                }
            )
            duplicate_hit_count += 1
            continue
        if len(collapsed) >= limit:
            continue
        current = dict(match)
        if fingerprint:
            current["duplicate_fingerprint"] = fingerprint
            current["duplicate_count"] = 0
            current["duplicate_source_refs"] = [_duplicate_source_ref(match)]
            current["duplicate_thread_count"] = 1
            by_fingerprint[fingerprint] = current
        collapsed.append(current)
    for item in collapsed:
        if int(item.get("duplicate_count") or 0) > 0:
            duplicate_cluster_count += 1
            item["source_count"] = int(item.get("duplicate_count") or 0) + 1
    return collapsed[:limit], {
        "duplicate_cluster_count": duplicate_cluster_count,
        "duplicate_hit_count": duplicate_hit_count,
    }
