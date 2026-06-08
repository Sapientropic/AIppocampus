#!/usr/bin/env python3
"""Public-safe #797 fixtures for presence-first recall behavior."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.recall import authority
from aippocampus_runtime.recall.prompt_context_render import context_for_hook


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ambient_context_for_cards(cards: Sequence[Mapping[str, Any]]) -> str:
    return context_for_hook(
        {
            "decision": "scent",
            "ambient_recall": {
                "mode": "silent_tuning",
                "cards": [dict(card) for card in cards],
            },
        }
    ) or ""


def _old_everything_is_scent_baseline(surface: Mapping[str, Any]) -> dict[str, Any]:
    """Model the old unsafe simplification #797 guards against.

    The baseline deliberately strips route, refs, and reopened-source markers
    before mapping authority. If this ever starts passing bounded evidence or
    source-court cases, the fixture stopped protecting the product semantics.
    """

    clean = {
        key: value
        for key, value in surface.items()
        if key
        not in {
            "action_grammar",
            "authority_state",
            "candidate_refs",
            "evidence_level",
            "reopen_plan",
            "route",
            "source_boundary",
            "source_refs",
            "source_reopen_required",
            "trust_contract",
            "trust_level",
            "visibility",
        }
    }
    clean["support_level"] = "scent"
    clean["provenance_class"] = "cached_warm_card"
    clean["visibility"] = "silent_tuning"
    return authority.with_trust_fields(clean)


def fixture_presence_first_matrix() -> dict[str, Any]:
    """Public-safe #797 fixture matrix over the presence-first foreground layers."""

    atmosphere = authority.with_authority_fields(
        {
            "support_level": "scent",
            "provenance_class": "cached_warm_card",
            "visibility": "silent_tuning",
            "theme": "Prior work felt emotionally important but has no source claim yet",
            "suggested_use": "Let it orient attention quietly; do not state it as fact.",
        }
    )
    continuity = authority.with_authority_fields(
        {
            "support_level": "source_required",
            "route": "reopen",
            "provenance_class": "source_backed_reopen",
            "visibility": "foreground",
            "theme": "Resume the public fixture by reopening the routed source ref",
            "suggested_use": "Use the route as the next action, not as evidence.",
            "source_refs": [
                {"thread_key": "public-fixture-continuity", "line": 12}
            ],
            "reopen_plan": {
                "status": "ready",
                "manual_query_invention_expected": False,
            },
        }
    )
    bounded = authority.with_authority_fields(
        {
            "support_level": "evidence",
            "evidence_level": "source_backed",
            "provenance_class": "source_backed_reopen",
            "visibility": "foreground",
            "theme": "Bounded public fixture evidence",
            "key_line": "The public fixture can be used within its declared scope.",
            "suggested_use": "Use this within scope; reopen for quotes or wider context.",
            "source_refs": [
                {
                    "thread_key": "public-fixture-continuity",
                    "line": 24,
                    "phase": "final_answer",
                    "turn_index": 3,
                }
            ],
            "source_boundary": {
                "clean_source_reopened": True,
                "cards_are_bounded_source_backed_context": True,
            },
        }
    )
    source_open = authority.with_authority_fields(
        {
            "support_level": "evidence",
            "evidence_level": "raw_source",
            "provenance_class": "source_backed_reopen",
            "visibility": "foreground",
            "theme": "Scoped source-open public fixture",
            "key_line": "Exact wording is available only inside this public fixture scope.",
            "suggested_use": "Use scoped exact wording without widening the claim.",
            "source_refs": [
                {
                    "thread_key": "public-fixture-continuity",
                    "line": 31,
                    "phase": "final_answer",
                    "turn_index": 4,
                }
            ],
            "source_boundary": {
                "clean_source_reopened": True,
                "raw_source_reopened": True,
            },
        }
    )
    source_court = authority.with_authority_fields(
        {
            "support_level": "source_required",
            "route": "reopen",
            "provenance_class": "source_backed_reopen",
            "visibility": "blocked",
            "theme": "Blocked public fixture route",
            "suggested_use": "Escalate or abstain instead of shaping the answer.",
            "source_refs": [
                {"thread_key": "public-fixture-continuity", "line": 44}
            ],
            "reopen_plan": {
                "status": "blocked",
                "reason": "privacy_or_conflict_boundary",
                "manual_query_invention_expected": False,
            },
        }
    )

    atmosphere_contract = _as_dict(atmosphere.get("trust_contract"))
    continuity_contract = _as_dict(continuity.get("trust_contract"))
    bounded_contract = _as_dict(bounded.get("trust_contract"))
    source_open_contract = _as_dict(source_open.get("trust_contract"))
    source_court_contract = _as_dict(source_court.get("trust_contract"))

    atmosphere_context = _ambient_context_for_cards([atmosphere])
    continuity_context = _ambient_context_for_cards([continuity])
    bounded_context = _ambient_context_for_cards([bounded])
    source_open_context = _ambient_context_for_cards([source_open])
    source_court_context = _ambient_context_for_cards([source_court])

    old_atmosphere = _old_everything_is_scent_baseline(atmosphere)
    old_continuity = _old_everything_is_scent_baseline(continuity)
    old_bounded = _old_everything_is_scent_baseline(bounded)
    old_source_open = _old_everything_is_scent_baseline(source_open)
    old_source_court = _old_everything_is_scent_baseline(source_court)

    old_atmosphere_contract = _as_dict(old_atmosphere.get("trust_contract"))
    old_continuity_contract = _as_dict(old_continuity.get("trust_contract"))
    old_bounded_contract = _as_dict(old_bounded.get("trust_contract"))
    old_source_open_contract = _as_dict(old_source_open.get("trust_contract"))

    first_use_copy = (
        "I found the prior route and enough source trail to continue carefully; "
        "I'll reopen exact source only where the claim needs it."
    )
    old_first_use_copy = (
        "I have a memory scent and may need you to tell me the old keywords."
    )

    cases_by_family: dict[str, dict[str, Any]] = {
        "memory_atmosphere": {
            "agent_behavior": "quietly_orients_without_claim",
            "action_grammar": atmosphere.get("action_grammar"),
            "context_layer_seen": (
                "Memory atmosphere" in atmosphere_context
                or "action: direction_only" in atmosphere_context
            ),
            "makes_factual_claim": bool(atmosphere_contract.get("treat_as_fact")),
            "current_posture_pass": bool(
                atmosphere.get("action_grammar") == authority.ACTION_DIRECTION_ONLY
                and not atmosphere_contract.get("treat_as_fact")
                and "action: direction_only" in atmosphere_context
                and "can_use: orientation only" in atmosphere_context
            ),
            "old_posture_pass": bool(
                old_atmosphere.get("action_grammar") == authority.ACTION_DIRECTION_ONLY
                and not old_atmosphere_contract.get("treat_as_fact")
            ),
        },
        "working_continuity_brief": {
            "agent_behavior": "uses_reopenable_route_without_manual_grep",
            "action_grammar": continuity.get("action_grammar"),
            "manual_query_invention_count": int(
                bool(continuity_contract.get("manual_query_invention_expected"))
            ),
            "next_action_changed": bool(
                continuity.get("action_grammar") == authority.ACTION_REOPENABLE_ROUTE
            ),
            "current_posture_pass": bool(
                continuity_contract.get("agent_should_reopen_source")
                and not continuity_contract.get("manual_query_invention_expected")
                and "Working continuity brief" in continuity_context
            ),
            "old_posture_pass": bool(
                old_continuity.get("action_grammar")
                == authority.ACTION_REOPENABLE_ROUTE
                and not old_continuity_contract.get("manual_query_invention_expected")
            ),
        },
        "bounded_evidence": {
            "agent_behavior": "answers_within_scope",
            "action_grammar": bounded.get("action_grammar"),
            "answer_changed_by_memory": bool(
                bounded_contract.get("agent_may_answer_within_scope")
            ),
            "manual_query_required": bool(
                bounded_contract.get("manual_query_invention_expected")
            ),
            "current_posture_pass": bool(
                bounded.get("action_grammar") == authority.ACTION_BOUNDED_EVIDENCE
                and bounded_contract.get("agent_may_answer_within_scope")
                and "bounded source-backed evidence" in bounded_context
            ),
            "old_posture_pass": bool(
                old_bounded_contract.get("agent_may_answer_within_scope")
            ),
        },
        "source_open": {
            "agent_behavior": "uses_scoped_exact_wording",
            "action_grammar": source_open.get("action_grammar"),
            "exact_wording_allowed": bool(
                source_open_contract.get("agent_may_quote_exact_wording")
            ),
            "requires_reopen_for_exact_wording": bool(
                source_open_contract.get("reopen_recommended_for_exact_quote")
            ),
            "current_posture_pass": bool(
                source_open.get("action_grammar") == authority.ACTION_SOURCE_OPEN
                and source_open_contract.get("agent_may_quote_exact_wording")
                and "raw source open" in source_open_context
            ),
            "old_posture_pass": bool(
                old_source_open_contract.get("agent_may_quote_exact_wording")
            ),
        },
        "source_court": {
            "agent_behavior": "escalates_or_abstains",
            "action_grammar": source_court.get("action_grammar"),
            "manual_query_invention_count": int(
                bool(source_court_contract.get("manual_query_invention_expected"))
            ),
            "blocked_route_does_not_shape_answer": bool(
                source_court_contract.get("agent_should_ignore")
                and not source_court_contract.get("treat_as_fact")
            ),
            "requires_reopen_or_abstain": bool(
                source_court.get("action_grammar")
                == authority.ACTION_IGNORE_OR_BLOCKED
            ),
            "current_posture_pass": bool(
                source_court_contract.get("agent_should_ignore")
                and "Source court" in source_court_context
            ),
            "old_posture_pass": bool(
                old_source_court.get("action_grammar")
                == authority.ACTION_IGNORE_OR_BLOCKED
            ),
        },
        "first_use_ten_minute_path": {
            "agent_behavior": "explains_recovered_continuity",
            "recovered_continuity_copy": first_use_copy,
            "feels_like_found_prior_context": "found the prior route"
            in first_use_copy,
            "feels_like_governance_console": any(
                word in first_use_copy.casefold()
                for word in ("taxonomy", "schema", "governance", "score")
            ),
            "current_posture_pass": bool(
                "found the prior route" in first_use_copy
                and "source trail" in first_use_copy
                and "keywords" not in first_use_copy
            ),
            "old_posture_pass": bool(
                "found the prior route" in old_first_use_copy
                and "source trail" in old_first_use_copy
            ),
        },
    }
    old_failures = [
        family
        for family, case in cases_by_family.items()
        if not bool(case.get("old_posture_pass"))
    ]
    return {
        "measured": True,
        "mode": "deterministic_fixture",
        "family_count": len(cases_by_family),
        "public_safe": True,
        "checks_behavior_not_just_fields": all(
            bool(case.get("agent_behavior")) and bool(case.get("current_posture_pass"))
            for case in cases_by_family.values()
        ),
        "old_everything_is_scent_baseline_fails": bool(old_failures),
        "old_posture_failure_count": len(old_failures),
        "old_posture_failure_families": old_failures,
        "cases_by_family": cases_by_family,
        "privacy": {
            "raw_source_window_serialized": False,
            "local_paths_serialized": False,
        },
        "boundary": {
            "fixture_public_safe": True,
            "no_external_model_calls": True,
            "no_repo_write": True,
            "raw_source_window_not_serialized": True,
            "old_baseline_strips_routes_refs_and_source_boundaries": True,
        },
    }
