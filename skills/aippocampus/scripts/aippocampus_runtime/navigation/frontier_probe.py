#!/usr/bin/env python3
"""Bounded concept-graph probes from Journey current-frontier rows.

Frontier probes are prospective navigation seeds. They can tell Dream or recall
where to look next, but they do not mutate Journey state and they are not source
evidence for factual claims.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, stable_json_join_id
from aippocampus_runtime.navigation import concept_graph
from aippocampus_runtime.question.source_refs import compact_source_refs, source_ref_key
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 1
FRONTIER_PROBE_KIND = "aippocampus_frontier_probe"
RESONANCE_CANDIDATE_KIND = "aippocampus_resonance_candidate"
DREAM_INPUT_SEED_KIND = "aippocampus_dream_input_seed"
NEGATIVE_FEEDBACK_OUTCOMES = {"dismissed", "corrected", "ignored"}


def _text(value: Any, limit: int = 220) -> str:
    return compact_text(str(value or "").strip(), limit)


def _tokens(value: str) -> list[str]:
    return [term for term in re.findall(r"[a-zA-Z0-9_]+", value.casefold()) if len(term) > 2]


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def frontier_terms_from_journey(journey: Mapping[str, Any], *, limit: int = 18) -> list[str]:
    """Extract deterministic concept seeds from the current frontier text."""

    current_frontier = _text(journey.get("current_frontier"), 360)
    extras = " ".join(str(item or "") for item in journey.get("active_questions") or [])
    text = " ".join(
        item
        for item in (
            current_frontier,
            _text(journey.get("path_label"), 120),
            _text(journey.get("core_inquiry"), 180),
            compact_text(extras, 240),
        )
        if item
    )
    tokens = _tokens(text)
    phrases: list[str] = []
    if current_frontier:
        phrases.append(current_frontier)
    phrases.extend(" ".join(tokens[idx : idx + 2]) for idx in range(max(0, len(tokens) - 1)))
    phrases.extend(" ".join(tokens[idx : idx + 3]) for idx in range(max(0, len(tokens) - 2)))
    phrases.extend(tokens)
    return unique_preserve(phrases, limit=limit)


def _frontier_fingerprint(journey: Mapping[str, Any]) -> str:
    return stable_json_join_id(
        "frontier",
        journey.get("journey_id"),
        journey.get("current_frontier"),
        journey.get("current_frontier_source_refs"),
        ensure_ascii=False,
        length=20,
        default_str=False,
    )


def _negative_feedback_key(journey: Mapping[str, Any]) -> str:
    return stable_json_join_id(
        "frontier_feedback",
        journey.get("journey_id"),
        _frontier_fingerprint(journey),
        ensure_ascii=False,
        default_str=False,
    )


def _feedback_blocks(feedback_rows: Sequence[Mapping[str, Any]], negative_feedback_key: str) -> bool:
    for row in feedback_rows:
        if str(row.get("negative_feedback_key") or row.get("target_key") or "") != negative_feedback_key:
            continue
        if str(row.get("outcome") or row.get("action") or "") in NEGATIVE_FEEDBACK_OUTCOMES:
            return True
    return False


def _journey_active(journey: Mapping[str, Any], *, now: str) -> bool:
    if str(journey.get("status") or "") in {"arrived", "abandoned"}:
        return False
    expires = _parse_time(journey.get("expires_at"))
    current = _parse_time(now)
    return not (expires and current and expires < current)


def _probe_expiry(journey: Mapping[str, Any], *, now: str) -> str:
    journey_expiry = _parse_time(journey.get("expires_at"))
    if journey_expiry:
        return _format_time(journey_expiry)
    current = _parse_time(now) or datetime.now(timezone.utc)
    return _format_time(current + timedelta(days=14))


def build_frontier_probes(
    journeys: Sequence[Mapping[str, Any]],
    concept_graph_path: Path,
    *,
    feedback_rows: Sequence[Mapping[str, Any]] | None = None,
    now: str | None = None,
    depth: int = 1,
    max_probes_per_journey: int = 3,
) -> list[dict[str, Any]]:
    """Build bounded probes from Journey frontiers into neighboring concepts."""

    now_value = now or now_utc()
    feedback_rows = feedback_rows or []
    probes: list[dict[str, Any]] = []
    for journey in journeys:
        if not isinstance(journey, Mapping) or not _journey_active(journey, now=now_value):
            continue
        frontier_refs = _source_refs(journey.get("current_frontier_source_refs"))
        if not frontier_refs:
            continue
        negative_key = _negative_feedback_key(journey)
        if _feedback_blocks(feedback_rows, negative_key):
            continue
        seed_terms = frontier_terms_from_journey(journey)
        if not seed_terms:
            continue
        seed_norms = {concept_graph.concept_normalized(term) for term in seed_terms}
        expansions = concept_graph.expand_concepts(
            concept_graph_path,
            seed_terms,
            depth=max(1, depth),
            max_terms=max_probes_per_journey * 4,
        )
        added = 0
        for row in expansions:
            candidate = _text(row.get("term"), 120)
            if not candidate or concept_graph.concept_normalized(candidate) in seed_norms:
                continue
            probe = {
                "schema_version": SCHEMA_VERSION,
                "kind": FRONTIER_PROBE_KIND,
                "probe_id": stable_json_join_id(
                    "frontier_probe",
                    journey.get("journey_id"),
                    _frontier_fingerprint(journey),
                    candidate,
                    row.get("path"),
                    ensure_ascii=False,
                    length=20,
                    default_str=False,
                ),
                "created_at": now_value,
                "expires_at": _probe_expiry(journey, now=now_value),
                "status": "candidate",
                "support_level": "bounded_probe",
                "journey_id": _text(journey.get("journey_id"), 120),
                "path_label": _text(journey.get("path_label"), 140),
                "current_frontier_fingerprint": _frontier_fingerprint(journey),
                "seed_terms": seed_terms,
                "seed_concepts": [
                    {"concept_id": concept_graph.concept_id_for(term), "label": term}
                    for term in seed_terms[:8]
                ],
                "candidate_concept": {
                    "concept_id": concept_graph.concept_id_for(candidate),
                    "label": candidate,
                },
                "probe_path": row.get("path") or [],
                "edge_types": row.get("edge_types") or [],
                "graph_score": row.get("score"),
                "depth": row.get("depth"),
                "source_refs": frontier_refs,
                "frontier_source_refs": frontier_refs,
                "graph_source_refs": [],
                "suggested_use": "prospective_scouting_seed",
                "claim_boundary": {
                    "not_evidence": True,
                    "requires_source_reopen_before_claim": True,
                    "does_not_mutate_journey": True,
                },
                "negative_feedback_key": negative_key,
            }
            probes.append(probe)
            added += 1
            if added >= max(1, max_probes_per_journey):
                break
    return probes


def build_resonance_candidates(
    journeys: Sequence[Mapping[str, Any]],
    probes: Sequence[Mapping[str, Any]],
    *,
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Find reviewable path-resonance candidates from shared frontier probes."""

    now_value = now or now_utc()
    journeys_by_id = {str(journey.get("journey_id") or ""): journey for journey in journeys}
    by_concept: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for probe in probes:
        concept = probe.get("candidate_concept")
        if not isinstance(concept, Mapping):
            continue
        label = _text(concept.get("label"), 120)
        if label:
            by_concept[label.casefold()].append(probe)

    candidates: list[dict[str, Any]] = []
    for _, rows in sorted(by_concept.items()):
        journey_ids = unique_preserve([str(row.get("journey_id") or "") for row in rows], limit=6)
        if len(journey_ids) < 2:
            continue
        labels = unique_preserve(
            [
                str((row.get("candidate_concept") or {}).get("label") or "")
                for row in rows
                if isinstance(row.get("candidate_concept"), Mapping)
            ],
            limit=6,
        )
        refs = _source_refs(*(row.get("source_refs") for row in rows), limit=12)
        scores = [float(row.get("graph_score") or 0.0) for row in rows]
        confidence = round(min(0.8, (sum(scores) / max(1, len(scores))) * 0.75), 4)
        candidates.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": RESONANCE_CANDIDATE_KIND,
                "candidate_id": stable_json_join_id(
                    "resonance_candidate",
                    journey_ids,
                    labels,
                    ensure_ascii=False,
                    length=20,
                    default_str=False,
                ),
                "created_at": now_value,
                "status": "reviewable_hypothesis",
                "match_kind": "neighboring_frontier_concepts",
                "journey_ids": journey_ids,
                "shared_or_neighboring_concepts": labels,
                "shared_structure": {
                    "arc_sequence": [],
                    "dynamics_labels": unique_preserve(
                        [
                            str(label)
                            for jid in journey_ids
                            for waypoint in (journeys_by_id.get(jid, {}).get("waypoints") or [])
                            for label in (waypoint.get("labels") or [])
                            if str(label).startswith("dynamics:")
                        ],
                        limit=8,
                    ),
                },
                "source_refs": [],
                "source_ref_count": len(refs),
                "confidence": confidence,
                "suggested_use": "source_refresh_cue",
                "claim_boundary": {
                    "hypothesis_not_fact": True,
                    "not_evidence": True,
                    "not_auto_merge": True,
                    "requires_source_reopen_before_use": True,
                },
            }
        )
    return candidates


def frontier_probes_to_dream_seeds(probes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for probe in probes:
        if probe.get("kind") != FRONTIER_PROBE_KIND:
            continue
        concept = probe.get("candidate_concept")
        concept_label = _text(concept.get("label"), 120) if isinstance(concept, Mapping) else ""
        seeds.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": DREAM_INPUT_SEED_KIND,
                "seed_kind": "frontier_probe",
                "seed_id": stable_json_join_id(
                    "dream_seed",
                    probe.get("probe_id"),
                    concept_label,
                    ensure_ascii=False,
                    length=20,
                    default_str=False,
                ),
                "source_probe_ids": [probe.get("probe_id")],
                "questions": [],
                "frontiers": [_text(probe.get("path_label"), 140)],
                "themes": [],
                "concepts": [concept_label] if concept_label else [],
                "source_refs": probe.get("source_refs") or [],
                "foreground_eligible": False,
                "formal_memory_eligible": False,
                "clean_source_mutation": False,
                "eligible_dream_functions": ["prospective"],
                "truth_boundary": "dream_input_seed_not_fact",
                "claim_boundary": {
                    "not_evidence": True,
                    "requires_source_reopen_before_claim": True,
                },
            }
        )
    return seeds
