#!/usr/bin/env python3
"""Search AIppocampus clean-source messages without touching raw rollout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from retrieval import split_query_terms
from aippocampuslib import compact_text


DEFAULT_CLEAN_SOURCE_DIR = ".aippocampus/clean-source"


def iter_clean_messages(path: Path) -> list[dict]:
    messages: list[dict] = []
    if not path.exists():
        return messages
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("text"):
                messages.append(item)
    return messages


def score_message(message: dict, terms: list[str]) -> float:
    text = str(message.get("text") or "")
    low = text.casefold()
    score = 0.0
    for term in terms:
        needle = term.casefold()
        if not needle:
            continue
        count = low.count(needle)
        if count:
            score += 8.0 + count * min(len(term), 20)
    if message.get("is_final") or message.get("phase") == "final_answer":
        score += 18.0
    elif message.get("role") == "user":
        score += 3.0
    elif message.get("phase") == "commentary":
        score -= 2.0
    return score


def search_clean_source(
    cwd: str | Path,
    patterns: list[str],
    *,
    clean_source_dir: str | Path = DEFAULT_CLEAN_SOURCE_DIR,
    limit: int = 10,
    snippet_chars: int = 700,
) -> dict:
    cwd = Path(cwd).resolve()
    source_dir = Path(clean_source_dir)
    if not source_dir.is_absolute():
        source_dir = cwd / source_dir
    messages_path = source_dir / "messages.jsonl"
    terms = split_query_terms(patterns)

    matches = []
    for message in iter_clean_messages(messages_path):
        score = score_message(message, terms)
        if score <= 0:
            continue
        matches.append(
            {
                "id": message.get("message_id") or message.get("id"),
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "source_id": message.get("source_id"),
                "clean_ordinal": message.get("clean_ordinal"),
                "source_line": message.get("source_line"),
                "raw_start_line": message.get("raw_start_line") or message.get("source_line"),
                "raw_end_line": message.get("raw_end_line") or message.get("source_line"),
                "timestamp": message.get("timestamp"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "turn_index": message.get("turn_index"),
                "is_final": bool(message.get("is_final")),
                "score": round(score, 3),
                "snippet": compact_text(str(message.get("text") or ""), snippet_chars),
            }
        )
    matches.sort(key=lambda item: (-float(item.get("score") or 0.0), int(item.get("source_line") or 0)))
    return {
        "source": str(messages_path),
        "query_terms": terms,
        "matches": matches[:limit],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patterns", nargs="+")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--clean-source-dir", default=DEFAULT_CLEAN_SOURCE_DIR)
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--snippet-chars", type=int, default=700)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = search_clean_source(
        args.cwd,
        args.patterns,
        clean_source_dir=args.clean_source_dir,
        limit=args.max,
        snippet_chars=args.snippet_chars,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"clean source: {result['source']}")
        for match in result["matches"]:
            print(
                f"- line {match.get('source_line')} | {match.get('role')} | "
                f"phase={match.get('phase') or '(none)'} | score={match.get('score')}"
            )
            print(f"  {match.get('snippet')}")
    return 0 if result["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
