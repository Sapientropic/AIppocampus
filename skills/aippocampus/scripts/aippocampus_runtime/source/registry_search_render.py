"""Foreground projection for registry-wide source search."""

from __future__ import annotations

# aippocampus-instruction-surface: registry search render owner; compact wording translates search posture without dumping proof fields.
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields, shell_quote
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


def _low_confidence_reopen_matches(
    suppressed_matches: list[dict[str, Any]],
    *,
    registry_root: Path | None,
    include_paths: bool,
    annotate_reopen_commands: AnnotateReopenCommands,
    limit: int = 1,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for match in suppressed_matches:
        if match_is_demoted_artifact(match) or not match_has_direct_source_open_route(match):
            continue
        profile_value = match.get("query_match_profile")
        profile: Mapping[str, Any] = profile_value if isinstance(profile_value, Mapping) else {}
        matched_count = _as_int(profile.get("matched_distinctive_anchor_count"))
        coverage = _as_float(profile.get("distinctive_anchor_coverage"))
        if not profile.get("exact_phrase_match") and matched_count < 2 and coverage < 0.5:
            continue
        candidate = dict(match)
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
    low_confidence_matches = _low_confidence_reopen_matches(
        evaluation.suppressed_matches,
        registry_root=inputs.registry_root,
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
    raw_payload: dict[str, Any] = {
        "kind": "aippocampus_registry_source_search",
        "ok": useful_target_hit,
        "status": (
            "ok"
            if useful_target_hit
            else "identifier_not_found"
            if inputs.query_gate.get("exact_identifier_query")
            else "no_phrase_like_matches"
            if no_phrase_like_matches
            else "matches_need_broadened_source_search"
            if matches or low_coverage_only_matches
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
        "first_match_usefulness": (
            {
                "status": first_match_status,
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
        "low_confidence_reopen_candidates": (
            [compact_registry_match(match) for match in low_confidence_matches]
            if low_confidence_matches
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
        "claim_boundary": (
            "source_reopen_required_before_claim"
            if useful_target_hit
            else "search_miss_is_not_absence_of_memory"
        ),
        "source_reopen_boundary": (
            "reopen_selected_registry_hit_before_claim"
            if useful_target_hit
            else "search_miss_is_not_absence_of_memory"
        ),
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
            {
                "authority": "bounded_evidence" if useful_target_hit else "direction_only",
                "registry_wide_search": True,
                "source_backed_claim_allowed": useful_target_hit,
                "source_reopen_required_before_claim": True,
                "partial_search_results": evaluation.budget_exhausted,
                "demoted_artifact_matches_are_diagnostic": bool(matches) and not useful_target_hit,
                "search_miss_is_not_absence_of_memory": not bool(matches),
                "low_coverage_matches_suppressed": low_coverage_only_matches,
                "phrase_like_low_coverage_suppressed": no_phrase_like_matches,
            }
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
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))
