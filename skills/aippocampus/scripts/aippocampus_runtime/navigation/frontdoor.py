#!/usr/bin/env python3
"""Foreground boundary card for navigation sidecars."""

from __future__ import annotations

import argparse
import json
from typing import Any

_OPERATOR_LANES = (
    (
        "cognitive_map",
        "python -m aippocampus_runtime.navigation.cognitive_map --help",
    ),
    (
        "concept_expansion",
        "python -m aippocampus_runtime.navigation.concept_graph_cli --help",
    ),
)


def navigation_payload(*, operator_detail: bool = False) -> dict[str, Any]:
    lanes = []
    for lane_id, diagnostic_command in _OPERATOR_LANES:
        lane = {
            "id": lane_id,
            "status": "operator_only",
            "operator_detail_command": "aippocampus navigate --operator-json",
        }
        if operator_detail:
            lane["diagnostic_command"] = diagnostic_command
        lanes.append(lane)
    return {
        "kind": "aippocampus_navigation_frontdoor",
        "ok": True,
        "status": "operator_only",
        "detail": "operator" if operator_detail else "compact",
        "lanes": lanes,
        "foreground_next_action": {
            "id": "use_recall_or_search_first",
            "command": 'aippocampus agent recall "old cue" --json',
            "alternatives": ['aippocampus search "exact phrase" --json'],
        },
        "operator_next_action": "aippocampus navigate --operator-json",
        "source_boundary": {
            "navigation_sidecars_are_not_source_truth": True,
            "source_reopen_required_before_claim": True,
            "model_job_started": False,
        },
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "AIppocampus navigation sidecars",
        f"status: {payload.get('status')}",
        "foreground: use agent recall/search first",
        'next: aippocampus agent recall "old cue" --json',
        "boundary: cognitive-map and concept expansion are operator-only diagnostics here",
        "claim rule: reopen source before treating any sidecar route as evidence",
        "operator details: aippocampus navigate --operator-json",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus navigate",
        usage="aippocampus navigate [status] [--json]",
        description=(
            "Show the boundary for cognitive-map and concept-expansion sidecars. "
            "Ordinary foreground continuity should start with recall/search."
        ),
    )
    parser.add_argument("command", nargs="?", choices=["status"], default="status")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Show maintainer-only module diagnostics as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = navigation_payload(operator_detail=bool(args.operator_json))
    if args.json_output or args.operator_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
