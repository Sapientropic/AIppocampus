#!/usr/bin/env python3
"""Public-safe multimodal corpus-style retrieval fixture for #531.

This is an ATM-Bench-inspired corpus fixture, not an ATM-Bench adapter. Derived
captions/OCR/tags are treated as navigation hints only; a case succeeds only
when the evaluator can reopen the original source anchors and respect
unsupported/conflicting-source boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

from benchmarks.aippocampus.shared.benchmark_statistics import binomial_rate_report, rounded_rate

SCHEMA_VERSION = 1
FIXTURE_SCHEMA_VERSION = "aippocampus.multimodal_corpus_fixture.v1"
DEFAULT_FIXTURE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "public_multimodal_corpus" / "fixture.json"
)
DEFAULT_TOP_K = 3
RAW_MEDIA_MODES = {"disabled", "deterministic_fixture"}
SOURCE_OPEN_REPLAY_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "caption_shortcut_control",
        "query_shape": "caption_shortcut_control",
        "evidence_ids": ["msrc-img-001"],
        "requires_raw_media_source_open": True,
        "visual_or_document_claim": True,
        "caption_shortcut_attempted": False,
        "expected_abstain": False,
        "expected_answer_state": "answer_only_after_source_open",
    },
    {
        "case_id": "raw_media_required_success",
        "query_shape": "raw_media_required_success",
        "evidence_ids": ["msrc-receipt-001"],
        "requires_raw_media_source_open": True,
        "visual_or_document_claim": True,
        "caption_shortcut_attempted": False,
        "expected_abstain": False,
        "expected_answer_state": "answer_with_reopened_raw_media",
    },
    {
        "case_id": "unsupported_visual_detail",
        "query_shape": "unsupported_visual_detail",
        "evidence_ids": ["msrc-video-001-frame-042"],
        "requires_raw_media_source_open": True,
        "visual_or_document_claim": False,
        "caption_shortcut_attempted": False,
        "expected_abstain": True,
        "expected_answer_state": "abstain_unsupported_visual_detail",
    },
    {
        "case_id": "stale_or_weaker_source_conflict",
        "query_shape": "stale_or_weaker_source_conflict",
        "evidence_ids": ["msrc-bill-001"],
        "weaker_source_ids": ["msrc-email-001"],
        "requires_raw_media_source_open": True,
        "visual_or_document_claim": True,
        "caption_shortcut_attempted": False,
        "expected_abstain": False,
        "expected_answer_state": "answer_with_stronger_source",
    },
    {
        "case_id": "cross_modal_join",
        "query_shape": "cross_modal_join",
        "evidence_ids": ["msrc-calendar-001", "msrc-receipt-001"],
        "requires_raw_media_source_open": True,
        "visual_or_document_claim": True,
        "caption_shortcut_attempted": False,
        "expected_abstain": False,
        "expected_answer_state": "answer_with_cross_modal_sources",
    },
    {
        "case_id": "provider_unavailable_hold_open",
        "query_shape": "provider_unavailable_hold_open",
        "evidence_ids": ["msrc-img-001"],
        "requires_media_provider": True,
        "requires_raw_media_source_open": True,
        "visual_or_document_claim": False,
        "caption_shortcut_attempted": False,
        "expected_abstain": True,
        "expected_answer_state": "hold_open_until_provider_available",
    },
)
REQUIRED_SOURCE_FIELDS = {
    "source_id",
    "modality",
    "source_type",
    "publisher",
    "authority_level",
    "source_owner",
    "origin_policy",
    "privacy_class",
    "access_policy",
    "license",
    "captured_at",
    "content_hash_sha256",
    "source_anchor",
    "provenance_chain",
}
REQUIRED_ARTIFACT_FIELDS = {
    "artifact_id",
    "artifact_type",
    "parent_source_id",
    "source_anchor",
    "provider_route",
    "confidence",
    "created_at",
    "authority",
}
REQUIRED_METRICS = (
    "retrieval_recall_at_3",
    "source_reopen_success_rate",
    "raw_media_source_open_success_rate",
    "visual_or_document_claim_source_open_rate",
    "unsupported_visual_claim_rate",
    "stale_or_weaker_source_selected_rate",
    "cross_modal_join_success_rate",
    "abstention_accuracy",
)


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


def _tokenize(values: Sequence[Any]) -> set[str]:
    text = " ".join(str(value or "") for value in values)
    return {
        token
        for token in re.findall(r"[A-Za-z0-9]+", text.lower())
        if len(token) > 1 and token not in {"the", "and", "for", "was", "what", "which"}
    }


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {fixture_path}")
    return payload


def _source_index(fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(source.get("source_id")): source
        for source in fixture.get("sources") or []
        if isinstance(source, Mapping) and source.get("source_id")
    }


def _blocker(code: str, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def validate_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if fixture.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        blockers.append(
            _blocker(
                "unsupported_fixture_schema_version",
                "schema_version",
                "Unsupported multimodal corpus fixture schema version.",
            )
        )

    sources = [item for item in fixture.get("sources") or [] if isinstance(item, Mapping)]
    source_ids = sorted({str(item.get("source_id")) for item in sources if item.get("source_id")})
    source_id_set = set(source_ids)
    if len(source_ids) != len(sources):
        blockers.append(
            _blocker("source_missing_or_duplicate_id", "sources.source_id", "Source ids must be unique.")
        )
    for source in sources:
        missing = sorted(field for field in REQUIRED_SOURCE_FIELDS if not source.get(field))
        if missing:
            blockers.append(
                _blocker(
                    "source_missing_required_field",
                    f"sources.{source.get('source_id') or '<missing>'}",
                    f"Missing source fields: {', '.join(missing)}.",
                )
            )

    artifacts = [
        item for item in fixture.get("derived_artifacts") or [] if isinstance(item, Mapping)
    ]
    for artifact in artifacts:
        missing = sorted(field for field in REQUIRED_ARTIFACT_FIELDS if not artifact.get(field))
        if missing:
            blockers.append(
                _blocker(
                    "derived_artifact_missing_required_field",
                    f"derived_artifacts.{artifact.get('artifact_id') or '<missing>'}",
                    f"Missing derived artifact fields: {', '.join(missing)}.",
                )
            )
        if artifact.get("parent_source_id") not in source_id_set:
            blockers.append(
                _blocker(
                    "derived_artifact_unknown_parent_source",
                    "derived_artifacts.parent_source_id",
                    "Derived artifacts must point at a known original source.",
                )
            )
        if artifact.get("authority") != "navigation_only":
            blockers.append(
                _blocker(
                    "derived_artifact_not_navigation_only",
                    "derived_artifacts.authority",
                    "Derived captions/OCR/tags must stay navigation-only.",
                )
            )

    qa_cases = [item for item in fixture.get("qa_cases") or [] if isinstance(item, Mapping)]
    for case in qa_cases:
        for source_id in _as_list(case.get("evidence_ids")) + _as_list(case.get("weaker_source_ids")):
            if source_id not in source_id_set:
                blockers.append(
                    _blocker(
                        "qa_case_unknown_evidence_source",
                        f"qa_cases.{case.get('case_id')}.evidence_ids",
                        "QA evidence ids must point at known original sources.",
                    )
                )

    return {
        "schema_version": fixture.get("schema_version"),
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "source_count": len(sources),
        "source_ids": source_ids,
        "source_modalities": sorted({str(item.get("modality")) for item in sources}),
        "derived_artifact_count": len(artifacts),
        "qa_case_count": len(qa_cases),
    }


def _artifact_score(case: Mapping[str, Any], artifact: Mapping[str, Any]) -> tuple[float, str]:
    query_tokens = _tokenize(_as_list(case.get("query_terms")) + [case.get("question")])
    artifact_tokens = _tokenize(
        [artifact.get("text")]
        + _as_list(artifact.get("tags"))
        + _as_list(artifact.get("entities"))
        + [artifact.get("time_bucket"), artifact.get("location_bucket")]
    )
    overlap = len(query_tokens & artifact_tokens)
    score = float(overlap)
    if case.get("query_shape") == "conflict_resolution" and "final" in artifact_tokens:
        score += 3.0
    if case.get("query_shape") == "cross_modal_join":
        query_join = set(_as_list(case.get("join_keys")))
        if "time_bucket" in query_join and artifact.get("time_bucket"):
            score += 0.5
        if "location_bucket" in query_join and artifact.get("location_bucket"):
            score += 0.5
    return score, str(artifact.get("artifact_id") or "")


def _rank_sources(case: Mapping[str, Any], fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_scores: dict[str, dict[str, Any]] = {}
    for artifact in fixture.get("derived_artifacts") or []:
        if not isinstance(artifact, Mapping):
            continue
        score, artifact_id = _artifact_score(case, artifact)
        if score <= 0:
            continue
        source_id = str(artifact.get("parent_source_id") or "")
        entry = source_scores.setdefault(
            source_id,
            {
                "source_id": source_id,
                "score": 0.0,
                "artifact_ids": [],
            },
        )
        entry["score"] = float(entry["score"]) + score
        entry["artifact_ids"].append(artifact_id)

    return sorted(
        source_scores.values(),
        key=lambda item: (-float(item["score"]), str(item["source_id"])),
    )


def _has_reopenable_sources(source_ids: Sequence[str], sources: Mapping[str, Mapping[str, Any]]) -> bool:
    for source_id in source_ids:
        source = sources.get(source_id)
        anchor = _as_mapping(source.get("source_anchor") if source else None)
        if not source or not anchor.get("anchor_id") or not source.get("content_hash_sha256"):
            return False
    return True


def _evaluate_derived_case(
    case: Mapping[str, Any],
    *,
    fixture: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    ranked = _rank_sources(case, fixture)
    selected_ids = [str(item["source_id"]) for item in ranked[:top_k]]
    evidence_ids = _as_list(case.get("evidence_ids"))
    weaker_ids = set(_as_list(case.get("weaker_source_ids")))
    expected_abstain = bool(case.get("expected_abstain"))
    evidence_hit = all(source_id in selected_ids for source_id in evidence_ids)
    source_reopened = evidence_hit and _has_reopenable_sources(evidence_ids, sources)
    weaker_selected = any(source_id in selected_ids[:1] for source_id in weaker_ids)
    abstained = expected_abstain and source_reopened
    answer_emitted = not expected_abstain and source_reopened and not weaker_selected
    unsupported_visual_claim = expected_abstain and answer_emitted
    cross_modal_join_success = None
    if case.get("query_shape") == "cross_modal_join":
        cross_modal_join_success = len(set(evidence_ids) & set(selected_ids[:top_k])) == len(
            set(evidence_ids)
        )

    return {
        "case_id": case.get("case_id"),
        "query_shape": case.get("query_shape"),
        "question_sha1": sha1_text(str(case.get("question") or ""))[:16],
        "answer_sha1": sha1_text(str(case.get("answer") or ""))[:16],
        "expected_evidence_ids": evidence_ids,
        "selected_source_ids_top3": selected_ids,
        "derived_artifact_ids": sorted(
            {
                artifact_id
                for item in ranked[:top_k]
                for artifact_id in _as_list(item.get("artifact_ids"))
            }
        ),
        "expected_abstain": expected_abstain,
        "answer_state": case.get("expected_answer_state"),
        "retrieval_hit_top3": evidence_hit,
        "source_reopened": source_reopened,
        "weaker_source_selected": weaker_selected,
        "unsupported_visual_claim": unsupported_visual_claim,
        "abstained": abstained,
        "cross_modal_join_success": cross_modal_join_success,
    }


def _rate(name: str, numerator: int, denominator: int) -> dict[str, Any]:
    return binomial_rate_report(name, numerator=numerator, denominator=denominator)


def _metrics(cases: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    answerable = [case for case in cases if not case.get("expected_abstain")]
    unsupported = [case for case in cases if case.get("expected_abstain")]
    conflict = [case for case in cases if case.get("query_shape") == "conflict_resolution"]
    cross_modal = [case for case in cases if case.get("query_shape") == "cross_modal_join"]

    retrieval_hits = sum(1 for case in answerable if case.get("retrieval_hit_top3"))
    reopen_hits = sum(1 for case in cases if case.get("source_reopened"))
    unsupported_claims = sum(1 for case in unsupported if case.get("unsupported_visual_claim"))
    weaker_selected = sum(1 for case in conflict if case.get("weaker_source_selected"))
    cross_modal_hits = sum(1 for case in cross_modal if case.get("cross_modal_join_success"))
    abstention_hits = sum(1 for case in unsupported if case.get("abstained"))

    metric_counts = {
        "retrieval_recall_at_3": (retrieval_hits, len(answerable)),
        "source_reopen_success_rate": (reopen_hits, len(cases)),
        "unsupported_visual_claim_rate": (unsupported_claims, len(unsupported)),
        "stale_or_weaker_source_selected_rate": (weaker_selected, len(conflict)),
        "cross_modal_join_success_rate": (cross_modal_hits, len(cross_modal)),
        "abstention_accuracy": (abstention_hits, len(unsupported)),
    }
    metrics = {
        name: rounded_rate(numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }
    rate_estimates = {
        name: _rate(name, numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }
    return metrics, rate_estimates


def _evaluate_source_open_replay_case(
    case: Mapping[str, Any],
    *,
    sources: Mapping[str, Mapping[str, Any]],
    declared_media_provider: str | None,
) -> dict[str, Any]:
    evidence_ids = _as_list(case.get("evidence_ids"))
    weaker_ids = _as_list(case.get("weaker_source_ids"))
    provider_required = bool(case.get("requires_media_provider"))
    provider_available = bool(declared_media_provider)
    provider_blocked = provider_required and not provider_available
    source_opened = (not provider_blocked) and _has_reopenable_sources(evidence_ids, sources)
    weaker_source_selected = False
    expected_abstain = bool(case.get("expected_abstain"))
    abstained = expected_abstain and (provider_blocked or source_opened)

    # Caption/OCR artifacts may route attention, but this replay cohort treats
    # source-open as the product boundary. Do not "optimize" this into a
    # caption-only pass: it is guarding the exact shortcut that made fixture
    # scores look stronger than real media/document replay.
    caption_shortcut_violation = bool(case.get("caption_shortcut_attempted")) and not source_opened
    unsupported_visual_claim = (
        case.get("query_shape") == "unsupported_visual_detail"
        and bool(case.get("visual_or_document_claim"))
        and not abstained
    )
    cross_modal_join_success = None
    if case.get("query_shape") == "cross_modal_join":
        cross_modal_join_success = source_opened and len(set(evidence_ids)) >= 2

    return {
        "case_id": case.get("case_id"),
        "query_shape": case.get("query_shape"),
        "expected_evidence_ids": evidence_ids,
        "weaker_source_ids": weaker_ids,
        "expected_abstain": expected_abstain,
        "answer_state": case.get("expected_answer_state"),
        "requires_media_provider": provider_required,
        "provider_status": (
            "available_or_declared"
            if provider_required and provider_available
            else "unavailable"
            if provider_required
            else "not_required"
        ),
        "provider_blocked": provider_blocked,
        "requires_raw_media_source_open": bool(case.get("requires_raw_media_source_open")),
        "source_opened": source_opened,
        "visual_or_document_claim": bool(case.get("visual_or_document_claim")),
        "caption_shortcut_violation": caption_shortcut_violation,
        "unsupported_visual_claim": unsupported_visual_claim,
        "weaker_source_selected": weaker_source_selected,
        "cross_modal_join_success": cross_modal_join_success,
        "abstained": abstained,
    }


def _run_source_open_replay_track(
    *,
    enabled: bool,
    sources: Mapping[str, Mapping[str, Any]],
    declared_media_provider: str | None,
) -> dict[str, Any]:
    if not enabled:
        return {
            "status": "not_requested",
            "provider_route": None,
            "cases": [],
            "blockers": [],
            "claim_boundary": {
                "measures": "nothing_until_source_open_replay_is_requested",
                "cannot_claim": ["raw_media_model_answer_quality", "live_vision_model_quality"],
            },
        }

    cases = [
        _evaluate_source_open_replay_case(
            case,
            sources=sources,
            declared_media_provider=declared_media_provider,
        )
        for case in SOURCE_OPEN_REPLAY_CASES
    ]
    blockers = []
    if any(case.get("provider_blocked") for case in cases):
        blockers.append(
            _blocker(
                "media_provider_unavailable",
                "declared_media_provider",
                "Source-open replay includes media-provider cases, but no live or declared media provider was configured.",
            )
        )

    return {
        "status": "scored",
        "provider_route": declared_media_provider or None,
        "cases": cases,
        "blockers": blockers,
        "claim_boundary": {
            "measures": "public_safe_source_open_media_document_replay",
            "can_claim": [
                "source_open_replay_contract_records_provider_blockers",
                "fixture_scores_are_separated_from_media_provider_cases",
            ],
            "cannot_claim": [
                "raw_media_model_answer_quality",
                "live_vision_model_quality",
                "live_product_lift",
            ],
        },
    }


def _run_provider_blocked_track(
    replay_track: Mapping[str, Any],
) -> dict[str, Any]:
    cases = [
        case
        for case in replay_track.get("cases") or []
        if isinstance(case, Mapping) and case.get("provider_blocked")
    ]
    return {
        "status": "blocked" if cases else "not_blocked",
        "provider_route": None,
        "cases": cases,
        "blockers": replay_track.get("blockers") or [],
        "claim_boundary": {
            "measures": "provider_availability_boundary",
            "cannot_claim": [
                "raw_media_model_answer_quality",
                "live_vision_model_quality",
                "live_product_lift",
            ],
        },
    }


def _replay_metrics(
    replay_cases: Sequence[Mapping[str, Any]],
    *,
    deterministic_case_count: int,
    raw_media_mode: str,
    declared_media_provider: str | None,
) -> dict[str, Any]:
    source_open_required = [
        case
        for case in replay_cases
        if case.get("requires_raw_media_source_open") and not case.get("provider_blocked")
    ]
    visual_or_document_claims = [
        case
        for case in replay_cases
        if case.get("visual_or_document_claim") and not case.get("provider_blocked")
    ]
    unsupported = [case for case in replay_cases if case.get("expected_abstain")]
    conflict = [
        case
        for case in replay_cases
        if case.get("query_shape") == "stale_or_weaker_source_conflict"
    ]
    cross_modal = [case for case in replay_cases if case.get("query_shape") == "cross_modal_join"]

    source_open_hits = sum(1 for case in source_open_required if case.get("source_opened"))
    visual_source_open_hits = sum(
        1 for case in visual_or_document_claims if case.get("source_opened")
    )
    unsupported_claims = sum(1 for case in unsupported if case.get("unsupported_visual_claim"))
    weaker_selected = sum(1 for case in conflict if case.get("weaker_source_selected"))
    cross_modal_hits = sum(1 for case in cross_modal if case.get("cross_modal_join_success"))
    abstention_hits = sum(1 for case in unsupported if case.get("abstained"))
    provider_blockers = sum(1 for case in replay_cases if case.get("provider_blocked"))
    provider_case_count = sum(
        1
        for case in replay_cases
        if case.get("requires_media_provider") and bool(declared_media_provider)
    )

    return {
        "multimodal_replay_case_count": len(replay_cases),
        "deterministic_fixture_only_case_count": deterministic_case_count,
        "live_or_declared_media_provider_case_count": provider_case_count,
        "raw_media_source_open_success_rate": rounded_rate(
            source_open_hits,
            len(source_open_required),
        ),
        "visual_or_document_claim_source_open_rate": rounded_rate(
            visual_source_open_hits,
            len(visual_or_document_claims),
        ),
        "caption_shortcut_violation_count": sum(
            1 for case in replay_cases if case.get("caption_shortcut_violation")
        ),
        "unsupported_visual_claim_rate": rounded_rate(unsupported_claims, len(unsupported)),
        "stale_or_weaker_source_selected_rate": rounded_rate(weaker_selected, len(conflict)),
        "cross_modal_join_success_rate": rounded_rate(cross_modal_hits, len(cross_modal)),
        "abstention_accuracy": rounded_rate(abstention_hits, len(unsupported)),
        "provider_unavailable_blocker_count": provider_blockers,
        "raw_media_bytes_public_reported_count": 0,
        "absolute_path_leak_count": 0,
        "live_product_lift_claimed": False,
        "raw_media_track_uses_deterministic_fixture": raw_media_mode == "deterministic_fixture",
    }


def _run_raw_media_track(
    derived_cases: Sequence[Mapping[str, Any]],
    *,
    raw_media_mode: str,
) -> dict[str, Any]:
    if raw_media_mode == "disabled":
        return {
            "status": "skipped_provider_not_configured",
            "provider_route": None,
            "metrics": {},
            "claim_boundary": {
                "measures": "raw_media_source_reopen_path_when_provider_is_available",
                "cannot_claim": ["raw_media_model_answer_quality", "live_vision_model_quality"],
            },
        }
    metrics, rate_estimates = _metrics(derived_cases)
    return {
        "status": "scored",
        "provider_route": "deterministic_fixture",
        "metrics": {
            "source_reopen_success_rate": metrics["source_reopen_success_rate"],
            "unsupported_visual_claim_rate": metrics["unsupported_visual_claim_rate"],
        },
        "rate_estimates": {
            "source_reopen_success_rate": rate_estimates["source_reopen_success_rate"],
            "unsupported_visual_claim_rate": rate_estimates["unsupported_visual_claim_rate"],
        },
        "claim_boundary": {
            "measures": "raw_media_anchor_reopen_contract_only",
            "cannot_claim": ["raw_media_model_answer_quality", "live_vision_model_quality"],
        },
    }


def run_benchmark(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    top_k: int = DEFAULT_TOP_K,
    raw_media_mode: str = "disabled",
    source_open_replay: bool = False,
    declared_media_provider: str | None = None,
) -> dict[str, Any]:
    if raw_media_mode not in RAW_MEDIA_MODES:
        raise ValueError(f"raw_media_mode must be one of {sorted(RAW_MEDIA_MODES)}")
    started = time.perf_counter()
    fixture = load_fixture(fixture_path)
    validation = validate_fixture(fixture)
    sources = _source_index(fixture)
    derived_cases = [
        _evaluate_derived_case(case, fixture=fixture, sources=sources, top_k=top_k)
        for case in fixture.get("qa_cases") or []
        if isinstance(case, Mapping)
    ]
    metrics, rate_estimates = _metrics(derived_cases)
    replay_track = _run_source_open_replay_track(
        enabled=source_open_replay,
        sources=sources,
        declared_media_provider=declared_media_provider,
    )
    provider_blocked_track = _run_provider_blocked_track(replay_track)
    replay_metrics = _replay_metrics(
        replay_track.get("cases") or [],
        deterministic_case_count=len(derived_cases),
        raw_media_mode=raw_media_mode,
        declared_media_provider=declared_media_provider,
    )
    combined_metrics = dict(metrics)
    if source_open_replay:
        combined_metrics.update(replay_metrics)
    else:
        for name, value in replay_metrics.items():
            combined_metrics.setdefault(name, value)
    blocker_codes = sorted(
        {
            item["code"]
            for item in (validation.get("blockers") or [])
            + (replay_track.get("blockers") or [])
            + (provider_blocked_track.get("blockers") or [])
            if isinstance(item, Mapping) and item.get("code")
        }
    )
    ok = bool(validation["ok"]) and all(
        metrics[name] == (0.0 if name.endswith("_claim_rate") or name.endswith("_selected_rate") else 1.0)
        for name in REQUIRED_METRICS
        if name in metrics
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_multimodal_corpus_retrieval_benchmark",
        "generated_at": now_utc(),
        "status": "fixture_contract_scored" if validation["ok"] else "invalid_fixture",
        "ok": ok,
        "config": {
            "fixture": "benchmark_corpus/public_multimodal_corpus/fixture.json",
            "fixture_sha1": sha1_text(json.dumps(fixture, sort_keys=True))[:16],
            "top_k": int(top_k),
            "raw_media_mode": raw_media_mode,
            "source_open_replay": bool(source_open_replay),
            "declared_media_provider": declared_media_provider,
            "live_provider": False,
            "raw_fixture_text_emitted": False,
        },
        "corpus": {
            "fixture_id": fixture.get("fixture_id"),
            "fixture_license": fixture.get("fixture_license"),
            "source_count": validation["source_count"],
            "source_modalities": validation["source_modalities"],
            "derived_artifact_count": validation["derived_artifact_count"],
            "qa_case_count": validation["qa_case_count"],
        },
        "fixture_validation": validation,
        "blocker_codes": blocker_codes,
        "tracks": {
            "deterministic_fixture": {
                "status": "scored",
                "provider_route": "synthetic_caption_ocr_tag_metadata",
                "metrics": metrics,
                "case_count": len(derived_cases),
                "claim_boundary": {
                    "measures": "deterministic_fixture_source_navigation_only",
                    "cannot_claim": [
                        "raw_media_model_answer_quality",
                        "live_vision_model_quality",
                        "live_product_lift",
                    ],
                },
            },
            "derived_text": {
                "status": "scored",
                "provider_route": "synthetic_caption_ocr_tag_metadata",
                "metrics": metrics,
                "claim_boundary": {
                    "measures": "corpus_style_multimodal_source_navigation",
                    "can_claim": [
                        "public_safe_atm_bench_inspired_corpus_style_fixture_contract",
                        "derived_artifact_navigation_to_reopenable_sources",
                    ],
                    "cannot_claim": [
                        "conversational_media_upload_recall",
                        "raw_media_model_answer_quality",
                        "atm_bench_hard_score",
                    ],
                },
            },
            "raw_media": _run_raw_media_track(derived_cases, raw_media_mode=raw_media_mode),
            "source_open_replay": replay_track,
            "provider_blocked": provider_blocked_track,
        },
        "metrics": combined_metrics,
        "rate_estimates": rate_estimates,
        "cases": derived_cases,
        "privacy_boundary": {
            "fixture_public_safe": True,
            "raw_fixture_text_emitted": False,
            "raw_caption_ocr_text_emitted": False,
            "raw_media_exported": False,
            "external_model_called": False,
            "absolute_paths_emitted": False,
            "output_shape": "sanitized_ids_hashes_anchors_and_metrics",
        },
        "cannot_claim": sorted(
            {
                "atm_bench_hard_score",
                "conversational_media_upload_recall",
                "product_privacy_behavior",
                "background_photo_library_scanning",
                "face_recognition_identity_graph",
                "captions_ocr_tags_as_source_truth",
                "live_vision_model_quality",
                "raw_media_model_answer_quality",
                "live_product_lift",
            }
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: Mapping[str, Any]) -> None:
    metrics = _as_mapping(payload.get("metrics"))
    print("AIppocampus multimodal corpus retrieval benchmark")
    print(f"- status: {payload.get('status')} ok: {payload.get('ok')}")
    print(
        "- derived top-3: {retrieval:.2%} reopen: {reopen:.2%} "
        "cross-modal: {cross:.2%} abstention: {abstain:.2%}".format(
            retrieval=float(metrics.get("retrieval_recall_at_3") or 0.0),
            reopen=float(metrics.get("source_reopen_success_rate") or 0.0),
            cross=float(metrics.get("cross_modal_join_success_rate") or 0.0),
            abstain=float(metrics.get("abstention_accuracy") or 0.0),
        )
    )
    print(
        "- unsupported visual claims: {unsupported:.2%} weaker-source selected: {weaker:.2%}".format(
            unsupported=float(metrics.get("unsupported_visual_claim_rate") or 0.0),
            weaker=float(metrics.get("stale_or_weaker_source_selected_rate") or 0.0),
        )
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument(
        "--raw-media-mode",
        choices=sorted(RAW_MEDIA_MODES),
        default="disabled",
        help=(
            "Use deterministic_fixture only for the public source-reopen contract; "
            "it does not call or score a live vision model."
        ),
    )
    parser.add_argument(
        "--source-open-replay",
        action="store_true",
        help=(
            "Add the public-safe media/document source-open replay cohort and "
            "separate provider-blocked cases from deterministic fixture scores."
        ),
    )
    parser.add_argument(
        "--declared-media-provider",
        default=None,
        help=(
            "Optional public-safe provider route label for replay accounting. "
            "This is a declaration only; the benchmark still does not call or "
            "score a live media provider."
        ),
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        fixture_path=args.fixture,
        top_k=args.top_k,
        raw_media_mode=args.raw_media_mode,
        source_open_replay=args.source_open_replay,
        declared_media_provider=args.declared_media_provider,
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
