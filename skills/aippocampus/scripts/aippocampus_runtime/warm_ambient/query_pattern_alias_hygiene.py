"""Alias quality gates for query-pattern routes."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

GENERIC_QUERY_PATTERN_ALIASES = {
    "aippocampus",
    "agent",
    "agents",
    "append",
    "clean",
    "core",
    "health",
    "hook",
    "hooks",
    "local",
    "maintenance",
    "memory",
    "plugin",
    "plugins",
    "recall",
    "rollout",
    "runtime",
    "source",
    "sources",
    "system",
    "thread",
    "threads",
    "test",
    "tests",
}


def alias_quality_key(value: Any) -> str:
    return re.sub(r"[\s\-_]+", " ", str(value or "").casefold()).strip()


def alias_fanout(routes: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for route in routes:
        if not isinstance(route, Mapping):
            continue
        for alias in route.get("query_aliases") or []:
            key = alias_quality_key(alias)
            if key:
                counts[key] = counts.get(key, 0) + 1
    return counts


def _high_fanout_threshold(route_count: int) -> int:
    return max(8, int(max(1, route_count) * 0.12))


def _alias_is_generic(value: str) -> bool:
    key = alias_quality_key(value)
    if not key:
        return True
    if key in GENERIC_QUERY_PATTERN_ALIASES:
        return True
    if re.fullmatch(r"(not|but|has|full|the|and|for|with|this|that|source|agent)", key):
        return True
    return key.startswith("--")


def route_match_quality(
    route: Mapping[str, Any],
    query_terms: list[str],
    *,
    alias_fanout_counts: Mapping[str, int],
    route_count: int,
    registry_alias_source: str,
    unspecified_alias_source: str,
) -> dict[str, int | bool]:
    aliases = [alias_quality_key(alias) for alias in route.get("query_aliases") or []]
    aliases = [alias for alias in aliases if alias]
    alias_source = str(route.get("alias_source") or unspecified_alias_source)
    high_fanout_threshold = _high_fanout_threshold(route_count)
    matched = 0
    distinctive = 0
    generic = 0
    high_fanout = 0
    for term in query_terms:
        query = alias_quality_key(term)
        if not query:
            continue
        for alias in aliases:
            if not (alias in query or query in alias):
                continue
            matched += 1
            fanout = int(alias_fanout_counts.get(alias) or 0)
            is_high_fanout = (
                alias_source == registry_alias_source and fanout >= high_fanout_threshold
            )
            if is_high_fanout:
                high_fanout += 1
            if _alias_is_generic(alias):
                generic += 1
                continue
            if is_high_fanout:
                continue
            distinctive += 1
    return {
        "matched": bool(matched),
        "matched_alias_count": matched,
        "distinctive_alias_count": distinctive,
        "generic_alias_count": generic,
        "high_fanout_alias_count": high_fanout,
    }


__all__ = ["alias_fanout", "alias_quality_key", "route_match_quality"]
