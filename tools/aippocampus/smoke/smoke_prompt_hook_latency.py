#!/usr/bin/env python3
"""Measure prompt-hook wall time without exposing prompt text.

The hook's own `elapsed_ms` measures recall work after the Python process has
loaded the runtime. This smoke wraps the compatibility script in a subprocess so
operators can see the extra startup/import/I/O overhead, especially on Windows
GUI launches where PATH and cold imports can dominate the foreground budget.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_HOOK = REPO_ROOT / "skills" / "aippocampus" / "scripts" / "aippocampus_prompt_hook.py"
DEFAULT_PROMPT = "把 dashboard 的按钮 hover 样式改一下，顺手跑测试"


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ((len(ordered) * percentile + 99) // 100) - 1))
    return round(float(ordered[index]), 2)


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(float(value) for value in values)
    return {
        "min": round(ordered[0], 2),
        "p50": _percentile(ordered, 50),
        "p95": _percentile(ordered, 95),
        "max": round(ordered[-1], 2),
    }


def _sanitized_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "wall_ms": round(float(row.get("wall_ms") or 0.0), 2),
        "hook_elapsed_ms": round(float(row.get("hook_elapsed_ms") or 0.0), 2),
        "startup_import_io_ms": round(float(row.get("startup_import_io_ms") or 0.0), 2),
        "decision": str(row.get("decision") or "unknown"),
        "returncode": int(row.get("returncode") or 0),
    }


def summarize_latency_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    clean_rows = [_sanitized_row(row) for row in rows]
    decision_counts: dict[str, int] = {}
    for row in clean_rows:
        decision = str(row.get("decision") or "unknown")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    return {
        "schema_version": 1,
        "report": "prompt_hook_latency_probe",
        "privacy_boundary": "sanitized_timing_only_no_raw_prompt_or_source_text",
        "platform": {
            "os_family": (platform.system() or sys.platform or "unknown").lower(),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        },
        "run_count": len(clean_rows),
        "decision_counts": decision_counts,
        "wall_ms": _summary([float(row.get("wall_ms") or 0.0) for row in clean_rows]),
        "hook_elapsed_ms": _summary(
            [float(row.get("hook_elapsed_ms") or 0.0) for row in clean_rows]
        ),
        "startup_import_io_ms": _summary(
            [float(row.get("startup_import_io_ms") or 0.0) for row in clean_rows]
        ),
        "rows": clean_rows,
    }


def run_probe_once(*, prompt: str, cwd: Path, timeout: float) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(PROMPT_HOOK),
        "--prompt",
        prompt,
        "--cwd",
        str(cwd),
        "--json",
        "--semantic-gate",
        "off",
        "--search-budget",
        "0",
        "--no-skip-telemetry",
    ]
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    wall_ms = round((time.perf_counter() - start) * 1000, 2)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}
    hook_elapsed_ms = float(payload.get("elapsed_ms") or 0.0)
    return {
        "wall_ms": wall_ms,
        "hook_elapsed_ms": round(hook_elapsed_ms, 2),
        "startup_import_io_ms": round(max(0.0, wall_ms - hook_elapsed_ms), 2),
        "decision": str(payload.get("decision") or "unknown"),
        "returncode": int(proc.returncode),
    }


def run_latency_probe(*, prompt: str, cwd: Path, runs: int, timeout: float) -> dict[str, Any]:
    rows = [
        run_probe_once(prompt=prompt, cwd=cwd, timeout=timeout)
        for _ in range(max(1, int(runs)))
    ]
    return summarize_latency_rows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--cwd", default=str(Path.cwd()))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = run_latency_probe(
        prompt=args.prompt,
        cwd=Path(args.cwd),
        runs=args.runs,
        timeout=args.timeout,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "prompt-hook latency: "
            f"runs={report['run_count']} "
            f"wall_p95={report['wall_ms']['p95']}ms "
            f"startup_import_io_p95={report['startup_import_io_ms']['p95']}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
