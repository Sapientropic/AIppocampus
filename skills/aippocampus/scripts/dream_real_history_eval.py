#!/usr/bin/env python3
"""Selected real-history dream-pack evaluation.

This runner is deliberately a structural eval, not a dream-quality benchmark.
It selects source-backed cross-thread packs from already materialized
question/frontier/working-memory rows, runs a tiny deterministic
compensatory/amplification worker, and compares the resulting adjudicated dream
hypotheses against the plain rows as recall/reflection substrate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text, now_utc
from dream_working_memory import (
    adjudicated_dream_findings_to_working_memory,
    background_adjudicate_dream_findings,
)
from memory_candidate_router import (
    default_jobs_path,
    default_working_memory_path,
    iter_jsonl,
    load_working_memory,
)
from model_client import DEEPSEEK_KV_CACHE_GUIDE_URL, DEEPSEEK_PREFIX_CACHE_CONTRACT
from registry_store import registry_paths

SCHEMA_VERSION = 1
EVAL_KIND = "aippocampus_dream_real_history_eval"
PACK_KIND = "aippocampus_dream_input_pack"
READY_STATUS = "ready_for_dream_worker"
CLAIM_LEVEL = "selected_real_history_structural_eval"

SEED_FINDING_KINDS = {"question_candidate", "frontier_marker", "question_link"}
LOW_SIGNAL_TERMS = {
    "aippocampus",
    "app",
    "candidate",
    "context",
    "finding",
    "implemented",
    "memory",
    "messages",
    "need",
    "project",
    "question",
    "source",
    "thread",
    "user",
    "work",
    "about",
    "across",
    "after",
    "also",
    "auto",
    "before",
    "continue",
    "could",
    "from",
    "into",
    "should",
    "that",
    "this",
    "with",
    "would",
}


def dream_live_worker_cache_contract() -> dict[str, Any]:
    return {
        "status": "required_before_live_model_worker",
        "provider": "deepseek",
        "cache_contract": DEEPSEEK_PREFIX_CACHE_CONTRACT,
        "official_guide": DEEPSEEK_KV_CACHE_GUIDE_URL,
        "message_order": [
            "stable_dream_worker_contract",
            "source_pack_payload",
            "variable_run_directive",
        ],
        "usage_fields": ["prompt_cache_hit_tokens", "prompt_cache_miss_tokens"],
        "runtime_notes": [
            "DeepSeek KV cache is server-side and automatic, but only complete repeated prefixes can hit.",
            "Future live dream workers must keep stable role/schema/function instructions before source packs, and put objective/sample/repair text at the tail.",
            "Same-prefix follow-up samples should start after an earlier request has completed enough to warm the provider cache.",
        ],
        "cannot_claim": [
            "do_not_claim_cache_hit_for_deterministic_worker",
            "do_not_emit_private_source_text_in_cache_metrics",
            "do_not_optimize_prompt_order_by_sorting_json_keys",
        ],
    }


@dataclass(frozen=True)
class RealHistorySeed:
    seed_id: str
    seed_kind: str
    terms: tuple[str, ...]
    source_refs: tuple[dict[str, Any], ...]
    confidence: float = 0.6


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


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def normalized_term(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    text = re.sub(r"^[^\w\u4e00-\u9fff]+|[^\w\u4e00-\u9fff]+$", "", text)
    if len(text) < 3 or text in LOW_SIGNAL_TERMS:
        return ""
    return text


def terms_from_text(text: str, *, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", text, flags=re.UNICODE)
    return unique_preserve(
        [
            term
            for term in (normalized_term(token) for token in tokens)
            if term and len(term) <= 40
        ],
        limit=limit,
    )


def row_id(row: Mapping[str, Any], *, prefix: str) -> str:
    for key in ("fingerprint", "candidate_key", "journey_id", "question_cluster_id", "id"):
        value = row.get(key)
        if value:
            return str(value)
    return stable_digest(row, prefix=prefix, length=18)


def job_seed(row: Mapping[str, Any]) -> RealHistorySeed | None:
    finding_kind = str(row.get("finding_kind") or "")
    if finding_kind not in SEED_FINDING_KINDS:
        return None
    refs = normalize_source_refs(row.get("source_refs"))
    if not refs:
        return None
    explicit_terms = [
        *(row.get("concepts") or []),
        row.get("linked_question_short"),
        row.get("question_short"),
        row.get("frontier_type"),
    ]
    text_terms = terms_from_text(
        " ".join(
            str(row.get(key) or "")
            for key in ("title", "summary", "question_text", "boundary_reason")
        )
    )
    terms = tuple(
        unique_preserve(
            [term for term in (normalized_term(item) for item in explicit_terms) if term] + text_terms,
            limit=18,
        )
    )
    if not terms:
        return None
    return RealHistorySeed(
        seed_id=row_id(row, prefix="dream_seed"),
        seed_kind=finding_kind,
        terms=terms,
        source_refs=refs,
        confidence=safe_float(row.get("confidence"), 0.6),
    )


def working_memory_seed(row: Mapping[str, Any]) -> RealHistorySeed | None:
    if row.get("kind") != "aippocampus_working_memory":
        return None
    if row.get("status") != "active":
        return None
    refs = normalize_source_refs(row.get("source_refs"))
    if not refs:
        return None
    explicit_terms = [*(row.get("trigger_terms") or []), *(row.get("concepts") or [])]
    text_terms = terms_from_text(
        " ".join(str(row.get(key) or "") for key in ("title", "summary", "recommendation"))
    )
    terms = tuple(
        unique_preserve(
            [term for term in (normalized_term(item) for item in explicit_terms) if term] + text_terms,
            limit=18,
        )
    )
    if not terms:
        return None
    return RealHistorySeed(
        seed_id=row_id(row, prefix="wm_seed"),
        seed_kind="working_memory",
        terms=terms,
        source_refs=refs,
        confidence=safe_float(row.get("confidence"), 0.6),
    )


def source_threads(refs: Iterable[Mapping[str, Any]]) -> set[str]:
    return {source_ref_thread(ref) for ref in refs if source_ref_thread(ref)}


def merge_refs(seeds: Iterable[RealHistorySeed], *, limit: int = 24) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for seed in seeds:
        for ref in seed.source_refs:
            key = source_ref_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
            if len(refs) >= limit:
                return refs
    return refs


def seed_surface_row(seed: RealHistorySeed) -> dict[str, Any]:
    return {
        "surface": "plain",
        "row_id": seed.seed_id,
        "seed_kind": seed.seed_kind,
        "terms": list(seed.terms),
        "source_refs": list(seed.source_refs),
        "reflection_ready": False,
        "bridge_claim_count": 0,
    }


def pack_from_seeds(
    *,
    resonance_term: str,
    seeds: list[RealHistorySeed],
) -> dict[str, Any]:
    refs = merge_refs(seeds)
    thread_keys = sorted(source_threads(refs))
    seed_kinds = unique_preserve([seed.seed_kind for seed in seeds], limit=12)
    themes = unique_preserve([resonance_term, *(term for seed in seeds for term in seed.terms)], limit=18)
    pack_seed = {
        "resonance_term": resonance_term,
        "source_seed_ids": [seed.seed_id for seed in seeds],
        "source_refs": refs,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PACK_KIND,
        "pack_id": stable_digest(pack_seed, prefix="real_dream_pack", length=18),
        "created_at": now_utc(),
        "status": READY_STATUS,
        "pack_kind": "selected_real_history_resonance_seed",
        "support_level": "seed",
        "foreground_eligible": False,
        "human_review_required": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "source_seed_ids": unique_preserve([seed.seed_id for seed in seeds], limit=32),
        "source_seed_kinds": seed_kinds,
        "source_refs": refs,
        "source_ref_audit": {
            "status": "structural_cross_thread",
            "source_ref_count": len(refs),
            "source_thread_count": len(thread_keys),
            "source_threads": thread_keys,
            "clean_source_resolution": "registry_clean_source_if_loaded_else_structural",
        },
        "selection": {
            "method": "shared_term_cross_thread_v1",
            "resonance_term": resonance_term,
            "seed_count": len(seeds),
        },
        "themes": themes,
        "eligible_dream_functions": ["compensatory", "amplification"],
        "eval_prompts": [
            f"What connects {resonance_term} across the selected source-backed threads?",
            f"What unresolved reflection edge should carry forward around {resonance_term}?",
        ],
        "eval_surface_rows": [seed_surface_row(seed) for seed in seeds],
        "truth_boundary": "real_history_dream_pack_seed_not_fact",
        "cannot_claim": [
            "dream_output_is_fact",
            "full_history_coverage",
            "private_real_history_dream_quality",
            "clean_source_resolution_without_reopen",
        ],
    }


def select_real_history_packs(
    *,
    job_rows: Iterable[Mapping[str, Any]],
    working_memory_rows: Iterable[Mapping[str, Any]],
    max_packs: int = 4,
    min_source_threads: int = 2,
) -> list[dict[str, Any]]:
    seeds = [
        seed
        for seed in [*(job_seed(row) for row in job_rows), *(working_memory_seed(row) for row in working_memory_rows)]
        if seed is not None
    ]
    by_term: dict[str, list[RealHistorySeed]] = {}
    for seed in seeds:
        for term in seed.terms:
            by_term.setdefault(term, []).append(seed)

    candidates: list[tuple[tuple[int, int, int, str], str, list[RealHistorySeed]]] = []
    for term, term_seeds in by_term.items():
        deduped: dict[str, RealHistorySeed] = {seed.seed_id: seed for seed in term_seeds}
        selected = list(deduped.values())
        refs = merge_refs(selected)
        thread_count = len(source_threads(refs))
        if thread_count < min_source_threads or len(selected) < 2:
            continue
        kind_count = len({seed.seed_kind for seed in selected})
        candidates.append(((thread_count, kind_count, len(selected), term), term, selected))

    candidates.sort(key=lambda item: (-item[0][0], -item[0][1], -item[0][2], len(item[1]), item[1]))
    used_terms: set[str] = set()
    used_seed_ids: set[str] = set()
    packs: list[dict[str, Any]] = []
    for _, term, seeds_for_term in candidates:
        if term in used_terms:
            continue
        seed_ids = {seed.seed_id for seed in seeds_for_term}
        if seed_ids & used_seed_ids:
            continue
        packs.append(pack_from_seeds(resonance_term=term, seeds=seeds_for_term))
        used_terms.add(term)
        used_seed_ids.update(seed_ids)
        if len(packs) >= max_packs:
            break
    return packs


def bridge_claim(claim: str, refs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"claim": compact_text(claim, 240), "source_refs": refs[:8]}


def dream_finding(
    *,
    pack: Mapping[str, Any],
    dream_function: str,
    title: str,
    summary: str,
    confidence: float,
) -> dict[str, Any]:
    refs = [ref for ref in pack.get("source_refs") or [] if isinstance(ref, dict)]
    term = str((pack.get("selection") or {}).get("resonance_term") or "selected resonance")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_dream_finding",
        "finding_kind": "dream_synthesized",
        "dream_function": dream_function,
        "dream_phase": "phase3_selected_real_history_eval",
        "support_level": "candidate",
        "review_state": "needs_review",
        "foreground_eligible": False,
        "human_review_required": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "fingerprint": stable_digest(pack.get("pack_id"), dream_function, prefix="dream_eval", length=18),
        "title": compact_text(title, 160),
        "summary": compact_text(summary, 520),
        "confidence": round(confidence, 4),
        "source_refs": refs,
        "source_ref_audit": {
            "status": "structural_cross_thread",
            "source_ref_count": len(refs),
            "source_thread_count": len(source_threads(refs)),
            "clean_source_resolution": "not_reopened_by_structural_eval",
        },
        "source_pack_id": pack.get("pack_id"),
        "source_seed_ids": pack.get("source_seed_ids") or [],
        "bridge_claims": [
            bridge_claim(f"The selected real-history pack has cross-thread source support for {term}.", refs),
            bridge_claim(
                f"This {dream_function} hypothesis is a bridge over selected source refs, not a fact.",
                refs,
            ),
        ],
        "downstream_use": ["working_memory", "reflection_space"],
        "truth_boundary": "dream_synthesized_candidate_not_fact",
    }


def run_pack_dream_worker(pack: Mapping[str, Any]) -> dict[str, Any]:
    if pack.get("status") != READY_STATUS:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_pack_dream_worker",
            "status": "skipped_pack_not_ready",
            "findings": [],
            "adjudicated_findings": [],
            "dream_working_memory_rows": [],
        }
    term = str((pack.get("selection") or {}).get("resonance_term") or "selected resonance")
    source_thread_count = int((pack.get("source_ref_audit") or {}).get("source_thread_count") or 0)
    findings = [
        dream_finding(
            pack=pack,
            dream_function="compensatory",
            title=f"Compensatory check: {term} may be carrying an unresolved edge",
            summary=(
                f"The selected real-history pack shows {term} across {source_thread_count} source threads. "
                "Treat the missing or unresolved edge as a background hypothesis before using it in recall."
            ),
            confidence=0.66,
        ),
        dream_finding(
            pack=pack,
            dream_function="amplification",
            title=f"Amplification check: {term} resonates across selected threads",
            summary=(
                f"The selected rows share {term} across multiple source-backed surfaces. "
                "Use this as a reflection bridge only after reopening source for factual claims."
            ),
            confidence=0.68,
        ),
    ]
    adjudicated = background_adjudicate_dream_findings(
        findings,
        source_pack=pack,
        adjudication_source="deterministic_real_history_dream_eval",
    )
    working_rows = adjudicated_dream_findings_to_working_memory(adjudicated)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_pack_dream_worker",
        "status": "candidate_emitted" if findings else "no_candidate",
        "pack_id": pack.get("pack_id"),
        "findings": findings,
        "adjudicated_findings": adjudicated,
        "dream_working_memory_rows": working_rows,
    }


def row_terms(row: Mapping[str, Any]) -> list[str]:
    explicit = [*(row.get("terms") or []), *(row.get("trigger_terms") or []), *(row.get("concepts") or [])]
    text = " ".join(str(row.get(key) or "") for key in ("title", "summary", "recommendation"))
    return unique_preserve(
        [term for term in (normalized_term(item) for item in explicit) if term] + terms_from_text(text),
        limit=20,
    )


def source_thread_count(row: Mapping[str, Any]) -> int:
    return len(source_threads(ref for ref in row.get("source_refs") or [] if isinstance(ref, Mapping)))


def dream_surface_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "surface": "dream_working_memory",
        "row_id": row.get("candidate_key"),
        "seed_kind": row.get("candidate_type"),
        "terms": row_terms(row),
        "source_refs": row.get("source_refs") or [],
        "reflection_ready": "reflection_space" in (row.get("downstream_use") or []),
        "bridge_claim_count": len(row.get("source_finding_ids") or []),
    }


def prompt_matches(prompt: str, row: Mapping[str, Any]) -> bool:
    low = prompt.casefold()
    return any(str(term).casefold() in low for term in row_terms(row))


def surface_metrics(prompts: Iterable[str], rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    prompt_list = list(prompts)
    row_list = list(rows)
    hit_count = 0
    source_thread_total = 0
    reflection_ready_total = 0
    bridge_claim_total = 0
    for prompt in prompt_list:
        matches = [row for row in row_list if prompt_matches(prompt, row)]
        if matches:
            hit_count += 1
        source_thread_total += max([source_thread_count(row) for row in matches] or [0])
        reflection_ready_total += sum(1 for row in matches if row.get("reflection_ready"))
        bridge_claim_total += max([int(row.get("bridge_claim_count") or 0) for row in matches] or [0])
    denominator = max(1, len(prompt_list))
    return {
        "prompt_count": len(prompt_list),
        "prompt_hit_count": hit_count,
        "prompt_hit_rate": round(hit_count / denominator, 4),
        "source_thread_coverage": round(source_thread_total / denominator, 4),
        "reflection_ready_count": reflection_ready_total,
        "bridge_claim_coverage": round(bridge_claim_total / denominator, 4),
    }


def compare_plain_and_augmented(
    *,
    packs: list[dict[str, Any]],
    dream_working_memory_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    prompts = [prompt for pack in packs for prompt in pack.get("eval_prompts") or []]
    plain_rows = [row for pack in packs for row in pack.get("eval_surface_rows") or []]
    dream_rows = [dream_surface_row(row) for row in dream_working_memory_rows]
    plain = surface_metrics(prompts, plain_rows)
    augmented = surface_metrics(prompts, [*plain_rows, *dream_rows])
    return {
        "plain": plain,
        "augmented": augmented,
        "lift": {
            "prompt_hit_rate_delta": round(augmented["prompt_hit_rate"] - plain["prompt_hit_rate"], 4),
            "source_thread_coverage_delta": round(
                augmented["source_thread_coverage"] - plain["source_thread_coverage"], 4
            ),
            "reflection_ready_delta": augmented["reflection_ready_count"] - plain["reflection_ready_count"],
            "bridge_claim_coverage_delta": round(
                augmented["bridge_claim_coverage"] - plain["bridge_claim_coverage"], 4
            ),
        },
    }


def sanitized_pack(pack: Mapping[str, Any]) -> dict[str, Any]:
    audit = pack.get("source_ref_audit") or {}
    return {
        "pack_id": pack.get("pack_id"),
        "kind": pack.get("kind"),
        "status": pack.get("status"),
        "pack_kind": pack.get("pack_kind"),
        "selection": pack.get("selection"),
        "source_seed_kinds": pack.get("source_seed_kinds") or [],
        "source_ref_audit": {
            "status": audit.get("status"),
            "source_ref_count": audit.get("source_ref_count"),
            "source_thread_count": audit.get("source_thread_count"),
            "clean_source_resolution": audit.get("clean_source_resolution"),
        },
        "themes": unique_preserve(
            [str((pack.get("selection") or {}).get("resonance_term") or "")],
            limit=1,
        ),
        "eligible_dream_functions": pack.get("eligible_dream_functions") or [],
        "truth_boundary": pack.get("truth_boundary"),
    }


def eval_status(pack_count: int, min_packs: int, lift: Mapping[str, Any]) -> str:
    if pack_count < min_packs:
        return "insufficient_real_history_packs"
    if (
        float(lift.get("source_thread_coverage_delta") or 0.0) > 0
        or int(lift.get("reflection_ready_delta") or 0) > 0
        or float(lift.get("bridge_claim_coverage_delta") or 0.0) > 0
    ):
        return "lift_observed"
    return "no_lift_observed"


def run_dream_real_history_eval(
    *,
    job_rows: Iterable[Mapping[str, Any]] | None = None,
    working_memory_rows: Iterable[Mapping[str, Any]] | None = None,
    registry_dir: Path | None = None,
    jobs_path: Path | None = None,
    working_memory_path: Path | None = None,
    max_packs: int = 4,
    min_packs: int = 1,
) -> dict[str, Any]:
    registry_path, _ = registry_paths(registry_dir)
    jobs = list(job_rows) if job_rows is not None else iter_jsonl(jobs_path or default_jobs_path(registry_path))
    working_rows = (
        list(working_memory_rows)
        if working_memory_rows is not None
        else load_working_memory(working_memory_path or default_working_memory_path(registry_path))
    )
    packs = select_real_history_packs(
        job_rows=jobs,
        working_memory_rows=working_rows,
        max_packs=max_packs,
    )
    worker_runs = [run_pack_dream_worker(pack) for pack in packs]
    dream_working_rows = [
        row
        for run in worker_runs
        for row in run.get("dream_working_memory_rows") or []
        if isinstance(row, dict)
    ]
    comparison = compare_plain_and_augmented(
        packs=packs,
        dream_working_memory_rows=dream_working_rows,
    )
    seed_kind_counts = Counter(
        kind for pack in packs for kind in (pack.get("source_seed_kinds") or [])
    )
    status = eval_status(len(packs), min_packs, comparison["lift"])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVAL_KIND,
        "created_at": now_utc(),
        "status": status,
        "claim_level": CLAIM_LEVEL,
        "private_text_emitted": False,
        "metrics": {
            "job_row_count": len(jobs),
            "working_memory_row_count": len(working_rows),
            "pack_count": len(packs),
            "dream_finding_count": sum(len(run.get("findings") or []) for run in worker_runs),
            "dream_working_memory_count": len(dream_working_rows),
            "source_seed_kind_counts": dict(sorted(seed_kind_counts.items())),
            **comparison,
        },
        "packs": [sanitized_pack(pack) for pack in packs],
        "live_worker_contract": dream_live_worker_cache_contract(),
        "can_claim": [
            "selected_real_history_packs_have_structural_cross_thread_source_refs",
            "deterministic_dream_hypotheses_can_be_compared_against_plain_rows",
        ],
        "cannot_claim": [
            "private_real_history_dream_quality",
            "live_model_behavioral_lift",
            "full_history_coverage",
            "user_visible_reflection_value",
            "clean_source_resolution_without_reopen",
            "formal_memory_promotion",
        ],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run selected real-history dream structural eval.")
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--working-memory", type=Path)
    parser.add_argument("--max-packs", type=int, default=4)
    parser.add_argument("--min-packs", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_dream_real_history_eval(
        registry_dir=args.registry_dir,
        jobs_path=args.jobs,
        working_memory_path=args.working_memory,
        max_packs=args.max_packs,
        min_packs=args.min_packs,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("status") in {"lift_observed", "no_lift_observed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
