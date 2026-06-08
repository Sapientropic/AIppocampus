#!/usr/bin/env python3
"""Explicit old/superseded-route blockers for foreground recall."""

from __future__ import annotations

import re

OLD_ROUTE_NEGATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(do not|don't|must not|should not).{0,36}(cite|quote|reopen|retrieve|reuse|use).{0,48}(old|prior|previous|stale|superseded).{0,48}(source|memory|route|note|thread|context|decision)",
        r"(old|prior|previous|stale|superseded).{0,64}(source|memory|route|note|thread|context|decision).{0,48}(do not|don't|must not|should not).{0,48}(cite|quote|reopen|retrieve|reuse|use|treat)",
        r"(不要|别|先别|不能|不要再).{0,36}(重开|打开|引用|复用|使用|沿用|当成|视为).{0,48}(旧|老|过期|废弃|已废弃|被取代|已取代).{0,48}(源|来源|记忆|路线|结论|线程|上下文)",
        r"(旧|老|过期|废弃|已废弃|被取代|已取代).{0,48}(源|来源|记忆|路线|结论|线程|上下文).{0,48}(不要|别|先别|不能|不要再).{0,48}(重开|打开|引用|复用|使用|沿用|当成|视为)",
    ]
]

FRESH_TASK_REDIRECT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(fresh|unrelated|new|current task only|current task|directly|from scratch)\b",
        r"\b(write|draft|create|make).{0,36}(fresh|unrelated|new)\b",
        r"(新的|全新|无关|当前任务|直接|从头|不要拉旧记忆|别拉旧记忆)",
    ]
]

LATER_SOURCE_REQUEST_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(can you|could you|please)\s+(cite|quote|retrieve|reopen|find)\b",
        r"\b(source-backed|source evidence|clean source|citation|quote|evidence)\b",
        r"(找回|找一下|查一下|引用|原话|原文|证据)",
    ]
]

SUPERSEDED_CURRENTNESS_BLOCK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(old|prior|previous|stale|superseded).{0,64}(source|memory|route|note|thread|context|decision).{0,64}(superseded|obsolete|outdated|retired).{0,64}(do not|don't|must not|should not).{0,48}(treat|use|present|surface).{0,32}(current|evidence|fact|source evidence)",
        r"(do not|don't|must not|should not).{0,48}(treat|use|present|surface).{0,48}(superseded|obsolete|outdated|retired).{0,48}(source|memory|route|note|thread|context|decision).{0,48}(current|evidence|fact|source evidence)",
        r"(已废弃|被取代|已取代|不再成立).{0,48}(不要|别|先别|不能|不要再).{0,48}(当成|视为|作为|用作).{0,32}(当前|现在|证据|事实|来源)",
    ]
]


def _unique_preserve(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = re.sub(r"\s+", " ", str(item)).strip()
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def memory_route_block_intent(prompt: str) -> list[str]:
    """Return explicit user constraints that forbid surfacing an old route.

    This is narrower than ordinary "no source" wording. It blocks old-route
    reuse only when the prompt either redirects to a fresh/unrelated task or
    explicitly says the old route is superseded and must not be treated as
    current evidence. A user can still ask for scent-only continuity, and can
    still forbid old route A while requesting source-backed route B.
    """

    text = str(prompt or "").strip()
    if not text:
        return []
    matches = []
    for pattern in SUPERSEDED_CURRENTNESS_BLOCK_PATTERNS:
        found = pattern.search(text)
        if found:
            matches.append(found.group(0))
    if matches:
        return _unique_preserve(matches, limit=4)
    old_route_negation = [
        found.group(0)
        for pattern in OLD_ROUTE_NEGATION_PATTERNS
        if (found := pattern.search(text))
    ]
    if old_route_negation and any(pattern.search(text) for pattern in FRESH_TASK_REDIRECT_PATTERNS):
        return _unique_preserve(old_route_negation, limit=4)
    return _unique_preserve(matches, limit=4)


def old_route_negation_has_later_source_request(prompt: str) -> bool:
    """Return whether a local old-route ban is followed by another source ask."""

    text = str(prompt or "").strip()
    if not text:
        return False
    old_route_negation = None
    for pattern in OLD_ROUTE_NEGATION_PATTERNS:
        old_route_negation = pattern.search(text)
        if old_route_negation:
            break
    if not old_route_negation:
        return False
    if any(pattern.search(text) for pattern in FRESH_TASK_REDIRECT_PATTERNS):
        return False
    if any(pattern.search(text) for pattern in SUPERSEDED_CURRENTNESS_BLOCK_PATTERNS):
        return False
    tail = text[old_route_negation.end():]
    return bool(tail and any(pattern.search(tail) for pattern in LATER_SOURCE_REQUEST_PATTERNS))
