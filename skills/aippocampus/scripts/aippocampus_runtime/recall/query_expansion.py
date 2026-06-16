"""Source-backed query expansion planning for FTS-first recall.

Expansion terms are navigation material only. They can widen lexical candidate
construction before top-k truncation, but they do not become factual evidence;
foreground claims still need source reopen or bounded source evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.query_policy import normalize_term, unique_preserve
from aippocampus_runtime.recall.semantic_bridge_map import (
    SEMANTIC_BRIDGE_SOURCE,
    semantic_bridge_expansion_terms,
)

SOURCE_FACTUAL_ALIAS_SOURCE = "source_factual_alias"
QUERY_EXPANSION_BOUNDARY = "navigation_only_source_reopen_required"


def _sha1_json(value: Any, *, length: int = 16) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8", errors="replace")).hexdigest()[:length]


def _safe_terms(values: Iterable[Any], *, limit: int = 32) -> list[str]:
    terms: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        term = normalize_term(value)
        if not term or len(term) > 96:
            continue
        # Keep raw private paths and secret-shaped tokens out of recall
        # diagnostics and query plans. The source alias materializer already
        # filters these, but the planner is a second guard for hand-built rows.
        if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", term):
            continue
        if re.search(r"\b(?:sk|pk|api[_-]?key|token|secret)[-_:=][A-Za-z0-9_-]{6,}", term, re.I):
            continue
        terms.append(term)
    return unique_preserve(terms, limit=limit)


def _overlaps_query(query_terms: list[str], aliases: list[str], route_terms: list[str]) -> bool:
    query_low = [term.casefold() for term in query_terms if term]
    for query in query_low:
        for term in aliases + route_terms:
            low = term.casefold()
            if not low:
                continue
            if query == low or query in low or low in query:
                return True
    return False


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    public_shape = {
        "kind": row.get("kind"),
        "row_id": row.get("row_id"),
        "source_generation_digest": row.get("source_generation_digest"),
        "source_ref_count": len(row.get("source_refs") or []),
        "query_alias_count": len(row.get("query_aliases") or []),
        "route_term_count": len(row.get("route_terms") or []),
    }
    return "sha1:" + _sha1_json(public_shape)


def load_source_factual_alias_rows(path: str | Path | None) -> list[dict[str, Any]]:
    """Load reviewed source-side alias rows without making them evidence."""

    if not path:
        return []
    alias_path = Path(path)
    if not alias_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with alias_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except OSError:
        return []
    return rows


def plan_query_expansion(
    query_terms: Iterable[str],
    *,
    source_alias_rows: Iterable[Mapping[str, Any]] | None = None,
    semantic_bridge_rows: Iterable[Mapping[str, Any]] | None = None,
    semantic_effectiveness_rows: Iterable[Mapping[str, Any]] | None = None,
    seed_terms: Iterable[str] | None = None,
    durable_aliases: Mapping[str, Iterable[str]] | None = None,
    limit: int = 64,
) -> dict[str, Any]:
    """Return expanded lexical terms and privacy-safe diagnostics.

    `seed_terms` lets existing anchor/static expansion remain the base plan.
    Source-backed aliases then add route terms before FTS top-k truncation.
    Diagnostics intentionally contain counts and fingerprints, not raw route
    terms, because alias text is a routing hint rather than source truth.
    """

    original = _safe_terms(query_terms, limit=limit)
    expanded = _safe_terms(seed_terms if seed_terms is not None else original, limit=limit)
    expansion_sources: dict[str, int] = {}
    fingerprints: list[str] = []

    for key, values in (durable_aliases or {}).items():
        alias_key = normalize_term(str(key or ""))
        if not alias_key:
            continue
        if any(alias_key.casefold() in term.casefold() or term.casefold() in alias_key.casefold() for term in original):
            safe_values = _safe_terms(values, limit=12)
            if safe_values:
                expanded.extend(safe_values)
                expansion_sources["durable_alias"] = expansion_sources.get("durable_alias", 0) + 1

    for row in source_alias_rows or []:
        aliases = _safe_terms(row.get("query_aliases") or [], limit=24)
        route_terms = _safe_terms(row.get("route_terms") or [], limit=32)
        if not aliases and not route_terms:
            continue
        if not _overlaps_query(original, aliases, route_terms):
            continue
        expanded.extend(route_terms)
        expansion_sources[SOURCE_FACTUAL_ALIAS_SOURCE] = (
            expansion_sources.get(SOURCE_FACTUAL_ALIAS_SOURCE, 0) + 1
        )
        fingerprints.append(_row_fingerprint(row))

    bridge_terms, bridge_diagnostics = semantic_bridge_expansion_terms(
        original,
        semantic_bridge_rows or [],
        semantic_effectiveness_rows=semantic_effectiveness_rows,
        limit=limit,
    )
    if bridge_terms:
        expanded.extend(bridge_terms)
        expansion_sources[SEMANTIC_BRIDGE_SOURCE] = bridge_diagnostics["semantic_bridge_count"]
        fingerprints.extend(bridge_diagnostics["semantic_bridge_fingerprints"])

    expanded = unique_preserve(expanded, limit=limit)
    added_count = max(0, len(expanded) - len(unique_preserve(original, limit=limit)))
    return {
        "original_terms": original,
        "expanded_terms": expanded,
        "diagnostics": {
            "policy": "source_backed_query_expansion_v1",
            "boundary": QUERY_EXPANSION_BOUNDARY,
            "original_term_count": len(original),
            "expanded_term_count": len(expanded),
            "added_term_count": added_count,
            "expansion_sources": expansion_sources,
            "source_fingerprints": unique_preserve(fingerprints, limit=12),
            "semantic_bridge": bridge_diagnostics,
            "semantic_effectiveness": bridge_diagnostics.get("semantic_effectiveness") or {},
            "provider_calls": 0,
        },
    }
