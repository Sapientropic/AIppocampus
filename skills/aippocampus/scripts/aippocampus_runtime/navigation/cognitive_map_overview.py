"""Registry-derived far-view overview for cognitive-map cold start."""

from __future__ import annotations

import hashlib
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.navigation.associations import (
    normalize_term,
    source_text_is_noise,
    term_is_noise,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import unique_preserve

MAX_OVERVIEW_TERMS = 28

GENERIC_OVERVIEW_TERMS = {
    "memory",
    "project",
    "source",
    "candidate",
    "thread",
    "route",
    "landmark",
    "region",
    "记忆",
    "项目",
    "来源",
    "候选",
    "线程",
    "路线",
    "地标",
    "区域",
}


def registry_overview_source_boundary() -> dict[str, bool]:
    return {
        "registry_derived_navigation_only": True,
        "not_source_backed_route": True,
        "registry_metadata_is_not_evidence": True,
        "source_reopen_required_for_claims": True,
    }


def compact_overview_terms(values: Any, *, limit: int = 12, chars: int = 90) -> list[str]:
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, list):
        source = values
    else:
        source = []
    out: list[str] = []
    for value in source:
        term = normalize_term(str(value or ""))
        if not term:
            continue
        if len(term) > chars:
            term = compact_text(term, chars)
        low = term.casefold()
        if low in GENERIC_OVERVIEW_TERMS or term_is_noise(term) or source_text_is_noise(term):
            continue
        out.append(term)
    return unique_preserve(out, limit=limit)


def overview_id(label: str) -> str:
    digest = hashlib.sha1(normalize_term(label).casefold().encode("utf-8")).hexdigest()[:18]
    return f"cmfo_{digest}"


def registry_overview_from_episodes(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    clusters_by_label: dict[str, list[dict[str, Any]]] = {}
    latest_first_episodes = sorted(
        episodes,
        key=lambda row: str(row.get("updated_at") or ""),
        reverse=True,
    )
    for episode in latest_first_episodes:
        label = compact_text(
            str(episode.get("project_label") or episode.get("title") or "Registry episodes"),
            120,
        )
        clusters_by_label.setdefault(label or "Registry episodes", []).append(episode)

    clusters: list[dict[str, Any]] = []
    for label, rows in clusters_by_label.items():
        ordered = rows
        thread_keys = unique_preserve(
            [str(row.get("thread_key") or "") for row in ordered if row.get("thread_key")],
            limit=12,
        )
        episode_titles = compact_overview_terms(
            [str(row.get("title") or "") for row in ordered], limit=8, chars=120
        )
        anchor_titles = compact_overview_terms(
            [str(value) for row in ordered for value in (row.get("anchor_titles") or [])],
            limit=10,
            chars=120,
        )
        keywords = compact_overview_terms(
            [str(value) for row in ordered for value in (row.get("keywords") or [])],
            limit=14,
        )
        navigation_terms = compact_overview_terms(
            [label] + episode_titles + anchor_titles + keywords,
            limit=MAX_OVERVIEW_TERMS,
        )
        if not thread_keys or not navigation_terms:
            continue
        updated_values = [
            str(row.get("updated_at") or "") for row in ordered if row.get("updated_at")
        ]
        cluster = {
            "cluster_id": overview_id(label),
            "kind": "cognitive_map_registry_overview_cluster",
            "label": label,
            "thread_keys": thread_keys,
            "episode_count": len(thread_keys),
            "updated_at": updated_values[0] if updated_values else None,
            "episode_titles": episode_titles,
            "anchor_titles": anchor_titles,
            "keywords": keywords,
            "navigation_terms": navigation_terms,
            "source": "registry_metadata",
            "source_boundary": registry_overview_source_boundary(),
        }
        clusters.append(
            {
                key: value
                for key, value in cluster.items()
                if value is not None and value != ""
            }
        )

    clusters.sort(
        key=lambda item: (
            str(item.get("updated_at") or ""),
            int(item.get("episode_count") or 0),
            str(item.get("label") or ""),
        ),
        reverse=True,
    )
    return {
        "kind": "cognitive_map_registry_overview",
        "overview_kind": "cold_start_far_view",
        "source": "registry_metadata",
        "cluster_count": len(clusters),
        "clusters": clusters,
        "source_boundary": registry_overview_source_boundary(),
    }


def cue_matches(prompt_low: str, prompt_terms: list[str], cue: str) -> bool:
    cue_low = str(cue or "").casefold().strip()
    if not cue_low:
        return False
    if cue_low in prompt_low:
        return True
    cue_terms = [term.casefold() for term in split_query_terms([cue]) if len(term.strip()) >= 3]
    return any(term and term in prompt_terms for term in cue_terms)


def cue_score(cue: str) -> float:
    length = len(str(cue or "").strip())
    return min(4.0, max(0.8, length / 8.0))


def match_registry_overview(
    prompt_low: str,
    prompt_terms: list[str],
    cognitive_map: dict[str, Any],
    *,
    project_label: str | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    overview = cognitive_map.get("registry_overview") or {}
    if not isinstance(overview, dict):
        return []
    matches: list[dict[str, Any]] = []
    for cluster in overview.get("clusters") or []:
        if not isinstance(cluster, dict):
            continue
        cues = unique_preserve(
            compact_overview_terms(cluster.get("navigation_terms"), limit=MAX_OVERVIEW_TERMS)
            + compact_overview_terms(cluster.get("episode_titles"), limit=8)
            + compact_overview_terms(cluster.get("anchor_titles"), limit=8)
            + compact_overview_terms(cluster.get("keywords"), limit=12),
            limit=MAX_OVERVIEW_TERMS,
        )
        matched = [cue for cue in cues if cue_matches(prompt_low, prompt_terms, cue)]
        if not matched:
            continue
        project_boost = 0.0
        label = str(cluster.get("label") or "")
        if project_label and label.casefold() == project_label.casefold():
            project_boost = 0.8
        score = min(8.0, sum(cue_score(cue) * 0.5 for cue in matched) + project_boost)
        matches.append(
            {
                "kind": "cognitive_map_registry_overview",
                "provenance_class": "cognitive_map_registry_overview",
                "route_id": cluster.get("cluster_id"),
                "route_kind": "registry_overview",
                "title": label,
                "landmark_labels": cluster.get("anchor_titles") or [],
                "region_labels": [label] if label else [],
                "route_cues": cues,
                "matched_cues": unique_preserve(matched, limit=8),
                "query_terms": unique_preserve(
                    [str(value) for value in cluster.get("navigation_terms") or []], limit=16
                ),
                "thread_keys": unique_preserve(
                    [str(value) for value in cluster.get("thread_keys") or []], limit=8
                ),
                "confidence": 0.1,
                "score": round(score, 3),
                "source": "registry_metadata",
                "source_refs": [],
                "source_boundary": dict(
                    cluster.get("source_boundary") or registry_overview_source_boundary()
                ),
            }
        )
    matches.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return matches[:limit]
