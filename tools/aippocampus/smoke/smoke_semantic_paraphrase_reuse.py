#!/usr/bin/env python3
"""Smoke the #157 semantic paraphrase reuse boundary.

The foreground hook has two different warm paths that are easy to conflate:

* exact semantic cache hits are exact-key reuse only;
* neighboring paraphrases should stay local only after a source-backed semantic
  cue has repeated enough to promote from staging to active.

This smoke keeps the evidence public-safe by using a synthetic registry and a
fake semantic gate. It verifies the product boundary directly instead of
depending on private rollout prompts or a live provider.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import aippocampus_prompt_hook as hook  # noqa: E402
import semantic_cue_cache as cue_cache  # noqa: E402

THREAD_KEY = "session:aippocampus-paraphrase-reuse"
SOURCE_REF = {"thread_key": THREAD_KEY, "message_id": "m1", "source_line": 1}
PROMPTS = {
    "exact_cache_hit": "Can you recall the exact external hippocampus note?",
    "single_warm_neighbor": "How is that memoria externa continuity layer going?",
    "repeated_cue_neighbor": "Please continue the memoria externa continuity thread.",
    "forced_live_calibration": "Could you calibrate memoria externa continuity again?",
}
ALIAS = "memoria externa"


def write_fixture(root: Path, cwd: Path) -> tuple[Path, Path, Path]:
    registry_path = root / "registry" / "threads.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": THREAD_KEY,
                        "title": "AIppocampus continuity work",
                        "project_label": "AIppocampus",
                        "anchor_titles": ["External hippocampus recall"],
                        "keywords": ["external hippocampus", "conversation continuity", ALIAS],
                        "summary": "Synthetic source-backed continuity work for external memory.",
                        "paths": {"workspace": str(cwd)},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return registry_path, root / "registry" / "semantic_cues.jsonl", root / "registry" / "semantic_cache.jsonl"


def semantic_success(*, cached: bool) -> dict[str, Any]:
    return {
        "available": True,
        "decision": "scent",
        "confidence": 0.86,
        "cached": cached,
        "cache_diagnostics": {"lookup": "hit" if cached else "miss"},
        "query_aliases": [ALIAS],
        "memory_scope": ["registered_threads"],
        "reasons": ["synthetic source-backed semantic cue"],
    }


def semantic_cold_timeout() -> dict[str, Any]:
    return {
        "available": False,
        "decision": "skip",
        "confidence": 0.0,
        "cached": False,
        "cache_diagnostics": {"lookup": "miss"},
        "workers": [{"worker": "synthetic", "ok": False}],
        "worker_count": 1,
        "errors": ["synthetic foreground read timeout"],
        "error_buckets": {"read_timeout": 1},
        "availability_reason": "foreground_budget_timeout",
        "diagnostic": "semantic_timed_out_under_foreground_budget",
        "query_aliases": [],
    }


def record_cue_hits(path: Path, *, count: int) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for index in range(count):
        reports.append(
            cue_cache.record_semantic_cue_hits(
                path,
                prompt=f"synthetic warm prompt {index}",
                semantic_result=semantic_success(cached=False),
                source_refs=[SOURCE_REF],
                route="semantic_gate",
            )
        )
    return reports


def assess(
    prompt: str,
    *,
    cwd: Path,
    registry_path: Path,
    cues_path: Path,
    cache_path: Path,
    gate: Callable[..., dict[str, Any]],
    semantic_gate_mode: str = "auto",
) -> dict[str, Any]:
    return hook.assess_prompt(
        prompt,
        cwd=cwd,
        registry_path=registry_path,
        semantic_cues_path=cues_path,
        semantic_cache_path=cache_path,
        semantic_gate_mode=semantic_gate_mode,
        semantic_timeout=5,
        semantic_gate_fn=gate,
        search_budget=0,
        max_elapsed_ms=5000,
        use_thread_cache=False,
        warm_background=False,
    )


def row_from_result(
    *,
    name: str,
    result: dict[str, Any],
    expected: dict[str, Any],
    gate_calls: int,
    cue_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reuse = result.get("semantic_gate_reuse") or {}
    semantic = result.get("semantic_gate")
    checks = {
        "source": reuse.get("source") == expected["source"],
        "exact_cache_hit": reuse.get("exact_cache_hit") is expected["exact_cache_hit"],
        "semantic_cue_hit": reuse.get("semantic_cue_hit") is expected["semantic_cue_hit"],
        "cold_model_call": reuse.get("cold_model_call") is expected["cold_model_call"],
        "skipped_by_semantic_cue": reuse.get("skipped_by_semantic_cue")
        is expected["skipped_by_semantic_cue"],
        "gate_calls": gate_calls == expected["gate_calls"],
        "semantic_present": bool(semantic) is expected["semantic_present"],
    }
    return {
        "name": name,
        "ok": all(checks.values()),
        "checks": checks,
        "decision": result.get("decision"),
        "semantic_reuse": reuse,
        "semantic_available": (semantic or {}).get("available") if isinstance(semantic, dict) else None,
        "semantic_diagnostic": (semantic or {}).get("diagnostic") if isinstance(semantic, dict) else None,
        "gate_calls": gate_calls,
        "cue_reports": cue_reports or [],
    }


def run_semantic_paraphrase_reuse_smoke(*, cwd: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry_path, cues_path, cache_path = write_fixture(root, cwd)
        rows: list[dict[str, Any]] = []

        calls = 0

        def exact_gate(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return semantic_success(cached=True)

        result = assess(
            PROMPTS["exact_cache_hit"],
            cwd=cwd,
            registry_path=registry_path,
            cues_path=cues_path,
            cache_path=cache_path,
            gate=exact_gate,
        )
        rows.append(
            row_from_result(
                name="exact_cache_hit",
                result=result,
                gate_calls=calls,
                expected={
                    "source": "exact_semantic_cache",
                    "exact_cache_hit": True,
                    "semantic_cue_hit": False,
                    "cold_model_call": False,
                    "skipped_by_semantic_cue": False,
                    "gate_calls": 1,
                    "semantic_present": True,
                },
            )
        )

        single_cues = root / "registry" / "single_warm_semantic_cues.jsonl"
        single_reports = record_cue_hits(single_cues, count=1)
        calls = 0

        def cold_gate(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return semantic_cold_timeout()

        result = assess(
            PROMPTS["single_warm_neighbor"],
            cwd=cwd,
            registry_path=registry_path,
            cues_path=single_cues,
            cache_path=cache_path,
            gate=cold_gate,
        )
        rows.append(
            row_from_result(
                name="single_warm_neighbor",
                result=result,
                gate_calls=calls,
                cue_reports=single_reports,
                expected={
                    "source": "cold_model_call",
                    "exact_cache_hit": False,
                    "semantic_cue_hit": False,
                    "cold_model_call": True,
                    "skipped_by_semantic_cue": False,
                    "gate_calls": 1,
                    "semantic_present": True,
                },
            )
        )

        repeated_cues = root / "registry" / "repeated_semantic_cues.jsonl"
        repeated_reports = record_cue_hits(repeated_cues, count=2)
        calls = 0

        def forbidden_gate(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            raise AssertionError("active semantic cue should skip cold semantic gate")

        result = assess(
            PROMPTS["repeated_cue_neighbor"],
            cwd=cwd,
            registry_path=registry_path,
            cues_path=repeated_cues,
            cache_path=cache_path,
            gate=forbidden_gate,
        )
        rows.append(
            row_from_result(
                name="repeated_cue_neighbor",
                result=result,
                gate_calls=calls,
                cue_reports=repeated_reports,
                expected={
                    "source": "semantic_cue_cache",
                    "exact_cache_hit": False,
                    "semantic_cue_hit": True,
                    "cold_model_call": False,
                    "skipped_by_semantic_cue": True,
                    "gate_calls": 0,
                    "semantic_present": False,
                },
            )
        )

        calls = 0
        result = assess(
            PROMPTS["forced_live_calibration"],
            cwd=cwd,
            registry_path=registry_path,
            cues_path=repeated_cues,
            cache_path=cache_path,
            gate=cold_gate,
            semantic_gate_mode="on",
        )
        rows.append(
            row_from_result(
                name="forced_live_calibration",
                result=result,
                gate_calls=calls,
                cue_reports=repeated_reports,
                expected={
                    "source": "cold_model_call",
                    "exact_cache_hit": False,
                    "semantic_cue_hit": True,
                    "cold_model_call": True,
                    "skipped_by_semantic_cue": False,
                    "gate_calls": 1,
                    "semantic_present": True,
                },
            )
        )

    return {
        "ok": all(row.get("ok") for row in rows),
        "case_count": len(rows),
        "passed": sum(1 for row in rows if row.get("ok")),
        "privacy": "synthetic_public_fixture",
        "claim_boundary": [
            "Exact semantic cache reuse is exact-key only.",
            "One source-backed semantic cue hit remains staging and does not promise paraphrase reuse.",
            "Repeated source-backed cue hits promote an active local semantic cue for neighboring paraphrases.",
            "semantic_gate=on is an explicit live calibration override even when an active cue matches.",
        ],
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_semantic_paraphrase_reuse_smoke(cwd=Path(args.cwd).resolve())
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"semantic paraphrase reuse smoke: {result['passed']}/{result['case_count']} passed")
        for row in result["rows"]:
            mark = "OK" if row.get("ok") else "FAIL"
            reuse = row.get("semantic_reuse") or {}
            print(
                f"- {mark} {row.get('name')}: source={reuse.get('source')} "
                f"cue={reuse.get('semantic_cue_hit')} cold={reuse.get('cold_model_call')} "
                f"gate_calls={row.get('gate_calls')}"
            )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
