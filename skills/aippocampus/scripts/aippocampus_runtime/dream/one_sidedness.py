#!/usr/bin/env python3
"""Deterministic one-sidedness gate for compensatory dream probes.

The opposite / 错卦 voice is only useful after source-backed journey structure
has become one-sided. This helper keeps the symbolic computation separate from
permission to generate a probe: computing an opposite arc is cheap, but it is
not evidence by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc

SCHEMA_VERSION = 1

GATE_KIND = "aippocampus_dream_one_sidedness_gate"
ATMOSPHERE_ARC_KIND = "hexagram_atmosphere_arc"
DREAM_FINDING_KIND = "dream_synthesized"
VOICE_ID = "opposite_hexagram_voice"

OPPOSITE_TRIGRAM = {
    "乾": "坤",
    "坤": "乾",
    "兑": "艮",
    "艮": "兑",
    "离": "坎",
    "坎": "离",
    "震": "巽",
    "巽": "震",
}


def stable_digest(*parts: object, prefix: str, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def _items(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in {None, ""}:
        return []
    return [value]


def normalize_source_refs(value: object) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in _items(value):
        if not isinstance(item, Mapping):
            continue
        key = (
            str(item.get("thread_key") or item.get("thread_id") or ""),
            str(item.get("message_id") or ""),
            str(item.get("turn_id") or ""),
            str(item.get("source_line") or item.get("line") or item.get("source_id") or ""),
        )
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append(dict(item))
    return refs


def merge_refs(*groups: Iterable[Mapping[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for group in groups:
        for ref in group:
            key = (
                str(ref.get("thread_key") or ref.get("thread_id") or ""),
                str(ref.get("message_id") or ""),
                str(ref.get("turn_id") or ""),
                str(ref.get("source_line") or ref.get("line") or ref.get("source_id") or ""),
            )
            if not any(key) or key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
            if len(refs) >= limit:
                return refs
    return refs


def _arc_from_text(text: str) -> dict[str, str]:
    upper_match = re.search(r"(?:upper|上卦)[:=：]\s*([乾坤兑艮离坎震巽])", text)
    lower_match = re.search(r"(?:lower|下卦)[:=：]\s*([乾坤兑艮离坎震巽])", text)
    return {
        "upper_trigram": upper_match.group(1) if upper_match else "",
        "lower_trigram": lower_match.group(1) if lower_match else "",
    }


def normalize_arc(value: object) -> dict[str, str]:
    if isinstance(value, Mapping):
        upper = str(value.get("upper_trigram") or value.get("upper") or value.get("上卦") or "")
        lower = str(value.get("lower_trigram") or value.get("lower") or value.get("下卦") or "")
    else:
        parsed = _arc_from_text(str(value or ""))
        upper = parsed["upper_trigram"]
        lower = parsed["lower_trigram"]
    return {
        "upper_trigram": upper if upper in OPPOSITE_TRIGRAM else "",
        "lower_trigram": lower if lower in OPPOSITE_TRIGRAM else "",
    }


def compute_opposite_arc(arc: object) -> dict[str, str]:
    normalized = normalize_arc(arc)
    upper = normalized["upper_trigram"]
    lower = normalized["lower_trigram"]
    return {
        "upper_trigram": OPPOSITE_TRIGRAM.get(upper, ""),
        "lower_trigram": OPPOSITE_TRIGRAM.get(lower, ""),
        "source_upper_trigram": upper,
        "source_lower_trigram": lower,
        "meaning": "deterministic_complement_not_evidence",
    }


def _waypoints(journey: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in journey.get("waypoints") or [] if isinstance(item, Mapping)]


def _source_backed_waypoints(journey: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for waypoint in _waypoints(journey):
        refs = normalize_source_refs(waypoint.get("source_refs"))
        arc = normalize_arc(waypoint.get("arc"))
        if refs and arc["upper_trigram"] and arc["lower_trigram"]:
            rows.append({**waypoint, "source_refs": refs, "normalized_arc": arc})
    return rows


def _same_trigram_signal(journey: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = _source_backed_waypoints(journey)
    if len(rows) < 3:
        return None
    recent = rows[-3:]
    shared = set(recent[0]["normalized_arc"].values())
    for row in recent[1:]:
        shared &= set(row["normalized_arc"].values())
    if not shared:
        return None
    trigram = sorted(shared)[0]
    return {
        "signal": "same_trigram_family_persistence",
        "source_refs": merge_refs(*(row["source_refs"] for row in recent)),
        "counter_evidence": [f"same trigram family persisted across recent source-backed waypoints: {trigram}"],
        "raw": {"trigram": trigram, "waypoint_count": len(recent)},
    }


def _source_backed_repeated_questions(active_questions: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in active_questions:
        refs = normalize_source_refs(row.get("source_refs"))
        has_counter = bool(normalize_source_refs(row.get("counter_perspective_refs") or row.get("counter_evidence_refs")))
        if not refs or has_counter:
            continue
        key = str(row.get("question_id") or row.get("question") or row.get("title") or "").casefold()
        if not key:
            continue
        grouped.setdefault(key, []).append(row)
    repeated = next((rows for rows in grouped.values() if len(rows) >= 2), [])
    if not repeated:
        return None
    return {
        "signal": "repeated_questions_without_counter_perspective",
        "source_refs": merge_refs(*(normalize_source_refs(row.get("source_refs")) for row in repeated)),
        "counter_evidence": ["repeated active question has no source-backed counter-perspective yet"],
        "raw": {"question_count": len(repeated)},
    }


def _source_backed_absent_theme(theme_residue: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in theme_residue:
        refs = normalize_source_refs(row.get("source_refs"))
        status = str(row.get("status") or row.get("state") or "").casefold()
        if not refs or status not in {"absent", "residue", "recurring_absent", "avoided"}:
            continue
        key = str(row.get("theme") or row.get("label") or row.get("title") or "").casefold()
        if not key:
            continue
        grouped.setdefault(key, []).append(row)
    recurring = next((rows for rows in grouped.values() if len(rows) >= 2), [])
    if not recurring:
        return None
    return {
        "signal": "recurring_absent_theme_residue",
        "source_refs": merge_refs(*(normalize_source_refs(row.get("source_refs")) for row in recurring)),
        "counter_evidence": ["theme recurs as absent residue rather than foreground route"],
        "raw": {"theme_count": len(recurring)},
    }


def _source_backed_avoided_correction(corrections: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    rows = [
        row
        for row in corrections
        if normalize_source_refs(row.get("source_refs")) and (row.get("avoided_angle") or row.get("angle"))
    ]
    if len(rows) < 2:
        return None
    return {
        "signal": "corrections_point_at_avoided_angle",
        "source_refs": merge_refs(*(normalize_source_refs(row.get("source_refs")) for row in rows)),
        "counter_evidence": ["source-backed corrections repeatedly point at an avoided angle"],
        "raw": {"correction_count": len(rows)},
    }


def evaluate_one_sidedness_gate(
    journey: Mapping[str, Any],
    *,
    active_questions: Sequence[Mapping[str, Any]] | None = None,
    theme_residue: Sequence[Mapping[str, Any]] | None = None,
    corrections: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    signals = [
        item
        for item in [
            _same_trigram_signal(journey),
            _source_backed_repeated_questions(active_questions or []),
            _source_backed_absent_theme(theme_residue or []),
            _source_backed_avoided_correction(corrections or []),
        ]
        if item is not None
    ]
    reasons = [str(item["signal"]) for item in signals]
    gate_open = "same_trigram_family_persistence" in reasons or len(reasons) >= 2
    source_refs = merge_refs(*(item["source_refs"] for item in signals))
    counter_evidence = [text for item in signals for text in item.get("counter_evidence") or []]
    suppression_reasons = [] if gate_open else ["one_sidedness_gate_closed", "insufficient_source_backed_one_sidedness"]
    latest_arc = {}
    for row in reversed(_source_backed_waypoints(journey)):
        latest_arc = dict(row["normalized_arc"])
        break
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": GATE_KIND,
        "gate_open": gate_open,
        "reasons": reasons,
        "suppression_reasons": suppression_reasons,
        "source_refs": source_refs,
        "source_ref_count": len(source_refs),
        "counter_evidence": counter_evidence,
        "latest_arc": latest_arc,
        "opposite_arc": compute_opposite_arc(latest_arc) if latest_arc else {},
        "signals": signals,
        "policy": {
            "opposite_hexagram_voice_requires_gate": True,
            "opposite_arc_is_not_evidence": True,
            "technical_threads_require_source_backed_one_sidedness": True,
        },
    }


def build_hexagram_atmosphere_arc(
    journey: Mapping[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any] | None:
    """Build a non-blocking symbolic atmosphere row from source-backed arcs.

    This row answers "what direction did the source-backed journey carry?" It
    deliberately does not reuse the compensatory gate: atmosphere can be
    recognized without authorizing an opposite-voice probe. Exact claims still
    require reopening source.
    """

    rows = _source_backed_waypoints(journey)
    if not rows:
        return None
    latest = rows[-1]
    arc = dict(latest["normalized_arc"])
    refs = merge_refs(*(row["source_refs"] for row in rows))
    journey_id = str(journey.get("journey_id") or "")
    upper = arc["upper_trigram"]
    lower = arc["lower_trigram"]
    arc_summary = compact_text(
        str(
            latest.get("frontier_hint")
            or journey.get("current_frontier")
            or "Source-backed journey direction is available as atmosphere."
        ),
        240,
    )
    arc_id = stable_digest(
        journey_id,
        upper,
        lower,
        refs,
        prefix="hexagram_atmosphere",
        length=20,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ATMOSPHERE_ARC_KIND,
        "arc_id": arc_id,
        "fingerprint": arc_id,
        "created_at": created_at or now_utc(),
        "journey_id": journey_id,
        "thread_key": journey.get("thread_key") or journey.get("thread_id"),
        "source_refs": refs,
        "source_ref_count": len(refs),
        "upper_trigram": upper,
        "lower_trigram": lower,
        "hexagram_key": f"{upper}/{lower}",
        "arc_summary": arc_summary,
        "source_basis": "source_backed_waypoints",
        "authority": "direction_only",
        "action_grammar": "direction_only",
        "memory_surface": "memory_atmosphere",
        "use_boundary": "atmosphere_not_evidence",
        "foreground_eligible": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "claims_user_fact": False,
        "claims_world_fact": False,
        "claims_source_fact": False,
        "source_reopen_required_before_claim": True,
        "truth_boundary": "hexagram_atmosphere_not_fact",
        "atmosphere_boundary": {
            "symbolic_direction_only": True,
            "not_prediction": True,
            "not_user_diagnosis": True,
            "not_hard_instruction": True,
            "source_reopen_required_for_exact_claims": True,
        },
        "cannot_claim": [
            "factual_user_profile",
            "world_or_project_fact",
            "prediction",
            "hard_instruction",
            "source_quote_without_reopen",
        ],
    }


def build_opposite_hexagram_probe(
    journey: Mapping[str, Any],
    *,
    active_questions: Sequence[Mapping[str, Any]] | None = None,
    theme_residue: Sequence[Mapping[str, Any]] | None = None,
    corrections: Sequence[Mapping[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any] | None:
    gate = evaluate_one_sidedness_gate(
        journey,
        active_questions=active_questions,
        theme_residue=theme_residue,
        corrections=corrections,
    )
    if not gate["gate_open"]:
        return None
    journey_id = str(journey.get("journey_id") or "")
    opposite_arc = gate["opposite_arc"]
    finding_id = stable_digest(journey_id, gate["reasons"], opposite_arc, prefix="dream_opposite_voice", length=20)
    summary = compact_text(
        "This journey structure may need a counterweight from the deterministic opposite arc; "
        "treat it as a source-reopen question, not a profile claim.",
        260,
    )
    refs = list(gate["source_refs"])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_dream_probe",
        "finding_kind": DREAM_FINDING_KIND,
        "candidate_type": "dream_hypothesis",
        "dream_finding_id": finding_id,
        "fingerprint": finding_id,
        "created_at": created_at or now_utc(),
        "voice_id": VOICE_ID,
        "dream_function": "compensatory",
        "probe_kind": "source_reopen_check",
        "review_state": "needs_review",
        "foreground_eligible": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "journey_id": journey_id,
        "title": "Opposite-arc counterweight check",
        "summary": summary,
        "source_refs": refs,
        "bridge_claims": [
            {
                "claim": "The one-sidedness gate fired from source-backed journey structure.",
                "source_refs": refs,
            }
        ],
        "counter_evidence": list(gate["counter_evidence"]),
        "one_sidedness_gate": gate,
        "opposite_arc": opposite_arc,
        "voice_boundary": {
            "speaks_from": "unresolved_journey_structure",
            "not_user_persona": True,
            "do_not_decode_symbol_as_profile": True,
        },
        "truth_boundary": "dream_synthesized_candidate_not_fact",
        "why_this_is_not_fact": (
            "The opposite arc names a possible counterweight after a source-backed gate; "
            "it is not evidence about the user or a fact about the project."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journey", required=True, help="JSON file containing a journey row/object.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = json.loads(Path(args.journey).read_text(encoding="utf-8"))
    probe = build_opposite_hexagram_probe(payload)
    output = {
        "gate": evaluate_one_sidedness_gate(payload),
        "probe": probe,
        "atmosphere_arc": build_hexagram_atmosphere_arc(payload),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
