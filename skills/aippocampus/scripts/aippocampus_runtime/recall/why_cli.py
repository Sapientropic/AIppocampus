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
    if payload.get("next_safe_action") == "reopen_source":
        next_command = "aippocampus agent recall \"<cue>\" --public; then deepen before claims"
    lines = [
        f"AIppocampus {mode}",
        f"what happened: {happened}",
        f"specificity: {specificity}",
        f"why: {', '.join(reasons) or 'no blocking reason recorded'}",
        f"next: {next_command}",
        "boundary: this diagnostic is route guidance, not source evidence.",
    ]
    return "\n".join(lines)


def build_parser(prog: str = "aippocampus why-recall") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Explain recall routing decisions.",
    )
    parser.add_argument("cue")
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


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv or [])
    mode = "why-recall"
    if args_list and args_list[0] in {"why-recall", "why-not-recall"}:
        mode = args_list.pop(0)
    prog = f"aippocampus {mode}"
    args = build_parser(prog=prog).parse_args(args_list)
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
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
