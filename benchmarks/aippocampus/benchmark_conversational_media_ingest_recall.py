#!/usr/bin/env python3
"""Conversational media-ingest recall contract for #532.

This benchmark is the counterpart to the ATM-Bench-inspired staged-corpus
fixture. Here, the conversation around an upload is itself source evidence, but
text hints still cannot replace reopening the media source for visual claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

from benchmarks.aippocampus.shared.benchmark_statistics import binomial_rate_report, rounded_rate

SCHEMA_VERSION = 1
FIXTURE_SCHEMA_VERSION = "aippocampus.conversational_media_ingest_fixture.v1"
DEFAULT_FIXTURE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "conversational_media_ingest" / "fixture.json"
)
REQUIRED_TURN_FIELDS = {
    "turn_id",
    "conversation_id",
    "role",
    "captured_at",
    "source_kind",
    "origin_policy",
    "privacy_class",
    "source_anchor",
    "attached_media_ids",
}
REQUIRED_MEDIA_FIELDS = {
    "media_id",
    "source_kind",
    "modality",
    "attached_to_turn_id",
    "origin_policy",
    "inspection_scope",
    "privacy_class",
    "content_hash_sha256",
    "source_anchor",
}
REQUIRED_METRICS = (
    "personal_reference_resolution_rate",
    "visual_source_reopen_rate",
    "text_hint_leakage_rate",
    "stale_label_correction_success_rate",
    "unsupported_visual_claim_rate",
    "hidden_durable_write_count",
)
REPLAY_REQUIRED_METRICS = (
    "conversational_media_replay_case_count",
    "fixture_boolean_only_case_count",
    "live_or_declared_media_provider_case_count",
    "conversation_turn_source_open_rate",
    "attached_media_source_open_rate",
    "personal_reference_resolution_rate",
    "text_hint_as_visual_proof_violation_count",
    "stale_label_correction_success_rate",
    "hidden_durable_write_count",
    "background_media_access_denied_count",
    "unsupported_visual_claim_rate",
    "provider_unavailable_blocker_count",
    "raw_media_bytes_public_reported_count",
    "absolute_path_leak_count",
    "live_product_lift_claimed",
)
SOURCE_OPEN_REPLAY_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "same_task_upload_success",
        "cohort": "source_open_replay",
        "flow": "same_task_upload_selection",
        "requires_conversation_source_open": True,
        "requires_attached_media_source_open": True,
        "source_open": {"conversation_turn": True, "attached_media": True},
        "personal_reference_expected": True,
        "personal_reference_resolved": True,
        "visual_claim_requires_media": True,
        "answer_state": "answer_with_conversation_and_attached_media_sources",
    },
    {
        "case_id": "text_hint_not_visual_proof",
        "cohort": "source_open_replay",
        "flow": "text_hint_only_control",
        "requires_conversation_source_open": True,
        "requires_attached_media_source_open": False,
        "source_open": {"conversation_turn": True, "attached_media": False},
        "visual_claim_requires_media": True,
        "answer_state": "hold_open_requires_attached_media_source_open",
        "text_hint_as_visual_proof_violation": False,
    },
    {
        "case_id": "media_only_label_missing",
        "cohort": "source_open_replay",
        "flow": "media_only_control",
        "requires_conversation_source_open": False,
        "requires_attached_media_source_open": True,
        "source_open": {"conversation_turn": False, "attached_media": True},
        "label_missing": True,
        "visual_claim_requires_media": True,
        "answer_state": "media_reopened_personal_label_missing",
    },
    {
        "case_id": "stale_label_correction",
        "cohort": "source_open_replay",
        "flow": "correction_turn_supersedes_stale_upload_label",
        "requires_conversation_source_open": True,
        "requires_attached_media_source_open": True,
        "source_open": {"conversation_turn": True, "attached_media": True},
        "personal_reference_expected": True,
        "personal_reference_resolved": True,
        "stale_label_corrected": True,
        "visual_claim_requires_media": True,
        "answer_state": "answer_with_corrected_label_source",
    },
    {
        "case_id": "hidden_durable_write_blocked",
        "cohort": "provider_blocked",
        "flow": "hidden_durable_write_request",
        "requires_conversation_source_open": True,
        "requires_attached_media_source_open": False,
        "source_open": {"conversation_turn": True, "attached_media": False},
        "blocked": True,
        "hidden_durable_write_attempted": True,
        "hidden_durable_write_performed": False,
        "answer_state": "blocked_hidden_durable_write",
    },
    {
        "case_id": "background_media_denied",
        "cohort": "provider_blocked",
        "flow": "background_media_access_request",
        "requires_conversation_source_open": False,
        "requires_attached_media_source_open": False,
        "source_open": {"conversation_turn": False, "attached_media": False},
        "blocked": True,
        "background_media_access_denied": True,
        "answer_state": "blocked_background_media_access",
    },
    {
        "case_id": "provider_unavailable_hold_open",
        "cohort": "provider_blocked",
        "flow": "declared_media_provider_unavailable",
        "requires_conversation_source_open": False,
        "requires_attached_media_source_open": False,
        "source_open": {"conversation_turn": False, "attached_media": False},
        "media_provider": "declared_unavailable",
        "provider_blocked": True,
        "answer_state": "hold_open_provider_unavailable",
    },
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


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {fixture_path}")
    return payload


def _blocker(code: str, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def validate_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if fixture.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        blockers.append(
            _blocker(
                "unsupported_fixture_schema_version",
                "schema_version",
                "Unsupported conversational media-ingest fixture schema version.",
            )
        )
    if fixture.get("consent_boundary") != "task_scoped_user_provided_media_only":
        blockers.append(
            _blocker(
                "invalid_consent_boundary",
                "consent_boundary",
                "Conversational media-ingest fixtures must stay task-scoped.",
            )
        )

    turns = [
        item for item in fixture.get("conversation_turns") or [] if isinstance(item, Mapping)
    ]
    media_sources = [
        item for item in fixture.get("media_sources") or [] if isinstance(item, Mapping)
    ]
    turn_ids = sorted({str(item.get("turn_id")) for item in turns if item.get("turn_id")})
    media_ids = sorted({str(item.get("media_id")) for item in media_sources if item.get("media_id")})
    turn_id_set = set(turn_ids)
    media_id_set = set(media_ids)

    for turn in turns:
        missing = sorted(field for field in REQUIRED_TURN_FIELDS if field not in turn)
        if missing:
            blockers.append(
                _blocker(
                    "conversation_turn_missing_required_field",
                    f"conversation_turns.{turn.get('turn_id') or '<missing>'}",
                    f"Missing turn fields: {', '.join(missing)}.",
                )
            )
        for media_id in _as_list(turn.get("attached_media_ids")):
            if media_id not in media_id_set:
                blockers.append(
                    _blocker(
                        "conversation_turn_unknown_attached_media",
                        "conversation_turns.attached_media_ids",
                        "Attached media ids must point at known media sources.",
                    )
                )

    for media in media_sources:
        missing = sorted(field for field in REQUIRED_MEDIA_FIELDS if field not in media)
        if missing:
            blockers.append(
                _blocker(
                    "media_source_missing_required_field",
                    f"media_sources.{media.get('media_id') or '<missing>'}",
                    f"Missing media fields: {', '.join(missing)}.",
                )
            )
        if media.get("attached_to_turn_id") not in turn_id_set:
            blockers.append(
                _blocker(
                    "media_source_unknown_attached_turn",
                    "media_sources.attached_to_turn_id",
                    "Media sources must be attached to a known conversation turn.",
                )
            )
        if media.get("origin_policy") != "user_provided_same_task":
            blockers.append(
                _blocker(
                    "media_source_invalid_origin_policy",
                    "media_sources.origin_policy",
                    "This fixture only covers media the user provided in the same task.",
                )
            )

    for case in fixture.get("cases") or []:
        if not isinstance(case, Mapping):
            continue
        for turn_id in _as_list(case.get("required_conversation_source_ids")):
            if turn_id not in turn_id_set:
                blockers.append(
                    _blocker(
                        "case_unknown_conversation_source",
                        f"cases.{case.get('case_id')}.required_conversation_source_ids",
                        "Case conversation source ids must point at known turns.",
                    )
                )
        for media_id in _as_list(case.get("required_media_source_ids")):
            if media_id not in media_id_set:
                blockers.append(
                    _blocker(
                        "case_unknown_media_source",
                        f"cases.{case.get('case_id')}.required_media_source_ids",
                        "Case media source ids must point at known media sources.",
                    )
                )

    return {
        "schema_version": fixture.get("schema_version"),
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "conversation_count": len({str(item.get("conversation_id")) for item in turns}),
        "turn_ids": turn_ids,
        "media_ids": media_ids,
        "media_anchor_count": sum(
            1 for item in media_sources if _as_mapping(item.get("source_anchor")).get("anchor_id")
        ),
        "source_kinds": sorted(
            {str(item.get("source_kind")) for item in turns + media_sources if item.get("source_kind")}
        ),
        "consent_boundary": fixture.get("consent_boundary"),
        "case_count": len([item for item in fixture.get("cases") or [] if isinstance(item, Mapping)]),
    }


def _source_reopen_ok(source_ids: Sequence[str], media_by_id: Mapping[str, Mapping[str, Any]]) -> bool:
    for source_id in source_ids:
        media = media_by_id.get(source_id)
        anchor = _as_mapping(media.get("source_anchor") if media else None)
        if not media or not anchor.get("anchor_id") or not media.get("content_hash_sha256"):
            return False
    return True


def _evaluate_case(
    case: Mapping[str, Any],
    *,
    media_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    required_media_ids = _as_list(case.get("required_media_source_ids"))
    conversation_hint = bool(case.get("conversation_hint_support"))
    media_reopened = bool(case.get("media_reopened")) and _source_reopen_ok(
        required_media_ids,
        media_by_id,
    )
    visual_claim_requires_media = bool(case.get("visual_claim_requires_media"))
    text_only_visual_attempt = (
        visual_claim_requires_media and conversation_hint and not media_reopened
    )
    answer_state = str(case.get("expected_answer_state") or "unknown")
    text_hint_leakage = text_only_visual_attempt and not answer_state.startswith("abstain")
    unsupported_visual_claim = visual_claim_requires_media and not media_reopened and not answer_state.startswith("abstain")
    stale_label_corrected = (
        case.get("control_arm") == "stale_label_correction"
        and bool(case.get("selected_label_source_id"))
        and bool(_as_list(case.get("rejected_stale_source_ids")))
    )
    personal_reference_resolved = (
        bool(case.get("personal_reference"))
        and conversation_hint
        and media_reopened
        and not text_hint_leakage
    )
    combined_success = (
        case.get("control_arm") == "combined_source_backed_recall"
        and conversation_hint
        and media_reopened
    )
    media_only_label_available = (
        case.get("control_arm") == "media_only_corpus_retrieval" and conversation_hint
    )

    return {
        "case_id": case.get("case_id"),
        "control_arm": case.get("control_arm"),
        "question_sha1": sha1_text(str(case.get("question") or ""))[:16],
        "answer_sha1": sha1_text(str(case.get("expected_answer") or ""))[:16],
        "required_conversation_source_ids": _as_list(case.get("required_conversation_source_ids")),
        "required_media_source_ids": required_media_ids,
        "support": {
            "conversation_hint": conversation_hint,
            "media_reopened": media_reopened,
            "visual_claim_requires_media": visual_claim_requires_media,
        },
        "answer_state": answer_state,
        "personal_reference_expected": bool(case.get("personal_reference")),
        "personal_reference_resolved": personal_reference_resolved,
        "combined_success": combined_success,
        "media_only_label_available": media_only_label_available,
        "text_hint_leakage": text_hint_leakage,
        "unsupported_visual_claim": unsupported_visual_claim,
        "stale_label_corrected": stale_label_corrected,
        "selected_label_source_id": case.get("selected_label_source_id"),
        "rejected_stale_source_ids": _as_list(case.get("rejected_stale_source_ids")),
        "hidden_durable_write": bool(case.get("hidden_durable_write")),
    }


def _rate(name: str, numerator: int, denominator: int) -> dict[str, Any]:
    return binomial_rate_report(name, numerator=numerator, denominator=denominator)


def _metrics(cases: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    personal = [case for case in cases if case.get("personal_reference_expected")]
    visual_reopen = [
        case
        for case in cases
        if case.get("support", {}).get("visual_claim_requires_media")
        and case.get("control_arm") != "text_only_conversational_hint"
        and case.get("control_arm") != "media_only_corpus_retrieval"
    ]
    text_only = [case for case in cases if case.get("control_arm") == "text_only_conversational_hint"]
    stale = [case for case in cases if case.get("control_arm") == "stale_label_correction"]
    unsupported = [case for case in cases if case.get("answer_state") == "abstain_requires_media_reopen"]

    personal_hits = sum(1 for case in personal if case.get("personal_reference_resolved"))
    visual_hits = sum(1 for case in visual_reopen if case.get("support", {}).get("media_reopened"))
    text_hint_leaks = sum(1 for case in text_only if case.get("text_hint_leakage"))
    stale_hits = sum(1 for case in stale if case.get("stale_label_corrected"))
    unsupported_claims = sum(1 for case in unsupported if case.get("unsupported_visual_claim"))
    hidden_writes = sum(1 for case in cases if case.get("hidden_durable_write"))

    metric_counts = {
        "personal_reference_resolution_rate": (personal_hits, len(personal)),
        "visual_source_reopen_rate": (visual_hits, len(visual_reopen)),
        "text_hint_leakage_rate": (text_hint_leaks, len(text_only)),
        "stale_label_correction_success_rate": (stale_hits, len(stale)),
        "unsupported_visual_claim_rate": (unsupported_claims, len(unsupported)),
    }
    metrics = {
        name: rounded_rate(numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }
    metrics["hidden_durable_write_count"] = hidden_writes
    return metrics, {
        name: _rate(name, numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }


def _control_arms(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def arm_cases(name: str) -> list[Mapping[str, Any]]:
        return [case for case in cases if case.get("control_arm") == name]

    text_only = arm_cases("text_only_conversational_hint")
    media_only = arm_cases("media_only_corpus_retrieval")
    combined = arm_cases("combined_source_backed_recall")
    stale = arm_cases("stale_label_correction")
    return {
        "text_only_conversational_hint": {
            "case_count": len(text_only),
            "visual_claim_allowed": False,
            "leakage_rate": rounded_rate(
                sum(1 for case in text_only if case.get("text_hint_leakage")),
                len(text_only),
            ),
        },
        "media_only_corpus_retrieval": {
            "case_count": len(media_only),
            "personal_label_available": any(case.get("media_only_label_available") for case in media_only),
            "claim_boundary": "Media-only retrieval can reopen the asset but cannot recover user-provided labels.",
        },
        "combined_source_backed_recall": {
            "case_count": len(combined),
            "success_rate": rounded_rate(
                sum(1 for case in combined if case.get("combined_success")),
                len(combined),
            ),
        },
        "stale_label_correction": {
            "case_count": len(stale),
            "success_rate": rounded_rate(
                sum(1 for case in stale if case.get("stale_label_corrected")),
                len(stale),
            ),
        },
    }


def _copy_replay_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Keep replay output sanitized: ids, state, and boundary booleans only."""
    copied: dict[str, Any] = {
        "case_id": case.get("case_id"),
        "cohort": case.get("cohort"),
        "flow": case.get("flow"),
        "source_open": dict(_as_mapping(case.get("source_open"))),
        "answer_state": case.get("answer_state"),
    }
    optional_fields = (
        "personal_reference_expected",
        "personal_reference_resolved",
        "visual_claim_requires_media",
        "text_hint_as_visual_proof_violation",
        "label_missing",
        "stale_label_corrected",
        "blocked",
        "hidden_durable_write_attempted",
        "hidden_durable_write_performed",
        "background_media_access_denied",
        "media_provider",
        "provider_blocked",
    )
    for field in optional_fields:
        if field in case:
            copied[field] = case[field]
    return copied


