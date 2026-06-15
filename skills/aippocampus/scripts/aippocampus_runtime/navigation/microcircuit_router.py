"""Shared microcircuit routing and controlled salience decay."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1
ROUTER_KIND = "aippocampus_microcircuit_router_report"
DECAY_KIND = "aippocampus_controlled_salience_decay_report"
QUIET_STATUSES = {"stale", "superseded", "resolved", "retired", "refuted"}
NOISY_OUTCOMES = {"ignored", "dismissed", "noisy", "wrong_route_drag"}


def _stable_id(prefix: str, *parts: Any) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _terms(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        tokens: set[str] = set()
        for item in value.values():
            tokens.update(_terms(item))
        return tokens
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        tokens = set()
        for item in value:
            tokens.update(_terms(item))
        return tokens
    return {
        token
        for token in str(value or "").casefold().replace("_", " ").replace("-", " ").split()
        if len(token) > 2
    }


def _source_ids(row: Mapping[str, Any]) -> set[str]:
    refs = row.get("source_refs") or row.get("source_ids") or []
    ids: set[str] = set()
    if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
        for ref in refs:
            if isinstance(ref, Mapping):
                value = ref.get("source_id") or ref.get("source_ref") or ref.get("path")
            else:
                value = ref
            if value:
                ids.add(str(value))
    return ids


def _candidate_score(
    row: Mapping[str, Any],
    *,
    query_terms: set[str],
    allowed_source_ids: set[str],
) -> float:
    explicit = row.get("score") or row.get("match_score") or row.get("confidence_score")
    try:
        score = float(explicit) if explicit is not None else 0.0
    except (TypeError, ValueError):
        score = 0.0
    row_terms = _terms(
        [
            row.get("title"),
            row.get("summary"),
            row.get("guidance"),
            row.get("route_terms"),
            row.get("match_terms"),
        ]
    )
    if query_terms:
        score += len(query_terms & row_terms) / max(1, len(query_terms))
    source_ids = _source_ids(row)
    if allowed_source_ids and source_ids & allowed_source_ids:
        score += 0.5
    if row.get("foreground_eligible"):
        score += 0.25
    return round(score, 4)


def route_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    policy_profile: str = "recall",
    query_terms: Sequence[str] | None = None,
    source_constraints: Mapping[str, Any] | None = None,
    top_k: int = 5,
    threshold: float = 0.0,
    diversity_key: str = "cluster_id",
    gold_source_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    rows = [dict(row) for row in candidates if isinstance(row, Mapping)]
    query = {str(term).casefold() for term in query_terms or [] if str(term).strip()}
    constraints = source_constraints or {}
    allowed = {str(item) for item in constraints.get("source_ids") or [] if str(item)}
    gold = {str(item) for item in gold_source_ids or [] if str(item)}
    scored: list[dict[str, Any]] = []
    pruned: list[dict[str, Any]] = []
    for row in rows:
        source_ids = _source_ids(row)
        if allowed and not (source_ids & allowed):
            pruned.append({"candidate_id": row.get("candidate_id") or row.get("route_id"), "reason": "source_filter"})
            continue
        score = _candidate_score(row, query_terms=query, allowed_source_ids=allowed)
        if score < threshold:
            pruned.append({"candidate_id": row.get("candidate_id") or row.get("route_id"), "reason": "threshold"})
            continue
        scored.append({**row, "microcircuit_score": score})
    scored.sort(key=lambda row: (row["microcircuit_score"], str(row.get("candidate_id") or row.get("route_id") or "")), reverse=True)
    selected: list[dict[str, Any]] = []
    used_diversity: set[str] = set()
    for row in scored:
        key = str(row.get(diversity_key) or "")
        if key and key in used_diversity:
            pruned.append({"candidate_id": row.get("candidate_id") or row.get("route_id"), "reason": "diversity"})
            continue
        if key:
            used_diversity.add(key)
        if len(selected) >= top_k:
            pruned.append({"candidate_id": row.get("candidate_id") or row.get("route_id"), "reason": "top_k"})
            continue
        selected.append(row)
    pruned_counts = Counter(row["reason"] for row in pruned)
    verifier_seen_sources = set().union(*[_source_ids(row) for row in selected]) if selected else set()
    return {
        "kind": ROUTER_KIND,
        "schema_version": SCHEMA_VERSION,
        "policy_profile": policy_profile,
        "authority": "candidate_structure_only_not_source_truth",
        "selected_candidates": selected,
        "pruned_candidates": pruned,
        "diagnostics": {
            "raw_pool_size": len(rows),
            "selected_count": len(selected),
            "threshold_prune_count": pruned_counts["threshold"],
            "top_k_prune_count": pruned_counts["top_k"],
            "source_filter_prune_count": pruned_counts["source_filter"],
            "diversity_prune_count": pruned_counts["diversity"],
            "gold_source_reached_pool": bool(gold and any(gold & _source_ids(row) for row in rows)),
            "gold_source_verifier_seen": bool(gold & verifier_seen_sources),
            "verifier_seen_count": len(verifier_seen_sources),
        },
        "boundary": {
            "scores_are_candidate_routing": True,
            "source_reopen_required_before_claim": True,
        },
    }


def apply_controlled_salience_decay(
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or row.get("freshness") or "").casefold()
        outcomes = {str(item).casefold() for item in row.get("feedback_outcomes") or []}
        local_only = str(row.get("scope") or "").casefold().startswith("machine:")
        quiet = status in QUIET_STATUSES or bool(outcomes & NOISY_OUTCOMES) or local_only
        reason_codes = []
        if status in QUIET_STATUSES:
            reason_codes.append(f"{status}_quieted")
        if outcomes & NOISY_OUTCOMES:
            reason_codes.append("negative_feedback_quieted")
        if local_only:
            reason_codes.append("local_environment_lesson_decay")
        rows.append(
            {
                "candidate_id": row.get("candidate_id") or row.get("route_id") or _stable_id("candidate", row),
                "foreground_prominence": "quiet" if quiet else "normal",
                "reopenable_from_source": bool(_source_ids(row)),
                "source_deleted": False,
                "reason_codes": reason_codes or ["kept_current"],
            }
        )
    return {
        "kind": DECAY_KIND,
        "schema_version": SCHEMA_VERSION,
        "rows": rows,
        "quieted_count": sum(1 for row in rows if row["foreground_prominence"] == "quiet"),
        "source_material_preserved": True,
    }


__all__ = ["apply_controlled_salience_decay", "route_candidates"]
