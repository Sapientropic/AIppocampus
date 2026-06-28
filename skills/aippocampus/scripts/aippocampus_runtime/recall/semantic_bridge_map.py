"""Source-backed semantic bridge candidates for query expansion.

Bridge rows connect user/query language to source-shaped route terms. They are
deliberately weaker than source aliases: a bridge can widen recall before FTS
candidate truncation, but it never becomes evidence and it must demote when
feedback says the route was wrong, stale, private, or source-free.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation.semantic_candidate_context import (
    build_semantic_candidate_context,
)
from aippocampus_runtime.recall.feedback.vocabulary import (
    feedback_signal_is_negative,
    feedback_signal_is_positive,
    normalize_feedback_signal,
)
from aippocampus_runtime.recall.query_policy import normalize_term, unique_preserve
from aippocampus_runtime.recall.semantic_effectiveness import (
    apply_semantic_effectiveness_to_candidates,
)
from aippocampus_runtime.source.io_kernel import parse_jsonl_dict_rows_text

SCHEMA_VERSION = 1
BRIDGE_KIND = "aippocampus_semantic_bridge_candidate"
AUTHORITY = "navigation_only"
CLAIM_PERMISSION = "none"
PRIVATE_BUCKETS = {"private", "restricted", "personal", "user_private", "machine_private"}
STALE_FRESHNESS = {"stale", "superseded", "refuted", "retired", "archived", "expired"}
SEMANTIC_BRIDGE_SOURCE = "semantic_bridge"


def _sha1_json(value: Any, *, length: int = 16) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:length]


def _safe_term(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    term = normalize_term(value)
    if not term or len(term) > 96:
        return ""
    if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", term):
        return ""
    if re.search(r"\b(?:sk|pk|api[_-]?key|token|secret)[-_:=][A-Za-z0-9_-]{6,}", term, re.I):
        return ""
    return term


def _terms(value: Any, *, limit: int = 16) -> list[str]:
    raw: Sequence[Any]
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw = value
    else:
        return []
    return unique_preserve([term for item in raw if (term := _safe_term(item))], limit=limit)


def _refs(value: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    raw = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        clean = {
            str(key): item.get(key)
            for key in (
                "thread_key",
                "source_id",
                "message_id",
                "turn_id",
                "turn_index",
                "line",
                "source_line",
                "event_id",
            )
            if item.get(key) not in (None, "", [])
        }
        marker = tuple(sorted((key, str(value)) for key, value in clean.items()))
        if clean and marker not in seen:
            seen.add(marker)
            refs.append(clean)
        if len(refs) >= limit:
            break
    return refs


def _bucket(value: Any) -> str:
    text = str(value or "public_default").strip().casefold().replace(" ", "_")
    text = re.sub(r"[^a-z0-9_.:#-]+", "_", text).strip("_")
    return text or "public_default"


def _candidate_id(row: Mapping[str, Any], from_terms: list[str], to_terms: list[str]) -> str:
    explicit = str(row.get("candidate_id") or row.get("bridge_id") or "").strip()
    if explicit and "\\" not in explicit and "/" not in explicit:
        return explicit[:120]
    return "sbridge_" + _sha1_json(
        {
            "from": from_terms,
            "to": to_terms,
            "scope": row.get("scope"),
            "refs": _refs(row.get("source_refs")) or _refs(row.get("event_refs")),
        },
        length=20,
    )


def _feedback_counts(feedback_rows: Iterable[Mapping[str, Any]], candidate_id: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in feedback_rows:
        route_id = str(row.get("route_id") or row.get("candidate_id") or "")
        if route_id != candidate_id:
            continue
        signal = normalize_feedback_signal(
            row.get("signal") or row.get("outcome"),
            default="",
        )
        if signal:
            counts[signal] += 1
    return counts


def reduce_semantic_bridge_candidate(
    row: Mapping[str, Any],
    *,
    feedback_rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    from_terms = _terms(row.get("from_terms") or row.get("query_aliases"), limit=16)
    to_terms = _terms(row.get("to_terms") or row.get("route_terms"), limit=24)
    aliases = _terms(row.get("route_aliases") or row.get("aliases"), limit=16)
    refs = _refs(row.get("source_refs"))
    event_refs = _refs(row.get("event_refs"))
    bucket = _bucket(row.get("scope_bucket") or row.get("privacy_partition"))
    freshness = _bucket(row.get("freshness") or "current")
    invalidators = _terms(row.get("invalidators"), limit=8)
    candidate_id = _candidate_id(row, from_terms, to_terms)
    feedback = _feedback_counts(feedback_rows or [], candidate_id)
    explicit_status = _bucket(row.get("status") or "")
    reasons: list[str] = ["semantic_bridge_navigation_only"]
    status = "accepted"

    if explicit_status in {"demoted", "retired", "blocked", "rejected", "local_only_scent"}:
        status = explicit_status
        reasons.append(f"explicit_status_{explicit_status}")
    elif not from_terms or not to_terms:
        status = "rejected"
        reasons.append("missing_from_or_to_terms")
    elif bucket in PRIVATE_BUCKETS:
        status = "blocked"
        reasons.append("privacy_bucket_blocked")
    elif freshness in STALE_FRESHNESS or invalidators:
        status = "retired"
        reasons.append("stale_or_invalidated")
    elif any(count for signal, count in feedback.items() if feedback_signal_is_negative(signal)):
        status = "demoted"
        reasons.append("negative_route_feedback")
    elif not refs and not event_refs:
        status = "local_only_scent" if bucket in {"workspace", "machine", "local_only"} else "rejected"
        reasons.append("source_free_bridge_cannot_expand_public_query")
    elif sum(count for signal, count in feedback.items() if feedback_signal_is_positive(signal)) > 0:
        reasons.append("source_reopen_success_seen")
    else:
        reasons.append("source_or_event_refs_present")

    context = build_semantic_candidate_context(
        {
            "producer": row.get("producer") or "semantic_bridge_map",
            "source_refs": refs,
            "event_refs": event_refs,
            "scope": row.get("scope") or "public_default",
            "scope_bucket": bucket,
            "topic_epoch": row.get("topic_epoch") or "topic-v1",
            "freshness": freshness,
            "invalidators": invalidators,
            "task_mode": row.get("task_mode") or "recall",
            "source_families": row.get("source_families") or ["semantic_bridge"],
            "recent_outcomes": dict(feedback),
        }
    )
    support_shape = {
        "candidate_id": candidate_id,
        "source_ref_count": len(refs),
        "event_ref_count": len(event_refs),
        "from_count": len(from_terms),
        "to_count": len(to_terms),
        "scope": row.get("scope") or "public_default",
    }
    return {
        "kind": BRIDGE_KIND,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "from_terms": from_terms,
        "to_terms": to_terms,
        "route_aliases": aliases,
        "source_refs": refs,
        "event_refs": event_refs,
        "scope": str(row.get("scope") or "public_default")[:120],
        "topic_epoch": str(row.get("topic_epoch") or "topic-v1")[:80],
        "freshness": freshness,
        "invalidators": invalidators,
        "scope_bucket": bucket,
        "authority": AUTHORITY,
        "action_grammar": "direction_with_ref" if refs else "direction_only",
        "claim_permission": CLAIM_PERMISSION,
        "status": status,
        "semantic_context_id": context["context_id"],
        "semantic_context_status": context["reducer_status"],
        "support_fingerprint": "sha1:" + _sha1_json(support_shape),
        "outcome_counts": dict(sorted(feedback.items())),
        "reason_codes": unique_preserve(reasons, limit=8),
        "source_reopen_required_before_claim": True,
        "cannot_claim": ["semantic_bridge_is_source_truth"],
    }


def reduce_semantic_bridge_candidates(
    rows: Iterable[Mapping[str, Any]],
    *,
    feedback_rows: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    feedback = list(feedback_rows or [])
    return [
        reduce_semantic_bridge_candidate(row, feedback_rows=feedback)
        for row in rows
        if isinstance(row, Mapping)
    ]


def _negative_outcome(value: Any) -> bool:
    return feedback_signal_is_negative(normalize_feedback_signal(value, default=""))


def _materialized_bridge_row(
    *,
    candidate_id: str,
    from_terms: Any,
    to_terms: Any,
    producer: str,
    source_refs: Any,
    event_refs: Any = None,
    scope: Any = None,
    scope_bucket: Any = None,
    topic_epoch: Any = None,
    freshness: Any = None,
    outcome: Any = None,
) -> dict[str, Any] | None:
    safe_from = _terms(from_terms, limit=16)
    safe_to = _terms(to_terms, limit=24)
    refs = _refs(source_refs)
    events = _refs(event_refs)
    if not safe_from or not safe_to:
        return None
    row: dict[str, Any] = {
        "kind": BRIDGE_KIND,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id
        or "sbridge_" + _sha1_json({"from": safe_from, "to": safe_to, "refs": refs or events}, length=20),
        "from_terms": safe_from,
        "to_terms": safe_to,
        "route_aliases": [],
        "producer": producer,
        "source_refs": refs,
        "event_refs": events,
        "scope": str(scope or "public_default")[:120],
        "scope_bucket": _bucket(scope_bucket or scope),
        "topic_epoch": str(topic_epoch or "topic-v1")[:80],
        "freshness": _bucket(freshness or "current"),
        "authority": AUTHORITY,
        "action_grammar": "direction_with_ref" if refs else "direction_only",
        "claim_permission": CLAIM_PERMISSION,
        "source_reopen_required_before_claim": True,
        "cannot_claim": ["semantic_bridge_is_source_truth"],
        "reason_codes": ["materialized_from_public_safe_signal", f"producer:{producer}"],
    }
    if _negative_outcome(outcome):
        row["status"] = "demoted"
        row["reason_codes"].append("negative_route_feedback")
    return row


def materialize_semantic_bridge_rows(
    *,
    feedback_rows: Iterable[Mapping[str, Any]] | None = None,
    learning_rows: Iterable[Mapping[str, Any]] | None = None,
    dream_rows: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Materialize public-safe semantic bridge rows from existing signals.

    The rows are an automatic sidecar for routing. They are intentionally weak:
    source/event refs preserve reopenability, while negative/private/stale rows
    are still demoted by the normal bridge reducer before expansion.
    """

    materialized: list[dict[str, Any]] = []
    for row in feedback_rows or []:
        if not isinstance(row, Mapping):
            continue
        bridge = _materialized_bridge_row(
            candidate_id=str(row.get("candidate_id") or row.get("route_id") or ""),
            from_terms=row.get("from_terms") or row.get("query_terms") or row.get("prompt_terms"),
            to_terms=row.get("to_terms") or row.get("reopened_terms") or row.get("corrected_terms") or row.get("route_terms"),
            producer="route_feedback",
            source_refs=row.get("source_refs") or ([{"source_id": row.get("source_id")}] if row.get("source_id") else []),
            event_refs=row.get("event_refs") or ([{"event_id": row.get("event_id")}] if row.get("event_id") else []),
            scope=row.get("scope"),
            scope_bucket=row.get("scope_bucket") or row.get("privacy_partition"),
            topic_epoch=row.get("topic_epoch"),
            freshness=row.get("freshness"),
            outcome=row.get("outcome") or row.get("signal"),
        )
        if bridge:
            materialized.append(bridge)
    for row in learning_rows or []:
        if not isinstance(row, Mapping):
            continue
        workflow = str(row.get("workflow_family") or row.get("finding_kind") or "").strip()
        bridge = _materialized_bridge_row(
            candidate_id=str(row.get("candidate_id") or row.get("finding_id") or ""),
            from_terms=row.get("from_terms") or row.get("activation_terms") or row.get("query_terms") or [workflow],
            to_terms=row.get("to_terms") or row.get("route_terms") or row.get("action_terms") or [workflow],
            producer="learning_loop",
            source_refs=row.get("source_refs"),
            event_refs=row.get("event_refs"),
            scope=row.get("scope"),
            scope_bucket=row.get("scope_bucket") or row.get("privacy_partition"),
            topic_epoch=row.get("topic_epoch"),
            freshness=row.get("freshness") or row.get("status"),
            outcome=row.get("outcome") or row.get("quality_gate"),
        )
        if bridge:
            materialized.append(bridge)
    for row in dream_rows or []:
        if not isinstance(row, Mapping):
            continue
        bridge = _materialized_bridge_row(
            candidate_id=str(row.get("candidate_id") or ""),
            from_terms=row.get("from_terms") or row.get("trigger_terms") or row.get("source_anchors"),
            to_terms=row.get("to_terms") or row.get("route_terms") or row.get("shared_topic_tokens"),
            producer="dream_topology",
            source_refs=row.get("source_refs") or [{"source_id": anchor} for anchor in _terms(row.get("source_anchors"), limit=6)],
            event_refs=row.get("event_refs"),
            scope=row.get("scope"),
            scope_bucket=row.get("scope_bucket") or row.get("privacy_partition"),
            topic_epoch=row.get("topic_epoch"),
            freshness=row.get("freshness"),
            outcome=row.get("outcome") or row.get("status"),
        )
        if bridge:
            materialized.append(bridge)
    return materialized


