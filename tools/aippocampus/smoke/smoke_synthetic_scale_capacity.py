#!/usr/bin/env python3
"""Synthetic GB-scale capacity smoke for AIppocampus.

This command does not create large files and does not read private registry
content. It models aggregate clean-source, generated-index, sync-policy, segment,
and fanout growth so threshold language can be tested in CI-safe slices before
real GB/TB long runs exist.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampuslib import now_utc
from storage_capacity_report import human_bytes, ratio

GIB = 1024**3
MIB = 1024**2


def threshold_state(value: float, warning: float, blocker: float | None = None) -> str:
    if blocker is not None and value >= blocker:
        return "blocker"
    if value >= warning:
        return "warning"
    return "pass"


def build_synthetic_scale_capacity_smoke(
    *,
    clean_source_gib: float = 4.0,
    thread_count: int = 128,
    generated_index_ratio: float = 0.6,
    segment_size_mib: int = 64,
    sync_policy_ratio: float = 0.35,
    fanout_budget: int = 64,
    generated_index_warning_ratio: float = 1.0,
    generated_index_blocker_ratio: float = 3.0,
    sync_warning_gib: float = 1.0,
) -> dict[str, Any]:
    clean_bytes = max(0, int(float(clean_source_gib) * GIB))
    threads = max(1, int(thread_count))
    segment_size_bytes = max(1, int(segment_size_mib) * MIB)
    generated_index_bytes = max(0, int(clean_bytes * float(generated_index_ratio)))
    sync_policy_bytes = max(0, int(clean_bytes * float(sync_policy_ratio)))
    segment_count = max(1, math.ceil(clean_bytes / segment_size_bytes)) if clean_bytes else 0
    main_sqlite_count = threads
    segment_sqlite_count = segment_count
    worst_case_sqlite_handles = main_sqlite_count + segment_sqlite_count
    planned_sqlite_handles = min(max(1, int(fanout_budget)), worst_case_sqlite_handles)
    clean_state = threshold_state(clean_bytes, GIB)
    index_state = threshold_state(
        float(generated_index_ratio),
        float(generated_index_warning_ratio),
        float(generated_index_blocker_ratio),
    )
    sync_state = threshold_state(sync_policy_bytes, float(sync_warning_gib) * GIB)
    fanout_state = "warning" if worst_case_sqlite_handles > fanout_budget else "pass"
    blockers = [
        name
        for name, state in {
            "generated_index_amplification": index_state,
        }.items()
        if state == "blocker"
    ]
    warnings = [
        name
        for name, state in {
            "clean_source_gb_scale": clean_state,
            "generated_index_amplification": index_state,
            "sync_policy_bytes": sync_state,
            "query_fanout": fanout_state,
        }.items()
        if state == "warning"
    ]
    return {
        "schema_version": 1,
        "kind": "aippocampus_synthetic_scale_capacity_smoke",
        "created_at": now_utc(),
        "ok": not blockers,
        "status": "blocked" if blockers else "simulated_with_warnings" if warnings else "simulated",
        "config": {
            "clean_source_gib": float(clean_source_gib),
            "thread_count": threads,
            "generated_index_ratio": float(generated_index_ratio),
            "segment_size_mib": int(segment_size_mib),
            "sync_policy_ratio": float(sync_policy_ratio),
            "fanout_budget": int(fanout_budget),
        },
        "metrics": {
            "canonical_clean_source_bytes": clean_bytes,
            "canonical_clean_source_human": human_bytes(clean_bytes),
            "generated_index_bytes": generated_index_bytes,
            "generated_index_human": human_bytes(generated_index_bytes),
            "index_amplification_ratio": ratio(generated_index_bytes, clean_bytes),
            "sync_policy_bytes": sync_policy_bytes,
            "sync_policy_human": human_bytes(sync_policy_bytes),
            "sync_policy_to_clean_source_ratio": ratio(sync_policy_bytes, clean_bytes),
            "segment_size_bytes": segment_size_bytes,
            "segment_count": segment_count,
            "main_sqlite_count": main_sqlite_count,
            "segment_sqlite_count": segment_sqlite_count,
            "worst_case_sqlite_handles": worst_case_sqlite_handles,
            "planned_sqlite_handles": planned_sqlite_handles,
            "estimated_rebuild_work_units": segment_count,
        },
        "thresholds": {
            "clean_source_gb_scale": {
                "state": clean_state,
                "warning_at_bytes": GIB,
                "meaning": "warning: prefer chunked manifests, delta sync, and fanout planning",
            },
            "generated_index_amplification": {
                "state": index_state,
                "warning_at_ratio": float(generated_index_warning_ratio),
                "blocker_at_ratio": float(generated_index_blocker_ratio),
                "meaning": "warning/blocker: generated caches must stay rebuildable and explainable",
            },
            "sync_policy_bytes": {
                "state": sync_state,
                "warning_at_bytes": int(float(sync_warning_gib) * GIB),
                "meaning": "warning: default sync should move source chunks and manifests, not large caches",
            },
            "query_fanout": {
                "state": fanout_state,
                "fanout_budget": int(fanout_budget),
                "meaning": "warning: registry planner should narrow candidates before opening indexes",
            },
        },
        "warnings": warnings,
        "blockers": blockers,
        "privacy_boundary": {
            "reads_private_registry": False,
            "creates_large_files": False,
            "reads_clean_source_message_bodies": False,
            "emits_absolute_paths": False,
            "output_shape": "synthetic_aggregate_capacity_model",
        },
        "cannot_claim": [
            "real_gb_registry_runtime",
            "real_tb_registry_runtime",
            "windows_interrupted_rebuild_recovery",
        ],
    }


def render_text(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    return "\n".join(
        [
            "AIppocampus synthetic scale capacity smoke",
            f"- status: {payload['status']}",
            f"- clean source: {metrics['canonical_clean_source_human']}",
            f"- generated indexes: {metrics['generated_index_human']} ({metrics['index_amplification_ratio']}x)",
            f"- sync policy: {metrics['sync_policy_human']} ({metrics['sync_policy_to_clean_source_ratio']}x)",
            f"- segments: {metrics['segment_count']} at {human_bytes(metrics['segment_size_bytes'])}",
            f"- SQLite fanout: worst {metrics['worst_case_sqlite_handles']} / planned {metrics['planned_sqlite_handles']}",
            f"- warnings: {', '.join(payload['warnings']) if payload['warnings'] else 'none'}",
            f"- blockers: {', '.join(payload['blockers']) if payload['blockers'] else 'none'}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-source-gib", type=float, default=4.0)
    parser.add_argument("--thread-count", type=int, default=128)
    parser.add_argument("--generated-index-ratio", type=float, default=0.6)
    parser.add_argument("--segment-size-mib", type=int, default=64)
    parser.add_argument("--sync-policy-ratio", type=float, default=0.35)
    parser.add_argument("--fanout-budget", type=int, default=64)
    parser.add_argument("--generated-index-warning-ratio", type=float, default=1.0)
    parser.add_argument("--generated-index-blocker-ratio", type=float, default=3.0)
    parser.add_argument("--sync-warning-gib", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    payload = build_synthetic_scale_capacity_smoke(
        clean_source_gib=args.clean_source_gib,
        thread_count=args.thread_count,
        generated_index_ratio=args.generated_index_ratio,
        segment_size_mib=args.segment_size_mib,
        sync_policy_ratio=args.sync_policy_ratio,
        fanout_budget=args.fanout_budget,
        generated_index_warning_ratio=args.generated_index_warning_ratio,
        generated_index_blocker_ratio=args.generated_index_blocker_ratio,
        sync_warning_gib=args.sync_warning_gib,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
