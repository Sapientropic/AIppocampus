"""Recall authority predicates for foreground memory surfaces."""

from __future__ import annotations

from typing import Any, Mapping

NAVIGATION_SCENT = "navigation_scent"
CANDIDATE_WITH_REFS = "candidate_with_refs"
BOUNDED_EVIDENCE_READY = "bounded_evidence_ready"
REOPEN_REQUIRED_BEFORE_CLAIM = "reopen_required_before_claim"
HIGH_RISK_REOPEN_REQUIRED = "high_risk_reopen_required"


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


def requires_reopen_before_claim(surface: Mapping[str, Any]) -> bool:
    if is_bounded_evidence(surface):
        return False
    if str(surface.get("authority_state") or "") == HIGH_RISK_REOPEN_REQUIRED:
        return True
    return bool(surface.get("source_reopen_required"))


def requires_reopen_for_exact_quote_only(surface: Mapping[str, Any]) -> bool:
    return is_bounded_evidence(surface)


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
    return clean
