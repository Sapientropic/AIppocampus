#!/usr/bin/env python3
"""Decide whether a long Codex thread should search its external memory."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from retrieval import (
    active_recall_decision,
    expanded_terms_from_anchors,
    match_anchors,
    split_query_terms,
)


SCRIPT_DIR = Path(__file__).resolve().parent


def run_json(cmd: list[str], *, allow_empty_result: bool = False) -> dict:
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        if allow_empty_result and proc.stdout.strip().startswith("{"):
            return json.loads(proc.stdout)
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def read_prompt(args: argparse.Namespace) -> str:
    parts = list(args.prompt or [])
    if args.stdin:
        parts.append(sys.stdin.read())
    return " ".join(parts).strip()


def resolve_anchor_path(cwd: Path, anchors: str) -> Path:
    path = Path(anchors)
    if not path.is_absolute():
        path = cwd / path
    return path


def search_terms_from_query(query_terms: list[str], prompt: str) -> list[str]:
    noise = {
        "还记得",
        "记得",
        "之前",
        "前面",
        "刚才",
        "上次",
        "那个",
        "这个",
        "那篇",
        "这篇",
        "我说过",
        "你说过",
        "之前那个",
        "的说法",
        "那段有关系",
    }
    out: list[str] = []
    for term in query_terms:
        low = term.casefold().strip()
        if low in noise:
            continue
        # Long prompts with deictic words are useful for deciding to recall but
        # poor FTS clauses. Keep their extracted content terms instead.
        if len(term) > 20 and any(marker in prompt for marker in ("之前", "还记得", "那个", "这个", "那篇", "这篇")):
            continue
        out.append(term)
    return out or [prompt]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="*", help="Current user message or task description.")
    parser.add_argument("--stdin", action="store_true", help="Read prompt text from stdin and append it to positional text.")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--search", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--max", type=int, default=8)
    parser.add_argument("--context", type=int, default=1)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    prompt = read_prompt(args)
    if not prompt:
        raise SystemExit("active_recall.py requires prompt text or --stdin")

    health = run_json([sys.executable, str(SCRIPT_DIR / "aippocampus_health.py"), "--cwd", str(cwd), "--json"])
    anchor_path = resolve_anchor_path(cwd, args.anchors)
    query_terms = split_query_terms([prompt])
    anchors = match_anchors(anchor_path, query_terms) if anchor_path.exists() else []
    expanded_terms = expanded_terms_from_anchors(query_terms, anchors, limit=24)
    decision = active_recall_decision(prompt, anchors, health)

    should_search = args.search == "always" or (args.search == "auto" and decision["decision"] == "search")
    search_payload = None
    if should_search:
        # Pass the user's extracted clues to search_rollout and let that command
        # do its own anchor expansion once. Passing already-expanded anchor terms
        # here caused broad anchors such as "vault" to be expanded twice, which
        # made maintenance/dashboard hits crowd out the original remembered turn.
        search_terms = search_terms_from_query(query_terms, prompt)[:10]
        segments = health.get("segments") or {}
        use_segments = bool(segments.get("exists")) or bool(segments.get("needed"))
        if use_segments:
            cmd = [
                sys.executable,
                str(SCRIPT_DIR / "search_segments.py"),
                *search_terms,
                "--cwd",
                str(cwd),
                "--mode",
                "hybrid",
                "--max",
                str(args.max),
                "--context",
                str(args.context),
                "--json",
            ]
            if not segments.get("exists") or segments.get("stale"):
                cmd.append("--build-segments")
        else:
            cmd = [
                sys.executable,
                str(SCRIPT_DIR / "search_rollout.py"),
                *search_terms,
                "--cwd",
                str(cwd),
                "--build-index",
                "--mode",
                "hybrid",
                "--max",
                str(args.max),
                "--context",
                str(args.context),
                "--json",
            ]
        search_payload = run_json(cmd, allow_empty_result=True)

    result = {
        "prompt": prompt,
        "decision": decision,
        "query_terms": query_terms,
        "suggested_terms": expanded_terms,
        "matched_anchors": anchors,
        "health_summary": {
            "status": health.get("status"),
            "index_stale": health.get("index", {}).get("stale"),
            "segments": health.get("segments"),
            "checkpoint_due": health.get("checkpoint", {}).get("due"),
            "graphify_stale": health.get("graphify", {}).get("stale"),
            "recommended_actions": health.get("recommended_actions", []),
        },
        "searched": bool(search_payload),
        "search": search_payload,
    }

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"decision: {decision['decision']} (score={decision['score']}, confidence={decision['confidence']})")
        for reason in decision["reasons"]:
            print(f"- {reason}")
        print(f"suggested terms: {', '.join(expanded_terms[:12]) or '(none)'}")
        if search_payload:
            print("\nsearch hits:")
            for hit in search_payload.get("matches", [])[: args.max]:
                print(f"- score {hit.get('score')} | line {hit.get('line')} | {hit.get('role')}: {hit.get('snippet')}")
        else:
            print("search: skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
