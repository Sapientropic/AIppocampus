"""Segment manifest metadata projection helpers."""

from __future__ import annotations

from typing import Sequence


def _partial_turn_indices(segment: dict) -> list[int]:
    turns = [
        int(item)
        for item in segment.get("partial_turn_indices") or []
        if type(item) is int
    ]
    return sorted(set(turns))


def cross_boundary_turn_contexts(segments: Sequence[dict]) -> dict[str, dict]:
    """Identify adjacent shard halves without expanding search fanout."""

    contexts: dict[str, dict] = {}
    turn_sets = [set(_partial_turn_indices(segment)) for segment in segments]
    for index, segment in enumerate(segments):
        segment_id = segment.get("id")
        if not isinstance(segment_id, str) or not turn_sets[index]:
            continue
        adjacent_ids: list[str] = []
        turn_indices: set[int] = set()
        for adjacent_index in (index - 1, index + 1):
            if adjacent_index < 0 or adjacent_index >= len(segments):
                continue
            shared_turns = turn_sets[index] & turn_sets[adjacent_index]
            if not shared_turns:
                continue
            adjacent_id = segments[adjacent_index].get("id")
            if not isinstance(adjacent_id, str):
                continue
            adjacent_ids.append(adjacent_id)
            turn_indices.update(shared_turns)
        if adjacent_ids:
            contexts[segment_id] = {
                "status": "identified",
                "turn_indices": sorted(turn_indices),
                "adjacent_segment_ids": adjacent_ids,
                "stitched": False,
            }
    return contexts


def annotate_segment_result(
    result: dict,
    segment: dict,
    ordinal: int,
    boundary_contexts: dict[str, dict] | None = None,
) -> dict:
    item = dict(result)
    item["segment_id"] = segment["id"]
    item["segment_ordinal"] = ordinal
    item["segment_start_line"] = segment.get("start_line")
    item["segment_end_line"] = segment.get("end_line")
    item["global_id_range"] = [segment.get("start_global_id"), segment.get("end_global_id")]
    item["segment_turn_range"] = [segment.get("start_turn_index"), segment.get("end_turn_index")]
    item["segment_starts_with_partial_turn"] = bool(segment.get("starts_with_partial_turn"))
    item["segment_ends_with_partial_turn"] = bool(segment.get("ends_with_partial_turn"))
    item["segment_partial_turn_indices"] = _partial_turn_indices(segment)
    cross_boundary_context = (boundary_contexts or {}).get(segment["id"])
    if cross_boundary_context:
        item["cross_boundary_turn_context"] = dict(cross_boundary_context)
    signals = dict(item.get("signals") or {})
    signals["segment_id"] = segment["id"]
    if item["segment_partial_turn_indices"]:
        signals["segment_partial_turn_indices"] = item["segment_partial_turn_indices"]
    item["signals"] = signals
    if item.get("context"):
        for ctx in item["context"]:
            ctx["segment_id"] = segment["id"]
    return item


def annotate_rag_chunk(chunk: dict, segment: dict, ordinal: int) -> dict:
    item = dict(chunk)
    item["segment_id"] = segment["id"]
    item["segment_ordinal"] = ordinal
    return item


def empty_turn_boundary_diagnostics() -> dict:
    return {
        "has_partial_turn_boundaries": False,
        "partial_segment_count": 0,
        "partial_turn_indices": [],
        "partial_segments": [],
    }


def turn_boundary_diagnostics(
    segments: Sequence[dict],
    boundary_contexts: dict[str, dict] | None = None,
) -> dict:
    partial_segments: list[dict] = []
    partial_turns: set[int] = set()
    boundary_contexts = boundary_contexts or {}
    for segment in segments:
        starts_partial = bool(segment.get("starts_with_partial_turn"))
        ends_partial = bool(segment.get("ends_with_partial_turn"))
        if not starts_partial and not ends_partial:
            continue
        segment_id = segment.get("id")
        turns = _partial_turn_indices(segment)
        partial_turns.update(turns)
        entry = {
            "segment_id": segment_id,
            "start_turn_index": segment.get("start_turn_index"),
            "end_turn_index": segment.get("end_turn_index"),
            "starts_with_partial_turn": starts_partial,
            "ends_with_partial_turn": ends_partial,
            "partial_turn_indices": turns,
        }
        if isinstance(segment_id, str) and segment_id in boundary_contexts:
            entry["adjacent_segment_ids"] = boundary_contexts[segment_id][
                "adjacent_segment_ids"
            ]
        partial_segments.append(entry)

    if not partial_segments:
        return empty_turn_boundary_diagnostics()
    return {
        "has_partial_turn_boundaries": True,
        "partial_segment_count": len(partial_segments),
        "partial_turn_indices": sorted(partial_turns),
        "partial_segments": partial_segments,
    }
