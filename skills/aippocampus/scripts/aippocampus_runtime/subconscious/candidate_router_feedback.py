"""Feedback pressure helpers for subconscious candidate routing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.feedback import events as feedback_events

PARK = "park"
USE_SILENTLY = "use_silently"
USE_WITH_SOURCE = "use_with_source"


def feedback_ids_for(entry: dict[str, Any], candidate: dict[str, Any]) -> set[str]:
    ids = {
        str(entry.get("candidate_key") or ""),
        str(entry.get("trigger_id") or ""),
        str(entry.get("route_id") or ""),
        str(candidate.get("candidate_id") or ""),
        str(candidate.get("route_id") or ""),
        str(candidate.get("trigger_id") or ""),
    }
    ids.update(str(value) for value in candidate.get("source_finding_ids") or [])
    return {value for value in ids if value}


def relevant_feedback_rows(
    entry: dict[str, Any], candidate: dict[str, Any], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ids = feedback_ids_for(entry, candidate)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        route_id = str(row.get("route_id") or row.get("candidate_id") or "")
        if route_id in ids:
            out.append(row)
    return out


def _safe_alias(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    safe = redact_sensitive_values(redact_private_paths(text)).strip()
    if safe != text or "\\" in safe or "/" in safe:
        return ""
    return safe[:72]


def merged_aliases_from_feedback(
    entry: dict[str, Any], candidate: dict[str, Any], rows: list[dict[str, Any]]
) -> list[str]:
    aliases: list[str] = []
    seen = {str(value).casefold() for value in entry.get("aliases") or []}
    for row in relevant_feedback_rows(entry, candidate, rows):
        if row.get("kind") != feedback_events.ALIAS_MERGE_EVENT_KIND:
            continue
        for raw_alias in row.get("aliases") or row.get("merge_aliases") or []:
            alias = _safe_alias(raw_alias)
            key = alias.casefold()
            if alias and key not in seen:
                aliases.append(alias)
                seen.add(key)
    return aliases


def suppression_cues_from_feedback(
    entry: dict[str, Any], candidate: dict[str, Any], rows: list[dict[str, Any]]
) -> list[str]:
    cues: list[str] = []
    seen = {str(value).casefold() for value in entry.get("negative_cues") or []}
    for row in relevant_feedback_rows(entry, candidate, rows):
        if row.get("kind") != feedback_events.CONTEXT_SUPPRESSION_EVENT_KIND:
            continue
        for raw_cue in row.get("context_cues") or row.get("negative_cues") or []:
            cue = _safe_alias(raw_cue)
            key = cue.casefold()
            if cue and key not in seen:
                cues.append(cue)
                seen.add(key)
    return cues


def apply_alias_merge_feedback(
    entry: dict[str, Any], candidate: dict[str, Any], feedback_rows: list[dict[str, Any]]
) -> None:
    aliases = merged_aliases_from_feedback(entry, candidate, feedback_rows)
    if not aliases:
        return
    existing = [str(value) for value in entry.get("aliases") or [] if str(value)]
    entry["aliases"] = [*existing, *aliases]
    if "trigger_terms" in entry:
        existing_terms = [str(value) for value in entry.get("trigger_terms") or [] if str(value)]
        term_seen = {value.casefold() for value in existing_terms}
        for alias in aliases:
            key = alias.casefold()
            if key not in term_seen:
                existing_terms.append(alias)
                term_seen.add(key)
        entry["trigger_terms"] = existing_terms[:18]
    adjustment = entry.setdefault("feedback_adjustment", {})
    adjustment["alias_merge_count"] = int(adjustment.get("alias_merge_count") or 0) + len(aliases)
    adjustment["source_refs_preserved"] = True
    adjustment["source_truth_changed"] = False
    entry.setdefault("routing_diagnostics", {})["feedback_alias_merged"] = True


def apply_context_suppression_feedback(
    entry: dict[str, Any], candidate: dict[str, Any], feedback_rows: list[dict[str, Any]]
) -> None:
    cues = suppression_cues_from_feedback(entry, candidate, feedback_rows)
    if not cues:
        return
    existing = [str(value) for value in entry.get("negative_cues") or [] if str(value)]
    entry["negative_cues"] = [*existing, *cues]
    adjustment = entry.setdefault("feedback_adjustment", {})
    adjustment["context_suppression_count"] = (
        int(adjustment.get("context_suppression_count") or 0) + len(cues)
    )
    adjustment["source_refs_preserved"] = True
    adjustment["source_truth_changed"] = False
    diagnostics = entry.setdefault("routing_diagnostics", {})
    diagnostics["feedback_context_suppressed"] = True
    diagnostics["reason_class"] = str(diagnostics.get("reason_class") or "feedback_context_suppressed")


def apply_feedback_adjustment(
    entry: dict[str, Any],
    candidate: dict[str, Any],
    feedback_rows: list[dict[str, Any]],
    *,
    ask_policy_for: Callable[[str], str],
) -> None:
    relevant = relevant_feedback_rows(entry, candidate, feedback_rows)
    apply_alias_merge_feedback(entry, candidate, feedback_rows)
    apply_context_suppression_feedback(entry, candidate, feedback_rows)
    prior_adjustment = dict(entry.get("feedback_adjustment") or {})
    if not relevant:
        return
    report = feedback_events.active_flow_activation_report(relevant)
    routes = report.get("routes") or []
    if not routes:
        return
    route = routes[0]
    adjustment = {
        **prior_adjustment,
        "activation_score": route.get("activation_score"),
        "event_count": route.get("event_count"),
        "signal_counts": route.get("signal_counts") or {},
        "foreground_eligible": bool(route.get("foreground_eligible")),
        "reason_codes": route.get("reason_codes") or [],
        "source_refs_preserved": True,
        "source_truth_changed": False,
    }
    entry["feedback_adjustment"] = adjustment
    score = float(route.get("activation_score") or 0.0)
    if not route.get("foreground_eligible") and score <= 0:
        entry["status"] = "parked"
        entry["route"] = PARK
        entry["foreground_policy"] = PARK
        entry["ask_policy"] = ask_policy_for(PARK)
        entry["route_reason"] = "suppressed by same-route feedback; source refs remain auditable"
        entry["routing_reason_class"] = "feedback_suppressed"
        entry["routing_diagnostics"]["reason_class"] = "feedback_suppressed"
        return
    if score > 0 and entry.get("status") == "active" and entry.get("route") == USE_SILENTLY:
        entry["route"] = USE_WITH_SOURCE
        entry["foreground_policy"] = USE_WITH_SOURCE
        entry["ask_policy"] = ask_policy_for(USE_WITH_SOURCE)
        entry["route_reason"] = "positive route feedback promoted navigation pressure"
        entry["routing_diagnostics"]["feedback_promoted"] = True
