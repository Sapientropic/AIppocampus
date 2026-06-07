#!/usr/bin/env python3
"""Cross-Journey Dream bridge helpers.

Journey bridge hypotheses are deliberately narrower than ordinary amplification:
they may suggest a route or unblock condition, but they remain Dream probes.
The guard here keeps the creative part source-carried, falsifiable, and unable
to harden into a profile/personality claim without human review.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.dream.risk_terms import dream_text_hard_risk
from aippocampus_runtime.dream.source_refs import source_ref_key

BRIDGE_STATUS = "dream_bridge_not_source_fact"
BRIDGE_KINDS = {
    "shared_blockage",
    "shared_unblock_condition",
    "frontier_rhyme",
    "counterpath",
}

ResolveRefs = Callable[[object, Mapping[str, dict[str, Any]]], list[dict[str, Any]]]


def _present(value: object) -> bool:
    return value is not None and value != "" and value != []


def _unique_preserve(values: Iterable[object], *, limit: int, max_chars: int = 180) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = compact_text(str(value or ""), max_chars)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _string_list(value: object, *, limit: int, max_chars: int = 180) -> list[str]:
    if isinstance(value, str):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    return _unique_preserve(raw_items, limit=limit, max_chars=max_chars)


def _clean_source_refs(value: object, *, limit: int = 8) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        key = source_ref_key(item)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in dict(item).items() if _present(v)})
        if len(refs) >= limit:
            break
    return refs


def _has_two_source_sides(refs: list[dict[str, Any]]) -> bool:
    thread_keys = {str(ref.get("thread_key") or ref.get("thread_id") or "") for ref in refs}
    thread_keys.discard("")
    return len(thread_keys) >= 2 or len({source_ref_key(ref) for ref in refs}) >= 2


def _shared_pattern_is_weak(text: str) -> bool:
    tokens = [part for part in text.replace("/", " ").replace("-", " ").split() if part]
    return len(tokens) < 4


def normalized_journey_bridge_hypothesis(
    candidate: Mapping[str, Any],
    *,
    dream_function: str,
    by_id: Mapping[str, dict[str, Any]],
    resolve_refs: ResolveRefs,
) -> tuple[dict[str, Any] | None, list[str], bool]:
    raw = candidate.get("journey_bridge_hypothesis")
    if raw is None:
        return None, [], False
    if not isinstance(raw, Mapping):
        return None, ["journey_bridge_not_object"], False

    failures: list[str] = []
    if dream_function != "amplification":
        failures.append("journey_bridge_unsupported_dream_function")
    bridge_kind = str(raw.get("bridge_kind") or "")
    if bridge_kind not in BRIDGE_KINDS:
        failures.append("journey_bridge_invalid_kind")
    status = str(raw.get("status") or "")
    if status != BRIDGE_STATUS:
        failures.append("journey_bridge_invalid_status")

    source_journey_refs = _string_list(raw.get("source_journey_refs"), limit=4, max_chars=120)
    if len(source_journey_refs) < 2:
        failures.append("journey_bridge_missing_source_journey_refs")

    refs = resolve_refs(raw.get("source_ref_ids"), by_id)
    if not _has_two_source_sides(refs):
        failures.append("journey_bridge_missing_source_refs_from_both_sides")

    shared_pattern = compact_text(str(raw.get("shared_pattern") or ""), 260)
    possible_reason = compact_text(str(raw.get("possible_reason") or ""), 360)
    unblock_condition = compact_text(str(raw.get("unblock_condition") or ""), 300)
    if not shared_pattern:
        failures.append("journey_bridge_missing_shared_pattern")
    elif _shared_pattern_is_weak(shared_pattern):
        failures.append("journey_bridge_shared_pattern_too_weak")
    if not possible_reason:
        failures.append("journey_bridge_missing_possible_reason")
    if not unblock_condition:
        failures.append("journey_bridge_missing_unblock_condition")

    falsification_cues = _string_list(
        raw.get("falsification_cues") or raw.get("counter_evidence"),
        limit=6,
        max_chars=180,
    )
    if not falsification_cues:
        failures.append("journey_bridge_missing_falsification_cues")

    sensitive_risk = dream_text_hard_risk(
        shared_pattern,
        possible_reason,
        unblock_condition,
        " ".join(falsification_cues),
    )
    if sensitive_risk:
        failures.append("sensitive_or_profile_journey_bridge_requires_human_review")

    bridge = {
        "bridge_kind": bridge_kind,
        "source_journey_refs": source_journey_refs,
        "shared_pattern": shared_pattern,
        "possible_reason": possible_reason,
        "unblock_condition": unblock_condition,
        "falsification_cues": falsification_cues,
        "status": BRIDGE_STATUS,
        "truth_boundary": BRIDGE_STATUS,
        "source_refs": refs[:8],
        "foreground_use": "journey_unblock_probe_not_evidence",
        "requires_source_reopen_before_claim": True,
    }
    return {key: value for key, value in bridge.items() if _present(value)}, failures, sensitive_risk


def normalized_bridge(
    candidate: Mapping[str, Any],
    dream_function: str,
    by_id: Mapping[str, dict[str, Any]],
    resolve_refs: ResolveRefs,
) -> tuple[dict[str, Any] | None, list[str], bool]:
    return normalized_journey_bridge_hypothesis(
        candidate,
        dream_function=dream_function,
        by_id=by_id,
        resolve_refs=resolve_refs,
    )


def attach_journey_bridge_to_finding(
    finding: dict[str, Any],
    bridge: Mapping[str, Any] | None,
) -> None:
    if not bridge:
        return
    finding["journey_bridge_hypothesis"] = dict(bridge)
    finding["downstream_use"] = ["working_memory", "ambient_recall_card", "reflection_space"]


def clean_journey_bridge_hypothesis(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping) or str(raw.get("status") or "") != BRIDGE_STATUS:
        return None
    bridge_kind = str(raw.get("bridge_kind") or "")
    if bridge_kind not in BRIDGE_KINDS:
        return None
    bridge = {
        "bridge_kind": bridge_kind,
        "source_journey_refs": _string_list(raw.get("source_journey_refs"), limit=4, max_chars=120),
        "shared_pattern": compact_text(str(raw.get("shared_pattern") or ""), 260),
        "possible_reason": compact_text(str(raw.get("possible_reason") or ""), 360),
        "unblock_condition": compact_text(str(raw.get("unblock_condition") or ""), 300),
        "falsification_cues": _string_list(raw.get("falsification_cues"), limit=6),
        "status": BRIDGE_STATUS,
        "truth_boundary": BRIDGE_STATUS,
        "source_refs": _clean_source_refs(raw.get("source_refs"), limit=8),
        "foreground_use": "journey_unblock_probe_not_evidence",
        "requires_source_reopen_before_claim": bool(
            raw.get("requires_source_reopen_before_claim") is not False
        ),
    }
    return {key: value for key, value in bridge.items() if _present(value)}


def journey_bridge_present_is_valid(raw: object) -> bool:
    return raw is None or bool(clean_journey_bridge_hypothesis(raw))


def journey_bridge_trigger_terms(raw: object) -> list[str]:
    bridge = clean_journey_bridge_hypothesis(raw)
    if not bridge:
        return []
    return _unique_preserve(
        [
            bridge.get("unblock_condition"),
            bridge.get("shared_pattern"),
            bridge.get("possible_reason"),
            *bridge.get("source_journey_refs", []),
        ],
        limit=8,
        max_chars=120,
    )


def clean_journey_bridge_from_finding(finding: Mapping[str, Any]) -> dict[str, Any] | None:
    return clean_journey_bridge_hypothesis(finding.get("journey_bridge_hypothesis"))


def trigger_terms_with_journey_bridge(
    trigger_terms: Iterable[object],
    bridge: Mapping[str, Any] | None,
) -> list[str]:
    return _unique_preserve(
        [*trigger_terms, *journey_bridge_trigger_terms(bridge)],
        limit=12,
        max_chars=120,
    )


def add_journey_bridge_foreground_use(
    foreground_use: dict[str, Any],
    bridge: Mapping[str, Any] | None,
) -> None:
    if bridge:
        foreground_use["journey_bridge_action"] = "optional_unblock_probe_on_trigger"


def attach_journey_bridge_to_row(row: dict[str, Any], bridge: Mapping[str, Any] | None) -> None:
    if bridge:
        row["journey_bridge_hypothesis"] = dict(bridge)


def journey_bridge_match_use(row: Mapping[str, Any]) -> dict[str, Any] | None:
    bridge = clean_journey_bridge_hypothesis(row.get("journey_bridge_hypothesis"))
    if not bridge or not bridge.get("unblock_condition"):
        return None
    return {
        "action": "deliver_as_optional_unblock_probe",
        "reason": "matched_journey_bridge_trigger",
        "journey_bridge_diagnostic": "delivered_as_optional_unblock_probe",
        "truth_boundary": bridge.get("truth_boundary") or row.get("truth_boundary"),
        "strong_claim_requires_source_reopen": True,
        "render_boundary": BRIDGE_STATUS,
        "bridge_kind": bridge.get("bridge_kind"),
        "unblock_condition": bridge.get("unblock_condition"),
        "source_journey_refs": bridge.get("source_journey_refs") or [],
    }


def render_journey_bridge_preview(row: Mapping[str, Any]) -> str | None:
    journey_bridge = clean_journey_bridge_hypothesis(row.get("journey_bridge_hypothesis"))
    if not journey_bridge:
        return None
    unblock = compact_text(str(journey_bridge.get("unblock_condition") or ""), 180)
    return (
        f"Journey bridge Dream hypothesis, not source fact: {unblock}. "
        "Use only as an optional unblock probe; reopen source before strong claims."
    )


def journey_bridge_delivery_plan(
    row: Mapping[str, Any],
    *,
    trust_horizon_status: str,
    matched_prompt_terms: list[str],
) -> dict[str, Any] | None:
    bridge = clean_journey_bridge_hypothesis(row.get("journey_bridge_hypothesis"))
    if not bridge or not bridge.get("unblock_condition"):
        return None
    return {
        "action": "deliver_as_optional_unblock_probe",
        "reason": "journey_bridge_trigger_matched",
        "journey_bridge_diagnostic": "delivered_as_optional_unblock_probe",
        "route": "working_memory",
        "requires_source_reopen": bool(bridge.get("requires_source_reopen_before_claim")),
        "truth_boundary": bridge.get("truth_boundary") or row.get("truth_boundary"),
        "trust_horizon_status": trust_horizon_status,
        "bridge_kind": bridge.get("bridge_kind"),
        "unblock_condition": bridge.get("unblock_condition"),
        "source_journey_refs": bridge.get("source_journey_refs") or [],
        "render_boundary": BRIDGE_STATUS,
        "matched_prompt_terms": matched_prompt_terms,
    }


def journey_bridge_delivery_plan_for_prompt(
    row: Mapping[str, Any],
    trust_horizon_status: str,
    matched_prompt_terms: list[str],
) -> dict[str, Any] | None:
    return journey_bridge_delivery_plan(
        row,
        trust_horizon_status=trust_horizon_status,
        matched_prompt_terms=matched_prompt_terms,
    )