def _source_open_replay_report(
    *,
    fixture_boolean_only_case_count: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    replay_cases = [_copy_replay_case(case) for case in SOURCE_OPEN_REPLAY_CASES]
    turn_expected = [
        case for case in SOURCE_OPEN_REPLAY_CASES if case.get("requires_conversation_source_open")
    ]
    media_expected = [
        case for case in SOURCE_OPEN_REPLAY_CASES if case.get("requires_attached_media_source_open")
    ]
    personal = [case for case in SOURCE_OPEN_REPLAY_CASES if case.get("personal_reference_expected")]
    stale = [case for case in SOURCE_OPEN_REPLAY_CASES if case.get("case_id") == "stale_label_correction"]
    unsupported_visual = [
        case
        for case in SOURCE_OPEN_REPLAY_CASES
        if case.get("visual_claim_requires_media")
        and case.get("answer_state") != "hold_open_requires_attached_media_source_open"
    ]
    turn_hits = sum(
        1
        for case in turn_expected
        if _as_mapping(case.get("source_open")).get("conversation_turn")
    )
    media_hits = sum(
        1
        for case in media_expected
        if _as_mapping(case.get("source_open")).get("attached_media")
    )
    personal_hits = sum(1 for case in personal if case.get("personal_reference_resolved"))
    stale_hits = sum(1 for case in stale if case.get("stale_label_corrected"))
    unsupported_claims = sum(
        1
        for case in unsupported_visual
        if not _as_mapping(case.get("source_open")).get("attached_media")
        and str(case.get("answer_state") or "").startswith("answer_")
    )

    metric_counts = {
        "conversation_turn_source_open_rate": (turn_hits, len(turn_expected)),
        "attached_media_source_open_rate": (media_hits, len(media_expected)),
        "personal_reference_resolution_rate": (personal_hits, len(personal)),
        "stale_label_correction_success_rate": (stale_hits, len(stale)),
        "unsupported_visual_claim_rate": (unsupported_claims, len(unsupported_visual)),
    }
    metrics = {
        name: rounded_rate(numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }
    metrics.update(
        {
            "conversational_media_replay_case_count": len(replay_cases),
            "fixture_boolean_only_case_count": fixture_boolean_only_case_count,
            "live_or_declared_media_provider_case_count": sum(
                1 for case in SOURCE_OPEN_REPLAY_CASES if case.get("media_provider")
            ),
            "text_hint_as_visual_proof_violation_count": sum(
                1
                for case in SOURCE_OPEN_REPLAY_CASES
                if case.get("text_hint_as_visual_proof_violation")
            ),
            # Hidden writes are a hard privacy boundary: attempted requests may be
            # represented, but performed writes must remain zero in this public-safe replay.
            "hidden_durable_write_count": sum(
                1
                for case in SOURCE_OPEN_REPLAY_CASES
                if case.get("hidden_durable_write_performed")
            ),
            "background_media_access_denied_count": sum(
                1
                for case in SOURCE_OPEN_REPLAY_CASES
                if case.get("background_media_access_denied")
            ),
            "provider_unavailable_blocker_count": sum(
                1 for case in SOURCE_OPEN_REPLAY_CASES if case.get("provider_blocked")
            ),
            "raw_media_bytes_public_reported_count": 0,
            "absolute_path_leak_count": 0,
            "live_product_lift_claimed": False,
        }
    )
    return replay_cases, metrics, {
        name: _rate(name, numerator, denominator)
        for name, (numerator, denominator) in metric_counts.items()
    }


def run_benchmark(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    source_open_replay: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    fixture = load_fixture(fixture_path)
    validation = validate_fixture(fixture)
    media_by_id = {
        str(item.get("media_id")): item
        for item in fixture.get("media_sources") or []
        if isinstance(item, Mapping) and item.get("media_id")
    }
    cases = [
        _evaluate_case(case, media_by_id=media_by_id)
        for case in fixture.get("cases") or []
        if isinstance(case, Mapping)
    ]
    metrics, rate_estimates = _metrics(cases)
    source_open_replay_cases: list[dict[str, Any]] = []
    if source_open_replay:
        source_open_replay_cases, metrics, rate_estimates = _source_open_replay_report(
            fixture_boolean_only_case_count=len(cases),
        )
    ok = (
        bool(validation["ok"])
        and metrics["personal_reference_resolution_rate"] == 1.0
        and metrics["stale_label_correction_success_rate"] == 1.0
        and metrics["unsupported_visual_claim_rate"] == 0.0
        and metrics["hidden_durable_write_count"] == 0
    )
    if source_open_replay:
        ok = (
            ok
            and metrics["conversational_media_replay_case_count"] == len(SOURCE_OPEN_REPLAY_CASES)
            and metrics["conversation_turn_source_open_rate"] == 1.0
            and metrics["attached_media_source_open_rate"] == 1.0
            and metrics["text_hint_as_visual_proof_violation_count"] == 0
            and metrics["raw_media_bytes_public_reported_count"] == 0
            and metrics["absolute_path_leak_count"] == 0
            and not metrics["live_product_lift_claimed"]
        )
    else:
        ok = (
            ok
            and metrics["visual_source_reopen_rate"] == 1.0
            and metrics["text_hint_leakage_rate"] == 0.0
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_conversational_media_ingest_recall_benchmark",
        "generated_at": now_utc(),
        "status": "fixture_contract_scored" if validation["ok"] else "invalid_fixture",
        "ok": ok,
        "config": {
            "fixture": "benchmark_corpus/conversational_media_ingest/fixture.json",
            "fixture_sha1": sha1_text(json.dumps(fixture, sort_keys=True))[:16],
            "live_provider": False,
            "source_open_replay": source_open_replay,
            "hidden_durable_writes_allowed": False,
            "raw_fixture_text_emitted": False,
        },
        "fixture_validation": validation,
        "corpus": {
            "fixture_id": fixture.get("fixture_id"),
            "fixture_license": fixture.get("fixture_license"),
            "conversation_count": validation["conversation_count"],
            "media_anchor_count": validation["media_anchor_count"],
            "case_count": validation["case_count"],
            "consent_boundary": validation["consent_boundary"],
        },
        "metrics": metrics,
        "rate_estimates": rate_estimates,
        "control_arms": _control_arms(cases),
        "cases": cases,
        "source_open_replay_cases": source_open_replay_cases,
        "privacy_boundary": {
            "fixture_public_safe": True,
            "task_scoped_user_provided_media_only": True,
            "background_scanning_allowed": False,
            "cross_domain_reuse_allowed": False,
            "hidden_durable_write_performed": False,
            "raw_transcript_text_emitted": False,
            "raw_media_text_emitted": False,
            "raw_media_bytes_emitted": False,
            "absolute_paths_emitted": False,
            "output_shape": "sanitized_ids_hashes_anchors_and_metrics",
        },
        "cannot_claim": sorted(
            {
                "atm_bench_hard_score",
                "atm_style_staged_corpus_retrieval",
                "background_photo_library_scanning",
                "cross_domain_media_reuse",
                "durable_memory_write_policy_quality",
                "face_recognition_identity_graph",
                "live_vision_model_quality",
                "media_only_personal_identity_resolution",
                "product_privacy_behavior",
                "text_hint_as_visual_proof",
            }
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: Mapping[str, Any]) -> None:
    metrics = _as_mapping(payload.get("metrics"))
    print("AIppocampus conversational media-ingest recall benchmark")
    print(f"- status: {payload.get('status')} ok: {payload.get('ok')}")
    print(
        "- personal refs: {personal:.2%} visual reopen: {visual:.2%} "
        "stale correction: {stale:.2%}".format(
            personal=float(metrics.get("personal_reference_resolution_rate") or 0.0),
            visual=float(metrics.get("visual_source_reopen_rate") or 0.0),
            stale=float(metrics.get("stale_label_correction_success_rate") or 0.0),
        )
    )
    print(
        "- text leakage: {leak:.2%} unsupported visual: {unsupported:.2%} hidden writes: {writes}".format(
            leak=float(metrics.get("text_hint_leakage_rate") or 0.0),
            unsupported=float(metrics.get("unsupported_visual_claim_rate") or 0.0),
            writes=int(metrics.get("hidden_durable_write_count") or 0),
        )
    )
    if metrics.get("conversational_media_replay_case_count") is not None:
        print(
            "- source-open replay cases: {cases} provider blockers: {blockers}".format(
                cases=int(metrics.get("conversational_media_replay_case_count") or 0),
                blockers=int(metrics.get("provider_unavailable_blocker_count") or 0),
            )
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--source-open-replay",
        action="store_true",
        help="Include the public-safe source-open replay cohort for upload/selection flows.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        fixture_path=args.fixture,
        source_open_replay=args.source_open_replay,
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
