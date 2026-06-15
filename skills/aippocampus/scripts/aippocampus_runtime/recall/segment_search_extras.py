"""Opt-in segment search sidecars kept out of the main search runner."""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.outcome_feedback import (
    build_recall_outcome_event,
    write_recall_outcome_event,
)
from aippocampus_runtime.recall.query_expansion import (
    load_source_factual_alias_rows,
    plan_query_expansion,
)

SOURCE_FACTUAL_ALIASES_FILENAME = "source-factual-aliases.jsonl"


def add_sidecar_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-aliases",
        default=None,
        help="Optional source-backed factual alias JSONL path for query expansion.",
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


def query_expansion_plan(
    query_terms: Sequence[str],
    *,
    seed_terms: Sequence[str],
    source_aliases: str | Path | None,
    cwd: Path,
) -> dict[str, Any]:
    alias_path = source_factual_aliases_path(source_aliases, cwd)
    return plan_query_expansion(
        query_terms,
        seed_terms=seed_terms,
        source_alias_rows=load_source_factual_alias_rows(alias_path),
    )


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
