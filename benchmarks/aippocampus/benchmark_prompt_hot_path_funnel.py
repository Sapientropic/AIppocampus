#!/usr/bin/env python3
"""Deterministic prompt hot-path funnel smoke for #602."""

from __future__ import annotations

import json
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.recall.prompt_recall_hot_path import run_hot_path_funnel  # noqa: E402


def _write_index(path: Path, messages: list[tuple[int, str, str]]) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE messages ("
            "id INTEGER PRIMARY KEY, line INTEGER, timestamp TEXT, role TEXT, kind TEXT, "
            "phase TEXT, turn_index INTEGER, is_final INTEGER, text TEXT)"
        )
        con.executemany(
            "INSERT INTO messages "
            "(id, line, timestamp, role, kind, phase, turn_index, is_final, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    idx,
                    idx * 10,
                    "2026-06-03T00:00:00Z",
                    role,
                    "message",
                    "final_answer" if role == "assistant" else "",
                    idx,
                    1 if role == "assistant" else 0,
                    text,
                )
                for idx, role, text in messages
            ],
        )
        con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(text, tokenize='trigram')")
        con.executemany(
            "INSERT INTO messages_fts (rowid, text) VALUES (?, ?)",
            [(idx, text) for idx, _role, text in messages],
        )
        con.commit()
    finally:
        con.close()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 3)
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percentile / 100.0) * (len(ordered) - 1)))))
    return round(ordered[index], 3)


def run_benchmark() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        phonics = root / "phonics.sqlite"
        profile = root / "profile.sqlite"
        _write_index(
            phonics,
            [
                (1, "user", "Phonics Lab Books 3 4 5 是否算完成"),
                (2, "assistant", "图片完成但音频和课程闭环未完全完成"),
            ],
        )
        _write_index(
            profile,
            [
                (1, "user", "resume CV LinkedIn profile"),
                (2, "assistant", "professional profile route"),
            ],
        )
        cases: list[dict[str, Any]] = [
            {
                "case_id": "thread-profile-continue",
                "prompt": "继续",
                "query_terms": ["继续"],
                "expected_decision": "scent",
                "candidate_indexes": [
                    {
                        "thread_key": "session:profile",
                        "index_path": profile,
                        "source_refs": [{"thread_key": "session:profile", "line": 10}],
                        "thread_profile": {
                            "terms": ["resume", "profile"],
                            "representative_message_ids": [1, 2],
                        },
                    }
                ],
            },
            {
                "case_id": "fts-fallback",
                "prompt": "之前说 Books 3/4/5 完成了吗，继续那个",
                "query_terms": ["Books", "3/4/5", "完成"],
                "expected_decision": "scent",
                "candidate_indexes": [
                    {
                        "thread_key": "session:phonics",
                        "index_path": phonics,
                        "source_refs": [{"thread_key": "session:phonics", "line": 10}],
                    }
                ],
            },
            {
                "case_id": "stale-cache-navigation",
                "prompt": "profile 这个线索继续",
                "query_terms": ["profile"],
                "expected_decision": "scent",
                "candidate_indexes": [
                    {
                        "thread_key": "session:profile",
                        "cue_cache": {"query_aliases": ["profile"], "state": "stale"},
                        "source_refs": [{"thread_key": "session:profile", "line": 10}],
                    }
                ],
            },
            {
                "case_id": "ordinary-code-no-op",
                "prompt": "把按钮 hover 样式调一下",
                "query_terms": ["按钮", "hover"],
                "expected_decision": "skip",
                "candidate_indexes": [],
            },
        ]
        for case in cases:
            start = time.perf_counter()
            result = run_hot_path_funnel(
                prompt=case["prompt"],
                query_terms=case["query_terms"],
                candidate_indexes=case["candidate_indexes"],
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "decision": result["decision"],
                    "expected_decision": case["expected_decision"],
                    "elapsed_ms": elapsed_ms,
                    "stage_count": len(result["stages"]),
                    "candidate_count": result["candidate_count"],
                    "false_evidence": bool(result["evidence"]),
                    "source_reopen_promotion_count": result["source_reopen_promotion_count"],
                }
            )
    latencies = [float(row["elapsed_ms"]) for row in rows]
    false_skip_count = sum(
        1
        for row in rows
        if row["expected_decision"] == "scent" and row["decision"] == "skip"
    )
    wrong_scent_count = sum(
        1
        for row in rows
        if row["expected_decision"] == "skip" and row["decision"] == "scent"
    )
    false_evidence_count = sum(1 for row in rows if row["false_evidence"])
    promotion_count = sum(int(row["source_reopen_promotion_count"]) for row in rows)
    return {
        "kind": "aippocampus_prompt_hot_path_funnel_benchmark",
        "ok": false_skip_count == 0 and wrong_scent_count == 0 and false_evidence_count == 0,
        "config": {
            "local_only": True,
            "uses_external_model": False,
            "uses_new_runtime_dependency": False,
            "uses_existing_trigram_fts": True,
        },
        "metrics": {
            "case_count": len(rows),
            "p50_latency_ms": round(statistics.median(latencies), 3) if latencies else 0.0,
            "p95_latency_ms": _percentile(latencies, 95),
            "false_skip_rate": round(false_skip_count / len(rows), 4),
            "wrong_scent_rate": round(wrong_scent_count / len(rows), 4),
            "source_reopen_promotion_rate": round(promotion_count / len(rows), 4),
            "false_evidence_count": false_evidence_count,
        },
        "rows": rows,
        "cannot_claim": [
            "speed alone is not quality evidence",
            "semantic paraphrase recall quality is out of scope",
            "scent remains navigation until source reopen",
        ],
    }


def main() -> int:
    print(json.dumps(run_benchmark(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
