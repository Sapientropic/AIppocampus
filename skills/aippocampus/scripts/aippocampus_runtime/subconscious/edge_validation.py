#!/usr/bin/env python3
"""Shared validation policy for source-backed subconscious concept edges."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.navigation.concept_graph import concept_is_noise

ALLOWED_EDGE_TYPES = {
    "alias",
    "same_decision_space",
    "project_topic",
    "decision_about",
    "depends_on",
    "contrasts_with",
    "supersedes",
    "related",
}

EDGE_MIN_CONFIDENCE = 0.45
EDGE_WHY_MAX_CHARS = 220


@dataclass(frozen=True)
class SourceBackedEdgePolicy:
    min_confidence: float = EDGE_MIN_CONFIDENCE
    max_source_refs: int = 3
    max_why_chars: int = EDGE_WHY_MAX_CHARS


WORKER_EDGE_POLICY = SourceBackedEdgePolicy(max_source_refs=3)
AGENT_EDGE_POLICY = SourceBackedEdgePolicy(max_source_refs=4)

SourceRefProjector = Callable[[str, Mapping[str, Any]], dict[str, Any]]


def clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def normalize_edge_type(value: Any) -> str:
    edge_type = str(value or "related").strip()
    return edge_type if edge_type in ALLOWED_EDGE_TYPES else "related"


def source_ref_id(ref_item: Any) -> str:
    if isinstance(ref_item, str):
        return ref_item.strip()
    if isinstance(ref_item, Mapping):
        return str(
            ref_item.get("ref") or ref_item.get("turn_ref") or ref_item.get("obs_ref") or ""
        ).strip()
    return ""


def source_refs_for_edge(
    edge: Mapping[str, Any],
    source_bank: Mapping[str, Mapping[str, Any]],
    *,
    project_source_ref: SourceRefProjector,
    max_source_refs: int,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref_item in edge.get("source_refs") or []:
        ref_id = source_ref_id(ref_item)
        if not ref_id:
            continue
        source = source_bank.get(ref_id)
        if not source:
            continue
        refs.append(project_source_ref(ref_id, source))
    return refs[: max(0, int(max_source_refs))]


def validate_source_backed_edges(
    parsed: Mapping[str, Any],
    source_bank: Mapping[str, Mapping[str, Any]],
    *,
    policy: SourceBackedEdgePolicy,
    project_source_ref: SourceRefProjector,
) -> list[dict[str, Any]]:
    """Validate model-proposed edges without giving staging rows truth authority.

    Worker and agent shells may cite different source-ref shapes, but they must
    share the hard gates here: source refs must resolve, generic/self edges are
    rejected, unknown edge types become `related`, and low-confidence edges
    remain outside the staging queue. Do not loosen these gates in one shell
    without making the policy difference explicit and tested.
    """

    out: list[dict[str, Any]] = []
    for edge in parsed.get("edges") or []:
        if not isinstance(edge, Mapping):
            continue
        src = str(edge.get("src") or "").strip()
        dst = str(edge.get("dst") or "").strip()
        confidence = clamp_confidence(edge.get("confidence"))
        if not src or not dst or src.casefold() == dst.casefold():
            continue
        if concept_is_noise(src) or concept_is_noise(dst):
            continue
        refs = source_refs_for_edge(
            edge,
            source_bank,
            project_source_ref=project_source_ref,
            max_source_refs=policy.max_source_refs,
        )
        if not refs or confidence < policy.min_confidence:
            continue
        out.append(
            {
                "src": src,
                "dst": dst,
                "edge_type": normalize_edge_type(edge.get("edge_type")),
                "confidence": round(confidence, 4),
                "why": compact_text(str(edge.get("why") or ""), policy.max_why_chars),
                "source_refs": refs,
            }
        )
    return out
