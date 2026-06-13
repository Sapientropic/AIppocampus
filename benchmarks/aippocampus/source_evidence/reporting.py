"""Shared reporting helpers for Track B source-evidence benchmark surfaces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from benchmark_memory_decision_gate import sha1_text as legacy_sha1_text
from benchmarks.aippocampus.shared.benchmark_statistics import binomial_rate_report
from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref

from .defaults import QUERY_ORIGIN_TAXONOMY, TRACK_B_QUERY_ORIGIN_ISSUES


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def reciprocal_rank(rank: Any) -> float:
    try:
        value = int(rank)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 / value if value > 0 else 0.0


def sha1_text(value: str) -> str:
    # Historical benchmark report ids keep the `sha1` field names for artifact
    # schema compatibility. Reuse the mature benchmark helper so this split does
    # not introduce a second fingerprinting policy.
    return legacy_sha1_text(value)


def query_origin(category: str, *, query_author: str, notes: str) -> dict[str, Any]:
    spec = QUERY_ORIGIN_TAXONOMY[category]
    return {
        "category": category,
        "bucket": spec["bucket"],
        "independent_of_target_source": bool(spec["independent_of_target_source"]),
        "query_author": query_author,
        "boundary": spec["boundary"],
        "notes": notes,
    }


def claim_boundary(
    *,
    measures: str,
    can_claim: list[str],
    cannot_claim: list[str],
) -> dict[str, Any]:
    return {
        "measures": measures,
        "can_claim": can_claim,
        "cannot_claim": cannot_claim,
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "issue_refs": TRACK_B_QUERY_ORIGIN_ISSUES,
    }


def track_rate_entries(track_name: str, track: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def maybe_add(metric: str, value: Any) -> None:
        if "hit_rate" not in metric:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        key = (track_name, metric)
        if key in seen:
            return
        seen.add(key)
        entries.append(
            {
                "track": track_name,
                "metric": metric,
                "value": round(float(value), 4),
            }
        )

    for key, value in sorted(track.items()):
        maybe_add(str(key), value)
    metrics = track.get("metrics") if isinstance(track.get("metrics"), dict) else {}
    for key, value in sorted(metrics.items()):
        maybe_add(str(key), value)
    return entries


def query_origin_summary(tracks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {
        "source_derived": {
            "tracks": [],
            "track_count": 0,
            "hit_rates": [],
            "claim_boundary": "Index-health and source-derived sanity checks; do not read as natural user-query recall.",
        },
        "non_source_derived": {
            "tracks": [],
            "track_count": 0,
            "hit_rates": [],
            "claim_boundary": "Independent user-like or fixture-authored query arms; report beside source-derived checks.",
        },
    }
    for track_name, track in tracks.items():
        if not isinstance(track, dict):
            continue
        origin = track.get("query_origin") if isinstance(track.get("query_origin"), dict) else {}
        bucket_name = str(origin.get("bucket") or "source_derived")
        bucket = buckets.setdefault(
            bucket_name,
            {
                "tracks": [],
                "track_count": 0,
                "hit_rates": [],
                "claim_boundary": "Unclassified query-origin bucket.",
            },
        )
        bucket["tracks"].append(track_name)
        bucket["hit_rates"].extend(track_rate_entries(track_name, track))
    for bucket in buckets.values():
        bucket["track_count"] = len(bucket["tracks"])
    return {
        "taxonomy": QUERY_ORIGIN_TAXONOMY,
        "source_derived": buckets["source_derived"],
        "non_source_derived": buckets["non_source_derived"],
        "reporting_rule": (
            "Report source-derived and non-source-derived hit rates side by side; "
            "do not average source-derived sanity checks into user-query recall claims."
        ),
        "issue_refs": TRACK_B_QUERY_ORIGIN_ISSUES,
    }


def source_evidence_validation_guidance(
    payload: dict[str, Any],
    *,
    require_semantic_sidecar: bool,
) -> dict[str, Any] | None:
    if not require_semantic_sidecar:
        return None
    if payload.get("status") != "insufficient_selected_cases":
        return None
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    if selection.get("mode") not in {None, "semantic_sidecar_required"}:
        return None

    explanation = (
        payload.get("selection_explanation")
        if isinstance(payload.get("selection_explanation"), dict)
        else {}
    )
    selected_count = int(
        explanation.get("selected_case_count")
        if explanation.get("selected_case_count") is not None
        else payload.get("case_count") or 0
    )
    problem = (
        "semantic_sidecar_selected_cases_absent"
        if selected_count == 0
        else "semantic_sidecar_selected_cases_below_minimum"
    )
    portable_command = (
        "python benchmarks/aippocampus/benchmark_source_evidence_retrieval.py "
        "--fts5-cases 1 --fts5-min-cases 1 "
        "--source-max-cases 1 --source-min-cases 1 "
        "--allow-deterministic-labels --json"
    )
    parent_claims = sorted({str(item) for item in payload.get("cannot_claim") or []})
    return {
        "problem": problem,
        "semantic_sidecar_required": True,
        "selected_case_count": selected_count,
        "min_cases": int(explanation.get("min_cases") or payload.get("min_cases") or 0),
        "semantic_sidecar_quality_check": (
            "Requires eligible prebuilt or refreshed semantic-scope sidecar rows."
        ),
        "portable_smoke_mode": "deterministic_label_fallback",
        "portable_smoke_command": portable_command,
        "portable_smoke_claim_boundary": (
            "Wiring baseline only; do not read fallback success as semantic-sidecar coverage."
        ),
        "sidecar_next_action": explanation.get("next_action"),
        "cannot_claim": ["deterministic_label_fallback_is_not_semantic_sidecar_evidence"],
        "inherited_boundaries": {
            "source": "parent report",
            "count": len(parent_claims),
        },
        "boundary_ref": (
            "docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md"
            "#track-b-source-evidence-retrieval"
        ),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md"
            "#track-b-source-evidence-retrieval"
        ),
    }


def rank_metrics(cases: list[dict[str, Any]], key: str, thresholds: list[int]) -> dict[str, Any]:
    total = len(cases)
    metrics: dict[str, Any] = {"total_cases": total}
    rate_estimates: dict[str, Any] = {}
    for threshold in sorted(set(thresholds)):
        hits = sum(
            1
            for case in cases
            if 0 < int((case.get(key) or {}).get("rank") or 0) <= threshold
        )
        metrics[f"hit_top{threshold}"] = hits
        metrics[f"miss_top{threshold}"] = total - hits
        metrics[f"hit_rate_top{threshold}"] = safe_rate(hits, total)
        rate_estimates[f"hit_rate_top{threshold}"] = binomial_rate_report(
            f"hit_rate_top{threshold}",
            numerator=hits,
            denominator=total,
        )
    metrics["mrr"] = round(
        sum(reciprocal_rank((case.get(key) or {}).get("rank")) for case in cases) / total,
        4,
    ) if total else 0.0
    metrics["rate_estimates"] = rate_estimates
    return metrics


def summarize_sharegpt_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": payload.get("kind") or "sharegpt_public_source_evidence_retrieval",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "config": payload.get("config") or {},
        "corpus": payload.get("corpus") or {},
        "sampling": payload.get("sampling") or {},
        "metrics": payload.get("metrics") or {},
        "skip_reason": payload.get("skip_reason"),
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": payload.get("cannot_claim") or [],
        "query_origin": query_origin(
            "source_derived_sparse",
            query_author="ShareGPT public Track B fixture builder",
            notes=(
                "Prompt text is templated from public conversation source terms; "
                "it is public and source-backed, but still source-derived."
            ),
        ),
        "claim_boundary": claim_boundary(
            measures="public_source_derived_source_navigation",
            can_claim=["public_sharegpt_source_navigation_on_source_derived_prompts"],
            cannot_claim=[
                "private_real_history_source_evidence_quality",
                "natural_user_query_recall",
            ],
        ),
    }


def summarize_standard_retrieval_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": payload.get("kind") or "standard_public_retrieval_qa_source_evidence",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "config": payload.get("config") or {},
        "corpus": payload.get("corpus") or {},
        "metrics": payload.get("metrics") or {},
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": payload.get("cannot_claim") or [],
        "query_origin": query_origin(
            "human_or_fixture_question",
            query_author="public benchmark dataset question",
            notes=(
                "LoCoMo and LongMemEval-style question text is not extracted from "
                "the target source line, so this is the first non-source-derived Track B arm."
            ),
        ),
        "claim_boundary": claim_boundary(
            measures="user_like_source_navigation",
            can_claim=["public_retrieval_qa_source_navigation"],
            cannot_claim=[
                "answer_generation_quality",
                "private_real_history_user_query_recall",
                "cross_dataset_model_comparison_without_matching_protocol",
            ],
        ),
    }
