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
    return "\n".join(
        [
            f"decision: {payload.get('decision')}",
            f"diagnostic_class: {payload.get('diagnostic_class')}",
            f"route_specificity: {payload.get('route_specificity')}",
            f"cue_hash: {payload.get('cue_hash')}",
            f"reasons: {', '.join(payload.get('reasons') or []) or 'none'}",
            f"route_ids: {', '.join(payload.get('route_ids') or []) or 'none'}",
            f"next_safe_action: {payload.get('next_safe_action')}",
            f"suggested_next: {payload.get('suggested_next')}",
        ]
    )


def build_parser(prog: str = "aippocampus why-recall") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Explain recall routing decisions.",
    )
    parser.add_argument("mode", choices=["why-recall", "why-not-recall"])
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
    prog = (
        f"aippocampus {args_list[0]}"
        if args_list and args_list[0] in {"why-recall", "why-not-recall"}
        else "aippocampus why-recall"
    )
    args = build_parser(prog=prog).parse_args(args_list)
    payload = recall_diagnostic_report(
        cue=args.cue,
        mode=args.mode,
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
