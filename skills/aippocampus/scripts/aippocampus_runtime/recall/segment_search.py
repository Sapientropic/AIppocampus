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
from aippocampus_runtime.recall.score_fusion import source_join_key
from aippocampus_runtime.recall.scoring_policy import SEGMENT_MERGE_POLICY, SegmentMergePolicy
from aippocampus_runtime.recall.segment_metadata import (
    annotate_rag_chunk,
    annotate_segment_result,
    cross_boundary_turn_contexts,
    empty_turn_boundary_diagnostics,
    turn_boundary_diagnostics,
)
from aippocampus_runtime.recall.structure_time import parse_datetime_utc, parse_temporal_cue

SCRIPT_DIR = Path(__file__).resolve().parents[2]
SEGMENTS_POINTER_NAME = "segments.pointer.json"


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


def segment_sort_key(
    result: dict,
    policy: SegmentMergePolicy = SEGMENT_MERGE_POLICY,
) -> tuple[float, int, int]:
    final_bonus = (
        policy.final_answer_bonus
        if result.get("phase") == "final_answer" or result.get("is_final")
        else 0.0
    )
    commentary_penalty = (
        policy.commentary_penalty if result.get("phase") == "commentary" else 0.0
    )
    return (
        -(float(result.get("score") or 0.0) + final_bonus + commentary_penalty),
        int(result.get("line") or 10**12),
        int(result.get("segment_ordinal") or 10**6),
    )


def segment_source_join_key(result: dict) -> str:
    """Return stable source identity when a segment hit exposes one.

    Segment-local SQLite ids collide and overlapped shards can surface the same
    clean-source row under different segment ids. Prefer the shared
    score-fusion source join semantics; use scalar `source_ref` only as an
    already-projected stable ref. Hits without a source key keep the legacy
    segment-local fallback path.
    """

    key = source_join_key(result)
    if key:
        return f"source_join:{key}"
    source_ref = str(result.get("source_ref") or "").strip()
    if source_ref:
        return f"source_ref:{source_ref}"
    return ""


def _dedupe_pool_by_source_key(pool: list[dict]) -> tuple[list[dict], int]:
    deduped: list[dict] = []
    seen: set[str] = set()
    dedupe_count = 0
    for item in pool:
        key = segment_source_join_key(item)
        if key and key in seen:
            dedupe_count += 1
            continue
        deduped.append(item)
        if key:
            seen.add(key)
    return deduped, dedupe_count


def merge_topk_with_diagnostics(
    results: list[dict],
    limit: int,
    policy: SegmentMergePolicy = SEGMENT_MERGE_POLICY,
) -> tuple[list[dict], dict[str, int]]:
    """Merge hits and report compact source-key dedupe diagnostics."""

    if not results:
        return (
            [],
            {
                "input_candidate_count": 0,
                "candidate_count_after_source_key_dedupe": 0,
                "source_key_dedupe_count": 0,
            },
        )
    pool = sorted(results, key=lambda item: segment_sort_key(item, policy))
    pool, source_key_dedupe_count = _dedupe_pool_by_source_key(pool)
    diagnostics = {
        "input_candidate_count": len(results),
        "candidate_count_after_source_key_dedupe": len(pool),
        "source_key_dedupe_count": source_key_dedupe_count,
    }
    if not pool:
        return [], diagnostics

    selected: list[dict] = []
    seen: set[tuple[str, int, int]] = set()

    def key(item: dict) -> tuple[str, int, int]:
        return (str(item.get("segment_id")), int(item.get("id") or 0), int(item.get("line") or 0))

    def add(item: dict | None) -> None:
        if not item:
            return
        item_key = key(item)
        if item_key in seen:
            return
        selected.append(item)
        seen.add(item_key)

    add(pool[0])
    literal_hits = [item for item in pool if (item.get("signals") or {}).get("literal_hits", 0) > 0]
    add(
        min(
            (item for item in literal_hits if item.get("role") == "user"),
            key=lambda item: item.get("line") or 10**12,
            default=None,
        )
    )
    add(min(literal_hits, key=lambda item: item.get("line") or 10**12, default=None))
    add(
        max(
            (item for item in pool if item.get("role") == "assistant"),
            key=lambda item: (
                (
                    policy.final_answer_bonus
                    if item.get("phase") == "final_answer" or item.get("is_final")
                    else 0.0
                )
                + float(item.get("score") or 0)
            ),
            default=None,
        )
    )

    while len(selected) < min(limit, len(pool)):
        selected_segments = {str(item.get("segment_id")) for item in selected}
        selected_lines = [int(item.get("line") or 0) for item in selected]
        best = None
        best_value = None
        for item in pool:
            if key(item) in seen:
                continue
            value = float(item.get("score") or 0.0)
            if str(item.get("segment_id")) in selected_segments:
                value -= policy.same_segment_penalty
            if item.get("phase") == "final_answer" or item.get("is_final"):
                value += policy.final_answer_bonus
            if item.get("phase") == "commentary":
                value += policy.commentary_penalty
            line = int(item.get("line") or 0)
            if any(
                abs(line - other) < policy.nearby_line_window
                for other in selected_lines
            ):
                value -= policy.nearby_line_penalty
            if (item.get("signals") or {}).get("literal_hits", 0) > 0 and item.get(
                "role"
            ) == "user":
                value += policy.user_literal_bonus
            if best_value is None or value > best_value:
                best = item
                best_value = value
        add(best)
        if best is None:
            break
    return selected[:limit], diagnostics


