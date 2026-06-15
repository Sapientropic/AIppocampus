"""Semantic candidate effectiveness ledger.

This module projects existing public-safe route feedback onto semantic
candidate ids. It is a report-only reducer: it can recommend bounded routing
promotion/demotion inside the same scope bucket, but it never mutates clean
source, runtime weights, or claim permission.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_semantic_candidate_effectiveness_report"
ROW_KIND = "aippocampus_semantic_candidate_effectiveness"
POSITIVE_OUTCOMES = {"source_reopen_success", "reopened_deepened", "user_confirmed"}
NEGATIVE_OUTCOMES = {"ignored", "wrong_route_drag", "blocked", "superseded", "expired", "corrected"}
SURFACE_OUTCOMES = {"candidate_delivered"}
PRIVATE_BUCKETS = {"private", "restricted", "personal", "user_private", "machine_private"}


def _sha1_json(value: Any, *, length: int = 16) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:length]


def _text(value: Any, default: str = "") -> str:
    text = str(value or default).strip()
    return text if text else default


def _bucket(value: Any) -> str:
    return _text(value, "public_default").casefold().replace(" ", "_")


def _refs(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in (value or []) if isinstance(item, Mapping)]


def _candidate_id(row: Mapping[str, Any]) -> str:
    explicit = _text(row.get("candidate_id") or row.get("route_id") or row.get("bridge_id"))
    if explicit:
        return explicit[:120]
    return "semcand_" + _sha1_json(
        {
            "kind": row.get("kind"),
            "scope": row.get("scope"),
            "refs": len(_refs(row.get("source_refs"))),
        },
        length=18,
    )


def _candidate_kind(row: Mapping[str, Any]) -> str:
    kind = _text(row.get("candidate_kind") or row.get("semantic_kind") or row.get("kind"), "semantic_candidate")
    if kind == "aippocampus_semantic_bridge_candidate":
        return "bridge"
    if "dream" in kind:
        return "dream_probe"
    if "aippo" in kind:
        return "aippo_clause"
    if "learning" in kind:
        return "learning_guidance"
    if "query" in kind:
        return "query_expansion"
    return kind[:80]


def _event_candidate_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("candidate_id") or row.get("route_id") or "")


def _event_outcome(row: Mapping[str, Any]) -> str:
    outcome = _text(row.get("outcome") or row.get("signal") or "")
    return "wrong_route_drag" if outcome == "wrong_route" else outcome


def _bounded_delta(counts: Counter[str], event_count: int) -> tuple[float, bool, bool]:
    positive = sum(counts[outcome] for outcome in POSITIVE_OUTCOMES)
    negative = sum(counts[outcome] for outcome in NEGATIVE_OUTCOMES)
    sparse = event_count < 2
    conflicting = positive > 0 and negative > 0
    if sparse or conflicting:
        return 0.0, sparse, conflicting
    raw = positive - negative
    return round(max(-1.0, min(1.0, raw / max(1, event_count))), 6), sparse, conflicting


def _recommendation(delta: float, counts: Counter[str], *, sparse: bool, conflicting: bool, bucket: str) -> str:
    if bucket in PRIVATE_BUCKETS:
        return "scope_local_only_no_public_promotion"
    if sparse:
        return "not_enough_evidence"
    if conflicting:
        return "conflicting_feedback_hold"
    if delta > 0:
        return "promote_for_routing"
    if delta < 0:
        return "demote"
    if counts.get("superseded") or counts.get("expired"):
        return "archive"
    return "not_enough_evidence"


def semantic_candidate_effectiveness_report(
    candidates: Iterable[Mapping[str, Any]],
    feedback_events: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate_rows = [row for row in candidates if isinstance(row, Mapping)]
    feedback_rows = [row for row in feedback_events if isinstance(row, Mapping)]
    events_by_candidate: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in feedback_rows:
        candidate_id = _event_candidate_id(event)
        if candidate_id:
            events_by_candidate[candidate_id].append(event)

    rows: list[dict[str, Any]] = []
    recommendation_counts: Counter[str] = Counter()
    for candidate in candidate_rows:
        candidate_id = _candidate_id(candidate)
        events = events_by_candidate.get(candidate_id, [])
        counts: Counter[str] = Counter(_event_outcome(event) for event in events if _event_outcome(event))
        surface_count = counts.get("candidate_delivered") or int(candidate.get("surface_count") or 0)
        event_count = sum(counts.values())
        bucket = _bucket(candidate.get("scope_bucket") or candidate.get("privacy_partition"))
        delta, sparse, conflicting = _bounded_delta(counts, event_count)
        recommendation = _recommendation(
            delta,
            counts,
            sparse=sparse,
            conflicting=conflicting,
            bucket=bucket,
        )
        recommendation_counts[recommendation] += 1
        row = {
            "kind": ROW_KIND,
            "schema_version": SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "candidate_kind": _candidate_kind(candidate),
            "scope_bucket": bucket,
            "source_ref_count": len(_refs(candidate.get("source_refs"))),
            "surface_count": surface_count,
            "last_surfaced_at": _text(candidate.get("last_surfaced_at") or candidate.get("created_at")),
            "outcome_counts": dict(sorted(counts.items())),
            "bounded_route_delta": delta,
            "recommendation": recommendation,
            "sparse_feedback_fallback": sparse,
            "conflicting_feedback_fallback": conflicting,
            "scope_bucket_preserved": True,
            "navigation_only": True,
            "source_reopen_required_before_claim": True,
            "cannot_claim": ["source_truth_from_semantic_feedback"],
        }
        rows.append(row)

    rows.sort(key=lambda row: (str(row["scope_bucket"]), str(row["candidate_kind"]), str(row["candidate_id"])))
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "candidate_count": len(rows),
        "event_count": len(feedback_rows),
        "rows": rows,
        "recommendation_counts": dict(sorted(recommendation_counts.items())),
        "policy_boundary": {
            "report_only": True,
            "runtime_weights_changed": False,
            "clean_source_mutation_allowed": False,
            "feedback_is_not_source_truth": True,
            "scope_buckets_must_not_bleed": True,
        },
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_private_source_excerpt": False,
            "stores_local_path": False,
        },
        "cannot_claim": [
            "source_truth_from_semantic_feedback",
            "cross_scope_feedback_generalization",
            "automatic_foreground_injection",
        ],
    }
