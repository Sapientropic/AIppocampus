#!/usr/bin/env python3
"""Aggregate private-history Episode/Arc adjudication for #663.

The runner reads local registry clean-source messages/events and reports only
counts, buckets, and claim boundaries. It never serializes source text, source
refs, event ids, thread ids, local paths, or source-ref hash samples.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from aippocampus_runtime.coding import decision_events, episode_arcs, sequence_reopen
from aippocampus_runtime.core import aippocampus_registry_dir, now_utc
from aippocampus_runtime.registry.api import load_registry, registry_paths, unique_preserve

REPORT_KIND = "aippocampus_episode_arc_private_history_adjudication_report"
SCHEMA_VERSION = 1
DEFAULT_MAX_THREADS = 100
DEFAULT_MAX_LINE_GAP = 3_000


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    if not path.is_file():
        return rows, bad_rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                bad_rows += 1
                continue
            if isinstance(item, dict):
                rows.append(item)
            else:
                bad_rows += 1
    return rows, bad_rows


def _path_from_entry(entry: Mapping[str, Any], key: str) -> Path | None:
    raw = _as_mapping(entry.get("paths")).get(key)
    return Path(str(raw)) if raw else None


def _source_line(row: Mapping[str, Any]) -> int | None:
    for key in ("source_line", "line", "raw_start_line", "clean_ordinal"):
        if (value := _as_int(row.get(key))) is not None:
            return value
    return None


def _first_ref_line(candidate: Mapping[str, Any]) -> int | None:
    lines = [
        line
        for ref in _as_list(candidate.get("source_refs"))
        if isinstance(ref, Mapping)
        if (line := _source_line(ref)) is not None
    ]
    return min(lines) if lines else None


def _source_ref_for_behavior(thread_key: str, row: Mapping[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {"thread_key": thread_key}
    for key in ("turn_id", "turn_index", "source_line", "line", "timestamp"):
        value = row.get(key)
        if value is not None and value != "":
            ref[key] = value
    return ref


def _event_row_from_behavior(
    thread_key: str,
    row: Mapping[str, Any],
    *,
    episode_id: str,
    event_kind: str | None = None,
) -> dict[str, Any]:
    line = _source_line(row)
    event_id = str(row.get("event_id") or row.get("id") or "")
    return {
        "episode_id": episode_id,
        "event_id": event_id,
        "event_kind": event_kind or str(row.get("event_kind") or ""),
        "hard_event_kind": row.get("hard_event_kind"),
        "status": row.get("status"),
        "exit_code": row.get("exit_code"),
        "command_class": row.get("command_class"),
        "target_class": row.get("target_class"),
        "failure_family": row.get("failure_family"),
        "sequence_index": line,
        "source_refs": [_source_ref_for_behavior(thread_key, row)],
        "origin": "behavior_event",
    }


def _event_row_from_decision(candidate: Mapping[str, Any], *, episode_id: str) -> dict[str, Any]:
    line = _first_ref_line(candidate)
    return {
        "episode_id": episode_id,
        "decision_id": str(candidate.get("decision_id") or ""),
        "event_type": str(candidate.get("event_type") or ""),
        "sequence_index": line,
        "source_refs": list(_as_list(candidate.get("source_refs"))),
        "affected_scope": dict(_as_mapping(candidate.get("affected_scope"))),
        "origin": "coding_decision_event",
    }


def _failed_behavior_events(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for row in rows:
        status = str(row.get("status") or "").casefold()
        hard_kind = str(row.get("hard_event_kind") or "").casefold()
        exit_code = _as_int(row.get("exit_code"))
        if status == "failed" or hard_kind == "tool_call_failed" or (exit_code is not None and exit_code != 0):
            out.append(row)
    return out


def _requested_by_call_ref(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    requested: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if str(row.get("event_kind") or "") != "tool_call_requested":
            continue
        call_ref = str(row.get("call_ref") or "")
        if call_ref:
            requested[call_ref] = row
    return requested


def _nearest_failed_before(
    failed_rows: Sequence[Mapping[str, Any]],
    decision_line: int | None,
    *,
    max_line_gap: int,
) -> Mapping[str, Any] | None:
    if decision_line is None:
        return failed_rows[-1] if failed_rows else None
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for row in failed_rows:
        line = _source_line(row)
        if line is None or line > decision_line:
            continue
        gap = decision_line - line
        if gap <= max(0, max_line_gap):
            candidates.append((line, row))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _episode_rows_for_rejected_decision(
    thread_key: str,
    candidate: Mapping[str, Any],
    *,
    failed_rows: Sequence[Mapping[str, Any]],
    requested: Mapping[str, Mapping[str, Any]],
    max_line_gap: int,
) -> list[dict[str, Any]]:
    decision_id = str(candidate.get("decision_id") or "")
    episode_id = f"private_history:{decision_id or _first_ref_line(candidate) or 'unknown'}"
    rows: list[dict[str, Any]] = []
    failed = _nearest_failed_before(
        failed_rows,
        _first_ref_line(candidate),
        max_line_gap=max_line_gap,
    )
    if failed is not None:
        call_ref = str(failed.get("call_ref") or "")
        request = requested.get(call_ref)
        if request is not None:
            rows.append(
                _event_row_from_behavior(
                    thread_key,
                    request,
                    episode_id=episode_id,
                    event_kind="attempted_route",
                )
            )
        rows.append(_event_row_from_behavior(thread_key, failed, episode_id=episode_id))
    rows.append(_event_row_from_decision(candidate, episode_id=episode_id))
    return rows


def _count_values(items: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(item.get(field) or "unknown") for item in items)
    return dict(sorted(counts.items()))


def _gap_counts(arcs: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for arc in arcs:
        for gap in _as_list(arc.get("sequence_gaps")):
            counts[str(gap)] += 1
    return dict(sorted(counts.items()))


def _safe_use_counts(arcs: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for arc in arcs:
        plan = episode_arcs.build_reopen_plan(arc)
        for safe_use in _as_list(plan.get("safe_uses")):
            counts[str(safe_use)] += 1
    return dict(sorted(counts.items()))


def _sequence_resolution_counts(arcs: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for arc in arcs:
        packet = episode_arcs.render_sequence_packet(arc, trigger="private_history_adjudication")
        plan = sequence_reopen.build_sequence_packet_reopen_plan(packet, source_catalog=[arc])
        counts[str(plan.get("resolution_status") or "unknown")] += 1
    return dict(sorted(counts.items()))


def _thread_entries(registry: Mapping[str, Any], max_threads: int) -> list[Mapping[str, Any]]:
    entries = [entry for entry in _as_list(registry.get("threads")) if isinstance(entry, Mapping)]
    return entries[: max(0, max_threads)]


def build_private_history_episode_arc_adjudication_report(
    registry: Mapping[str, Any],
    *,
    max_threads: int = DEFAULT_MAX_THREADS,
    max_line_gap: int = DEFAULT_MAX_LINE_GAP,
) -> dict[str, Any]:
    """Build a public-safe aggregate readout over local private history."""

    all_episode_rows: list[dict[str, Any]] = []
    metrics: Counter[str] = Counter()
    bad_json_rows = 0
    for entry in _thread_entries(registry, max_threads):
        thread_key = str(entry.get("thread_key") or "")
        if not thread_key:
            continue
        metrics["thread_count_scanned"] += 1
        messages_path = _path_from_entry(entry, "clean_source_messages_jsonl")
        events_path = _path_from_entry(entry, "clean_source_events_jsonl")
        message_rows: list[dict[str, Any]] = []
        behavior_rows: list[dict[str, Any]] = []
        if messages_path and messages_path.is_file():
            message_rows, bad_rows = _read_jsonl(messages_path)
            bad_json_rows += bad_rows
            metrics["threads_with_clean_messages"] += 1
            metrics["message_rows_scanned"] += len(message_rows)
        if events_path and events_path.is_file():
            behavior_rows, bad_rows = _read_jsonl(events_path)
            bad_json_rows += bad_rows
            metrics["threads_with_clean_events"] += 1
            metrics["behavior_event_rows_scanned"] += len(behavior_rows)

        decisions = decision_events.extract_decision_candidates(
            message_rows,
            thread_key=thread_key,
            workspace=str(entry.get("workspace_name") or ""),
        )
        rejected = [
            candidate
            for candidate in decisions
            if str(candidate.get("event_type") or "") in {"rejected_route", "do_not_repeat"}
        ]
        metrics["decision_candidate_count"] += len(decisions)
        metrics["rejected_decision_candidate_count"] += len(rejected)
        failed_rows = _failed_behavior_events(behavior_rows)
        requested = _requested_by_call_ref(behavior_rows)
        metrics["failed_behavior_event_count"] += len(failed_rows)
        for candidate in rejected:
            rows = _episode_rows_for_rejected_decision(
                thread_key,
                candidate,
                failed_rows=failed_rows,
                requested=requested,
                max_line_gap=max_line_gap,
            )
            if len(rows) > 1:
                metrics["rejected_decision_with_failed_behavior_chain_count"] += 1
            all_episode_rows.extend(rows)

    arcs = episode_arcs.build_episode_arcs(all_episode_rows)
    complete_arcs = [arc for arc in arcs if not arc.get("sequence_gaps")]
    rejected_route_arcs = [
        arc for arc in arcs if str(arc.get("episode_kind") or "") == "rejected_route_arc"
    ]
    complete_rejected_route_arcs = [
        arc for arc in rejected_route_arcs if not arc.get("sequence_gaps")
    ]
    status = (
        "measured_public_safe_aggregate"
        if metrics["thread_count_scanned"] and metrics["message_rows_scanned"]
        else "insufficient_real_history"
    )
    source_ref_count = sum(len(_as_list(arc.get("source_refs"))) for arc in arcs)
    sequence_resolution_counts = _sequence_resolution_counts(arcs)
    safe_use_counts = _safe_use_counts(arcs)
    return {
        "ok": True,
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "created_at": now_utc(),
        "status": status,
        "input_surface": {
            "thread_count_scanned": int(metrics["thread_count_scanned"]),
            "threads_with_clean_messages": int(metrics["threads_with_clean_messages"]),
            "threads_with_clean_events": int(metrics["threads_with_clean_events"]),
            "message_rows_scanned": int(metrics["message_rows_scanned"]),
            "behavior_event_rows_scanned": int(metrics["behavior_event_rows_scanned"]),
            "bad_json_row_count": bad_json_rows,
            "max_threads": max(0, max_threads),
            "max_line_gap": max(0, max_line_gap),
        },
        "metrics": {
            "decision_candidate_count": int(metrics["decision_candidate_count"]),
            "rejected_decision_candidate_count": int(metrics["rejected_decision_candidate_count"]),
            "failed_behavior_event_count": int(metrics["failed_behavior_event_count"]),
            "rejected_decision_with_failed_behavior_chain_count": int(
                metrics["rejected_decision_with_failed_behavior_chain_count"]
            ),
            "episode_arc_count": len(arcs),
            "rejected_route_arc_count": len(rejected_route_arcs),
            "complete_arc_count": len(complete_arcs),
            "gappy_arc_count": len(arcs) - len(complete_arcs),
            "complete_rejected_route_arc_count": len(complete_rejected_route_arcs),
            "source_ref_count": source_ref_count,
            "sequence_packet_reopen_complete_count": int(sequence_resolution_counts.get("complete") or 0),
            "remind_safe_use_count": int(safe_use_counts.get("remind") or 0),
        },
        "episode_kind_counts": _count_values(arcs, "episode_kind"),
        "origin_counts": _count_values(arcs, "origin"),
        "current_validity_counts": _count_values(arcs, "current_validity"),
        "outcome_counts": _count_values(arcs, "outcome"),
        "sequence_gap_counts": _gap_counts(arcs),
        "sequence_packet_reopen_resolution_counts": sequence_resolution_counts,
        "safe_use_counts": safe_use_counts,
        "issue_readouts": {
            "github_663": {
                "private_history_adjudication": status,
                "complete_rejected_route_arc_count": len(complete_rejected_route_arcs),
                "gappy_arc_count": len(arcs) - len(complete_arcs),
                "source_reopen_from_sequence_packet": "aggregate_measured",
                "live_host_behavior": "not_measured",
                "closeout_eligible": False,
            }
        },
        "privacy_boundary": {
            "aggregate_only": True,
            "raw_source_text_emitted": False,
            "raw_command_text_emitted": False,
            "source_refs_emitted": False,
            "source_ref_hash_samples_emitted": False,
            "event_ids_emitted": False,
            "thread_ids_emitted": False,
            "local_paths_emitted": False,
        },
        "contract": {
            "episode_arcs_are_read_models": True,
            "sequence_packets_are_navigation_only": True,
            "current_validity_requires_source_reopen": True,
            "source_truth_unchanged": True,
            "formal_memory_promoted": False,
        },
        "cannot_claim": unique_preserve(
            [
                "broad_episode_arc_owner_complete",
                "live_host_behavior_lift",
                "user_visible_recall_lift",
                "current_validity_without_source_reopen",
                "episode_arc_as_truth_layer",
                "private_history_generalizes_beyond_this_registry",
            ],
            limit=12,
        ),
    }


def _resolve_registry_path(raw: str | None) -> Path:
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_file() else registry_paths(path)[0]
    return registry_paths(aippocampus_registry_dir())[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", help="Registry file or directory. Defaults to AIppocampus registry.")
    parser.add_argument("--max-threads", type=int, default=DEFAULT_MAX_THREADS)
    parser.add_argument("--max-line-gap", type=int, default=DEFAULT_MAX_LINE_GAP)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    registry_path = _resolve_registry_path(args.registry)
    report = build_private_history_episode_arc_adjudication_report(
        load_registry(registry_path),
        max_threads=args.max_threads,
        max_line_gap=args.max_line_gap,
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    if args.json_output or not args.output:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
