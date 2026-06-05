#!/usr/bin/env python3
"""Track S semantic robustness diagnostics for AIppocampus.

Track S is a cross-cutting diagnostic layer over existing Track A/B surfaces.
It intentionally reuses the prompt-hook decision gate and local source-retrieval
helpers instead of inventing another semantic scorer. The default path is
public-safe and does not call live LLM judges, provider APIs, or downloaded
proxy models.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import benchmark_memory_decision_gate as track_a
from aippocampus_runtime.recall.index_builder import make_sqlite
from aippocampus_runtime.recall.retrieval import search_hybrid_index, split_query_terms

SCHEMA_VERSION = 1
DEFAULT_TOP_K = 5
DEFAULT_CANDIDATE_LIMIT = 40
TRACK_S_CANNOT_CLAIM = [
    "human_level_semantic_understanding",
    "track_a_b_product_quality_replacement",
    "live_llm_judge_quality",
    "proxy_model_agreement_as_source_truth",
    "broad_real_history_semantic_robustness",
    "embedding_topology_as_understanding_proof",
]


@dataclass(frozen=True)
class GateVariant:
    variant_id: str
    perturbation: str
    expected: str
    prompt: str
    search_budget: int = 0
    use_semantic_gate: bool = False
    semantic_gate_fixture: str = "disabled"

    def to_case(self, bundle_id: str) -> track_a.GateCase:
        return track_a.GateCase(
            case_id=f"track_s::{bundle_id}::{self.variant_id}",
            case_type=f"track_s_{self.perturbation}",
            expected=self.expected,
            prompt=self.prompt,
            search_budget=self.search_budget,
            use_semantic_gate=self.use_semantic_gate,
            semantic_gate_fixture=self.semantic_gate_fixture,
        )


@dataclass(frozen=True)
class GateBundle:
    bundle_id: str
    slice_id: str
    variants: tuple[GateVariant, ...]


@dataclass(frozen=True)
class RetrievalBundle:
    bundle_id: str
    source_ref: str
    expected_line: int
    queries: tuple[tuple[str, str], ...]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def variance(values: list[float]) -> float:
    return round(statistics.pvariance(values), 4) if len(values) > 1 else 0.0


def build_gate_bundles() -> list[GateBundle]:
    return [
        GateBundle(
            bundle_id="source_reopen_equivalent_requests",
            slice_id="s1_gate_robustness",
            variants=(
                GateVariant(
                    variant_id="zh_explicit_source",
                    perturbation="cross_lingual_source_request",
                    expected="should_evidence",
                    prompt="找回之前那句关于外置海马体和 raw history 的原文证据",
                    search_budget=2,
                ),
                GateVariant(
                    variant_id="en_formal_source",
                    perturbation="formal_register_source_request",
                    expected="should_evidence",
                    prompt=(
                        "Please retrieve source-backed evidence for the old note that raw "
                        "history is local but compressed context does not know what to search."
                    ),
                    search_budget=2,
                ),
                GateVariant(
                    variant_id="mixed_language_source",
                    perturbation="mixed_language_source_request",
                    expected="should_evidence",
                    prompt=(
                        "Reopen the clean source about 外置海马体, raw history, and the "
                        "compressed-context search failure."
                    ),
                    search_budget=2,
                ),
            ),
        ),
        GateBundle(
            bundle_id="vague_continuation_paraphrases",
            slice_id="s1_gate_robustness",
            variants=(
                GateVariant(
                    variant_id="colloquial_zh",
                    perturbation="colloquial_register_shift",
                    expected="should_scent",
                    prompt="之前那个外置海马体思路我们继续推进一下",
                    use_semantic_gate=True,
                    semantic_gate_fixture="paraphrase_scent",
                ),
                GateVariant(
                    variant_id="typo_en",
                    perturbation="keyboard_near_miss",
                    expected="should_scent",
                    prompt="Continue the externl hippocampus raw-histroy thread.",
                    use_semantic_gate=True,
                    semantic_gate_fixture="paraphrase_scent",
                ),
                GateVariant(
                    variant_id="syntax_rewrite",
                    perturbation="syntax_restructuring",
                    expected="should_scent",
                    prompt="That continuity layer idea from before: can we pick it back up?",
                    use_semantic_gate=True,
                    semantic_gate_fixture="paraphrase_scent",
                ),
            ),
        ),
        GateBundle(
            bundle_id="fresh_task_should_stay_quiet",
            slice_id="s1_gate_robustness",
            variants=(
                GateVariant(
                    variant_id="fresh_python_sorting",
                    perturbation="fresh_task_no_memory",
                    expected="should_skip",
                    prompt="Explain Python sorted versus list sort for a new tutorial.",
                ),
                GateVariant(
                    variant_id="fresh_unit_test_copy",
                    perturbation="fresh_task_no_memory",
                    expected="should_skip",
                    prompt="Write a fresh unit-test naming guideline for a new repository.",
                ),
                GateVariant(
                    variant_id="fresh_release_note",
                    perturbation="current_task_distractor",
                    expected="should_skip",
                    prompt=(
                        "Current task only: draft release-note wording for a new CLI flag. "
                        "Do not pull old memory into this."
                    ),
                ),
            ),
        ),
        GateBundle(
            bundle_id="context_pollution_hard_negative",
            slice_id="s1_gate_robustness",
            variants=(
                GateVariant(
                    variant_id="negated_source_terms",
                    perturbation="current_task_distractor",
                    expected="should_skip",
                    prompt=(
                        "Do not cite or reopen the old raw history external hippocampus "
                        "source; write a fresh unrelated packaging note."
                    ),
                    search_budget=2,
                ),
                GateVariant(
                    variant_id="superseded_route_terms",
                    perturbation="negative_constraint",
                    expected="should_skip",
                    prompt=(
                        "The old AIppocampus Atlas recall gate note is superseded; do not "
                        "treat it as current source evidence."
                    ),
                    search_budget=2,
                ),
            ),
        ),
    ]


def run_gate_variant(
    bundle: GateBundle,
    variant: GateVariant,
    fixture: track_a.SyntheticFixture,
    *,
    include_private_text: bool,
) -> dict[str, Any]:
    case = variant.to_case(bundle.bundle_id)
    row = track_a.run_case(case, fixture)
    result = {
        "bundle_id": bundle.bundle_id,
        "slice_id": bundle.slice_id,
        "variant_id": variant.variant_id,
        "perturbation": variant.perturbation,
        "expected": variant.expected,
        "actual": row.get("actual"),
        "correct": row.get("correct"),
        "semantic_gate_called": bool(row.get("semantic_gate_called")),
        "evidence_count": int(row.get("evidence_count") or 0),
        "candidate_count": int(row.get("candidate_count") or 0),
        "prompt_sha1": sha1_text(variant.prompt)[:16],
    }
    if include_private_text:
        result["prompt"] = variant.prompt
        result["track_a_debug"] = row
    return result


def run_s1_gate_robustness(
    *,
    include_private_text: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="aippocampus-track-s-gate-") as tmp:
        fixture = track_a.build_synthetic_fixture(Path(tmp))
        rows = [
            run_gate_variant(bundle, variant, fixture, include_private_text=include_private_text)
            for bundle in build_gate_bundles()
            for variant in bundle.variants
        ]
    bundles: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bundles.setdefault(str(row["bundle_id"]), []).append(row)

    stable_count = 0
    route_flip_taxonomy: dict[str, int] = {}
    for bundle_rows in bundles.values():
        decisions = [str(row.get("actual") or "skip") for row in bundle_rows]
        if len(set(decisions)) <= 1:
            stable_count += 1
        baseline = decisions[0] if decisions else "skip"
        for decision in decisions[1:]:
            if decision != baseline:
                key = f"{baseline}_to_{decision}"
                route_flip_taxonomy[key] = route_flip_taxonomy.get(key, 0) + 1

    non_evidence_expected = [row for row in rows if row.get("expected") != "should_evidence"]
    should_surface = [row for row in rows if row.get("expected") in {"should_scent", "should_evidence"}]
    false_evidence = [row for row in non_evidence_expected if row.get("actual") == "evidence"]
    missed_surface = [row for row in should_surface if row.get("actual") == "skip"]
    metrics = {
        "bundle_count": len(bundles),
        "variant_count": len(rows),
        "decision_stability_rate": safe_rate(stable_count, len(bundles)),
        "false_evidence_escalation_count": len(false_evidence),
        "false_evidence_escalation_rate": safe_rate(len(false_evidence), len(non_evidence_expected)),
        "missed_scent_or_evidence_count": len(missed_surface),
        "missed_scent_or_evidence_rate": safe_rate(len(missed_surface), len(should_surface)),
        "route_flip_taxonomy": route_flip_taxonomy,
        "semantic_fixture_call_count": sum(1 for row in rows if row.get("semantic_gate_called")),
    }
    return {
        "status": "diagnostic_only",
        "claim_boundary": "gate_stability_under_public_safe_perturbations_not_live_semantic_quality",
        "metrics": metrics,
        "cases": rows,
    }, rows


def retrieval_messages() -> list[dict[str, Any]]:
    return [
        {
            "line": 10,
            "timestamp": "2026-06-05T00:00:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 1,
            "is_final": True,
            "sha1": "track-s-route-readiness",
            "text": (
                "The route-readiness packet is a navigation-only source reopen plan. "
                "It exposes route handles, keeps stale candidates silent, and is also "
                "called 路由就绪包."
            ),
        },
        {
            "line": 20,
            "timestamp": "2026-06-05T00:02:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 2,
            "is_final": True,
            "sha1": "track-s-active-path-packet",
            "text": (
                "Active Path Packet separates scent, reopen, evidence, and ignore routes. "
                "主动路径包 marks stale paths as unsafe current-fact boundaries."
            ),
        },
        {
            "line": 30,
            "timestamp": "2026-06-05T00:04:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 3,
            "is_final": True,
            "sha1": "track-s-observatory",
            "text": (
                "The cognitive observatory report is read-only diagnostics, not a control "
                "plane, and not source authority."
            ),
        },
        {
            "line": 40,
            "timestamp": "2026-06-05T00:06:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 4,
            "is_final": True,
            "sha1": "track-s-distractor",
            "text": (
                "A release checklist can mention packaging notes and CLI flags without "
                "becoming memory evidence."
            ),
        },
    ]


def build_retrieval_bundles() -> list[RetrievalBundle]:
    return [
        RetrievalBundle(
            bundle_id="route_readiness_navigation_only",
            source_ref="track-s-route-readiness",
            expected_line=10,
            queries=(
                ("canonical", "route-readiness packet navigation-only source reopen"),
                ("lexically_distant", "prepared route handles for stale candidates"),
                ("mixed_language", "路由就绪包 source reopen plan"),
            ),
        ),
        RetrievalBundle(
            bundle_id="active_path_route_separation",
            source_ref="track-s-active-path-packet",
            expected_line=20,
            queries=(
                ("canonical", "Active Path Packet scent reopen evidence ignore"),
                ("syntax_rewrite", "separate reopen route from evidence route"),
                ("mixed_language", "主动路径包 unsafe current fact boundary"),
            ),
        ),
    ]


def target_rank(hits: list[dict[str, Any]], expected_line: int) -> int | None:
    for idx, hit in enumerate(hits, start=1):
        try:
            if int(hit.get("line") or -1) == expected_line:
                return idx
        except (TypeError, ValueError):
            continue
    return None


def target_score(hits: list[dict[str, Any]], expected_line: int) -> float:
    for hit in hits:
        try:
            if int(hit.get("line") or -1) == expected_line:
                return float(hit.get("score") or 0.0)
        except (TypeError, ValueError):
            continue
    return 0.0


def run_s2_retrieval_invariance(
    *,
    top_k: int,
    candidate_limit: int,
    include_private_text: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="aippocampus-track-s-retrieval-") as tmp:
        index_path = Path(tmp) / "source_index.sqlite"
        make_sqlite(index_path, retrieval_messages(), anchors=[], turns=[])
        rows: list[dict[str, Any]] = []
        for bundle in build_retrieval_bundles():
            for variant_id, query in bundle.queries:
                terms = split_query_terms([query])
                hits = search_hybrid_index(
                    index_path,
                    terms,
                    terms,
                    [],
                    limit=max(top_k, candidate_limit),
                    candidate_limit=candidate_limit,
                    snippet_chars=160 if include_private_text else 1,
                    context_radius=0,
                    use_rag_chunks=True,
                )
                rank = target_rank(hits, bundle.expected_line)
                row: dict[str, Any] = {
                    "bundle_id": bundle.bundle_id,
                    "variant_id": variant_id,
                    "query_sha1": sha1_text(query)[:16],
                    "target_source_ref_sha1": sha1_text(bundle.source_ref)[:16],
                    "target_rank": rank,
                    "target_score": round(target_score(hits, bundle.expected_line), 4),
                    "hit_top_k": bool(rank and rank <= top_k),
                    "top_lines": [int(hit["line"]) for hit in hits[:top_k] if hit.get("line") is not None],
                }
                if include_private_text:
                    row["query"] = query
                    row["top_snippets"] = [
                        str(hit.get("snippet") or "") for hit in hits[: min(top_k, 3)]
                    ]
                rows.append(row)

    by_bundle: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_bundle.setdefault(str(row["bundle_id"]), []).append(row)

    rank_variances: list[float] = []
    score_variances: list[float] = []
    rank_drop_count = 0
    compared_variants = 0
    missing_rank = top_k + 1
    for bundle_rows in by_bundle.values():
        ranks = [
            float(row.get("target_rank") or missing_rank)
            for row in bundle_rows
        ]
        scores = [float(row.get("target_score") or 0.0) for row in bundle_rows]
        rank_variances.append(variance(ranks))
        score_variances.append(variance(scores))
        baseline_rank = int(bundle_rows[0].get("target_rank") or missing_rank)
        for row in bundle_rows[1:]:
            compared_variants += 1
            rank = int(row.get("target_rank") or missing_rank)
            if rank > baseline_rank:
                rank_drop_count += 1

    top_k_hits = sum(1 for row in rows if row.get("hit_top_k"))
    metrics = {
        "bundle_count": len(by_bundle),
        "query_variant_count": len(rows),
        "top_k": int(top_k),
        "candidate_limit": int(candidate_limit),
        "top_k_survival_count": top_k_hits,
        "top_k_survival_rate": safe_rate(top_k_hits, len(rows)),
        "target_source_rank_variance_avg": round(
            sum(rank_variances) / len(rank_variances),
            4,
        )
        if rank_variances
        else 0.0,
        "score_variance_avg": round(sum(score_variances) / len(score_variances), 4)
        if score_variances
        else 0.0,
        "rank_drop_count": rank_drop_count,
        "rank_drop_rate": safe_rate(rank_drop_count, compared_variants),
    }
    return {
        "status": "diagnostic_only",
        "claim_boundary": "retrieval_invariance_over_public_safe_equivalent_queries_not_answer_quality",
        "metrics": metrics,
        "cases": rows,
    }, rows


def hard_negative_cases() -> list[GateVariant]:
    return [
        GateVariant(
            variant_id="explicit_negation_old_source",
            perturbation="explicit_negative_constraint",
            expected="should_skip",
            prompt=(
                "Do not cite or reopen the old raw history external hippocampus source; "
                "write a fresh unrelated packaging note."
            ),
            search_budget=2,
        ),
        GateVariant(
            variant_id="superseded_currentness",
            perturbation="superseded_currentness",
            expected="should_skip",
            prompt=(
                "The old AIppocampus Atlas recall gate note is superseded; do not treat "
                "it as current source evidence."
            ),
            search_budget=2,
        ),
        GateVariant(
            variant_id="related_but_forbidden_algorithm",
            perturbation="hard_negative_high_overlap",
            expected="should_skip",
            prompt=(
                "Use the iterative quicksort approach; do not reuse yesterday's recursive "
                "version that leaked memory."
            ),
        ),
    ]


def run_s3_hard_negative_suppression(
    *,
    include_private_text: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bundle = GateBundle(
        bundle_id="hard_negative_suppression",
        slice_id="s3_hard_negative_suppression",
        variants=tuple(hard_negative_cases()),
    )
    with tempfile.TemporaryDirectory(prefix="aippocampus-track-s-hard-negative-") as tmp:
        fixture = track_a.build_synthetic_fixture(Path(tmp))
        rows = [
            run_gate_variant(bundle, variant, fixture, include_private_text=include_private_text)
            for variant in bundle.variants
        ]
    suppressed = [row for row in rows if row.get("actual") == "skip"]
    evidence_over = [row for row in rows if row.get("actual") == "evidence"]
    lingering_scent = [row for row in rows if row.get("actual") == "scent"]
    stale_rows = [row for row in rows if row.get("variant_id") == "superseded_currentness"]
    stale_as_current = [row for row in stale_rows if row.get("actual") == "evidence"]
    negation_violations = [row for row in rows if row.get("actual") != "skip"]
    metrics = {
        "case_count": len(rows),
        "hard_negative_suppressed_count": len(suppressed),
        "hard_negative_suppression_rate": safe_rate(len(suppressed), len(rows)),
        "stale_as_current_count": len(stale_as_current),
        "stale_as_current_rate": safe_rate(len(stale_as_current), len(stale_rows)),
        "explicit_negation_violation_count": len(negation_violations),
        "explicit_negation_violation_rate": safe_rate(len(negation_violations), len(rows)),
        "source_evidence_over_escalation_count": len(evidence_over),
        "source_evidence_over_escalation_rate": safe_rate(len(evidence_over), len(rows)),
        "surface_lingering_scent_count": len(lingering_scent),
    }
    return {
        "status": "diagnostic_only",
        "claim_boundary": "hard_negative_and_negation_suppression_diagnostic_not_truth_proof",
        "metrics": metrics,
        "cases": rows,
    }, rows


def s4_offline_proxy_alignment(*, include_proxy_alignment: bool) -> dict[str, Any]:
    if not include_proxy_alignment:
        return {
            "status": "disabled_by_default",
            "claim_boundary": "proxy_not_truth",
            "metrics": {
                "alignment_case_count": 0,
                "proxy_model_available": False,
                "live_llm_required": False,
            },
            "next_step": "Enable only after local model availability and license review.",
        }
    return {
        "status": "skipped_missing_local_model",
        "claim_boundary": "proxy_not_truth",
        "metrics": {
            "alignment_case_count": 0,
            "proxy_model_available": False,
            "live_llm_required": False,
        },
        "skip_reason": "offline_cross_encoder_not_configured",
    }


def s5_representation_space_health() -> dict[str, Any]:
    return {
        "status": "skipped_no_embedding_index",
        "claim_boundary": "health_check_not_quality_claim",
        "metrics": {
            "embedding_index_available": False,
            "cosine_distribution_reported": False,
            "anisotropy_reported": False,
            "neighborhood_purity_reported": False,
            "live_llm_required": False,
        },
        "next_step": "Report vector-space health only when a local embedding index is explicitly supplied.",
    }


def run_semantic_robustness_benchmark(
    *,
    include_private_text: bool = False,
    include_proxy_alignment: bool = False,
    top_k: int = DEFAULT_TOP_K,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    started = time.perf_counter()
    s1, s1_rows = run_s1_gate_robustness(include_private_text=include_private_text)
    s2, s2_rows = run_s2_retrieval_invariance(
        top_k=top_k,
        candidate_limit=candidate_limit,
        include_private_text=include_private_text,
    )
    s3, s3_rows = run_s3_hard_negative_suppression(include_private_text=include_private_text)
    quality_gate_ok = (
        float(s2["metrics"].get("top_k_survival_rate") or 0.0) >= 0.8
        and int(s1["metrics"].get("false_evidence_escalation_count") or 0) == 0
        and int(s3["metrics"].get("source_evidence_over_escalation_count") or 0) == 0
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_semantic_robustness_benchmark",
        "track": "Track S",
        "generated_at": now_utc(),
        "status": "diagnostic_only",
        "ok": True,
        "quality_gate_ok": quality_gate_ok,
        "config": {
            "uses_live_llm_judge": False,
            "requires_provider_keys": False,
            "include_private_text": bool(include_private_text),
            "include_proxy_alignment": bool(include_proxy_alignment),
            "top_k": int(top_k),
            "candidate_limit": int(candidate_limit),
        },
        "tracks": {
            "s1_gate_robustness": s1,
            "s2_retrieval_invariance": s2,
            "s3_hard_negative_suppression": s3,
            "s4_offline_proxy_alignment": s4_offline_proxy_alignment(
                include_proxy_alignment=include_proxy_alignment,
            ),
            "s5_representation_space_health": s5_representation_space_health(),
        },
        "privacy_boundary": {
            "raw_prompt_or_query_text_emitted": bool(include_private_text),
            "snippets_emitted": bool(include_private_text),
            "source_reference_details_emitted": bool(include_private_text),
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": False,
            "output_shape": "sanitized_track_s_semantic_robustness_diagnostics",
        },
        "claim_boundary": (
            "Track S is source-backed no-live-judge robustness evidence over Track A/B "
            "surfaces. It is not a human-level semantic-understanding proof and does "
            "not replace product-behavior benchmarks."
        ),
        "cannot_claim": TRACK_S_CANNOT_CLAIM,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if include_private_text:
        payload["private_debug"] = {
            "s1_gate_cases": s1_rows,
            "s2_retrieval_cases": s2_rows,
            "s3_hard_negative_cases": s3_rows,
        }
    return payload


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus Track S semantic robustness diagnostics")
    print(f"- status: {payload['status']} quality_gate_ok: {payload['quality_gate_ok']}")
    s1 = payload["tracks"]["s1_gate_robustness"]["metrics"]
    s2 = payload["tracks"]["s2_retrieval_invariance"]["metrics"]
    s3 = payload["tracks"]["s3_hard_negative_suppression"]["metrics"]
    print(
        "- S1 gate stability: "
        f"{s1['decision_stability_rate']:.2%}; "
        f"false-evidence {s1['false_evidence_escalation_count']}"
    )
    print(
        "- S2 retrieval invariance: "
        f"top-k survival {s2['top_k_survival_rate']:.2%}; "
        f"avg rank variance {s2['target_source_rank_variance_avg']}"
    )
    print(
        "- S3 hard negatives: "
        f"suppression {s3['hard_negative_suppression_rate']:.2%}; "
        f"negation violations {s3['explicit_negation_violation_count']}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--include-proxy-alignment", action="store_true")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_semantic_robustness_benchmark(
        include_private_text=args.include_private_text,
        include_proxy_alignment=args.include_proxy_alignment,
        top_k=args.top_k,
        candidate_limit=args.candidate_limit,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
