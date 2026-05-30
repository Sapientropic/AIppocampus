#!/usr/bin/env python3
"""Search AIppocampus clean-source messages without touching raw rollout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text, default_thread_clean_source_dir, resolve_artifact_path
from build_clean_source import SCOPE_LABEL_ORDER
from retrieval import split_query_terms
from semantic_scope_labels import (
    load_semantic_scope_labels,
    merged_scope_labels,
    semantic_labels_for_message,
)

LEGACY_CLEAN_SOURCE_DIR = ".aippocampus/clean-source"


def iter_clean_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
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


def score_message(message: dict[str, Any], terms: list[str]) -> float:
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


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def search_clean_source(
    cwd: str | Path,
    patterns: list[str],
    *,
    clean_source_dir: str | Path | None = None,
    limit: int = 10,
    snippet_chars: int = 700,
    scope_labels: list[str] | None = None,
) -> dict[str, Any]:
    cwd = Path(cwd).resolve()
    if clean_source_dir is None:
        global_dir = default_thread_clean_source_dir(cwd)
        legacy_dir = cwd / LEGACY_CLEAN_SOURCE_DIR
        source_dir = (
            global_dir
            if (global_dir / "messages.jsonl").exists()
            or not (legacy_dir / "messages.jsonl").exists()
            else legacy_dir
        )
    else:
        source_dir = resolve_artifact_path(
            clean_source_dir, cwd, default_thread_clean_source_dir(cwd)
        )
    messages_path = source_dir / "messages.jsonl"
    semantic_sidecar = load_semantic_scope_labels(source_dir)
    terms = split_query_terms(patterns)
    label_filter = [str(label).strip() for label in scope_labels or [] if str(label).strip()]
    known_scope_labels = set(SCOPE_LABEL_ORDER)
    warnings: list[dict[str, Any]] = [
        {
            "code": "unknown_scope_label",
            "scope_label": label,
            "message": f"Unknown scope label: {label}",
        }
        for label in label_filter
        if label not in known_scope_labels
    ]
    missing_scope_label_count = 0

    matches: list[dict[str, Any]] = []
    for message in iter_clean_messages(messages_path):
        if "scope_labels" not in message:
            missing_scope_label_count += 1
        base_scope_labels = [
            str(label) for label in message.get("scope_labels", []) if isinstance(label, str)
        ]
        semantic_scope_labels = semantic_labels_for_message(message, semantic_sidecar)
        message_scope_labels = merged_scope_labels(base_scope_labels, semantic_scope_labels)
        if label_filter and not set(label_filter).intersection(message_scope_labels):
            continue
        score = score_message(message, terms)
        if score <= 0:
            continue
        matches.append(
            {
                "id": message.get("message_id") or message.get("id"),
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "source_id": message.get("source_id"),
                "source_ref": message.get("source_ref"),
                "clean_ordinal": message.get("clean_ordinal"),
                "source_line": message.get("source_line"),
                "raw_start_line": message.get("raw_start_line") or message.get("source_line"),
                "raw_end_line": message.get("raw_end_line") or message.get("source_line"),
                "timestamp": message.get("timestamp"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "turn_index": message.get("turn_index"),
                "is_final": bool(message.get("is_final")),
                "scope_labels": message_scope_labels,
                "semantic_scope_labels": semantic_scope_labels,
                "score": round(score, 3),
                "snippet": compact_text(str(message.get("text") or ""), snippet_chars),
            }
        )
    matches.sort(
        key=lambda item: (-as_float(item.get("score")), as_int(item.get("source_line")))
    )
    if label_filter and missing_scope_label_count:
        warnings.append(
            {
                "code": "missing_scope_labels",
                "count": missing_scope_label_count,
                "message": "Some clean-source messages predate scope_labels; rebuild clean source before treating filtered results as complete.",
            }
        )
    return {
        "source": str(messages_path),
        "query_terms": terms,
        "scope_labels": label_filter,
        "warnings": warnings,
        "matches": matches[:limit],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patterns", nargs="+")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(
        "--clean-source-dir",
        default=None,
        help="Defaults to global clean source, with project-local legacy fallback.",
    )
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--snippet-chars", type=int, default=700)
    parser.add_argument(
        "--scope-label",
        action="append",
        default=None,
        help="Filter to clean-source messages carrying this scope label. Repeat for OR semantics.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = search_clean_source(
        args.cwd,
        args.patterns,
        clean_source_dir=args.clean_source_dir,
        limit=args.max,
        snippet_chars=args.snippet_chars,
        scope_labels=args.scope_label,
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
        for warning in result.get("warnings") or []:
            print(f"warning: {warning.get('code')}: {warning.get('message')}")
    return 0 if result["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
