"""Pointer projection for continuity-domain pathlets.

Pathlets are ordered source-ref routes. They are useful for fresh-thread
orientation, but they must never become source truth or user-profile claims.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.authority import (
    ACTION_IGNORE_OR_BLOCKED,
    ACTION_REOPENABLE_ROUTE,
)
from aippocampus_runtime.recall.query_policy import split_query_terms

CONTINUITY_PATHLET_POINTER_KIND = "continuity_pathlet_pointer"
INACTIVE_PATHLET_STATUSES = {"blocked", "stale", "superseded", "retired"}


def _safe_text(value: Any, chars: int = 220) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _safe_list(values: Any, *, limit: int = 12, chars: int = 80) -> list[str]:
    if not isinstance(values, (list, tuple)):
        values = [values] if values not in (None, "") else []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _safe_text(value, chars).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _terms(text: str) -> set[str]:
    out: set[str] = set()
    for raw in split_query_terms([str(text or "")]):
        token = raw.strip(".,:;!?()[]{}<>\"'`").casefold()
        if len(token) < 2:
            continue
        out.add(token)
        for part in token.replace("#", " #").split():
            clean = part.strip(".,:;!?()[]{}<>\"'`").casefold()
            if len(clean) >= 2:
                out.add(clean)
    return out


def _overlap_score(
    prompt_terms: set[str],
    prompt_text: str,
    route_terms: set[str],
    route_text: str,
) -> int:
    score = len(prompt_terms & route_terms)
    prompt_low = prompt_text.casefold()
    route_low = route_text.casefold()
    for term in route_terms:
        if term and term in prompt_low:
            score += 1
    for term in prompt_terms:
        if term and term in route_low:
            score += 1
    return score


def continuity_pathlet_pointer(
    pathlet: Mapping[str, Any],
    *,
    why_it_may_matter_now: str = "",
) -> dict[str, Any]:
    status = str(pathlet.get("status") or "active")
    blocked = status in INACTIVE_PATHLET_STATUSES
    action = str(pathlet.get("action_grammar") or ACTION_REOPENABLE_ROUTE)
    if blocked:
        action = ACTION_IGNORE_OR_BLOCKED
    refs = safe_source_refs(pathlet.get("ordered_source_refs") or pathlet.get("source_refs"))[:8]
    pointer = {
        "card_kind": CONTINUITY_PATHLET_POINTER_KIND,
        "pathlet_id": _safe_text(pathlet.get("pathlet_id"), 120),
        "label": _safe_text(pathlet.get("title") or pathlet.get("pathlet_id"), 120),
        "theme": _safe_text(pathlet.get("title") or pathlet.get("pathlet_id"), 120),
        "status": status,
        "support_level": "source_required" if action == ACTION_REOPENABLE_ROUTE else "suppressed",
        "action_grammar": action,
        "ordered_source_refs": refs,
        "source_refs": refs,
        "scope_labels": _safe_list(pathlet.get("scope_labels"), limit=8),
        "domain_ids": _safe_list(pathlet.get("domain_ids"), limit=8),
        "why_it_may_matter_now": _safe_text(
            why_it_may_matter_now or "The current prompt overlaps this ordered source route.",
            180,
        ),
        "suggested_use": "Use as an ordered route to reopen source; do not treat the pathlet as a fact.",
        "reopen_plan": {
            "status": "ready" if action == ACTION_REOPENABLE_ROUTE and refs else "blocked",
            "recommended_tool": "recall_deepen" if refs else "search_memory",
            "arguments": {"source_refs": refs} if refs else {"pathlet_id": pathlet.get("pathlet_id")},
            "manual_query_invention_expected": False,
        },
        "source_boundary": {
            "pathlet_is_navigation_only": True,
            "pathlet_is_not_source_fact": True,
            "source_reopen_required_before_claim": True,
            "clean_source_is_authority": True,
            "raw_source_text_serialized": False,
        },
        "cannot_claim": [
            "pathlet_is_fact",
            "pathlet_summary_is_source_truth",
            "exact_claim_without_source_reopen",
        ],
    }
    return redact_sensitive_values(redact_private_paths(pointer))


def match_continuity_pathlet_pointers(
    prompt: str,
    snapshot: Mapping[str, Any] | None,
    *,
    limit: int = 3,
    include_blocked: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(snapshot, Mapping):
        return []
    prompt_text = str(prompt or "")
    prompt_terms = _terms(prompt_text)
    if not prompt_terms:
        return []
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for pathlet in snapshot.get("pathlets") or []:
        if not isinstance(pathlet, Mapping):
            continue
        status = str(pathlet.get("status") or "active")
        action = str(pathlet.get("action_grammar") or ACTION_REOPENABLE_ROUTE)
        inactive = status in INACTIVE_PATHLET_STATUSES or action == ACTION_IGNORE_OR_BLOCKED
        if inactive and not include_blocked:
            continue
        text = " ".join(
            [
                str(pathlet.get("pathlet_id") or ""),
                str(pathlet.get("title") or ""),
                " ".join(str(item) for item in pathlet.get("scope_labels") or []),
                " ".join(str(item) for item in pathlet.get("domain_ids") or []),
            ]
        )
        pathlet_terms = _terms(text)
        overlap = _overlap_score(prompt_terms, prompt_text, pathlet_terms, text)
        if overlap <= 0:
            continue
        status_bonus = -3 if inactive else 0
        scored.append((overlap + status_bonus, str(pathlet.get("pathlet_id") or ""), dict(pathlet)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        continuity_pathlet_pointer(
            pathlet,
            why_it_may_matter_now="The current prompt overlaps this source-ordered pathlet.",
        )
        for score, _, pathlet in scored
        if score > 0
    ][: max(0, limit)]
