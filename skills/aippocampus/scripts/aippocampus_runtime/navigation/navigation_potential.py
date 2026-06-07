#!/usr/bin/env python3
"""Project source-backed navigation routes into bounded action affordances.

The cognitive map says where a route points. The navigation-potential projection
adds the prompt-time question: what, if anything, can the foreground agent do
with that route now? It remains a navigation layer. Source refs and clean source
still own factual claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.navigation.repo_familiarity import navigation_routes_from_cards
from aippocampus_runtime.question.source_refs import compact_source_refs, source_ref_key
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 1
PROJECTION_KIND = "aippocampus_navigation_potential_projection"
POTENTIAL_KIND = "aippocampus_navigation_potential"

STATUSES = {
    "open",
    "unresolved",
    "blocked",
    "superseded",
    "corrected",
    "stale",
    "resolved",
}
STATUS_RANK = {
    "blocked": 80,
    "superseded": 76,
    "corrected": 72,
    "resolved": 68,
    "stale": 56,
    "unresolved": 44,
    "open": 20,
}
TERMINAL_SUPPRESSED_STATUSES = {"blocked", "superseded", "resolved"}

AFFORDANCES = {
    "silent",
    "backstage_prepare",
    "state_check",
    "light_nudge",
    "offer_next_step",
    "surface_warning",
}

ACTION_GRAMMAR = {
    "direction_only",
    "reopenable_route",
    "bounded_evidence",
    "source_open",
    "ignore_or_blocked",
}

SOURCE_THICKNESS_RANK = {"thin": 0, "usable": 1, "strong": 2}
NEGATIVE_FEEDBACK_OUTCOMES = {"ignored", "dismissed", "corrected"}


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return f"{prefix}_{_sha1(raw)[:length]}"


def _text(value: Any, limit: int = 220) -> str:
    return compact_text(str(value or "").strip(), limit)


def _strings(value: Any, *, limit: int = 12, chars: int = 120) -> list[str]:
    if isinstance(value, str):
        raw_items: Iterable[Any] = [value]
    elif isinstance(value, Sequence):
        raw_items = value
    else:
        raw_items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _text(item, chars)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _source_refs(*values: Any, limit: int = 12) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for value in values:
        for ref in compact_source_refs(value or [], limit=limit):
            key = source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
            if len(refs) >= limit:
                return refs
    return refs


def _ref_keys(refs: Sequence[Mapping[str, Any]]) -> set[tuple[str, str, str, str]]:
    return {source_ref_key(ref) for ref in refs if source_ref_key(ref)[0]}


def _thread_keys_from_refs(refs: Sequence[Mapping[str, Any]]) -> list[str]:
    return unique_preserve(
        [str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key")],
        limit=16,
    )


def _source_thickness(refs: Sequence[Mapping[str, Any]], explicit: Any = None) -> str:
    text = str(explicit or "").strip()
    if text in SOURCE_THICKNESS_RANK:
        return text
    if len(refs) >= 3:
        return "strong"
    if refs:
        return "usable"
    return "thin"


def _status(value: Any, fallback: str = "open") -> str:
    text = str(value or fallback).strip()
    aliases = {
        "active": "open",
        "candidate": "open",
        "pending": "unresolved",
        "frontier": "unresolved",
        "open_frontier": "unresolved",
        "terminal": "resolved",
        "arrived": "resolved",
        "abandoned": "blocked",
        "merged": "superseded",
    }
    text = aliases.get(text, text)
    return text if text in STATUSES else fallback


def _route_id(route: Mapping[str, Any]) -> str:
    for key in ("route_id", "id", "card_id", "journey_id", "affordance_id"):
        value = _text(route.get(key), 120)
        if value:
            return value
    return stable_id("nav_route", route.get("title"), route.get("summary"), route.get("source_refs"))


def _route_title(route: Mapping[str, Any]) -> str:
    return _text(
        route.get("title")
        or route.get("landmark")
        or route.get("path_label")
        or route.get("core_inquiry")
        or route.get("route_kind")
        or _route_id(route),
        140,
    )


def _route_summary(route: Mapping[str, Any]) -> str:
    return _text(
        route.get("summary")
        or route.get("current_frontier")
        or route.get("action_delta_required")
        or route.get("why_now")
        or _route_title(route),
        520,
    )


def _route_terms(route: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in (
        "route_cues",
        "matched_cues",
        "query_terms",
        "landmark_labels",
        "region_labels",
        "active_questions",
        "route_terms",
    ):
        terms.extend(_strings(route.get(key), limit=24, chars=120))
    terms.extend(_strings([_route_title(route), _route_summary(route)], limit=8, chars=120))
    return unique_preserve(terms, limit=48)


def _row_terms(row: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in (
        "route_cues",
        "matched_cues",
        "query_terms",
        "landmark_labels",
        "region_labels",
        "active_questions",
        "route_terms",
        "src",
        "dst",
        "label",
        "title",
        "summary",
        "current_frontier",
        "frontier",
        "why_now",
    ):
        terms.extend(_strings(row.get(key), limit=24, chars=120))
    return unique_preserve(terms, limit=48)


def _thread_keys(row: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> list[str]:
    explicit = _strings(row.get("thread_keys") or row.get("target_thread_keys"), limit=20)
    for key in ("thread_key", "thread_id", "source_thread_key"):
        value = _text(row.get(key), 120)
        if value:
            explicit.append(value)
    return unique_preserve([*explicit, *_thread_keys_from_refs(refs)], limit=24)


def _id_values(row: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in (
        "route_id",
        "id",
        "card_id",
        "journey_id",
        "affordance_id",
        "ticket_id",
        "source_finding_id",
        "src_route_id",
        "dst_route_id",
        "target_route_id",
        "superseded_route_id",
        "blocked_route_id",
        "corrected_route_id",
    ):
        value = _text(row.get(key), 160)
        if value:
            values.add(value)
    raw_source_ids = row.get("source_ids")
    if isinstance(raw_source_ids, Sequence) and not isinstance(raw_source_ids, (str, bytes)):
        values.update(_text(item, 160) for item in raw_source_ids if _text(item, 160))
    scope = row.get("scope")
    if isinstance(scope, Mapping):
        stable = _text(scope.get("stable_id"), 160)
        if stable:
            values.add(stable)
    return values


def _signal(
    *,
    source: str,
    signal: str,
    effect: str,
    detail: str = "",
    matched_by: Sequence[str] = (),
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": source,
        "signal": signal,
        "effect": effect,
    }
    if detail:
        payload["detail"] = _text(detail, 220)
    matched = unique_preserve([str(item) for item in matched_by if item], limit=6)
    if matched:
        payload["matched_by"] = matched
    return payload


def _match_row_to_route(
    row: Mapping[str, Any],
    *,
    route_id: str,
    route_terms: Sequence[str],
    route_refs: Sequence[Mapping[str, Any]],
    route_threads: Sequence[str],
) -> tuple[bool, list[str], bool]:
    """Return whether a sidecar row belongs to a route.

    A term-only match can orient diagnostics, but it should not be enough to
    promote source-thin scent into foreground action. Callers receive the
    term-only flag and downgrade accordingly.
    """

    matched_by: list[str] = []
    row_ids = _id_values(row)
    if route_id and route_id in row_ids:
        matched_by.append("route_id")
    for link_key in ("dst_route_id", "target_route_id", "superseded_route_id", "blocked_route_id", "corrected_route_id"):
        if _text(row.get(link_key), 160) == route_id:
            matched_by.append(link_key)

    row_refs = _source_refs(
        row.get("source_refs"),
        row.get("evidence_refs"),
        row.get("clean_source_refs"),
        limit=12,
    )
    if _ref_keys(route_refs) & _ref_keys(row_refs):
        matched_by.append("source_ref")

    row_threads = set(_thread_keys(row, row_refs))
    if row_threads and set(route_threads) & row_threads:
        matched_by.append("thread_key")

    route_term_set = {term.casefold() for term in route_terms if len(term) >= 3}
    row_term_set = {term.casefold() for term in _row_terms(row) if len(term) >= 3}
    if route_term_set and row_term_set and route_term_set & row_term_set:
        matched_by.append("term")

    # Route ids, source refs, and thread ids are source-reachable handles. Terms
    # alone are only scent and must not be treated as evidence of actionability.
    strong_match = bool(set(matched_by) - {"term"})
    return bool(matched_by), unique_preserve(matched_by, limit=8), not strong_match


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_time(*values: Any) -> str:
    times: list[datetime] = []
    for value in values:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                parsed = _parse_time(item)
                if parsed:
                    times.append(parsed)
        else:
            parsed = _parse_time(value)
            if parsed:
                times.append(parsed)
    if not times:
        return ""
    return max(times).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _route_last_visited(route: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> str:
    explicit = _latest_time(
        route.get("last_visited"),
        route.get("updated_at"),
        route.get("created_at"),
        [ref.get("timestamp") for ref in refs if isinstance(ref, Mapping)],
    )
    return explicit


def _route_visit_count(route: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> int:
    raw = route.get("visit_count")
    if raw is not None:
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            pass
    return max(0, len(set(_thread_keys(route, refs))) or len(refs))


def _apply_status(current: str, candidate: str) -> str:
    candidate = _status(candidate, fallback=current)
    return candidate if STATUS_RANK[candidate] > STATUS_RANK[current] else current


def _edge_effect(edge: Mapping[str, Any], *, route_id: str) -> tuple[str, str] | None:
    edge_type = str(edge.get("edge_type") or edge.get("type") or "").strip()
    status = _status(edge.get("status"), fallback="")
    dst_route_id = _text(edge.get("dst_route_id") or edge.get("target_route_id"), 160)
    src_route_id = _text(edge.get("src_route_id"), 160)

    if edge_type == "supersedes":
        if dst_route_id == route_id or _text(edge.get("superseded_route_id"), 160) == route_id:
            return "superseded", "supersedes_edge_targets_route"
        if src_route_id == route_id:
            return "open", "route_supersedes_another"
    if status == "blocked" or edge_type in {"blocked_by", "blocks"}:
        return "blocked", edge_type or "blocked_edge"
    if edge_type == "depends_on" and status in {"blocked", "stale"}:
        return "blocked", "blocked_dependency"
    if status in {"superseded", "resolved", "stale"}:
        return status, f"concept_edge_status:{status}"
    return None


def _journey_effect(journey: Mapping[str, Any]) -> tuple[str, str, str]:
    status = str(journey.get("status") or "").strip()
    if status == "abandoned":
        return "blocked", "low", "abandoned_journey"
    if status == "arrived":
        return "resolved", "low", "arrived_journey"
    if status == "camped":
        return "unresolved", "high", "camped_frontier"
    if status == "traveling":
        return "unresolved", "high", "traveling_frontier"
    return "open", "medium", "journey_candidate"


def _annoyance_risk(
    *,
    explicit: Any,
    source_thickness: str,
    negative_feedback_count: int,
    correction_count: int,
    affordance: str,
) -> str:
    text = str(explicit or "").strip()
    if text in {"low", "medium", "high"}:
        return text
    if negative_feedback_count > 0 or correction_count > 0:
        return "high"
    if source_thickness == "thin":
        return "medium"
    if affordance in {"surface_warning", "state_check"}:
        return "medium"
    return "low"


def _action_grammar(status: str, source_thickness: str, affordance: str) -> str:
    if status in TERMINAL_SUPPRESSED_STATUSES:
        return "ignore_or_blocked"
    if source_thickness == "thin":
        return "direction_only"
    if affordance == "surface_warning":
        return "reopenable_route"
    if source_thickness == "strong":
        return "bounded_evidence"
    return "reopenable_route"


def _proposed_action(affordance: str, route: Mapping[str, Any], *, status: str) -> dict[str, str]:
    raw_action = route.get("proposed_action")
    if isinstance(raw_action, Mapping):
        verb = _text(raw_action.get("verb"), 80)
        obj = _text(raw_action.get("object"), 260)
        if verb and obj:
            if affordance == "backstage_prepare":
                return {"verb": "refresh_sources", "object": obj}
            if affordance == "surface_warning" and not verb.startswith("warn"):
                return {"verb": "warn_route", "object": obj}
            return {"verb": verb, "object": obj}
    summary = _route_summary(route)
    title = _route_title(route)
    obj = compact_text(summary or title, 220)
    if affordance == "surface_warning":
        return {
            "verb": "warn_route",
            "object": obj,
        }
    if affordance == "offer_next_step":
        return {
            "verb": "offer_next_step",
            "object": obj,
        }
    if affordance == "state_check":
        return {
            "verb": "ask_state_check",
            "object": obj,
        }
    if affordance == "light_nudge":
        return {
            "verb": "summarize_route_anchor",
            "object": obj,
        }
    if affordance == "backstage_prepare":
        return {
            "verb": "refresh_sources",
            "object": obj,
        }
    return {
        "verb": "stay_silent",
        "object": compact_text(status or title, 120),
    }


def _choose_affordance(
    *,
    status: str,
    source_thickness: str,
    frontier_proximity: str,
    correction_count: int,
    negative_feedback_count: int,
    has_concrete_next_step: bool,
) -> str:
    # Suppression statuses should not become richer nudges. The point of this
    # projection is to prevent stale or superseded routes from being resurfaced
    # as if they were ordinary memory candidates.
    if status in TERMINAL_SUPPRESSED_STATUSES:
        return "silent"
    if status == "corrected" or correction_count:
        return "surface_warning" if source_thickness != "thin" else "state_check"
    if negative_feedback_count and frontier_proximity != "high":
        return "backstage_prepare"
    if status == "stale":
        return "backstage_prepare"
    if source_thickness == "thin":
        return "backstage_prepare"
    if frontier_proximity == "high" and status in {"open", "unresolved"} and has_concrete_next_step:
        return "offer_next_step"
    if status == "unresolved":
        return "state_check"
    return "backstage_prepare"


def _foreground_eligible(
    *,
    affordance: str,
    source_thickness: str,
    status: str,
    annoyance_risk: str,
    matched_terms_only: bool,
) -> bool:
    if affordance not in {"state_check", "light_nudge", "offer_next_step", "surface_warning"}:
        return False
    if status in TERMINAL_SUPPRESSED_STATUSES:
        return False
    if matched_terms_only:
        return False
    if source_thickness == "thin" and affordance != "state_check":
        return False
    if annoyance_risk == "high" and affordance not in {"state_check", "surface_warning"}:
        return False
    return True


def _route_has_next_step(route: Mapping[str, Any], signals: Sequence[Mapping[str, Any]]) -> bool:
    if _text(route.get("proposed_action") or route.get("action_delta_required") or route.get("current_frontier")):
        return True
    return any(
        signal.get("source") == "journey" and str(signal.get("effect") or "").startswith("frontier")
        for signal in signals
    )


def _explicit_base_status(route: Mapping[str, Any]) -> str:
    status = _status(route.get("status"), fallback="open")
    route_kind = str(route.get("route_kind") or "").casefold()
    if status == "open" and any(term in route_kind for term in ("frontier", "question", "unresolved")):
        return "unresolved"
    return status


def _potential_from_route(
    route: Mapping[str, Any],
    *,
    concept_edges: Sequence[Mapping[str, Any]],
    agency_affordances: Sequence[Mapping[str, Any]],
    agency_feedback: Sequence[Mapping[str, Any]],
    correction_windows: Sequence[Mapping[str, Any]],
    journeys: Sequence[Mapping[str, Any]],
    now: str,
) -> dict[str, Any] | None:
    route_id = _route_id(route)
    route_refs = _source_refs(
        route.get("source_refs"),
        route.get("evidence_refs"),
        route.get("clean_source_refs"),
        limit=12,
    )
    route_threads = _thread_keys(route, route_refs)
    terms = _route_terms(route)
    title = _route_title(route)
    summary = _route_summary(route)
    if not title and not summary and not route_refs:
        return None

    now_dt = _parse_time(now)
    status = _explicit_base_status(route)
    signals: list[dict[str, Any]] = []
    matched_terms_only = not route_refs
    frontier_proximity = str(route.get("frontier_proximity") or "low")
    correction_count = int(route.get("correction_count") or 0)
    negative_feedback_count = 0
    source_thickness = _source_thickness(route_refs, route.get("source_thickness"))

    expires_at = _parse_time(route.get("expires_at"))
    if expires_at and now_dt and expires_at < now_dt:
        status = _apply_status(status, "stale")
        signals.append(
            _signal(
                source="route",
                signal="expires_at",
                effect="status:stale",
                detail=str(route.get("expires_at") or ""),
            )
        )

    for edge in concept_edges:
        matched, matched_by, term_only = _match_row_to_route(
            edge,
            route_id=route_id,
            route_terms=terms,
            route_refs=route_refs,
            route_threads=route_threads,
        )
        if not matched:
            continue
        effect = _edge_effect(edge, route_id=route_id)
        if not effect:
            continue
        next_status, reason = effect
        status = _apply_status(status, next_status)
        matched_terms_only = matched_terms_only and term_only
        signals.append(
            _signal(
                source="concept_graph",
                signal=str(edge.get("edge_type") or edge.get("status") or "edge"),
                effect=f"status:{next_status}",
                detail=reason,
                matched_by=matched_by,
            )
        )

    for correction in correction_windows:
        matched, matched_by, term_only = _match_row_to_route(
            correction,
            route_id=route_id,
            route_terms=terms,
            route_refs=route_refs,
            route_threads=route_threads,
        )
        if not matched:
            continue
        status = _apply_status(status, "corrected")
        correction_count += 1
        matched_terms_only = matched_terms_only and term_only
        correction_refs = _source_refs(correction.get("source_refs"), correction.get("evidence_refs"))
        route_refs = _source_refs(route_refs, correction_refs, limit=12)
        source_thickness = _source_thickness(route_refs, route.get("source_thickness"))
        signals.append(
            _signal(
                source="correction_window",
                signal=str(correction.get("kind") or correction.get("trigger") or "correction"),
                effect="status:corrected",
                detail=correction.get("instruction") or correction.get("summary") or "",
                matched_by=matched_by,
            )
        )

    for feedback in agency_feedback:
        matched, matched_by, term_only = _match_row_to_route(
            feedback,
            route_id=route_id,
            route_terms=terms,
            route_refs=route_refs,
            route_threads=route_threads,
        )
        if not matched:
            continue
        outcome = str(feedback.get("outcome") or "")
        if outcome in NEGATIVE_FEEDBACK_OUTCOMES:
            negative_feedback_count += 1
        if outcome == "corrected":
            status = _apply_status(status, "corrected")
            correction_count += 1
        matched_terms_only = matched_terms_only and term_only
        signals.append(
            _signal(
                source="agency_feedback",
                signal=outcome or "feedback",
                effect="annoyance_or_correction_pressure",
                matched_by=matched_by,
            )
        )

    for agency_row in agency_affordances:
        matched, matched_by, term_only = _match_row_to_route(
            agency_row,
            route_id=route_id,
            route_terms=terms,
            route_refs=route_refs,
            route_threads=route_threads,
        )
        if not matched:
            continue
        level = str(agency_row.get("intervention_level") or "")
        if level in {"warning", "surface_warning"}:
            status = _apply_status(status, "corrected")
        matched_terms_only = matched_terms_only and term_only
        signals.append(
            _signal(
                source="agency_affordance",
                signal=level or "affordance",
                effect="existing_affordance_signal",
                matched_by=matched_by,
            )
        )

    for journey in journeys:
        matched, matched_by, term_only = _match_row_to_route(
            journey,
            route_id=route_id,
            route_terms=terms,
            route_refs=route_refs,
            route_threads=route_threads,
        )
        if not matched:
            continue
        next_status, proximity, reason = _journey_effect(journey)
        status = _apply_status(status, next_status)
        if proximity == "high" or frontier_proximity != "high":
            frontier_proximity = proximity
        matched_terms_only = matched_terms_only and term_only
        journey_refs = _source_refs(
            journey.get("current_frontier_source_refs"),
            journey.get("source_refs"),
            limit=12,
        )
        route_refs = _source_refs(route_refs, journey_refs, limit=12)
        source_thickness = _source_thickness(route_refs, route.get("source_thickness"))
        signals.append(
            _signal(
                source="journey",
                signal=str(journey.get("status") or "journey"),
                effect=f"frontier_proximity:{proximity}",
                detail=reason,
                matched_by=matched_by,
            )
        )

    source_thickness = _source_thickness(route_refs, route.get("source_thickness"))
    has_next_step = _route_has_next_step(route, signals)
    selected_affordance = _choose_affordance(
        status=status,
        source_thickness=source_thickness,
        frontier_proximity=frontier_proximity,
        correction_count=correction_count,
        negative_feedback_count=negative_feedback_count,
        has_concrete_next_step=has_next_step,
    )
    annoyance_risk = _annoyance_risk(
        explicit=route.get("annoyance_risk"),
        source_thickness=source_thickness,
        negative_feedback_count=negative_feedback_count,
        correction_count=correction_count,
        affordance=selected_affordance,
    )
    grammar = _action_grammar(status, source_thickness, selected_affordance)
    foreground_eligible = _foreground_eligible(
        affordance=selected_affordance,
        source_thickness=source_thickness,
        status=status,
        annoyance_risk=annoyance_risk,
        matched_terms_only=matched_terms_only,
    )

    route_thread_keys = _thread_keys(route, route_refs)
    potential = {
        "schema_version": SCHEMA_VERSION,
        "kind": POTENTIAL_KIND,
        "potential_id": stable_id(
            "nav_potential",
            route_id,
            status,
            selected_affordance,
            route_refs,
            length=20,
        ),
        "route_id": route_id,
        "source_kind": str(route.get("kind") or "cognitive_map_route"),
        "route_kind": route.get("route_kind") or route.get("category") or "navigation_route",
        "title": title,
        "summary": summary,
        "status": status,
        "affordance": selected_affordance,
        "action_grammar": grammar,
        "foreground_eligible": foreground_eligible,
        "proposed_action": _proposed_action(selected_affordance, route, status=status),
        "source_refs": route_refs,
        "source_thickness": source_thickness,
        "last_visited": _route_last_visited(route, route_refs),
        "visit_count": _route_visit_count(route, route_refs),
        "correction_count": correction_count,
        "frontier_proximity": frontier_proximity,
        "annoyance_risk": annoyance_risk,
        "thread_keys": route_thread_keys,
        "matched_terms_only": matched_terms_only,
        "requires_source_reopen": grammar in {"reopenable_route", "direction_only"},
        "preconditions": _strings(route.get("preconditions"), limit=8, chars=180),
        "do_not_do": _strings(route.get("do_not_do"), limit=10, chars=160),
        "diagnostics": {
            "raw_prompt_stored": False,
            "signal_count": len(signals),
            "signals": signals,
            "suppressed_reason": status if selected_affordance == "silent" else "",
        },
    }
    return potential


def build_navigation_potential_projection(
    *,
    cognitive_routes: Sequence[Mapping[str, Any]] | None = None,
    concept_edges: Sequence[Mapping[str, Any]] | None = None,
    agency_affordances: Sequence[Mapping[str, Any]] | None = None,
    agency_feedback: Sequence[Mapping[str, Any]] | None = None,
    correction_windows: Sequence[Mapping[str, Any]] | None = None,
    journeys: Sequence[Mapping[str, Any]] | None = None,
    repo_familiarity_cards: Sequence[Mapping[str, Any]] | None = None,
    topic_epoch: str = "default",
    now: str | None = None,
) -> dict[str, Any]:
    """Build a source-backed action projection over existing route sidecars."""

    now_value = now or now_utc()
    routes: list[Mapping[str, Any]] = list(cognitive_routes or [])
    routes.extend(navigation_routes_from_cards(repo_familiarity_cards or []))
    potentials = [
        potential
        for route in routes
        if isinstance(route, Mapping)
        for potential in [
            _potential_from_route(
                route,
                concept_edges=concept_edges or [],
                agency_affordances=agency_affordances or [],
                agency_feedback=agency_feedback or [],
                correction_windows=correction_windows or [],
                journeys=journeys or [],
                now=now_value,
            )
        ]
        if potential is not None
    ]
    potentials.sort(
        key=lambda item: (
            item.get("foreground_eligible") is True,
            SOURCE_THICKNESS_RANK.get(str(item.get("source_thickness") or "thin"), 0),
            STATUS_RANK.get(str(item.get("status") or "open"), 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PROJECTION_KIND,
        "created_at": now_value,
        "topic_epoch": topic_epoch,
        "potential_count": len(potentials),
        "foreground_eligible_count": len([item for item in potentials if item.get("foreground_eligible")]),
        "potentials": potentials,
        "agency_affordance_inputs": navigation_potentials_to_agency_inputs(potentials),
        "rules": {
            "navigation_not_truth": True,
            "source_refs_required_for_non_state_check_foreground": True,
            "source_thin_routes_are_direction_only": True,
            "suppressed_statuses": sorted(TERMINAL_SUPPRESSED_STATUSES),
            "raw_prompt_stored": False,
        },
    }


def _agency_level(affordance: str) -> str:
    aliases = {
        "surface_warning": "warning",
        "backstage_prepare": "backstage_only",
    }
    return aliases.get(affordance, affordance)


def _agency_trigger(potential: Mapping[str, Any]) -> str:
    status = str(potential.get("status") or "")
    affordance = str(potential.get("affordance") or "")
    if status == "corrected" or affordance == "surface_warning":
        return "user_correction"
    if affordance == "offer_next_step":
        return "compaction_loss"
    if affordance == "state_check":
        return "unfinished_task_reentry"
    return "compaction_loss"


def navigation_potentials_to_agency_inputs(
    potentials: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for potential in potentials:
        affordance = str(potential.get("affordance") or "")
        if affordance == "silent":
            continue
        raw_action = potential.get("proposed_action")
        action: Mapping[str, Any] = raw_action if isinstance(raw_action, Mapping) else {}
        rows.append(
            {
                "title": potential.get("title"),
                "summary": potential.get("summary") or action.get("object"),
                "intervention_level": _agency_level(affordance),
                "trigger": _agency_trigger(potential),
                "source_refs": potential.get("source_refs") or [],
                "source_thickness": potential.get("source_thickness"),
                "annoyance_risk": potential.get("annoyance_risk"),
                "matched_terms_only": potential.get("matched_terms_only"),
                "proposed_action": {
                    "verb": action.get("verb") or "refresh_sources",
                    "object": action.get("object") or potential.get("summary") or "",
                },
                "why_now": {
                    "trigger": _agency_trigger(potential),
                    "explanation": compact_text(
                        f"{potential.get('status')} route projected to {affordance}: {potential.get('title')}",
                        220,
                    ),
                },
                "preconditions": [
                    "reopen attached source refs before exact or high-risk claims",
                    *[
                        str(item)
                        for item in potential.get("preconditions") or []
                        if str(item).strip()
                    ],
                ],
                "do_not_do": [
                    "treat_navigation_potential_as_source_truth",
                    *[str(item) for item in potential.get("do_not_do") or [] if str(item).strip()],
                ],
            }
        )
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build AIppocampus navigation-potential projection.")
    parser.add_argument("--input", required=True, help="JSON object with route and sidecar rows.")
    parser.add_argument("--output", help="Optional output JSON path.")
    parser.add_argument("--topic-epoch", default="default")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    raw = _load_json(Path(args.input))
    projection = build_navigation_potential_projection(
        cognitive_routes=raw.get("cognitive_routes") or raw.get("routes") or [],
        concept_edges=raw.get("concept_edges") or [],
        agency_affordances=raw.get("agency_affordances") or [],
        agency_feedback=raw.get("agency_feedback") or raw.get("agency_feedback_events") or [],
        correction_windows=raw.get("correction_windows") or [],
        journeys=raw.get("journeys") or [],
        repo_familiarity_cards=raw.get("repo_familiarity_cards") or [],
        topic_epoch=args.topic_epoch,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(projection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        print(json.dumps(projection, ensure_ascii=False, indent=2))
    else:
        print(f"navigation potentials: {projection['potential_count']}")
        print(f"foreground eligible: {projection['foreground_eligible_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
