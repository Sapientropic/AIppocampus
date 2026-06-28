"""Foreground projection for registry-wide source search."""

from __future__ import annotations

# aippocampus-instruction-surface: registry search render owner; compact wording translates search posture without dumping proof fields.
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields, shell_quote
from aippocampus_runtime.foreground_compact_language import (
    compact_details_flag,
    strip_compact_policy_vocabulary,
)
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.artifact_role import match_is_demoted_artifact
from aippocampus_runtime.source.discussion_atlas_pointer import (
    discussion_atlas_action,
    discussion_atlas_pointer_for_query,
)
from aippocampus_runtime.source.registry_search_actions import (
    registry_search_actions,
    registry_search_open_source_action,
)
from aippocampus_runtime.source.registry_search_duplicates import (
    compact_registry_match,
    diagnostic_registry_match,
)
from aippocampus_runtime.source.registry_search_evidence import (
    first_match_usefulness_status,
    match_evidence_diagnostics,
    match_has_direct_source_open_route,
    match_is_useful_registry_target,
    suppressed_match_state,
)
from aippocampus_runtime.source.registry_search_skips import skipped_maintenance_actions

AnnotateReopenCommands = Callable[..., None]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _best_useful_registry_match(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    for match in matches:
        if match_is_useful_registry_target(match):
            return match
    return None


def _source_cluster_key(match: Mapping[str, Any]) -> str:
    route_value = match.get("source_route")
    route: Mapping[str, Any] = route_value if isinstance(route_value, Mapping) else {}
    thread_key = str(route.get("thread_key") or "").strip()
    if not thread_key:
        thread = match.get("thread")
        thread_map = thread if isinstance(thread, Mapping) else {}
        thread_key = str(thread_map.get("thread_key") or "").strip()
    if not thread_key:
        return ""
    message_id = str(route.get("message_id") or match.get("message_id") or "").strip()
    line = str(route.get("line") or match.get("line") or "").strip()
    return "|".join(part for part in (thread_key, message_id or line) if part)


def _source_cluster_counts(matches: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in matches:
        key = _source_cluster_key(match)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _is_low_confidence_reopen_candidate(
    match: Mapping[str, Any],
    *,
    cluster_count: int,
) -> bool:
    """Decide whether a suppressed hit can be foreground navigation.

    This is deliberately stricter than "has a high score": exact identifiers
    must never open fuzzy matches, artifacts stay diagnostic, and a near hit
    must either carry several query anchors or be reinforced by another hit in
    the same source route. The result is still navigation-only until opened.
    """

    if match_is_demoted_artifact(match) or not match_has_direct_source_open_route(match):
        return False
    profile_value = match.get("query_match_profile")
    profile: Mapping[str, Any] = profile_value if isinstance(profile_value, Mapping) else {}
    if profile.get("exact_identifier_query") and not profile.get("identifier_match"):
        return False
    matched_count = _as_int(profile.get("matched_distinctive_anchor_count"))
    coverage = _as_float(profile.get("distinctive_anchor_coverage"))
    if profile.get("exact_phrase_match"):
        return True
    if matched_count >= 2 and coverage >= 0.5:
        return True
    return cluster_count >= 2 and matched_count >= 1 and coverage >= 0.25


def _query_match_profile(match: Mapping[str, Any]) -> Mapping[str, Any]:
    profile = match.get("query_match_profile")
    return profile if isinstance(profile, Mapping) else {}


def _low_confidence_reopen_matches(
    suppressed_matches: list[dict[str, Any]],
    *,
    registry_root: Path | None,
    include_paths: bool,
    annotate_reopen_commands: AnnotateReopenCommands,
    limit: int = 1,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    cluster_counts = _source_cluster_counts(suppressed_matches)
    sorted_matches = sorted(
        suppressed_matches,
        key=lambda match: (
            -_as_int(_query_match_profile(match).get("matched_distinctive_anchor_count")),
            -_as_float(_query_match_profile(match).get("distinctive_anchor_coverage")),
            -cluster_counts.get(_source_cluster_key(match), 0),
            -_as_float(match.get("score")),
        ),
    )
    for match in sorted_matches:
        if not _is_low_confidence_reopen_candidate(
            match,
            cluster_count=cluster_counts.get(_source_cluster_key(match), 0),
        ):
            continue
        candidate = dict(match)
        candidate["candidate_kind"] = "low_confidence_reopen_candidate"
        candidate["claim_boundary"] = "near_hit_navigation_only_no_claim"
        annotate_reopen_commands(
            [candidate],
            registry_dir=registry_root,
            include_paths=include_paths,
        )
        if str(candidate.get("reopen_command") or "").strip():
            candidates.append(candidate)
        if len(candidates) >= limit:
            break
    return candidates


def _semantic_position_reopen_matches(
    evaluation: Any,
    *,
    inputs: Any,
    include_paths: bool,
    annotate_reopen_commands: AnnotateReopenCommands,
) -> list[dict[str, Any]]:
    matches = [
        dict(match)
        for match in getattr(evaluation, "semantic_position_candidates", []) or []
        if isinstance(match, Mapping)
    ][:1]
    if not matches:
        return []
    annotate_reopen_commands(
        matches,
        registry_dir=inputs.registry_root,
        include_paths=include_paths,
    )
    return [match for match in matches if str(match.get("reopen_command") or "").strip()]


def _semantic_position_open_action(
    *,
    inputs: Any,
    matches: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not matches:
        return None
    return registry_search_open_source_action(
        query=inputs.query_text,
        match=matches[0],
        action_id="inspect_recall_semantic_position_source",
        label="Inspect the positioned current-thread source",
        why=(
            "A prior explicit recall cue positioned this thread for these terms. "
            "Open the source as navigation, not proof."
        ),
        claim_boundary="semantic_positioning_navigation_only_no_claim",
    )


def _registry_search_status(
    *,
    useful_target_hit: bool,
    low_confidence_matches: list[dict[str, Any]],
    semantic_position_matches: list[dict[str, Any]],
    exact_identifier_query: bool,
    no_phrase_like_matches: bool,
    matches: list[dict[str, Any]],
    low_coverage_only_matches: bool,
) -> str:
    if useful_target_hit:
        return "ok"
    if low_confidence_matches:
        return "low_confidence_reopen_candidate"
    if semantic_position_matches:
        return "recall_semantic_position_candidate"
    if exact_identifier_query:
        return "identifier_not_found"
    if no_phrase_like_matches:
        return "no_phrase_like_matches"
    if matches or low_coverage_only_matches:
        return "matches_need_broadened_source_search"
    return "no_matches"


def _registry_search_boundaries(
    *,
    useful_target_hit: bool,
    low_confidence_matches: list[dict[str, Any]],
    semantic_position_matches: list[dict[str, Any]],
) -> tuple[str, str]:
    if useful_target_hit:
        return "source_reopen_required_before_claim", "reopen_selected_registry_hit_before_claim"
    if low_confidence_matches:
        return (
            "near_hit_navigation_only_no_claim",
            "open_low_confidence_near_hit_as_navigation_before_claim",
        )
    if semantic_position_matches:
        return (
            "semantic_positioning_navigation_only_no_claim",
            "open_semantic_positioning_source_as_navigation_before_claim",
        )
    return "search_miss_is_not_absence_of_memory", "search_miss_is_not_absence_of_memory"


def _registry_source_boundary(
    *,
    useful_target_hit: bool,
    low_confidence_matches: list[dict[str, Any]],
    semantic_position_matches: list[dict[str, Any]],
    evaluation: Any,
    matches: list[dict[str, Any]],
    low_coverage_only_matches: bool,
    no_phrase_like_matches: bool,
) -> dict[str, Any]:
    return {
        "authority": "bounded_evidence" if useful_target_hit else "direction_only",
        "registry_wide_search": True,
        "source_backed_claim_allowed": useful_target_hit,
        "source_reopen_required_before_claim": True,
        "low_confidence_reopen_candidate": bool(low_confidence_matches),
        "recall_semantic_position_candidate": bool(semantic_position_matches),
        "partial_search_results": evaluation.budget_exhausted,
        "demoted_artifact_matches_are_diagnostic": bool(matches) and not useful_target_hit,
        "search_miss_is_not_absence_of_memory": not bool(matches),
        "low_coverage_matches_suppressed": low_coverage_only_matches,
        "phrase_like_low_coverage_suppressed": no_phrase_like_matches,
    }


def _first_match_usefulness_payload(
    *,
    first_match: Mapping[str, Any] | None,
    first_match_status: str,
    first_match_profile: Mapping[str, Any],
    diagnostic_output: bool,
) -> dict[str, Any] | None:
    if first_match is None:
        return None
    payload = {
        "status": first_match_status,
        "first_hit_demoted": match_is_demoted_artifact(first_match),
        "matched_distinctive_anchor_count": first_match_profile.get(
            "matched_distinctive_anchor_count"
        ),
    }
    if diagnostic_output:
        payload["artifact_role"] = first_match.get("artifact_role")
    return payload


def _registry_search_raw_payload(
    *,
    inputs: Any,
    evaluation: Any,
    matches: list[dict[str, Any]],
    duplicate_metrics: Mapping[str, int],
    include_paths: bool,
    diagnostic_output: bool,
    detail_command: str | None,
    output_matches: list[dict[str, Any]],
    useful_target_hit: bool,
    low_confidence_matches: list[dict[str, Any]],
    semantic_position_matches: list[dict[str, Any]],
    no_phrase_like_matches: bool,
    low_coverage_only_matches: bool,
    first_match: Mapping[str, Any] | None,
    first_match_profile: Mapping[str, Any],
    first_match_status: str,
    discussion_pointer: dict[str, Any] | None,
    next_reopen_command: str,
    claim_boundary: str,
    source_reopen_boundary: str,
) -> dict[str, Any]:
    return {
        "kind": "aippocampus_registry_source_search",
        "ok": useful_target_hit,
        "status": _registry_search_status(
            useful_target_hit=useful_target_hit,
            low_confidence_matches=low_confidence_matches,
            semantic_position_matches=semantic_position_matches,
            exact_identifier_query=bool(inputs.query_gate.get("exact_identifier_query")),
            no_phrase_like_matches=no_phrase_like_matches,
            matches=matches,
            low_coverage_only_matches=low_coverage_only_matches,
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
        "partial": True if evaluation.budget_exhausted else None,
        "degraded_reason": (
            "foreground_search_time_budget_exhausted" if evaluation.budget_exhausted else None
        ),
        "max_elapsed_ms": evaluation.max_elapsed_ms,
        "elapsed_ms": evaluation.elapsed_ms,
        "unsearched_entry_count": (
            evaluation.unsearched_entry_count if evaluation.budget_exhausted else None
        ),
        "next_precise_reopen_command": (
            next_reopen_command if evaluation.budget_exhausted and next_reopen_command else None
        ),
        "first_match_usefulness": _first_match_usefulness_payload(
            first_match=first_match,
            first_match_status=first_match_status,
            first_match_profile=first_match_profile,
            diagnostic_output=diagnostic_output,
        ),
        "duplicate_cluster_count": duplicate_metrics["duplicate_cluster_count"],
        "duplicate_collapsed_hit_count": duplicate_metrics["duplicate_hit_count"],
        "repo_doc_match_count": len(inputs.repo_doc_matches),
        "discussion_atlas_pointer": discussion_pointer,
        "suppressed_low_coverage_match_count": len(evaluation.suppressed_matches),
        "low_confidence_reopen_candidates": (
            [compact_registry_match(match) for match in low_confidence_matches]
            if low_confidence_matches
            else None
        ),
        "recall_semantic_position_candidates": (
            [diagnostic_registry_match(match) for match in semantic_position_matches]
            if diagnostic_output and semantic_position_matches
            else None
        ),
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
        "diagnostic_fields_omitted": None,
        "diagnostic_detail_command": None,
        "detail_command": detail_command if not diagnostic_output else None,
        "claim_boundary": claim_boundary,
        "source_reopen_boundary": source_reopen_boundary,
        "suppression_boundary": (
            "phrase_like_low_coverage_suppressed"
            if no_phrase_like_matches
            else "low_coverage_matches_suppressed"
            if low_coverage_only_matches
            else None
        ),
        "output_boundary": (
            "local_private_source_routes_with_paths"
            if include_paths
            else "foreground_safe_registry_source_routes"
        ),
        "source_boundary": (
            _registry_source_boundary(
                useful_target_hit=useful_target_hit,
                low_confidence_matches=low_confidence_matches,
                semantic_position_matches=semantic_position_matches,
                evaluation=evaluation,
                matches=matches,
                low_coverage_only_matches=low_coverage_only_matches,
                no_phrase_like_matches=no_phrase_like_matches,
            )
            if diagnostic_output
            else None
        ),
        "privacy": (
            {
                "paths_included": include_paths,
                "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
                "raw_source_snippets_emitted": False,
                "capped_source_snippets_emitted": bool(matches),
                "full_session_metadata_emitted": False,
                "last_search_cache_contains_paths": False,
            }
            if diagnostic_output
            else None
        ),
    }


def render_registry_search_payload(
    inputs: Any,
    evaluation: Any,
    *,
    matches: list[dict[str, Any]],
    duplicate_metrics: Mapping[str, int],
    include_paths: bool,
    search_budget: str,
    annotate_reopen_commands: AnnotateReopenCommands,
) -> dict[str, Any]:
    first_match = matches[0] if matches else None
    raw_profile = first_match.get("query_match_profile") if isinstance(first_match, Mapping) else None
    first_match_profile: Mapping[str, Any] = raw_profile if isinstance(raw_profile, Mapping) else {}
    first_match_useful = (
        match_is_useful_registry_target(first_match)
        if isinstance(first_match, Mapping)
        else False
    )
    foreground_match = _best_useful_registry_match(matches) or first_match
    useful_target_hit = bool(
        foreground_match
        and isinstance(foreground_match, Mapping)
        and match_is_useful_registry_target(foreground_match)
    )
    no_phrase_like_matches, low_coverage_only_matches = suppressed_match_state(
        phrase_like_query=bool(inputs.query_gate.get("phrase_like_query")),
        visible_match_count=len(matches),
        suppressed_match_count=len(evaluation.suppressed_matches),
    )
    first_match_status = first_match_usefulness_status(
        first_match,
        first_match_profile=first_match_profile,
        first_match_useful=first_match_useful,
        low_coverage_only_matches=low_coverage_only_matches,
    )
    discussion_pointer = discussion_atlas_pointer_for_query(
        inputs.query_text,
        cwd=inputs.registry_root or Path.cwd(),
    )
    discussion_action = discussion_atlas_action(discussion_pointer, query=inputs.query_text)
    actions = registry_search_actions(
        query=inputs.query_text,
        has_matches=bool(matches),
        first_match=foreground_match,
        useful_target_hit=useful_target_hit,
        first_match_usefulness_status=first_match_status,
        low_coverage_only_matches=low_coverage_only_matches,
    )
    # Exact phrase-like misses are a strong foreground signal: if no visible
    # match preserved enough query coverage, do not promote generic suppressed
    # rows into a "near hit" just because they are reopenable.
    low_confidence_matches = (
        []
        if no_phrase_like_matches
        else _low_confidence_reopen_matches(
            evaluation.suppressed_matches,
            registry_root=inputs.registry_root,
            include_paths=include_paths,
            annotate_reopen_commands=annotate_reopen_commands,
        )
    )
    semantic_position_matches = _semantic_position_reopen_matches(
        evaluation,
        inputs=inputs,
        include_paths=include_paths,
        annotate_reopen_commands=annotate_reopen_commands,
    )
    if low_confidence_matches and not useful_target_hit:
        near_hit_action = registry_search_open_source_action(
            query=inputs.query_text,
            match=low_confidence_matches[0],
            action_id="inspect_low_confidence_registry_near_hit",
            label="Inspect a low-confidence near-hit source",
            why=(
                "No target-evidence hit passed the phrase gate, but one nearby "
                "source can be reopened as navigation. Treat it as orientation only."
            ),
            claim_boundary="near_hit_navigation_only_no_claim",
        )
        if near_hit_action:
            actions = [near_hit_action, *actions]
    if semantic_position_matches and not useful_target_hit:
        semantic_position_action = _semantic_position_open_action(
            inputs=inputs,
            matches=semantic_position_matches,
        )
        if semantic_position_action:
            actions = [semantic_position_action, *actions]
    if discussion_action:
        actions = [discussion_action, *actions]

    diagnostic_output = include_paths or search_budget == "deep"
    detail_command = (
        f"aippocampus search --all {shell_quote(inputs.query_text)} "
        "--search-budget deep --json --max-elapsed-ms 15000"
        if not diagnostic_output and inputs.query_text
        else None
    )
    output_matches = (
        [diagnostic_registry_match(match) for match in matches]
        if diagnostic_output
        else [compact_registry_match(match) for match in matches]
    )
    next_reopen_command = str((actions[0] if actions else {}).get("command") or "")
    claim_boundary, source_reopen_boundary = _registry_search_boundaries(
        useful_target_hit=useful_target_hit,
        low_confidence_matches=low_confidence_matches,
        semantic_position_matches=semantic_position_matches,
    )
    raw_payload = _registry_search_raw_payload(
        inputs=inputs,
        evaluation=evaluation,
        matches=matches,
        duplicate_metrics=duplicate_metrics,
        include_paths=include_paths,
        diagnostic_output=diagnostic_output,
        detail_command=detail_command,
        output_matches=output_matches,
        useful_target_hit=useful_target_hit,
        low_confidence_matches=low_confidence_matches,
        semantic_position_matches=semantic_position_matches,
        no_phrase_like_matches=no_phrase_like_matches,
        low_coverage_only_matches=low_coverage_only_matches,
        first_match=first_match,
        first_match_profile=first_match_profile,
        first_match_status=first_match_status,
        discussion_pointer=discussion_pointer,
        next_reopen_command=next_reopen_command,
        claim_boundary=claim_boundary,
        source_reopen_boundary=source_reopen_boundary,
    )
    payload = {key: item for key, item in raw_payload.items() if item not in (None, "", {})}
    if actions:
        payload.update(
            canonical_foreground_action_fields(
                actions[0],
                safe_next_actions=actions,
                max_safe_next_actions=1,
                safe_next_read_only_only=True,
            )
        )
    if not diagnostic_output:
        payload.update(compact_details_flag(payload))
        payload = strip_compact_policy_vocabulary(payload)
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))
