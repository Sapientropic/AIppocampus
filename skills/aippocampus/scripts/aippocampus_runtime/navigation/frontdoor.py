#!/usr/bin/env python3
"""Foreground boundary card for navigation sidecars."""

from __future__ import annotations

import argparse
import json
import shlex
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


def _quote(value: str) -> str:
    return shlex.quote(value)


def navigation_payload(*, cue: str | None = None, operator_detail: bool = False) -> dict[str, Any]:
    clean_cue = (cue or "").strip()
    lanes = []
    for lane_id, diagnostic_command in _OPERATOR_LANES:
        lane = {
            "id": lane_id,
            "status": "operator_only",
            "operator_detail_command": "aippocampus navigate --operator-json",
            "foreground_limitation": (
                "diagnostic_sidecar_only; foreground navigation starts from a user cue "
                "or a reopenable route returned by recall/search"
            ),
        }
        if operator_detail:
            lane["diagnostic_command"] = diagnostic_command
        lanes.append(lane)
    foreground_next_actions: list[dict[str, Any]]
    if clean_cue:
        foreground_next_actions = [
            {
                "id": "recall_with_supplied_cue",
                "kind": "shell_command",
                "command": f"aippocampus agent recall {_quote(clean_cue)} --json",
                "requires": "none",
                "mutation_risk": "read_only",
                "claim_boundary": "no_claim_before_reopen",
            },
            {
                "id": "search_exact_supplied_cue",
                "kind": "shell_command",
                "command": f"aippocampus search {_quote(clean_cue)} --json",
                "requires": "none",
                "mutation_risk": "read_only",
                "claim_boundary": "search_result_requires_source_boundary",
            },
        ]
        status = "foreground_route_available"
    else:
        foreground_next_actions = [
            {
                "id": "provide_navigation_cue",
                "kind": "shell_command_template",
                "command_template": 'aippocampus navigate "{cue}" --json',
                "requires": ["cue"],
                "template_only": True,
                "mutation_risk": "read_only",
                "claim_boundary": "no_claim_before_reopen",
            },
            {
                "id": "use_recall_directly",
                "kind": "shell_command_template",
                "command_template": 'aippocampus agent recall "{cue}" --json',
                "requires": ["cue"],
                "template_only": True,
                "mutation_risk": "read_only",
                "claim_boundary": "no_claim_before_reopen",
            },
        ]
        status = "needs_cue"
    return {
        "kind": "aippocampus_navigation_frontdoor",
        "ok": True,
        "status": status,
        "detail": "operator" if operator_detail else "compact",
        "cue_supplied": bool(clean_cue),
        "lanes": lanes,
        "foreground_next_actions": foreground_next_actions,
        "operator_next_action": "aippocampus navigate --operator-json",
        "source_boundary": {
            "navigation_sidecars_are_not_source_truth": True,
            "source_reopen_required_before_claim": True,
            "model_job_started": False,
        },
    }


def render_text(payload: dict[str, Any]) -> str:
    actions = payload.get("foreground_next_actions") or []
    next_command = (
        actions[0].get("command") or actions[0].get("command_template")
        if actions and isinstance(actions[0], dict)
        else ""
    )
    lines = [
        "AIppocampus navigation sidecars",
        f"status: {payload.get('status')}",
        "foreground: provide a cue, then use recall/search first",
        f"next: {next_command}",
        "boundary: cognitive-map and concept expansion are operator-only diagnostics here",
        "claim rule: reopen source before treating any sidecar route as evidence",
        "operator details: aippocampus navigate --operator-json",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus navigate",
        usage='aippocampus navigate ["cue"] [--json]',
        description=(
            "Show the boundary for cognitive-map and concept-expansion sidecars. "
            "Ordinary foreground continuity should start with recall/search."
        ),
    )
    parser.add_argument("cue", nargs="?")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Show maintainer-only module diagnostics as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cue = None if args.cue == "status" else args.cue
    payload = navigation_payload(cue=cue, operator_detail=bool(args.operator_json))
    if args.json_output or args.operator_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
