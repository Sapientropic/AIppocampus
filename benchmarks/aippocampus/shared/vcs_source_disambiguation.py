"""Source-disambiguation actionability helpers for the VCS recall benchmark."""

from __future__ import annotations

from typing import Any

SOURCE_DISAMBIGUATION_INPUT_FIELDS = [
    "future_window.text",
    "future_window.family",
    "future_window.hard_event_kind",
    "past_window.kind",
    "past_window.text",
    "past_window.behavior_backed",
    "past_window.tool_name",
    "past_window.command_class",
    "past_window.failure_family",
]
SUCCESSFUL_CURRENT_EVENT_KINDS = {"test_passed", "tool_call_succeeded"}
NEAR_MISS_MARKERS = ("near-miss", "near miss")


def retrieval_text_for_event(event: dict[str, Any]) -> str:
    # Do not include expected_signal, flag_worthy, or required_past_source_ids.
    # The production-like arm receives the future event surface, not the grader.
    return " ".join(
        str(field or "")
        for field in (
            event.get("text"),
            event.get("family"),
            event.get("hard_event_kind"),
        )
    )


def event_requests_current_source(event: dict[str, Any]) -> bool:
    text = retrieval_text_for_event(event).casefold()
    return any(
        marker in text
        for marker in (
            "current",
            "effective",
            "override",
            "overrides",
            "overridden",
            "newer",
            "active",
        )
    )


def event_requests_behavior_source(event: dict[str, Any]) -> bool:
    text = retrieval_text_for_event(event).casefold()
    return any(
        marker in text
        for marker in (
            "behavior",
            "failed",
            "failure",
            "test_failed",
            "tool_call_failed",
            "edit_reverted",
            "route_abandoned",
        )
    )


def event_has_unsupported_signal(event: dict[str, Any]) -> bool:
    text = retrieval_text_for_event(event).casefold()
    return any(
        marker in text
        for marker in (
            "unsupported",
            "no source-backed",
            "without support",
            "unrelated",
            "similar surface",
            "weak related",
            "narrative-only",
            "successful tool behavior",
            "docs-only",
        )
    )


def hard_negative_subtype_for_event(event: dict[str, Any]) -> str:
    text = retrieval_text_for_event(event).casefold()
    if not any(marker in text for marker in NEAR_MISS_MARKERS):
        return ""
    if "stale-current" in text or ("old source" in text and "current" in text):
        return "stale_current_lure"
    if "wrong-stance" in text or "opposite stance" in text:
        return "wrong_stance_lure"
    if "lexical recap" in text or (
        "recap" in text and ("without source-backed" in text or "summary-like" in text)
    ):
        return "lexical_recap_lure"
    if any(
        marker in text
        for marker in (
            "not support",
            "same token",
            "shares",
            "without source-backed",
            "without support",
        )
    ):
        return "lexical_near_miss_lure"
    return ""


def event_is_successful_current_event(event: dict[str, Any]) -> bool:
    return str(event.get("hard_event_kind") or "").casefold() in SUCCESSFUL_CURRENT_EVENT_KINDS


def route_candidate_from_ranked_sources(
    *,
    event: dict[str, Any],
    ranked_sources: list[dict[str, Any]],
    min_score: float,
) -> tuple[bool, str]:
    if not ranked_sources:
        return False, "no_ranked_sources"
    top = ranked_sources[0]
    if float(top["score"]) < min_score:
        return False, "below_min_score"
    if event_has_unsupported_signal(event):
        return False, "unsupported_signal"
    hard_negative_subtype = hard_negative_subtype_for_event(event)
    if hard_negative_subtype:
        return False, f"hard_negative:{hard_negative_subtype}"
    top_kind = str(top.get("kind") or "").casefold()
    if top_kind in {"weak_related_source", "assistant_message"}:
        return False, "weak_or_narrative_source"
    if top.get("behavior_backed") is False and event_requests_behavior_source(event):
        return False, "behavior_source_required"
    return True, "route_candidate"


def route_actionability_for_event(
    *,
    event: dict[str, Any],
    route_candidate: bool,
    candidate_reason: str,
) -> dict[str, Any]:
    if not route_candidate:
        return {
            "decision": "suppress",
            "reason": candidate_reason,
            "foreground_visible": False,
        }
    # A successful current event may still retrieve the old failed route for
    # diagnosis. It must not become a foreground warning/action route unless a
    # separate source-backed currentness rule says the old failure still applies.
    if event_is_successful_current_event(event):
        return {
            "decision": "suppress",
            "reason": "successful_current_event",
            "foreground_visible": False,
        }
    return {
        "decision": "flag",
        "reason": "source_route_actionable",
        "foreground_visible": True,
    }


def should_flag_from_ranked_sources(
    *,
    event: dict[str, Any],
    ranked_sources: list[dict[str, Any]],
    min_score: float,
) -> bool:
    route_candidate, candidate_reason = route_candidate_from_ranked_sources(
        event=event,
        ranked_sources=ranked_sources,
        min_score=min_score,
    )
    actionability = route_actionability_for_event(
        event=event,
        route_candidate=route_candidate,
        candidate_reason=candidate_reason,
    )
    return str(actionability["decision"]) == "flag"
