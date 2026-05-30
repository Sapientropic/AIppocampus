#!/usr/bin/env python3
"""Private real-history question-aware recall structural benchmark.

This runner evaluates whether source-backed question/theme rows can form a
compact recall scaffold without leaking private source text. It is a structural
proxy only: exact quotes and final claims still require reopening clean source.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import _paths

_paths.ensure_paths()

import benchmark_cognitive_portrait as portrait  # noqa: E402
from registry import registry_paths  # noqa: E402
from subconscious_jobs_config import default_jobs_output_path  # noqa: E402

SCHEMA_VERSION = 1
BENCHMARK_KIND = "aippocampus_question_aware_real_history_benchmark"
SOURCE_FINDING_KINDS = {
    "question_candidate",
    "frontier_marker",
    "question_link",
    "theme_candidate",
}
PORTRAIT_FINDING_KINDS = {
    "question_candidate",
    "frontier_marker",
    "question_link",
    "theme_candidate",
}
DEFAULT_ROWS_PER_PACK = 32


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


def finding_kind(row: Mapping[str, Any]) -> str:
    return str(row.get("finding_kind") or row.get("kind") or "").strip()


def row_id(row: Mapping[str, Any]) -> str:
    return portrait.row_id(row)


def source_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    return portrait.source_refs(row)


def source_ref_hashes(refs: Iterable[Mapping[str, Any]]) -> list[str]:
    hashes: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        token = portrait.stable_ref_token(ref)
        digest = "sr_" + portrait.sha1_text(token)[:12]
        if digest in seen:
            continue
        seen.add(digest)
        hashes.append(digest)
    return hashes


def is_relevant_source_backed(row: Mapping[str, Any]) -> bool:
    return finding_kind(row) in SOURCE_FINDING_KINDS and bool(source_refs(row))


def compact_values(values: Iterable[Any], *, limit: int = 16) -> list[str]:
    return portrait.unique_preserve(values, limit=limit)


def render_plain_source_terms(rows: Iterable[Mapping[str, Any]]) -> str:
    lines = [
        "Plain source-derived terms for structural comparison.",
        "This is not source text; reopen clean source for quotes.",
    ]
    for row in rows:
        refs = ", ".join(source_ref_hashes(source_refs(row)))
        label = (
            row.get("question_short")
            or row.get("linked_question_short")
            or row.get("theme_short")
            or row.get("title")
            or finding_kind(row)
        )
        concepts = ", ".join(compact_values(row.get("concepts") or row.get("shared_concepts") or []))
        lines.append(f"- {finding_kind(row)}: {portrait.compact_text(label, 90)} [{refs}] {concepts}")
    return "\n".join(lines)


def expected_terms_for_rows(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    terms: list[Any] = []
    for row in rows:
        terms.extend(row.get("concepts") or [])
        terms.extend(row.get("shared_concepts") or [])
        terms.extend(
            [
                row.get("question_short"),
                row.get("linked_question_short"),
                row.get("theme_short"),
            ]
        )
    return compact_values(terms, limit=24)


def structural_case_metrics(
    *,
    rows: Sequence[Mapping[str, Any]],
    plain_context: str,
    portrait_context: str,
) -> dict[str, Any]:
    expected_terms = expected_terms_for_rows(rows)
    plain_hits, total, _plain_missing = portrait.term_coverage(plain_context, expected_terms)
    portrait_hits, _total, _portrait_missing = portrait.term_coverage(
        portrait_context,
        expected_terms,
    )
    quote_required = sum(1 for row in rows if str(row.get("question_text") or "").strip())
    plain_coverage = round(plain_hits / max(1, total), 4)
    question_aware_coverage = round(portrait_hits / max(1, total), 4)
    return {
        "prompt_case_count": 1 if expected_terms else 0,
        "expected_term_count": total,
        "plain_term_coverage": plain_coverage,
        "question_aware_term_coverage": question_aware_coverage,
        "term_coverage_delta": round(question_aware_coverage - plain_coverage, 4),
        "quote_required_case_count": quote_required,
        "prompt_case_hashes": ["pc_" + portrait.sha1_text("|".join(expected_terms))[:12]]
        if expected_terms
        else [],
    }


def build_question_aware_pack(
    rows: Sequence[Mapping[str, Any]],
    *,
    pack_index: int,
    include_private_text: bool = False,
) -> dict[str, Any]:
    portrait_rows = [row for row in rows if finding_kind(row) in PORTRAIT_FINDING_KINDS]
    cognitive_portrait = portrait.build_cognitive_portrait(portrait_rows)
    portrait_context = portrait.render_structured_portrait(cognitive_portrait)
    plain_context = render_plain_source_terms(rows)
    source_ref_count = sum(len(source_refs(row)) for row in rows)
    source_thread_count = len(
        {
            str(ref.get("thread_key") or "")
            for row in rows
            for ref in source_refs(row)
            if ref.get("thread_key")
        }
    )
    source_fidelity = portrait.source_fidelity_metrics(cognitive_portrait)
    over_personalization = portrait.over_personalization_metrics(
        {"question_aware_portrait": portrait_context}
    )
    seed_kind_counts = Counter(finding_kind(row) for row in rows)
    structural_cases = structural_case_metrics(
        rows=rows,
        plain_context=plain_context,
        portrait_context=portrait_context,
    )
    pack_id = "qhr_" + portrait.sha1_text("|".join(row_id(row) for row in rows))[:16]
    payload: dict[str, Any] = {
        "pack_id": pack_id,
        "pack_index": pack_index,
        "source_seed_kind_counts": dict(sorted(seed_kind_counts.items())),
        "source_ref_audit": {
            "source_ref_count": source_ref_count,
            "source_thread_count": source_thread_count,
            "source_ref_hashes": source_ref_hashes(ref for row in rows for ref in source_refs(row))[:16],
        },
        "portrait_item_count": source_fidelity["portrait_item_count"],
        "theme_candidate_count": seed_kind_counts.get("theme_candidate", 0),
        "source_fidelity_rate": source_fidelity["source_fidelity_rate"],
        "plain_context_approx_tokens": portrait.approx_token_count(plain_context),
        "question_aware_context_approx_tokens": portrait.approx_token_count(portrait_context),
        "over_personalization_risk_count": over_personalization["risk_counts"].get(
            "question_aware_portrait",
            0,
        ),
        **structural_cases,
    }
    payload["question_aware_to_plain_token_ratio"] = round(
        payload["question_aware_context_approx_tokens"]
        / max(1, payload["plain_context_approx_tokens"]),
        4,
    )
    if include_private_text:
        payload["debug_contexts"] = {
            "plain_source_terms": plain_context,
            "question_aware_portrait": portrait_context,
        }
    return payload


def select_question_aware_packs(
    *,
    job_rows: Iterable[Mapping[str, Any]],
    max_packs: int = 4,
    rows_per_pack: int = DEFAULT_ROWS_PER_PACK,
    include_private_text: bool = False,
) -> list[dict[str, Any]]:
    eligible = [dict(row) for row in job_rows if is_relevant_source_backed(row)]
    eligible.sort(
        key=lambda row: (
            str(row.get("created_at") or ""),
            finding_kind(row),
            row_id(row),
        )
    )
    packs: list[dict[str, Any]] = []
    for start in range(0, len(eligible), max(1, rows_per_pack)):
        chunk = eligible[start : start + max(1, rows_per_pack)]
        if not chunk:
            continue
        packs.append(
            build_question_aware_pack(
                chunk,
                pack_index=len(packs) + 1,
                include_private_text=include_private_text,
            )
        )
        if len(packs) >= max(1, max_packs):
            break
    return packs


def pack_selection_report(
    *,
    rows: Sequence[Mapping[str, Any]],
    packs: Sequence[Mapping[str, Any]],
    max_packs: int,
    min_packs: int,
    rows_per_pack: int,
) -> dict[str, Any]:
    eligible = [row for row in rows if is_relevant_source_backed(row)]
    available_kind_counts: Counter[str] = Counter()
    for row in eligible:
        available_kind_counts[finding_kind(row)] += 1
    selected_kind_counts: Counter[str] = Counter()
    for pack in packs:
        selected_kind_counts.update(pack.get("source_seed_kind_counts") or {})
    missing_selected_kinds = sorted(
        SOURCE_FINDING_KINDS - set(selected_kind_counts),
        key=str.casefold,
    )
    return {
        "strategy": "chronological_source_backed_question_rows",
        "max_packs": max_packs,
        "min_packs": min_packs,
        "rows_per_pack": rows_per_pack,
        "job_row_count": len(rows),
        "eligible_row_count": len(eligible),
        "available_eligible_kind_counts": dict(sorted(available_kind_counts.items())),
        "skipped_unbacked_row_count": sum(
            1
            for row in rows
            if finding_kind(row) in SOURCE_FINDING_KINDS and not source_refs(row)
        ),
        "selected_pack_count": len(packs),
        "selected_source_seed_kind_counts": dict(sorted(selected_kind_counts.items())),
        "missing_selected_kinds": missing_selected_kinds,
        "selected_lacks_link_or_theme_context": not (
            selected_kind_counts.get("question_link") or selected_kind_counts.get("theme_candidate")
        ),
        "pack_ids": [str(pack.get("pack_id") or "") for pack in packs],
        "sanitization": {
            "source_refs": "hashed",
            "private_text_default": "omitted",
            "debug_private_text_requires_flag": True,
        },
    }


def aggregate_metrics(packs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    source_seed_kind_counts: Counter[str] = Counter()
    for pack in packs:
        source_seed_kind_counts.update(pack.get("source_seed_kind_counts") or {})
    total_plain = sum(int(pack.get("plain_context_approx_tokens") or 0) for pack in packs)
    total_portrait = sum(
        int(pack.get("question_aware_context_approx_tokens") or 0) for pack in packs
    )
    total_expected_terms = sum(int(pack.get("expected_term_count") or 0) for pack in packs)
    plain_hits = sum(
        float(pack.get("plain_term_coverage") or 0.0)
        * int(pack.get("expected_term_count") or 0)
        for pack in packs
    )
    question_aware_hits = sum(
        float(pack.get("question_aware_term_coverage") or 0.0)
        * int(pack.get("expected_term_count") or 0)
        for pack in packs
    )
    plain_coverage = round(plain_hits / max(1, total_expected_terms), 4)
    question_aware_coverage = round(question_aware_hits / max(1, total_expected_terms), 4)
    return {
        "pack_count": len(packs),
        "source_seed_kind_counts": dict(sorted(source_seed_kind_counts.items())),
        "source_ref_fidelity_rate": min(
            [float(pack.get("source_fidelity_rate") or 0.0) for pack in packs] or [0.0]
        ),
        "portrait_token_ratio": round(total_portrait / max(1, total_plain), 4),
        "plain_term_coverage": plain_coverage,
        "question_aware_term_coverage": question_aware_coverage,
        "term_coverage_delta": round(question_aware_coverage - plain_coverage, 4),
        "prompt_case_count": sum(int(pack.get("prompt_case_count") or 0) for pack in packs),
        "quote_required_case_count": sum(
            int(pack.get("quote_required_case_count") or 0) for pack in packs
        ),
        "over_personalization_risk_count": sum(
            int(pack.get("over_personalization_risk_count") or 0) for pack in packs
        ),
        "raw_text_emitted": any("debug_contexts" in pack for pack in packs),
    }


def scaffold_vs_evidence_report(metrics: Mapping[str, Any]) -> dict[str, Any]:
    delta = float(metrics.get("term_coverage_delta") or 0.0)
    if delta >= 0:
        verdict = "question_aware_scaffold_preserves_or_improves_structural_terms"
    else:
        verdict = "question_aware_scaffold_loses_structural_terms"
    return {
        "answer_usefulness_evidence": {
            "measurement": "deterministic_structural_proxy",
            "live_model_answer_quality_measured": False,
            "plain_term_coverage": metrics.get("plain_term_coverage", 0.0),
            "question_aware_term_coverage": metrics.get("question_aware_term_coverage", 0.0),
            "term_coverage_delta": metrics.get("term_coverage_delta", 0.0),
            "verdict": verdict,
        },
        "helpful_recall_scaffolding": [
            "source-backed question/frontier/link/theme rows can be selected into sanitized packs",
            "hashed source-ref back-pointers preserve a route for later clean-source lookup",
            "structural term coverage can be compared with a plain source-derived baseline",
        ],
        "requires_clean_source_lookup": [
            "exact quotes",
            "final factual claims",
            "user-visible summaries",
            "answer-quality judgments beyond the deterministic structural proxy",
        ],
    }


def benchmark_status(
    *,
    packs: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    selection: Mapping[str, Any],
    min_packs: int,
) -> str:
    if len(packs) < min_packs or float(metrics.get("source_ref_fidelity_rate") or 0.0) < 1.0:
        return "insufficient_real_history_packs"
    if float(metrics.get("term_coverage_delta") or 0.0) < 0.0:
        return "structural_proxy_ready_but_scaffold_regressed"
    if (
        float(metrics.get("portrait_token_ratio") or 0.0) >= 1.0
        or selection.get("selected_lacks_link_or_theme_context")
    ):
        return "structural_proxy_ready_but_lookup_required"
    return "structural_proxy_ready"


def known_failure_modes(
    metrics: Mapping[str, Any],
    *,
    status: str,
    selection: Mapping[str, Any],
) -> list[dict[str, str]]:
    modes: list[dict[str, str]] = [
        {
            "code": "structural_proxy_not_answer_quality",
            "severity": "expected",
            "meaning": "The benchmark compares sanitized scaffold structure, not live model answers.",
            "next_step": "Run an opt-in clean-source answer comparison before claiming user-visible lift.",
        },
        {
            "code": "clean_source_required_for_evidence",
            "severity": "expected",
            "meaning": "Hashed refs and portraits are navigation hints; source text remains authoritative.",
            "next_step": "Reopen clean source for quotes and factual claims.",
        },
        {
            "code": "selected_slice_not_full_history",
            "severity": "expected",
            "meaning": "The benchmark samples eligible rows into bounded packs; it is not full-history coverage.",
            "next_step": "Use broader selected packs or a full-history run before coverage claims.",
        },
    ]
    if status == "insufficient_real_history_packs":
        modes.append(
            {
                "code": "insufficient_real_history_packs",
                "severity": "blocking",
                "meaning": "Too few source-backed question rows were available for the requested pack count.",
                "next_step": "Run question extraction/tracking/theme jobs or lower min-packs for diagnostics.",
            }
        )
    if int(metrics.get("quote_required_case_count") or 0) > 0:
        modes.append(
            {
                "code": "quote_fidelity_requires_clean_source_reopen",
                "severity": "expected",
                "meaning": "Some selected rows contain question text, but default benchmark output omits it.",
                "next_step": "Use clean-source lookup for quote validation; do not infer quote fidelity from packs.",
            }
        )
    if float(metrics.get("portrait_token_ratio") or 0.0) >= 1.0:
        modes.append(
            {
                "code": "question_aware_scaffold_not_token_cheaper",
                "severity": "warning",
                "meaning": "The question-aware scaffold is not smaller than the plain structural baseline.",
                "next_step": "Do not claim token savings; tune portrait rendering before size claims.",
            }
        )
    if float(metrics.get("term_coverage_delta") or 0.0) < 0.0:
        modes.append(
            {
                "code": "question_aware_term_coverage_regressed",
                "severity": "warning",
                "meaning": "The question-aware scaffold preserved fewer expected structural terms than the plain baseline.",
                "next_step": "Treat the pack as navigation-only and improve rendering before helpfulness claims.",
            }
        )
    if selection.get("selected_lacks_link_or_theme_context"):
        modes.append(
            {
                "code": "selected_rows_lack_link_or_theme_context",
                "severity": "warning",
                "meaning": "Selected packs do not yet include recurring question links or theme candidates.",
                "next_step": "Run tracking/theme materialization or select richer packs before question-aware recall claims.",
            }
        )
    if float(metrics.get("source_ref_fidelity_rate") or 0.0) < 1.0:
        modes.append(
            {
                "code": "source_ref_fidelity_gap",
                "severity": "blocking",
                "meaning": "At least one reusable portrait item lost its source-ref back-pointer.",
                "next_step": "Fix source-ref propagation before using the scaffold.",
            }
        )
    if int(metrics.get("over_personalization_risk_count") or 0) > 0:
        modes.append(
            {
                "code": "over_personalization_risk_detected",
                "severity": "warning",
                "meaning": "A rendered scaffold contains trait-like or identity-like phrasing.",
                "next_step": "Keep the output as private diagnostics until wording is reviewed.",
            }
        )
    return modes


def run_question_aware_real_history_benchmark(
    *,
    job_rows: Iterable[Mapping[str, Any]] | None = None,
    registry_dir: Path | None = None,
    jobs_path: Path | None = None,
    max_packs: int = 4,
    min_packs: int = 1,
    rows_per_pack: int = DEFAULT_ROWS_PER_PACK,
    include_private_text: bool = False,
) -> dict[str, Any]:
    registry_path, _ = registry_paths(registry_dir)
    rows = list(job_rows) if job_rows is not None else list(iter_jsonl(jobs_path or default_jobs_output_path(registry_path)))
    packs = select_question_aware_packs(
        job_rows=rows,
        max_packs=max_packs,
        rows_per_pack=rows_per_pack,
        include_private_text=include_private_text,
    )
    metrics = aggregate_metrics(packs)
    selection = pack_selection_report(
        rows=rows,
        packs=packs,
        max_packs=max_packs,
        min_packs=min_packs,
        rows_per_pack=rows_per_pack,
    )
    status = benchmark_status(
        packs=packs,
        metrics=metrics,
        selection=selection,
        min_packs=min_packs,
    )
    scaffold_report = scaffold_vs_evidence_report(metrics)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": BENCHMARK_KIND,
        "created_at": portrait.now_utc(),
        "status": status,
        "claim_level": "private_structural_proxy",
        "private_text_emitted": include_private_text,
        "job_row_count": len(rows),
        "eligible_row_count": sum(1 for row in rows if is_relevant_source_backed(row)),
        "pack_selection": selection,
        "metrics": metrics,
        "scaffold_vs_evidence": scaffold_report,
        "known_failure_modes": known_failure_modes(
            metrics,
            status=status,
            selection=selection,
        ),
        "packs": packs,
        "can_claim": [
            "selected_question_rows_can_form_sanitized_source_backed_structural_packs",
            "question_aware_portrait_preserves_back_pointers_for_navigation",
            "known_failure_modes_are_reported_without_private_text",
        ],
        "cannot_claim": [
            "private_real_history_answer_quality",
            "live_model_behavioral_equivalence",
            "full_history_coverage",
            "quote_fidelity_without_clean_source_reopen",
            "user_visible_recall_improvement",
            "identity_or_personality_profile_validity",
            "answer_usefulness_beyond_structural_proxy",
        ],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run private real-history question-aware recall structural benchmark."
    )
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--max-packs", type=int, default=4)
    parser.add_argument("--min-packs", type=int, default=1)
    parser.add_argument("--rows-per-pack", type=int, default=DEFAULT_ROWS_PER_PACK)
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_question_aware_real_history_benchmark(
        registry_dir=args.registry_dir,
        jobs_path=args.jobs,
        max_packs=args.max_packs,
        min_packs=args.min_packs,
        rows_per_pack=args.rows_per_pack,
        include_private_text=args.include_private_text,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if str(payload.get("status") or "").startswith("structural_proxy_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
