#!/usr/bin/env python3
"""Confirmation artifact contract for borderline question-link pairs.

The model or live reviewer may only accept or reject an already source-backed
candidate pair. This helper keeps artifact parsing/auditing separate from the
question-link scorer so future live calibration cannot quietly weaken the
source-ref boundary.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from aippocampus_runtime.core import compact_text, now_utc

DEFAULT_CONFIRMATION_MAX_AGE_DAYS = 14
DEFAULT_CONFIRMATION_REQUESTS_NAME = "question_pair_confirmation_requests.jsonl"
DEFAULT_CONFIRMATION_ARTIFACTS_NAME = "question_pair_confirmation_artifacts.jsonl"
CONFIRMATION_ACCEPT_DECISIONS = {"accept", "same", "link", "confirmed"}
CONFIRMATION_REJECT_DECISIONS = {"reject", "deny", "different", "separate", "dismiss"}

ConfirmationFn = Callable[[dict[str, Any]], Mapping[str, Any] | None]


def default_confirmation_requests_path(jobs_output_path: Path) -> Path:
    return jobs_output_path.resolve().parent / DEFAULT_CONFIRMATION_REQUESTS_NAME


def default_confirmation_artifacts_path(jobs_output_path: Path) -> Path:
    return jobs_output_path.resolve().parent / DEFAULT_CONFIRMATION_ARTIFACTS_NAME


def iter_confirmation_jsonl(path: Path) -> Iterable[dict[str, Any]]:
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


def confirmation_pair_key(source_finding_ids: Iterable[str]) -> str:
    ids = sorted(str(value) for value in source_finding_ids)
    if len(ids) != 2:
        raise ValueError("confirmation pair key requires exactly two source finding ids")
    first, second = ids
    raw = "\n".join([first, second])
    return f"qp_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:18]}"


def parse_confirmation_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_confirmation_decisions(path: Path | None) -> ConfirmationFn | None:
    if path is None:
        return None
    by_pair: dict[str, dict[str, Any]] = {}
    for row in iter_confirmation_jsonl(path):
        key = str(row.get("pair_id") or "").strip()
        if not key:
            ids = [str(value) for value in row.get("source_finding_ids") or [] if str(value)]
            if len(ids) == 2:
                key = confirmation_pair_key(ids)
        if key:
            by_pair[key] = row

    def confirm(payload: dict[str, Any]) -> Mapping[str, Any] | None:
        return by_pair.get(str(payload.get("pair_id") or ""))

    return confirm


def question_for_confirmation(candidate: Any) -> dict[str, Any]:
    return {
        "question_id": candidate.question_id,
        "source_finding_id": candidate.finding_id,
        "question_text": candidate.question_text,
        "question_short": candidate.question_short,
        "intent_orientation": candidate.intent_orientation,
        "what_features": list(candidate.what_features),
        "where_context": list(candidate.where_context),
        "phase_context": candidate.phase_context,
        "collaboration_context": list(candidate.collaboration_context),
        "salience": {
            "score": candidate.salience.score,
            "tags": list(candidate.salience.tags),
            "trackable": candidate.salience.trackable,
        },
        "source_ref_count": len(candidate.source_refs),
        "source_thread_count": len(
            {ref.get("thread_key") for ref in candidate.source_refs if ref.get("thread_key")}
        ),
    }


def borderline_confirmation_request(
    left: Any,
    right: Any,
    score: float,
    threshold_policy: Mapping[str, Any],
    *,
    pair_id: str,
    schema_version: int,
) -> dict[str, Any]:
    """Return the only payload a live/model confirmer should see.

    The request includes compact extracted question fields and stable source
    finding ids, but not clean-source messages or full source refs. Future live
    adapters should preserve this boundary instead of reopening full history
    inside the confirmation step.
    """

    return {
        "schema_version": schema_version,
        "kind": "question_pair_confirmation_request",
        "pair_id": pair_id,
        "score": score,
        "source_finding_ids": [left.finding_id, right.finding_id],
        "question_ids": [left.question_id, right.question_id],
        "threshold_policy": dict(threshold_policy),
        "left": question_for_confirmation(left),
        "right": question_for_confirmation(right),
        "privacy_contract": {
            "full_history_included": False,
            "raw_clean_source_text_included": False,
            "source_refs_included": False,
            "model_may_only_accept_or_reject_source_backed_pair": True,
        },
    }


def existing_confirmation_request_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for row in iter_confirmation_jsonl(path):
        if str(row.get("kind") or "") != "question_pair_confirmation_request":
            continue
        pair = str(row.get("pair_id") or "")
        if pair:
            ids.add(pair)
    return ids


def append_confirmation_requests(path: Path, requests: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = existing_confirmation_request_ids(path)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for request in requests:
            pair = str(request.get("pair_id") or "")
            if not pair or pair in existing:
                continue
            payload = dict(request)
            payload["created_at"] = now_utc()
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            existing.add(pair)
            count += 1
    return count


def existing_confirmation_artifact_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for row in iter_confirmation_jsonl(path):
        pair = str(row.get("pair_id") or "")
        if pair:
            ids.add(pair)
    return ids


def append_confirmation_artifacts(path: Path, artifacts: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = existing_confirmation_artifact_ids(path)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for artifact in artifacts:
            pair = str(artifact.get("pair_id") or "")
            if not pair or pair in existing:
                continue
            fh.write(json.dumps(dict(artifact), ensure_ascii=False) + "\n")
            existing.add(pair)
            count += 1
    return count


def confirmation_artifact_audit(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return compact metadata proving which artifact affected a pair decision.

    The audit block intentionally excludes source refs and raw question text.
    Tracking already owns the original source-backed request; this block only
    lets a reviewer trace the model/reviewer artifact that accepted, rejected,
    or invalidated that borderline pair.
    """

    source_ids = [
        str(value)
        for value in raw.get("source_finding_ids") or []
        if str(value)
    ][:2]
    audit: dict[str, Any] = {
        "artifact_kind": compact_text(str(raw.get("artifact_kind") or raw.get("kind") or ""), 80),
        "pair_id": compact_text(str(raw.get("pair_id") or ""), 80),
        "source_finding_ids": source_ids,
        "source": compact_text(str(raw.get("source") or ""), 120),
        "prompt_version": compact_text(str(raw.get("prompt_version") or ""), 120),
        "created_at": compact_text(str(raw.get("created_at") or ""), 80),
        "model": compact_text(str(raw.get("model") or raw.get("source") or "external"), 120),
        "decision": compact_text(str(raw.get("decision") or raw.get("action") or ""), 40),
    }
    if "confidence" in raw:
        try:
            audit["confidence"] = round(float(raw.get("confidence") or 0.0), 4)
        except (TypeError, ValueError):
            audit["confidence"] = compact_text(str(raw.get("confidence") or ""), 40)
    return {
        key: value
        for key, value in audit.items()
        if value is not None and value != "" and value != [] and value != ()
    }


