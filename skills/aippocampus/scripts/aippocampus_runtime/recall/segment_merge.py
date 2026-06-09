"""Segment-result merge helpers with stable source-key dedupe."""

from __future__ import annotations

from aippocampus_runtime.recall.score_fusion import source_join_key
from aippocampus_runtime.recall.scoring_policy import SEGMENT_MERGE_POLICY, SegmentMergePolicy


def segment_sort_key(
    result: dict,
    policy: SegmentMergePolicy = SEGMENT_MERGE_POLICY,
) -> tuple[float, int, int]:
    final_bonus = (
        policy.final_answer_bonus
        if result.get("phase") == "final_answer" or result.get("is_final")
        else 0.0
    )
    commentary_penalty = (
        policy.commentary_penalty if result.get("phase") == "commentary" else 0.0
    )
    return (
        -(float(result.get("score") or 0.0) + final_bonus + commentary_penalty),
        int(result.get("line") or 10**12),
        int(result.get("segment_ordinal") or 10**6),
    )


def segment_source_join_key(result: dict) -> str:
    """Return stable source identity when a segment hit exposes one.

    Segment-local SQLite ids collide and overlapped shards can surface the same
    clean-source row under different segment ids. Prefer the shared
    score-fusion source join semantics; use scalar `source_ref` only as an
    already-projected stable ref. Hits without a source key keep the legacy
    segment-local fallback path.
    """

    key = source_join_key(result)
    if key:
        return f"source_join:{key}"
    source_ref = str(result.get("source_ref") or "").strip()
    if source_ref:
        return f"source_ref:{source_ref}"
    return ""


def _dedupe_pool_by_source_key(pool: list[dict]) -> tuple[list[dict], int]:
    deduped: list[dict] = []
    seen: set[str] = set()
    dedupe_count = 0
    for item in pool:
        key = segment_source_join_key(item)
        if key and key in seen:
            dedupe_count += 1
            continue
        deduped.append(item)
        if key:
            seen.add(key)
    return deduped, dedupe_count


def merge_topk_with_diagnostics(
    results: list[dict],
    limit: int,
    policy: SegmentMergePolicy = SEGMENT_MERGE_POLICY,
) -> tuple[list[dict], dict[str, int]]:
    """Merge hits and report compact source-key dedupe diagnostics."""

    if not results:
        return (
            [],
            {
                "input_candidate_count": 0,
                "candidate_count_after_source_key_dedupe": 0,
                "source_key_dedupe_count": 0,
            },
        )
    pool = sorted(results, key=lambda item: segment_sort_key(item, policy))
    pool, source_key_dedupe_count = _dedupe_pool_by_source_key(pool)
    diagnostics = {
        "input_candidate_count": len(results),
        "candidate_count_after_source_key_dedupe": len(pool),
        "source_key_dedupe_count": source_key_dedupe_count,
    }
    if not pool:
        return [], diagnostics

    selected: list[dict] = []
    seen: set[tuple[str, int, int]] = set()

    def key(item: dict) -> tuple[str, int, int]:
        return (str(item.get("segment_id")), int(item.get("id") or 0), int(item.get("line") or 0))

    def add(item: dict | None) -> None:
        if not item:
            return
        item_key = key(item)
        if item_key in seen:
            return
        selected.append(item)
        seen.add(item_key)

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
            key=lambda item: (
                (
                    policy.final_answer_bonus
                    if item.get("phase") == "final_answer" or item.get("is_final")
                    else 0.0
                )
                + float(item.get("score") or 0)
            ),
            default=None,
        )
    )

    while len(selected) < min(limit, len(pool)):
        selected_segments = {str(item.get("segment_id")) for item in selected}
        selected_lines = [int(item.get("line") or 0) for item in selected]
        best = None
        best_value = None
        for item in pool:
            if key(item) in seen:
                continue
            value = float(item.get("score") or 0.0)
            if str(item.get("segment_id")) in selected_segments:
                value -= policy.same_segment_penalty
            if item.get("phase") == "final_answer" or item.get("is_final"):
                value += policy.final_answer_bonus
            if item.get("phase") == "commentary":
                value += policy.commentary_penalty
            line = int(item.get("line") or 0)
            if any(
                abs(line - other) < policy.nearby_line_window
                for other in selected_lines
            ):
                value -= policy.nearby_line_penalty
            if (item.get("signals") or {}).get("literal_hits", 0) > 0 and item.get(
                "role"
            ) == "user":
                value += policy.user_literal_bonus
            if best_value is None or value > best_value:
                best = item
                best_value = value
        add(best)
        if best is None:
            break
    return selected[:limit], diagnostics


def merge_topk(
    results: list[dict],
    limit: int,
    policy: SegmentMergePolicy = SEGMENT_MERGE_POLICY,
) -> list[dict]:
    """Merge per-shard hits without letting one dense recap shard dominate.

    Segment-local SQLite row ids collide, so this intentionally avoids
    retrieval.diversify_results, whose duplicate guard assumes one monolithic
    index. The merge keeps high-score hits first, then applies light penalties
    for same-segment and near-line repeats so early source evidence and later
    summaries can both surface. The optional policy argument is for deterministic
    calibration/sensitivity tests; the CLI path uses the default named policy.
    """

    selected, _ = merge_topk_with_diagnostics(results, limit, policy=policy)
    return selected
