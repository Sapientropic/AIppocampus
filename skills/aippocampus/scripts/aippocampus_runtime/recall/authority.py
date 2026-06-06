"""Recall authority and trust predicates for foreground memory surfaces.

The trust taxonomy is intentionally small. It reuses existing packet fields
instead of adding a scoring layer, so host agents can distinguish semantic
wayfinding, source-reopen routes, and bounded evidence without weakening the
clean-source boundary.
"""

from __future__ import annotations

from typing import Any, Mapping

NAVIGATION_SCENT = "navigation_scent"
CANDIDATE_WITH_REFS = "candidate_with_refs"
BOUNDED_EVIDENCE_READY = "bounded_evidence_ready"
REOPEN_REQUIRED_BEFORE_CLAIM = "reopen_required_before_claim"
HIGH_RISK_REOPEN_REQUIRED = "high_risk_reopen_required"

TRUST_IGNORE = "ignore"
TRUST_SEMANTIC_HINT = "semantic_hint"
TRUST_SCENT = "scent"
TRUST_CANDIDATE_BACKED = "candidate_backed"
TRUST_SOURCE_REQUIRED = "source_required"
TRUST_BOUNDED_EVIDENCE = "bounded_evidence"
TRUST_RAW_SOURCE_REOPENED = "raw_source_reopened"

ACTION_IGNORE_OR_BLOCKED = "ignore_or_blocked"
ACTION_DIRECTION_ONLY = "direction_only"
ACTION_DIRECTION_WITH_REF = "direction_with_ref"
ACTION_REOPENABLE_ROUTE = "reopenable_route"
ACTION_BOUNDED_EVIDENCE = "bounded_evidence"
ACTION_SOURCE_OPEN = "source_open"

