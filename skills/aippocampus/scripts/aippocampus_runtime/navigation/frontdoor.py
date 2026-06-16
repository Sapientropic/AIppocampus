#!/usr/bin/env python3
"""Foreground boundary card for navigation sidecars."""

from __future__ import annotations

import argparse
import json
from typing import Any


def navigation_payload() -> dict[str, Any]:
    return {
        "kind": "aippocampus_navigation_frontdoor",
        "ok": True,
        "status": "operator_only",
        "lanes": [
            {
                "id": "cognitive_map",
                "status": "operator_only",
                "diagnostic_command": "python -m aippocampus_runtime.navigation.cognitive_map --help",
            },
            {
                "id": "concept_expansion",
                "status": "operator_only",
                "diagnostic_command": "python -m aippocampus_runtime.navigation.concept_graph_cli --help",
            },
        ],
        "foreground_next_action": {
            "id": "use_recall_or_search_first",
            "command": 'aippocampus agent recall "old cue" --json',
            "alternatives": ['aippocampus search "exact phrase" --json'],
        },
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
        "operator diagnostics:",
    ]
    for lane in payload.get("lanes") or []:
        if isinstance(lane, dict):
            lines.append(f"- {lane.get('id')}: {lane.get('diagnostic_command')}")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = navigation_payload()
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