def confirmation_invalid(
    raw: Mapping[str, Any], reason: str, *, confidence: float | None = None
) -> dict[str, Any]:
    payload = {
        "decision": "invalid",
        "valid": False,
        "invalid_reason": reason,
        "confidence": round(float(confidence or 0.0), 4),
        "model": compact_text(str(raw.get("model") or raw.get("source") or "external"), 120),
        "rationale": compact_text(str(raw.get("rationale") or raw.get("reason") or ""), 260),
    }
    audit = confirmation_artifact_audit(raw)
    if audit:
        payload["artifact_audit"] = audit
    return payload


def confirmation_is_stale(
    raw: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_CONFIRMATION_MAX_AGE_DAYS,
) -> bool:
    now = now or datetime.now(timezone.utc)
    expires_at = parse_confirmation_timestamp(str(raw.get("expires_at") or ""))
    if expires_at and expires_at <= now:
        return True
    created_at = parse_confirmation_timestamp(str(raw.get("created_at") or ""))
    if not created_at or max_age_days <= 0:
        return False
    return (now - created_at).days > max_age_days


def normalize_confirmation(
    raw: Mapping[str, Any] | None,
    *,
    payload: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if not raw:
        return None
    decision = str(raw.get("decision") or raw.get("action") or "").strip().casefold()
    if decision not in CONFIRMATION_ACCEPT_DECISIONS | CONFIRMATION_REJECT_DECISIONS:
        return confirmation_invalid(raw, "unsupported_decision")
    expected_ids = {
        str(value)
        for value in ((payload or {}).get("source_finding_ids") or [])
        if str(value)
    }
    artifact_ids = {
        str(value) for value in (raw.get("source_finding_ids") or []) if str(value)
    }
    if expected_ids and artifact_ids and expected_ids != artifact_ids:
        return confirmation_invalid(raw, "source_finding_id_mismatch")
    if confirmation_is_stale(raw, now=now):
        return confirmation_invalid(raw, "stale_artifact")
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0.0)))
    except (TypeError, ValueError):
        return confirmation_invalid(raw, "malformed_confidence")
    if confidence < 0.45:
        return confirmation_invalid(raw, "low_confidence", confidence=confidence)
    normalized_decision = "accept" if decision in CONFIRMATION_ACCEPT_DECISIONS else "reject"
    link_type = str(raw.get("link_type") or "related").strip()
    if link_type not in {"recurring", "evolving", "parent_of", "child_of", "related"}:
        link_type = "related"
    return {
        "decision": normalized_decision,
        "valid": True,
        "link_type": link_type,
        "confidence": round(confidence, 4),
        "model": compact_text(str(raw.get("model") or raw.get("source") or "external"), 120),
        "rationale": compact_text(str(raw.get("rationale") or raw.get("reason") or ""), 260),
        "artifact_audit": confirmation_artifact_audit(raw),
    }


def confirmation_diagnostics(pair_decisions: Iterable[Any]) -> dict[str, Any]:
    pairs = list(pair_decisions)
    accepted = [pair for pair in pairs if pair.decision == "accepted"]
    rejected = [pair for pair in pairs if pair.decision == "confirmation_rejected"]
    invalid = [pair for pair in pairs if pair.decision == "confirmation_invalid"]
    stale = [
        pair
        for pair in invalid
        if (pair.confirmation or {}).get("invalid_reason") == "stale_artifact"
    ]
    malformed = [
        pair
        for pair in invalid
        if (pair.confirmation or {}).get("invalid_reason")
        in {"unsupported_decision", "malformed_confidence", "low_confidence"}
    ]
    source_mismatch = [
        pair
        for pair in invalid
        if (pair.confirmation or {}).get("invalid_reason") == "source_finding_id_mismatch"
    ]
    return {
        "borderline_confirmation_accepted_pair_count": sum(
            1 for pair in accepted if pair.confirmation
        ),
        "borderline_confirmation_rejected_pair_count": len(rejected),
        "borderline_confirmation_stale_pair_count": len(stale),
        "borderline_confirmation_malformed_pair_count": len(malformed),
        "borderline_confirmation_source_mismatch_pair_count": len(source_mismatch),
        "borderline_confirmation_audit": [
            {
                "pair_id": pair.pair_id,
                "decision": pair.decision,
                "score": pair.score,
                "reason": pair.reason,
                "confirmation": pair.confirmation,
            }
            for pair in pairs
            if pair.confirmation
        ][:24],
    }
