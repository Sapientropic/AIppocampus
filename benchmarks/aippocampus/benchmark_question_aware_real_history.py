#!/usr/bin/env python3
"""Private real-history question-aware recall structural benchmark.

This runner evaluates whether source-backed question/theme rows can form a
compact recall scaffold without leaking private source text. It is a structural
proxy only: exact quotes and final claims still require reopening clean source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import _paths

_paths.ensure_paths()

import benchmark_cognitive_portrait as portrait  # noqa: E402
import benchmark_question_tracking_calibration as calibration  # noqa: E402
import question_aware_public_shadow_support as public_shadow_support  # noqa: E402
from aippocampus_runtime.registry.api import registry_paths  # noqa: E402
from aippocampus_runtime.subconscious.jobs_config import default_jobs_output_path  # noqa: E402
from aippocampus_runtime.subconscious.question_extraction_gate import (  # noqa: E402
    question_extraction_skip_reason,
)

SCHEMA_VERSION = 1
BENCHMARK_KIND = "aippocampus_question_aware_real_history_benchmark"
PUBLIC_SHADOW_KIND = "aippocampus_question_aware_public_shadow_benchmark"
DEFAULT_PUBLIC_SHADOW_FIXTURE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "question_aware_public_shadow" / "fixture.json"
)
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
ANSWER_QUALITY_REVIEW_KIND = "question_aware_answer_quality_review"
EVALUATION_DESIGN_KIND = "question_aware_evaluation_design_diagnostic"
ANSWER_QUALITY_REVIEW_ARMS = (
    "plain_baseline",
    "question_aware_source_reopen",
)


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


def public_digest(value: Any, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


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


def render_question_blind_source_terms(rows: Iterable[Mapping[str, Any]]) -> str:
    lines = [
        "Question-blind source-derived terms for structural comparison.",
        "This omits question/theme labels; reopen clean source for quotes.",
    ]
    for row in rows:
        refs = ", ".join(source_ref_hashes(source_refs(row)))
        # This is still a same-selected-row structural proxy, not a true
        # retrieval baseline. It intentionally keeps only generic row kind,
        # source back-pointers, and non-theme concept tags so question-aware
        # labels must earn their lift instead of being handed to the baseline.
        concepts = ", ".join(compact_values(row.get("concepts") or []))
        concept_suffix = f" concepts={concepts}" if concepts else ""
        lines.append(f"- {finding_kind(row)} [{refs}]{concept_suffix}")
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
    question_blind_context: str,
    portrait_context: str,
) -> dict[str, Any]:
    expected_terms = expected_terms_for_rows(rows)
    plain_hits, total, _plain_missing = portrait.term_coverage(plain_context, expected_terms)
    question_blind_hits, _total, _question_blind_missing = portrait.term_coverage(
        question_blind_context,
        expected_terms,
    )
    portrait_hits, _total, _portrait_missing = portrait.term_coverage(
        portrait_context,
        expected_terms,
    )
    quote_required = sum(1 for row in rows if str(row.get("question_text") or "").strip())
    plain_coverage = round(plain_hits / max(1, total), 4)
    question_blind_coverage = round(question_blind_hits / max(1, total), 4)
    question_aware_coverage = round(portrait_hits / max(1, total), 4)
    return {
        "prompt_case_count": 1 if expected_terms else 0,
        "expected_term_count": total,
        "plain_term_coverage": plain_coverage,
        "question_blind_term_coverage": question_blind_coverage,
        "question_aware_term_coverage": question_aware_coverage,
        "term_coverage_delta": round(question_aware_coverage - plain_coverage, 4),
        "question_aware_over_question_blind_delta": round(
            question_aware_coverage - question_blind_coverage,
            4,
        ),
        "quote_required_case_count": quote_required,
        "prompt_case_hashes": ["pc_" + portrait.sha1_text("|".join(expected_terms))[:12]]
        if expected_terms
        else [],
    }


def no_lift_reason_codes(
    *,
    plain_term_coverage: float,
    question_blind_term_coverage: float,
    question_aware_term_coverage: float,
    term_coverage_delta: float,
    question_aware_over_question_blind_delta: float,
    question_aware_to_plain_token_ratio: float,
    question_aware_to_question_blind_token_ratio: float,
    selected_kind_counts: Mapping[str, Any],
) -> list[str]:
    codes = ["same_selected_rows_baseline"]
    if plain_term_coverage >= 1.0:
        codes.append("plain_baseline_term_ceiling")
    if question_blind_term_coverage >= 1.0:
        codes.append("question_blind_baseline_term_ceiling")
    if term_coverage_delta <= 0.0:
        codes.append("question_aware_no_structural_term_lift")
    if question_aware_over_question_blind_delta <= 0.0:
        codes.append("question_aware_no_question_blind_structural_lift")
    if question_aware_term_coverage < plain_term_coverage:
        codes.append("question_aware_term_coverage_regressed")
    if question_aware_term_coverage < question_blind_term_coverage:
        codes.append("question_aware_question_blind_term_coverage_regressed")
    if question_aware_to_plain_token_ratio >= 1.0:
        codes.append("question_aware_scaffold_longer_than_plain")
    if question_aware_to_question_blind_token_ratio >= 1.0:
        codes.append("question_aware_scaffold_longer_than_question_blind")
    if int(selected_kind_counts.get("theme_candidate") or 0) <= 0:
        codes.append("no_selected_theme_candidates")
    if int(selected_kind_counts.get("question_link") or 0) < 3:
        codes.append("not_enough_selected_question_links_for_theme_layer")
    return codes


def comparison_design_diagnostic(
    *,
    selected_kind_counts: Mapping[str, Any],
    plain_term_coverage: float,
    question_blind_term_coverage: float,
    question_aware_term_coverage: float,
    term_coverage_delta: float,
    question_aware_over_question_blind_delta: float,
    question_aware_to_plain_token_ratio: float,
    question_aware_to_question_blind_token_ratio: float,
) -> dict[str, Any]:
    return {
        "kind": EVALUATION_DESIGN_KIND,
        "same_selected_rows_for_plain_and_question_aware": True,
        "plain_baseline_receives_question_metadata": True,
        "plain_baseline_fields": [
            "question_short",
            "linked_question_short",
            "theme_short",
            "title",
            "concepts",
            "shared_concepts",
            "hashed_source_refs",
        ],
        "question_blind_structural_baseline_measured": True,
        "question_blind_baseline_receives_question_metadata": False,
        "question_blind_baseline_fields": [
            "finding_kind",
            "concepts",
            "hashed_source_refs",
        ],
        "question_blind_is_true_retrieval_baseline": False,
        "expected_terms_derived_from_same_rows": True,
        "selection_lift_measured": False,
        "answer_generation_measured_by_benchmark": False,
        "baseline_contamination_risk": True,
        "plain_baseline_term_ceiling": plain_term_coverage >= 1.0,
        "question_blind_baseline_term_ceiling": question_blind_term_coverage >= 1.0,
        "selected_question_link_count": int(selected_kind_counts.get("question_link") or 0),
        "selected_theme_candidate_count": int(selected_kind_counts.get("theme_candidate") or 0),
        "theme_layer_ready": int(selected_kind_counts.get("theme_candidate") or 0) > 0,
        "term_coverage_delta": term_coverage_delta,
        "question_aware_over_question_blind_delta": question_aware_over_question_blind_delta,
        "question_aware_to_plain_token_ratio": question_aware_to_plain_token_ratio,
        "question_aware_to_question_blind_token_ratio": (
            question_aware_to_question_blind_token_ratio
        ),
        "no_lift_reason_codes": no_lift_reason_codes(
            plain_term_coverage=plain_term_coverage,
            question_blind_term_coverage=question_blind_term_coverage,
            question_aware_term_coverage=question_aware_term_coverage,
            term_coverage_delta=term_coverage_delta,
            question_aware_over_question_blind_delta=question_aware_over_question_blind_delta,
            question_aware_to_plain_token_ratio=question_aware_to_plain_token_ratio,
            question_aware_to_question_blind_token_ratio=(
                question_aware_to_question_blind_token_ratio
            ),
            selected_kind_counts=selected_kind_counts,
        ),
        "valid_next_evaluation": [
            "compare a true no-question-aware retrieval/answer path against a question-aware retrieval/answer path",
            "materialize enough source-backed question links and theme candidates before testing theme-aware lift",
            "record actual generated answer arms or source-reopened operator review without giving the plain arm question-aware metadata",
        ],
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
    question_blind_context = render_question_blind_source_terms(rows)
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
        question_blind_context=question_blind_context,
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
        "question_blind_context_approx_tokens": portrait.approx_token_count(
            question_blind_context
        ),
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
    payload["question_aware_to_question_blind_token_ratio"] = round(
        payload["question_aware_context_approx_tokens"]
        / max(1, payload["question_blind_context_approx_tokens"]),
        4,
    )
    payload["comparison_design"] = comparison_design_diagnostic(
        selected_kind_counts=seed_kind_counts,
        plain_term_coverage=float(payload["plain_term_coverage"]),
        question_blind_term_coverage=float(payload["question_blind_term_coverage"]),
        question_aware_term_coverage=float(payload["question_aware_term_coverage"]),
        term_coverage_delta=float(payload["term_coverage_delta"]),
        question_aware_over_question_blind_delta=float(
            payload["question_aware_over_question_blind_delta"]
        ),
        question_aware_to_plain_token_ratio=float(payload["question_aware_to_plain_token_ratio"]),
        question_aware_to_question_blind_token_ratio=float(
            payload["question_aware_to_question_blind_token_ratio"]
        ),
    )
    if include_private_text:
        payload["debug_contexts"] = {
            "plain_source_terms": plain_context,
            "question_blind_source_terms": question_blind_context,
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
    total_question_blind = sum(
        int(pack.get("question_blind_context_approx_tokens") or 0) for pack in packs
    )
    total_portrait = sum(
        int(pack.get("question_aware_context_approx_tokens") or 0) for pack in packs
    )
    total_expected_terms = sum(int(pack.get("expected_term_count") or 0) for pack in packs)
    plain_hits = sum(
        float(pack.get("plain_term_coverage") or 0.0)
        * int(pack.get("expected_term_count") or 0)
        for pack in packs
    )
    question_blind_hits = sum(
        float(pack.get("question_blind_term_coverage") or 0.0)
        * int(pack.get("expected_term_count") or 0)
        for pack in packs
    )
    question_aware_hits = sum(
        float(pack.get("question_aware_term_coverage") or 0.0)
        * int(pack.get("expected_term_count") or 0)
        for pack in packs
    )
    plain_coverage = round(plain_hits / max(1, total_expected_terms), 4)
    question_blind_coverage = round(question_blind_hits / max(1, total_expected_terms), 4)
    question_aware_coverage = round(question_aware_hits / max(1, total_expected_terms), 4)
    return {
        "pack_count": len(packs),
        "source_seed_kind_counts": dict(sorted(source_seed_kind_counts.items())),
        "source_ref_fidelity_rate": min(
            [float(pack.get("source_fidelity_rate") or 0.0) for pack in packs] or [0.0]
        ),
        "portrait_token_ratio": round(total_portrait / max(1, total_plain), 4),
        "question_aware_to_question_blind_token_ratio": round(
            total_portrait / max(1, total_question_blind),
            4,
        ),
        "plain_term_coverage": plain_coverage,
        "question_blind_term_coverage": question_blind_coverage,
        "question_aware_term_coverage": question_aware_coverage,
        "term_coverage_delta": round(question_aware_coverage - plain_coverage, 4),
        "question_aware_over_question_blind_delta": round(
            question_aware_coverage - question_blind_coverage,
            4,
        ),
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
            "question_blind_term_coverage": metrics.get("question_blind_term_coverage", 0.0),
            "question_aware_term_coverage": metrics.get("question_aware_term_coverage", 0.0),
            "term_coverage_delta": metrics.get("term_coverage_delta", 0.0),
            "question_aware_over_question_blind_delta": metrics.get(
                "question_aware_over_question_blind_delta",
                0.0,
            ),
            "verdict": verdict,
        },
        "helpful_recall_scaffolding": [
            "source-backed question/frontier/link/theme rows can be selected into sanitized packs",
            "hashed source-ref back-pointers preserve a route for later clean-source lookup",
        "structural term coverage can be compared with a plain source-derived baseline",
        "question-aware labels can also be compared with a question-blind same-row baseline",
        ],
        "requires_clean_source_lookup": [
            "exact quotes",
            "final factual claims",
            "user-visible summaries",
            "answer-quality judgments beyond the deterministic structural proxy",
        ],
    }


def evaluation_design_report(
    *,
    metrics: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> dict[str, Any]:
    selected_kind_counts = selection.get("selected_source_seed_kind_counts") or {}
    return comparison_design_diagnostic(
        selected_kind_counts=selected_kind_counts,
        plain_term_coverage=float(metrics.get("plain_term_coverage") or 0.0),
        question_blind_term_coverage=float(metrics.get("question_blind_term_coverage") or 0.0),
        question_aware_term_coverage=float(metrics.get("question_aware_term_coverage") or 0.0),
        term_coverage_delta=float(metrics.get("term_coverage_delta") or 0.0),
        question_aware_over_question_blind_delta=float(
            metrics.get("question_aware_over_question_blind_delta") or 0.0
        ),
        question_aware_to_plain_token_ratio=float(metrics.get("portrait_token_ratio") or 0.0),
        question_aware_to_question_blind_token_ratio=float(
            metrics.get("question_aware_to_question_blind_token_ratio") or 0.0
        ),
    )


def parse_review_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "pass", "passed"}:
        return True
    if text in {"0", "false", "no", "n", "fail", "failed"}:
        return False
    return None


def parse_review_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def answer_quality_review_kind(row: Mapping[str, Any]) -> str:
    return str(row.get("kind") or row.get("review_kind") or "").strip()


def answer_quality_case_id(row: Mapping[str, Any]) -> str:
    return str(row.get("case_id") or row.get("prompt_case_id") or row.get("id") or "").strip()


def rate_for(
    case_arms: Sequence[Mapping[str, Mapping[str, Any]]],
    *,
    arm: str,
    field: str,
) -> float | None:
    values = [
        parsed
        for parsed in (parse_review_bool(case[arm].get(field)) for case in case_arms)
        if parsed is not None
    ]
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 4)


def mean_delta_for(
    case_arms: Sequence[Mapping[str, Mapping[str, Any]]],
    *,
    field: str,
) -> float | None:
    deltas: list[float] = []
    for case in case_arms:
        plain = parse_review_float(case["plain_baseline"].get(field))
        question_aware = parse_review_float(case["question_aware_source_reopen"].get(field))
        if plain is None or question_aware is None:
            continue
        deltas.append(question_aware - plain)
    if not deltas:
        return None
    return round(sum(deltas) / len(deltas), 4)


def answer_quality_case_summary(
    case_id: str,
    arms: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    arms_present = [arm for arm in ANSWER_QUALITY_REVIEW_ARMS if arm in arms]
    return {
        "case_hash": public_digest(case_id, prefix="aqr_case"),
        "arms_present": arms_present,
        "complete_comparison": all(arm in arms for arm in ANSWER_QUALITY_REVIEW_ARMS),
        "source_reopened_by_arm": {
            arm: parse_review_bool(arms[arm].get("source_reopened"))
            for arm in arms_present
        },
        "answer_useful_by_arm": {
            arm: parse_review_bool(arms[arm].get("answer_useful"))
            for arm in arms_present
        },
        "answer_supported_by_arm": {
            arm: parse_review_bool(arms[arm].get("answer_supported"))
            for arm in arms_present
        },
        "citation_correct_by_arm": {
            arm: parse_review_bool(arms[arm].get("citation_correct"))
            for arm in arms_present
        },
        "wrong_hint_by_arm": {
            arm: parse_review_bool(arms[arm].get("wrong_hint"))
            for arm in arms_present
        },
    }


def answer_quality_review_report(
    review_rows: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    raw_rows = list(review_rows or [])
    cases: dict[str, dict[str, Mapping[str, Any]]] = {}
    invalid_row_count = 0
    ignored_row_count = 0
    duplicate_arm_count = 0

    for row in raw_rows:
        kind = answer_quality_review_kind(row)
        if kind and kind != ANSWER_QUALITY_REVIEW_KIND:
            ignored_row_count += 1
            continue
        case_id = answer_quality_case_id(row)
        arm = str(row.get("arm") or "").strip()
        if not case_id or arm not in ANSWER_QUALITY_REVIEW_ARMS:
            invalid_row_count += 1
            continue
        case = cases.setdefault(case_id, {})
        if arm in case:
            duplicate_arm_count += 1
            continue
        case[arm] = row

    case_summaries = [
        answer_quality_case_summary(case_id, arms)
        for case_id, arms in sorted(cases.items(), key=lambda item: public_digest(item[0], prefix="aqr_case"))
    ]
    complete_case_arms = [
        arms
        for arms in cases.values()
        if all(arm in arms for arm in ANSWER_QUALITY_REVIEW_ARMS)
    ]
    plain_useful = rate_for(
        complete_case_arms,
        arm="plain_baseline",
        field="answer_useful",
    )
    question_aware_useful = rate_for(
        complete_case_arms,
        arm="question_aware_source_reopen",
        field="answer_useful",
    )
    usefulness_delta = (
        round(question_aware_useful - plain_useful, 4)
        if plain_useful is not None and question_aware_useful is not None
        else None
    )
    question_aware_source_reopened = rate_for(
        complete_case_arms,
        arm="question_aware_source_reopen",
        field="source_reopened",
    )

    metrics = {
        "input_row_count": len(raw_rows),
        "review_row_count": sum(len(arms) for arms in cases.values()),
        "ignored_row_count": ignored_row_count,
        "invalid_review_row_count": invalid_row_count,
        "duplicate_arm_row_count": duplicate_arm_count,
        "review_case_count": len(cases),
        "complete_comparison_case_count": len(complete_case_arms),
        "plain_baseline_answer_useful_rate": plain_useful,
        "question_aware_source_reopen_answer_useful_rate": question_aware_useful,
        "answer_usefulness_delta": usefulness_delta,
        "plain_baseline_answer_supported_rate": rate_for(
            complete_case_arms,
            arm="plain_baseline",
            field="answer_supported",
        ),
        "question_aware_answer_supported_rate": rate_for(
            complete_case_arms,
            arm="question_aware_source_reopen",
            field="answer_supported",
        ),
        "plain_baseline_citation_correct_rate": rate_for(
            complete_case_arms,
            arm="plain_baseline",
            field="citation_correct",
        ),
        "question_aware_citation_correct_rate": rate_for(
            complete_case_arms,
            arm="question_aware_source_reopen",
            field="citation_correct",
        ),
        "question_aware_source_reopened_rate": question_aware_source_reopened,
        "question_aware_wrong_hint_rate": rate_for(
            complete_case_arms,
            arm="question_aware_source_reopen",
            field="wrong_hint",
        ),
        "mean_extra_verification_steps_delta": mean_delta_for(
            complete_case_arms,
            field="extra_verification_steps",
        ),
    }

    if not cases:
        status = "answer_quality_review_absent"
    elif len(complete_case_arms) < len(cases):
        status = "answer_quality_review_incomplete"
    elif question_aware_source_reopened != 1.0:
        status = "answer_quality_review_ready_but_source_reopen_gap"
    else:
        status = "selected_source_reopened_answer_quality_review_ready"

    can_claim = ["answer_quality_review_output_is_public_safe"]
    cannot_claim = [
        "full_history_answer_quality",
        "live_model_behavioral_equivalence",
        "user_visible_recall_improvement_without_release_trial",
        "default_prefilter_safety",
    ]
    if status == "selected_source_reopened_answer_quality_review_ready":
        can_claim.append("selected_source_reopened_answer_quality_review_recorded")
    if status == "answer_quality_review_absent":
        cannot_claim.append("selected_answer_quality_review")
    if status == "answer_quality_review_incomplete":
        cannot_claim.append("paired_answer_quality_review_missing")
    if status == "answer_quality_review_ready_but_source_reopen_gap":
        cannot_claim.append("question_aware_source_reopen_not_confirmed")

    return {
        "kind": ANSWER_QUALITY_REVIEW_KIND,
        "status": status,
        "measurement": "opt_in_source_reopened_operator_review_v1",
        "arms": list(ANSWER_QUALITY_REVIEW_ARMS),
        "metrics": metrics,
        "case_summaries": case_summaries,
        "privacy": {
            "case_identifiers": "sha256_hash_only",
            "raw_answer_text_emitted": False,
            "raw_source_text_emitted": False,
            "raw_source_refs_emitted": False,
            "local_paths_emitted": False,
        },
        "can_claim": can_claim,
        "cannot_claim": cannot_claim,
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
    if float(metrics.get("plain_term_coverage") or 0.0) >= 1.0:
        modes.append(
            {
                "code": "plain_baseline_term_ceiling",
                "severity": "warning",
                "meaning": (
                    "The plain baseline already covers all expected structural terms, "
                    "so this run cannot show positive term-coverage lift."
                ),
                "next_step": "Use a true no-question-aware retrieval baseline or harder selected prompts.",
            }
        )
    if float(metrics.get("question_blind_term_coverage") or 0.0) >= 1.0:
        modes.append(
            {
                "code": "question_blind_baseline_term_ceiling",
                "severity": "warning",
                "meaning": (
                    "The question-blind structural baseline already covers all expected terms, "
                    "so this run cannot show positive question-label term lift."
                ),
                "next_step": "Use harder selected prompts or a true no-question-aware retrieval baseline.",
            }
        )
    if int((selection.get("selected_source_seed_kind_counts") or {}).get("question_link") or 0) < 3:
        modes.append(
            {
                "code": "not_enough_selected_question_links_for_theme_layer",
                "severity": "warning",
                "meaning": "The selected slice has too few question_link rows to exercise theme-aware recall.",
                "next_step": "Materialize more source-backed links before testing theme-level lift.",
            }
        )
    if "theme_candidate" in (selection.get("missing_selected_kinds") or []):
        modes.append(
            {
                "code": "no_selected_theme_candidates",
                "severity": "warning",
                "meaning": "The selected slice has no theme_candidate rows, so theme resonance is not being tested.",
                "next_step": "Run theme emergence after enough recurring question links exist.",
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
    if float(metrics.get("question_aware_over_question_blind_delta") or 0.0) <= 0.0:
        modes.append(
            {
                "code": "question_aware_no_question_blind_structural_lift",
                "severity": "warning",
                "meaning": (
                    "Question-aware labels did not add structural expected-term coverage "
                    "over the question-blind same-row baseline."
                ),
                "next_step": (
                    "Use richer question-link/theme rows, improve rendering, or move to "
                    "a source-reopened answer comparison."
                ),
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
    answer_quality_review_rows: Iterable[Mapping[str, Any]] | None = None,
    answer_quality_review_path: Path | None = None,
    registry_dir: Path | None = None,
    jobs_path: Path | None = None,
    max_packs: int = 4,
    min_packs: int = 1,
    rows_per_pack: int = DEFAULT_ROWS_PER_PACK,
    include_private_text: bool = False,
) -> dict[str, Any]:
    registry_path, _ = registry_paths(registry_dir)
    rows = (
        list(job_rows)
        if job_rows is not None
        else list(iter_jsonl(jobs_path or default_jobs_output_path(registry_path)))
    )
    review_rows = (
        list(answer_quality_review_rows)
        if answer_quality_review_rows is not None
        else list(iter_jsonl(answer_quality_review_path))
        if answer_quality_review_path
        else []
    )
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
    evaluation_design = evaluation_design_report(metrics=metrics, selection=selection)
    answer_review = answer_quality_review_report(review_rows)
    can_claim = [
        "selected_question_rows_can_form_sanitized_source_backed_structural_packs",
        "question_aware_portrait_preserves_back_pointers_for_navigation",
        "known_failure_modes_are_reported_without_private_text",
    ]
    if float(metrics.get("question_aware_over_question_blind_delta") or 0.0) > 0.0:
        can_claim.append(
            "question_aware_fields_add_structural_route_terms_over_question_blind_baseline"
        )
    for claim in answer_review["can_claim"]:
        if claim not in can_claim:
            can_claim.append(claim)
    cannot_claim = [
        "private_real_history_answer_quality",
        "live_model_behavioral_equivalence",
        "full_history_coverage",
        "quote_fidelity_without_clean_source_reopen",
        "user_visible_recall_improvement",
        "true_no_question_aware_retrieval_baseline",
        "identity_or_personality_profile_validity",
        "answer_usefulness_beyond_structural_proxy",
    ]
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
        "evaluation_design": evaluation_design,
        "scaffold_vs_evidence": scaffold_report,
        "answer_quality_review": answer_review,
        "known_failure_modes": known_failure_modes(
            metrics,
            status=status,
            selection=selection,
        ),
        "packs": packs,
        "can_claim": can_claim,
        "cannot_claim": cannot_claim,
    }


def read_public_shadow_fixture(path: Path | None = None) -> dict[str, Any]:
    fixture_path = path or DEFAULT_PUBLIC_SHADOW_FIXTURE
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{fixture_path} must contain a JSON object")
    return data


def public_shadow_threshold_readout() -> dict[str, Any]:
    report = calibration.run_question_tracking_calibration()
    modes = (
        report.get("metrics", {})
        .get("six_axis_dynamic_thresholds", {})
        .get("comparison_modes", {})
    )
    return {
        "source": "benchmark_question_tracking_calibration.selected_fixture_scenarios",
        "fixed_similarity_threshold": modes.get("fixed_similarity_threshold", {}),
        "static_strong_threshold": modes.get("static_strong_threshold", {}),
        "dynamic_six_axis_threshold": modes.get("dynamic_six_axis_threshold", {}),
        "claim_boundary": "navigation_policy_calibration_not_source_truth",
    }


def public_shadow_negative_control_readout(
    negative_controls: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    readout: list[dict[str, Any]] = []
    for index, item in enumerate(negative_controls, start=1):
        raw_turn = item.get("turn")
        turn: Mapping[str, Any] = raw_turn if isinstance(raw_turn, Mapping) else {}
        observed_reason = question_extraction_skip_reason(turn)
        expected_reason = str(item.get("expected_skip_reason") or "").strip()
        passed = bool(observed_reason) and (
            not expected_reason or observed_reason == expected_reason
        )
        readout.append(
            {
                "case_hash": public_digest(item.get("case_id") or index, prefix="neg"),
                "kind": item.get("kind"),
                "expected_behavior": item.get("expected_behavior"),
                "expected_skip_reason": expected_reason or None,
                "observed_skip_reason": observed_reason or "selected",
                "passed": passed,
            }
        )
    return readout


def run_question_aware_public_shadow_benchmark(
    *,
    fixture_path: Path | None = None,
) -> dict[str, Any]:
    fixture = read_public_shadow_fixture(fixture_path)
    rows = [row for row in fixture.get("job_rows") or [] if isinstance(row, Mapping)]
    review_rows = [
        row for row in fixture.get("answer_quality_review_rows") or [] if isinstance(row, Mapping)
    ]
    structural = run_question_aware_real_history_benchmark(
        job_rows=rows,
        answer_quality_review_rows=review_rows,
        max_packs=int(fixture.get("max_packs") or 1),
        min_packs=1,
        rows_per_pack=int(fixture.get("rows_per_pack") or max(1, len(rows))),
    )
    threshold_readout = public_shadow_threshold_readout()
    review_metrics = structural["answer_quality_review"]["metrics"]
    manual_query_reduction_delta = round(
        -float(review_metrics.get("mean_extra_verification_steps_delta") or 0.0),
        4,
    )
    raw_metadata = fixture.get("metadata")
    metadata: Mapping[str, Any] = (
        raw_metadata if isinstance(raw_metadata, Mapping) else {}
    )
    negative_controls = [
        item for item in fixture.get("negative_controls") or [] if isinstance(item, Mapping)
    ]
    negative_control_readout = public_shadow_negative_control_readout(negative_controls)
    baseline_preregistration = public_shadow_support.baseline_preregistration(fixture=fixture)
    materialization_review_evidence = public_shadow_support.materialization_review_evidence(
        structural=structural,
        review_metrics=review_metrics,
        manual_query_reduction_delta=manual_query_reduction_delta,
        negative_controls=negative_control_readout,
        threshold_readout=threshold_readout,
    )
    no_question_retrieval_answer_baseline = (
        public_shadow_support.true_no_question_retrieval_answer_baseline(
            fixture=fixture,
            structural=structural,
            review_metrics=review_metrics,
        )
    )
    public_safe_calibration_readout = (
        public_shadow_support.public_safe_local_calibration_readout(
            no_question_baseline=no_question_retrieval_answer_baseline,
            review_metrics=review_metrics,
            negative_controls=negative_control_readout,
            threshold_readout=threshold_readout,
        )
    )
    review_metrics_with_delta = {
        **review_metrics,
        "manual_query_reduction_delta": manual_query_reduction_delta,
    }
    metrics = public_shadow_support.public_shadow_metrics(
        metadata=metadata,
        review_rows=review_rows,
        negative_controls=negative_controls,
        structural=structural,
        review_metrics=review_metrics_with_delta,
        no_question_baseline=no_question_retrieval_answer_baseline,
        calibration_readout=public_safe_calibration_readout,
        threshold_readout=threshold_readout,
        negative_control_readout=negative_control_readout,
    )
    status = public_shadow_support.public_shadow_status(
        structural=structural,
        metrics=metrics,
        negative_control_readout=negative_control_readout,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PUBLIC_SHADOW_KIND,
        "created_at": portrait.now_utc(),
        "status": status,
        "claim_level": "public_replayable_shadow_fixture",
        "fixture": {
            "id": metadata.get("id", "question_aware_public_shadow_v1"),
            "source_family_counts": metadata.get("source_family_counts", {}),
            "case_family_counts": metadata.get("case_family_counts", {}),
        },
        "metrics": metrics,
        "threshold_readout": threshold_readout,
        "structural_readout": {
            "status": structural["status"],
            "pack_selection": structural["pack_selection"],
            "evaluation_design": structural["evaluation_design"],
            "known_failure_modes": structural["known_failure_modes"],
        },
        "baseline_preregistration": baseline_preregistration,
        "no_question_retrieval_answer_baseline": no_question_retrieval_answer_baseline,
        "answer_quality_review": structural["answer_quality_review"],
        "materialization_review_evidence": materialization_review_evidence,
        "public_safe_calibration_readout": public_safe_calibration_readout,
        "issue_readouts": public_safe_calibration_readout["issue_readouts"],
        "negative_controls": negative_control_readout,
        "privacy": {
            "raw_source_text_emitted": False,
            "raw_answer_text_emitted": False,
            "local_path_emitted": False,
            "source_refs_emitted": False,
            "fixture_path_emitted": False,
        },
        "can_claim": [
            "public_shadow_question_aware_source_reopen_comparison_recorded",
            "public_shadow_selected_baseline_preregistered",
            "public_shadow_true_no_question_retrieval_baseline_shape_recorded",
            "public_shadow_materialization_review_evidence_recorded",
            "public_safe_question_tracking_calibration_classes_recorded",
            "issue_248_public_safe_owner_closeout",
            "public_shadow_threshold_readout_recorded",
            "public_shadow_negative_controls_recorded",
        ],
        "cannot_claim": [
            "private_real_history_answer_quality",
            "broad_no_question_aware_retrieval_baseline",
            "live_user_visible_recall_improvement",
            "theme_resonance_calibration",
            "default_prefilter_adoption",
            "source_truth_from_question_theme_rows",
            "broad_question_tracking_quality",
            "private_or_live_issue_248_closeout",
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
    parser.add_argument(
        "--answer-quality-review",
        type=Path,
        help=(
            "Optional JSONL review rows for plain_baseline vs "
            "question_aware_source_reopen answer-quality comparisons."
        ),
    )
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument(
        "--public-shadow",
        action="store_true",
        help="Run the public replayable #248 question-aware shadow fixture.",
    )
    parser.add_argument(
        "--public-shadow-fixture",
        type=Path,
        default=DEFAULT_PUBLIC_SHADOW_FIXTURE,
    )
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.public_shadow:
        payload = run_question_aware_public_shadow_benchmark(
            fixture_path=args.public_shadow_fixture,
        )
    else:
        payload = run_question_aware_real_history_benchmark(
            registry_dir=args.registry_dir,
            jobs_path=args.jobs,
            max_packs=args.max_packs,
            min_packs=args.min_packs,
            rows_per_pack=args.rows_per_pack,
            answer_quality_review_path=args.answer_quality_review,
            include_private_text=args.include_private_text,
        )
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    status = str(payload.get("status") or "")
    return 0 if status.startswith("structural_proxy_ready") or status == "public_shadow_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
