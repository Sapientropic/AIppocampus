"""Registry-source candidates for APW recovery.

APW uses these rows as navigation only. A registry exact-search hit can tell the
agent where to reopen source, but it must still pass the APW source-shape guard
and `agent deepen` before it supports a claim.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.recall.apw_anchor_coverage import (
    low_actual_anchor_coverage_reason,
    matched_terms_from_text,
    query_anchor_terms,
    source_anchor_gate,
)
from aippocampus_runtime.recall.foreground import route_quality as foreground_route_quality
from aippocampus_runtime.recall.query_policy import unique_preserve
from aippocampus_runtime.source.artifact_role import match_is_demoted_artifact
from aippocampus_runtime.source.registry_search import search_registry_sources
from aippocampus_runtime.source.registry_search_duplicates import match_haystack
from aippocampus_runtime.source.search_terms import search_query_terms

PRIVATE_BUCKETS = {"private", "restricted", "personal", "user_private", "machine_private"}


def _compact(value: Any, limit: int = 120) -> str:
    sanitized, _ = core.sanitize_external_model_text(str(value or ""))
    return core.compact_text(sanitized, limit)


def _component(name: str, *, status: str, row_count: int, malformed_count: int = 0) -> dict[str, Any]:
    result = {
        "component": name,
        "status": status,
        "row_count": int(row_count),
        "malformed_row_count": int(malformed_count),
        "authority": "navigation_only_not_source_truth",
    }
    if status == "missing":
        result["next_action"] = "continue without registry APW candidates or pass a registry_dir"
    return result


def _scope_bucket(match: Mapping[str, Any]) -> str:
    labels = [
        str(label).strip().casefold()
        for value in (
            match.get("scope_labels"),
            match.get("semantic_scope_labels"),
        )
        for label in (value if isinstance(value, Sequence) and not isinstance(value, str) else [value])
        if str(label or "").strip()
    ]
    if any(label in PRIVATE_BUCKETS for label in labels):
        return "user_private"
    return labels[0] if labels else "registry_source"


def _source_ref_from_registry_match(match: Mapping[str, Any]) -> dict[str, Any]:
    raw_route = match.get("source_route")
    route = raw_route if isinstance(raw_route, Mapping) else {}
    if route.get("kind") != "registry_clean_source_hit":
        return {}
    raw_thread = match.get("thread")
    thread = raw_thread if isinstance(raw_thread, Mapping) else {}
    ref = {
        "thread_key": route.get("thread_key") or thread.get("thread_key"),
        "source_id": match.get("source_id"),
        "message_id": route.get("message_id") or match.get("message_id"),
        "turn_id": match.get("turn_id"),
        "turn_index": match.get("turn_index"),
        "line": route.get("line") or match.get("line"),
        "phase": match.get("phase") or "",
    }
    clean = {key: value for key, value in ref.items() if value not in (None, "", [])}
    if not clean.get("thread_key"):
        return {}
    if not any(clean.get(key) for key in ("message_id", "turn_id", "turn_index", "line")):
        return {}
    return clean


def _candidate_from_match(
    match: Mapping[str, Any],
    *,
    query: str,
    anchor_terms: Sequence[str],
    skip_reasons: Counter[str] | None = None,
) -> dict[str, Any] | None:
    ref = _source_ref_from_registry_match(match)
    if not ref:
        if skip_reasons is not None:
            skip_reasons["missing_reopenable_source_ref"] += 1
        return None
    haystack = match_haystack(match)
    anchor_matches = matched_terms_from_text(haystack, anchor_terms)
    search_term_matches = matched_terms_from_text(
        haystack,
        search_query_terms([query]),
        limit=12,
    )
    # Registry search may split a Chinese cue into useful subterms when the old
    # source says "黏菌式探索" and "召回算法" rather than the exact later cue
    # "探索算法". Accept that as APW navigation only when it still carries at
    # least one declared anchor or multiple concrete query subterms.
    if not anchor_matches and len(search_term_matches) < 2:
        if skip_reasons is not None:
            skip_reasons["insufficient_anchor_matches"] += 1
        return None
    matched_terms = unique_preserve([*anchor_matches, *search_term_matches], limit=8)
    low_anchor_reason = low_actual_anchor_coverage_reason(
        matched_terms=matched_terms,
        anchor_terms=anchor_terms,
    )
    if low_anchor_reason:
        if skip_reasons is not None:
            skip_reasons[low_anchor_reason] += 1
        return None
    anchor_quality = foreground_route_quality.anchor_quality(
        matched_terms=matched_terms,
        anchor_terms=anchor_terms,
    )
    meaningful_matched_terms = foreground_route_quality.meaningful_terms(matched_terms)
    route_terms = unique_preserve(meaningful_matched_terms or matched_terms, limit=12)
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    thread_key = str(ref.get("thread_key") or "")
    message_id = str(ref.get("message_id") or "")
    line = str(ref.get("line") or "")
    route_id_seed = "|".join(part for part in (thread_key, message_id, line) if part)
    public_id = core.stable_text_fingerprint(
        route_id_seed or haystack,
        namespace="registry-apw-source-candidate",
        prefix="apwr",
        length=16,
    )
    return {
        "route_id": f"registry-clean-source:{public_id}",
        "candidate_id": f"registry-clean-source:{public_id}",
        "thread_key": _compact(thread_key, 120),
        "route_terms": route_terms,
        "query_anchor_terms": unique_preserve(anchor_terms, limit=12),
        "actual_source_matched_terms": route_terms,
        "meaningful_matched_terms": route_terms,
        "anchor_quality": anchor_quality,
        "source_anchor_gate": source_anchor_gate(
            matched_terms=matched_terms,
            anchor_terms=anchor_terms,
        ),
        "route_label": "APW registry source route: " + " / ".join(route_terms[:3]),
        "source_refs": [ref],
        "scope_bucket": _scope_bucket(match),
        "freshness": "registered_source",
        "source": "registry_clean_source",
        "candidate_source_kind": "registry_clean_source",
        "source_shape_completeness": "complete",
        "reason_codes": ["registry_source_exact_search_candidate"],
        "title": _compact(thread_map.get("title") or query, 120),
    }


def registry_source_candidate_rows(
    *,
    query: str,
    cwd: str | Path | None = None,
    registry_dir: str | Path | None = None,
    limit: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive APW navigation candidates from registry-wide exact source search."""

    if registry_dir is None:
        return [], _component("registry_clean_source_candidates", status="missing", row_count=0)
    anchor_terms = query_anchor_terms(query)
    if not anchor_terms:
        return [], _component("registry_clean_source_candidates", status="needs_query", row_count=0)
    try:
        payload = search_registry_sources(
            [query],
            registry_dir=registry_dir,
            limit=max(1, int(limit or 1)),
            per_thread_limit=max(5, int(limit or 1)),
            search_budget="deep",
            cwd=cwd,
        )
    except Exception:
        return [], _component("registry_clean_source_candidates", status="unreadable", row_count=0)
    candidates: list[dict[str, Any]] = []
    skip_reasons: Counter[str] = Counter()
    # The registry query gate may suppress thin anchor hits before APW sees
    # candidate rows; keep that loss visible in APW diagnostics so a safe
    # abstain does not look like the registry source path was never tested.
    upstream_low_coverage_filtered_count = int(
        payload.get("suppressed_low_coverage_match_count") or 0
    )
    demoted_count = 0
    malformed_count = 0
    for match in payload.get("matches") or []:
        if not isinstance(match, Mapping):
            malformed_count += 1
            continue
        if match_is_demoted_artifact(match):
            demoted_count += 1
            continue
        candidate = _candidate_from_match(
            match,
            query=query,
            anchor_terms=anchor_terms,
            skip_reasons=skip_reasons,
        )
        if candidate:
            candidates.append(candidate)
    candidates = candidates[: max(1, int(limit or 1))]
    component = _component(
        "registry_clean_source_candidates",
        status="loaded" if candidates else "loaded_no_matches",
        row_count=len(candidates),
        malformed_count=malformed_count,
    )
    component.update(
        {
            "searched_entry_count": int(payload.get("searched_entry_count") or 0),
            "registry_match_count": int(payload.get("match_count") or 0),
            "demoted_artifact_match_count": demoted_count,
            "low_actual_source_anchor_coverage_filtered_count": int(
                upstream_low_coverage_filtered_count
                + skip_reasons.get("low_actual_source_anchor_coverage", 0)
                + skip_reasons.get("missing_cjk_context_anchor", 0)
            ),
            "source_reopenable_candidate_count": len(candidates),
        }
    )
    return candidates, component


def has_registry_source_candidate_input(
    *,
    query: str,
    cwd: str | Path | None = None,
    registry_dir: str | Path | None = None,
) -> bool:
    candidates, _component_report = registry_source_candidate_rows(
        query=query,
        cwd=cwd,
        registry_dir=registry_dir,
        limit=1,
    )
    return bool(candidates)


__all__ = [
    "has_registry_source_candidate_input",
    "registry_source_candidate_rows",
]
