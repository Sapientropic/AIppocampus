#!/usr/bin/env python3
"""Source-open recall cue learning on top of the semantic cue cache.

This module owns the #2860 alias-learning policy so the cache file stays a
storage/reporting owner. A learned cue is still navigation-only: source refs are
reopen handles, not evidence text.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.recall import semantic_cue_cache as cue_cache
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.source.agent_trace_admission import learning_priority_for_signal
from aippocampus_runtime.source.io_kernel import write_jsonl_dict_rows

RECALL_SOURCE_OPEN_ALIAS_SOURCE = "agent_recall_source_open"


def _safe_route_token(value: Any) -> str:
    text = cue_cache.normalize_cue(value)
    if not text:
        return "agent_recall_route"
    if cue_cache.SENSITIVE_TERM_RE.search(text) or re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", text):
        return "route_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:18]
    return compact_text(text, 160)


def recall_cue_aliases_from_query(query: str) -> list[str]:
    """Return sanitized recall cue fragments suitable for navigation aliases."""

    public_query = cue_cache.SENSITIVE_TERM_RE.sub(" ", str(query or ""))
    return cue_cache.safe_position_terms(split_query_terms([public_query]))


def promote_recall_cue_after_source_open(
    path: Path,
    *,
    query: str,
    source_refs: list[dict[str, Any]],
    route_id: str = "",
    explicit_useful: bool = False,
    confidence: float = 0.82,
) -> dict[str, Any]:
    """Learn a successful recall cue as a source-reopenable alias."""

    refs = cue_cache.merge_semantic_source_refs([], source_refs)
    aliases = recall_cue_aliases_from_query(query)
    route = _safe_route_token(route_id or RECALL_SOURCE_OPEN_ALIAS_SOURCE)
    if not refs or not aliases:
        return {"path": str(path), "updated_count": 0, "active_count": 0, "cues": []}

    now = now_utc()
    rows = cue_cache.rows_by_key(cue_cache.all_semantic_cues(path))
    prompt_id = cue_cache.prompt_hash(query)
    updated_ids: list[str] = []
    for alias in aliases:
        script = cue_cache.detect_script(alias)
        key = cue_cache.cue_key(alias, route)
        row = rows.get(key) or {
            "schema_version": cue_cache.SEMANTIC_CUE_SCHEMA_VERSION,
            "kind": cue_cache.SEMANTIC_CUE_KIND,
            "cue_id": key,
            "cue": alias,
            "route": route,
            "alias_source": RECALL_SOURCE_OPEN_ALIAS_SOURCE,
            "script": script,
            "language": cue_cache.language_hint_for_script(script),
            "status": "staging",
            "created_at": now,
            "hit_count": 0,
            "false_positive_count": 0,
            "source_open_success_count": 0,
            "explicit_useful_feedback_count": 0,
            "source_refs": [],
            "prompt_hashes": [],
        }
        row["cue"] = alias
        row["route"] = route
        row["alias_source"] = RECALL_SOURCE_OPEN_ALIAS_SOURCE
        row["script"] = script
        row["language"] = cue_cache.language_hint_for_script(script)
        row["updated_at"] = now
        row["last_seen_at"] = now
        row["last_seen_unix"] = time.time()
        row["hit_count"] = int(row.get("hit_count") or 0) + 1
        row["source_open_success_count"] = int(row.get("source_open_success_count") or 0) + 1
        if explicit_useful:
            row["explicit_useful_feedback_count"] = int(row.get("explicit_useful_feedback_count") or 0) + 1
        row["last_feedback_signal"] = "explicit_useful" if explicit_useful else "source_open"
        row["confidence"] = round(max(float(row.get("confidence") or 0.0), confidence), 4)
        row["source_refs"] = cue_cache.merge_semantic_source_refs(list(row.get("source_refs") or []), refs)
        row["prompt_hashes"] = unique_preserve(
            [str(value) for value in row.get("prompt_hashes") or []] + [prompt_id],
            limit=cue_cache.MAX_PROMPT_HASHES,
        )
        row["when_to_use"] = "successful_agent_recall_cue_after_source_open"
        row["when_not_to_use"] = "cue_text_is_navigation_not_evidence_demote_on_wrong_route"
        row["training_role"] = "positive_demo"
        row["trace_admission_level"] = "reopenable_route"
        row["source_reopen_required_before_claim"] = True
        row["cue_learning_source"] = "agent_recall_deepen_source_open"
        row["candidate_lifecycle_state"] = (
            "actionable_reopenable_route"
            if int(row.get("hit_count") or 0) >= cue_cache.MIN_PROMOTION_HITS or explicit_useful
            else "draft_candidate_staging"
        )
        row["learning_priority"] = learning_priority_for_signal(
            {
                "source_ref_count": len(row.get("source_refs") or []),
                "opened_anchor_hits": int(row.get("source_open_success_count") or 0),
                "cue_frequency": int(row.get("hit_count") or 0),
                "multilingual": script != "Latn" or len(aliases) > 1,
                "alias_like": True,
                "manual_search_reduced": explicit_useful,
            }
        )
        rows[key] = cue_cache.refresh_status(row)
        updated_ids.append(key)

    all_rows = cue_cache.sorted_rows(list(rows.values()))
    write_jsonl_dict_rows(path, [*cue_cache.non_cue_rows(path), *all_rows], sort_keys=True)
    active_count = sum(1 for row in all_rows if row.get("cue_id") in updated_ids and cue_cache.cue_is_active(row))
    return {
        "path": str(path),
        "updated_count": len(updated_ids),
        "active_count": active_count,
        "cues": [rows[key]["cue"] for key in updated_ids],
    }


def demote_recall_cue_route(
    path: Path,
    *,
    route_id: str,
    cues: list[str] | None = None,
    reason: str = "wrong_route_drag",
    preferred_route_id: str = "",
) -> dict[str, Any]:
    """Apply route-local negative feedback to learned recall cue aliases."""

    route = _safe_route_token(route_id)
    safe_reason = str(reason or "wrong_route_drag").casefold()
    if safe_reason in {"wrong_route", "wrong"}:
        safe_reason = "wrong_route_drag"
    elif safe_reason in {"dismiss", "dismissed"}:
        safe_reason = "dismissed"
    elif safe_reason in {"manual_search", "manual_search_after_route"}:
        safe_reason = "manual_search_after_route"
    elif safe_reason in {"context_suppression", "context_suppressed"}:
        safe_reason = "context_suppressed"
    elif safe_reason in {"park", "parked"}:
        safe_reason = "parked"
    wanted = {cue_cache.normalize_cue(cue).casefold() for cue in (cues or []) if cue_cache.normalize_cue(cue)}
    rows = cue_cache.rows_by_key(cue_cache.all_semantic_cues(path))
    updated = 0
    now = now_utc()
    for row in rows.values():
        if str(row.get("route") or "") != route:
            continue
        if wanted and str(row.get("cue") or "").casefold() not in wanted:
            continue
        row["false_positive_count"] = int(row.get("false_positive_count") or 0) + 1
        row["updated_at"] = now
        row["last_feedback_signal"] = safe_reason
        row["suppression_lifecycle_state"] = (
            "suppressed_hard_negative"
            if safe_reason in cue_cache.HARD_NEGATIVE_RECALL_FEEDBACK_SIGNALS
            else "parked_recheck"
            if safe_reason in cue_cache.PARKED_RECALL_FEEDBACK_SIGNALS
            else "expired_recheck"
            if safe_reason == "expired"
            else "staging_recheck"
        )
        row["preferred_route_id"] = _safe_route_token(preferred_route_id) if preferred_route_id else ""
        row["rejected_route_ids"] = unique_preserve(
            [str(value) for value in row.get("rejected_route_ids") or []] + [route],
            limit=8,
        )
        if safe_reason in cue_cache.HARD_NEGATIVE_RECALL_FEEDBACK_SIGNALS:
            row["training_role"] = "hard_negative"
            row["trace_admission_level"] = "navigation_candidate"
        row["false_positive_reasons"] = unique_preserve(
            [str(value) for value in row.get("false_positive_reasons") or []] + [compact_text(safe_reason, 120)],
            limit=cue_cache.MAX_FALSE_POSITIVE_REASONS,
        )
        cue_cache.refresh_status(row)
        updated += 1
    if updated:
        write_jsonl_dict_rows(
            path,
            [*cue_cache.non_cue_rows(path), *cue_cache.sorted_rows(list(rows.values()))],
            sort_keys=True,
        )
    return {
        "path": str(path),
        "updated_count": updated,
        "route_id": route,
        "status": "updated" if updated else "not_found",
    }
