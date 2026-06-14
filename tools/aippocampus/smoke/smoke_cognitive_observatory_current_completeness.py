#!/usr/bin/env python3
"""Smoke the public-safe current completeness projection for the observatory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from _paths import ensure_paths  # noqa: E402

ensure_paths()

from aippocampus_runtime.ops import observatory_completeness  # noqa: E402
from aippocampus_runtime.public_output import emit_public_text  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Emit a public-safe read-only completeness report for the Cognitive "
            "Observatory current fixture."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full sanitized JSON report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the sanitized JSON report.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = observatory_completeness.build_current_completeness_report()
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_text + "\n", encoding="utf-8")

    if args.json:
        emit_public_text(json_text)
    else:
        summary = report["summary"]
        emit_public_text(
            "\n".join(
                [
                    f"ok={bool(report['ok'])}",
                    f"included={summary['included_surface_count']}/{summary['expected_surface_count']}",
                    f"missing={','.join(summary['missing_surfaces']) or 'none'}",
                    f"blocked_control_attempts={summary['control_attempts_blocked']}",
                    f"raw_leak_flags={summary['raw_leak_flag_count']}",
                ]
            )
        )
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
