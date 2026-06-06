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
TRUST_SOURCE_REQUIRED = "source_required"
TRUST_BOUNDED_EVIDENCE = "bounded_evidence"
TRUST_RAW_SOURCE_REOPENED = "raw_source_reopened"

TRUST_TAXONOMY: tuple[dict[str, Any], ...] = (
    {
        "trust_level": TRUST_IGNORE,
        "allowed_use": "ignore_or_report_boundary",
        "summary": "Stale, suppressed, superseded, privacy-blocked, or otherwise unsafe.",
    },
    {
        "trust_level": TRUST_SEMANTIC_HINT,
        "allowed_use": "wayfinding_only",
        "summary": "Model, cognitive-map, or semantic route material; navigation only.",
    },
    {
        "trust_level": TRUST_SCENT,
        "allowed_use": "weak_navigation",
        "summary": "A weak association that may decide whether further recall is worth it.",
    },
    {
        "trust_level": TRUST_SOURCE_REQUIRED,
        "allowed_use": "reopen_source",
        "summary": "Actionable source-reopen route; not factual evidence yet.",
    },
    {
        "trust_level": TRUST_BOUNDED_EVIDENCE,
        "allowed_use": "use_within_declared_scope",
        "summary": "Clean source has already been reopened into bounded evidence.",
    },
    {
        "trust_level": TRUST_RAW_SOURCE_REOPENED,
        "allowed_use": "use_raw_source_with_redaction",
        "summary": "Raw/local source is open to the host; still scope- and redaction-bound.",
    },
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def trust_contract_for_level(level: str, surface: Mapping[str, Any] | None = None) -> dict[str, Any]:
    clean_level = str(level or TRUST_SCENT)
    surface_map = _mapping(surface)
    if clean_level == TRUST_IGNORE:
        return {
            "allowed_use": "ignore_or_report_boundary",
            "agent_may_answer_within_scope": False,
            "source_reopen_required_before_claim": False,
            "reopen_recommended_for_exact_quote": False,
            "manual_query_invention_expected": False,
            "treat_as_fact": False,
        }
    if clean_level == TRUST_SEMANTIC_HINT:
        return {
            "allowed_use": "wayfinding_only",
            "agent_may_answer_within_scope": False,
            "source_reopen_required_before_claim": True,
            "reopen_recommended_for_exact_quote": True,
            "manual_query_invention_expected": True,
            "treat_as_fact": False,
        }
    if clean_level == TRUST_SOURCE_REQUIRED:
        plan = _mapping(surface_map.get("reopen_plan"))
        return {
            "allowed_use": "reopen_source",
            "agent_may_answer_within_scope": False,
            "source_reopen_required_before_claim": True,
            "reopen_recommended_for_exact_quote": True,
            "manual_query_invention_expected": bool(
                plan.get("manual_query_invention_expected", False)
            ),
            "treat_as_fact": False,
        }
    if clean_level == TRUST_BOUNDED_EVIDENCE:
        return {
            "allowed_use": "use_within_declared_scope",
            "agent_may_answer_within_scope": True,
            "source_reopen_required_before_claim": False,
            "reopen_recommended_for_exact_quote": True,
            "manual_query_invention_expected": False,
            "treat_as_fact": True,
        }
    if clean_level == TRUST_RAW_SOURCE_REOPENED:
        return {
            "allowed_use": "use_raw_source_with_redaction",
            "agent_may_answer_within_scope": True,
            "source_reopen_required_before_claim": False,
            "reopen_recommended_for_exact_quote": False,
            "manual_query_invention_expected": False,
            "treat_as_fact": True,
        }
    return {
        "allowed_use": "weak_navigation",
        "agent_may_answer_within_scope": False,
        "source_reopen_required_before_claim": True,
        "reopen_recommended_for_exact_quote": True,
        "manual_query_invention_expected": True,
        "treat_as_fact": False,
    }


def with_trust_fields(surface: Mapping[str, Any]) -> dict[str, Any]:
    clean = dict(surface)
    level = trust_level(clean)
    clean["trust_level"] = level
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
        REOPEN_REQUIRED_BEFORE_CLAIM,
        HIGH_RISK_REOPEN_REQUIRED,
    }
    clean["reopen_recommended_for_exact_quote"] = requires_reopen_for_exact_quote_only(clean)
    if state == BOUNDED_EVIDENCE_READY:
        clean["source_reopen_required"] = False
    return with_trust_fields(clean)
