"""Standalone CLI entrypoint for spend doctor."""

from __future__ import annotations

import argparse
import json
from typing import Any

from aippocampus_runtime.ops.doctors.spend_doctor import (
    DEFAULT_DAYS,
    build_compact_spend_doctor_report,
    build_spend_doctor_report,
    compact_spend_doctor_card,
    render_text,
)


def main(argv: list[str] | None = None) -> int:
    """Run spend doctor without importing the aggregate provider-doctor CLI."""

    parser = argparse.ArgumentParser(
        prog="aippocampus doctor spend",
        description="Report private-safe local model spend and foreground yield.",
        epilog="Privacy boundary: aggregate counts only; no prompts, keys, or source text.",
    )
    parser.add_argument("--registry-dir")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--warning-effective-tokens", type=int, default=None)
    parser.add_argument("--warning-min-foreground-value-rate", type=float, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--detail",
        choices=["compact", "full"],
        default="compact",
        help="JSON detail level. Default --json emits a compact foreground decision card.",
    )
    parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit full local spend/yield telemetry JSON; implies JSON output.",
    )
    args = parser.parse_args(argv)

    kwargs: dict[str, Any] = {}
    if args.warning_effective_tokens is not None:
        kwargs["warn_effective_tokens"] = args.warning_effective_tokens
    if args.warning_min_foreground_value_rate is not None:
        kwargs["warn_min_foreground_value_rate"] = args.warning_min_foreground_value_rate
    full_detail_json = bool(args.operator_json or args.detail == "full")
    builder = (
        build_compact_spend_doctor_report
        if args.json_output and not full_detail_json
        else build_spend_doctor_report
    )
    report = builder(registry_dir=args.registry_dir, days=args.days, **kwargs)
    if args.json_output and not full_detail_json:
        print(json.dumps(compact_spend_doctor_card(report), ensure_ascii=False, indent=2))
    elif args.json_output or args.operator_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
