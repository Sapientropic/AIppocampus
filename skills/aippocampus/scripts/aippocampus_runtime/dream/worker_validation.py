"""Retrospective source-evidence validation for prospective dream findings."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aippocampus_runtime.dream import worker
from aippocampus_runtime.dream.source_refs import has_source_refs


def prospective_finding_id(finding: Mapping[str, Any]) -> str:
    return str(finding.get("dream_finding_id") or finding.get("fingerprint") or finding.get("id") or "")


def validation_targets(row: Mapping[str, Any]) -> set[str]:
    raw: list[object] = [
        row.get("target_finding_id"),
        row.get("target_fingerprint"),
        row.get("prospective_finding_id"),
    ]
    for key in ("target_finding_ids", "source_finding_ids"):
        value = row.get(key)
        if isinstance(value, list):
            raw.extend(value)
    return {str(item) for item in raw if item not in {None, ""}}


def validation_status_from_row(row: Mapping[str, Any]) -> str:
    raw = str(
        row.get("validation_status")
        or row.get("prospective_validation_status")
        or row.get("retrospective_status")
        or ""
    ).casefold()
    if raw in {"supported", "support", "confirmed", "later_supported"}:
        return "supported"
    if raw in {"adopted", "used", "delivered", "accepted"}:
        return "adopted"
    if raw in {"ignored", "dismissed", "rejected", "not_used"}:
        return "ignored"
    if raw in {"refuted", "refute", "contradicted", "later_refuted"}:
        return "refuted"
    if raw in {"stale", "expired", "superseded"}:
        return "stale"
    return ""


def explicit_validation_evidence(later_rows: list[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    evidence: dict[str, dict[str, int]] = {}
    for row in later_rows:
        if not isinstance(row, Mapping):
            continue
        status = validation_status_from_row(row)
        targets = validation_targets(row)
        if status not in {"supported", "adopted", "ignored", "refuted", "stale"} or not targets or not has_source_refs(row):
            continue
        for target in targets:
            bucket = evidence.setdefault(
                target,
                {
                    "supported": 0,
                    "adopted": 0,
                    "ignored": 0,
                    "refuted": 0,
                    "stale": 0,
                    "source_ref_count": 0,
                },
            )
            bucket[status] += 1
            bucket["source_ref_count"] += len(row.get("source_refs") or [])
    return evidence


def retrospective_validate_prospective_findings(
    findings: list[Mapping[str, Any]],
    later_rows: list[Mapping[str, Any]],
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Bucket prospective hypotheses against explicit later source evidence.

    Similar terms are deliberately ignored. Retrospective support/refutation
    requires a later row that names the prospective finding id and carries clean
    source refs; otherwise the result stays unknown or stale after expiry.
    """

    now_dt = worker.normalize_now(now)
    evidence = explicit_validation_evidence(later_rows)
    items: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        if finding.get("finding_kind") != worker.FINDING_KIND or finding.get("dream_function") != "prospective":
            continue
        finding_id = prospective_finding_id(finding)
        if not finding_id:
            continue
        bucket = evidence.get(finding_id, {})
        expires_at = worker.parse_utc(str(finding.get("expires_at") or ""))
        is_invitation = isinstance(finding.get("prospective_invitation"), Mapping)
        if int(bucket.get("refuted") or 0) > 0:
            status = "refuted"
        elif int(bucket.get("adopted") or 0) > 0:
            status = "adopted"
        elif int(bucket.get("ignored") or 0) > 0:
            status = "ignored"
        elif int(bucket.get("stale") or 0) > 0:
            status = "stale"
        elif int(bucket.get("supported") or 0) > 0:
            status = "supported"
        elif expires_at and expires_at <= now_dt:
            status = "stale"
        elif is_invitation:
            status = "still_unknown"
        else:
            status = "unknown"
        items.append(
            {
                "finding_id": finding_id,
                "validation_status": status,
                "evidence_ref_count": int(bucket.get("source_ref_count") or 0),
                "expires_at": finding.get("expires_at"),
            }
        )
    counts = {key: count for key, count in sorted(Counter(item["validation_status"] for item in items).items())}
    return {
        "schema_version": worker.SCHEMA_VERSION,
        "kind": "aippocampus_prospective_retrospective_validation",
        "created_at": worker.format_utc(now_dt),
        "items": items,
        "counts": counts,
        "policy": {
            "term_overlap_alone_counts_as_evidence": False,
            "requires_explicit_target_finding_id": True,
            "requires_source_handles": True,
            "public_output_omits_source_handles": True,
        },
    }
