#!/usr/bin/env python3
"""Low-noise drift report for foreground route-anchor vocabulary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from repo_paths import ensure_repo_imports


def _route_quality_module() -> Any:
    ensure_repo_imports(Path(__file__).resolve())
    from aippocampus_runtime.recall.foreground import route_quality

    return route_quality


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--term",
        action="append",
        default=[],
        help="Candidate anchor term to classify. Defaults to the built-in drift sample.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    route_quality = _route_quality_module()
    report = route_quality.anchor_quality_drift_report(args.term or None)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "pass" if report["ok"] else "needs owner decision"
        print(f"AIppocampus route anchor quality guard: {status}")
        for row in report["classifications"]:
            posture = "low-signal" if row["low_signal"] else "meaningful"
            print(f"- {row['term']}: {posture} ({row['reason']})")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
