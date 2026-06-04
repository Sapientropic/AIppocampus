#!/usr/bin/env python3
"""Source-diverse ordering for recall results."""

from __future__ import annotations

from aippocampus_runtime.recall import scoring_policy


def _result_bucket(result: dict, anchor_matches: list[dict]) -> str:
    snippet = str(result.get("snippet") or "").casefold()
    for anchor in anchor_matches:
        title = str(anchor.get("title") or "")
        if title and title.casefold() in snippet:
            return "anchor:" + title
        for keyword in anchor.get("keywords") or []:
            key = str(keyword)
            if key and key.casefold() in snippet:
                return "anchor:" + title
    line = int(result.get("line") or 0)
    return f"{result.get('role') or 'unknown'}:{line // 200}"


def diversify_results(
    results: list[dict],
    limit: int,
    anchor_matches: list[dict] | None = None,
    *,
    mode: str = "balanced",
) -> list[dict]:
    """Return a source-diverse ordering for recall snippets.

    Long threads often contain later recaps that score higher than the original
    turn. Diversity keeps the best hit, then makes room for early/source hits
    and different buckets before filling the rest by score. This should stay a
    ranking policy, not a filter that hides evidence.
    """

    if mode == "none" or len(results) <= 2:
        return results[:limit]
    anchor_matches = anchor_matches or []
    pool = list(results)
    selected: list[dict] = []
    selected_ids: set[int] = set()

    def add(item: dict | None) -> None:
        if not item:
            return
        item_id = int(item.get("id") or item.get("line") or len(selected_ids) + 1)
        if item_id in selected_ids:
            return
        selected.append(item)
        selected_ids.add(item_id)

    add(pool[0])
    literal_hits = [item for item in pool if (item.get("signals") or {}).get("literal_hits", 0) > 0]
    add(
        min(
            (item for item in literal_hits if item.get("role") == "user"),
            key=lambda item: item.get("line") or 10**12,
            default=None,
        )
    )
    add(min(literal_hits, key=lambda item: item.get("line") or 10**12, default=None))
    add(
        max(
            (item for item in pool if item.get("role") == "assistant"),
            key=lambda item: item.get("score") or 0,
            default=None,
        )
    )

    while len(selected) < min(limit, len(pool)):
        best = None
        best_value = None
        policy = scoring_policy.RETRIEVAL_DIVERSITY_POLICY
        selected_buckets = {_result_bucket(item, anchor_matches) for item in selected}
        selected_lines = [int(item.get("line") or 0) for item in selected]
        for item in pool:
            item_id = int(item.get("id") or item.get("line") or 0)
            if item_id in selected_ids:
                continue
            value = float(item.get("score") or 0)
            bucket = _result_bucket(item, anchor_matches)
            if bucket in selected_buckets:
                value -= policy.bucket_repeat_penalty
            line = int(item.get("line") or 0)
            if any(abs(line - other) < policy.nearby_line_window for other in selected_lines):
                value -= policy.nearby_line_penalty
            if mode == "early" and (item.get("signals") or {}).get("literal_hits", 0) > 0:
                value += max(0.0, policy.early_literal_boost - line / policy.early_line_divisor)
            if best_value is None or value > best_value:
                best = item
                best_value = value
        add(best)
        if best is None:
            break
    return selected[:limit]
