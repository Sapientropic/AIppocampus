#!/usr/bin/env python3
"""Executable long-thread segment build/search soak for #376.

The default profile creates a small public-safe rollout-shaped file, builds
real segment SQLite shards, and compares full fanout, budgeted fanout, and an
optional monolithic index. It is a CI-safe contract smoke, not a GB performance
claim; larger local runs can raise the turn/message budgets explicitly.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import statistics
import time
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc  # noqa: E402
from aippocampus_runtime.recall import (  # noqa: E402
    index_builder,
    segment_builder,
    segment_search,
)
from aippocampus_runtime.recall.retrieval import (  # noqa: E402
    search_hybrid_index,
    split_query_terms,
)
from aippocampus_runtime.source.rollout import normalize_rollout  # noqa: E402

MIN_SEGMENT_BYTES = 1024 * 1024
DEFAULT_TURN_COUNT = 160
DEFAULT_SEGMENT_MAX_MESSAGES = 50
DEFAULT_QUERY_LIMIT = 6
DEFAULT_FANOUT_BUDGET = 2


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _marker_for_turn(turn: int, *, turn_count: int, segment_max_messages: int) -> list[str]:
    middle_turn = max(2, turn_count // 2)
    boundary_turn = max(2, segment_max_messages // 2 + 1)
    markers: list[str] = []
    if turn == 3:
        markers.append("SOAK_EARLY_BEACON")
    if turn == middle_turn:
        markers.append("SOAK_MIDDLE_BEACON")
    if turn == turn_count - 2:
        markers.append("SOAK_LATE_BEACON")
    if turn == boundary_turn:
        markers.append("SOAK_BOUNDARY_BEACON")
    if turn in {5, turn_count - 3}:
        markers.append("SOAK_DUPLICATE_BEACON")
    if turn == 4:
        markers.append("SOAK_SUPERSEDED_OLD")
    if turn == turn_count - 4:
        markers.append("SOAK_SUPERSEDED_CURRENT")
    return markers


def write_public_safe_rollout(
    path: Path,
    *,
    workspace: Path,
    turn_count: int,
    segment_max_messages: int,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    query_cases = [
        {"id": "early", "query": "SOAK_EARLY_BEACON", "expected_token": "SOAK_EARLY_BEACON"},
        {
            "id": "middle",
            "query": "SOAK_MIDDLE_BEACON",
            "expected_token": "SOAK_MIDDLE_BEACON",
        },
        {"id": "late", "query": "SOAK_LATE_BEACON", "expected_token": "SOAK_LATE_BEACON"},
        {
            "id": "boundary",
            "query": "SOAK_BOUNDARY_BEACON",
            "expected_token": "SOAK_BOUNDARY_BEACON",
        },
        {
            "id": "duplicate",
            "query": "SOAK_DUPLICATE_BEACON",
            "expected_token": "SOAK_DUPLICATE_BEACON",
        },
        {
            "id": "superseded_current",
            "query": "SOAK_SUPERSEDED_CURRENT",
            "expected_token": "SOAK_SUPERSEDED_CURRENT",
        },
    ]
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            _json_line(
                {
                    "type": "session_meta",
                    "timestamp": "2026-06-06T00:00:00Z",
                    "payload": {
                        "id": "public-long-thread-segment-soak",
                        "cwd": str(workspace),
                    },
                }
            )
        )
        for turn in range(1, turn_count + 1):
            markers = _marker_for_turn(
                turn,
                turn_count=turn_count,
                segment_max_messages=segment_max_messages,
            )
            marker_text = " ".join(markers) if markers else f"SOAK_BACKGROUND_{turn:04d}"
            f.write(
                _json_line(
                    {
                        "type": "event_msg",
                        "timestamp": f"2026-06-06T00:{turn % 60:02d}:00Z",
                        "payload": {
                            "type": "user_message",
                            "message": (
                                f"Public-safe synthetic turn {turn}. "
                                f"{marker_text}. "
                                "This generated row models a long-lived thread without private text."
                            ),
                        },
                    }
                )
            )
            f.write(
                _json_line(
                    {
                        "type": "event_msg",
                        "timestamp": f"2026-06-06T00:{turn % 60:02d}:30Z",
                        "payload": {
                            "type": "agent_message",
                            "phase": "final_answer",
                            "message": (
                                f"Public-safe synthetic answer {turn}. "
                                f"{marker_text}. "
                                "The answer repeats the marker so final-answer recall stays measurable."
                            ),
                        },
                    }
                )
            )
    return {"turn_count": turn_count, "query_cases": query_cases}


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _build_segments(
    *,
    workspace: Path,
    rollout: Path,
    segments_dir: Path,
    segment_max_messages: int,
    segment_bytes: int,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    argv = [
        "--cwd",
        str(workspace),
        "--rollout",
        str(rollout),
        "--output-dir",
        str(segments_dir),
        "--segment-bytes",
        str(max(MIN_SEGMENT_BYTES, segment_bytes)),
        "--max-messages",
        str(max(50, segment_max_messages)),
        "--no-rag-cache",
        "--json",
    ]
    # The builder prints a manifest containing absolute staging paths. Keep that
    # local-only and reload the sanitized manifest through the segment pointer.
    with contextlib.redirect_stdout(io.StringIO()):
        code = segment_builder.main(argv)
    if code != 0:
        raise RuntimeError(f"segment builder failed with exit code {code}")
    elapsed = _elapsed_ms(started)
    pointer = json.loads((segments_dir / "segments.pointer.json").read_text(encoding="utf-8"))
    manifest_path = segments_dir / pointer["current"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest, elapsed


def _build_monolithic_index(
    *,
    rollout: Path,
    index_path: Path,
) -> tuple[Path, float]:
    started = time.perf_counter()
    messages, turns = normalize_rollout(rollout)
    index_builder.make_sqlite(index_path, messages, [], turns, rag_cache=False)
    return index_path, _elapsed_ms(started)


def _hit_for_token(matches: list[dict[str, Any]], token: str) -> bool:
    for item in matches:
        snippet = str(item.get("snippet") or "")
        if token in snippet:
            return True
    return False


def _compact_query_result(payload: dict[str, Any], *, expected_token: str) -> dict[str, Any]:
    matches = list(payload.get("matches") or [])
    fanout = dict(payload.get("fanout") or {})
    return {
        "status": payload.get("status"),
        "hit": _hit_for_token(matches, expected_token),
        "match_count": len(matches),
        "top_segment_id": str(matches[0].get("segment_id") or "") if matches else "",
        "fanout": {
            "mode": fanout.get("mode"),
            "planned_segment_count": fanout.get("planned_segment_count", 0),
            "searched_segment_count": fanout.get("searched_segment_count", 0),
            "skipped_segment_count": fanout.get("skipped_segment_count", 0),
            "budget_exhausted": bool(fanout.get("budget_exhausted")),
        },
    }


def _search_segments(
    *,
    workspace: Path,
    segments_dir: Path,
    query_cases: list[dict[str, str]],
    fanout_budget: int,
    full_fanout: bool,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    for case in query_cases:
        payload = segment_search.search_segments_payload(
            segment_search.SegmentSearchOptions(
                patterns=[case["query"]],
                cwd=workspace,
                segments_dir=segments_dir,
                build_segments=False,
                mode="hybrid",
                per_segment=4,
                candidate_max=24,
                rag_context=0,
                max_results=8,
                snippet_chars=260,
                fanout_budget=fanout_budget,
                full_fanout=full_fanout,
            )
        )
        results.append(
            {
                "id": case["id"],
                "expected_token": case["expected_token"],
                **_compact_query_result(payload, expected_token=case["expected_token"]),
            }
        )
    return results, _elapsed_ms(started)


def _search_monolithic(
    *,
    index_path: Path,
    query_cases: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    for case in query_cases:
        terms = split_query_terms([case["query"]])
        matches = search_hybrid_index(
            index_path,
            terms,
            terms,
            [],
            limit=8,
            candidate_limit=24,
            snippet_chars=260,
            context_radius=0,
            use_rag_chunks=False,
        )
        results.append(
            {
                "id": case["id"],
                "expected_token": case["expected_token"],
                "status": "ok",
                "hit": _hit_for_token(matches, case["expected_token"]),
                "match_count": len(matches),
            }
        )
    return results, _elapsed_ms(started)


def _hit_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row.get("hit")) / len(rows), 6)


def _agreement_rate(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> float | None:
    if not left or not right:
        return None
    right_hits = {str(row.get("id")): bool(row.get("hit")) for row in right}
    comparable = [row for row in left if str(row.get("id")) in right_hits]
    if not comparable:
        return None
    agreed = sum(1 for row in comparable if bool(row.get("hit")) == right_hits[str(row.get("id"))])
    return round(agreed / len(comparable), 6)


def _p50_p95(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0}
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))]
    return {"p50": round(float(p50), 3), "p95": round(float(p95), 3)}


def run_long_thread_segment_soak(
    *,
    workspace: Path,
    turn_count: int = DEFAULT_TURN_COUNT,
    segment_max_messages: int = DEFAULT_SEGMENT_MAX_MESSAGES,
    segment_bytes: int = MIN_SEGMENT_BYTES,
    fanout_budget: int = DEFAULT_FANOUT_BUDGET,
    query_limit: int = DEFAULT_QUERY_LIMIT,
    include_monolithic: bool = True,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_root = workspace / ".tmp" / "long-thread-segment-soak"
    rollout = artifact_root / "rollout.jsonl"
    segments_dir = artifact_root / "segments"
    monolithic_index = artifact_root / "monolithic.sqlite"
    fixture = write_public_safe_rollout(
        rollout,
        workspace=workspace,
        turn_count=max(12, int(turn_count)),
        segment_max_messages=max(50, int(segment_max_messages)),
    )
    query_cases = fixture["query_cases"][: max(1, int(query_limit))]

    manifest, segment_build_ms = _build_segments(
        workspace=workspace,
        rollout=rollout,
        segments_dir=segments_dir,
        segment_max_messages=segment_max_messages,
        segment_bytes=segment_bytes,
    )
    full_rows, full_ms = _search_segments(
        workspace=workspace,
        segments_dir=segments_dir,
        query_cases=query_cases,
        fanout_budget=fanout_budget,
        full_fanout=True,
    )
    budgeted_rows, budgeted_ms = _search_segments(
        workspace=workspace,
        segments_dir=segments_dir,
        query_cases=query_cases,
        fanout_budget=fanout_budget,
        full_fanout=False,
    )
    monolithic_rows: list[dict[str, Any]] = []
    monolithic_build_ms = 0.0
    monolithic_ms = 0.0
    if include_monolithic:
        _, monolithic_build_ms = _build_monolithic_index(
            rollout=rollout,
            index_path=monolithic_index,
        )
        monolithic_rows, monolithic_ms = _search_monolithic(
            index_path=monolithic_index,
            query_cases=query_cases,
        )

    quality_metrics = {
        "query_count": len(query_cases),
        "full_fanout_hit_rate": _hit_rate(full_rows),
        "budgeted_fanout_hit_rate": _hit_rate(budgeted_rows),
        "monolithic_hit_rate": _hit_rate(monolithic_rows) if include_monolithic else None,
        "full_vs_monolithic_agreement_rate": (
            _agreement_rate(full_rows, monolithic_rows) if include_monolithic else None
        ),
        "budgeted_vs_full_agreement_rate": _agreement_rate(budgeted_rows, full_rows),
    }
    quality_gate_ok = bool(
        quality_metrics["full_fanout_hit_rate"] == 1.0
        and (
            not include_monolithic
            or quality_metrics["full_vs_monolithic_agreement_rate"] is not None
            and quality_metrics["full_vs_monolithic_agreement_rate"] >= 0.75
        )
    )
    quality_metrics["quality_gate_ok"] = quality_gate_ok
    query_wall_values = [full_ms / max(1, len(query_cases)), budgeted_ms / max(1, len(query_cases))]
    if include_monolithic:
        query_wall_values.append(monolithic_ms / max(1, len(query_cases)))

    segment_count = int(manifest.get("segment_count") or len(manifest.get("segments") or []))
    return {
        "schema_version": 1,
        "kind": "aippocampus_long_thread_segment_soak",
        "created_at": now_utc(),
        "ok": quality_gate_ok,
        "status": "passed" if quality_gate_ok else "quality_gate_failed",
        "data_boundary": {
            "input_shape": "public_safe_generated_rollout",
            "turn_count": int(fixture["turn_count"]),
            "message_count": int(manifest.get("message_count") or 0),
            "simulated_parts": [
                "public-safe generated text",
                "small PR-tier physical file size",
                "synthetic marker query cases",
            ],
            "real_file_parts": [
                "rollout-shaped JSONL written to disk",
                "segment SQLite shards built through segment_builder",
                "segmented search through segment_search_payload",
                "optional monolithic SQLite comparison",
            ],
            "larger_local_mode_available": True,
        },
        "capacity_metrics": {
            "rollout_bytes": int(rollout.stat().st_size),
            "segment_count": segment_count,
            "segment_max_messages": max(50, int(segment_max_messages)),
            "segment_bytes": max(MIN_SEGMENT_BYTES, int(segment_bytes)),
            "worst_case_sqlite_handles": segment_count,
            "fanout_budget": int(fanout_budget),
            "budgeted_sqlite_handles": min(segment_count, int(fanout_budget)),
        },
        "timing_ms": {
            "segment_build_wall": segment_build_ms,
            "monolithic_build_wall": monolithic_build_ms if include_monolithic else None,
            "full_fanout_query_wall": full_ms,
            "budgeted_fanout_query_wall": budgeted_ms,
            "monolithic_query_wall": monolithic_ms if include_monolithic else None,
            "query_wall_per_case": _p50_p95(query_wall_values),
        },
        "quality_metrics": quality_metrics,
        "query_modes": {
            "full_fanout": {"queries": full_rows},
            "budgeted_fanout": {"queries": budgeted_rows},
            **({"monolithic": {"queries": monolithic_rows}} if include_monolithic else {}),
        },
        "privacy_boundary": {
            "reads_private_registry": False,
            "reads_private_rollouts": False,
            "emits_private_text": False,
            "emits_absolute_paths": False,
            "output_shape": "sanitized_long_thread_segment_soak_metrics",
        },
        "cannot_claim": [
            "real_gb_registry_runtime",
            "real_tb_registry_runtime",
            "private_history_segment_quality",
            "windows_interrupted_rebuild_recovery",
            "real_file_fixture_not_gb_claim",
            "budgeted_fanout_is_not_full_quality_claim",
        ],
        "issue": "#376",
    }


def render_text(payload: dict[str, Any]) -> str:
    capacity = payload["capacity_metrics"]
    quality = payload["quality_metrics"]
    timing = payload["timing_ms"]
    return "\n".join(
        [
            "AIppocampus long-thread segment soak",
            f"- status: {payload['status']}",
            f"- segments: {capacity['segment_count']} from {capacity['rollout_bytes']} bytes",
            f"- fanout: budget {capacity['fanout_budget']} / worst {capacity['worst_case_sqlite_handles']}",
            f"- build ms: segmented {timing['segment_build_wall']}",
            f"- hit rate: full {quality['full_fanout_hit_rate']} / budgeted {quality['budgeted_fanout_hit_rate']}",
            f"- monolithic hit rate: {quality['monolithic_hit_rate']}",
            "- boundary: public-safe generated fixture; not a GB/private-history claim",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(".tmp/long-thread-segment-soak-workspace"))
    parser.add_argument("--turn-count", type=int, default=DEFAULT_TURN_COUNT)
    parser.add_argument("--segment-max-messages", type=int, default=DEFAULT_SEGMENT_MAX_MESSAGES)
    parser.add_argument("--segment-bytes", type=int, default=MIN_SEGMENT_BYTES)
    parser.add_argument("--fanout-budget", type=int, default=DEFAULT_FANOUT_BUDGET)
    parser.add_argument("--query-limit", type=int, default=DEFAULT_QUERY_LIMIT)
    parser.add_argument("--no-monolithic", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    payload = run_long_thread_segment_soak(
        workspace=args.workspace,
        turn_count=args.turn_count,
        segment_max_messages=args.segment_max_messages,
        segment_bytes=args.segment_bytes,
        fanout_budget=args.fanout_budget,
        query_limit=args.query_limit,
        include_monolithic=not args.no_monolithic,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
