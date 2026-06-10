#!/usr/bin/env python3
"""Retrieval-triggered reconsolidation review candidates.

Retrieval lifecycle rows say that a source-backed route was activated, opened,
or later acted on. This module consumes those rows only as review evidence:
stale, superseded, refuted, or still-current outcomes can open a staging
candidate, but they never rewrite clean source, raw rollout, or formal memory.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampus_runtime.core import compact_text, now_utc, stable_text_fingerprint
from aippocampus_runtime.reflection import reconsolidation as correction_reconsolidation
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-retrieval-lifecycle-v1"

RETRIEVAL_KIND = "retrieval_lifecycle_event"
OUTCOME_KIND = "retrieval_lifecycle_outcome_event"
RECONSOLIDATION_CANDIDATE_KIND = "retrieval_reconsolidation_candidate"

RECONSOLIDATION_OUTCOME_CATEGORIES = {
    "conflicted",
    "contradicted",
    "corrected",
    "pinned",
    "refuted",
    "stale",
    "still_current",
    "superseded",
}
CONFLICT_OUTCOME_CATEGORIES = {
    "conflicted",
    "contradicted",
    "corrected",
    "refuted",
    "stale",
    "superseded",
}
USED_OUTCOME_CATEGORIES = {"opened", "pinned", "still_current"}


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return stable_text_fingerprint(
        raw,
        namespace="retrieval-reconsolidation-id",
        prefix=prefix,
        length=length,
    )


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def append_candidate_events(path: Path, events: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for event in events:
            if event.get("kind") != RECONSOLIDATION_CANDIDATE_KIND:
                raise ValueError(
                    f"unsupported retrieval reconsolidation candidate kind: {event.get('kind')}"
                )
            fh.write(json.dumps(dict(event), ensure_ascii=False) + "\n")
            count += 1
    return count


def _latest_outcomes_by_retrieval(events: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    outcomes: dict[str, Mapping[str, Any]] = {}
    for event in sorted(events, key=lambda item: str(item.get("created_at") or "")):
        if event.get("kind") != OUTCOME_KIND:
            continue
        retrieval_id = str(event.get("retrieval_event_id") or "")
        if retrieval_id:
            outcomes[retrieval_id] = event
    return outcomes


def _outcome_to_candidate_type(category: str) -> str | None:
    if category == "superseded":
        return "supersession_candidate"
    if category in {"refuted", "contradicted"}:
        return "refuted_recall_candidate"
    if category in {"conflicted", "corrected", "stale"}:
        return "revision_candidate"
    if category in {"still_current", "pinned"}:
        return "still_current_candidate"
    return None


def _outcome_to_correction_status(category: str) -> str:
    if category == "superseded":
        return "superseded"
    if category in {"refuted", "contradicted"}:
        return "refuted"
    if category in {"still_current", "pinned"}:
        return "valid_adopted"
    return "uncertain"


def _reason_codes_for(category: str, retrieval: Mapping[str, Any]) -> list[str]:
    reason_codes = [f"retrieval_{category}_observed"]
    if category in {"conflicted", "corrected", "stale"}:
        reason_codes.append("retrieval_conflict_observed")
    if category in {"superseded", "refuted", "contradicted"}:
        reason_codes.append("stale_recall_review_required")
    if retrieval.get("source_confirmed_evidence"):
        reason_codes.append("source_reopened_before_review")
    else:
        reason_codes.append("source_reopen_required_before_truth_claim")
    return unique_preserve(reason_codes, limit=8)


def build_reconsolidation_candidate(
    retrieval: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Project a retrieval lifecycle observation into a review candidate."""

    category = str(outcome.get("outcome_category") or "")
    candidate_type = _outcome_to_candidate_type(category)
    if not candidate_type:
        return None
    source_refs = [
        dict(ref)
        for ref in [
            *(retrieval.get("source_refs") or []),
            *(outcome.get("source_refs") or []),
        ]
        if isinstance(ref, Mapping)
    ]
    if not source_refs:
        return None
    status = _outcome_to_correction_status(category)
    route = correction_reconsolidation.route_for_adjudication(status)
    retrieval_id = str(retrieval.get("event_id") or "")
    outcome_id = str(outcome.get("event_id") or "")
    summary = compact_text(
        f"{candidate_type} from {retrieval.get('route')} retrieval after {category} outcome.",
        360,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RECONSOLIDATION_CANDIDATE_KIND,
        "created_at": now_utc(),
        "prompt_version": PROMPT_VERSION,
        "candidate_id": stable_id(
            "retr_recon",
            retrieval_id,
            outcome_id,
            category,
            length=20,
        ),
        "retrieval_event_id": retrieval_id,
        "outcome_event_id": outcome_id,
        "thread_id": retrieval.get("thread_id") or outcome.get("thread_id"),
        "workspace": retrieval.get("workspace") or outcome.get("workspace"),
        "workspace_sha1": retrieval.get("workspace_sha1") or outcome.get("workspace_sha1"),
        "source_key": retrieval.get("source_key") or outcome.get("source_key"),
        "source_refs": source_refs[:12],
        "route": retrieval.get("route"),
        "action_grammar": retrieval.get("action_grammar"),
        "outcome_category": category,
        "candidate_type": candidate_type,
        "correction_adjudication_status": status,
        "correction_route": route,
        "reason_codes": _reason_codes_for(category, retrieval),
        "title": compact_text(f"Retrieval reconsolidation: {candidate_type}", 160),
        "summary": summary,
        "review_state": "staging",
        "truth_status": "reviewable_candidate_not_memory_truth",
        "status": "staging",
        "source": "deterministic_retrieval_reconsolidation",
        "append_only": True,
        "formal_memory_promoted": False,
        "source_update_performed": False,
        "clean_source_mutated": False,
        "raw_rollout_mutated": False,
        "artifact_boundary": {
            "retrieval_opens_review_window": True,
            "formal_memory": False,
            "source_truth_updated": False,
            "review_or_validation_required": True,
            "uses_correction_reconsolidation_routes": True,
        },
    }


