#!/usr/bin/env python3
"""Build dynamic semantic recall triggers from source-backed candidates.

Hard-coded cue lists are only safety rails. This script turns reviewed
subconscious promotion candidates into a small data layer consumed by
`semantic_recall_gate.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text, now_utc
from build_associations import normalize_term, source_text_is_noise, term_is_noise
from memory_candidate_router import default_candidates_path, iter_jsonl, write_jsonl
from registry import registry_paths, unique_preserve
from retrieval import split_query_terms
from semantic_recall_gate import default_semantic_triggers_path

TRIGGER_SCHEMA_VERSION = 1
TRIGGER_TYPES = {"hook_trigger", "project_memory", "concept_edge"}
MIN_CONFIDENCE = 0.62
GENERIC_ALIASES = {
    "memory",
    "project",
    "candidate",
    "trigger",
    "source",
    "decision",
    "context",
    "记忆",
    "项目",
    "候选",
    "触发",
    "来源",
    "决策",
}


def trigger_key(candidate: dict[str, Any]) -> str:
    raw = "\n".join(
        [
            str(candidate.get("candidate_type") or ""),
            normalize_term(str(candidate.get("title") or "")).casefold(),
            "|".join(sorted(str(value) for value in candidate.get("source_finding_ids") or [])),
        ]
    )
    return "st_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def source_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in candidate.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        line = (
            ref.get("source_line")
            or ref.get("assistant_line")
            or ref.get("user_line")
            or ref.get("line")
        )
        clean = {
            "thread_key": ref.get("thread_key"),
            "title": ref.get("title"),
            "project_label": ref.get("project_label"),
            "turn_index": ref.get("turn_index"),
            "line": line,
            "message_id": ref.get("message_id"),
        }
        key = (
            str(clean.get("thread_key") or ""),
            str(clean.get("line") or ""),
            str(clean.get("message_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in clean.items() if v not in {None, ""}})
    return refs[:8]


def alias_candidates(candidate: dict[str, Any]) -> list[str]:
    text = "\n".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("summary") or ""),
            str(candidate.get("recommendation") or ""),
        ]
    )
    aliases: list[str] = []
    aliases.append(str(candidate.get("title") or ""))
    aliases.extend(split_query_terms([text]))
    aliases.extend(str(value) for value in candidate.get("concepts") or [])
    clean: list[str] = []
    for alias in aliases:
        alias = normalize_term(alias)
        if not alias or alias.casefold() in GENERIC_ALIASES:
            continue
        if len(alias) > 72 or source_text_is_noise(alias) or term_is_noise(alias):
            continue
        clean.append(alias)
    return unique_preserve(clean, limit=16)


def route_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    if candidate.get("kind") != "aippocampus_promotion_candidate":
        return None
    if candidate.get("status") not in {None, "staging", "active"}:
        return None
    candidate_type = str(candidate.get("candidate_type") or "")
    confidence = float(candidate.get("confidence") or 0.0)
    if candidate_type not in TRIGGER_TYPES or confidence < MIN_CONFIDENCE:
        return None
    refs = source_refs(candidate)
    if not refs:
        return None
    aliases = alias_candidates(candidate)
    if not aliases:
        return None
    return {
        "schema_version": TRIGGER_SCHEMA_VERSION,
        "kind": "aippocampus_semantic_trigger",
        "trigger_id": trigger_key(candidate),
        "created_at": now_utc(),
        "status": "active",
        "source": "semantic_trigger_router",
        "source_candidate_type": candidate_type,
        "title": compact_text(str(candidate.get("title") or ""), 100),
        "concept": compact_text(str(candidate.get("title") or ""), 100),
        "aliases": aliases,
        "when_to_use": compact_text(str(candidate.get("summary") or ""), 320),
        "when_not_to_use": "Use as a semantic recall hint only; search clean source before presenting exact claims as facts.",
        "confidence": round(confidence, 4),
        "source_refs": refs,
    }


def build_semantic_triggers(
    *,
    candidates_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for candidate in iter_jsonl(candidates_path):
        trigger = route_candidate(candidate)
        if not trigger:
            continue
        key = str(trigger.get("trigger_id"))
        existing = by_key.get(key)
        if existing and float(existing.get("confidence") or 0.0) >= float(
            trigger.get("confidence") or 0.0
        ):
            continue
        by_key[key] = trigger
    rows = sorted(
        by_key.values(),
        key=lambda row: (float(row.get("confidence") or 0.0), str(row.get("title") or "")),
        reverse=True,
    )
    write_jsonl(output_path, rows)
    summary = {
        "schema_version": TRIGGER_SCHEMA_VERSION,
        "kind": "aippocampus_semantic_trigger_routing",
        "created_at": now_utc(),
        "source_candidates": str(candidates_path),
        "trigger_count": len(rows),
        "output": str(output_path),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--candidates")
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    candidates = (
        Path(args.candidates).resolve()
        if args.candidates
        else default_candidates_path(registry_path=registry_path)
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else default_semantic_triggers_path(registry_path=registry_path)
    )
    result = build_semantic_triggers(candidates_path=candidates, output_path=output)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"semantic triggers: {result['trigger_count']}")
        print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
