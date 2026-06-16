#!/usr/bin/env python3
"""CLI wrapper for recall why/why-not diagnostics."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Mapping

from aippocampus_runtime.recall.why_diagnostics import recall_diagnostic_report
from aippocampus_runtime.recall.why_reason_codes import DEFAULT_MAX_ROUTES


def render_text(payload: Mapping[str, Any]) -> str:
    mode = str(payload.get("mode") or "why-recall")
    decision = str(payload.get("decision") or "unknown")
    diagnostic = str(payload.get("diagnostic_class") or "unknown")
    reasons = [str(item) for item in payload.get("reasons") or []][:3]
    specificity = payload.get("route_specificity") or "unknown"
    action_card = payload.get("action_card") if isinstance(payload.get("action_card"), Mapping) else {}
    if mode == "why-not-recall" and diagnostic == "surfaced_but_low_specificity":
        happened = "A route did surface, but it was too broad to treat as a good recall answer."
        next_command = "aippocampus why-recall \"<more specific cue>\""
    elif decision == "surfaced":
        happened = "Recall surfaced a source route."
        next_command = "aippocampus agent recall \"<cue>\" --public"
    elif decision in {"suppressed", "silent"}:
        happened = "Recall stayed quiet or suppressed the route."
        next_command = "tighten the cue, then run aippocampus why-recall \"<cue>\""
    else:
        happened = f"Recall diagnostic returned {decision}."
        next_command = "aippocampus health --json"
    if action_card.get("next_command"):
        next_command = str(action_card["next_command"])
    elif payload.get("next_safe_action") == "reopen_source":
        next_command = "aippocampus agent recall \"<cue>\" --public; then deepen before claims"
    display_cue = str(payload.get("_display_cue") or "").strip()
    if display_cue:
        quoted = json.dumps(display_cue, ensure_ascii=False)
        next_command = next_command.replace('"<cue>"', quoted)
        next_command = next_command.replace('"<distinctive exact phrase>"', quoted)
        next_command = next_command.replace('" <cue> "', f" {quoted} ")
        if "then deepen route 1" in next_command:
            next_command = next_command.replace(
                "then deepen route 1",
                "then aippocampus agent deepen --request 1 --last-recall --json",
            )
    lines = [
        f"AIppocampus {mode}",
        f"what happened: {happened}",
        f"specificity: {specificity}",
        f"why: {', '.join(reasons) or 'no blocking reason recorded'}",
        f"next: {next_command}",
        "boundary: this diagnostic is route guidance, not source evidence.",
    ]
    return "\n".join(lines)


def _description_for_prog(prog: str) -> str:
    if "why-not" in prog:
        return """What this command is for:
  Explain why memory did not help, or why a surfaced route is too broad to trust.
  Primary next action: refine cue first; deepen only if continuity genuinely matters.

Advanced/operator detail:
  Semantic, lock, cache, and handle flags are diagnostics for local investigation."""
    return """What this command is for:
  Explain why recall surfaced, stayed silent, or degraded before you rely on memory.
  Primary next action: deepen selected route before claims, or refine cue if no route surfaced.

