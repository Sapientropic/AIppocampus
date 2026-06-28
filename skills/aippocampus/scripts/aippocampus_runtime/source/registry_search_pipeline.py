"""Foreground-safe registry-wide source search projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from aippocampus_runtime.core import compact_text, stable_text_fingerprint
from aippocampus_runtime.source.artifact_role import (
    artifact_role_profile,
    match_is_demoted_artifact,
)
from aippocampus_runtime.source.query_match_gate import (
    match_query_profile,
    query_match_gate,
)
from aippocampus_runtime.source.registry_search_duplicates import (
    collapse_duplicate_matches,
    match_haystack,
    process_noise_reason,
)
from aippocampus_runtime.source.registry_search_evidence import (
    duplicate_ref_has_direct_source_open_route,
    match_has_direct_source_open_route,
    query_anchor_rank,
)
from aippocampus_runtime.source.registry_search_render import render_registry_search_payload
from aippocampus_runtime.source.registry_search_skips import (
    registry_entry_ref,
    registry_entry_search_skip,
)
from aippocampus_runtime.source.registry_source_routes import (
    registry_clean_source_route,
    registry_source_window_command,
)
from aippocampus_runtime.source.registry_source_window import write_last_registry_search_cache
from aippocampus_runtime.source.relationship_origin import (
    relationship_origin_allows_low_coverage,
    relationship_origin_rank_adjustment,
)
from aippocampus_runtime.source.repo_doc_search import repo_checkout_doc_matches
from aippocampus_runtime.source.search_terms import search_query_terms

DEFAULT_PUBLIC_SNIPPET_CHARS = 260


@dataclass
class RegistrySearchInput:
    registry_root: Path | None
    registry_json: Path
    registry_payload: Mapping[str, Any]
    query_text: str
    terms: list[str]
    query_gate: Mapping[str, Any]
    budget: Any
    repo_doc_matches: list[dict[str, Any]]
    max_elapsed_ms: int | None = None
    started_at: float = 0.0


@dataclass
class RegistrySearchEvaluation:
    matches: list[dict[str, Any]]
    suppressed_matches: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    searched_entry_count: int
    skipped_entries: list[dict[str, Any]]
    skipped_reason_counts: dict[str, int]
    unavailable_source_count: int
    budget_exhausted: bool = False
    elapsed_ms: float = 0.0
    max_elapsed_ms: int | None = None
    unsearched_entry_count: int = 0


def _search_deadline(started_at: float, max_elapsed_ms: int | None) -> float | None:
    if max_elapsed_ms is None or max_elapsed_ms <= 0:
        return None
    return started_at + (max_elapsed_ms / 1000.0)


def _deadline_exhausted(deadline: float | None) -> bool:
    return deadline is not None and perf_counter() >= deadline


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _hit_selector(route: Mapping[str, Any]) -> str:
    return stable_text_fingerprint(
        json.dumps(route, ensure_ascii=False, sort_keys=True, default=str),
        namespace="registry-search-hit-selector",
        prefix="srchit",
        length=18,
    )


def _registry_match(
    *,
    entry: Mapping[str, Any],
    hit: Mapping[str, Any],
    include_paths: bool,
) -> dict[str, Any]:
    raw_paths = entry.get("paths")
    paths: Mapping[str, Any] = raw_paths if isinstance(raw_paths, Mapping) else {}
    thread_key = str(entry.get("thread_key") or "").strip()
    source_kind = str(hit.get("source") or "")
    message_id = hit.get("message_id") or (hit.get("id") if source_kind == "clean_source" else None)
    route_line = hit.get("line") if source_kind == "clean_source" or message_id else None
    # SQLite line numbers are index/raw positions, not clean-source reopen keys.
    # Keeping line-only index scent out of source_route prevents agents from
    # treating it as a copy-pasteable source-open handle.
    source_route = (
        registry_clean_source_route(
            thread_key=thread_key,
            message_id=message_id,
            line=route_line,
        )
        if message_id or route_line is not None
        else {}
    )
    raw_snippet = str(hit.get("snippet") or "")
    snippet = compact_text(raw_snippet, DEFAULT_PUBLIC_SNIPPET_CHARS)
    noise_reason = str(hit.get("noise_reason") or "") or process_noise_reason(snippet)
    artifact_role = artifact_role_profile(
        text=snippet,
        metadata={
            "role": hit.get("role"),
            "phase": hit.get("phase"),
            "material_class": hit.get("material_class"),
            "source_claim_policy": hit.get("source_claim_policy"),
            "scope_labels": hit.get("scope_labels") or [],
            "semantic_scope_labels": hit.get("semantic_scope_labels") or [],
        },
    )
    match = {
        "hit_selector": _hit_selector(source_route),
        "thread": registry_entry_ref(entry),
        "source": hit.get("source"),
        "message_id": message_id,
        "turn_id": hit.get("turn_id"),
        "line": hit.get("line"),
        "role": hit.get("role"),
        "phase": hit.get("phase") or "",
        "material_class": hit.get("material_class"),
        "source_claim_policy": hit.get("source_claim_policy"),
        "turn_index": hit.get("turn_index"),
        "is_final": bool(hit.get("is_final")),
        "scope_labels": hit.get("scope_labels") or [],
        "semantic_scope_labels": hit.get("semantic_scope_labels") or [],
        "score": hit.get("rank_score") or hit.get("score"),
        "snippet": snippet,
        "search_noise": bool(hit.get("search_noise")) or bool(noise_reason),
        "noise_reason": noise_reason,
        "artifact_role": artifact_role if artifact_role.get("role") != "topic_candidate" else None,
        "artifact_demoted": bool(artifact_role.get("demote")),
        "source_route": source_route,
    }
    if raw_snippet and raw_snippet != snippet:
        match["_ranking_haystack"] = raw_snippet
    if include_paths:
        match["local_diagnostic"] = {
            "workspace": paths.get("workspace"),
            "clean_source_messages_jsonl": paths.get("clean_source_messages_jsonl"),
            "sqlite": paths.get("sqlite"),
        }
    return {key: value for key, value in match.items() if value not in (None, "", [], {})}


def _annotate_last_search_reopen_commands(
    matches: list[dict[str, Any]],
    *,
    registry_dir: str | Path | None,
    include_paths: bool,
) -> None:
    for index, match in enumerate(matches, start=1):
        raw_route = match.get("source_route")
        route: Mapping[str, Any] = raw_route if isinstance(raw_route, Mapping) else {}
        if route.get("kind") == "repo_checkout_doc_hit":
            command = str(match.get("source_window_command") or match.get("reopen_command") or "").strip()
            match["hit_index"] = index
            if command:
                match["reopen_command"] = command
                match["source_window_command"] = command
                match["last_search_reopen_command"] = command
            continue
        match["hit_index"] = index
        if match_has_direct_source_open_route(match):
            source_window_command = registry_source_window_command(
                route,
                registry_dir=registry_dir,
                include_registry_dir=include_paths,
            )
            match["reopen_command"] = source_window_command
            match["source_window_command"] = source_window_command
            match["last_search_reopen_command"] = (
                f"aippocampus search --hit {index} --last-search --json"
            )
        duplicate_refs = [
            ref for ref in match.get("duplicate_source_refs") or [] if isinstance(ref, dict)
        ]
        for ref_index, ref in enumerate(duplicate_refs, start=1):
            route_ref = registry_clean_source_route(
                thread_key=str(ref.get("thread_key") or ""),
                message_id=str(ref.get("message_id") or ""),
                line=ref.get("line"),
            )
            if not route_ref.get("thread_key"):
                continue
            if not duplicate_ref_has_direct_source_open_route(match, ref, route_ref):
                continue
            ref_command = registry_source_window_command(
                route_ref,
                registry_dir=registry_dir,
                include_registry_dir=include_paths,
            )
            ref["source_ref_index"] = ref_index
            ref["source_route"] = route_ref
            ref["reopen_command"] = ref_command
            ref["source_window_command"] = ref_command
            ref["last_search_reopen_command"] = (
                f"aippocampus search --hit {index} --last-search "
                f"--source-ref-index {ref_index} --json"
            )


def _load_registry_search_input(
    patterns: list[str],
    *,
    registry_dir: str | Path | None,
    search_budget: str,
    cwd: str | Path | None,
    limit: int,
    max_elapsed_ms: int | None,
) -> RegistrySearchInput:
    from aippocampus_runtime.registry.search import REGISTRY_SEARCH_DEEP_BUDGET
    from aippocampus_runtime.registry.store import load_registry, registry_paths

    registry_root = Path(registry_dir).resolve() if registry_dir else None
    registry_json, _ = registry_paths(registry_root)
    registry_payload = load_registry(registry_json)
    query_text = " ".join(str(pattern) for pattern in patterns).strip()
    terms = search_query_terms(patterns)
    query_gate = query_match_gate(query_text)
    repo_doc_matches = repo_checkout_doc_matches(
        cwd=cwd or Path.cwd(),
        query_text=query_text,
        query_gate=query_gate,
        limit=limit,
        snippet_chars=DEFAULT_PUBLIC_SNIPPET_CHARS,
    )
    return RegistrySearchInput(
        registry_root=registry_root,
        registry_json=registry_json,
        registry_payload=registry_payload,
        query_text=query_text,
        terms=terms,
        query_gate=query_gate,
        budget=REGISTRY_SEARCH_DEEP_BUDGET if search_budget == "deep" else None,
        repo_doc_matches=repo_doc_matches,
        max_elapsed_ms=max_elapsed_ms,
        started_at=perf_counter(),
    )


def _profile_registry_match(
    *,
    match: dict[str, Any],
    query_text: str,
    query_gate: Mapping[str, Any],
) -> Mapping[str, Any]:
    profile = match_query_profile(
        query_text=query_text,
        gate=query_gate,
        haystack=match_haystack(match),
    )
    if profile["accepted"]:
        return profile
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    origin_profile = relationship_origin_allows_low_coverage(
        query_text=query_text,
        haystack=match_haystack(match),
        scope_labels=[
            *[str(label) for label in match.get("scope_labels") or []],
            *[str(label) for label in match.get("semantic_scope_labels") or []],
        ],
        thread_title=str(thread_map.get("title") or ""),
    )
    if not origin_profile["accepted"]:
        return profile
    return {
        **profile,
        "accepted": True,
        "suppression_reason": "",
        "relationship_origin_override": origin_profile["suppression_override_reason"],
        "relationship_origin": {
            key: value
            for key, value in origin_profile.items()
            if key
            in {
                "primary_anchor_count",
                "supporting_anchor_count",
                "matched_primary_anchors",
                "matched_supporting_anchors",
            }
        },
    }


def _collect_registry_search_matches(
    inputs: RegistrySearchInput,
    *,
    include_paths: bool,
    per_thread_limit: int,
) -> RegistrySearchEvaluation:
    from aippocampus_runtime.registry.search import deep_search_entry_result

    matches = list(inputs.repo_doc_matches)
    suppressed_matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    searched_entry_count = 0
    skipped_entries: list[dict[str, Any]] = []
    skipped_reason_counts: dict[str, int] = {}
    unavailable_source_count = 0
    budget_exhausted = False
    unsearched_entry_count = 0
    deadline = _search_deadline(inputs.started_at, inputs.max_elapsed_ms)
    entries = [
        entry
        for entry in inputs.registry_payload.get("threads") or []
        if isinstance(entry, Mapping)
    ]
    for index, entry in enumerate(entries):
        if _deadline_exhausted(deadline):
            budget_exhausted = True
            unsearched_entry_count = len(entries) - index
            warnings.append(
                {
                    "stage": "registry_search",
                    "code": "foreground_search_time_budget_exhausted",
                    "message": "Registry-wide search stopped at the foreground wall-clock budget.",
                    "max_elapsed_ms": inputs.max_elapsed_ms,
                    "unsearched_entry_count": unsearched_entry_count,
                }
            )
            break
        searched_entry_count += 1
        skip = registry_entry_search_skip(entry)
        if skip:
            skipped_entries.append(skip)
            reason = str(skip.get("reason") or "not_searchable")
            skipped_reason_counts[reason] = skipped_reason_counts.get(reason, 0) + 1
            if reason == "configured_search_sources_missing":
                unavailable_source_count += 1
            continue
        result = deep_search_entry_result(
            dict(entry),
            inputs.terms,
            max_hits=per_thread_limit,
            search_budget=inputs.budget,
            deadline=deadline,
        )
        if result.get("budget_exhausted"):
            budget_exhausted = True
        entry_warnings = []
        for warning in result.get("warnings") or []:
            item = dict(warning) if isinstance(warning, Mapping) else {"message": str(warning)}
            item["thread_key"] = entry.get("thread_key")
            entry_warnings.append(item)
        if entry_warnings:
            warnings.extend(entry_warnings)
            unavailable_source_count += 1
        for hit in result.get("hits") or []:
            if not isinstance(hit, Mapping):
                continue
            match = _registry_match(
                entry=entry,
                hit=hit,
                include_paths=include_paths,
            )
            text_for_artifact = match_haystack(match)
            artifact_role = artifact_role_profile(
                text=text_for_artifact,
                query_text=inputs.query_text,
                metadata={
                    "role": match.get("role"),
                    "phase": match.get("phase"),
                    "material_class": match.get("material_class"),
                    "source_claim_policy": match.get("source_claim_policy"),
                    "scope_labels": match.get("scope_labels") or [],
                    "semantic_scope_labels": match.get("semantic_scope_labels") or [],
                },
            )
            if artifact_role.get("role") != "topic_candidate":
                match["artifact_role"] = artifact_role
            else:
                match.pop("artifact_role", None)
            match["artifact_demoted"] = bool(artifact_role.get("demote"))
            profile = _profile_registry_match(
                match=match,
                query_text=inputs.query_text,
                query_gate=inputs.query_gate,
            )
            match["query_match_profile"] = profile
            if profile["accepted"]:
                matches.append(match)
            else:
                suppressed_matches.append(
                    {
                        "thread": match.get("thread"),
                        "score": match.get("score"),
                        "query_match_profile": profile,
                        "source": match.get("source"),
                        "line": match.get("line"),
                    }
                )
        if budget_exhausted:
            unsearched_entry_count = len(entries) - index - 1
            break
    return RegistrySearchEvaluation(
        matches=matches,
        suppressed_matches=suppressed_matches,
        warnings=warnings,
        searched_entry_count=searched_entry_count,
        skipped_entries=skipped_entries,
        skipped_reason_counts=skipped_reason_counts,
        unavailable_source_count=unavailable_source_count,
        budget_exhausted=budget_exhausted,
        elapsed_ms=round((perf_counter() - inputs.started_at) * 1000, 3),
        max_elapsed_ms=inputs.max_elapsed_ms,
        unsearched_entry_count=unsearched_entry_count,
    )


def _finalize_registry_search_matches(
    matches: list[dict[str, Any]],
    *,
    query_text: str,
    registry_root: Path | None,
    include_paths: bool,
    record_last_search: bool,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") or match_is_demoted_artifact(item) else 0,
            -query_anchor_rank(item)[0],
            -query_anchor_rank(item)[1],
            -query_anchor_rank(item)[2],
            -(
                as_float(item.get("score"))
                + relationship_origin_rank_adjustment(
                    query_text=query_text,
                    match=item,
                    haystack=match_haystack(item),
                )
            ),
            str((item.get("thread") or {}).get("thread_key") or ""),
            as_int(item.get("line")),
        )
    )
    collapsed_matches, duplicate_metrics = collapse_duplicate_matches(matches, limit=limit)
    _annotate_last_search_reopen_commands(
        collapsed_matches,
        registry_dir=registry_root,
        include_paths=include_paths,
    )
    if record_last_search:
        write_last_registry_search_cache(
            registry_dir=registry_root,
            query_text=query_text,
            matches=collapsed_matches,
        )
    return collapsed_matches, duplicate_metrics


def search_registry_sources(
    patterns: list[str],
    *,
    registry_dir: str | Path | None = None,
    limit: int = 10,
    per_thread_limit: int = 3,
    include_paths: bool = False,
    search_budget: str = "default",
    record_last_search: bool = False,
    cwd: str | Path | None = None,
    max_elapsed_ms: int | None = 5000,
) -> dict[str, Any]:
    """Search registered clean-source/index entries without exposing raw paths by default.

    aippocampus-stage-map: load registry/searchable entries -> evaluate query
    coverage, artifact demotion, and relationship-origin overrides -> rank and
    collapse source routes -> render compact foreground-safe output with detail
    diagnostics behind opt-in flags. Keep proof/follow-through evidence out of
    the default card; this function only selects source-open routes.
    """

    inputs = _load_registry_search_input(
        patterns,
        registry_dir=registry_dir,
        search_budget=search_budget,
        cwd=cwd,
        limit=limit,
        max_elapsed_ms=max_elapsed_ms,
    )
    evaluation = _collect_registry_search_matches(
        inputs,
        include_paths=include_paths,
        per_thread_limit=per_thread_limit,
    )
    matches, duplicate_metrics = _finalize_registry_search_matches(
        evaluation.matches,
        query_text=inputs.query_text,
        registry_root=inputs.registry_root,
        include_paths=include_paths,
        record_last_search=record_last_search,
        limit=limit,
    )
    return render_registry_search_payload(
        inputs,
        evaluation,
        matches=matches,
        duplicate_metrics=duplicate_metrics,
        include_paths=include_paths,
        search_budget=search_budget,
        annotate_reopen_commands=_annotate_last_search_reopen_commands,
    )
