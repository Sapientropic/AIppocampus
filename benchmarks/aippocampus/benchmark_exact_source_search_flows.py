#!/usr/bin/env python3
"""Public-safe probes for registry-wide and last-recall exact source search."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.recall.agent_recall_cache import write_last_recall_cache
from aippocampus_runtime.source.last_recall_search import search_last_recall_sources
from aippocampus_runtime.source.registry_search import (
    open_registry_source_window,
    search_registry_sources,
)

SCHEMA_VERSION = 1
SEARCH_MISS_NOT_ABSENCE = "search_miss_is_not_absence_of_memory"


def _write_messages(clean_dir: Path, rows: list[dict[str, Any]]) -> None:
    clean_dir.mkdir(parents=True, exist_ok=True)
    with (clean_dir / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_registry(root: Path, threads: list[dict[str, Any]]) -> None:
    (root / "threads.json").write_text(
        json.dumps({"schema_version": 1, "threads": threads}, ensure_ascii=False),
        encoding="utf-8",
    )


def _setup_fixture(root: Path) -> tuple[Path, Path]:
    current_clean = root / "current" / "clean-source"
    registry_clean = root / "registry-thread" / "clean-source"
    registry_duplicate_clean = root / "registry-duplicate-thread" / "clean-source"
    recall_clean = root / "recall-thread" / "clean-source"
    _write_messages(
        current_clean,
        [
            {
                "id": "msg_current",
                "message_id": "msg_current",
                "source_line": 3,
                "role": "assistant",
                "phase": "final_answer",
                "text": "The current thread intentionally lacks the cross-thread fixture phrase.",
            }
        ],
    )
    _write_messages(
        registry_clean,
        [
            {
                "id": "msg_registry",
                "message_id": "msg_registry",
                "source_line": 8,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 2,
                "is_final": True,
                "text": "The cross-thread exact search fixture phrase lives in a registered source.",
            }
        ],
    )
    _write_messages(
        registry_duplicate_clean,
        [
            {
                "id": "msg_registry_duplicate",
                "message_id": "msg_registry_duplicate",
                "source_line": 12,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 4,
                "is_final": True,
                "text": "The cross-thread exact search fixture phrase lives in a registered source.",
            }
        ],
    )
    _write_messages(
        recall_clean,
        [
            {
                "id": "msg_recall",
                "message_id": "msg_recall",
                "source_line": 9,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 3,
                "is_final": True,
                "text": "The last-recall exact search fixture phrase lives in a recalled route.",
            }
        ],
    )
    _write_registry(
        root,
        [
            {
                "thread_key": "session:registry",
                "title": "Registry exact source fixture",
                "paths": {
                    "workspace": str(root / "private-workspace"),
                    "clean_source_messages_jsonl": str(registry_clean / "messages.jsonl"),
                    "sqlite": str(root / "missing-registry.sqlite"),
                },
            },
            {
                "thread_key": "session:registry-duplicate",
                "title": "Registry exact source duplicate fixture",
                "paths": {
                    "clean_source_messages_jsonl": str(
                        registry_duplicate_clean / "messages.jsonl"
                    ),
                    "sqlite": str(root / "missing-registry-duplicate.sqlite"),
                },
            },
            {
                "thread_key": "session:recall",
                "title": "Last recall exact source fixture",
                "paths": {
                    "clean_source_messages_jsonl": str(recall_clean / "messages.jsonl"),
                    "sqlite": str(root / "missing-recall.sqlite"),
                },
            },
        ],
    )
    cache_path = root / "last-recall.json"
    ok = write_last_recall_cache(
        [
            {
                "request_index": 1,
                "route_id": "route_recall",
                "handle": {
                    "kind": "thread_candidate",
                    "thread_key": "session:recall",
                    "route_id": "route_recall",
                },
            }
        ],
        query="last recall exact search fixture",
        cwd=root,
        clean_source_dir=current_clean,
        registry_dir=root,
        macro_state_path=None,
        project="fixture",
        max_matches=5,
        schema_version="agent-continuity-path-v1",
        path=cache_path,
    )
    if not ok:
        raise RuntimeError("failed to write last recall fixture cache")
    return current_clean, cache_path


def _search_miss_not_absence_boundary(payload: dict[str, Any]) -> bool:
    source_boundary = payload.get("source_boundary")
    if (
        isinstance(source_boundary, dict)
        and source_boundary.get("search_miss_is_not_absence_of_memory") is True
    ):
        return True
    return (
        payload.get("source_reopen_boundary") == SEARCH_MISS_NOT_ABSENCE
        or payload.get("claim_boundary") == SEARCH_MISS_NOT_ABSENCE
    )


def evaluate_exact_source_search_flows() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, cache_path = _setup_fixture(root)
        registry_hit = search_registry_sources(
            ["cross-thread exact search fixture phrase"],
            registry_dir=root,
            record_last_search=True,
        )
        registry_reopen = open_registry_source_window(
            registry_dir=root,
            hit_index=1,
            use_last_search=True,
        )
        registry_duplicate_reopen = open_registry_source_window(
            registry_dir=root,
            hit_index=1,
            source_ref_index=2,
            use_last_search=True,
        )
        registry_miss = search_registry_sources(
            ["zqxj-unmatched-registry-needle"],
            registry_dir=root,
        )
        last_recall_hit = search_last_recall_sources(
            ["last-recall exact search fixture phrase"],
            cwd=root,
            last_recall_path=cache_path,
        )
        last_recall_miss = search_last_recall_sources(
            ["zqxj-unmatched-last-recall-needle"],
            cwd=root,
            last_recall_path=cache_path,
        )
        stale_last_recall = search_last_recall_sources(
            ["last-recall exact search fixture phrase"],
            cwd=root,
            last_recall_path=root / "missing-last-recall.json",
        )
        payloads = [
            registry_hit,
            registry_reopen,
            registry_duplicate_reopen,
            registry_miss,
            last_recall_hit,
            last_recall_miss,
            stale_last_recall,
        ]
        duplicate_refs = registry_hit["matches"][0].get("duplicate_source_refs") or []
        target_in_duplicate_refs = any(
            isinstance(ref, dict)
            and ref.get("thread_key") == "session:registry-duplicate"
            and bool(ref.get("source_window_command"))
            for ref in duplicate_refs
        )
        encoded = json.dumps(payloads, ensure_ascii=False)
        rows = [
            {
                "case_id": "registry_wide_cross_thread_hit",
                "ok": bool(registry_hit.get("ok"))
                and registry_hit.get("match_count") >= 1
                and registry_hit["matches"][0]["thread"]["thread_key"] == "session:registry",
                "scope": registry_hit.get("search_scope"),
                "reopenable": bool(registry_hit["matches"][0].get("reopen_command")),
            },
            {
                "case_id": "registry_wide_hit_reopens_source_window",
                "ok": bool(registry_reopen.get("ok"))
                and registry_reopen.get("metrics", {}).get("source_reopen_success") is True,
                "scope": "registry_source_window",
                "reopenable": True,
                "top_level_target_hit": True,
                "target_in_duplicate_refs": False,
            },
            {
                "case_id": "registry_wide_duplicate_ref_reopens_source_window",
                "ok": target_in_duplicate_refs
                and bool(registry_duplicate_reopen.get("ok"))
                and registry_duplicate_reopen.get("source_route", {}).get("thread_key")
                == "session:registry-duplicate",
                "scope": "registry_source_window",
                "reopenable": True,
                "top_level_target_hit": False,
                "target_in_duplicate_refs": target_in_duplicate_refs,
            },
            {
                "case_id": "registry_wide_no_match_boundary",
                "ok": registry_miss.get("status") == "no_matches"
                and _search_miss_not_absence_boundary(registry_miss),
                "scope": registry_miss.get("search_scope"),
                "reopenable": False,
            },
            {
                "case_id": "last_recall_candidate_hit",
                "ok": bool(last_recall_hit.get("ok"))
                and last_recall_hit.get("match_count") == 1
                and last_recall_hit["matches"][0]["request_index"] == 1,
                "scope": last_recall_hit.get("search_scope"),
                "reopenable": bool(
                    last_recall_hit["matches"][0].get("source_window_command")
                    or last_recall_hit["matches"][0].get("reopen_command")
                ),
            },
            {
                "case_id": "last_recall_no_match_boundary",
                "ok": last_recall_miss.get("status") == "no_matches"
                and _search_miss_not_absence_boundary(last_recall_miss),
                "scope": last_recall_miss.get("search_scope"),
                "reopenable": False,
            },
            {
                "case_id": "last_recall_missing_cache_recovery",
                "ok": stale_last_recall.get("status") == "cannot_verify"
                and stale_last_recall.get("error", {}).get("code") == "last_recall_unavailable",
                "scope": stale_last_recall.get("search_scope"),
                "reopenable": False,
            },
        ]
        red_lines = {
            "privacy_path_leak_count": int(str(root) in encoded),
            "raw_registry_entry_shape_count": sum(
                1
                for payload in payloads
                if isinstance(payload, dict)
                and any("session_meta" in str(match) or "paths" in str(match) for match in payload.get("matches") or [])
            ),
            "search_miss_claims_absence_count": sum(
                1
                for payload in (registry_miss, last_recall_miss)
                if not _search_miss_not_absence_boundary(payload)
            ),
        }
        ok = all(row["ok"] for row in rows) and all(value == 0 for value in red_lines.values())
        return {
            "kind": "aippocampus_exact_source_search_flow_benchmark",
            "schema_version": SCHEMA_VERSION,
            "run_at": now_utc(),
            "ok": ok,
            "quality_gate_ok": ok,
            "rows": rows,
            "metrics": {
                "case_count": len(rows),
                "hit_correctness_count": sum(1 for row in rows if row["ok"]),
                "reopenable_hit_count": sum(1 for row in rows if row["reopenable"]),
                "target_in_duplicate_refs_count": sum(
                    1 for row in rows if row.get("target_in_duplicate_refs")
                ),
                "privacy_path_leak_count": red_lines["privacy_path_leak_count"],
            },
            "red_lines": red_lines,
            "boundary": {
                "public_safe_synthetic_fixture": True,
                "private_history_quality_claimed": False,
                "live_recall_quality_claimed": False,
            },
            "cannot_claim": [
                "private_history_search_quality",
                "live_recall_quality",
                "absence_of_memory_from_search_miss",
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = evaluate_exact_source_search_flows()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"exact source search flow benchmark: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
