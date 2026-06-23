#!/usr/bin/env python3
"""Deterministic Phase 3 theme emergence over source-backed question links.

This runner turns recurring `question_link` rows into conservative
`theme_candidate` findings. It does not discover themes with a model and it does
not create a new staging file: every output remains append-only in
`subconscious_jobs.jsonl` and every claim is backed by the source refs already
attached to question links and frontier markers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.navigation.concept_graph import (
    default_concept_graph_path,
    expand_concepts,
)
from aippocampus_runtime.question.source_refs import source_ref_key
from aippocampus_runtime.registry.api import registry_paths, unique_preserve
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows
from aippocampus_runtime.subconscious.jobs_config import default_jobs_output_path
from aippocampus_runtime.subconscious.theme_emergence_inputs import (
    FrontierMarker,
    QuestionLink,
    concept_is_specific,
    concept_key,
    concept_terms,
    frontier_from_row,
    normalize_concept,
    parse_timestamp,
    question_link_from_row,
    row_finding_kind,
)

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-theme-emergence-v1"
FINDING_ROW_KIND = "aippocampus_subconscious_job_finding"
THEME_CANDIDATE_KIND = "theme_candidate"
DEFAULT_MIN_RECURRING_LINKS = 3
THEME_RESONANCE_BOUNDARY = "Deterministic source-backed navigation is not user resonance proof."
THEME_RESONANCE_CANNOT_CLAIM = (
    "theme_label_resonates_with_user",
    "user_visible_recall_lift",
    "answer_quality_improvement",
    "llm_theme_naming_supported",
)

def stable_digest(*parts: str, prefix: str, length: int = 18) -> str:
    raw = "\n".join(parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:length]}"


def existing_theme_ids(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        if row.get("kind") != FINDING_ROW_KIND:
            continue
        if row_finding_kind(row) != THEME_CANDIDATE_KIND:
            continue
        theme_id = str(row.get("theme_cluster_id") or "").strip()
        if theme_id:
            ids.add(theme_id)
    return ids


def load_theme_inputs(path: Path) -> tuple[list[QuestionLink], list[FrontierMarker], list[dict[str, Any]]]:
    rows = load_jsonl_dict_rows(path).rows
    links: list[QuestionLink] = []
    frontiers: list[FrontierMarker] = []
    for row in rows:
        link = question_link_from_row(row)
        if link:
            links.append(link)
            continue
        frontier = frontier_from_row(row)
        if frontier:
            frontiers.append(frontier)
    return links, frontiers, rows


def cluster_question_links(
    links: list[QuestionLink],
    *,
    concept_graph_path: Path | None,
    min_links: int = DEFAULT_MIN_RECURRING_LINKS,
) -> list[tuple[list[QuestionLink], list[str]]]:
    if concept_graph_path is None or not concept_graph_path.exists():
        return []
    enriched_links = [
        enrich_link_theme_terms(link, concept_graph_path=concept_graph_path) for link in links
    ]
    by_concept: dict[str, list[QuestionLink]] = {}
    display: dict[str, str] = {}
    for link in enriched_links:
        for concept in link.theme_terms:
            if not concept_is_specific(concept):
                continue
            key = concept_key(concept)
            display.setdefault(key, normalize_concept(concept))
            by_concept.setdefault(key, []).append(link)
    by_link_set: dict[tuple[str, ...], set[str]] = {}
    for key, concept_links in by_concept.items():
        unique_links = sorted(
            {link.link_id: link for link in concept_links}.values(),
            key=lambda item: item.link_id,
        )
        if len(unique_links) < min_links:
            continue
        link_set_key = tuple(link.link_id for link in unique_links)
        by_link_set.setdefault(link_set_key, set()).add(display.get(key, key))
    clusters: list[tuple[list[QuestionLink], list[str]]] = []
    by_id = {link.link_id: link for link in enriched_links}
    for link_ids, shared in by_link_set.items():
        if len(shared) < 2:
            continue
        clusters.append(([by_id[link_id] for link_id in link_ids], sorted(shared, key=str.casefold)))
    clusters.sort(key=lambda item: (-len(item[0]), item[1][0].casefold()))
    return clusters


def enrich_link_theme_terms(link: QuestionLink, *, concept_graph_path: Path) -> QuestionLink:
    seed_terms = unique_preserve(
        [concept for concept in link.concepts if concept_is_specific(concept)]
        + [link.linked_question_short],
        limit=16,
    )
    expansions = expand_concepts(
        concept_graph_path,
        seed_terms,
        depth=1,
        max_terms=16,
        min_score=0.10,
    )
    graph_terms = [
        normalize_concept(str(item.get("term") or ""))
        for item in expansions
        if concept_is_specific(str(item.get("term") or ""))
    ]
    return replace(link, theme_terms=tuple(unique_preserve(seed_terms + graph_terms, limit=24)))


def merge_refs(links: Iterable[QuestionLink], frontiers: Iterable[FrontierMarker]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in list(links) + list(frontiers):
        for ref in item.source_refs:
            key = source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
    return refs[:18]


def cluster_time_bounds(links: list[QuestionLink]) -> tuple[str, str, int]:
    parsed = []
    for link in links:
        for value in (link.first_seen, link.last_seen):
            timestamp = parse_timestamp(value)
            if timestamp:
                parsed.append(timestamp)
    if not parsed:
        return "", "", 0
    first = min(parsed)
    last = max(parsed)
    days = max(0, math.ceil((last - first).total_seconds() / 86400))
    return first.isoformat().replace("+00:00", "Z"), last.isoformat().replace("+00:00", "Z"), days


def frontiers_for_theme(
    links: list[QuestionLink],
    frontiers: list[FrontierMarker],
    shared_concepts: list[str],
) -> list[FrontierMarker]:
    terms = set()
    for concept in shared_concepts:
        terms |= concept_terms(concept)
    for link in links:
        terms |= concept_terms(link.linked_question_short, link.title, " ".join(link.concepts))
    out: list[FrontierMarker] = []
    for frontier in frontiers:
        frontier_terms = concept_terms(
            frontier.linked_question_short,
            frontier.boundary_reason,
            " ".join(frontier.concepts),
        )
        if terms and frontier_terms and terms & frontier_terms:
            out.append(frontier)
    return out[:8]


def theme_fingerprint(theme_id: str, link_ids: Iterable[str]) -> str:
    return stable_digest(theme_id, "|".join(sorted(link_ids)), prefix="sf", length=20)


def theme_cluster_id(links: list[QuestionLink], shared_concepts: list[str]) -> str:
    return stable_digest(
        "|".join(sorted(link.link_id for link in links)),
        "|".join(sorted(concept.casefold() for concept in shared_concepts)),
        prefix="th",
        length=18,
    )


def theme_resonance_calibration_boundary() -> dict[str, Any]:
    # Keep this explicit until a user-review artifact exists. Source-derived
    # labels are useful navigation handles, but silently treating them as user
    # resonance evidence would overstate the Phase 3 contract.
    return {
        "status": "absent",
        "user_review_evidence": False,
        "claim_boundary": THEME_RESONANCE_BOUNDARY,
        "cannot_claim": list(THEME_RESONANCE_CANNOT_CLAIM),
    }


def theme_resonance_calibration_report(themes: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(
        str(theme.get("theme_resonance_calibration", {}).get("status") or "unknown")
        for theme in themes
    )
    return {
        **theme_resonance_calibration_boundary(),
        "theme_count": len(themes),
        "status_counts": dict(sorted(status_counts.items())),
    }


def build_theme_candidate(
    links: list[QuestionLink],
    shared_concepts: list[str],
    frontiers: list[FrontierMarker],
    *,
    min_links: int = DEFAULT_MIN_RECURRING_LINKS,
) -> dict[str, Any]:
    theme_short = compact_text(shared_concepts[0], 90)
    theme_id = theme_cluster_id(links, shared_concepts)
    source_refs = merge_refs(links, frontiers)
    first_seen, last_seen, time_span_days = cluster_time_bounds(links)
    thread_span = len({ref.get("thread_key") for ref in source_refs if ref.get("thread_key")})
    average_confidence = sum(link.confidence for link in links) / max(1, len(links))
    confidence = round(
        min(0.96, average_confidence * 0.75 + min(1.0, len(links) / 5) * 0.12 + min(1.0, thread_span / 5) * 0.08),
        4,
    )
    boundary_counts = Counter(frontier.frontier_type for frontier in frontiers)
    link_ids = [link.link_id for link in links]
    return {
        "job": "theme_emergence",
        "kind": THEME_CANDIDATE_KIND,
        "finding_kind": THEME_CANDIDATE_KIND,
        "title": compact_text(f"Recurring question theme: {theme_short}", 140),
        "summary": compact_text(
            f"{len(links)} recurring question links share source-backed concept evidence around {theme_short}.",
            480,
        ),
        "confidence": confidence,
        "source_refs": source_refs,
        "concepts": unique_preserve(shared_concepts + [concept for link in links for concept in link.concepts], limit=16),
        "recommendation": "Use as quiet navigation scent only; open clean source before making factual claims.",
        "theme_cluster_id": theme_id,
        "theme_label": compact_text(f"Recurring question theme: {theme_short}", 140),
        "theme_short": theme_short,
        "cluster_method": "deterministic_shared_concept_neighbors_v1",
        "shared_concepts": shared_concepts[:12],
        "question_link_count": len(links),
        "linked_question_count": sum(link.question_count for link in links),
        "thread_span": thread_span,
        "time_span_days": time_span_days,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "source_question_link_ids": [link.finding_id for link in links],
        "question_link_refs": [
            {
                "question_cluster_id": link.link_id,
                "source_finding_id": link.finding_id,
                "linked_question_short": link.linked_question_short,
                "question_count": link.question_count,
                "source_refs": list(link.source_refs)[:4],
            }
            for link in links
        ],
        "frontier_refs": [
            {
                "source_finding_id": frontier.finding_id,
                "frontier_type": frontier.frontier_type,
                "linked_question_short": frontier.linked_question_short,
                "boundary_reason": frontier.boundary_reason,
                "source_refs": list(frontier.source_refs)[:4],
            }
            for frontier in frontiers
        ],
        "boundary_map": {
            "frontier_count": len(frontiers),
            "frontier_type_counts": dict(sorted(boundary_counts.items())),
            "contract": "Boundary aggregation is source-backed navigation, not proof that the theme is unresolved.",
        },
        "match_evidence": {
            "method": "deterministic_shared_concept_graph_neighbors_v1",
            "min_recurring_question_link_count": min_links,
            "shared_concept_count": len(shared_concepts),
            "concept_graph_required": True,
            "source_question_link_count": len(links),
        },
        "naming_evidence": {
            "method": "deterministic_source_backed_label_v1",
            "llm_naming": False,
            "label_source": "shared_concepts",
            "hallucination_guard": "Theme names are selected from source-derived shared concepts only.",
        },
        "theme_resonance_calibration": theme_resonance_calibration_boundary(),
        "fingerprint": theme_fingerprint(theme_id, link_ids),
        "quality": {
            "bucket": "usable" if confidence < 0.82 else "strong",
            "promotion_readiness": confidence,
            "signals": {
                "source_ref_count": len(source_refs),
                "source_thread_count": thread_span,
                "question_link_count": len(links),
                "frontier_count": len(frontiers),
            },
        },
    }


def build_theme_candidates(
    links: list[QuestionLink],
    frontiers: list[FrontierMarker],
    *,
    concept_graph_path: Path | None,
    min_links: int = DEFAULT_MIN_RECURRING_LINKS,
) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = []
    for cluster_links, shared_concepts in cluster_question_links(
        links,
        concept_graph_path=concept_graph_path,
        min_links=min_links,
    ):
        cluster_frontiers = frontiers_for_theme(cluster_links, frontiers, shared_concepts)
        themes.append(
            build_theme_candidate(
                cluster_links,
                shared_concepts,
                cluster_frontiers,
                min_links=min_links,
            )
        )
    themes.sort(key=lambda item: (str(item.get("theme_short") or ""), str(item.get("theme_cluster_id") or "")))
    return themes


def theme_materialization_blockers(
    links: list[QuestionLink],
    themes: list[dict[str, Any]],
    *,
    concept_graph_path: Path | None,
    min_links: int,
) -> list[dict[str, Any]]:
    if themes:
        return []
    graph_available = bool(concept_graph_path and concept_graph_path.exists())
    if not graph_available:
        return [
            {
                "code": "concept_graph_missing",
                "question_link_count": len(links),
                "min_links": min_links,
                "concept_graph": str(concept_graph_path) if concept_graph_path else None,
            }
        ]
    if len(links) < min_links:
        return [
            {
                "code": "not_enough_question_links",
                "question_link_count": len(links),
                "min_links": min_links,
            }
        ]
    return [
        {
            "code": "no_shared_concept_cluster",
            "question_link_count": len(links),
            "min_links": min_links,
            "reason": "Recurring links exist, but no cluster met the shared source-derived concept/neighbor requirement.",
        }
    ]


def append_theme_candidates(
    path: Path,
    themes: Iterable[dict[str, Any]],
    *,
    batch_id: str,
    source: str = "deterministic_theme_emergence",
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for theme in themes:
            payload = dict(theme)
            payload.pop("kind", None)
            payload.pop("finding_kind", None)
            event = {
                "schema_version": SCHEMA_VERSION,
                "kind": FINDING_ROW_KIND,
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": "deterministic",
                "batch_id": batch_id,
                "status": "staging",
                "source": source,
                "model_route": {"provider": "deterministic"},
                "usage": {},
                "finding_kind": THEME_CANDIDATE_KIND,
                **payload,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            count += 1
    return count


def run_theme_emergence(
    *,
    jobs_path: Path,
    concept_graph_path: Path | None = None,
    output_path: Path | None = None,
    min_links: int = DEFAULT_MIN_RECURRING_LINKS,
    no_write: bool = False,
) -> dict[str, Any]:
    output = output_path or jobs_path
    links, frontiers, rows = load_theme_inputs(jobs_path)
    themes = build_theme_candidates(
        links,
        frontiers,
        concept_graph_path=concept_graph_path,
        min_links=min_links,
    )
    blockers = theme_materialization_blockers(
        links,
        themes,
        concept_graph_path=concept_graph_path,
        min_links=min_links,
    )
    existing_ids = existing_theme_ids(
        rows if output == jobs_path else load_jsonl_dict_rows(output).rows
    )
    fresh_themes = [
        theme for theme in themes if str(theme.get("theme_cluster_id") or "") not in existing_ids
    ]
    duplicate_count = len(themes) - len(fresh_themes)
    batch_id = f"theme-emergence-{hashlib.sha1(now_utc().encode('utf-8')).hexdigest()[:12]}"
    wrote_count = 0
    if not no_write and fresh_themes:
        wrote_count = append_theme_candidates(output, fresh_themes, batch_id=batch_id)
    return {
        "ok": True,
        "job": "theme_emergence",
        "jobs_input": str(jobs_path),
        "output": str(output),
        "question_link_count": len(links),
        "frontier_count": len(frontiers),
        "concept_graph": str(concept_graph_path) if concept_graph_path else None,
        "concept_graph_available": bool(concept_graph_path and concept_graph_path.exists()),
        "theme_count": len(themes),
        "fresh_theme_count": len(fresh_themes),
        "duplicate_theme_count": duplicate_count,
        "materialization_blockers": blockers,
        "wrote_count": wrote_count,
        "wrote": bool(wrote_count),
        "no_write": no_write,
        "min_links": min_links,
        "themes": themes,
        "batch_id": batch_id,
        "naming_contract": "deterministic shared-concept labels only; no LLM theme discovery or naming",
        "theme_resonance_calibration": theme_resonance_calibration_report(themes),
    }


def default_registry_path(registry: str | None, registry_dir: str | None) -> Path | None:
    if registry:
        return Path(registry).resolve()
    if registry_dir:
        registry_path, _ = registry_paths(Path(registry_dir).resolve())
        return registry_path
    registry_path, _ = registry_paths(None)
    return registry_path


def default_jobs_path(registry: str | None, registry_dir: str | None) -> Path:
    registry_path = default_registry_path(registry, registry_dir)
    if registry_path:
        return default_jobs_output_path(registry_path=registry_path)
    registry_path, _ = registry_paths(None)
    return default_jobs_output_path(registry_path=registry_path)


def default_concept_graph(registry: str | None, registry_dir: str | None) -> Path:
    registry_path = default_registry_path(registry, registry_dir)
    if registry_path:
        return default_concept_graph_path(registry_path=registry_path)
    registry_path, _ = registry_paths(None)
    return default_concept_graph_path(registry_path=registry_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs-input")
    parser.add_argument("--concept-graph")
    parser.add_argument("--output")
    parser.add_argument("--min-links", type=int, default=DEFAULT_MIN_RECURRING_LINKS)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    jobs_path = (
        Path(args.jobs_input).resolve()
        if args.jobs_input
        else default_jobs_path(args.registry, args.registry_dir)
    )
    output_path = Path(args.output).resolve() if args.output else jobs_path
    concept_graph = (
        Path(args.concept_graph).resolve()
        if args.concept_graph
        else default_concept_graph(args.registry, args.registry_dir)
    )
    result = run_theme_emergence(
        jobs_path=jobs_path,
        concept_graph_path=concept_graph,
        output_path=output_path,
        min_links=max(2, int(args.min_links or DEFAULT_MIN_RECURRING_LINKS)),
        no_write=args.no_write,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"theme candidates: {result['fresh_theme_count']} fresh / {result['theme_count']} total")
        if result["wrote"]:
            print(f"wrote: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