def build_reconsolidation_candidates(
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    latest_outcomes = _latest_outcomes_by_retrieval(events)
    candidates: list[dict[str, Any]] = []
    for event in events:
        if event.get("kind") != RETRIEVAL_KIND:
            continue
        retrieval_id = str(event.get("event_id") or "")
        outcome = latest_outcomes.get(retrieval_id)
        if not outcome:
            continue
        candidate = build_reconsolidation_candidate(event, outcome)
        if candidate:
            candidates.append(candidate)
    return candidates


def reconsolidation_counts(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter(
        {
            "activated": 0,
            "used": 0,
            "ignored": 0,
            "conflicted": 0,
            "superseded": 0,
            "refuted": 0,
            "still_current": 0,
            "blocked_missing_source_refs": 0,
        }
    )
    retrievals = {
        str(event.get("event_id") or ""): event
        for event in events
        if event.get("kind") == RETRIEVAL_KIND and event.get("event_id")
    }
    counts["activated"] = len(retrievals)
    latest_outcomes = _latest_outcomes_by_retrieval(events)
    for retrieval_id, outcome in latest_outcomes.items():
        category = str(outcome.get("outcome_category") or "unclear")
        if category in USED_OUTCOME_CATEGORIES:
            counts["used"] += 1
        if category == "ignored":
            counts["ignored"] += 1
        if category in CONFLICT_OUTCOME_CATEGORIES:
            counts["conflicted"] += 1
        if category == "superseded":
            counts["superseded"] += 1
        if category in {"refuted", "contradicted"}:
            counts["refuted"] += 1
        if category in {"still_current", "pinned"}:
            counts["still_current"] += 1
        if category in RECONSOLIDATION_OUTCOME_CATEGORIES:
            retrieval = retrievals.get(retrieval_id, {})
            source_refs = [
                *(retrieval.get("source_refs") or []),
                *(outcome.get("source_refs") or []),
            ]
            if not any(isinstance(ref, Mapping) for ref in source_refs):
                counts["blocked_missing_source_refs"] += 1
    return dict(counts)


def reconsolidation_projection(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = build_reconsolidation_candidates(events)
    candidate_type_counts = Counter(str(item.get("candidate_type") or "unknown") for item in candidates)
    return {
        "ok": True,
        "kind": "aippocampus_retrieval_reconsolidation_report",
        "schema_version": SCHEMA_VERSION,
        "candidate_count": len(candidates),
        "reconsolidation_counts": reconsolidation_counts(events),
        "candidate_type_counts": dict(sorted(candidate_type_counts.items())),
        "privacy_boundary": {
            "public_projection_omits_source_refs": True,
            "public_projection_omits_raw_prompt": True,
            "public_projection_omits_source_text": True,
            "public_projection_omits_local_paths": True,
        },
        "cannot_claim": [
            "default_foreground_hook_writes",
            "automatic_memory_update",
            "retrieval_reconsolidation_does_not_update_source_truth",
            "live_semantic_adjudication_quality",
            "private_real_history_behavior_lift",
        ],
    }


def run_reconsolidation_review(
    *,
    events_path: Path,
    output_path: Path | None = None,
    no_write: bool = False,
) -> dict[str, Any]:
    events = iter_jsonl(events_path)
    candidates = build_reconsolidation_candidates(events)
    wrote_count = 0
    if output_path and not no_write and candidates:
        wrote_count = append_candidate_events(output_path, candidates)
    report = reconsolidation_projection(events)
    report.update(
        {
            "events_input": str(events_path),
            "output": str(output_path) if output_path else None,
            "no_write": no_write,
            "wrote_count": wrote_count,
            "candidates": candidates,
        }
    )
    return report
