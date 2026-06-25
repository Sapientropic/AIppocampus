"""Foreground-safe registry-wide source search projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    shell_quote,
)
from aippocampus_runtime.core import compact_text, stable_text_fingerprint
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.artifact_role import (
    artifact_role_profile,
    match_is_demoted_artifact,
)
from aippocampus_runtime.source.discussion_atlas_pointer import (
    discussion_atlas_action,
    discussion_atlas_pointer_for_query,
)
from aippocampus_runtime.source.query_match_gate import (
    match_query_profile,
    query_match_gate,
)
from aippocampus_runtime.source.registry_search_actions import registry_search_actions
from aippocampus_runtime.source.registry_search_duplicates import (
    collapse_duplicate_matches,
    compact_registry_match,
    diagnostic_registry_match,
    match_haystack,
    process_noise_reason,
)
from aippocampus_runtime.source.registry_search_evidence import (
    match_evidence_diagnostics,
    match_is_useful_registry_target,
    query_anchor_rank,
)
from aippocampus_runtime.source.registry_search_skips import (
    registry_entry_ref,
    registry_entry_search_skip,
    skipped_maintenance_actions,
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


@dataclass
class RegistrySearchEvaluation:
    matches: list[dict[str, Any]]
    suppressed_matches: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    searched_entry_count: int
    skipped_entries: list[dict[str, Any]]
    skipped_reason_counts: dict[str, int]
    unavailable_source_count: int


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
    source_route = {
        "kind": "registry_clean_source_hit",
        "thread_key": thread_key,
        "line": hit.get("line"),
        "message_id": hit.get("message_id") or hit.get("id"),
        "boundary": "reopen_source_before_quoting_or_strong_claims",
    }
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
        "message_id": hit.get("message_id") or hit.get("id"),
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
    registry_arg = ""
    if include_paths and registry_dir:
        registry_arg = f" --registry-dir {shell_quote(str(Path(registry_dir).resolve()))}"
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
        thread_key = str(route.get("thread_key") or "")
        message_id = str(route.get("message_id") or "")
        line = route.get("line")
        line_arg = ""
        if line is not None and str(line).isdigit():
            line_arg = f"--line {int(str(line))}"
        direct_parts = [
            "aippocampus search --open-source",
            f"--thread-key {shell_quote(thread_key)}" if thread_key else "",
            f"--message-id {shell_quote(message_id)}" if message_id else "",
            line_arg,
            registry_arg.strip(),
            "--json",
        ]
        source_window_command = " ".join(part for part in direct_parts if part)
        match["hit_index"] = index
        match["reopen_command"] = source_window_command
        match["source_window_command"] = source_window_command
        match["last_search_reopen_command"] = f"aippocampus search --hit {index} --last-search --json"


def _load_registry_search_input(
    patterns: list[str],
    *,
    registry_dir: str | Path | None,
    search_budget: str,
    cwd: str | Path | None,
    limit: int,
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
    for entry in inputs.registry_payload.get("threads") or []:
        if not isinstance(entry, Mapping):
            continue
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
        )
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
    return RegistrySearchEvaluation(
        matches=matches,
        suppressed_matches=suppressed_matches,
        warnings=warnings,
        searched_entry_count=searched_entry_count,
        skipped_entries=skipped_entries,
        skipped_reason_counts=skipped_reason_counts,
        unavailable_source_count=unavailable_source_count,
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


def _render_registry_search_payload(
    inputs: RegistrySearchInput,
    evaluation: RegistrySearchEvaluation,
    *,
    matches: list[dict[str, Any]],
    duplicate_metrics: Mapping[str, int],
    include_paths: bool,
    search_budget: str,
) -> dict[str, Any]:
    first_match = matches[0] if matches else None
    raw_first_match_profile = (
        first_match.get("query_match_profile") if isinstance(first_match, Mapping) else None
    )
    first_match_profile: Mapping[str, Any] = (
        raw_first_match_profile if isinstance(raw_first_match_profile, Mapping) else {}
    )
    first_match_useful = (
        match_is_useful_registry_target(first_match)
        if isinstance(first_match, Mapping)
        else False
    )
    useful_target_hit = bool(first_match and first_match_useful)
    discussion_pointer = discussion_atlas_pointer_for_query(
        inputs.query_text,
        cwd=inputs.registry_root or Path.cwd(),
    )
    discussion_action = discussion_atlas_action(discussion_pointer, query=inputs.query_text)
    actions = registry_search_actions(
        query=inputs.query_text,
        has_matches=bool(matches),
        first_match=matches[0] if matches else None,
        useful_target_hit=useful_target_hit,
        first_match_usefulness_status=(
            "identifier_not_found"
            if first_match_profile.get("exact_identifier_query")
            and not first_match_profile.get("identifier_match")
            else "demoted_artifact"
            if first_match is not None and match_is_demoted_artifact(first_match)
            else "query_anchor_missing"
            if first_match is not None and not first_match_useful
            else "topic_bearing_candidate"
        ),
    )
    if discussion_action:
        actions = [discussion_action, *actions]
    no_phrase_like_matches = (
        bool(inputs.query_gate.get("phrase_like_query"))
        and not matches
        and bool(evaluation.suppressed_matches)
    )
    diagnostic_output = include_paths or search_budget == "deep"
    output_matches = (
        [diagnostic_registry_match(match) for match in matches]
        if diagnostic_output
        else [compact_registry_match(match) for match in matches]
    )
    raw_payload: dict[str, Any] = {
        "kind": "aippocampus_registry_source_search",
        "ok": useful_target_hit,
        "status": (
            "ok"
            if useful_target_hit
            else "identifier_not_found"
            if inputs.query_gate.get("exact_identifier_query")
            else "matches_need_broadened_source_search"
            if matches
            else "no_phrase_like_matches"
            if no_phrase_like_matches
            else "no_matches"
        ),
        "search_scope": "registered_clean_source_and_indexes",
        "scope_description": (
            "registered clean-source/index entries across the local registry; "
            "a miss is not proof that no memory exists"
        ),
        "registry": str(inputs.registry_json),
        "query_text": inputs.query_text,
        "query_terms": inputs.terms if diagnostic_output else None,
        "query_match_gate": inputs.query_gate if diagnostic_output else None,
        "matches": output_matches,
        "match_count": len(matches),
        "useful_target_hit": useful_target_hit,
        "first_match_usefulness": (
            {
                "status": "demoted_artifact"
                if first_match is not None and match_is_demoted_artifact(first_match)
                else "identifier_not_found"
                if first_match_profile.get("exact_identifier_query")
                and not first_match_profile.get("identifier_match")
                else "query_anchor_missing"
                if not first_match_useful
                else "topic_bearing_candidate",
                "artifact_role": first_match.get("artifact_role") if first_match else None,
                "first_hit_demoted": bool(
                    first_match is not None and match_is_demoted_artifact(first_match)
                ),
                "matched_distinctive_anchor_count": first_match_profile.get(
                    "matched_distinctive_anchor_count"
                ),
            }
            if first_match
            else None
        ),
        "duplicate_cluster_count": duplicate_metrics["duplicate_cluster_count"],
        "duplicate_collapsed_hit_count": duplicate_metrics["duplicate_hit_count"],
        "repo_doc_match_count": len(inputs.repo_doc_matches),
        "discussion_atlas_pointer": discussion_pointer,
        "suppressed_low_coverage_match_count": len(evaluation.suppressed_matches),
        "match_evidence_diagnostics": (
            match_evidence_diagnostics(
                matches,
                query_text=inputs.query_text,
                suppressed_count=len(evaluation.suppressed_matches),
            )
            if diagnostic_output
            else None
        ),
        "suppressed_low_coverage_matches": (
            evaluation.suppressed_matches[:3] if diagnostic_output else None
        ),
        "searched_entry_count": evaluation.searched_entry_count,
        "skipped_entry_count": len(evaluation.skipped_entries),
        "skipped_reason_counts": evaluation.skipped_reason_counts or None,
        "skipped_entries": evaluation.skipped_entries[:20] if diagnostic_output else None,
        "maintenance_actions": skipped_maintenance_actions(evaluation.skipped_entries) or None,
        "unavailable_source_count": evaluation.unavailable_source_count,
        "warnings": evaluation.warnings,
        "diagnostic_fields_omitted": (
            [
                "query_terms",
                "query_match_gate",
                "matches[].score",
                "matches[].query_match_profile",
                "suppressed_low_coverage_matches",
                "skipped_entries",
            ]
            if not diagnostic_output
            else None
        ),
        "diagnostic_detail_command": (
            f"aippocampus search --all {shell_quote(inputs.query_text)} --search-budget deep --json"
            if not diagnostic_output and inputs.query_text
            else None
        ),
        "output_boundary": (
            "local_private_source_routes_with_paths"
            if include_paths
            else "foreground_safe_registry_source_routes"
        ),
        "source_boundary": {
            "authority": "bounded_evidence" if useful_target_hit else "direction_only",
            "registry_wide_search": True,
            "source_backed_claim_allowed": useful_target_hit,
            "source_reopen_required_before_claim": True,
            "demoted_artifact_matches_are_diagnostic": bool(matches) and not useful_target_hit,
            "search_miss_is_not_absence_of_memory": not bool(matches),
            "phrase_like_low_coverage_suppressed": no_phrase_like_matches,
        },
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_source_snippets_emitted": False,
            "capped_source_snippets_emitted": bool(matches),
            "full_session_metadata_emitted": False,
            "last_search_cache_contains_paths": False,
        },
    }
    payload: dict[str, Any] = {
        key: item for key, item in raw_payload.items() if item not in (None, "", {})
    }
    if actions:
        payload.update(
            canonical_foreground_action_fields(
                actions[0],
                safe_next_actions=actions,
            )
        )
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))


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
    return _render_registry_search_payload(
        inputs,
        evaluation,
        matches=matches,
        duplicate_metrics=duplicate_metrics,
        include_paths=include_paths,
        search_budget=search_budget,
    )