TRUST_TAXONOMY: tuple[dict[str, Any], ...] = (
    {
        "trust_level": TRUST_IGNORE,
        "action_grammar": ACTION_IGNORE_OR_BLOCKED,
        "allowed_use": "ignore_or_report_boundary",
        "summary": "Stale, suppressed, superseded, privacy-blocked, or otherwise unsafe.",
    },
    {
        "trust_level": TRUST_SEMANTIC_HINT,
        "action_grammar": ACTION_DIRECTION_ONLY,
        "allowed_use": "wayfinding_only",
        "summary": "Model, cognitive-map, or semantic route material; navigation only.",
    },
    {
        "trust_level": TRUST_SCENT,
        "action_grammar": ACTION_DIRECTION_ONLY,
        "allowed_use": "weak_navigation",
        "summary": "A weak association that may decide whether further recall is worth it.",
    },
    {
        "trust_level": TRUST_CANDIDATE_BACKED,
        "action_grammar": ACTION_DIRECTION_WITH_REF,
        "allowed_use": "shape_direction_with_refs",
        "summary": "A source-ref-backed candidate may shape direction, depth, or route choice.",
    },
    {
        "trust_level": TRUST_SOURCE_REQUIRED,
        "action_grammar": ACTION_REOPENABLE_ROUTE,
        "allowed_use": "reopen_source",
        "summary": "Actionable source-reopen route; not factual evidence yet.",
    },
    {
        "trust_level": TRUST_BOUNDED_EVIDENCE,
        "action_grammar": ACTION_BOUNDED_EVIDENCE,
        "allowed_use": "use_within_declared_scope",
        "summary": "Clean source has already been reopened into bounded evidence.",
    },
    {
        "trust_level": TRUST_RAW_SOURCE_REOPENED,
        "action_grammar": ACTION_SOURCE_OPEN,
        "allowed_use": "use_raw_source_with_redaction",
        "summary": "Raw/local source is open to the host; still scope- and redaction-bound.",
    },
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _has_route_refs(surface: Mapping[str, Any]) -> bool:
    return bool(surface.get("source_refs") or surface.get("candidate_refs"))


def _has_candidate_conflict(surface: Mapping[str, Any]) -> bool:
    boundary = _mapping(surface.get("source_boundary"))
    status = str(surface.get("conflict_status") or boundary.get("conflict_status") or "").casefold()
    return bool(surface.get("conflict_flags")) or status in {
        "conflict",
        "conflicted",
        "source_conflict",
        "uncleared",
        "unreviewed",
    }


def is_bounded_evidence(surface: Mapping[str, Any]) -> bool:
    """Return true only when a surface already came from bounded clean source."""

    if str(surface.get("support_level") or "").casefold() != "evidence":
        return False
    boundary = _mapping(surface.get("source_boundary"))
    return bool(
        str(surface.get("provenance_class") or "") == "source_backed_reopen"
        or str(surface.get("evidence_level") or "") == "source_backed"
        or boundary.get("clean_source_reopened")
        or boundary.get("cards_are_bounded_source_backed_context")
    )


def trust_taxonomy() -> list[dict[str, Any]]:
    return [dict(row) for row in TRUST_TAXONOMY]


def requires_reopen_before_claim(surface: Mapping[str, Any]) -> bool:
    if is_bounded_evidence(surface):
        return False
    if str(surface.get("authority_state") or "") == HIGH_RISK_REOPEN_REQUIRED:
        return True
    return bool(surface.get("source_reopen_required"))


def requires_reopen_for_exact_quote_only(surface: Mapping[str, Any]) -> bool:
    return is_bounded_evidence(surface)


def trust_level(surface: Mapping[str, Any]) -> str:
    """Map existing packet/card fields to the #786 agent-facing trust tier."""

    support = str(surface.get("support_level") or "").casefold()
    provenance = str(surface.get("provenance_class") or "").casefold()
    route = str(surface.get("route") or "").casefold()
    visibility = str(surface.get("visibility") or "").casefold()
    currentness = str(surface.get("currentness") or surface.get("freshness") or "").casefold()
    authority = str(surface.get("authority_state") or "").casefold()
    boundary = _mapping(surface.get("source_boundary"))

    if (
        route == "ignore"
        or support == "suppressed"
        or visibility == "blocked"
        or currentness in {"stale", "superseded"}
    ):
        return TRUST_IGNORE
    if boundary.get("raw_source_reopened") or str(surface.get("evidence_level") or "") == "raw_source":
        return TRUST_RAW_SOURCE_REOPENED
    if is_bounded_evidence(surface):
        return TRUST_BOUNDED_EVIDENCE
    if support == "source_required" or route == "reopen" or authority in {
        REOPEN_REQUIRED_BEFORE_CLAIM,
        HIGH_RISK_REOPEN_REQUIRED,
    }:
        return TRUST_SOURCE_REQUIRED
    if (
        _has_route_refs(surface)
        and (support == "candidate" or authority == CANDIDATE_WITH_REFS)
        and _has_candidate_conflict(surface)
    ):
        return TRUST_IGNORE
    if (
        _has_route_refs(surface)
        and (support == "candidate" or authority == CANDIDATE_WITH_REFS)
        and bool(surface.get("source_reopen_required", True))
    ):
        return TRUST_CANDIDATE_BACKED
    if provenance in {
        "cognitive_map_route",
        "working_memory_model",
        "warm_scout_proposal",
    }:
        return TRUST_SEMANTIC_HINT
    if support in {"scent", "candidate", "soft_hypothesis", "silent_scent"} or route == "scent":
        return TRUST_SCENT
    if surface.get("source_refs") and surface.get("source_reopen_required"):
        return TRUST_SOURCE_REQUIRED
    return TRUST_SCENT


def action_grammar_for_level(
    level: str,
    surface: Mapping[str, Any] | None = None,
) -> str:
    """Project the trust tier into the foreground agent's next-action grammar."""

    clean_level = str(level or TRUST_SCENT)
    surface_map = _mapping(surface)
    plan = _mapping(surface_map.get("reopen_plan"))
    plan_status = str(plan.get("status") or "").casefold()
    route = str(surface_map.get("route") or "").casefold()
    visibility = str(surface_map.get("visibility") or "").casefold()
    currentness = str(
        surface_map.get("currentness") or surface_map.get("freshness") or ""
    ).casefold()
    support = str(surface_map.get("support_level") or "").casefold()

    if (
        clean_level == TRUST_IGNORE
        or route == "ignore"
        or support == "suppressed"
        or visibility == "blocked"
        or currentness in {"stale", "superseded"}
        or plan_status == "blocked"
        or (clean_level == TRUST_CANDIDATE_BACKED and _has_candidate_conflict(surface_map))
    ):
        return ACTION_IGNORE_OR_BLOCKED
    if clean_level == TRUST_RAW_SOURCE_REOPENED:
        return ACTION_SOURCE_OPEN
    if clean_level == TRUST_BOUNDED_EVIDENCE:
        return ACTION_BOUNDED_EVIDENCE
    if clean_level == TRUST_CANDIDATE_BACKED:
        if not surface_map or _has_route_refs(surface_map):
            return ACTION_DIRECTION_WITH_REF
        return ACTION_DIRECTION_ONLY
    if clean_level == TRUST_SOURCE_REQUIRED:
        if not surface_map:
            return ACTION_REOPENABLE_ROUTE
        if (
            plan_status == "ready"
            or route == "reopen"
            or surface_map.get("source_refs")
            or surface_map.get("candidate_refs")
        ):
            return ACTION_REOPENABLE_ROUTE
        return ACTION_IGNORE_OR_BLOCKED
    return ACTION_DIRECTION_ONLY


def action_grammar(surface: Mapping[str, Any]) -> str:
    return action_grammar_for_level(trust_level(surface), surface)


def trust_contract_for_level(level: str, surface: Mapping[str, Any] | None = None) -> dict[str, Any]:
    clean_level = str(level or TRUST_SCENT)
    surface_map = _mapping(surface)
    grammar = action_grammar_for_level(clean_level, surface_map)
    should_ignore = grammar == ACTION_IGNORE_OR_BLOCKED
    should_reopen = grammar == ACTION_REOPENABLE_ROUTE
    may_quote = grammar == ACTION_SOURCE_OPEN
    if clean_level == TRUST_IGNORE:
        return {
            "action_grammar": grammar,
            "allowed_use": "ignore_or_report_boundary",
            "agent_may_answer_within_scope": False,
            "agent_may_quote_exact_wording": may_quote,
            "agent_should_ignore": True,
            "agent_should_reopen_source": False,
            "source_reopen_required_before_claim": False,
            "reopen_recommended_for_exact_quote": False,
            "manual_query_invention_expected": False,
            "treat_as_fact": False,
        }
    if clean_level == TRUST_SEMANTIC_HINT:
        return {
            "action_grammar": grammar,
            "allowed_use": "wayfinding_only",
            "agent_may_answer_within_scope": False,
            "agent_may_quote_exact_wording": may_quote,
            "agent_should_ignore": should_ignore,
            "agent_should_reopen_source": should_reopen,
            "source_reopen_required_before_claim": True,
            "reopen_recommended_for_exact_quote": True,
            "manual_query_invention_expected": True,
            "treat_as_fact": False,
        }
    if clean_level == TRUST_SOURCE_REQUIRED:
        plan = _mapping(surface_map.get("reopen_plan"))
        return {
            "action_grammar": grammar,
            "allowed_use": "blocked_reopen_boundary" if should_ignore else "reopen_source",
            "agent_may_answer_within_scope": False,
            "agent_may_quote_exact_wording": may_quote,
            "agent_should_ignore": should_ignore,
            "agent_should_reopen_source": should_reopen,
            "source_reopen_required_before_claim": True,
            "reopen_recommended_for_exact_quote": True,
            "manual_query_invention_expected": bool(
                False if should_ignore else plan.get("manual_query_invention_expected", False)
            ),
            "treat_as_fact": False,
        }
    if clean_level == TRUST_CANDIDATE_BACKED:
        refs_available = bool(_has_route_refs(surface_map)) if surface_map else True
        return {
            "action_grammar": grammar,
            "allowed_use": "shape_direction_with_refs",
            "agent_may_answer_within_scope": False,
            "agent_may_quote_exact_wording": may_quote,
            "agent_should_ignore": should_ignore,
            "agent_should_reopen_source": False,
            "source_reopen_required_before_claim": True,
            "reopen_recommended_for_exact_quote": True,
            "manual_query_invention_expected": not refs_available,
            "treat_as_fact": False,
        }
    if clean_level == TRUST_BOUNDED_EVIDENCE:
        return {
            "action_grammar": grammar,
            "allowed_use": "use_within_declared_scope",
            "agent_may_answer_within_scope": True,
            "agent_may_quote_exact_wording": may_quote,
            "agent_should_ignore": should_ignore,
            "agent_should_reopen_source": should_reopen,
            "source_reopen_required_before_claim": False,
            "reopen_recommended_for_exact_quote": True,
            "manual_query_invention_expected": False,
            "treat_as_fact": True,
        }
    if clean_level == TRUST_RAW_SOURCE_REOPENED:
        return {
            "action_grammar": grammar,
            "allowed_use": "use_raw_source_with_redaction",
            "agent_may_answer_within_scope": True,
            "agent_may_quote_exact_wording": may_quote,
            "agent_should_ignore": should_ignore,
            "agent_should_reopen_source": should_reopen,
            "source_reopen_required_before_claim": False,
            "reopen_recommended_for_exact_quote": False,
            "manual_query_invention_expected": False,
            "treat_as_fact": True,
        }
    return {
        "action_grammar": grammar,
        "allowed_use": "weak_navigation",
        "agent_may_answer_within_scope": False,
        "agent_may_quote_exact_wording": may_quote,
        "agent_should_ignore": should_ignore,
        "agent_should_reopen_source": should_reopen,
        "source_reopen_required_before_claim": True,
        "reopen_recommended_for_exact_quote": True,
        "manual_query_invention_expected": True,
        "treat_as_fact": False,
    }


def with_trust_fields(surface: Mapping[str, Any]) -> dict[str, Any]:
    clean = dict(surface)
    level = trust_level(clean)
    grammar = action_grammar_for_level(level, clean)
    clean["trust_level"] = level
    clean["action_grammar"] = grammar
    clean["trust_contract"] = trust_contract_for_level(level, clean)
    return clean


def authority_state(surface: Mapping[str, Any]) -> str:
    if is_bounded_evidence(surface):
        return BOUNDED_EVIDENCE_READY
    if requires_reopen_before_claim(surface):
        return REOPEN_REQUIRED_BEFORE_CLAIM
    if surface.get("source_refs"):
        return CANDIDATE_WITH_REFS
    return NAVIGATION_SCENT


def with_authority_fields(surface: Mapping[str, Any]) -> dict[str, Any]:
    """Attach concise authority fields without changing source refs or snippets."""

    clean = dict(surface)
    state = authority_state(clean)
    clean["authority_state"] = state
    clean["reopen_required_before_claim"] = state in {
        CANDIDATE_WITH_REFS,
        REOPEN_REQUIRED_BEFORE_CLAIM,
        HIGH_RISK_REOPEN_REQUIRED,
    }
    clean["reopen_recommended_for_exact_quote"] = requires_reopen_for_exact_quote_only(clean)
    if state == BOUNDED_EVIDENCE_READY:
        clean["source_reopen_required"] = False
    return with_trust_fields(clean)
