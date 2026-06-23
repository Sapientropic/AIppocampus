"""Quality diagnostics for subconscious review runs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from aippocampus_runtime.subconscious.job_validation import quality_score_contract


def quality_bucket_for_finding(finding: dict[str, Any]) -> str:
    raw_quality = finding.get("quality")
    quality = raw_quality if isinstance(raw_quality, dict) else {}
    bucket = str(quality.get("bucket") or "unknown")
    if bucket not in {"strong", "usable", "weak", "noise"}:
        return "unknown"
    return bucket


def ordered_nonzero_counts(counts: dict[str, int]) -> dict[str, int]:
    ordered: dict[str, int] = {}
    for key in ("strong", "usable", "weak", "noise", "unknown"):
        value = int(counts.get(key) or 0)
        if value:
            ordered[key] = value
    return ordered


def review_quality_diagnostics(
    findings: list[dict[str, Any]], review: dict[str, Any] | None = None
) -> dict[str, Any]:
    bucket_counts: dict[str, int] = defaultdict(int)
    bucket_by_id: dict[str, str] = {}
    outcomes: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "input_findings": 0,
            "promotion_candidate_source": 0,
            "weak_finding": 0,
            "duplicate_canonical": 0,
            "duplicate_duplicate": 0,
        }
    )
    for finding in findings:
        bucket = quality_bucket_for_finding(finding)
        bucket_counts[bucket] += 1
        outcomes[bucket]["input_findings"] += 1
        finding_id = str(finding.get("fingerprint") or "")
        if finding_id:
            bucket_by_id[finding_id] = bucket

    if review:
        for candidate in review.get("promotion_candidates") or []:
            for finding_id in candidate.get("source_finding_ids") or []:
                bucket = bucket_by_id.get(str(finding_id), "unknown")
                outcomes[bucket]["promotion_candidate_source"] += 1
        for weak in review.get("weak_findings") or []:
            bucket = bucket_by_id.get(str(weak.get("finding_id") or ""), "unknown")
            outcomes[bucket]["weak_finding"] += 1
        for group in review.get("duplicate_groups") or []:
            canonical = str(group.get("canonical_finding_id") or "")
            if canonical:
                outcomes[bucket_by_id.get(canonical, "unknown")]["duplicate_canonical"] += 1
            for finding_id in group.get("duplicate_finding_ids") or []:
                outcomes[bucket_by_id.get(str(finding_id), "unknown")][
                    "duplicate_duplicate"
                ] += 1

    return {
        "score_contract": quality_score_contract(),
        "bucket_distribution": ordered_nonzero_counts(bucket_counts),
        "review_outcomes_by_bucket": {
            bucket: {name: count for name, count in counts.items() if count}
            for bucket, counts in outcomes.items()
            if any(counts.values())
        },
        "interpretation": (
            "Bucket outcomes are audit diagnostics for heuristic score behavior; "
            "they are not calibration proof."
        ),
    }
