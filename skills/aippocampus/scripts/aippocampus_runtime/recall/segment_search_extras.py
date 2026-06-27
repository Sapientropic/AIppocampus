"""Opt-in segment search sidecars kept out of the main search runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.feedback.outcome import (
    build_recall_outcome_event,
    write_recall_outcome_event,
)
from aippocampus_runtime.recall.query_expansion import (
    load_source_factual_alias_rows,
    plan_query_expansion,
)
from aippocampus_runtime.recall.semantic_bridge_map import load_semantic_bridge_rows
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows_strict
from aippocampus_runtime.source.source_texture import (
    SOURCE_TEXTURE_BOUNDARY,
    build_source_texture_boundary_hints,
)

SOURCE_FACTUAL_ALIASES_FILENAME = "source-factual-aliases.jsonl"
SEMANTIC_BRIDGES_FILENAME = "semantic-bridges.jsonl"
SOURCE_TEXTURE_FILENAME = "source-texture.jsonl"
TEXTURE_HINT_BOUNDARY = "texture_hint_read_model_not_source_fact"


def add_sidecar_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-aliases",
        default=None,
        help="Optional source-backed factual alias JSONL path for query expansion.",
    )
    parser.add_argument(
        "--semantic-bridges",
        default=None,
        help=(
            "Optional source-backed semantic bridge JSONL path for query expansion. "
            "Bridges are navigation-only and never count as evidence."
        ),
    )
    parser.add_argument(
        "--outcome-feedback-path",
        default=None,
        help="Opt in to local-safe recall outcome telemetry JSONL emission.",
    )
    parser.add_argument(
        "--outcome-signal",
        default=None,
        help="Outcome label to write when --outcome-feedback-path is set.",
    )
    parser.add_argument(
        "--outcome-run-id",
        default=None,
        help="Stable run id for opt-in outcome telemetry; defaults to a query hash.",
    )
    parser.add_argument(
        "--source-texture",
        default=None,
        help=(
            "Optional source-texture JSONL or derived texture-hint sidecar. "
            "Hints are read-model navigation aids only and never replace source refs."
        ),
    )


def source_factual_aliases_path(source_aliases: str | Path | None, cwd: Path) -> Path | None:
    if source_aliases:
        path = Path(source_aliases)
        return path if path.is_absolute() else cwd / path
    candidates = [
        cwd / SOURCE_FACTUAL_ALIASES_FILENAME,
        cwd / "clean-source" / SOURCE_FACTUAL_ALIASES_FILENAME,
        cwd / ".aippocampus" / "clean-source" / SOURCE_FACTUAL_ALIASES_FILENAME,
    ]
    return next((path for path in candidates if path.exists()), None)


def semantic_bridges_path(semantic_bridges: str | Path | None, cwd: Path) -> Path | None:
    if semantic_bridges:
        path = Path(semantic_bridges)
        return path if path.is_absolute() else cwd / path
    candidates = [
        cwd / SEMANTIC_BRIDGES_FILENAME,
        cwd / "clean-source" / SEMANTIC_BRIDGES_FILENAME,
        cwd / ".aippocampus" / "clean-source" / SEMANTIC_BRIDGES_FILENAME,
    ]
    return next((path for path in candidates if path.exists()), None)


def query_expansion_plan(
    query_terms: Sequence[str],
    *,
    seed_terms: Sequence[str],
    source_aliases: str | Path | None,
    semantic_bridges: str | Path | None = None,
    cwd: Path,
) -> dict[str, Any]:
    alias_path = source_factual_aliases_path(source_aliases, cwd)
    bridge_path = semantic_bridges_path(semantic_bridges, cwd)
    return plan_query_expansion(
        query_terms,
        seed_terms=seed_terms,
        source_alias_rows=load_source_factual_alias_rows(alias_path),
        semantic_bridge_rows=load_semantic_bridge_rows(bridge_path),
    )


def source_texture_path(source_texture: str | Path | None, cwd: Path) -> Path | None:
    if not source_texture:
        return None
    path = Path(source_texture)
    return path if path.is_absolute() else cwd / path


def load_source_texture_sidecar_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, Mapping)]
        if isinstance(payload, Mapping):
            for key in ("hints", "texture_hints", "rows", "source_texture"):
                nested_rows = payload.get(key)
                if isinstance(nested_rows, list):
                    return [dict(item) for item in nested_rows if isinstance(item, Mapping)]
            return [dict(payload)]
        if payload is not None:
            return []
    return load_jsonl_dict_rows_strict(path)


def _looks_like_texture_hint(row: Mapping[str, Any]) -> bool:
    return (
        row.get("kind") == "aippocampus_source_texture_boundary_hint"
        or bool(row.get("canonical_segment_id") and row.get("derived_segment_id"))
    )


def _segment_id(segment: Mapping[str, Any], ordinal: int | None = None) -> str:
    return str(
        segment.get("segment_id")
        or segment.get("id")
        or (f"segment-{ordinal:06d}" if ordinal is not None else "")
    )


def _tokenize_hint_text(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = str(value or "").casefold().replace("_", " ").replace("-", " ")
        for part in re.findall(r"[a-z0-9]{2,}|[\u3400-\u9fff]{2,}", text):
            tokens.add(part)
        compact = "".join(re.findall(r"[\u3400-\u9fff]", text))
        if 2 <= len(compact) <= 12:
            tokens.add(compact)
    return tokens


def _hint_query_overlap(hint: Mapping[str, Any], query_terms: Sequence[str]) -> bool:
    query_tokens: set[str] = set()
    for term in query_terms:
        query_tokens.update(_tokenize_hint_text(term))
    if not query_tokens:
        return False
    hint_tokens = _tokenize_hint_text(
        hint.get("signal_kind"),
        hint.get("boundary_reason"),
        hint.get("signal_detail"),
        *(hint.get("reason_codes") or []),
    )
    return bool(query_tokens & hint_tokens)


def build_texture_hint_plan(
    *,
    source_texture: str | Path | None,
    cwd: Path,
    segments: Sequence[Mapping[str, Any]],
    planned_segments: Sequence[tuple[int, Mapping[str, Any]]],
    query_terms: Sequence[str],
    expanded_terms: Sequence[str],
    limit: int = 64,
) -> dict[str, Any]:
    """Return opt-in segment fanout extensions from source-texture hints.

    Source texture is a derived read model: it may help search decide which
    canonical segment to open, but it must not create source ids, replace stable
    segment ids, or support claims without reopening source.
    """

    if not source_texture:
        return {
            "enabled": False,
            "texture_hint_count": 0,
            "texture_hints_available": 0,
            "texture_hints_used": 0,
            "added_segment_count": 0,
            "suppression_reasons": {},
            "reason_codes": ["source_texture_not_requested"],
            "read_model_only": True,
            "source_reopen_required_before_claim": True,
        }
    path = source_texture_path(source_texture, cwd)
    if path is None or not path.exists():
        return {
            "enabled": True,
            "source_texture_path_present": False,
            "texture_hint_count": 0,
            "texture_hints_available": 0,
            "texture_hints_used": 0,
            "added_segment_count": 0,
            "suppression_reasons": {"sidecar_missing": 1},
            "reason_codes": ["source_texture_sidecar_missing"],
            "read_model_only": True,
            "source_reopen_required_before_claim": True,
        }

    try:
        rows = load_source_texture_sidecar_rows(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "enabled": True,
            "source_texture_path_present": True,
            "texture_hint_count": 0,
            "texture_hints_available": 0,
            "texture_hints_used": 0,
            "added_segment_count": 0,
            "suppression_reasons": {"sidecar_load_error": 1},
            "reason_codes": ["source_texture_sidecar_load_error", type(exc).__name__],
            "read_model_only": True,
            "source_reopen_required_before_claim": True,
        }
    sidecar_reasons: Counter[str] = Counter()
    trusted_texture_rows: list[dict[str, Any]] = []
    for row in rows:
        if _looks_like_texture_hint(row):
            trusted_texture_rows.append(row)
            continue
        if row.get("truth_boundary") != SOURCE_TEXTURE_BOUNDARY:
            sidecar_reasons["source_texture_boundary_mismatch"] += 1
            continue
        trusted_texture_rows.append(row)
    raw_hints = (
        trusted_texture_rows
        if trusted_texture_rows and all(_looks_like_texture_hint(row) for row in trusted_texture_rows)
        else build_source_texture_boundary_hints(segments, trusted_texture_rows, limit=limit)
    )
    segment_by_id = {_segment_id(segment): (ordinal, segment) for ordinal, segment in enumerate(segments, start=1)}
    planned_ids = {_segment_id(segment) for _ordinal, segment in planned_segments}
    added: list[dict[str, Any]] = []
    available = 0
    used_hints = 0
    used_segment_ids: set[str] = set()
    reasons: Counter[str] = Counter(sidecar_reasons)
    query_surface = [*query_terms, *expanded_terms]

    for hint in raw_hints[: max(0, int(limit))]:
        canonical_id = str(hint.get("canonical_segment_id") or "")
        if not canonical_id or canonical_id not in segment_by_id:
            reasons["canonical_segment_missing"] += 1
            continue
        if str(hint.get("truth_boundary") or "") != TEXTURE_HINT_BOUNDARY:
            reasons["hint_boundary_mismatch"] += 1
            continue
        if hint.get("read_model_only") is not True or hint.get("source_reopen_required_before_claim") is not True:
            reasons["unsafe_hint_boundary"] += 1
            continue
        if not (hint.get("source_refs") or hint.get("canonical_source_refs")):
            reasons["missing_hint_refs"] += 1
            continue
        if not _hint_query_overlap(hint, query_surface):
            reasons["query_mismatch"] += 1
            continue
        available += 1
        if canonical_id in planned_ids:
            reasons["segment_already_planned"] += 1
            continue
        if canonical_id in used_segment_ids:
            reasons["duplicate_canonical_segment"] += 1
            continue
        ordinal, segment = segment_by_id[canonical_id]
        used_segment_ids.add(canonical_id)
        used_hints += 1
        added.append(
            {
                "ordinal": ordinal,
                "segment": segment,
                "reason_code": "texture_hint_query_match",
            }
        )

    reason_codes = ["source_texture_hint_read_model"]
    if added:
        reason_codes.append("texture_hint_added_segment")
    if reasons:
        reason_codes.extend(f"texture_hint_{name}" for name in sorted(reasons))
    return {
        "enabled": True,
        "source_texture_path_present": True,
        "texture_hint_count": len(raw_hints),
        "texture_hints_available": available,
        "texture_hints_used": used_hints,
        "added_segment_count": len(added),
        "added_segments": added,
        "suppression_reasons": dict(sorted(reasons.items())),
        "reason_codes": reason_codes,
        "read_model_only": True,
        "source_truth_authority": "none",
        "source_reopen_required_before_claim": True,
    }


def apply_texture_hint_plan(
    planned_segments: list[tuple[int, dict]],
    fanout: dict[str, Any],
    texture_hint_plan: Mapping[str, Any],
) -> list[tuple[int, dict]]:
    """Apply texture hint fanout reprioritization without growing the runner."""

    additions = [
        (int(row["ordinal"]), dict(row["segment"]))
        for row in texture_hint_plan.get("added_segments") or []
        if isinstance(row, Mapping) and isinstance(row.get("segment"), Mapping)
    ]
    if not additions:
        fanout["source_texture_hints"] = {
            key: value
            for key, value in texture_hint_plan.items()
            if key != "added_segments"
        }
        return planned_segments

    hint_ids = {_segment_id(segment, ordinal) for ordinal, segment in additions}
    combined = [
        *additions,
        *[
            (ordinal, segment)
            for ordinal, segment in planned_segments
            if _segment_id(segment, ordinal) not in hint_ids
        ],
    ]
    target_count = int(fanout.get("effective_max_segments") or len(planned_segments))
    if target_count <= 0:
        target_count = len(combined)
    new_planned = combined[:target_count]
    displaced = combined[target_count:]
    planned_ids = {_segment_id(segment, ordinal) for ordinal, segment in new_planned}
    old_entries = [
        *(fanout.get("planned_segments") or []),
        *(fanout.get("skipped_segments") or []),
    ]
    entry_by_id = {
        str(entry.get("segment_id") or ""): dict(entry)
        for entry in old_entries
        if isinstance(entry, Mapping)
    }

    def entry_for(ordinal: int, segment: Mapping[str, Any]) -> dict[str, Any]:
        segment_id = _segment_id(segment, ordinal)
        entry = dict(entry_by_id.get(segment_id) or {"segment_id": segment_id, "ordinal": ordinal})
        if segment_id in hint_ids:
            entry.pop("reason", None)
            entry["texture_hint_used"] = True
            entry["texture_hint_reason"] = "texture_hint_query_match"
        return entry

    fanout["planned_segments"] = [entry_for(ordinal, segment) for ordinal, segment in new_planned]
    skipped: list[dict[str, Any]] = []
    seen_skipped: set[str] = set()
    for entry in fanout.get("skipped_segments") or []:
        if not isinstance(entry, Mapping):
            continue
        segment_id = str(entry.get("segment_id") or "")
        if not segment_id or segment_id in planned_ids or segment_id in seen_skipped:
            continue
        seen_skipped.add(segment_id)
        skipped.append(dict(entry))
    for ordinal, segment in displaced:
        segment_id = _segment_id(segment, ordinal)
        if segment_id in planned_ids or segment_id in seen_skipped:
            continue
        entry = entry_for(ordinal, segment)
        entry["reason"] = "texture_hint_reprioritized"
        seen_skipped.add(segment_id)
        skipped.append(entry)
    fanout["skipped_segments"] = skipped
    fanout["planned_segment_count"] = len(new_planned)
    fanout["skipped_segment_count"] = len(skipped)
    fanout["budget_exhausted"] = bool(skipped)
    fanout["source_texture_hints"] = {
        key: value
        for key, value in texture_hint_plan.items()
        if key != "added_segments"
    }
    return new_planned


def apply_source_texture_hints(
    source_texture: str | Path | None,
    cwd: Path,
    segments: Sequence[Mapping[str, Any]],
    planned_segments: list[tuple[int, dict]],
    fanout: dict[str, Any],
    query_terms: Sequence[str],
    expanded_terms: Sequence[str],
) -> list[tuple[int, dict]]:
    plan = build_texture_hint_plan(
        source_texture=source_texture,
        cwd=cwd,
        segments=segments,
        planned_segments=planned_segments,
        query_terms=query_terms,
        expanded_terms=expanded_terms,
    )
    return apply_texture_hint_plan(planned_segments, fanout, plan)


def outcome_candidate_refs(results: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in results[:24]:
        ref: dict[str, str] = {}
        route_id = item.get("route_id") or item.get("stable_source_id") or item.get("source_ref")
        if route_id:
            ref["route_id"] = str(route_id)
        source_ref_id = item.get("source_ref_id") or item.get("source_ref") or item.get("message_id")
        if source_ref_id:
            ref["source_ref_id"] = str(source_ref_id)
        segment_id = item.get("segment_id")
        if segment_id:
            ref["segment_id"] = str(segment_id)
        if ref:
            refs.append(ref)
    return refs


def maybe_emit_outcome_feedback(
    *,
    outcome_feedback_path: str | Path | None,
    outcome_signal: str | None,
    outcome_run_id: str | None,
    patterns: Sequence[str],
    mode: str,
    strategy: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not outcome_feedback_path or not outcome_signal:
        return {"emitted": False, "reason": "not_requested"}
    raw_query = " ".join(str(item) for item in patterns)
    run_id = outcome_run_id
    if not run_id:
        digest = hashlib.sha256(raw_query.encode("utf-8", errors="replace")).hexdigest()[:16]
        run_id = f"segment_search:{digest}"
    path = Path(outcome_feedback_path)
    event = build_recall_outcome_event(
        raw_query=raw_query,
        run_id=str(run_id),
        route_family=mode,
        scoring_policy=str(strategy.get("freshness_mode") or "neutral"),
        delivered_candidates=outcome_candidate_refs(results),
        outcome_signal=str(outcome_signal),
        selected_route_id=str((results[0] if results else {}).get("route_id") or ""),
        currentness=str(strategy.get("freshness_mode") or "unknown"),
    )
    write_recall_outcome_event(path, event)
    return {
        "emitted": True,
        "path": str(path),
        "event_id": event["event_id"],
        "authority": event["authority"],
    }