def merge_topk(
    results: list[dict],
    limit: int,
    policy: SegmentMergePolicy = SEGMENT_MERGE_POLICY,
) -> list[dict]:
    """Merge per-shard hits without letting one dense recap shard dominate.

    Segment-local SQLite row ids collide, so this intentionally avoids
    retrieval.diversify_results, whose duplicate guard assumes one monolithic
    index. The merge keeps high-score hits first, then applies light penalties
    for same-segment and near-line repeats so early source evidence and later
    summaries can both surface. The optional policy argument is for deterministic
    calibration/sensitivity tests; the CLI path uses the default named policy.
    """

    selected, _ = merge_topk_with_diagnostics(results, limit, policy=policy)
    return selected


def query_context_payload(options: SegmentSearchOptions, cwd: Path) -> dict:
    patterns = list(options.patterns)
    anchor_path = resolve_anchor_path(str(cwd), str(options.anchors))
    query_terms = split_query_terms(patterns)
    anchors = match_anchors(anchor_path, query_terms) if anchor_path.exists() else []
    expanded_terms = (
        expanded_terms_from_anchors(query_terms, anchors)
        if options.mode == "hybrid"
        else query_terms
    )
    graph = (
        graph_neighbors(auto_graph_path(str(cwd)), expanded_terms)
        if options.mode == "hybrid"
        else []
    )
    return {
        "query_terms": query_terms,
        "expanded_terms": expanded_terms,
        "matched_anchors": anchors,
        "graph_neighbors": graph,
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
            "turn_boundary_diagnostics": empty_turn_boundary_diagnostics(),
            "availability": {
                "reason": reason,
                "build_required": True,
                "build_requested": bool(options.build_segments),
            },
        }
    )
    return payload


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

        raw_results: list[dict] = []
        rag_context: list[dict] = []
        segment_errors: list[dict] = []
        segments = list(data.get("segments") or [])
        boundary_contexts = cross_boundary_turn_contexts(segments)
        boundary_diagnostics = turn_boundary_diagnostics(segments, boundary_contexts)
        temporal_cue = _temporal_cue_for_options(options)
        planned_segments, fanout = plan_segments(segments, options, temporal_cue=temporal_cue)
        searched_segment_count = 0
        missing_index_count = 0
        for ordinal, segment in planned_segments:
            index = Path(segment["sqlite"])
            if not index.exists():
                missing_index_count += 1
                segment_errors.append({"segment_id": segment.get("id"), "error": "sqlite missing"})
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
                    if options.mode == "hybrid" and options.rag_context > 0:
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
                raw_results.extend(
                    annotate_segment_result(hit, segment, ordinal, boundary_contexts)
                    for hit in hits
                )
            except Exception as exc:
                segment_errors.append({"segment_id": segment.get("id"), "error": str(exc)})

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

        return {
            "ok": available,
            "status": "ok" if available else "segments_unavailable",
            "source": str(manifest),
            "mode": f"segmented-{options.mode}",
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
            "turn_boundary_diagnostics": boundary_diagnostics,
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
