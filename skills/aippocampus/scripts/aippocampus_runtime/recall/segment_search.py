#!/usr/bin/env python3
"""Fan out a query across segmented thread indexes and merge top-k hits."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from aippocampus_runtime.artifacts.generation_pins import pin_resolved_generation
from aippocampus_runtime.core import default_thread_segments_dir
from aippocampus_runtime.recall import segment_merge
from aippocampus_runtime.recall.retrieval import (
    expanded_terms_from_anchors,
    graph_neighbors,
    match_anchors,
    search_hybrid_index,
    search_rag_chunks,
    split_query_terms,
)
from aippocampus_runtime.recall.rollout_search import (
    auto_graph_path,
    resolve_anchor_path,
    search_index_literal,
)
from aippocampus_runtime.recall.segment_deep_recall import (
    disabled_diagnostics,
    now_seconds,
    run_explicit_deep_recall,
    source_keys,
    unavailable_diagnostics,
)
from aippocampus_runtime.recall.segment_merge import (
    merge_topk_with_diagnostics,
    segment_source_join_key,
)
from aippocampus_runtime.recall.segment_metadata import (
    annotate_rag_chunk,
    annotate_segment_result,
    cross_boundary_turn_contexts,
    empty_turn_boundary_diagnostics,
    turn_boundary_diagnostics,
)
from aippocampus_runtime.recall.segment_search_extras import (
    add_sidecar_arguments,
    apply_source_texture_hints,
    maybe_emit_outcome_feedback,
    query_expansion_plan,
)
from aippocampus_runtime.recall.strategy_planner import select_recall_strategy
from aippocampus_runtime.recall.structure_time import parse_datetime_utc, parse_temporal_cue

SCRIPT_DIR = Path(__file__).resolve().parents[2]
SEGMENTS_POINTER_NAME = "segments.pointer.json"
merge_topk = segment_merge.merge_topk


@dataclass(frozen=True)
class SegmentSearchOptions:
    patterns: Sequence[str]
    cwd: str | Path = os.getcwd()
    rollout: str | Path | None = None
    segments_dir: str | Path | None = None
    anchors: str | Path = "thread-anchors.md"
    build_segments: bool = False
    mode: str = "hybrid"
    context: int = 0
    per_segment: int = 12
    candidate_max: int = 120
    rag_context: int = 6
    max_results: int = 30
    snippet_chars: int = 700
    fanout_budget: int | None = None
    max_segments: int | None = None
    full_fanout: bool = False
    now: str | None = None
    deep: bool = False
    deep_max_hops: int = 1
    deep_candidate_budget: int | None = None
    deep_elapsed_budget_ms: int | None = None
    deep_terms_per_hop: int = 8
    source_aliases: str | Path | None = None
    outcome_feedback_path: str | Path | None = None
    outcome_signal: str | None = None
    outcome_run_id: str | None = None
    source_texture: str | Path | None = None


def manifest_path(cwd: Path, segments_dir: str | None, *, prefer_existing: bool = True) -> Path:
    if segments_dir:
        path = Path(segments_dir)
        if not path.is_absolute():
            path = cwd / path
        return path / "manifest.json"
    global_manifest = default_thread_segments_dir(cwd) / "manifest.json"
    legacy_manifest = cwd / ".aippocampus" / "segments" / "manifest.json"
    if prefer_existing and not global_manifest.exists() and legacy_manifest.exists():
        return legacy_manifest
    return global_manifest


def _load_segment_pointer(pointer_path: Path) -> dict:
    if not pointer_path.exists():
        return {}
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _pointer_candidate(pointer_path: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = pointer_path.parent / candidate
    return candidate


def resolve_manifest_path(manifest: Path) -> Path:
    """Pin a segment generation manifest once for this search query."""

    pointer_path = manifest.with_name(SEGMENTS_POINTER_NAME)
    pointer = _load_segment_pointer(pointer_path)
    for key in ("current", "last_known_good", "stable"):
        candidate = _pointer_candidate(pointer_path, pointer.get(key))
        if candidate and candidate.is_file():
            return candidate
    return manifest


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_segments(cwd: Path, rollout: str | None, manifest: Path, force: bool) -> None:
    if not force:
        return
    cmd = [
        sys.executable,
        "-m", "aippocampus_runtime.recall.segment_builder",
        "--cwd",
        str(cwd),
        "--output-dir",
        str(manifest.parent),
    ]
    if rollout:
        cmd.extend(["--rollout", rollout])
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)


def _safe_int(value: object, default: int = 0) -> int:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    return max(0, _safe_int(value))


def _segment_id(segment: dict, ordinal: int) -> str:
    return str(segment.get("id") or f"segment-{ordinal:06d}")


def _segment_recency_key(item: tuple[int, dict]) -> tuple[int, int, int, int]:
    ordinal, segment = item
    return (
        _safe_int(segment.get("end_global_id")),
        _safe_int(segment.get("end_line")),
        _safe_int(segment.get("start_line")),
        ordinal,
    )


def _empty_fanout(options: SegmentSearchOptions) -> dict:
    return {
        "mode": "full" if options.full_fanout else "budgeted",
        "requested_fanout_budget": options.fanout_budget,
        "requested_max_segments": options.max_segments,
        "effective_max_segments": 0,
        "planned_segment_count": 0,
        "searched_segment_count": 0,
        "skipped_segment_count": 0,
        "missing_index_count": 0,
        "budget_exhausted": False,
        "planned_segments": [],
        "skipped_segments": [],
        "temporal_cue_parsed": False,
        "temporal_cue_kind": "",
        "temporal_window_start": "",
        "temporal_window_end": "",
        "temporal_boosted_segments": [],
    }


def _temporal_cue_for_options(options: SegmentSearchOptions) -> dict[str, Any] | None:
    prompt = " ".join(str(item) for item in options.patterns if str(item).strip())
    return parse_temporal_cue(prompt, now=options.now) if prompt else None


def _segment_time_range(segment: dict) -> tuple[Any | None, Any | None]:
    start = parse_datetime_utc(segment.get("start_timestamp"))
    end = parse_datetime_utc(segment.get("end_timestamp"))
    if start is None and end is None:
        return None, None
    if start is None:
        start = end
    if end is None:
        end = start
    if start is not None and end is not None and end < start:
        start, end = end, start
    return start, end


def _segment_temporal_overlap_score(segment: dict, temporal_cue: dict[str, Any] | None) -> float:
    if not temporal_cue:
        return 0.0
    window_start = parse_datetime_utc(temporal_cue.get("window_start"))
    window_end = parse_datetime_utc(temporal_cue.get("window_end"))
    segment_start, segment_end = _segment_time_range(segment)
    if (
        window_start is None
        or window_end is None
        or segment_start is None
        or segment_end is None
        or window_end <= window_start
    ):
        return 0.0
    if segment_start < window_end and segment_end >= window_start:
        confidence = max(0.0, min(1.0, float(temporal_cue.get("confidence") or 0.0)))
        return round(confidence, 3)
    return 0.0


def _segment_fanout_entry(
    segment: dict,
    ordinal: int,
    temporal_scores: dict[int, float],
    *,
    skipped_reason: str | None = None,
) -> dict:
    entry = {"segment_id": _segment_id(segment, ordinal), "ordinal": ordinal}
    temporal_score = temporal_scores.get(ordinal, 0.0)
    entry["temporal_boosted"] = temporal_score > 0.0
    if temporal_score > 0.0:
        entry["temporal_overlap_score"] = temporal_score
    if skipped_reason:
        entry["reason"] = skipped_reason
    return entry


def plan_segments(
    segments: Sequence[dict],
    options: SegmentSearchOptions,
    temporal_cue: dict[str, Any] | None = None,
) -> tuple[list[tuple[int, dict]], dict]:
    if temporal_cue is None:
        temporal_cue = _temporal_cue_for_options(options)
    temporal_scores = {
        ordinal: _segment_temporal_overlap_score(segment, temporal_cue)
        for ordinal, segment in enumerate(segments, start=1)
    }
    if temporal_cue:
        ranked = sorted(
            enumerate(segments, start=1),
            key=lambda item: (
                temporal_scores.get(item[0], 0.0) > 0.0,
                temporal_scores.get(item[0], 0.0),
                *_segment_recency_key(item),
            ),
            reverse=True,
        )
    else:
        ranked = sorted(enumerate(segments, start=1), key=_segment_recency_key, reverse=True)
    budget_values: list[int] = []
    if not options.full_fanout:
        for value in (options.fanout_budget, options.max_segments):
            parsed = _optional_nonnegative_int(value)
            if parsed is not None:
                budget_values.append(parsed)
    effective_max = len(ranked) if not budget_values else min(len(ranked), min(budget_values))
    planned = ranked[:effective_max]
    skipped = ranked[effective_max:]
    # The budget must be resolved before touching any SQLite shard. Full fanout
    # stays explicit so diagnostics and benchmark comparisons can still measure
    # worst-case search without changing foreground latency by accident.
    fanout = {
        "mode": "full" if options.full_fanout else "budgeted",
        "requested_fanout_budget": options.fanout_budget,
        "requested_max_segments": options.max_segments,
        "effective_max_segments": effective_max,
        "planned_segment_count": len(planned),
        "searched_segment_count": 0,
        "skipped_segment_count": len(skipped),
        "missing_index_count": 0,
        "budget_exhausted": bool(skipped),
        "planned_segments": [
            _segment_fanout_entry(segment, ordinal, temporal_scores)
            for ordinal, segment in planned
        ],
        "skipped_segments": [
            _segment_fanout_entry(
                segment,
                ordinal,
                temporal_scores,
                skipped_reason="fanout_budget",
            )
            for ordinal, segment in skipped
        ],
        "temporal_cue_parsed": bool(temporal_cue),
        "temporal_cue_kind": str((temporal_cue or {}).get("cue_kind") or ""),
        "temporal_window_start": str((temporal_cue or {}).get("window_start") or ""),
        "temporal_window_end": str((temporal_cue or {}).get("window_end") or ""),
        "temporal_boosted_segments": [
            _segment_id(segment, ordinal)
            for ordinal, segment in ranked
            if temporal_scores.get(ordinal, 0.0) > 0.0
        ],
    }
    return planned, fanout


def query_context_payload(options: SegmentSearchOptions, cwd: Path) -> dict:
    patterns = list(options.patterns)
    anchor_path = resolve_anchor_path(str(cwd), str(options.anchors))
    query_terms = split_query_terms(patterns)
    anchors = match_anchors(anchor_path, query_terms) if anchor_path.exists() else []
    anchor_expanded_terms = (
        expanded_terms_from_anchors(query_terms, anchors)
        if options.mode == "hybrid"
        else query_terms
    )
    expansion_plan = query_expansion_plan(
        query_terms,
        seed_terms=anchor_expanded_terms,
        source_aliases=options.source_aliases,
        cwd=cwd,
    )
    expanded_terms = expansion_plan["expanded_terms"]
    graph = (
        graph_neighbors(auto_graph_path(str(cwd)), expanded_terms)
        if options.mode == "hybrid"
        else []
    )
    strategy = select_recall_strategy(" ".join(str(item) for item in patterns))
    return {
        "query_terms": query_terms,
        "expanded_terms": expanded_terms,
        "matched_anchors": anchors,
        "graph_neighbors": graph,
        "query_expansion": expansion_plan["diagnostics"],
        "recall_strategy": strategy,
    }


def unavailable_segments_payload(
    options: SegmentSearchOptions,
    cwd: Path,
    manifest: Path,
    *,
    reason: str,
) -> dict:
    payload = query_context_payload(options, cwd)
    payload.update(
        {
            "ok": False,
            "status": "segments_unavailable",
            "source": str(manifest),
            "mode": f"segmented-{options.mode}",
            "segment_count": 0,
            "rag_context": [],
            "matches": [],
            "merge_diagnostics": {
                "input_candidate_count": 0,
                "candidate_count_after_source_key_dedupe": 0,
                "source_key_dedupe_count": 0,
            },
            "segment_errors": [],
            "fanout": _empty_fanout(options),
            "deep_recall": unavailable_diagnostics(options),
            "turn_boundary_diagnostics": empty_turn_boundary_diagnostics(),
            "availability": {
                "reason": reason,
                "build_required": True,
                "build_requested": bool(options.build_segments),
            },
        }
    )
    return payload


def _search_segment_pass(
    *,
    options: SegmentSearchOptions,
    patterns: list[str],
    query_terms: list[str],
    expanded_terms: list[str],
    anchors: list[dict],
    planned_segments: list[tuple[int, dict]],
    boundary_contexts: dict[str, dict],
    temporal_cue: dict[str, Any] | None,
    recall_hop: int,
    include_rag_context: bool,
) -> dict[str, Any]:
    raw_results: list[dict] = []
    rag_context: list[dict] = []
    segment_errors: list[dict] = []
    searched_segment_count = 0
    missing_index_count = 0
    for ordinal, segment in planned_segments:
        index = Path(segment["sqlite"])
        if not index.exists():
            missing_index_count += 1
            segment_errors.append(
                {
                    "segment_id": segment.get("id"),
                    "error": "sqlite missing",
                    "recall_hop": recall_hop,
                }
            )
            continue
        searched_segment_count += 1
        try:
            if options.mode == "literal":
                hits = search_index_literal(
                    index,
                    patterns,
                    options.per_segment,
                    options.snippet_chars,
                )
            else:
                if (
                    include_rag_context
                    and options.mode == "hybrid"
                    and options.rag_context > 0
                ):
                    for chunk in search_rag_chunks(
                        index,
                        query_terms,
                        expanded_terms,
                        anchors,
                        limit=max(1, options.rag_context // 2),
                        candidate_limit=max(24, options.candidate_max // 2),
                        snippet_chars=max(options.snippet_chars, 900),
                    ):
                        rag_context.append(annotate_rag_chunk(chunk, segment, ordinal))
                hits = search_hybrid_index(
                    index,
                    query_terms,
                    expanded_terms,
                    anchors if options.mode == "hybrid" else [],
                    limit=options.per_segment,
                    candidate_limit=options.candidate_max,
                    snippet_chars=options.snippet_chars,
                    context_radius=options.context,
                    temporal_cue=temporal_cue,
                )
            for hit in hits:
                item = annotate_segment_result(hit, segment, ordinal, boundary_contexts)
                item["recall_hop"] = recall_hop
                raw_results.append(item)
        except Exception as exc:
            segment_errors.append(
                {"segment_id": segment.get("id"), "error": str(exc), "recall_hop": recall_hop}
            )
    return {
        "raw_results": raw_results,
        "rag_context": rag_context,
        "segment_errors": segment_errors,
        "searched_segment_count": searched_segment_count,
        "missing_index_count": missing_index_count,
    }


def search_segments_payload(options: SegmentSearchOptions) -> dict:
    patterns = list(options.patterns)
    cwd = Path(options.cwd).resolve()
    manifest = manifest_path(
        cwd,
        str(options.segments_dir) if options.segments_dir else None,
        prefer_existing=not options.build_segments,
    )
    ensure_segments(
        cwd,
        str(options.rollout) if options.rollout else None,
        manifest,
        options.build_segments,
    )
    manifest = resolve_manifest_path(manifest)
    with pin_resolved_generation(manifest, artifact_kind="segments"):
        data = load_manifest(manifest)
        if not data:
            return unavailable_segments_payload(
                options,
                cwd,
                manifest,
                reason="manifest_missing",
            )

        query_payload = query_context_payload(options, cwd)
        query_terms = query_payload["query_terms"]
        expanded_terms = query_payload["expanded_terms"]
        anchors = query_payload["matched_anchors"]

        segments = list(data.get("segments") or [])
        boundary_contexts = cross_boundary_turn_contexts(segments)
        boundary_diagnostics = turn_boundary_diagnostics(segments, boundary_contexts)
        temporal_cue = _temporal_cue_for_options(options)
        planned_segments, fanout = plan_segments(segments, options, temporal_cue=temporal_cue)
        planned_segments = apply_source_texture_hints(
            options.source_texture, cwd, segments, planned_segments, fanout, query_terms, expanded_terms
        )
        started_at = now_seconds()
        first_pass = _search_segment_pass(
            options=options,
            patterns=patterns,
            query_terms=query_terms,
            expanded_terms=expanded_terms,
            anchors=anchors,
            planned_segments=planned_segments,
            boundary_contexts=boundary_contexts,
            temporal_cue=temporal_cue,
            recall_hop=0,
            include_rag_context=True,
        )
        raw_results = list(first_pass["raw_results"])
        rag_context = list(first_pass["rag_context"])
        segment_errors = list(first_pass["segment_errors"])
        searched_segment_count = int(first_pass["searched_segment_count"])
        missing_index_count = int(first_pass["missing_index_count"])
        deep_recall = disabled_diagnostics()
        if options.deep:
            initial_source_keys = source_keys(raw_results, segment_source_join_key)
            deep_pass = run_explicit_deep_recall(
                options=options,
                query_terms=query_terms,
                planned_segments=planned_segments,
                boundary_contexts=boundary_contexts,
                temporal_cue=temporal_cue,
                initial_results=raw_results,
                initial_source_keys=initial_source_keys,
                started_at=started_at,
                search_pass=_search_segment_pass,
                source_key_fn=segment_source_join_key,
            )
            deep_recall = deep_pass["diagnostics"]
            deep_recall["searched_segment_count"] = int(deep_pass["searched_segment_count"])
            deep_recall["missing_index_count"] = int(deep_pass["missing_index_count"])
            raw_results.extend(deep_pass["raw_results"])
            rag_context.extend(deep_pass["rag_context"])
            segment_errors.extend(deep_pass["segment_errors"])
        fanout["searched_segment_count"] = searched_segment_count
        fanout["missing_index_count"] = missing_index_count
        results, merge_diagnostics = merge_topk_with_diagnostics(
            raw_results,
            options.max_results,
        )
        rag_context.sort(
            key=lambda item: (
                -float(item.get("score") or 0.0),
                int(item.get("start_line") or 10**12),
            )
        )
        rag_context = rag_context[: options.rag_context]
        available = searched_segment_count > 0 or not planned_segments
        mode = f"segmented-{options.mode}"
        outcome_feedback = maybe_emit_outcome_feedback(
            outcome_feedback_path=options.outcome_feedback_path,
            outcome_signal=options.outcome_signal,
            outcome_run_id=options.outcome_run_id,
            patterns=patterns,
            mode=mode,
            strategy=query_payload.get("recall_strategy") or {},
            results=results,
        )

        return {
            "ok": available,
            "status": "ok" if available else "segments_unavailable",
            "source": str(manifest),
            "mode": mode,
            "segment_count": int(data.get("segment_count") or len(data.get("segments") or [])),
            "query_terms": query_terms,
            "expanded_terms": expanded_terms,
            "matched_anchors": anchors,
            "graph_neighbors": query_payload["graph_neighbors"],
            "rag_context": rag_context,
            "matches": results,
            "merge_diagnostics": merge_diagnostics,
            "segment_errors": segment_errors,
            "fanout": fanout,
            "deep_recall": deep_recall,
            "turn_boundary_diagnostics": boundary_diagnostics,
            "outcome_feedback": outcome_feedback,
            "availability": {
                "reason": "available" if available else "sqlite_missing",
                "build_required": bool(missing_index_count),
                "build_requested": bool(options.build_segments),
            },
        }


def options_from_args(args: argparse.Namespace) -> SegmentSearchOptions:
    return SegmentSearchOptions(
        patterns=args.patterns,
        cwd=args.cwd,
        rollout=args.rollout,
        segments_dir=args.segments_dir,
        anchors=args.anchors,
        build_segments=args.build_segments,
        mode=args.mode,
        context=args.context,
        per_segment=args.per_segment,
        candidate_max=args.candidate_max,
        rag_context=args.rag_context,
        max_results=args.max,
        snippet_chars=args.snippet_chars,
        fanout_budget=args.fanout_budget,
        max_segments=args.max_segments,
        full_fanout=args.full_fanout,
        now=args.now,
        deep=args.deep,
        deep_max_hops=args.deep_max_hops,
        deep_candidate_budget=args.deep_candidate_budget,
        deep_elapsed_budget_ms=args.deep_elapsed_budget_ms,
        deep_terms_per_hop=args.deep_terms_per_hop,
        source_aliases=args.source_aliases,
        outcome_feedback_path=args.outcome_feedback_path,
        outcome_signal=args.outcome_signal,
        outcome_run_id=args.outcome_run_id,
        source_texture=args.source_texture,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patterns", nargs="+", help="Literal clues or recall prompt.")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument(
        "--segments-dir",
        default=None,
        help="Defaults to global segments, with project-local legacy fallback.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--build-segments", action="store_true")
    parser.add_argument("--mode", choices=["literal", "ranked", "hybrid"], default="hybrid")
    parser.add_argument("--context", type=int, default=0)
    parser.add_argument("--per-segment", type=int, default=12)
    parser.add_argument("--candidate-max", type=int, default=120)
    parser.add_argument("--rag-context", type=int, default=6)
    parser.add_argument(
        "--fanout-budget",
        type=int,
        default=None,
        help="Maximum segment shards to plan before opening SQLite indexes.",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Compatibility alias for an explicit segment fanout cap.",
    )
    parser.add_argument(
        "--full-fanout",
        action="store_true",
        help="Ignore fanout caps for diagnostics and benchmark comparisons.",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="UTC ISO timestamp for deterministic relative temporal cues.",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Opt in to explicit bounded multi-hop recall; ambient hooks do not use this by default.",
    )
    parser.add_argument(
        "--deep-max-hops",
        type=int,
        default=1,
        help="Maximum extra source-joined search hops for --deep.",
    )
    parser.add_argument(
        "--deep-candidate-budget",
        type=int,
        default=None,
        help="Stop --deep before expansion once this many stable source keys are already found.",
    )
    parser.add_argument(
        "--deep-elapsed-budget-ms",
        type=int,
        default=None,
        help="Stop --deep before expansion once elapsed search time reaches this budget.",
    )
    parser.add_argument(
        "--deep-terms-per-hop",
        type=int,
        default=8,
        help="Maximum navigation terms extracted from source-joined hits per deep hop.",
    )
    add_sidecar_arguments(parser)
    parser.add_argument("--show-anchors", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--max", type=int, default=30)
    parser.add_argument("--snippet-chars", type=int, default=700)
    args = parser.parse_args()

    try:
        payload = search_segments_payload(options_from_args(args))
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    query_terms = payload["query_terms"]
    expanded_terms = payload["expanded_terms"]
    anchors = payload["matched_anchors"]
    graph = payload["graph_neighbors"]
    rag_context = payload["rag_context"]
    segment_errors = payload["segment_errors"]
    results = payload["matches"]

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"source: {payload['source']}")
        print(f"mode: {payload['mode']} ({payload['segment_count']} segments)")
        availability = payload.get("availability") or {}
        if not payload.get("ok", True):
            print(
                "availability: "
                f"{payload.get('status')} ({availability.get('reason')}; "
                f"build_required={availability.get('build_required')})"
            )
        fanout = payload.get("fanout") or {}
        if fanout:
            print(
                "fanout: "
                f"{fanout.get('planned_segment_count', 0)} planned, "
                f"{fanout.get('searched_segment_count', 0)} searched, "
                f"{fanout.get('skipped_segment_count', 0)} skipped"
            )
        deep_recall = payload.get("deep_recall") or {}
        if deep_recall.get("enabled"):
            print(
                "deep recall: "
                f"{deep_recall.get('completed_hops', 0)} explicit hop(s), "
                f"stop={deep_recall.get('stop_reason')}"
            )
        if args.mode == "hybrid":
            print(f"query terms: {', '.join(query_terms) or '(none)'}")
            print(f"expanded terms: {', '.join(expanded_terms) or '(none)'}")
        if args.show_anchors and anchors:
            print("\nmatched anchors:")
            for anchor in anchors:
                print(f"- score {anchor['score']} | {anchor['title']}")
        if args.show_anchors and graph:
            print("\ngraph neighbors:")
            for node in graph:
                marker = "*" if node.get("matched") else "-"
                print(f"{marker} {node.get('type')}: {node.get('label')}")
        if rag_context:
            print("\nrag context:")
            for chunk in rag_context:
                print(
                    f"- score {chunk['score']} | {chunk['segment_id']} chunk {chunk['id']} | "
                    f"lines {chunk['start_line']}-{chunk['end_line']}"
                )
                print(f"  {chunk['summary']}")
        if segment_errors:
            print("\nsegment errors:")
            for item in segment_errors:
                print(f"- {item['segment_id']}: {item['error']}")
        for item in results:
            score = f" score {item['score']} |" if item.get("score") is not None else ""
            print(
                f"\n- {item['segment_id']} id {item.get('id')} |{score} "
                f"line {item['line']} | {item['timestamp']} | {item['role']} | {item['kind']}"
                f"{' | phase=' + str(item.get('phase')) if item.get('phase') else ''}"
                f"{' | turn=' + str(item.get('turn_index')) if item.get('turn_index') is not None else ''}"
            )
            if item.get("score") is not None:
                compact_signals = {
                    k: v for k, v in (item.get("signals") or {}).items() if k != "fts_rank"
                }
                print(f"  signals: {compact_signals}")
            print(f"  {item['snippet']}")
            if item.get("context"):
                print("  context:")
                for ctx in item["context"]:
                    ctx_phase = f"/{ctx.get('phase')}" if ctx.get("phase") else ""
                    ctx_turn = (
                        f" turn={ctx.get('turn_index')}"
                        if ctx.get("turn_index") is not None
                        else ""
                    )
                    print(
                        f"    - {ctx['segment_id']} id {ctx['id']} | line {ctx['line']} | {ctx['role']}{ctx_phase}{ctx_turn}: {ctx['snippet']}"
                    )
    return 0 if results or anchors or rag_context else 1


if __name__ == "__main__":
    raise SystemExit(main())