Advanced/operator detail:
  Semantic, lock, cache, and handle flags are diagnostics for local investigation."""


def build_parser(prog: str = "aippocampus why-recall") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        usage=f"{prog} cue [--json] [advanced/operator flags]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=_description_for_prog(prog),
    )
    parser.add_argument("cue", nargs="?")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--clean-source-dir")
    parser.add_argument("--registry-dir")
    parser.add_argument("--registry")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_ROUTES)
    parser.add_argument("--handle")
    parser.add_argument("--thread-id")
    parser.add_argument("--topic-epoch")
    parser.add_argument("--lock-id")
    parser.add_argument("--lock-path")
    parser.add_argument("--cache-path")
    parser.add_argument("--semantic-result-json")
    parser.add_argument("--run-semantic-gate", action="store_true")
    parser.add_argument("--semantic-gate-mode", choices=["off", "auto", "on"], default="off")
    parser.add_argument("--semantic-timeout", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    return parser


def render_compact_help(mode: str) -> str:
    if mode == "why-not-recall":
        first_line = "Explain silence or no-help recall before you broaden search."
        example = 'aippocampus why-not-recall "old decision about setup"'
        when = "Use why-not-recall when recall stayed quiet or surfaced only broad/noisy routes."
    else:
        first_line = "Explain a surfaced, stale-looking, broad, or surprising recall route."
        example = 'aippocampus why-recall "old decision about setup"'
        when = "Use why-recall after recall/search when you need to understand a route before relying on it."
    return "\n".join(
        [
            f"usage: aippocampus {mode} \"<cue>\" [--json]",
            "",
            "What this command is for:",
            f"  {first_line}",
            "",
            "Useful shapes:",
            f"  {example}",
            '  aippocampus agent recall "old cue" --json',
            "  aippocampus agent deepen --request 1 --last-recall --json",
            "  primary next action: deepen selected route before claims, or refine cue if no route surfaced.",
            "",
            "When to use it:",
            f"  {when}",
            "  Use agent recall/deepen for the normal source-backed path.",
            "",
            "Boundary:",
            "  This is recovery/explanation guidance, not source evidence.",
            "  Reopen/deepen the selected route before claims.",
            "",
            "Advanced/operator flags:",
            f"  aippocampus {mode} --help-advanced",
        ]
    )


def _recovery_payload(mode: str) -> dict[str, Any]:
    return {
        "kind": "aippocampus_recall_diagnostic_recovery",
        "mode": mode,
        "ok": False,
        "error": {
            "code": "cue_required",
            "message": "Provide a cue so the diagnostic can explain a recall route or silence.",
        },
        "example_cue": "old decision about setup",
        "when_to_use": {
            "why-recall": "Use when recall surfaced a route that is surprising, stale-looking, broad, or needs explanation.",
            "why-not-recall": "Use when recall stayed silent or did not help for a cue you expected to work.",
        },
        "next_actions": [
            {
                "label": "try recall first",
                "command": 'aippocampus agent recall "old decision about setup" --json',
            },
            {
                "label": "deepen selected route",
                "command": "aippocampus agent deepen --request 1 --last-recall --json",
            },
        ],
        "claim_boundary": "Diagnostic output is route guidance, not source evidence; reopen source before claims.",
    }


def render_recovery_text(payload: Mapping[str, Any]) -> str:
    mode = str(payload.get("mode") or "why-recall")
    actions = [row for row in payload.get("next_actions") or [] if isinstance(row, Mapping)]
    lines = [
        f"AIppocampus {mode}",
        "what happened: no cue was provided, so no diagnostic ran.",
        "example cue: old decision about setup",
        "when to use why-recall: explain a surprising or broad surfaced route.",
        "when to use why-not-recall: explain silence or no-help recall.",
    ]
    if actions:
        lines.append("next: " + str(actions[0].get("command")))
        if len(actions) > 1:
            lines.append("then: " + str(actions[1].get("command")))
    lines.append("boundary: diagnostic route guidance is not source evidence.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv or [])
    mode = "why-recall"
    if args_list and args_list[0] in {"why-recall", "why-not-recall", "why-not"}:
        raw_mode = args_list.pop(0)
        mode = "why-not-recall" if raw_mode == "why-not" else raw_mode
    prog = f"aippocampus {mode}"
    if args_list and args_list[0] in {"--help", "-h"}:
        print(render_compact_help(mode))
        return 0
    if args_list and args_list[0] in {"--help-advanced", "--advanced-help"}:
        build_parser(prog=prog).print_help()
        return 0
    args = build_parser(prog=prog).parse_args(args_list)
    if not args.cue:
        payload = _recovery_payload(mode)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else render_recovery_text(payload))
        return 2
    payload = recall_diagnostic_report(
        cue=args.cue,
        mode=mode,
        cwd=args.cwd,
        clean_source_dir=args.clean_source_dir,
        registry_dir=args.registry_dir,
        registry_path=args.registry,
        max_routes=args.max,
        handle=args.handle,
        thread_id=args.thread_id,
        topic_epoch=args.topic_epoch,
        lock_id=args.lock_id,
        lock_path=args.lock_path,
        cache_path=args.cache_path,
        semantic_result_json=args.semantic_result_json,
        run_live_semantic_gate=args.run_semantic_gate,
        semantic_gate_mode=args.semantic_gate_mode,
        semantic_timeout=args.semantic_timeout,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        text_payload = dict(payload)
        text_payload["_display_cue"] = args.cue
        print(render_text(text_payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
