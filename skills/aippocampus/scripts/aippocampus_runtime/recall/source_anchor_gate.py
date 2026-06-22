"""Cue-anchor gate for default recall route actions.

This is a foreground-action guard, not a truth scorer. It only decides whether
the top route is strong enough to be the *default* `agent deepen` action. A
low-hit route may still remain available as secondary navigation, but it should
not masquerade as the useful next step when the opened source does not carry the
distinctive cue anchors.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp.recall_navigation import RecallNavigationError, recall_deepen_packet

_ANCHOR_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_-]{3,}")
_NORMALIZE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_LOW_SIGNAL_ANCHORS = {
    "agent",
    "agents",
    "clean",
    "continuity",
    "current",
    "deep",
    "issue",
    "issues",
    "memory",
    "recall",
    "route",
    "source",
    "source-backed",
    "sourcebacked",
}
_SOURCE_CHAIN_ROLE_ALLOWLIST = {
    "original_mechanical_ascension_source",
    "original_external_hippocampus_design",
    "origin_reflection",
    "canonical_doc",
}


def distinctive_query_anchors(query: str, *, limit: int = 8) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for match in _ANCHOR_RE.finditer(str(query or "")):
        raw = match.group(0)
        key = _NORMALIZE_RE.sub("", raw.casefold())
        if not key or key in _LOW_SIGNAL_ANCHORS or key in seen:
            continue
        seen.add(key)
        anchors.append(raw)
        if len(anchors) >= limit:
            break
    return anchors


def _source_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload.get("source_window") or {}, ensure_ascii=False, sort_keys=True)


def _anchor_hits(source_text: str, anchors: Sequence[str]) -> list[str]:
    haystack = source_text.casefold()
    hits: list[str] = []
    for anchor in anchors:
        if anchor and anchor.casefold() in haystack:
            hits.append(anchor)
    return hits


def _top_mapping(values: Any) -> Mapping[str, Any]:
    if not isinstance(values, list | tuple) or not values:
        return {}
    first = values[0]
    return first if isinstance(first, Mapping) else {}


def top_route_source_anchor_gate(
    *,
    query: str,
    routes: Sequence[Mapping[str, Any]],
    deepen_requests: Sequence[Mapping[str, Any]],
    clean_source_dir: Path,
    registry_dir: Path | None,
) -> dict[str, Any]:
    """Return a public-safe diagnostic for the top route's source-anchor fit."""

    route = _top_mapping(list(routes))
    request = _top_mapping(list(deepen_requests))
    if not route or not request:
        return {"status": "skipped", "reason": "no_reopenable_top_route"}

    source_chain_role = str(route.get("source_chain_role") or "").strip()
    if source_chain_role in _SOURCE_CHAIN_ROLE_ALLOWLIST:
        return {
            "status": "passed",
            "reason": "source_chain_role_allowlist",
            "source_chain_role": source_chain_role,
            "opened_anchor_hits": None,
            "target_source_matched": True,
        }

    anchors = distinctive_query_anchors(query)
    if len(anchors) < 2:
        return {
            "status": "skipped",
            "reason": "not_enough_distinctive_query_anchors",
            "anchor_count": len(anchors),
        }

    handle = request.get("handle") or request.get("callable_handle")
    if not handle:
        return {"status": "skipped", "reason": "missing_deepen_handle"}

    try:
        opened = recall_deepen_packet(
            handle=handle,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
        )
    except RecallNavigationError as exc:
        return {
            "status": "blocked",
            "reason": "top_route_source_not_reopenable",
            "error_code": exc.code,
            "anchor_count": len(anchors),
            "opened_anchor_hits": 0,
            "target_source_matched": False,
        }

    hits = _anchor_hits(_source_text(opened), anchors)
    required_hits = 2 if len(anchors) >= 3 else 1
    status = "passed" if len(hits) >= required_hits else "blocked"
    return {
        "status": status,
        "reason": "opened_source_anchor_coverage",
        "anchor_count": len(anchors),
        "opened_anchor_hits": len(hits),
        "required_anchor_hits": required_hits,
        "target_source_matched": status == "passed",
    }


def apply_top_route_source_anchor_gate(
    *,
    query: str,
    routes: Sequence[Mapping[str, Any]],
    deepen_requests: Sequence[Mapping[str, Any]],
    memory_packets: list[dict[str, Any]],
    clean_source_dir: Path,
    registry_dir: Path | None,
) -> dict[str, Any]:
    gate = top_route_source_anchor_gate(
        query=query,
        routes=routes,
        deepen_requests=deepen_requests,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
    )
    if gate.get("status") == "blocked" and memory_packets:
        flags = list(memory_packets[0].get("risk_flags") or [])
        if "low_source_anchor_coverage" not in flags:
            flags.append("low_source_anchor_coverage")
        memory_packets[0]["risk_flags"] = flags
        memory_packets[0]["route_choice_posture"] = "low_confidence_source_anchor_gap"
        memory_packets[0]["source_anchor_gate"] = {
            key: value
            for key, value in gate.items()
            if key not in {"source_ref"} and value not in (None, "", [], {})
        }
    return gate


__all__ = [
    "apply_top_route_source_anchor_gate",
    "distinctive_query_anchors",
    "top_route_source_anchor_gate",
]
