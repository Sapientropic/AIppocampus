#!/usr/bin/env python3
"""Optional retrieval score fusion policy for source-joined ranking signals.

Default local recall is lexical-structural search, not dense vector retrieval.
Scores here are ranking hints only. The source join key remains the boundary:
optional vector or graph proximity can improve ordering after a candidate points
back to stable clean-source evidence, but a high score never becomes source
truth.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.recall.scoring_policy import (
    RAG_CHUNK_TEXT_POLICY,
    RETRIEVAL_TEXT_POLICY,
    SCORE_FUSION_POLICY,
    SOURCE_SIGNAL_POLICY,
)
from aippocampus_runtime.source.io_kernel import safe_float, source_ref_key

SCHEMA_VERSION = 1
FUSION_KIND = "aippocampus_retrieval_score_fusion"

CONTEXT_WEIGHTS: dict[str, dict[str, float]] = SCORE_FUSION_POLICY.context_weights_dict()


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return f"{prefix}_{sha1_text(raw)[:length]}"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def positive(value: Any) -> float:
    return max(0.0, safe_float(value))


def retrieval_text_score(
    signals: Mapping[str, Any],
    *,
    literal_hits: int = 0,
    expanded_hits: int = 0,
    anchor_hits: int = 0,
    phase_weight: float = 0.0,
) -> float:
    """Preserve the existing production text-retrieval score contract.

    `retrieval.py` historically combined FTS, RAG chunk, literal, expanded, and
    anchor signals inline. Keeping the formula here makes later vector/graph
    fusion explicit without silently changing exact/source-backed recall.
    """

    literal = max(0, int(literal_hits))
    expanded = max(0, int(expanded_hits))
    anchors = max(0, int(anchor_hits))
    score = 0.0
    score += positive(signals.get("fts"))
    score += positive(signals.get("rag_chunk"))
    score += literal * RETRIEVAL_TEXT_POLICY.literal_hit
    score += max(0, expanded - literal) * RETRIEVAL_TEXT_POLICY.expanded_hit
    score += anchors * RETRIEVAL_TEXT_POLICY.anchor_hit
    score += safe_float(phase_weight)
    return score


def rag_chunk_text_score(
    signals: Mapping[str, Any],
    *,
    literal_hits: int = 0,
    expanded_hits: int = 0,
    anchor_hits: int = 0,
) -> float:
    literal = max(0, int(literal_hits))
    expanded = max(0, int(expanded_hits))
    anchors = max(0, int(anchor_hits))
    return (
        positive(signals.get("chunk_fts"))
        + positive(signals.get("chunk_literal_scan"))
        + literal * RAG_CHUNK_TEXT_POLICY.literal_hit
        + max(0, expanded - literal) * RAG_CHUNK_TEXT_POLICY.expanded_hit
        + anchors * RAG_CHUNK_TEXT_POLICY.anchor_hit
    )


def source_ref_fingerprint(refs: Sequence[Mapping[str, Any]]) -> str:
    keys = [source_ref_key(ref) for ref in refs if source_ref_key(ref)[0]]
    if not keys:
        return ""
    return stable_id("src_refs", keys, length=16)


def source_join_key(candidate: Mapping[str, Any]) -> str:
    for key in ("stable_source_id", "source_id", "clean_source_id"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    thread_key = str(candidate.get("thread_key") or "").strip()
    for key in ("message_id", "turn_id"):
        value = str(candidate.get(key) or "").strip()
        if value and thread_key:
            return f"{thread_key}:{key}:{value}"
        if value:
            return value
    refs = [ref for ref in candidate.get("source_refs") or [] if isinstance(ref, Mapping)]
    fingerprint = source_ref_fingerprint(refs)
    if fingerprint:
        return fingerprint
    line = str(candidate.get("line") or candidate.get("source_line") or "").strip()
    if line and candidate.get("thread_key"):
        return stable_id("source_line", candidate.get("thread_key"), line, length=18)
    return ""


def text_signal(candidate: Mapping[str, Any]) -> float:
    if candidate.get("text_score") is not None:
        return positive(candidate.get("text_score"))
    raw_signals = candidate.get("signals")
    signals: Mapping[str, Any] = raw_signals if isinstance(raw_signals, Mapping) else {}
    literal = safe_int(candidate.get("literal_hits") or signals.get("literal_hits") or 0)
    expanded = safe_int(candidate.get("expanded_hits") or signals.get("expanded_hits") or literal)
    anchors = safe_int(candidate.get("anchor_hits") or signals.get("anchor_hits") or 0)
    phase = safe_float(candidate.get("phase_weight") or signals.get("phase_weight") or 0.0)
    return retrieval_text_score(
        signals,
        literal_hits=literal,
        expanded_hits=expanded,
        anchor_hits=anchors,
        phase_weight=phase,
    )


def vector_signal(candidate: Mapping[str, Any]) -> float:
    if candidate.get("vector_score") is not None:
        return positive(candidate.get("vector_score"))
    if candidate.get("score_kind") == "vector":
        return positive(candidate.get("score"))
    return 0.0


def graph_signal(candidate: Mapping[str, Any]) -> float:
    if candidate.get("graph_score") is not None:
        return positive(candidate.get("graph_score"))
    if candidate.get("score_kind") in {"graph", "concept_graph"}:
        return positive(candidate.get("score"))
    return 0.0


def source_richness_signal(candidate: Mapping[str, Any]) -> float:
    """Return post-gate provenance richness, not source eligibility.

    `blend()` rejects candidates without a stable source join before this
    function runs. A join key alone is enough to remain eligible, but it is weak
    provenance and should not earn a soft ranking boost by itself.
    """

    refs = [ref for ref in candidate.get("source_refs") or [] if isinstance(ref, Mapping)]
    if refs:
        return min(
            SOURCE_SIGNAL_POLICY.maximum,
            SOURCE_SIGNAL_POLICY.ref_base + len(refs) * SOURCE_SIGNAL_POLICY.per_ref,
        )
    return SOURCE_SIGNAL_POLICY.join_key_only if source_join_key(candidate) else 0.0


def source_signal(candidate: Mapping[str, Any]) -> float:
    """Compatibility alias for the post-gate provenance richness signal."""

    return source_richness_signal(candidate)


def provenance_richness_class(candidate: Mapping[str, Any]) -> str:
    return "source_refs" if candidate.get("source_refs") else "weak_join_only"


def normalize(values: Mapping[str, float], key: str) -> float:
    value = positive(values.get(key))
    maxima = positive(values.get(f"max_{key}"))
    if maxima <= 0.0:
        return 0.0
    return min(1.0, value / maxima)


def context_weights(context: str) -> dict[str, float]:
    return SCORE_FUSION_POLICY.weights_for(context)


def merge_candidate(into: dict[str, Any], candidate: Mapping[str, Any]) -> None:
    into["text_score"] = max(float(into.get("text_score") or 0.0), text_signal(candidate))
    into["vector_score"] = max(float(into.get("vector_score") or 0.0), vector_signal(candidate))
    into["graph_score"] = max(float(into.get("graph_score") or 0.0), graph_signal(candidate))
    into["source_score"] = max(
        float(into.get("source_score") or 0.0), source_richness_signal(candidate)
    )
    refs = into.setdefault("source_refs", [])
    seen = {source_ref_key(ref) for ref in refs if isinstance(ref, Mapping)}
    for ref in candidate.get("source_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        key = source_ref_key(ref)
        if not key[0] or key in seen:
            continue
        refs.append(dict(ref))
        seen.add(key)
    channels = into.setdefault("channels", set())
    for channel in candidate.get("channels") or []:
        if channel:
            channels.add(str(channel))
    if candidate.get("score_kind"):
        channels.add(str(candidate["score_kind"]))
    if text_signal(candidate):
        channels.add("text")
    if vector_signal(candidate):
        channels.add("vector")
    if graph_signal(candidate):
        channels.add("graph")
    if candidate.get("payload") is not None and into.get("payload") is None:
        into["payload"] = candidate.get("payload")


def score_merged_candidate(
    candidate: Mapping[str, Any],
    *,
    weights: Mapping[str, float],
    maxima: Mapping[str, float],
    context: str,
) -> dict[str, Any]:
    values = {
        "text": positive(candidate.get("text_score")),
        "vector": positive(candidate.get("vector_score")),
        "graph": positive(candidate.get("graph_score")),
        "source": positive(candidate.get("source_score")),
        "max_text": positive(maxima.get("text")),
        "max_vector": positive(maxima.get("vector")),
        "max_graph": positive(maxima.get("graph")),
        "max_source": positive(maxima.get("source")),
    }
    normalized = {
        "text": normalize(values, "text"),
        "vector": normalize(values, "vector"),
        "graph": normalize(values, "graph"),
        "source": normalize(values, "source"),
    }
    components = {
        key: round(normalized[key] * float(weights.get(key, 0.0)), 6)
        for key in ("text", "vector", "graph", "source")
    }
    score = sum(components.values())
    if (
        context == "exact_quote"
        and normalized["text"] >= SCORE_FUSION_POLICY.exact_text_guard_threshold
    ):
        score += SCORE_FUSION_POLICY.exact_text_guard_bonus
        components["exact_text_guard"] = SCORE_FUSION_POLICY.exact_text_guard_bonus
    return {
        "source_id": candidate["source_id"],
        "score": round(score, 6),
        "score_components": components,
        "normalized_signals": {key: round(value, 6) for key, value in normalized.items()},
        "raw_signals": {
            "text": round(values["text"], 6),
            "vector": round(values["vector"], 6),
            "graph": round(values["graph"], 6),
            "source": round(values["source"], 6),
        },
        "channels": sorted(str(channel) for channel in candidate.get("channels") or []),
        "source_refs": list(candidate.get("source_refs") or []),
        "source_boundary": {
            "source_join_gate": "passed",
            "stable_source_join_required": True,
            "source_refs_present": bool(candidate.get("source_refs")),
            "provenance_richness": provenance_richness_class(candidate),
            "source_richness_score_is_ranking_hint": True,
            "ranking_scores_are_not_truth": True,
            "source_reopen_required_for_claims": True,
        },
        "payload": candidate.get("payload"),
    }


def blend(
    candidates: Sequence[Mapping[str, Any]],
    *,
    context: str = "normal_recall",
    vectors_available: bool = True,
    graph_available: bool = True,
    limit: int = 10,
) -> dict[str, Any]:
    weights = context_weights(context)
    if not vectors_available:
        weights["text"] += weights.pop("vector", 0.0)
        weights["vector"] = 0.0
    if not graph_available:
        weights["text"] += weights.pop("graph", 0.0)
        weights["graph"] = 0.0

    merged: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        source_id = source_join_key(candidate)
        if not source_id:
            skipped.append(
                {
                    "gate": "source_join_gate",
                    "reason": "missing_stable_source_join",
                    "channels": candidate.get("channels") or [candidate.get("score_kind") or ""],
                    "source_richness_scored": False,
                }
            )
            continue
        row = merged.setdefault(
            source_id,
            {
                "source_id": source_id,
                "text_score": 0.0,
                "vector_score": 0.0,
                "graph_score": 0.0,
                "source_score": 0.0,
                "source_refs": [],
                "channels": set(),
                "payload": None,
            },
        )
        merge_candidate(row, candidate)

    maxima = {
        "text": max([row["text_score"] for row in merged.values()] + [0.0]),
        "vector": max([row["vector_score"] for row in merged.values()] + [0.0]),
        "graph": max([row["graph_score"] for row in merged.values()] + [0.0]),
        "source": max([row["source_score"] for row in merged.values()] + [0.0]),
    }
    ranked = [
        score_merged_candidate(row, weights=weights, maxima=maxima, context=context)
        for row in merged.values()
    ]
    ranked.sort(
        key=lambda row: (
            -float(row["score"]),
            -float(row["normalized_signals"].get("text") or 0.0),
            str(row["source_id"]),
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": FUSION_KIND,
        "created_at": now_utc(),
        "context": SCORE_FUSION_POLICY.canonical_context(context),
        "weights": weights,
        "ranked": ranked[: max(0, int(limit))],
        "candidate_count": len(candidates),
        "ranked_count": min(len(ranked), max(0, int(limit))),
        "skipped": skipped,
        "policy_boundary": {
            "scores_are_ranking_hints_only": True,
            "source_refs_or_stable_source_ids_required": True,
            "source_join_gate_required": True,
            "source_richness_is_post_gate_ranking_hint": True,
            "vectors_optional": True,
            "graph_optional": True,
        },
    }


def build_public_score_fusion_calibration_report() -> dict[str, Any]:
    """Return the public #309 score-fusion calibration report."""

    from aippocampus_runtime.recall.score_fusion_calibration import (
        build_public_score_fusion_calibration_report as build_report,
    )

    return build_report(
        blend_fn=blend,
        safe_float_fn=safe_float,
        schema_version=SCHEMA_VERSION,
        now_utc_fn=now_utc,
    )
