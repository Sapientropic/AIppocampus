#!/usr/bin/env python3
"""Concept graph participation lifecycle policy.

Lifecycle status controls graph expansion only. It is not source truth, and it
never writes back to clean source or staging JSONL.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from aippocampus_runtime.navigation.associations import normalize_term
from aippocampus_runtime.navigation.concept_kinds import concept_kind_source_boundary
from aippocampus_runtime.registry.api import unique_preserve

GRAPH_ACTIVE_STATUSES = {"verified", "staging"}
GRAPH_SUPPRESSED_STATUSES = {"parked", "retired"}
GRAPH_STATUSES = GRAPH_ACTIVE_STATUSES | GRAPH_SUPPRESSED_STATUSES
STATUS_PRIORITY = {
    "staging": 0,
    "verified": 1,
    "parked": 2,
    "retired": 3,
}
KNOWN_EDGE_TYPES = {
    "alias",
    "verified_related",
    "same_decision_space",
    "decision_about",
    "project_topic",
    "depends_on",
    "contrasts_with",
    "supersedes",
    "related",
    "co_occurs",
}


def normalize_graph_status(value: Any) -> str:
    status = str(value or "staging").strip().casefold()
    if status in {"archived", "dead_letter", "dead-letter"}:
        return "retired"
    if status in {"contradicted", "superseded", "blocked"}:
        return "retired"
    if status in GRAPH_STATUSES:
        return status
    return "staging"


def graph_status_is_active(status: str) -> bool:
    return normalize_graph_status(status) in GRAPH_ACTIVE_STATUSES


def graph_source_boundary() -> dict[str, bool]:
    boundary = concept_kind_source_boundary()
    boundary.update(
        {
            "graph_status_is_navigation_only": True,
            "graph_status_is_not_source_truth": True,
            "verified_graph_status_still_requires_source_reopen": True,
            "parked_or_retired_only_suppresses_graph_participation": True,
        }
    )
    return boundary


def source_ref_thread_keys(refs: list[dict[str, Any]]) -> list[str]:
    return unique_preserve(
        [
            str(ref.get("thread_key") or ref.get("thread") or "")
            for ref in refs
            if ref.get("thread_key") or ref.get("thread")
        ]
    )


def source_ref_identity(ref: dict[str, Any]) -> str:
    parts = [
        str(ref.get("thread_key") or ref.get("thread") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(ref.get("source_line") or ref.get("assistant_line") or ref.get("line") or ""),
        str(ref.get("ref") or ""),
    ]
    return "|".join(parts)


def unique_source_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for ref in refs:
        identity = source_ref_identity(ref)
        if identity in seen:
            continue
        seen.add(identity)
        out.append(ref)
    return out


def safe_diagnostic_hash(value: Any) -> str:
    normalized = normalize_term(str(value or "")).casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"sha256:{digest}"


def safe_edge_type(value: Any) -> str:
    edge_type = str(value or "").strip()
    if edge_type in KNOWN_EDGE_TYPES:
        return edge_type
    if not edge_type:
        return "unknown"
    return f"custom:{safe_diagnostic_hash(edge_type)}"


def lifecycle_decision(
    *,
    requested_status: Any,
    confidence: float,
    evidence_count: int,
    thread_count: int,
    lifecycle_signal: Any = None,
    source_backed: bool = False,
) -> tuple[str, str]:
    signal = str(lifecycle_signal or requested_status or "").strip().casefold()
    if signal in {"contradicted", "superseded", "contradiction"}:
        return "retired", "contradicted_or_superseded"
    if signal in {"retired", "archived", "dead_letter", "dead-letter"}:
        return "retired", "dead_letter_or_archived"
    if signal in {"stale", "stale_without_reuse"}:
        return "parked", "stale_without_reuse"
    if signal in {"low_utility", "wrong_route_drag", "low_utility_route"}:
        return "parked", "low_utility"
    if signal in {"parked", "missing_source_refs"}:
        return "parked", signal or "parked_by_input"
    if confidence < 0.45:
        return "parked", "low_confidence"
    if not source_backed:
        return "parked", "missing_source_refs"
    if evidence_count >= 3 and thread_count >= 2:
        return "verified", "repeated_cross_thread_source_refs"
    if evidence_count >= 3:
        return "verified", "repeated_source_refs"
    if thread_count >= 2:
        return "verified", "cross_thread_evidence"
    if signal in {"accepted_review", "accepted_subconscious_review", "curated"}:
        return "verified", "accepted_source_backed_review"
    return "staging", "staging_source_backed"


def choose_status(existing_status: str, incoming_status: str) -> str:
    existing = normalize_graph_status(existing_status)
    incoming = normalize_graph_status(incoming_status)
    if incoming in GRAPH_SUPPRESSED_STATUSES:
        return incoming
    return (
        incoming
        if STATUS_PRIORITY.get(incoming, 0) >= STATUS_PRIORITY.get(existing, 0)
        else existing
    )


def strongest_lifecycle_signal(values: list[Any]) -> str:
    normalized = [str(value or "").strip().casefold() for value in values]
    for signal in ("contradicted", "superseded", "retired", "archived", "dead_letter"):
        if signal in normalized:
            return signal
    for signal in ("stale_without_reuse", "stale", "low_utility", "wrong_route_drag", "parked"):
        if signal in normalized:
            return signal
    for signal in ("accepted_review", "accepted_subconscious_review", "curated"):
        if signal in normalized:
            return signal
    if "verified" in normalized:
        return "verified"
    return "staging"


def status_counts(con: sqlite3.Connection, table: str) -> dict[str, int]:
    if table not in {"concepts", "concept_edges"}:
        return {status: 0 for status in sorted(GRAPH_STATUSES)}
    rows = con.execute(
        f"SELECT status AS value, COUNT(*) AS count FROM {table} GROUP BY status"
    ).fetchall()
    counts = {status: 0 for status in sorted(GRAPH_STATUSES)}
    counts.update({str(row["value"] or "unknown"): int(row["count"] or 0) for row in rows})
    return counts


def nested_increment(root: dict[str, Any], *keys: str) -> None:
    cursor: dict[str, Any] = root
    for key in keys[:-1]:
        cursor = cursor.setdefault(key, {})
    cursor[keys[-1]] = int(cursor.get(keys[-1], 0)) + 1


def lifecycle_diagnostics(con: sqlite3.Connection) -> dict[str, Any]:
    concept_status_counts = status_counts(con, "concepts")
    edge_status_counts = status_counts(con, "concept_edges")
    reason_counts: dict[str, int] = {}
    for table in ("concepts", "concept_edges"):
        rows = con.execute(
            f"SELECT lifecycle_reason AS reason, COUNT(*) AS count FROM {table} "
            "GROUP BY lifecycle_reason"
        ).fetchall()
        for row in rows:
            reason = str(row["reason"] or "unknown")
            reason_counts[reason] = reason_counts.get(reason, 0) + int(row["count"] or 0)
    suppressed_reasons: dict[str, Any] = {}
    for row in con.execute(
        """
        SELECT edge_type, status, lifecycle_reason, COUNT(*) AS count
        FROM concept_edges
        WHERE status IN ('parked', 'retired')
        GROUP BY edge_type, status, lifecycle_reason
        """
    ).fetchall():
        edge_type = safe_edge_type(row["edge_type"] or "unknown")
        status = str(row["status"] or "unknown")
        reason = str(row["lifecycle_reason"] or "unknown")
        for _ in range(int(row["count"] or 0)):
            nested_increment(suppressed_reasons, edge_type, status, reason)
    oldest_staging_rows: list[dict[str, Any]] = []
    for row in con.execute(
        """
        SELECT 'concept' AS row_kind, label AS label, NULL AS edge_type,
               status, lifecycle_reason, hit_count AS evidence_count,
               thread_count, created_at AS first_seen_at, updated_at AS last_seen_at
        FROM concepts
        WHERE status = 'staging'
        UNION ALL
        SELECT 'edge' AS row_kind, NULL AS label, edge_type AS edge_type,
               status, lifecycle_reason, evidence_count, thread_count,
               first_seen_at, last_seen_at
        FROM concept_edges
        WHERE status = 'staging'
        ORDER BY first_seen_at ASC
        LIMIT 8
        """
    ).fetchall():
        oldest_staging_rows.append(
            {
                "row_kind": row["row_kind"],
                "label_hash": safe_diagnostic_hash(row["label"]) if row["label"] else None,
                "edge_type": safe_edge_type(row["edge_type"]) if row["edge_type"] else None,
                "status": row["status"],
                "reason": row["lifecycle_reason"],
                "evidence_count": int(row["evidence_count"] or 0),
                "thread_count": int(row["thread_count"] or 0),
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
        )
    return {
        "schema_version": "concept_graph_lifecycle_v1",
        "concept_status_counts": concept_status_counts,
        "edge_status_counts": edge_status_counts,
        "promoted_count": concept_status_counts.get("verified", 0)
        + edge_status_counts.get("verified", 0),
        "parked_count": concept_status_counts.get("parked", 0)
        + edge_status_counts.get("parked", 0),
        "retired_count": concept_status_counts.get("retired", 0)
        + edge_status_counts.get("retired", 0),
        "suppressed_edge_count": edge_status_counts.get("parked", 0)
        + edge_status_counts.get("retired", 0),
        "reason_counts": dict(sorted(reason_counts.items())),
        "suppressed_reasons": suppressed_reasons,
        "oldest_staging_rows": oldest_staging_rows,
        "source_boundary": graph_source_boundary(),
    }
