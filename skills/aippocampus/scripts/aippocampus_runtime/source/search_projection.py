"""Foreground authority projection for clean-source search results."""

from __future__ import annotations

# aippocampus-instruction-surface: clean-source search projection owner; boundary text stays in projection/detail lanes, not hidden agent instructions.
from typing import Any

from aippocampus_runtime.contracts import shell_quote
from aippocampus_runtime.source.artifact_role import match_is_demoted_artifact


def _query_text(query_terms: list[str], query_text: str | None) -> str:
    explicit = str(query_text or "").strip()
    if explicit:
        return explicit
    return " ".join(str(term) for term in query_terms if str(term).strip()).strip()


def _first_match_selector(matches: list[dict[str, Any]]) -> dict[str, Any]:
    if not matches:
        return {}
    first = matches[0]
    for key in ("message_id", "id", "turn_id", "turn_index"):
        value = first.get(key)
        if value not in (None, ""):
            return {key: value}
    return {}


def search_foreground_authority(
    *,
    matches: list[dict[str, Any]],
    query_terms: list[str],
    metadata_only: bool,
    query_text: str | None = None,
) -> dict[str, Any]:
    """Project clean-source search into the shared foreground authority posture.

    Search may expose local snippets in CLI JSON, or metadata-only cards through
    public/MCP surfaces. Both are useful first-touch routes, but neither should
    be mistaken for permission to quote or make broad claims without reopening
    the clean source window. Keep the action machine-readable so foreground
    agents do not have to parse prose like "reopen before quoting".
    """

    query = _query_text(query_terms, query_text)
    has_matches = bool(matches)
    useful_target_hit = bool(matches) and not match_is_demoted_artifact(matches[0])
    first_hit_profile = (
        {
            "status": "demoted_artifact" if not useful_target_hit else "topic_bearing_candidate",
            "artifact_role": matches[0].get("artifact_role") if matches else None,
            "first_hit_demoted": bool(matches and match_is_demoted_artifact(matches[0])),
        }
        if matches
        else {}
    )
    if has_matches and not useful_target_hit:
        return {
            "kind": "aippocampus_search_result",
            "ok": False,
            "status": "matches_need_broadened_source_search",
            "entry_state": "explicit_search_invoked",
            "route_state": "no_useful_target_hit",
            "usefulness": "needs_broadened_source_search",
            "useful_target_hit": False,
            "first_match_usefulness": first_hit_profile,
            "claim_permission": "no_claim_before_topic_bearing_source",
            "source_boundary": {
                "authority": "direction_only",
                "source_backed_claim_allowed": False,
                "source_reopen_required_before_claim": True,
                "demoted_artifact_matches_remain_diagnostic": True,
            },
            "foreground_action": {
                "action_id": "broaden_source_search_for_topic_bearing_hit",
                "label": "Broaden source search",
                "tool_name": "search_memory",
                "arguments": {
                    "query": query or "distinctive old source cue",
                    "scope": "all_registered_sources",
                    "max": 5,
                },
                "mutation_risk": "read_only",
                "claim_boundary": "search_hit_not_yet_topic_bearing_source",
                "why": (
                    "Search found validation, fixture, or closeout material that repeats "
                    "the cue; find a topic-bearing source before relying on it."
                ),
            },
            "forbidden_claims": [
                "source-backed fact from demoted artifact",
                "exact wording beyond diagnostic artifact",
                "absence of topic-bearing source",
            ],
        }
    if has_matches and metadata_only:
        local_search_command = (
            f"aippocampus search {shell_quote(query)} --json --detail full"
            if query
            else "aippocampus search \"<distinctive old source cue>\" --json --detail full"
        )
        return {
            "kind": "aippocampus_search_result",
            "ok": True,
            "status": "ok",
            "entry_state": "explicit_search_invoked",
            "route_state": "metadata_only_needs_local_source_refs",
            "usefulness": "useful_for_next_action",
            "useful_target_hit": True,
            "first_match_usefulness": first_hit_profile,
            "claim_permission": "capped_search_snippet_no_claim_before_reopen",
            "source_boundary": {
                "authority": "reopenable_route",
                "source_backed_claim_allowed": False,
                "metadata_only": True,
                "capped_snippets_are_bounded_receipts": True,
                "source_reopen_required_before_claim": True,
                "snippets_are_source_open": False,
            },
            "foreground_action": {
                "action_id": "rerun_search_with_local_source_refs",
                "label": "Rerun locally with source refs",
                "tool_name": "search_memory",
                "arguments": {
                    "query": query or "distinctive old source cue",
                    "scope": "current_thread_clean_source",
                    "detail": "full",
                },
                "command": local_search_command,
                "cli_equivalent_for_tool_action": True,
                "mutation_risk": "read_only",
                "claim_boundary": "metadata_only_no_private_reopen_refs",
                "why": (
                    "Public metadata found a capped receipt but withheld private "
                    "source refs; rerun locally before quoting or relying on exact wording."
                ),
            },
            "forbidden_claims": [
                "exact wording",
                "sensitive/stale/disputed facts",
                "absence of other source matches",
            ],
        }
    if has_matches:
        return {
            "kind": "aippocampus_search_result",
            "ok": True,
            "status": "ok",
            "entry_state": "explicit_search_invoked",
            "route_state": "source_refs_available",
            "usefulness": "useful_for_next_action",
            "useful_target_hit": True,
            "first_match_usefulness": first_hit_profile,
            "claim_permission": "bounded_search_receipt_requires_reopen",
            "source_boundary": {
                "authority": "bounded_evidence",
                "source_backed_claim_allowed": True,
                "metadata_only": False,
                "source_reopen_required_before_claim": True,
                "snippets_are_bounded_receipts": True,
            },
            "foreground_action": {
                "action_id": "reopen_search_match_source",
                "label": "Reopen the first search match",
                "tool_name": "get_turn_context",
                "arguments": _first_match_selector(matches),
                "command": str(matches[0].get("reopen_command") or "").strip(),
                "cli_equivalent_for_tool_action": True,
                "mutation_risk": "read_only",
                "claim_boundary": "source_reopen_required_before_claim",
                "why": (
                    "Use the selected clean-source match as a route, then reopen "
                    "the surrounding turn before quoting or making strong claims."
                ),
            },
            "forbidden_claims": [
                "exact wording beyond the emitted snippet",
                "sensitive/stale/disputed facts",
                "absence of other source matches",
            ],
        }
    return {
        "kind": "aippocampus_search_result",
        "ok": False,
        "status": "no_matches",
        "entry_state": "explicit_search_invoked",
        "route_state": "no_useful_route",
        "usefulness": "needs_refined_cue",
        "claim_permission": "no_claim_before_source_match",
        "source_boundary": {
            "authority": "direction_only",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claim": True,
            "search_miss_is_not_absence_of_memory": True,
        },
        "foreground_action": {
            "action_id": "refine_or_recall",
            "label": "Refine the cue or use recall",
            "tool_name": "agent_recall",
            "arguments": {"query": query or "old decision or handoff cue"},
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
            "why": (
                "Search found no source-backed snippet; use a richer continuity "
                "cue or exact wording before claiming from memory."
            ),
        },
        "forbidden_claims": [
            "source-backed fact",
            "absence of memory",
            "exact wording",
        ],
    }