def load_semantic_bridge_rows(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    bridge_path = Path(path)
    if not bridge_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = bridge_path.read_text(encoding="utf-8").strip()
    except OSError:
        return []
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        return [dict(item) for item in data if isinstance(item, Mapping)]
    rows.extend(parse_jsonl_dict_rows_text(text).rows)
    return rows


def bridge_overlaps_query(query_terms: Sequence[str], bridge: Mapping[str, Any]) -> bool:
    query_low = [term.casefold() for term in _terms(query_terms, limit=64)]
    bridge_terms = _terms(
        [
            *(bridge.get("from_terms") or []),
            *(bridge.get("route_aliases") or []),
        ],
        limit=64,
    )
    for query in query_low:
        for term in bridge_terms:
            low = term.casefold()
            if query == low or query in low or low in query:
                return True
    return False


def semantic_bridge_expansion_terms(
    query_terms: Sequence[str],
    bridge_rows: Iterable[Mapping[str, Any]],
    *,
    semantic_effectiveness_rows: Iterable[Mapping[str, Any]] | None = None,
    limit: int = 64,
) -> tuple[list[str], dict[str, Any]]:
    raw_rows = [row for row in bridge_rows if isinstance(row, Mapping)]
    effective_rows = apply_semantic_effectiveness_to_candidates(
        raw_rows,
        semantic_effectiveness_rows or [],
    )
    applied = [row for row in effective_rows if row.get("semantic_effectiveness_applied")]
    demoted = [
        row
        for row in applied
        if row.get("effectiveness_recommendation") in {"demote", "archive", "scope_local_only_no_public_promotion"}
    ]
    reduced = [
        row
        for row in reduce_semantic_bridge_candidates(effective_rows)
        if row["status"] == "accepted" and bridge_overlaps_query(query_terms, row)
    ]
    terms = unique_preserve(
        [term for row in reduced for term in [*(row["to_terms"]), *(row["route_aliases"])]],
        limit=limit,
    )
    return terms, {
        "semantic_bridge_count": len(reduced),
        "semantic_bridge_fingerprints": unique_preserve(
            [row["support_fingerprint"] for row in reduced],
            limit=12,
        ),
        "semantic_bridge_reason_codes": unique_preserve(
            [reason for row in reduced for reason in row["reason_codes"]],
            limit=8,
        ),
        "semantic_effectiveness": {
            "applied_count": len(applied),
            "demoted_count": len(demoted),
            "source_reopen_required_before_claim": True,
            "feedback_is_not_source_truth": True,
        },
    }
