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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text, now_utc

SCHEMA_VERSION = 1
PACK_KIND = "aippocampus_dream_input_pack"
READY_STATUS = "ready_for_dream_worker"
PACK_KIND_CROSS_THREAD = "cross_thread_resonance_seed"
TRUTH_BOUNDARY = "dream_input_pack_seed_not_fact"


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
        refs.append({k: v for k, v in ref.items() if is_present(v)})
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


def seed_from_row(row: Mapping[str, Any]) -> DreamSeed | None:
    return question_link_seed(row) or journey_seed(row) or ambient_residue_seed(row)


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


def eligible_dream_functions(*, refs: list[dict[str, Any]], min_source_threads: int) -> list[str]:
    thread_count = len({source_ref_thread(ref) for ref in refs if source_ref_thread(ref)})
    if not refs or thread_count < min_source_threads:
        return []
    return ["compensatory", "amplification"]


def build_dream_input_pack(
    rows: Iterable[Mapping[str, Any]],
    *,
    objective: str = "",
    min_source_threads: int = 2,
    max_source_refs: int = 24,
) -> dict[str, Any]:
    seeds = [seed for seed in (seed_from_row(row) for row in rows) if seed is not None]
    clean_seeds = [seed for seed in seeds if seed.source_refs]
    refs = merge_refs(clean_seeds, limit=max_source_refs)
    audit = audit_status(refs, min_source_threads=min_source_threads)
    functions = eligible_dream_functions(refs=refs, min_source_threads=min_source_threads)
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
    pack_seed = {
        "objective": compact_text(objective, 240),
        "source_seed_ids": seed_ids,
        "source_finding_ids": source_finding_ids,
        "source_refs": refs,
        "weak_source_handles": weak_handles,
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
        "source_refs": refs,
        "source_ref_audit": audit,
        "source_ref_fingerprints": weak_handles,
        "weak_source_handle_count": len(weak_handles),
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a source-backed dream input pack.")
    parser.add_argument("input", type=Path, help="JSONL rows from question/journey/ambient outputs.")
    parser.add_argument("--objective", default="", help="Optional dream worker objective.")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path, help="Optional output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = build_dream_input_pack(iter_jsonl(args.input), objective=args.objective)
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("status") == READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
