"""Consumer for retrieval reconsolidation staging candidates.

The consumer routes reviewed candidates into bounded navigation metadata. It
does not mutate clean source, raw rollout, or formal memory; missing source refs
stay blocked until a future source reopen can adjudicate them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import stable_json_join_id
from aippocampus_runtime.reflection.retrieval_reconsolidation import (
    RECONSOLIDATION_CANDIDATE_KIND,
)

SCHEMA_VERSION = 1
KIND = "retrieval_reconsolidation_consumer_report"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_refs(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in candidate.get("source_refs") or []:
        if not isinstance(item, Mapping):
            continue
        ref = {
            str(key): item[key]
            for key in ("source_id", "message_id", "turn_ref", "issue", "url")
            if item.get(key) not in (None, "")
        }
        if ref:
            refs.append(ref)
    return refs[:12]


def _final_state(candidate: Mapping[str, Any]) -> str:
    refs = _source_refs(candidate)
    if not refs:
        return "needs_source_reopen"
    ctype = _text(candidate.get("candidate_type"))
    outcome = _text(candidate.get("outcome_category"))
    review = _text(candidate.get("review_state") or "reviewed")
    if review in {"blocked", "rejected"}:
        return "blocked"
    if ctype in {"supersession_candidate", "refuted_recall_candidate"} or outcome in {
        "superseded",
        "refuted",
        "contradicted",
    }:
        return "superseded"
    if outcome == "conflicted":
        return "blocked"
    if ctype in {"revision_candidate"} or outcome in {"corrected", "stale"}:
        return "needs_source_reopen"
    if ctype == "still_current_candidate" or outcome in {"still_current", "pinned"}:
        return "routed"
    return "blocked"


def consume_retrieval_reconsolidation_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for candidate in candidates:
        if not isinstance(candidate, Mapping) or candidate.get("kind") != RECONSOLIDATION_CANDIDATE_KIND:
            continue
        final_state = _final_state(candidate)
        counts[final_state] += 1
        refs = _source_refs(candidate)
        route_id = _text(candidate.get("route") or candidate.get("source_key") or candidate.get("candidate_id"))
        row = {
            "kind": "retrieval_reconsolidation_navigation_metadata",
            "schema_version": SCHEMA_VERSION,
            "metadata_id": stable_json_join_id(
                "retr_nav",
                candidate.get("candidate_id"),
                final_state,
                ensure_ascii=False,
                default_str=False,
            ),
            "candidate_id": _text(candidate.get("candidate_id")),
            "review_state": "reviewed",
            "final_state": final_state,
            "route_id": route_id,
            "route": route_id,
            "candidate_type": _text(candidate.get("candidate_type")),
            "outcome_category": _text(candidate.get("outcome_category")),
            "source_refs": refs,
            "source_reopen_required": final_state in {"needs_source_reopen", "superseded"},
            "foreground_eligible": final_state == "routed",
            "rank_eligible": final_state == "routed",
            "authority_level": "direction_only",
            "claim_permission": "none",
            "fact_claim_allowed": False,
            "clean_source_mutated": False,
            "raw_rollout_mutated": False,
            "formal_memory_promoted": False,
            "reason_codes": [
                f"retrieval_reconsolidation_{final_state}",
                "source_reopen_required_before_claim",
            ],
        }
        if final_state in {"blocked", "needs_source_reopen"}:
            row["rank_eligible"] = False
        rows.append(row)
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "input_candidate_count": len([item for item in candidates if isinstance(item, Mapping)]),
        "metadata_count": len(rows),
        "counts_by_final_state": dict(sorted(counts.items())),
        "navigation_metadata": rows,
        "clean_source_mutated": False,
        "raw_rollout_mutated": False,
        "formal_memory_promoted": False,
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "source_text_serialized": False,
            "local_paths_serialized": False,
        },
        "cannot_claim": [
            "retrieval_consumer_updates_source_truth",
            "missing_source_candidate_ranks_foreground",
            "reviewed_candidate_is_fact_without_source_reopen",
        ],
    }


__all__ = ["consume_retrieval_reconsolidation_candidates"]
