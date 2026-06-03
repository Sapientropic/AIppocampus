#!/usr/bin/env python3
"""NIAH-style multimodal evidence-pool contract for #533.

This runner intentionally removes retrieval from the measurement. Each row gets
a fixed pool that already contains all ground-truth evidence plus distractors,
so the scored surface is source selection, source reopen/citation, reasoning
under conflict, and abstention. A deliberate stale-source failure proves this
slice can catch answer-synthesis mistakes even when the right evidence is in
the pool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

from benchmark_statistics import binomial_rate_report, rounded_rate

SCHEMA_VERSION = 1
FIXTURE_SCHEMA_VERSION = "aippocampus.multimodal_niah_evidence_pool_fixture.v1"
SOURCE_FIXTURE_SCHEMA_VERSION = "aippocampus.multimodal_corpus_fixture.v1"
DEFAULT_FIXTURE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "multimodal_niah_evidence_pool" / "fixture.json"
)
SOURCE_REOPEN_MODES = {"disabled", "deterministic_fixture"}
REQUIRED_CASE_FIELDS = {
    "case_id",
    "corpus_case_id",
    "query_shape",
    "pool_size",
    "ground_truth_evidence_ids",
    "distractor_evidence_ids",
    "pool_evidence_ids",
    "selected_evidence_ids",
    "cited_source_anchor_ids",
    "expected_answer_state",
    "selected_answer_state",
    "answer_correct",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {fixture_path}")
    return payload


def load_source_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = _as_mapping(fixture.get("source_fixture"))
    source_path = _paths.REPO_ROOT / str(source_ref.get("path") or "")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object source fixture: {source_path}")
    return payload


def _source_index(source_fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(source.get("source_id")): source
        for source in source_fixture.get("sources") or []
        if isinstance(source, Mapping) and source.get("source_id")
    }


def _qa_index(source_fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(case.get("case_id")): case
        for case in source_fixture.get("qa_cases") or []
        if isinstance(case, Mapping) and case.get("case_id")
    }


def _blocker(code: str, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def _deterministic_pool_order(case: Mapping[str, Any], *, seed: str) -> list[str]:
    candidates = _as_list(case.get("ground_truth_evidence_ids")) + _as_list(
        case.get("distractor_evidence_ids")
    )
    deduped = list(dict.fromkeys(candidates))
    rng_seed = int(sha1_text(f"{seed}:{case.get('case_id')}")[:16], 16)
    rng = random.Random(rng_seed)
    rng.shuffle(deduped)
    return deduped


def _anchor_ids(source_ids: Sequence[str], sources: Mapping[str, Mapping[str, Any]]) -> list[str]:
    anchor_ids: list[str] = []
    for source_id in source_ids:
        source = sources.get(source_id)
        anchor = _as_mapping(source.get("source_anchor") if source else None)
        if anchor.get("anchor_id"):
            anchor_ids.append(str(anchor["anchor_id"]))
    return anchor_ids


def _has_reopenable_sources(
    source_ids: Sequence[str],
    sources: Mapping[str, Mapping[str, Any]],
) -> bool:
    for source_id in source_ids:
        source = sources.get(source_id)
        anchor = _as_mapping(source.get("source_anchor") if source else None)
        if not source or not anchor.get("anchor_id") or not source.get("content_hash_sha256"):
            return False
    return True


def _modality_mix(source_ids: Sequence[str], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                str(sources[source_id].get("modality"))
                for source_id in source_ids
                if source_id in sources and sources[source_id].get("modality")
            ).items()
        )
    )


def build_pools(
    fixture: Mapping[str, Any],
    source_fixture: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    sources = _source_index(source_fixture)
    seed = str(fixture.get("pool_shuffle_seed") or "")
    pools: dict[str, dict[str, Any]] = {}
    for case in fixture.get("cases") or []:
        if not isinstance(case, Mapping):
            continue
        pool_evidence_ids = _deterministic_pool_order(case, seed=seed)
        pools[str(case.get("case_id"))] = {
            "case_id": case.get("case_id"),
            "pool_size": len(pool_evidence_ids),
            "ground_truth_evidence_ids": _as_list(case.get("ground_truth_evidence_ids")),
            "distractor_evidence_ids": _as_list(case.get("distractor_evidence_ids")),
            "pool_evidence_ids": pool_evidence_ids,
            "modality_mix": _modality_mix(pool_evidence_ids, sources),
        }
    return pools


def validate_fixture(
    fixture: Mapping[str, Any],
    source_fixture: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if fixture.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        blockers.append(
            _blocker(
                "unsupported_fixture_schema_version",
                "schema_version",
                "Unsupported multimodal NIAH fixture schema version.",
            )
        )
    if source_fixture.get("schema_version") != SOURCE_FIXTURE_SCHEMA_VERSION:
        blockers.append(
            _blocker(
                "unsupported_source_fixture_schema_version",
                "source_fixture.schema_version",
                "NIAH evidence pools currently build from the public multimodal corpus fixture.",
            )
        )
    if not _as_mapping(fixture.get("boundary")).get("retrieval_not_scored"):
        blockers.append(
            _blocker(
                "retrieval_boundary_not_declared",
                "boundary.retrieval_not_scored",
                "NIAH evidence-pool fixtures must declare that retrieval is not scored.",
            )
        )

    sources = _source_index(source_fixture)
    source_ids = set(sources)
    qa_by_id = _qa_index(source_fixture)
    built_pools = build_pools(fixture, source_fixture)
    seen_case_ids: set[str] = set()
    report_cases: list[dict[str, Any]] = []
    for case in fixture.get("cases") or []:
        if not isinstance(case, Mapping):
            continue
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in seen_case_ids:
            blockers.append(
                _blocker(
                    "case_missing_or_duplicate_id",
                    "cases.case_id",
                    "NIAH case ids must be present and unique.",
                )
            )
        seen_case_ids.add(case_id)

        missing = sorted(field for field in REQUIRED_CASE_FIELDS if field not in case)
        if missing:
            blockers.append(
                _blocker(
                    "case_missing_required_field",
                    f"cases.{case_id or '<missing>'}",
                    f"Missing case fields: {', '.join(missing)}.",
                )
            )
        corpus_case = qa_by_id.get(str(case.get("corpus_case_id") or ""))
        if not corpus_case:
            blockers.append(
                _blocker(
                    "case_unknown_corpus_case",
                    f"cases.{case_id}.corpus_case_id",
                    "Each NIAH row must point back to a corpus-style QA row.",
                )
            )

        ground_truth_ids = _as_list(case.get("ground_truth_evidence_ids"))
        distractor_ids = _as_list(case.get("distractor_evidence_ids"))
        pool_ids = _as_list(case.get("pool_evidence_ids"))
        selected_ids = _as_list(case.get("selected_evidence_ids"))
        all_case_source_ids = ground_truth_ids + distractor_ids + pool_ids + selected_ids
        for source_id in all_case_source_ids:
            if source_id not in source_ids:
                blockers.append(
                    _blocker(
                        "case_unknown_source_id",
                        f"cases.{case_id}.source_ids",
                        "NIAH evidence ids must point at known source fixture ids.",
                    )
                )
        if corpus_case and set(ground_truth_ids) != set(_as_list(corpus_case.get("evidence_ids"))):
            blockers.append(
                _blocker(
                    "case_ground_truth_mismatch_source_fixture",
                    f"cases.{case_id}.ground_truth_evidence_ids",
                    "Ground-truth ids must match the referenced corpus QA row.",
                )
            )
        if len(pool_ids) != len(set(pool_ids)):
            blockers.append(
                _blocker(
                    "pool_duplicate_source_id",
                    f"cases.{case_id}.pool_evidence_ids",
                    "Fixed evidence pools must not duplicate source ids.",
                )
            )
        if len(pool_ids) != int(case.get("pool_size") or 0):
            blockers.append(
                _blocker(
                    "pool_size_mismatch",
                    f"cases.{case_id}.pool_size",
                    "pool_size must match the fixed pool evidence id count.",
                )
            )
        if not set(ground_truth_ids) <= set(pool_ids):
            blockers.append(
                _blocker(
                    "pool_missing_ground_truth_evidence",
                    f"cases.{case_id}.pool_evidence_ids",
                    "Fixed NIAH pools must include all ground-truth evidence ids.",
                )
            )
        if not set(selected_ids) <= set(pool_ids):
            blockers.append(
                _blocker(
                    "selection_outside_supplied_pool",
                    f"cases.{case_id}.selected_evidence_ids",
                    "A scored answerer may only select evidence from the supplied pool.",
                )
            )
        expected_pool = built_pools.get(case_id, {}).get("pool_evidence_ids", [])
        if pool_ids != expected_pool:
            blockers.append(
                _blocker(
                    "pool_order_not_deterministic",
                    f"cases.{case_id}.pool_evidence_ids",
                    "Fixed pool order must match the deterministic shuffle seed.",
                )
            )
        if not distractor_ids:
            blockers.append(
                _blocker(
                    "pool_missing_distractors",
                    f"cases.{case_id}.distractor_evidence_ids",
                    "NIAH pools must include distractors, not only ground truth.",
                )
            )

        report_cases.append(
            {
                "case_id": case_id,
                "corpus_case_id": case.get("corpus_case_id"),
                "pool_size": len(pool_ids),
                "ground_truth_evidence_ids": ground_truth_ids,
                "distractor_evidence_ids": distractor_ids,
                "pool_evidence_ids": pool_ids,
                "selected_evidence_ids": selected_ids,
                "expected_failure": bool(case.get("expected_failure")),
            }
        )

    return {
        "schema_version": fixture.get("schema_version"),
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "fixture_id": fixture.get("fixture_id"),
        "source_fixture_id": _as_mapping(fixture.get("source_fixture")).get("fixture_id"),
        "case_count": len(report_cases),
        "pool_sizes": sorted({case["pool_size"] for case in report_cases}),
        "expected_failure_case_count": sum(1 for case in report_cases if case["expected_failure"]),
        "cases": report_cases,
    }


def _evaluate_case(
    case: Mapping[str, Any],
    *,
    corpus_case: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ground_truth_ids = _as_list(case.get("ground_truth_evidence_ids"))
    pool_ids = _as_list(case.get("pool_evidence_ids"))
    selected_ids = _as_list(case.get("selected_evidence_ids"))
    stale_or_conflicting = set(_as_list(case.get("stale_or_conflicting_distractor_ids")))
    cited_anchor_ids = _as_list(case.get("cited_source_anchor_ids"))
    expected_abstain = bool(case.get("expected_abstain")) or str(
        case.get("expected_answer_state") or ""
    ).startswith("abstain")
    selected_abstained = str(case.get("selected_answer_state") or "").startswith("abstain")
    ground_truth_present = set(ground_truth_ids) <= set(pool_ids)
    source_selection_correct = set(selected_ids) == set(ground_truth_ids)
    source_anchor_citation_correct = source_selection_correct and set(
        _anchor_ids(ground_truth_ids, sources)
    ) <= set(cited_anchor_ids)
    stale_or_conflicting_selected = bool(set(selected_ids) & stale_or_conflicting)
    unsupported_claim = expected_abstain and not selected_abstained
    answer_correct = bool(case.get("answer_correct"))

    return {
        "case_id": case.get("case_id"),
        "corpus_case_id": case.get("corpus_case_id"),
        "query_shape": case.get("query_shape"),
        "question_sha1": sha1_text(str(corpus_case.get("question") or ""))[:16],
        "answer_sha1": sha1_text(str(corpus_case.get("answer") or ""))[:16],
        "expected_answer_state_sha1": sha1_text(str(case.get("expected_answer_state") or ""))[:16],
        "selected_answer_state_sha1": sha1_text(str(case.get("selected_answer_state") or ""))[:16],
        "pool_size": len(pool_ids),
        "pool_evidence_ids": pool_ids,
        "pool_modality_mix": _modality_mix(pool_ids, sources),
        "ground_truth_evidence_ids": ground_truth_ids,
        "selected_evidence_ids": selected_ids,
        "cited_source_anchor_ids": cited_anchor_ids,
        "ground_truth_present": ground_truth_present,
        "ground_truth_reopenable": _has_reopenable_sources(ground_truth_ids, sources),
        "selected_sources_reopenable": _has_reopenable_sources(selected_ids, sources),
        "answer_correct": answer_correct,
        "source_selection_correct": source_selection_correct,
        "source_anchor_citation_correct": source_anchor_citation_correct,
        "expected_abstain": expected_abstain,
        "abstention_correct": expected_abstain and selected_abstained,
        "unsupported_claim": unsupported_claim,
        "stale_or_conflicting_distractor_selected": stale_or_conflicting_selected,
        "expected_failure": bool(case.get("expected_failure")),
        "failure_mode": case.get("failure_mode") if case.get("expected_failure") else None,
    }


def _rate(name: str, numerator: int, denominator: int) -> dict[str, Any]:
    return binomial_rate_report(name, numerator=numerator, denominator=denominator)


def _metrics(cases: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    unsupported = [case for case in cases if case.get("expected_abstain")]
    conflict = [case for case in cases if case.get("query_shape") == "conflict_resolution"]
    metric_counts = {
        "pool_ground_truth_coverage_rate": (
            sum(1 for case in cases if case.get("ground_truth_present")),
            len(cases),
        ),
        "answer_correctness": (
            sum(1 for case in cases if case.get("answer_correct")),
            len(cases),
        ),
        "source_selection_accuracy": (
            sum(1 for case in cases if case.get("source_selection_correct")),
            len(cases),
        ),
        "source_anchor_citation_accuracy": (
            sum(1 for case in cases if case.get("source_anchor_citation_correct")),
            len(cases),
        ),
        "unsupported_claim_rate": (
            sum(1 for case in unsupported if case.get("unsupported_claim")),
            len(unsupported),
        ),
        "abstention_accuracy": (
            sum(1 for case in unsupported if case.get("abstention_correct")),
            len(unsupported),
        ),
        "stale_or_conflicting_distractor_selection_rate": (
            sum(1 for case in conflict if case.get("stale_or_conflicting_distractor_selected")),
            len(conflict),
        ),
    }
    metrics = {
        name: rounded_rate(numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }
    return metrics, {
        name: _rate(name, numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }


def _source_reopen_track(
    cases: Sequence[Mapping[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    if mode == "disabled":
        return {
            "status": "skipped_provider_not_configured",
            "provider_route": None,
            "metrics": {},
            "claim_boundary": {
                "measures": "source_reopen_path_when_raw_media_or_document_provider_is_available",
                "cannot_claim": ["live_vision_model_quality", "raw_media_model_answer_quality"],
            },
        }
    ground_truth_hits = sum(1 for case in cases if case.get("ground_truth_reopenable"))
    selected_hits = sum(1 for case in cases if case.get("selected_sources_reopenable"))
    return {
        "status": "scored",
        "provider_route": "deterministic_fixture",
        "metrics": {
            "ground_truth_source_reopen_rate": rounded_rate(ground_truth_hits, len(cases)),
            "selected_source_reopen_rate": rounded_rate(selected_hits, len(cases)),
        },
        "rate_estimates": {
            "ground_truth_source_reopen_rate": _rate(
                "ground_truth_source_reopen_rate",
                ground_truth_hits,
                len(cases),
            ),
            "selected_source_reopen_rate": _rate(
                "selected_source_reopen_rate",
                selected_hits,
                len(cases),
            ),
        },
        "claim_boundary": {
            "measures": "deterministic_source_anchor_reopen_contract_only",
            "cannot_claim": ["live_vision_model_quality", "raw_media_model_answer_quality"],
        },
    }


def run_benchmark(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    source_reopen_mode: str = "disabled",
) -> dict[str, Any]:
    if source_reopen_mode not in SOURCE_REOPEN_MODES:
        raise ValueError(f"source_reopen_mode must be one of {sorted(SOURCE_REOPEN_MODES)}")
    started = time.perf_counter()
    fixture = load_fixture(fixture_path)
    source_fixture = load_source_fixture(fixture)
    sources = _source_index(source_fixture)
    qa_by_id = _qa_index(source_fixture)
    validation = validate_fixture(fixture, source_fixture)
    cases = [
        _evaluate_case(
            case,
            corpus_case=qa_by_id.get(str(case.get("corpus_case_id") or ""), {}),
            sources=sources,
        )
        for case in fixture.get("cases") or []
        if isinstance(case, Mapping)
    ]
    metrics, rate_estimates = _metrics(cases)
    expected_failure_observed = any(
        case.get("expected_failure") and not case.get("source_selection_correct") for case in cases
    )
    ok = (
        bool(validation["ok"])
        and metrics["pool_ground_truth_coverage_rate"] == 1.0
        and metrics["unsupported_claim_rate"] == 0.0
        and metrics["abstention_accuracy"] == 1.0
        and expected_failure_observed
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_multimodal_niah_evidence_pool_benchmark",
        "generated_at": now_utc(),
        "status": "fixture_contract_scored" if validation["ok"] else "invalid_fixture",
        "ok": ok,
        "config": {
            "fixture": "benchmark_corpus/multimodal_niah_evidence_pool/fixture.json",
            "fixture_sha1": sha1_text(json.dumps(fixture, sort_keys=True))[:16],
            "source_fixture": _as_mapping(fixture.get("source_fixture")).get("path"),
            "pool_shuffle_seed_sha1": sha1_text(str(fixture.get("pool_shuffle_seed") or ""))[:16],
            "source_reopen_mode": source_reopen_mode,
            "live_provider": False,
            "raw_fixture_text_emitted": False,
        },
        "fixture_validation": validation,
        "corpus": {
            "fixture_id": fixture.get("fixture_id"),
            "fixture_license": fixture.get("fixture_license"),
            "source_fixture_id": _as_mapping(fixture.get("source_fixture")).get("fixture_id"),
            "case_count": validation["case_count"],
            "pool_sizes": validation["pool_sizes"],
            "expected_failure_case_count": validation["expected_failure_case_count"],
        },
        "tracks": {
            "derived_text_pool": {
                "status": "scored",
                "provider_route": "fixed_evidence_pool_from_public_multimodal_corpus",
                "metrics": metrics,
                "claim_boundary": {
                    "measures": "answer_synthesis_under_supplied_evidence_pool",
                    "retrieval_not_scored": True,
                    "cannot_claim": ["retrieval_quality", "atm_bench_hard_score"],
                },
            },
            "source_reopen": _source_reopen_track(cases, mode=source_reopen_mode),
        },
        "metrics": metrics,
        "rate_estimates": rate_estimates,
        "cases": cases,
        "claim_boundary": {
            "measures": "generation_reasoning_and_citation_under_supplied_evidence_pool",
            "retrieval_not_scored": True,
            "pool_contains_ground_truth": True,
            "agent_visible_prompt_excludes": [
                "ground_truth_evidence_ids",
                "expected_answer",
                "answer_correct",
                "failure_mode",
                "hidden_scoring_metadata",
            ],
        },
        "privacy_boundary": {
            "fixture_public_safe": True,
            "raw_questions_emitted": False,
            "raw_answers_emitted": False,
            "raw_fixture_text_emitted": False,
            "raw_media_bytes_emitted": False,
            "external_model_called": False,
            "absolute_paths_emitted": False,
            "output_shape": "sanitized_ids_hashes_pool_ids_anchors_and_metrics",
        },
        "cannot_claim": sorted(
            {
                "atm_bench_hard_score",
                "retrieval_quality",
                "product_privacy_behavior",
                "background_photo_library_scanning",
                "conversational_media_upload_recall",
                "captions_ocr_tags_as_source_truth",
                "live_vision_model_quality",
                "raw_media_model_answer_quality",
            }
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: Mapping[str, Any]) -> None:
    metrics = _as_mapping(payload.get("metrics"))
    print("AIppocampus multimodal NIAH evidence-pool benchmark")
    print(f"- status: {payload.get('status')} ok: {payload.get('ok')}")
    print(
        "- pool coverage: {coverage:.2%} answer: {answer:.2%} source selection: {selection:.2%}".format(
            coverage=float(metrics.get("pool_ground_truth_coverage_rate") or 0.0),
            answer=float(metrics.get("answer_correctness") or 0.0),
            selection=float(metrics.get("source_selection_accuracy") or 0.0),
        )
    )
    print(
        "- unsupported claims: {unsupported:.2%} abstention: {abstention:.2%} stale/conflict selected: {stale:.2%}".format(
            unsupported=float(metrics.get("unsupported_claim_rate") or 0.0),
            abstention=float(metrics.get("abstention_accuracy") or 0.0),
            stale=float(metrics.get("stale_or_conflicting_distractor_selection_rate") or 0.0),
        )
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--source-reopen-mode",
        choices=sorted(SOURCE_REOPEN_MODES),
        default="disabled",
        help=(
            "Use deterministic_fixture only for source-anchor reopen contract checks; "
            "it does not call or score a live multimodal provider."
        ),
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        fixture_path=args.fixture,
        source_reopen_mode=args.source_reopen_mode,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
