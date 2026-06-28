"""Explicit-scale query packets for cognitive-map sidecars."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol

from aippocampus_runtime.core import compact_text, dict_or_empty
from aippocampus_runtime.navigation.associations import (
    normalize_term,
    source_text_is_noise,
    term_is_noise,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import unique_preserve

MAP_QUERY_SCALES = {"far", "mid", "near"}
GENERIC_MAP_QUERY_TERMS = {
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


class NearMatcher(Protocol):
    def __call__(
        self,
        prompt: str,
        cognitive_map: dict[str, Any],
        *,
        project_label: str | None = None,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        ...


def _safe_rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _count_dict(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        label = compact_text(str(value or "").strip(), 120)
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _compact_terms(values: Any, *, limit: int = 12, chars: int = 90) -> list[str]:
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
        if low in GENERIC_MAP_QUERY_TERMS or term_is_noise(term) or source_text_is_noise(term):
            continue
        out.append(term)
    return unique_preserve(out, limit=limit)


def _month_bucket(value: Any) -> str:
    text = str(value or "")
    return text[:7] if len(text) >= 7 else "undated"


def _source_boundary() -> dict[str, bool]:
    return {
        "navigation_only": True,
        "source_reopen_required_for_claims": True,
        "exact_wording_requires_clean_source": True,
    }


def _cue_matches(prompt_low: str, prompt_terms: list[str], cue: str) -> bool:
    cue_low = str(cue or "").casefold().strip()
    if not cue_low:
        return False
    if cue_low in prompt_low:
        return True
    cue_terms = [term.casefold() for term in split_query_terms([cue]) if len(term.strip()) >= 3]
    return any(term and term in prompt_terms for term in cue_terms)


def _route_cues(route: Mapping[str, Any]) -> Iterable[str]:
    for value in route.get("route_cues") or ():
        yield str(value)
    for value in route.get("query_terms") or ():
        yield str(value)
    title = route.get("title")
    if title:
        yield str(title)


def _cue_score(cue: str) -> float:
    length = len(str(cue or "").strip())
    return min(4.0, max(0.8, length / 8.0))


def map_query_diagnostics(scale: str) -> dict[str, bool | str]:
    return {
        "scale": scale,
        "map_summary_is_navigation_only": True,
        "source_reopen_required_for_claims": True,
        "far_view_explicit_only": scale == "far",
        "prompt_hook_default_safe": scale == "near",
    }


def map_query_coverage(cognitive_map: dict[str, Any], **extra: int) -> dict[str, int]:
    overview = dict_or_empty(cognitive_map.get("registry_overview"))
    coverage = {
        "episode_count": int(cognitive_map.get("episode_count") or 0),
        "landmark_count": int(cognitive_map.get("landmark_count") or 0),
        "region_count": int(cognitive_map.get("region_count") or 0),
        "route_count": int(cognitive_map.get("route_count") or 0),
        "registry_overview_count": int(cognitive_map.get("registry_overview_count") or 0),
        "registry_overview_cluster_count": len(_safe_rows(overview.get("clusters"))),
    }
    coverage.update(extra)
    return coverage


def _far_theme_counts(routes: list[dict[str, Any]], cognitive_map: dict[str, Any]) -> dict[str, int]:
    theme_terms: list[str] = []
    for route in routes:
        # Far view should privilege broad regions over individual landmarks.
        # Landmarks remain useful scent, but they should not crowd out the
        # "what directions did I spend time on?" layer.
        for label in route.get("region_labels") or []:
            theme_terms.extend([str(label), str(label)])
        theme_terms.extend(str(label) for label in route.get("landmark_labels") or [])
    theme_counts = _count_dict(theme_terms)
    if theme_counts:
        return theme_counts
    overview = dict_or_empty(cognitive_map.get("registry_overview"))
    return _count_dict(
        str(label)
        for cluster in _safe_rows(overview.get("clusters"))
        for label in [cluster.get("label"), *(cluster.get("keywords") or [])]
    )


def _far_view(cognitive_map: dict[str, Any], *, limit: int) -> dict[str, Any]:
    episodes = _safe_rows(cognitive_map.get("episodes"))
    routes = _safe_rows(cognitive_map.get("routes"))
    route_thread_keys = {
        str(thread)
        for route in routes
        for thread in route.get("thread_keys") or []
        if str(thread).strip()
    }
    episode_thread_keys = {
        str(row.get("thread_key") or "") for row in episodes if row.get("thread_key")
    }
    theme_counts = _far_theme_counts(routes, cognitive_map)
    coverage = map_query_coverage(cognitive_map)
    return {
        "scale": "far",
        "themes": [
            {"label": label, "count": count, "source_boundary": _source_boundary()}
            for label, count in list(theme_counts.items())[:limit]
        ],
        "project_distribution": _count_dict(
            str(row.get("project_label") or row.get("title") or "") for row in episodes
        ),
        "time_distribution": _count_dict(_month_bucket(row.get("updated_at")) for row in episodes),
        "coverage": coverage,
        "coverage_gaps": {
            "registry_only_episode_count": max(0, len(episode_thread_keys - route_thread_keys)),
            "route_without_source_ref_count": sum(1 for route in routes if not route.get("source_refs")),
            "registry_overview_cluster_count": coverage["registry_overview_cluster_count"],
        },
        "diagnostics": map_query_diagnostics("far"),
    }


def _mid_region_rows(
    prompt: str,
    cognitive_map: dict[str, Any],
    *,
    project_label: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    prompt_low = prompt.casefold()
    prompt_terms = [
        term.casefold() for term in split_query_terms([prompt]) if len(term.strip()) >= 3
    ]
    landmarks_by_region: dict[str, list[str]] = {}
    for landmark in _safe_rows(cognitive_map.get("landmarks")):
        for region_id in landmark.get("region_ids") or []:
            landmarks_by_region.setdefault(str(region_id), []).append(
                str(landmark.get("label") or "")
            )
    routes_by_region: dict[str, list[dict[str, Any]]] = {}
    for route in _safe_rows(cognitive_map.get("routes")):
        for region_id in route.get("region_ids") or []:
            routes_by_region.setdefault(str(region_id), []).append(route)

    rows: list[dict[str, Any]] = []
    for region in _safe_rows(cognitive_map.get("regions")):
        region_id = str(region.get("region_id") or "")
        region_routes = routes_by_region.get(region_id, [])
        landmark_labels = unique_preserve(landmarks_by_region.get(region_id, []), limit=12)
        cues = unique_preserve(
            [str(region.get("label") or "")]
            + landmark_labels
            + [
                str(value)
                for route in region_routes
                for value in _route_cues(route)
            ],
            limit=40,
        )
        matched = [cue for cue in cues if _cue_matches(prompt_low, prompt_terms, cue)]
        project_boost = 0.0
        if project_label and str(region.get("label") or "").casefold() == project_label.casefold():
            project_boost = 0.8
        score = min(
            20.0,
            sum(_cue_score(cue) for cue in matched)
            + float(region.get("confidence") or 0.0) * 4.0
            + project_boost,
        )
        rows.append(
            {
                "region_id": region_id,
                "label": region.get("label"),
                "matched_cues": unique_preserve(matched, limit=8),
                "score": round(score, 3),
                "landmark_labels": landmark_labels,
                "representative_threads": unique_preserve(
                    [str(thread) for thread in region.get("thread_keys") or []], limit=8
                ),
                "representative_routes": [
                    {
                        "route_id": route.get("route_id"),
                        "title": route.get("title"),
                        "thread_keys": unique_preserve(
                            [str(thread) for thread in route.get("thread_keys") or []], limit=4
                        ),
                    }
                    for route in region_routes[:3]
                ],
                "route_count": len(region_routes),
                "source_boundary": _source_boundary(),
            }
        )
    rows.sort(
        key=lambda item: (
            bool(item.get("matched_cues")),
            float(item.get("score") or 0.0),
            int(item.get("route_count") or 0),
            str(item.get("label") or ""),
        ),
        reverse=True,
    )
    return rows[:limit]


def _mid_view(
    prompt: str,
    cognitive_map: dict[str, Any],
    *,
    project_label: str | None,
    limit: int,
) -> dict[str, Any]:
    rows = _mid_region_rows(prompt, cognitive_map, project_label=project_label, limit=limit)
    return {
        "scale": "mid",
        "regions": rows,
        "coverage": map_query_coverage(
            cognitive_map,
            matched_region_count=sum(1 for row in rows if row.get("matched_cues")),
        ),
        "diagnostics": map_query_diagnostics("mid"),
    }


def _near_view(
    prompt: str,
    cognitive_map: dict[str, Any],
    *,
    project_label: str | None,
    limit: int,
    near_matcher: NearMatcher | None,
) -> dict[str, Any]:
    matches = (
        near_matcher(
            prompt,
            cognitive_map,
            project_label=project_label,
            limit=limit,
        )
        if near_matcher is not None
        else _match_near_cognitive_map(
            prompt,
            cognitive_map,
            project_label=project_label,
            limit=limit,
        )
    )
    return {
        "scale": "near",
        "matches": matches,
        "coverage": map_query_coverage(cognitive_map, match_count=len(matches)),
        "diagnostics": map_query_diagnostics("near"),
    }


def _match_near_cognitive_map(
    prompt: str,
    cognitive_map: dict[str, Any],
    *,
    project_label: str | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if not prompt or not cognitive_map:
        return []
    prompt_low = prompt.casefold()
    prompt_terms = [
        term.casefold() for term in split_query_terms([prompt]) if len(term.strip()) >= 3
    ]
    matches: list[dict[str, Any]] = []
    for route in _safe_rows(cognitive_map.get("routes")):
        negative = _compact_terms(route.get("negative_cues"), limit=12)
        if any(_cue_matches(prompt_low, prompt_terms, cue) for cue in negative):
            continue
        cues = unique_preserve(
            _compact_terms(route.get("route_cues"), limit=16)
            + _compact_terms(route.get("landmark_labels"), limit=10)
            + _compact_terms(route.get("region_labels"), limit=8)
            + _compact_terms(route.get("query_terms"), limit=16),
            limit=36,
        )
        matched = [cue for cue in cues if _cue_matches(prompt_low, prompt_terms, cue)]
        if not matched:
            continue
        project_boost = 0.0
        if project_label:
            labels = [str(value) for value in route.get("region_labels") or []]
            labels.extend(
                str(ref.get("project_label") or "")
                for ref in route.get("source_refs") or []
                if isinstance(ref, dict)
            )
            if any(label and label.casefold() == project_label.casefold() for label in labels):
                project_boost = 1.5
        score = min(
            30.0,
            sum(_cue_score(cue) for cue in matched)
            + float(route.get("confidence") or 0.0) * 8.0
            + project_boost,
        )
        matches.append(
            {
                "route_id": route.get("route_id"),
                "route_kind": route.get("route_kind"),
                "title": route.get("title"),
                "landmark_labels": route.get("landmark_labels") or [],
                "region_labels": route.get("region_labels") or [],
                "route_cues": route.get("route_cues") or [],
                "matched_cues": unique_preserve(matched, limit=8),
                "query_terms": unique_preserve(
                    [str(value) for value in route.get("query_terms") or []], limit=16
                ),
                "thread_keys": unique_preserve(
                    [str(value) for value in route.get("thread_keys") or []], limit=8
                ),
                "confidence": route.get("confidence"),
                "score": round(score, 3),
                "source": route.get("source"),
                "source_refs": route.get("source_refs") or [],
            }
        )
    matches.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            float(item.get("confidence") or 0.0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return matches[:limit]


def query_cognitive_map(
    prompt: str,
    cognitive_map: dict[str, Any],
    *,
    scale: str = "near",
    project_label: str | None = None,
    limit: int = 4,
    near_matcher: NearMatcher | None = None,
) -> dict[str, Any]:
    """Return an explicit-scale cognitive-map navigation packet.

    Far and mid views intentionally summarize map structure instead of exposing
    every route. They orient attention only; exact claims still require
    reopening clean source through a near route packet.
    """
    scale_key = str(scale or "near").casefold()
    if scale_key not in MAP_QUERY_SCALES:
        raise ValueError(f"unsupported cognitive-map query scale: {scale}")
    if scale_key == "far":
        return _far_view(cognitive_map, limit=limit)
    if scale_key == "mid":
        return _mid_view(
            prompt,
            cognitive_map,
            project_label=project_label,
            limit=limit,
        )
    return _near_view(
        prompt,
        cognitive_map,
        project_label=project_label,
        limit=limit,
        near_matcher=near_matcher,
    )
