"""Semantic candidate effectiveness ledger.

This module projects existing public-safe route feedback onto semantic
candidate ids. It is a report-only reducer: it can recommend bounded routing
promotion/demotion inside the same scope bucket, but it never mutates clean
source, runtime weights, or claim permission.
"""

# aippocampus-instruction-surface: semantic effectiveness ledger owner; feedback
# adjusts navigation pressure only, never source truth.

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.feedback.vocabulary import (
    feedback_signal_is_negative,
    feedback_signal_is_positive,
    normalize_feedback_signal,
)
from aippocampus_runtime.source.io_kernel import append_jsonl_dict_rows, load_jsonl_dict_rows

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_semantic_candidate_effectiveness_report"
ROW_KIND = "aippocampus_semantic_candidate_effectiveness"
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


def _public_refs(value: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    raw: Sequence[Any]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw = value
    else:
        raw = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        clean = {
            str(key): item.get(key)
            for key in (
                "source_id",
                "source_ref",
                "thread_key",
                "message_id",
                "turn_id",
                "turn_index",
                "event_id",
                "line",
            )
            if item.get(key) not in (None, "", [])
        }
        if clean and clean not in refs:
            refs.append(clean)
        if len(refs) >= limit:
            break
    return refs


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
    return normalize_feedback_signal(row.get("outcome") or row.get("signal"), default="")


def _bounded_delta(counts: Counter[str], event_count: int) -> tuple[float, bool, bool]:
    positive = sum(count for outcome, count in counts.items() if feedback_signal_is_positive(outcome))
    negative = sum(count for outcome, count in counts.items() if feedback_signal_is_negative(outcome))
    sparse = event_count < 2
    raw = positive - negative
    conflicting = positive > 0 and negative > 0 and raw == 0
    if sparse or conflicting:
        return 0.0, sparse, conflicting
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
            "producer_kind": _candidate_kind(candidate),
            "scope_bucket": bucket,
            "source_ref_count": len(_refs(candidate.get("source_refs"))),
            "source_refs": _public_refs(candidate.get("source_refs")),
            "surface_count": surface_count,
            "last_surfaced_at": _text(candidate.get("last_surfaced_at") or candidate.get("created_at")),
            "surface_event_refs": _public_refs(
                [
                    ref
                    for event in events
                    for ref in _refs(event.get("event_refs") or event.get("surface_event_refs"))
                    if _event_outcome(event) in SURFACE_OUTCOMES
                ]
            ),
            "outcome_event_refs": _public_refs(
                [
                    ref
                    for event in events
                    for ref in _refs(event.get("event_refs") or event.get("outcome_event_refs"))
                    if _event_outcome(event) not in SURFACE_OUTCOMES
                ]
            ),
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


def semantic_effectiveness_rows_from_candidates_and_feedback(
    candidates: Iterable[Mapping[str, Any]],
    feedback_events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return durable append-only semantic effectiveness rows.

    The rows are the same bounded reducer output used by diagnostics, but this
    helper names the durable ledger path explicitly so callers do not have to
    treat a report object as storage.
    """

    return list(semantic_candidate_effectiveness_report(candidates, feedback_events)["rows"])


def append_semantic_effectiveness_rows(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
) -> int:
    prepared: list[Mapping[str, Any]] = []
    for row in rows:
        if row.get("kind") != ROW_KIND:
            raise ValueError(f"unsupported semantic effectiveness row kind: {row.get('kind')}")
        prepared.append(row)
    return append_jsonl_dict_rows(path, prepared, sort_keys=True)


def load_semantic_effectiveness_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [dict(item) for item in load_jsonl_dict_rows(path).rows if item.get("kind") == ROW_KIND]


def _ledger_row_outcome_counts(row: Mapping[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    raw_counts = row.get("outcome_counts")
    if isinstance(raw_counts, Mapping):
        for outcome, raw_count in raw_counts.items():
            try:
                count = int(raw_count or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                counts[str(outcome)] += count
    if counts:
        return counts
    recommendation = str(row.get("recommendation") or "")
    if recommendation == "promote_for_routing":
        counts["source_reopen_success"] += 2
    elif recommendation in {"demote", "archive", "scope_local_only_no_public_promotion"}:
        counts["wrong_route_drag"] += 2
    return counts


def _aggregate_semantic_effectiveness_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    bucket: str,
) -> dict[str, Any]:
    """Apply append-only semantic feedback as cumulative same-scope pressure.

    Semantic effectiveness rows are durable observations. The routing consumer
    must not treat them as a latest-state table, because a later positive batch
    would erase earlier wrong-route drag exactly where candidate priority is
    decided. A later net-positive history can still recover the candidate.
    """

    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(_ledger_row_outcome_counts(row))
    event_count = sum(counts.values())
    delta, sparse, conflicting = _bounded_delta(counts, event_count)
    recommendation = _recommendation(
        delta,
        counts,
        sparse=sparse,
        conflicting=conflicting,
        bucket=bucket,
    )
    return {
        "recommendation": recommendation,
        "bounded_route_delta": delta,
        "outcome_counts": dict(sorted(counts.items())),
        "ledger_row_count": len(rows),
        "event_count": event_count,
        "sparse_feedback_fallback": sparse,
        "conflicting_feedback_fallback": conflicting,
        "aggregate_policy": "bounded_cumulative_same_scope_feedback",
    }


def apply_semantic_effectiveness_to_candidates(
    candidates: Iterable[Mapping[str, Any]],
    ledger_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Apply same-scope semantic feedback before a candidate is surfaced.

    This changes only navigation pressure/status. It deliberately does not
    mutate source refs, clean source, or claim permission; cross-scope rows are
    ignored so a private/project correction cannot become a global mask.
    """

    rows_by_candidate: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        if not isinstance(row, Mapping) or row.get("kind") != ROW_KIND:
            continue
        candidate_id = _event_candidate_id(row)
        bucket = _bucket(row.get("scope_bucket") or row.get("privacy_partition"))
        if candidate_id:
            rows_by_candidate[(bucket, candidate_id)].append(row)
    aggregates = {
        key: _aggregate_semantic_effectiveness_rows(rows, bucket=key[0])
        for key, rows in rows_by_candidate.items()
    }

    projected: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        copy = dict(candidate)
        candidate_id = _candidate_id(copy)
        bucket = _bucket(copy.get("scope_bucket") or copy.get("privacy_partition"))
        row = aggregates.get((bucket, candidate_id))
        if not row:
            projected.append(copy)
            continue
        recommendation = str(row.get("recommendation") or "")
        copy["effectiveness_recommendation"] = recommendation
        copy["effectiveness_bounded_route_delta"] = row.get("bounded_route_delta")
        copy["effectiveness_scope_bucket"] = bucket
        copy["navigation_priority_delta"] = row.get("bounded_route_delta")
        copy["semantic_effectiveness_applied"] = True
        copy["semantic_effectiveness_ledger_row_count"] = row.get("ledger_row_count")
        copy["semantic_effectiveness_event_count"] = row.get("event_count")
        copy["semantic_effectiveness_aggregate_policy"] = row.get("aggregate_policy")
        if recommendation in {"demote", "archive", "scope_local_only_no_public_promotion"}:
            copy["status"] = "demoted" if recommendation == "demote" else "blocked"
            copy["freshness"] = "stale" if recommendation in {"demote", "archive"} else copy.get("freshness")
        elif recommendation == "promote_for_routing":
            copy["status"] = copy.get("status") or "accepted"
            copy["routing_promotion"] = "same_scope_effectiveness"
        projected.append(copy)
    return projected
