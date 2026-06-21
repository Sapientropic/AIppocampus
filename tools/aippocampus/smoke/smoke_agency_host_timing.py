#!/usr/bin/env python3
"""No-write smoke for agency-ticket host timing replay evidence."""

from __future__ import annotations

import argparse
import json

from _paths import ensure_paths


def _agency_host_timing_runtime():
    ensure_paths()
    from aippocampus_runtime.coding import agency_host_timing

    return agency_host_timing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic agency host-timing replay smoke."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    agency_host_timing = _agency_host_timing_runtime()
    report = agency_host_timing.fixture_host_timing_replay()
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(agency_host_timing.render_text(report), end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
