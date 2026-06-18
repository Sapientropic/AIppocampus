#!/usr/bin/env python3
"""Foreground boundary card for navigation sidecars."""

from __future__ import annotations

import argparse
import json
import shlex
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
)

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
            foreground_shell_action(
                action_id="recall_with_supplied_cue",
                command=f"aippocampus agent recall {_quote(clean_cue)} --json",
                label="Recall from supplied cue",
                why="Use recall first so a foreground agent gets reopenable route choices.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
            foreground_shell_action(
                action_id="search_exact_supplied_cue",
                command=f"aippocampus search {_quote(clean_cue)} --json",
                label="Search supplied cue",
                why="Use search when the cue is exact wording or a stable source phrase.",
                mutation_risk="read_only",
                claim_boundary="search_result_requires_source_boundary",
            ),
        ]
        status = "foreground_route_available"
    else:
        foreground_next_actions = [
            foreground_template_action(
                action_id="provide_navigation_cue",
                command_template='aippocampus navigate "{cue}" --json',
                requires=["cue"],
                label="Provide navigation cue",
                why="Navigation sidecars need a concrete cue before they can route useful attention.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
            foreground_template_action(
                action_id="use_recall_directly",
                command_template='aippocampus agent recall "{cue}" --json',
                requires=["cue"],
                label="Use recall directly",
                why="Recall is the ordinary frontdoor when you already have a user/task cue.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
        ]
        status = "needs_cue"
    payload = {
        "kind": "aippocampus_navigation_frontdoor",
        "ok": True,
        "status": status,
        "detail": "operator" if operator_detail else "compact",
        "cue_supplied": bool(clean_cue),
        "lanes": lanes,
        "operator_next_action": "aippocampus navigate --operator-json",
        "source_boundary": {
            "navigation_sidecars_are_not_source_truth": True,
            "source_reopen_required_before_claim": True,
            "model_job_started": False,
        },
    }
    payload.update(
        canonical_foreground_action_fields(
            foreground_next_actions[0],
            safe_next_actions=foreground_next_actions,
        )
    )
    return payload


def render_text(payload: dict[str, Any]) -> str:
    action = payload.get("foreground_action") if isinstance(payload.get("foreground_action"), dict) else {}
    next_command = action.get("command") or action.get("command_template") or ""
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
