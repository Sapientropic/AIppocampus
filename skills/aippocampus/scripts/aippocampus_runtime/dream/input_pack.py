#!/usr/bin/env python3
"""Build source-backed input packs for background dream workers.

The pack is a staging contract, not a memory surface. It lets later dream
workers consume real-history signals from question tracking, Journey Tracking,
and ambient residue without pretending that residue fingerprints are clean
source refs or that a dream hypothesis is already true.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.source.texture_consumption import (
    select_texture_signals,
    texture_signal_summary,
)

SCHEMA_VERSION = 1
PACK_KIND = "aippocampus_dream_input_pack"
READY_STATUS = "ready_for_dream_worker"
PACK_KIND_CROSS_THREAD = "cross_thread_resonance_seed"
TRUTH_BOUNDARY = "dream_input_pack_seed_not_fact"
SAFE_SOURCE_REF_KEYS = {
    "ref",
    "turn_ref",
    "thread_key",
    "thread_id",
    "message_id",
    "turn_id",
    "source_id",
    "source_ref",
    "clean_ordinal",
    "source_line",
    "line",
    "user_line",
    "assistant_line",
    "turn_index",
    "title",
    "project_label",
    "role",
    "phase",
    "timestamp",
}


@dataclass(frozen=True)
class DreamSeed:
    seed_id: str
    seed_kind: str
    title: str
    summary: str
    source_refs: tuple[dict[str, Any], ...]
    source_ref_fingerprints: tuple[str, ...] = ()
    source_finding_ids: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    frontiers: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()
    negative_contexts: tuple[str, ...] = ()
    texture_signals: tuple[dict[str, Any], ...] = ()


def stable_digest(*parts: object, prefix: str, length: int = 16) -> str:
    raw = "\n".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def is_present(value: object) -> bool:
    return value is not None and value != ""


def unique_preserve(values: Iterable[object], *, limit: int = 16, max_chars: int = 120) -> list[str]:
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


def string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if is_present(item))
    return ()


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(
            ref.get("source_id")
            or ref.get("source_line")
            or ref.get("line")
            or ref.get("source_ref")
            or ""
        ),
    )


def source_ref_thread(ref: Mapping[str, Any]) -> str:
    return str(ref.get("thread_key") or ref.get("thread_id") or "")


def normalize_source_refs(value: object) -> tuple[dict[str, Any], ...]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = []

    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        ref = dict(item)
        key = source_ref_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in ref.items() if k in SAFE_SOURCE_REF_KEYS and is_present(v)})
    return tuple(refs)


def merge_refs(seeds: Iterable[DreamSeed], *, limit: int = 24) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for seed in seeds:
        for ref in seed.source_refs:
            key = source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(ref))
            if len(out) >= limit:
                return out
    return out


def row_id(row: Mapping[str, Any], *, prefix: str) -> str:
    for key in (
        "fingerprint",
        "source_finding_id",
        "journey_id",
        "residue_id",
        "question_cluster_id",
        "id",
    ):
        value = row.get(key)
        if value:
            return str(value)
    return stable_digest(row, prefix=prefix, length=18)


def row_types(row: Mapping[str, Any]) -> set[str]:
    return {
        str(value)
        for value in (row.get("kind"), row.get("finding_kind"), row.get("candidate_type"))
        if value
    }


def refs_from_row(row: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        [
            *normalize_source_refs(row.get("source_refs")),
            *normalize_source_refs(row.get("evidence_refs")),
            *normalize_source_refs(row.get("clean_source_refs")),
        ]
    )


def weak_handles_from_row(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        unique_preserve(
            [
                *string_values(row.get("source_ref_fingerprints")),
                *string_values(row.get("source_ref_handles")),
                *string_values(row.get("weak_source_handles")),
            ],
            limit=24,
        )
    )


def question_link_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    if str(row.get("finding_kind") or row.get("kind") or "") != "question_link":
        return None
    refs = normalize_source_refs(row.get("source_refs"))
    if not refs:
        return None
    linked_questions = [
        item
        for item in row.get("linked_questions") or []
        if isinstance(item, Mapping)
    ]
    frontier_refs = [item for item in row.get("frontier_refs") or [] if isinstance(item, Mapping)]
    questions = unique_preserve(
        [
            row.get("linked_question_short"),
            *(
                item.get("question_text") or item.get("question_short") or ""
                for item in linked_questions
            ),
        ],
        limit=12,
        max_chars=180,
    )
    frontiers = unique_preserve(
        [
            item.get("boundary_reason") or item.get("linked_question_short") or ""
            for item in frontier_refs
        ],
        limit=8,
        max_chars=220,
    )
    source_ids = unique_preserve(
        [
            row_id(row, prefix="ql"),
            *string_values(row.get("question_source_finding_ids")),
            *(item.get("source_finding_id") or "" for item in frontier_refs),
        ],
        limit=20,
    )
    concepts = unique_preserve(string_values(row.get("concepts")), limit=14)
    return DreamSeed(
        seed_id=row_id(row, prefix="ql"),
        seed_kind="question_link",
        title=compact_text(str(row.get("title") or "Question continuity seed"), 160),
        summary=compact_text(str(row.get("summary") or ""), 420),
        source_refs=refs,
        source_finding_ids=tuple(source_ids),
        questions=tuple(questions),
        frontiers=tuple(frontiers),
        themes=tuple(concepts),
        concepts=tuple(concepts),
    )


def journey_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    if str(row.get("kind") or "") != "aippocampus_journey" and not row.get("journey_id"):
        return None
    refs = tuple(
        [
            *normalize_source_refs(row.get("source_refs")),
            *normalize_source_refs(row.get("current_frontier_source_refs")),
        ]
    )
    if not refs:
        return None
    questions = unique_preserve(
        [row.get("core_inquiry"), *string_values(row.get("active_questions"))],
        limit=12,
        max_chars=220,
    )
    frontiers = unique_preserve([row.get("current_frontier")], limit=4, max_chars=260)
    themes = unique_preserve([row.get("path_label"), row.get("status")], limit=8)
    return DreamSeed(
        seed_id=row_id(row, prefix="journey"),
        seed_kind="journey",
        title=compact_text(str(row.get("path_label") or "Journey seed"), 160),
        summary=compact_text(str(row.get("core_inquiry") or row.get("current_frontier") or ""), 420),
        source_refs=refs,
        source_finding_ids=(row_id(row, prefix="journey"),),
        questions=tuple(questions),
        frontiers=tuple(frontiers),
        themes=tuple(themes),
        concepts=tuple(themes),
    )


def ambient_residue_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    if str(row.get("kind") or "") != "aippocampus_ambient_residue":
        return None
    if str(row.get("status") or "") != "dream_seed":
        return None
    handles = unique_preserve(string_values(row.get("source_ref_fingerprints")), limit=24)
    if not handles:
        return None
    themes = unique_preserve(string_values(row.get("themes")), limit=12)
    return DreamSeed(
        seed_id=row_id(row, prefix="ares"),
        seed_kind="ambient_residue",
        title=compact_text(", ".join(themes) or "Ambient residue seed", 160),
        summary=compact_text(str(row.get("reason") or ""), 300),
        source_refs=(),
        source_ref_fingerprints=tuple(handles),
        source_finding_ids=(row_id(row, prefix="ares"),),
        themes=tuple(themes),
        concepts=tuple(themes),
        negative_contexts=tuple(unique_preserve(string_values(row.get("negative_contexts")), limit=8)),
    )


def concept_edge_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    if "concept_edge" not in row_types(row):
        return None
    refs = refs_from_row(row)
    if not refs:
        return None
    concepts = unique_preserve(
        [row.get("src"), row.get("dst"), *string_values(row.get("concepts"))],
        limit=14,
    )
    edge_type = compact_text(str(row.get("edge_type") or "related"), 80)
    return DreamSeed(
        seed_id=row_id(row, prefix="cedge"),
        seed_kind="concept_edge",
        title=compact_text(
            str(row.get("title") or f"{row.get('src') or 'concept'} -> {row.get('dst') or 'concept'}"),
            160,
        ),
        summary=compact_text(str(row.get("why") or row.get("summary") or ""), 420),
        source_refs=refs,
        source_finding_ids=(row_id(row, prefix="cedge"),),
        themes=tuple(unique_preserve([edge_type, *concepts], limit=12)),
        concepts=tuple(concepts),
    )


def theme_candidate_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    kinds = row_types(row)
    if not (kinds & {"theme_candidate", "ambient_theme_candidate"}):
        return None
    refs = refs_from_row(row)
    weak_handles = weak_handles_from_row(row)
    if not refs and not weak_handles:
        return None
    themes = unique_preserve(
        [
            row.get("theme"),
            row.get("theme_label"),
            row.get("title"),
            *string_values(row.get("themes")),
        ],
        limit=12,
        max_chars=160,
    )
    concepts = unique_preserve(
        [
            *themes,
            *string_values(row.get("matched_terms")),
            *string_values(row.get("concepts")),
        ],
        limit=16,
    )
    return DreamSeed(
        seed_id=row_id(row, prefix="theme"),
        seed_kind="theme_candidate",
        title=compact_text(", ".join(themes) or "Theme candidate seed", 160),
        summary=compact_text(
            str(row.get("summary") or row.get("nudge") or row.get("key_line") or row.get("reason") or ""),
            360,
        ),
        source_refs=refs,
        source_ref_fingerprints=weak_handles,
        source_finding_ids=(row_id(row, prefix="theme"),),
        themes=tuple(themes),
        concepts=tuple(concepts),
        negative_contexts=tuple(unique_preserve(string_values(row.get("negative_contexts")), limit=8)),
    )


def correction_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    if not (row_types(row) & {
        "correction_activation_event",
        "correction_outcome_event",
        "correction_adjudication_candidate",
        "correction_active_task_anchor",
    }):
        return None
    refs = refs_from_row(row)
    if not refs:
        return None
    themes = unique_preserve(
        [
            "correction",
            row.get("target_type"),
            row.get("adoption_signal"),
            row.get("adjudication_status"),
            row.get("route"),
        ],
        limit=10,
    )
    return DreamSeed(
        seed_id=row_id(row, prefix="corr"),
        seed_kind="correction",
        title=compact_text(str(row.get("title") or "Correction seed"), 160),
        summary=compact_text(
            str(
                row.get("summary")
                or row.get("correction_surface")
                or row.get("outcome_summary")
                or row.get("instruction")
                or ""
            ),
            420,
        ),
        source_refs=refs,
        source_finding_ids=tuple(
            unique_preserve(
                [
                    row.get("event_id"),
                    row.get("candidate_id"),
                    row.get("activation_event_id"),
                    row.get("outcome_event_id"),
                ],
                limit=8,
            )
        ),
        themes=tuple(themes),
        concepts=tuple(themes),
        negative_contexts=("correction rows are adjudication triggers, not dream facts",),
    )


def recall_miss_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    kinds = row_types(row)
    event_type = str(row.get("event_type") or row.get("feedback_type") or "")
    if not (
        kinds
        & {
            "recall_feedback_event",
            "recall_miss",
            "late_reopen_recovery",
            "source_evidence_recall_feedback",
        }
        or event_type in {"recall_miss", "late_reopen_recovery"}
    ):
        return None
    refs = refs_from_row(row)
    if not refs:
        return None
    signal = "late_reopen_recovery" if event_type == "late_reopen_recovery" else "recall_miss"
    themes = unique_preserve(
        [
            signal,
            row.get("query_origin"),
            row.get("route_kind"),
            row.get("miss_stage"),
            row.get("benchmark_family"),
            *string_values(row.get("diagnostic_terms")),
        ],
        limit=12,
    )
    return DreamSeed(
        seed_id=row_id(row, prefix="recallmiss"),
        seed_kind="recall_miss",
        title=compact_text(str(row.get("title") or f"Recall feedback: {signal}"), 160),
        summary=compact_text(
            str(row.get("summary") or row.get("diagnostic_summary") or row.get("outcome_summary") or ""),
            360,
        ),
        source_refs=refs,
        source_finding_ids=tuple(
            unique_preserve(
                [
                    row.get("event_id"),
                    row.get("feedback_id"),
                    row.get("benchmark_case_id"),
                    row.get("case_id"),
                ],
                limit=8,
            )
        ),
        themes=tuple(themes),
        concepts=tuple(themes),
        negative_contexts=(
            "recall miss feedback is a compensatory trigger, not source truth",
            "absence of recall is not automatically a miss without source-backed recovery evidence",
        ),
    )


def reflection_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    kinds = row_types(row)
    if not (kinds & {"aippocampus_reflection_adjustment", "aippocampus_reflection_feedback"}):
        return None
    refs = refs_from_row(row)
    if not refs:
        return None
    action = compact_text(
        str(row.get("feedback_action") or row.get("recall_effect") or row.get("action") or ""),
        80,
    )
    themes = unique_preserve(["reflection", action, row.get("surface"), row.get("journey_id")], limit=10)
    return DreamSeed(
        seed_id=row_id(row, prefix="refl"),
        seed_kind="reflection_feedback",
        title=compact_text(str(row.get("title") or f"Reflection feedback: {action or 'adjustment'}"), 160),
        summary=compact_text(str(row.get("reason") or row.get("note") or row.get("summary") or ""), 420),
        source_refs=refs,
        source_finding_ids=(row_id(row, prefix="refl"),),
        themes=tuple(themes),
        concepts=tuple(themes),
    )


def agency_or_coding_seed(row: Mapping[str, Any]) -> DreamSeed | None:
    kinds = row_types(row)
    if not (kinds & {
        "aippocampus_agency_ticket",
        "aippocampus_agency_affordance",
        "aippocampus_coding_continuity_ticket",
        "coding_decision_event",
        "decision_event",
    }):
        return None
    refs = refs_from_row(row)
    if not refs:
        return None
    scope = row.get("scope") if isinstance(row.get("scope"), Mapping) else {}
    themes = unique_preserve(
        [
            "agency" if "aippocampus_agency_ticket" in kinds or "aippocampus_agency_affordance" in kinds else "coding",
            row.get("intervention_level"),
            row.get("trigger"),
            (row.get("why_now") or {}).get("trigger") if isinstance(row.get("why_now"), Mapping) else None,
            row.get("event_type"),
            scope.get("label") if isinstance(scope, Mapping) else None,
        ],
        limit=12,
    )
    concepts = unique_preserve(
        [
            *themes,
            *string_values(row.get("trigger_terms")),
            *string_values(row.get("do_not_repeat")),
            *string_values(row.get("do_not_do")),
        ],
        limit=18,
    )
    return DreamSeed(
        seed_id=row_id(row, prefix="agency"),
        seed_kind="agency_ticket" if "aippocampus_agency_ticket" in kinds or "aippocampus_agency_affordance" in kinds else "coding_ticket",
        title=compact_text(str(row.get("title") or "Agency/coding ticket seed"), 160),
        summary=compact_text(
            str(row.get("summary") or row.get("recommendation") or row.get("instruction") or ""),
            420,
        ),
        source_refs=refs,
        source_finding_ids=tuple(
            unique_preserve(
                [row.get("ticket_id"), row.get("affordance_id"), row.get("decision_id")],
                limit=8,
            )
        ),
        themes=tuple(themes),
        concepts=tuple(concepts),
        negative_contexts=tuple(unique_preserve(string_values(row.get("do_not_do")), limit=8)),
    )


def texture_seed_from_signal(signal: Mapping[str, Any]) -> DreamSeed | None:
    refs = normalize_source_refs(signal.get("source_refs"))
    if not refs:
        return None
    signal_kind = compact_text(str(signal.get("signal_kind") or "source_texture"), 80)
    signal_detail = compact_text(str(signal.get("signal_detail") or ""), 120)
    labels = unique_preserve([signal_kind, signal_detail, *string_values(signal.get("signal_labels"))], limit=10)
    suggested_use = compact_text(str(signal.get("suggested_use") or "dream_seed"), 80)
    return DreamSeed(
        seed_id=str(signal.get("texture_id") or row_id(signal, prefix="texture")),
        seed_kind="source_texture",
        title=compact_text(f"Source texture: {signal_kind}", 160),
        summary=compact_text(
            f"{signal_kind} ({signal_detail or suggested_use}) routes Dream work; reopen source before claims.",
            360,
        ),
        source_refs=refs,
        source_finding_ids=(str(signal.get("texture_id") or row_id(signal, prefix="texture")),),
        questions=(),
        frontiers=tuple(labels if signal_kind in {"uncertainty_or_frontier_signal", "abandoned_direction"} else ()),
        themes=tuple(labels),
        concepts=tuple(labels),
        negative_contexts=(
            "source texture is routing material, not evidence for user facts",
            "reopen clean source before any factual claim",
        ),
        texture_signals=(dict(signal),),
    )


def seed_from_row(row: Mapping[str, Any]) -> DreamSeed | None:
    return (
        question_link_seed(row)
        or journey_seed(row)
        or ambient_residue_seed(row)
        or concept_edge_seed(row)
        or theme_candidate_seed(row)
        or correction_seed(row)
        or recall_miss_seed(row)
        or reflection_seed(row)
        or agency_or_coding_seed(row)
    )


def audit_status(refs: list[dict[str, Any]], *, min_source_threads: int) -> dict[str, Any]:
    thread_keys = sorted({source_ref_thread(ref) for ref in refs if source_ref_thread(ref)})
    if not refs:
        status = "missing_clean_source_refs"
    elif len(thread_keys) < min_source_threads:
        status = "insufficient_source_threads"
    else:
        status = "structural_cross_thread"
    return {
        "status": status,
        "checks": [
            "clean_source_refs_present",
            "distinct_source_threads_present",
            "ambient_residue_treated_as_weak_handle_only",
        ],
        "source_ref_count": len(refs),
        "source_thread_count": len(thread_keys),
        "source_threads": thread_keys,
        "clean_source_resolution": "not_checked_without_registry_index",
    }


def eligible_dream_functions(
    *,
    refs: list[dict[str, Any]],
    min_source_threads: int,
    texture_signals: Iterable[Mapping[str, Any]] = (),
) -> list[str]:
    thread_count = len({source_ref_thread(ref) for ref in refs if source_ref_thread(ref)})
    if not refs or thread_count < min_source_threads:
        return []
    functions = ["compensatory", "amplification"]
    signal_kinds = {str(signal.get("signal_kind") or "") for signal in texture_signals}
    if signal_kinds & {"uncertainty_or_frontier_signal", "process_route_note"}:
        functions.append("prospective")
    if signal_kinds & {"abandoned_direction", "rejected_route", "affect_marker", "self_correction_signal"}:
        functions.append("active_imagination")
    return unique_preserve(functions, limit=4)


def source_contributions(seeds: Iterable[DreamSeed]) -> list[dict[str, Any]]:
    contributions: list[dict[str, Any]] = []
    for seed in seeds:
        thread_count = len(
            {source_ref_thread(ref) for ref in seed.source_refs if source_ref_thread(ref)}
        )
        contributions.append(
            {
                "seed_id": seed.seed_id,
                "seed_kind": seed.seed_kind,
                "source_ref_count": len(seed.source_refs),
                "source_thread_count": thread_count,
                "source_ref_fingerprint_count": len(seed.source_ref_fingerprints),
                "readiness_role": (
                    "texture_route_anchor"
                    if seed.seed_kind == "source_texture"
                    else "clean_anchor"
                    if seed.source_refs
                    else "weak_context"
                ),
                "question_count": len(seed.questions),
                "frontier_count": len(seed.frontiers),
                "theme_count": len(seed.themes),
                "concept_count": len(seed.concepts),
                "texture_signal_count": len(seed.texture_signals),
            }
        )
    return contributions


def build_dream_input_pack(
    rows: Iterable[Mapping[str, Any]],
    *,
    objective: str = "",
    min_source_threads: int = 2,
    max_source_refs: int = 24,
) -> dict[str, Any]:
    row_list = list(rows)
    texture_selection = select_texture_signals(row_list, consumer="dream", limit=12)
    texture_signals = [
        signal for signal in texture_selection.get("signals") or [] if isinstance(signal, Mapping)
    ]
    seeds = [seed for seed in (seed_from_row(row) for row in row_list) if seed is not None]
    seeds.extend(
        seed
        for seed in (texture_seed_from_signal(signal) for signal in texture_signals)
        if seed is not None
    )
    clean_seeds = [seed for seed in seeds if seed.source_refs]
    refs = merge_refs(clean_seeds, limit=max_source_refs)
    audit = audit_status(refs, min_source_threads=min_source_threads)
    functions = eligible_dream_functions(
        refs=refs,
        min_source_threads=min_source_threads,
        texture_signals=texture_signals,
    )
    weak_handles = unique_preserve(
        [handle for seed in seeds for handle in seed.source_ref_fingerprints],
        limit=32,
    )
    if not refs:
        status = "no_clean_source_refs"
    elif not functions:
        status = "no_cross_thread_source_pattern"
    else:
        status = READY_STATUS

    seed_ids = unique_preserve((seed.seed_id for seed in seeds), limit=32)
    seed_kinds = unique_preserve((seed.seed_kind for seed in seeds), limit=8)
    source_finding_ids = unique_preserve(
        (source_id for seed in seeds for source_id in seed.source_finding_ids),
        limit=48,
    )
    questions = unique_preserve((value for seed in seeds for value in seed.questions), limit=16, max_chars=220)
    frontiers = unique_preserve((value for seed in seeds for value in seed.frontiers), limit=12, max_chars=260)
    themes = unique_preserve((value for seed in seeds for value in seed.themes), limit=16, max_chars=160)
    concepts = unique_preserve((value for seed in seeds for value in seed.concepts), limit=18, max_chars=120)
    negative_contexts = unique_preserve(
        (value for seed in seeds for value in seed.negative_contexts),
        limit=10,
        max_chars=160,
    )
    contributions = source_contributions(seeds)
    texture_summary = texture_signal_summary(
        texture_signals,
        consumer="dream",
        suppression_reasons=(texture_selection.get("diagnostics") or {}).get("suppression_reasons") or {},
    )
    pack_seed = {
        "objective": compact_text(objective, 240),
        "source_seed_ids": seed_ids,
        "source_finding_ids": source_finding_ids,
        "source_contributions": contributions,
        "source_refs": refs,
        "weak_source_handles": weak_handles,
        "texture_signals": texture_signals,
        "questions": questions,
        "frontiers": frontiers,
        "themes": themes,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PACK_KIND,
        "pack_id": stable_digest(pack_seed, prefix="dream_pack", length=18),
        "created_at": now_utc(),
        "status": status,
        "pack_kind": PACK_KIND_CROSS_THREAD if status == READY_STATUS else "insufficient_source_seed",
        "support_level": "seed",
        "objective": compact_text(objective, 240),
        "foreground_eligible": False,
        "human_review_required": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "source_seed_ids": seed_ids,
        "source_seed_kinds": seed_kinds,
        "source_finding_ids": source_finding_ids,
        "source_contributions": contributions,
        "source_refs": refs,
        "source_ref_audit": audit,
        "source_ref_fingerprints": weak_handles,
        "weak_source_handle_count": len(weak_handles),
        "texture_signals": texture_signals,
        "source_texture_consumption": texture_summary,
        "questions": questions,
        "frontiers": frontiers,
        "themes": themes,
        "concepts": concepts,
        "negative_contexts": negative_contexts,
        "eligible_dream_functions": functions,
        "downstream_use": ["background_dream_worker"] if functions else [],
        "adjudication_policy": {
            "default_adjudicator": "background_dream_worker",
            "human_review_required": False,
            "requires_source_refs_for_bridge_claims": True,
            "requires_clean_source_reopen_for_factual_claims": True,
        },
        "truth_boundary": TRUTH_BOUNDARY,
        "cannot_claim": [
            "dream_output_is_fact",
            "formal_memory_promotion",
            "foreground_hook_eligibility",
            "clean_source_resolution_without_registry_index",
            "user_profile_fact_from_ambient_residue",
        ],
    }


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield item


def public_pack_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    audit_value = payload.get("source_ref_audit")
    audit: Mapping[str, Any] = audit_value if isinstance(audit_value, Mapping) else {}
    contributions = [
        {
            "seed_kind": item.get("seed_kind"),
            "source_ref_count": item.get("source_ref_count"),
            "source_thread_count": item.get("source_thread_count"),
            "readiness_role": item.get("readiness_role"),
            "question_count": item.get("question_count"),
            "frontier_count": item.get("frontier_count"),
            "theme_count": item.get("theme_count"),
            "concept_count": item.get("concept_count"),
        }
        for item in payload.get("source_contributions") or []
        if isinstance(item, Mapping)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_dream_input_pack_summary",
        "pack_id": payload.get("pack_id"),
        "status": payload.get("status"),
        "pack_kind": payload.get("pack_kind"),
        "source_seed_kind_counts": dict(Counter(str(kind) for kind in payload.get("source_seed_kinds") or [])),
        "source_ref_audit": {
            "status": audit.get("status"),
            "source_ref_count": audit.get("source_ref_count"),
            "source_thread_count": audit.get("source_thread_count"),
            "clean_source_resolution": audit.get("clean_source_resolution"),
        },
        "weak_source_handle_count": payload.get("weak_source_handle_count"),
        "source_contributions": contributions,
        "eligible_dream_functions": payload.get("eligible_dream_functions") or [],
        "downstream_use": payload.get("downstream_use") or [],
        "foreground_eligible": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "truth_boundary": payload.get("truth_boundary"),
        "cannot_claim": payload.get("cannot_claim") or [],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a source-backed dream input pack.")
    parser.add_argument("input", type=Path, help="JSONL rows from question/journey/ambient outputs.")
    parser.add_argument("--objective", default="", help="Optional dream worker objective.")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path, help="Optional output path.")
    parser.add_argument(
        "--internal-full",
        action="store_true",
        help="Emit full internal pack with source refs. Do not use for public logs or issues.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = build_dream_input_pack(iter_jsonl(args.input), objective=args.objective)
    output_payload = payload if args.internal_full else public_pack_summary(payload)
    text = json.dumps(output_payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("status") == READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
