"""Foreground Memory Evidence Drawer packet projection.

The drawer is an explanation surface, not a recall engine. It takes already
computed recall cards or Active Path Packet paths and exposes why a memory
surface appeared, what authority it has, and what the agent/user can do next.
It must stay ids-only by default: no raw prompt text, source windows, local
paths, or private snippets.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text, stable_text_id
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.recall import authority

DRAWER_KIND = "aippocampus_memory_evidence_drawer"
DRAWER_SCHEMA_VERSION = 1
MAX_SOURCE_REFS = 3

ACTION_LABELS = {
    authority.ACTION_IGNORE_OR_BLOCKED: "blocked_or_abstain",
    authority.ACTION_DIRECTION_ONLY: "navigation_only",
    authority.ACTION_DIRECTION_WITH_REF: "direction_with_source_refs",
    authority.ACTION_REOPENABLE_ROUTE: "reopen_source",
    authority.ACTION_BOUNDED_EVIDENCE: "use_bounded_evidence_within_scope",
    authority.ACTION_SOURCE_OPEN: "use_source_open_with_redaction",
}


def _safe_text(value: Any, chars: int = 220) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _refs(surface: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("source_refs", "candidate_refs"):
        refs = safe_source_refs(surface.get(key))
        if refs:
            return refs[:MAX_SOURCE_REFS]
    return []


def _reopen_plan(surface: Mapping[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    raw_plan = _mapping(surface.get("reopen_plan"))
    status = str(raw_plan.get("status") or "").casefold()
    action = str(surface.get("action_grammar") or "")
    if status == "blocked" or action == authority.ACTION_IGNORE_OR_BLOCKED:
        return {
            "status": "blocked",
            "recommended_tool": None,
            "arguments": {},
            "manual_query_invention_expected": False,
            "reason_codes": list(raw_plan.get("failure_reason_codes") or raw_plan.get("reason_codes") or []),
        }
    if raw_plan:
        raw_arguments = raw_plan.get("arguments")
        clean_arguments = dict(raw_arguments) if isinstance(raw_arguments, Mapping) else {}
        return {
            "status": status or ("ready" if refs else "missing"),
            "recommended_tool": raw_plan.get("recommended_tool") or "recall_deepen",
            "arguments": clean_arguments,
            "manual_query_invention_expected": bool(raw_plan.get("manual_query_invention_expected", False)),
            "reason_codes": list(raw_plan.get("reason_codes") or []),
        }
    if refs:
        ref = refs[0]
        arguments = {
            key: ref[key]
            for key in ("thread_key", "message_id", "turn_id", "turn_index", "line")
            if key in ref
        }
        return {
            "status": "ready",
            "recommended_tool": "recall_deepen",
            "arguments": arguments,
            "manual_query_invention_expected": False,
            "reason_codes": [],
        }
    return {
        "status": "missing",
        "recommended_tool": None,
        "arguments": {},
        "manual_query_invention_expected": False,
        "reason_codes": ["source_refs_missing"],
    }


def _why(surface: Mapping[str, Any], action: str) -> str:
    for key in ("why_lit", "why_this_may_matter", "suggested_use", "expand_if", "route_reason"):
        text = _safe_text(surface.get(key))
        if text:
            return text
    if action == authority.ACTION_BOUNDED_EVIDENCE:
        return "Clean source was reopened into bounded evidence for the current task."
    if action == authority.ACTION_REOPENABLE_ROUTE:
        return "A prior route has source refs; reopen clean source before making a claim."
    if action == authority.ACTION_IGNORE_OR_BLOCKED:
        return "The route is blocked, stale, conflicting, or insufficient; abstain or reopen safely."
    return "A weak navigation signal surfaced; use it only to orient attention."


def _navigation_only(action: str) -> bool:
    return action in {
        authority.ACTION_DIRECTION_ONLY,
        authority.ACTION_DIRECTION_WITH_REF,
        authority.ACTION_REOPENABLE_ROUTE,
        authority.ACTION_IGNORE_OR_BLOCKED,
    }


def _claim_requires_reopen(action: str, contract: Mapping[str, Any]) -> bool:
    if action == authority.ACTION_SOURCE_OPEN:
        return False
    if action == authority.ACTION_BOUNDED_EVIDENCE:
        return bool(contract.get("reopen_recommended_for_exact_quote", True))
    return True


def _affordances(action: str) -> dict[str, Any]:
    return {
        "suppress": True,
        "correct": True,
        "pin": action in {
            authority.ACTION_REOPENABLE_ROUTE,
            authority.ACTION_BOUNDED_EVIDENCE,
            authority.ACTION_SOURCE_OPEN,
        },
        "deepen": action in {
            authority.ACTION_DIRECTION_WITH_REF,
            authority.ACTION_REOPENABLE_ROUTE,
            authority.ACTION_BOUNDED_EVIDENCE,
            authority.ACTION_SOURCE_OPEN,
        },
    }


@dataclass(frozen=True)
class EvidenceDrawerItem:
    drawer_item_id: str
    source_surface_kind: str
    title: str
    why_this_surfaced: str
    action_grammar: str
    trust_level: str
    authority_label: str
    route_strength: str
    source_refs: list[dict[str, Any]]
    reopen_plan: dict[str, Any]
    navigation_only: bool
    can_support_factual_claim: bool
    exact_claim_requires_source_reopen: bool
    abstention_reason: str | None
    affordances: dict[str, Any]
    source_boundary: dict[str, Any]
    cannot_claim: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def drawer_item_from_surface(
    surface: Mapping[str, Any],
    *,
    source_surface_kind: str = "recall_surface",
) -> EvidenceDrawerItem:
    """Project one already-computed recall surface into drawer item form."""

    projected = authority.with_trust_fields(dict(surface))
    action = str(projected.get("action_grammar") or authority.ACTION_DIRECTION_ONLY)
    trust = str(projected.get("trust_level") or authority.TRUST_SCENT)
    contract = _mapping(projected.get("trust_contract"))
    refs = _refs(projected)
    reopen_plan = _reopen_plan(projected, refs)
    navigation_only = _navigation_only(action)
    can_claim = bool(contract.get("agent_may_answer_within_scope")) and action in {
        authority.ACTION_BOUNDED_EVIDENCE,
        authority.ACTION_SOURCE_OPEN,
    }
    blocked = action == authority.ACTION_IGNORE_OR_BLOCKED
    title = _safe_text(
        projected.get("title")
        or projected.get("theme")
        or projected.get("card_id")
        or projected.get("path_id")
        or "Memory evidence drawer item",
        120,
    )
    cannot_claim = []
    if navigation_only:
        cannot_claim.append("navigation_only_surface_supports_factual_claim")
    if action != authority.ACTION_SOURCE_OPEN:
        cannot_claim.append("exact_wording_without_source_open")
    if blocked:
        cannot_claim.append("blocked_or_insufficient_evidence_shapes_answer")
    return EvidenceDrawerItem(
        drawer_item_id=stable_text_id("med", source_surface_kind, title, action, refs, length=18),
        source_surface_kind=source_surface_kind,
        title=title,
        why_this_surfaced=_why(projected, action),
        action_grammar=action,
        trust_level=trust,
        authority_label=ACTION_LABELS.get(action, "navigation_only"),
        route_strength=str(projected.get("confidence") or projected.get("resonance") or "unknown"),
        source_refs=refs,
        reopen_plan=reopen_plan,
        navigation_only=navigation_only,
        can_support_factual_claim=can_claim,
        exact_claim_requires_source_reopen=_claim_requires_reopen(action, contract),
        abstention_reason=(
            _safe_text(projected.get("abstention_reason") or "blocked_or_insufficient_evidence")
            if blocked
            else None
        ),
        affordances=_affordances(action),
        source_boundary={
            "clean_source_is_authority": True,
            "raw_prompt_text_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "confidence_is_not_authority": True,
            "navigation_only": navigation_only,
            "source_reopen_required_before_claim": _claim_requires_reopen(action, contract),
        },
        cannot_claim=cannot_claim,
    )


def drawer_items_from_active_path_packet(packet: Mapping[str, Any]) -> list[EvidenceDrawerItem]:
    paths = packet.get("paths") if isinstance(packet, Mapping) else []
    if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)):
        return []
    return [
        drawer_item_from_surface(path, source_surface_kind="active_path_packet")
        for path in paths
        if isinstance(path, Mapping)
    ]


def drawer_items_from_bounded_evidence_context(context: Mapping[str, Any]) -> list[EvidenceDrawerItem]:
    cards = context.get("cards") if isinstance(context, Mapping) else []
    if not isinstance(cards, Sequence) or isinstance(cards, (str, bytes)):
        return []
    return [
        drawer_item_from_surface(card, source_surface_kind="bounded_evidence_context")
        for card in cards
        if isinstance(card, Mapping)
    ]


def build_memory_evidence_drawer(
    *,
    surfaces: Sequence[Mapping[str, Any]] = (),
    active_path_packet: Mapping[str, Any] | None = None,
    bounded_evidence_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact foreground-facing explanation packet.

    The packet is safe to expose as a drawer/debug surface beside foreground
    memory context. It intentionally explains authority and reopen affordances
    without serializing snippets, raw source windows, prompts, or paths.
    """

    items: list[EvidenceDrawerItem] = []
    items.extend(
        drawer_item_from_surface(surface, source_surface_kind="recall_surface")
        for surface in surfaces
        if isinstance(surface, Mapping)
    )
    if active_path_packet:
        items.extend(drawer_items_from_active_path_packet(active_path_packet))
    if bounded_evidence_context:
        items.extend(drawer_items_from_bounded_evidence_context(bounded_evidence_context))
    rows = [item.to_dict() for item in items]
    return {
        "kind": DRAWER_KIND,
        "schema_version": DRAWER_SCHEMA_VERSION,
        "items": rows,
        "item_count": len(rows),
        "privacy_boundary": {
            "raw_prompt_text_serialized": False,
            "raw_source_text_serialized": False,
            "source_windows_serialized": False,
            "local_paths_serialized": False,
            "secret_values_serialized": False,
        },
        "source_boundary": {
            "drawer_explains_recall": True,
            "drawer_is_not_source_truth": True,
            "clean_source_is_authority": True,
            "confidence_is_not_authority": True,
            "navigation_only_items_cannot_support_factual_claims": True,
        },
        "affordance_contract": {
            "suppress": "hide this route/card for the current foreground use",
            "correct": "record or route an explicit correction back to source-backed memory",
            "pin": "promote a source-trailed route/boundary, not raw drawer prose",
            "deepen": "open the source route through recall_deepen/get_turn_context before stronger claims",
        },
        "cannot_claim": [
            "drawer_item_is_source_truth",
            "confidence_score_is_authority",
            "navigation_only_item_supports_factual_claim",
            "exact_quote_without_source_open",
        ],
    }
