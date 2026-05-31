#!/usr/bin/env python3
"""Sanitized real-history life-wide registry smoke for Stage 2.

This smoke reads a real AIppocampus registry and reports aggregate coverage for
life-wide labels without emitting private message text, titles, source refs, or
absolute paths. It is a readiness diagnostic: labels and timeline groups are
navigation sidecars over clean source, not proof of a user's state.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampuslib import aippocampus_registry_dir
from build_project_timeline import build_project_timeline
from registry import load_registry

NON_TECHNICAL_LIFE_LABELS = tuple(label for label in SCOPE_LABEL_ORDER if label != "technical_work")


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def iter_jsonl_safely(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    if not path.is_file():
        return rows, bad_rows
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
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


def count_manifest_schema(clean_source_dir: Path) -> str:
    manifest_path = clean_source_dir / "manifest.json"
    if not manifest_path.is_file():
        return "missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return "unreadable"
    return str(manifest.get("schema_version") or "unknown")


def summarize_scope_coverage(registry: dict[str, Any]) -> dict[str, Any]:
    label_message_counts: Counter[str] = Counter()
    label_thread_counts: dict[str, set[str]] = {label: set() for label in SCOPE_LABEL_ORDER}
    schema_versions: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    counts: Counter[str] = Counter()

    for index, entry in enumerate(registry.get("threads") or []):
        if not isinstance(entry, dict):
            warnings["non_dict_registry_entry"] += 1
            continue
        thread_id = str(entry.get("thread_key") or f"entry:{index}")
        paths = dict_value(entry.get("paths"))
        messages_value = paths.get("clean_source_messages_jsonl")
        turns_value = paths.get("clean_source_turns_jsonl")
        sqlite_value = paths.get("sqlite")
        graph_value = paths.get("graph_json")

        counts["threads"] += 1
        messages_path = Path(str(messages_value)) if messages_value else None
        turns_path = Path(str(turns_value)) if turns_value else None
        if messages_path:
            counts["clean_source_message_paths"] += 1
        if turns_path:
            counts["clean_source_turn_paths"] += 1
        if messages_path and messages_path.is_file():
            counts["clean_source_messages_exists"] += 1
            schema_versions[count_manifest_schema(messages_path.parent)] += 1
        else:
            warnings["missing_clean_source_messages"] += 1
            continue
        if turns_path and turns_path.is_file():
            counts["clean_source_turns_exists"] += 1
        else:
            warnings["missing_clean_source_turns"] += 1
        if sqlite_value and Path(str(sqlite_value)).is_file():
            counts["sqlite_indexes_exists"] += 1
        if graph_value and Path(str(graph_value)).is_file():
            counts["graph_json_exists"] += 1

        sidecar_path = messages_path.parent / "semantic-scope-labels.jsonl"
        sidecar_rows, sidecar_bad_rows = iter_jsonl_safely(sidecar_path)
        if sidecar_bad_rows:
            warnings["bad_semantic_sidecar_rows"] += sidecar_bad_rows
        if sidecar_rows:
            counts["semantic_sidecar_threads"] += 1
            counts["semantic_sidecar_rows"] += len(sidecar_rows)

        message_rows, bad_rows = iter_jsonl_safely(messages_path)
        if bad_rows:
            warnings["bad_clean_source_message_rows"] += bad_rows
        counts["clean_source_messages"] += len(message_rows)
        thread_seen_labels: set[str] = set()
        for message in message_rows:
            message_labels = [
                str(label)
                for label in message.get("scope_labels") or []
                if isinstance(label, str) and label in SCOPE_LABEL_ORDER
            ]
            semantic_labels = [
                str(label)
                for label in message.get("semantic_scope_labels") or []
                if isinstance(label, str) and label in SCOPE_LABEL_ORDER
            ]
            if message_labels:
                counts["messages_with_scope_labels"] += 1
            if semantic_labels:
                counts["messages_with_semantic_scope_labels"] += 1
            for label in set(message_labels + semantic_labels):
                label_message_counts[label] += 1
                label_thread_counts[label].add(thread_id)
                thread_seen_labels.add(label)
        if thread_seen_labels:
            counts["threads_with_scope_labels"] += 1
        if any(label in NON_TECHNICAL_LIFE_LABELS for label in thread_seen_labels):
            counts["threads_with_non_technical_life_labels"] += 1

    label_summary = {
        label: {
            "message_count": int(label_message_counts.get(label, 0)),
            "thread_count": len(label_thread_counts[label]),
        }
        for label in SCOPE_LABEL_ORDER
        if label_message_counts.get(label, 0) or label_thread_counts[label]
    }
    return {
        "artifact_counts": dict(sorted(counts.items())),
        "clean_source_schema_versions": dict(sorted(schema_versions.items())),
        "scope_label_coverage": {
            "canonical_label_count": len(label_summary),
            "non_technical_life_label_count": len(
                [label for label in label_summary if label in NON_TECHNICAL_LIFE_LABELS]
            ),
            "labels": label_summary,
        },
        "warnings": dict(sorted(warnings.items())),
    }


def summarize_timeline(
    registry_path: Path, *, max_turns_per_thread: int, max_per_life_label: int
) -> dict[str, Any]:
    timeline = build_project_timeline(
        registry_path,
        max_turns_per_thread=max_turns_per_thread,
        max_per_life_label=max_per_life_label,
    )
    life_wide = dict_value(timeline.get("life_wide"))
    label_groups = dict_value(life_wide.get("labels"))
    labels: dict[str, Any] = {}
    source_backed_turns = 0
    semantic_turns = 0
    latest_turns_count = 0
    for label, group in label_groups.items():
        if not isinstance(group, dict):
            continue
        latest_turns = [turn for turn in group.get("latest_turns") or [] if isinstance(turn, dict)]
        latest_turns_count += len(latest_turns)
        source_backed_turns += sum(1 for turn in latest_turns if turn.get("source_refs"))
        semantic_turns += sum(1 for turn in latest_turns if turn.get("semantic_scope_labels"))
        labels[str(label)] = {
            "turn_count": int(group.get("turn_count") or 0),
            "thread_count": int(group.get("thread_count") or 0),
            "project_count": int(group.get("project_count") or 0),
            "latest_turn_count": len(latest_turns),
            "latest_turns_source_backed": sum(
                1 for turn in latest_turns if turn.get("source_refs")
            ),
            "latest_turns_with_semantic_scope_labels": sum(
                1 for turn in latest_turns if turn.get("semantic_scope_labels")
            ),
        }
    return {
        "computed_in_memory": True,
        "project_count": int(timeline.get("project_count") or 0),
        "life_label_count": int(life_wide.get("label_count") or 0),
        "latest_turn_count": latest_turns_count,
        "latest_turns_source_backed": source_backed_turns,
        "latest_turns_with_semantic_scope_labels": semantic_turns,
        "labels": labels,
        "boundary": "Navigation sidecar only; exact claims still require clean-source evidence.",
    }


def determine_evidence_status(
    coverage: dict[str, Any],
    timeline: dict[str, Any] | None,
    *,
    min_life_labels: int,
    min_life_threads: int,
) -> str:
    artifact_counts = dict_value(coverage.get("artifact_counts"))
    if int(artifact_counts.get("threads") or 0) <= 0:
        return "skipped_empty_registry"
    scope = dict_value(coverage.get("scope_label_coverage"))
    non_technical_count = int(scope.get("non_technical_life_label_count") or 0)
    threads_with_life = int(artifact_counts.get("threads_with_non_technical_life_labels") or 0)
    if non_technical_count < min_life_labels or threads_with_life < min_life_threads:
        return "insufficient_scope_label_coverage"
    if timeline:
        life_label_count = int(timeline.get("life_label_count") or 0)
        source_backed_turns = int(timeline.get("latest_turns_source_backed") or 0)
        if life_label_count < min_life_labels or source_backed_turns <= 0:
            return "insufficient_timeline_coverage"
    return "sufficient"


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def coverage_ratios(coverage: dict[str, Any], timeline: dict[str, Any] | None) -> dict[str, Any]:
    """Machine-readable claim guard for aggregate Stage 2 evidence.

    `sufficient` means the smoke found real source-backed life-wide evidence,
    not that the whole registry has been semantically refreshed. Keep these
    ratios close to the raw counts so future release notes cannot quietly turn a
    slice-level diagnostic into a full-history claim.
    """

    artifact_counts = dict_value(coverage.get("artifact_counts"))
    timeline_counts = dict_value(timeline)
    thread_count = int(artifact_counts.get("threads") or 0)
    message_count = int(artifact_counts.get("clean_source_messages") or 0)
    timeline_turns = int(timeline_counts.get("latest_turn_count") or 0)
    semantic_sidecar_rows = int(artifact_counts.get("semantic_sidecar_rows") or 0)
    return {
        "labeled_message_ratio": ratio(
            int(artifact_counts.get("messages_with_scope_labels") or 0), message_count
        ),
        "life_labeled_thread_ratio": ratio(
            int(artifact_counts.get("threads_with_non_technical_life_labels") or 0), thread_count
        ),
        "scope_labeled_thread_ratio": ratio(
            int(artifact_counts.get("threads_with_scope_labels") or 0), thread_count
        ),
        "semantic_sidecar_thread_ratio": ratio(
            int(artifact_counts.get("semantic_sidecar_threads") or 0), thread_count
        ),
        "semantic_sidecar_row_count": semantic_sidecar_rows,
        "source_backed_timeline_turn_ratio": ratio(
            int(timeline_counts.get("latest_turns_source_backed") or 0), timeline_turns
        ),
        "semantic_timeline_turn_ratio": ratio(
            int(timeline_counts.get("latest_turns_with_semantic_scope_labels") or 0),
            timeline_turns,
        ),
    }


def claim_level_for_status(status: str) -> str:
    if status == "sufficient":
        return "first_pass_real_history_slice"
    if status.startswith("skipped_"):
        return "no_real_registry_evidence"
    return "diagnostic_only"


def cannot_claim_for_stage2(status: str) -> list[str]:
    claims = [
        "full_history_refresh",
        "semantic_completeness",
        "label_correctness_without_clean_source_review",
    ]
    if status != "sufficient":
        claims.append("stage2_life_wide_readiness")
    return claims


def run_life_wide_registry_smoke(
    registry_path: str | Path | None = None,
    *,
    compute_timeline: bool = True,
    require_evidence: bool = False,
    min_life_labels: int = 2,
    min_life_threads: int = 2,
    max_turns_per_thread: int = 5,
    max_per_life_label: int = 20,
) -> dict[str, Any]:
    path = (
        Path(registry_path).resolve()
        if registry_path
        else (aippocampus_registry_dir() / "threads.json").resolve()
    )
    privacy_boundary = {
        "raw_text_emitted": False,
        "snippets_emitted": False,
        "titles_emitted": False,
        "source_reference_details_emitted": False,
        "absolute_paths_emitted": False,
        "output_shape": "aggregate_counts_only",
    }
    if not path.is_file():
        status = "skipped_missing_registry"
        coverage = {
            "artifact_counts": {},
            "clean_source_schema_versions": {},
            "scope_label_coverage": {
                "canonical_label_count": 0,
                "non_technical_life_label_count": 0,
                "labels": {},
            },
            "warnings": {"missing_registry": 1},
        }
        return {
            "ok": not require_evidence,
            "stage2_evidence_status": status,
            "claim_level": claim_level_for_status(status),
            "cannot_claim": cannot_claim_for_stage2(status),
            "privacy_boundary": privacy_boundary,
            "registry": {"exists": False},
            "artifact_counts": {},
            "scope_label_coverage": {
                "canonical_label_count": 0,
                "non_technical_life_label_count": 0,
                "labels": {},
            },
            "timeline_coverage": None,
            "coverage_ratios": coverage_ratios(coverage, None),
            "warnings": {"missing_registry": 1},
        }

    registry = load_registry(path)
    coverage = summarize_scope_coverage(registry)
    timeline = (
        summarize_timeline(
            path, max_turns_per_thread=max_turns_per_thread, max_per_life_label=max_per_life_label
        )
        if compute_timeline
        else None
    )
    status = determine_evidence_status(
        coverage,
        timeline,
        min_life_labels=min_life_labels,
        min_life_threads=min_life_threads,
    )
    return {
        "ok": status == "sufficient" or not require_evidence,
        "stage2_evidence_status": status,
        "claim_level": claim_level_for_status(status),
        "cannot_claim": cannot_claim_for_stage2(status),
        "privacy_boundary": privacy_boundary,
        "registry": {"exists": True},
        "artifact_counts": coverage["artifact_counts"],
        "clean_source_schema_versions": coverage["clean_source_schema_versions"],
        "scope_label_coverage": coverage["scope_label_coverage"],
        "timeline_coverage": timeline,
        "coverage_ratios": coverage_ratios(coverage, timeline),
        "thresholds": {
            "min_life_labels": min_life_labels,
            "min_life_threads": min_life_threads,
            "require_evidence": require_evidence,
        },
        "warnings": coverage["warnings"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        help="Path to threads.json. Defaults to CODEX_HOME/aippocampus-registry/threads.json.",
    )
    parser.add_argument("--no-compute-timeline", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--min-life-labels", type=int, default=2)
    parser.add_argument("--min-life-threads", type=int, default=2)
    parser.add_argument("--max-turns-per-thread", type=int, default=5)
    parser.add_argument("--max-per-life-label", type=int, default=20)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_life_wide_registry_smoke(
        args.registry,
        compute_timeline=not args.no_compute_timeline,
        require_evidence=args.require_evidence,
        min_life_labels=args.min_life_labels,
        min_life_threads=args.min_life_threads,
        max_turns_per_thread=args.max_turns_per_thread,
        max_per_life_label=args.max_per_life_label,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"life-wide registry smoke: {result.get('stage2_evidence_status')}")
        print(f"ok: {result.get('ok')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
