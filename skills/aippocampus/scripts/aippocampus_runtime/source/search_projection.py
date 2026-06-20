"""Foreground authority projection for clean-source search results."""

from __future__ import annotations

from typing import Any


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
    if has_matches and metadata_only:
        return {
            "kind": "aippocampus_search_result",
            "ok": True,
            "status": "ok",
            "entry_state": "explicit_search_invoked",
            "route_state": "reopenable_route",
            "usefulness": "useful_for_next_action",
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
                "action_id": "recall_context_from_search",
                "label": "Recall context from search match",
                "tool_name": "recall_context",
                "arguments": {"intent": query, "max": min(max(len(matches), 1), 5)},
                "mutation_risk": "read_only",
                "claim_boundary": "source_reopen_required_before_claim",
                "why": (
                    "Capped search snippet found matching clean-source wording; "
                    "reopen context before quoting or relying on exact wording."
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
