"""Task-time narrative packet projection for source-backed recall routes.

The packet is a foreground route mesh, not a new truth layer. It composes
already-built pathlets, continuity-domain pointers, sequence packets, active
path routes, and optional situation glyphs so a later agent can reopen source
without manually stitching every surface together.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.coding import sequence_packets, sequence_reopen
from aippocampus_runtime.core import dict_or_empty
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.authority import (
    ACTION_BOUNDED_EVIDENCE,
    ACTION_DIRECTION_ONLY,
    ACTION_DIRECTION_WITH_REF,
    ACTION_IGNORE_OR_BLOCKED,
    ACTION_REOPENABLE_ROUTE,
    ACTION_SOURCE_OPEN,
    TRUST_BOUNDED_EVIDENCE,
    TRUST_CANDIDATE_BACKED,
    TRUST_IGNORE,
    TRUST_RAW_SOURCE_REOPENED,
    TRUST_SCENT,
    TRUST_SOURCE_REQUIRED,
    trust_contract_for_level,
)
from aippocampus_runtime.registry.common import unique_preserve

NARRATIVE_PACKET_KIND = "aippocampus_narrative_packet"
NARRATIVE_PACKET_SCHEMA_VERSION = 1
SOURCE_DISCUSSION = 700

BLOCKED_STATUSES = {"blocked", "retired", "stale", "superseded"}
HARD_BOUNDARY_EFFECTS = {"block_hook", "suppress_domain", "suppress_packet", "do_not_use_here"}


def compile_narrative_packet(
    *,
    trigger: str,
    current_query: str = "",
    pathlets: Sequence[Mapping[str, Any]] = (),
    continuity_domain_pointers: Sequence[Mapping[str, Any]] = (),
    sequence_packets: Sequence[Mapping[str, Any]] = (),
    active_path_packet: Mapping[str, Any] | None = None,
    optional_glyphs: Sequence[Mapping[str, Any]] = (),
    source_catalog: Sequence[Mapping[str, Any]] = (),
    max_items: int = 8,
) -> dict[str, Any]:
    """Compose source-backed navigation surfaces into one public-safe route packet.

    This function is intentionally pure and no-write. It preserves route order
    and source-ref handles, but never serializes raw source text or upgrades a
    story, domain, sequence, or glyph into evidence.
    """

    limit = max(1, int(max_items or 1))
    recommended_refs: list[dict[str, Any]] = []
    cannot_claim: list[str] = [
        "narrative_packet_is_not_source",
        "narrative_packet_proves_memory_fact",
        "route_context_is_exact_source_wording",
        "exact_factual_claim_without_source_reopen",
        "public_claim_without_source_reopen",
        "sensitive_or_high_risk_claim_without_source_reopen",
    ]
    sequence_risks: dict[str, list[dict[str, Any]]] = {
        "missing_middle_events": [],
        "supersession_or_extinction": [],
        "order_sensitive_chains": [],
    }
    hard_block = False
    blocked_route_count = 0
    nonblocked_route_count = 0
    has_reopenable_route = False
    has_direction_ref = False
    has_bounded_evidence = False
    bounded_evidence_count = 0

    normalized_pathlets: list[dict[str, Any]] = []
    for row in _mapping_items(pathlets, limit=limit):
        pathlet = _normalize_pathlet(row)
        normalized_pathlets.append(pathlet)
        cannot_claim.extend(pathlet.get("cannot_claim") or [])
        if _is_blocked(pathlet):
            blocked_route_count += 1
            continue
        nonblocked_route_count += 1
        has_reopenable_route = True
        _extend_refs(recommended_refs, pathlet.get("ordered_source_refs"))

    normalized_domains: list[dict[str, Any]] = []
    for row in _mapping_items(continuity_domain_pointers, limit=limit):
        domain = _normalize_domain_pointer(row)
        normalized_domains.append(domain)
        cannot_claim.extend(domain.get("cannot_claim") or [])
        if _has_hard_boundary(domain):
            hard_block = True
        if _is_blocked(domain):
            blocked_route_count += 1
            continue
        nonblocked_route_count += 1
        action = str(domain.get("action_grammar") or "")
        if action == ACTION_REOPENABLE_ROUTE:
            has_reopenable_route = True
        elif action == ACTION_DIRECTION_WITH_REF:
            has_direction_ref = True
        _extend_refs(recommended_refs, domain.get("source_refs"))

    normalized_sequences: list[dict[str, Any]] = []
    sequence_reopen_plans: list[dict[str, Any]] = []
    for index, row in enumerate(_mapping_items(sequence_packets, limit=limit)):
        sequence = _normalize_sequence_packet(
            row,
            packet_index=index,
            source_catalog=source_catalog,
        )
        normalized_sequences.append(sequence)
        plan = sequence["reopen_plan"]
        sequence_reopen_plans.append(plan)
        cannot_claim.extend(sequence.get("cannot_claim") or [])
        _collect_sequence_risks(sequence, sequence_risks)
        if _is_blocked(sequence):
            blocked_route_count += 1
            continue
        nonblocked_route_count += 1
        has_reopenable_route = True
        _extend_refs(recommended_refs, plan.get("route", {}).get("source_refs"))

    active_routes: list[dict[str, Any]] = []
    active_blockers: list[dict[str, Any]] = []
    for row in _active_path_rows(active_path_packet, limit=limit):
        active = _normalize_active_path(row)
        cannot_claim.extend(active.get("cannot_claim") or [])
        if _has_hard_boundary(active):
            hard_block = True
        if _is_blocked(active):
            active_blockers.append(active)
            blocked_route_count += 1
            continue
        active_routes.append(active)
        nonblocked_route_count += 1
        action = str(active.get("action_grammar") or "")
        if action == ACTION_REOPENABLE_ROUTE:
            has_reopenable_route = True
        elif action == ACTION_DIRECTION_WITH_REF:
            has_direction_ref = True
        elif action in {ACTION_BOUNDED_EVIDENCE, ACTION_SOURCE_OPEN}:
            has_bounded_evidence = True
            bounded_evidence_count += 1
        _extend_refs(recommended_refs, active.get("source_refs"))

    normalized_glyphs: list[dict[str, Any]] = []
    for row in _mapping_items(optional_glyphs, limit=limit):
        glyph = _normalize_glyph(row)
        normalized_glyphs.append(glyph)
        cannot_claim.extend(glyph.get("cannot_claim") or [])
        if _has_hard_boundary(glyph):
            hard_block = True
        if _is_blocked(glyph):
            blocked_route_count += 1

    only_blocked_routes = blocked_route_count > 0 and nonblocked_route_count == 0 and not normalized_glyphs
    action_grammar = _packet_action_grammar(
        hard_block=hard_block,
        only_blocked_routes=only_blocked_routes,
        has_reopenable_route=has_reopenable_route,
        has_direction_ref=has_direction_ref,
        has_bounded_evidence=has_bounded_evidence,
        bounded_evidence_only=(
            bounded_evidence_count > 0 and bounded_evidence_count == nonblocked_route_count
        ),
        has_glyphs=bool(normalized_glyphs),
    )
    if action_grammar == ACTION_IGNORE_OR_BLOCKED:
        recommended_refs = []
        cannot_claim.append("hard_boundary_blocks_narrative_packet_use" if hard_block else "stale_or_blocked_route")
    if blocked_route_count:
        cannot_claim.append("stale_or_superseded_route_is_not_current_fact")
    if normalized_glyphs and nonblocked_route_count == 0:
        cannot_claim.append("glyph_only_atmosphere_not_evidence")

    recommended_refs = _dedupe_refs(recommended_refs, limit=48)
    required_before_claim = [] if action_grammar in {ACTION_IGNORE_OR_BLOCKED, ACTION_DIRECTION_ONLY} else recommended_refs
    trust_level = _trust_level_for_packet(action_grammar)
    trust_contract = trust_contract_for_level(
        trust_level,
        {
            "source_refs": required_before_claim,
            "source_reopen_required": bool(required_before_claim),
        },
    )
    route_shape = {
        "pathlets": normalized_pathlets,
        "continuity_domains": normalized_domains,
        "sequence_packets": normalized_sequences,
        "active_path_routes": active_routes,
        "active_path_blockers": active_blockers,
        "optional_glyphs": normalized_glyphs,
    }
    packet = {
        "kind": NARRATIVE_PACKET_KIND,
        "schema_version": NARRATIVE_PACKET_SCHEMA_VERSION,
        "source_discussion": SOURCE_DISCUSSION,
        "trigger": _safe_text(trigger, limit=80) or "explicit_recall",
        "current_query": _safe_text(current_query, limit=240),
        "route_shape": route_shape,
        "source_reopen": {
            "recommended_refs": recommended_refs,
            "required_before_claim": required_before_claim,
            "sequence_reopen_plans": sequence_reopen_plans,
            "manual_query_invention_expected": not bool(recommended_refs),
        },
        "sequence_risks": sequence_risks,
        "use_boundary": {
            "action_grammar": action_grammar,
            "trust_level": trust_level,
            "agent_may_answer_within_scope": bool(
                trust_contract.get("agent_may_answer_within_scope")
            )
            and action_grammar == ACTION_BOUNDED_EVIDENCE,
            "agent_should_reopen_source": action_grammar == ACTION_REOPENABLE_ROUTE,
            "source_reopen_required_before_claim": action_grammar
            not in {ACTION_IGNORE_OR_BLOCKED, ACTION_SOURCE_OPEN},
            "cannot_claim": unique_preserve(cannot_claim, limit=32),
            "trust_contract": trust_contract,
        },
        "source_boundary": {
            "narrative_packet_is_not_source_truth": True,
            "clean_source_is_authority": True,
            "source_reopen_required_before_factual_claim": True,
            "pathlet_sequence_domain_and_glyphs_are_navigation": True,
            "bounded_evidence_does_not_promote_mixed_packet": True,
            "raw_source_text_serialized": False,
        },
        "privacy": {
            "local_first": True,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "secret_values_serialized": False,
            "cloud_calls": False,
            "external_model_calls": False,
        },
        "metrics": {
            "pathlet_count": len(normalized_pathlets),
            "continuity_domain_count": len(normalized_domains),
            "sequence_packet_count": len(normalized_sequences),
            "active_path_route_count": len(active_routes),
            "active_path_blocker_count": len(active_blockers),
            "optional_glyph_count": len(normalized_glyphs),
            "recommended_ref_count": len(recommended_refs),
            "blocked_route_count": blocked_route_count,
        },
        "no_write": True,
    }
    return redact_sensitive_values(redact_private_paths(packet))


def _normalize_pathlet(row: Mapping[str, Any]) -> dict[str, Any]:
    status = _status(row)
    ordered_refs = safe_source_refs(row.get("ordered_source_refs") or row.get("source_refs"))
    blocked = status in BLOCKED_STATUSES
    action = ACTION_IGNORE_OR_BLOCKED if blocked else str(row.get("action_grammar") or ACTION_REOPENABLE_ROUTE)
    return {
        "pathlet_id": _safe_text(row.get("pathlet_id"), limit=120),
        "title": _safe_text(row.get("title") or row.get("pathlet_id"), limit=160),
        "status": status,
        "ordered_source_refs": ordered_refs,
        "source_refs": _dedupe_refs(ordered_refs, limit=24),
        "domain_ids": _safe_string_list(row.get("domain_ids"), limit=12),
        "scope_labels": _safe_string_list(row.get("scope_labels"), limit=12),
        "truth_boundary": "pathlet_is_ordered_route_not_source_fact",
        "action_grammar": action,
        "cannot_claim": ["pathlet_is_fact"],
    }


def _normalize_domain_pointer(row: Mapping[str, Any]) -> dict[str, Any]:
    status = _status(row)
    refs = safe_source_refs(row.get("source_refs") or row.get("representative_sources"))
    pinned = [
        {
            "kind": _safe_text(item.get("kind"), limit=80),
            "strength": _safe_text(item.get("strength"), limit=40),
            "effect": _safe_text(item.get("effect"), limit=80),
        }
        for item in _mapping_items(row.get("pinned_boundary_conditions"), limit=8)
    ]
    hard_boundary = any(_boundary_is_hard(item) for item in pinned)
    blocked = status in BLOCKED_STATUSES or hard_boundary
    action = ACTION_IGNORE_OR_BLOCKED if blocked else str(row.get("action_grammar") or ACTION_REOPENABLE_ROUTE)
    return {
        "card_kind": "continuity_domain_pointer",
        "domain_id": _safe_text(row.get("domain_id"), limit=120),
        "label": _safe_text(row.get("label") or row.get("theme") or row.get("domain_id"), limit=160),
        "domain_type": _safe_text(row.get("domain_type"), limit=80) or "recurring_question",
        "scale": _safe_text(row.get("scale"), limit=40) or "meso",
        "status": status,
        "action_grammar": action,
        "source_refs": refs,
        "pinned_boundary_conditions": pinned,
        "why_it_may_matter_now": _safe_text(row.get("why_it_may_matter_now"), limit=220),
        "reopen_plan": _safe_reopen_plan(row.get("reopen_plan")),
        "source_boundary": {
            "continuity_domain_pointer_is_not_summary_truth": True,
            "source_reopen_required_before_claim": True,
        },
        "cannot_claim": ["continuity_domain_pointer_is_summary_truth"],
    }


def _normalize_sequence_packet(
    row: Mapping[str, Any],
    *,
    packet_index: int,
    source_catalog: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    plan = sequence_reopen.build_sequence_packet_reopen_plan(row, source_catalog=source_catalog)
    timeline = [
        {
            "event_id": _safe_text(item.get("event_id"), limit=120),
            "event_kind": _safe_text(item.get("event_kind"), limit=80),
            "source_ref_hash": _safe_text(item.get("source_ref_hash"), limit=120),
        }
        for item in _mapping_items(row.get("timeline"), limit=24)
    ]
    gaps = _safe_string_list(row.get("sequence_gaps"), limit=12)
    current_assessment = _safe_current_assessment(row.get("current_assessment"))
    action = ACTION_REOPENABLE_ROUTE if timeline else ACTION_IGNORE_OR_BLOCKED
    cannot_claim = unique_preserve(
        _safe_string_list(row.get("cannot_claim"), limit=16)
        + _safe_string_list(plan.get("cannot_claim"), limit=16)
        + ["sequence_packet_is_not_evidence"],
        limit=20,
    )
    return {
        "kind": _safe_text(row.get("kind"), limit=80) or sequence_packets.SEQUENCE_PACKET_KIND,
        "packet_index": packet_index,
        "trigger": _safe_text(row.get("trigger"), limit=80),
        "why_relevant": _safe_text(row.get("why_relevant"), limit=180),
        "timeline": timeline,
        "current_assessment": current_assessment,
        "sequence_gaps": gaps,
        "reopen_plan": plan,
        "action_grammar": action,
        "truth_boundary": "sequence_packet_is_navigation_not_evidence",
        "cannot_claim": cannot_claim,
    }


def _normalize_active_path(row: Mapping[str, Any]) -> dict[str, Any]:
    action = str(row.get("action_grammar") or "")
    if not action:
        action = ACTION_IGNORE_OR_BLOCKED if _is_blocked(row) else ACTION_REOPENABLE_ROUTE
    source_boundary = dict_or_empty(row.get("source_boundary"))
    return {
        "title": _safe_text(row.get("title") or row.get("path_id") or row.get("route"), limit=160),
        "route": _safe_text(row.get("route"), limit=40) or "reopen",
        "currentness": _safe_text(row.get("currentness") or row.get("freshness"), limit=40),
        "action_grammar": action,
        "next_action": _safe_text(row.get("next_action"), limit=80),
        "source_refs": safe_source_refs(row.get("source_refs") or row.get("candidate_refs")),
        "reason_codes": _safe_string_list(row.get("reason_codes"), limit=8),
        "source_boundary": {
            "source_reopen_required": bool(source_boundary.get("source_reopen_required")),
            "unsafe_to_use_as_current_fact": bool(source_boundary.get("unsafe_to_use_as_current_fact")),
            "bounded_evidence_usable_within_scope": bool(
                source_boundary.get("bounded_evidence_usable_within_scope")
            ),
        },
        "cannot_claim": _safe_string_list(row.get("cannot_claim"), limit=10),
    }


def _normalize_glyph(row: Mapping[str, Any]) -> dict[str, Any]:
    pinned = [
        {
            "kind": _safe_text(item.get("kind"), limit=80),
            "strength": _safe_text(item.get("strength"), limit=40),
            "effect": _safe_text(item.get("effect"), limit=80),
        }
        for item in _mapping_items(row.get("pinned_boundary_conditions"), limit=8)
    ]
    hard_boundary = any(_boundary_is_hard(item) for item in pinned)
    action = ACTION_IGNORE_OR_BLOCKED if hard_boundary else str(row.get("action_grammar") or ACTION_DIRECTION_ONLY)
    return {
        "glyph_id": _safe_text(row.get("glyph_id"), limit=120),
        "label": _safe_text(row.get("label") or row.get("title") or row.get("glyph_id"), limit=160),
        "signal_labels": _safe_string_list(row.get("signal_labels"), limit=12),
        "action_grammar": action,
        "pinned_boundary_conditions": pinned,
        "truth_boundary": "glyph_is_atmosphere_not_source_evidence",
        "cannot_claim": ["glyph_is_fact", "glyph_only_atmosphere_not_evidence"],
    }


def _collect_sequence_risks(
    sequence: Mapping[str, Any],
    risks: dict[str, list[dict[str, Any]]],
) -> None:
    gaps = _safe_string_list(sequence.get("sequence_gaps"), limit=12)
    if "missing_middle_event" in gaps:
        risks["missing_middle_events"].append(
            {
                "packet_index": sequence.get("packet_index"),
                "sequence_gaps": gaps,
                "safe_use": sequence.get("reopen_plan", {}).get("recommended_use"),
            }
        )
    timeline = [item for item in sequence.get("timeline") or [] if isinstance(item, Mapping)]
    if len(timeline) > 1:
        risks["order_sensitive_chains"].append(
            {
                "packet_index": sequence.get("packet_index"),
                "source_event_ids": [
                    str(item.get("event_id") or "") for item in timeline if item.get("event_id")
                ],
                "preserve_packet_order": True,
            }
        )
    cannot_text = " ".join(_safe_string_list(sequence.get("cannot_claim"), limit=20)).casefold()
    if any(term in cannot_text for term in ("supersed", "extinct", "current_truth", "not_current")):
        risks["supersession_or_extinction"].append(
            {
                "packet_index": sequence.get("packet_index"),
                "safe_use": sequence.get("reopen_plan", {}).get("recommended_use"),
            }
        )


def _packet_action_grammar(
    *,
    hard_block: bool,
    only_blocked_routes: bool,
    has_reopenable_route: bool,
    has_direction_ref: bool,
    has_bounded_evidence: bool,
    bounded_evidence_only: bool,
    has_glyphs: bool,
) -> str:
    if hard_block or only_blocked_routes:
        return ACTION_IGNORE_OR_BLOCKED
    if has_reopenable_route:
        return ACTION_REOPENABLE_ROUTE
    if has_direction_ref:
        return ACTION_DIRECTION_WITH_REF
    if has_bounded_evidence and bounded_evidence_only:
        return ACTION_BOUNDED_EVIDENCE
    if has_glyphs:
        return ACTION_DIRECTION_ONLY
    return ACTION_IGNORE_OR_BLOCKED


def _trust_level_for_packet(action_grammar: str) -> str:
    if action_grammar == ACTION_IGNORE_OR_BLOCKED:
        return TRUST_IGNORE
    if action_grammar == ACTION_REOPENABLE_ROUTE:
        return TRUST_SOURCE_REQUIRED
    if action_grammar == ACTION_DIRECTION_WITH_REF:
        return TRUST_CANDIDATE_BACKED
    if action_grammar == ACTION_BOUNDED_EVIDENCE:
        return TRUST_BOUNDED_EVIDENCE
    if action_grammar == ACTION_SOURCE_OPEN:
        return TRUST_RAW_SOURCE_REOPENED
    return TRUST_SCENT


def _mapping_items(value: Any, *, limit: int) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        items: Sequence[Any] = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = value
    else:
        items = []
    return [item for item in items[:limit] if isinstance(item, Mapping)]


def _active_path_rows(value: Mapping[str, Any] | None, *, limit: int) -> list[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    return _mapping_items(value.get("paths"), limit=limit)


def _safe_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _safe_string_list(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str):
        items: Sequence[Any] = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = value
    else:
        items = []
    return unique_preserve([_safe_text(item, limit=180) for item in items], limit=limit)


def _status(row: Mapping[str, Any]) -> str:
    return _safe_text(row.get("status") or row.get("currentness") or "active", limit=40).casefold() or "active"


def _is_blocked(row: Mapping[str, Any]) -> bool:
    status = _status(row)
    action = str(row.get("action_grammar") or "")
    route = str(row.get("route") or "").casefold()
    source_boundary = dict_or_empty(row.get("source_boundary"))
    return bool(
        status in BLOCKED_STATUSES
        or action == ACTION_IGNORE_OR_BLOCKED
        or route == "ignore"
        or source_boundary.get("unsafe_to_use_as_current_fact")
    )


def _boundary_is_hard(row: Mapping[str, Any]) -> bool:
    strength = str(row.get("strength") or "").casefold()
    effect = str(row.get("effect") or "").casefold()
    return strength == "hard" and effect in HARD_BOUNDARY_EFFECTS


def _has_hard_boundary(row: Mapping[str, Any]) -> bool:
    return any(
        _boundary_is_hard(item)
        for item in _mapping_items(row.get("pinned_boundary_conditions"), limit=12)
    )


def _safe_reopen_plan(value: Any) -> dict[str, Any]:
    plan = value if isinstance(value, Mapping) else {}
    return {
        "status": _safe_text(plan.get("status"), limit=40) or "needs_context",
        "recommended_tool": _safe_text(plan.get("recommended_tool"), limit=80),
        "arguments": dict(plan.get("arguments") or {}) if isinstance(plan.get("arguments"), Mapping) else {},
        "manual_query_invention_expected": bool(plan.get("manual_query_invention_expected")),
    }


def _safe_current_assessment(value: Any) -> dict[str, Any]:
    row = value if isinstance(value, Mapping) else {}
    return {
        "source_thickness": _safe_text(row.get("source_thickness"), limit=40),
        "freshness": _safe_text(row.get("freshness"), limit=40),
        "proposed_use": _safe_text(row.get("proposed_use"), limit=80),
        "truth_boundary": _safe_text(row.get("truth_boundary"), limit=120)
        or "derived_weather_not_source_fact",
    }


def _ref_marker(ref: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in ref.items()))


def _dedupe_refs(value: Any, *, limit: int) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    _extend_refs(refs, value, limit=limit)
    return refs


def _extend_refs(target: list[dict[str, Any]], value: Any, *, limit: int = 48) -> None:
    seen = {_ref_marker(ref) for ref in target}
    for ref in safe_source_refs(value):
        marker = _ref_marker(ref)
        if marker in seen:
            continue
        seen.add(marker)
        target.append(ref)
        if len(target) >= limit:
            return
