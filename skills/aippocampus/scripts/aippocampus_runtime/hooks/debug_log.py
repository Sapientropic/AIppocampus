"""Explicit prompt-hook debug logging with write-boundary redaction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aippocampus_runtime import core as runtime_core


def write_debug_log(
    result: dict[str, Any],
    *,
    hook_input: dict[str, Any] | None = None,
    log_path: Path | None = None,
    include_skip: bool = False,
) -> None:
    if result.get("decision") == "skip" and not include_skip:
        return
    from aippocampus_runtime.recall.prompt_context_render import ambient_debug_summary  # noqa: I001, PLC0415

    path = log_path or (runtime_core.aippocampus_registry_dir() / "aippocampus_prompt_hook.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    ambient_summary = ambient_debug_summary(result)
    semantic_gate = result.get("semantic_gate") or {}
    semantic_debug_keys = (
        "available",
        "decision",
        "confidence",
        "cached",
        "query_aliases",
        "availability_reason",
        "diagnostic",
        "elapsed_ms",
        "timeout",
        "budget",
        "error_buckets",
    )
    event = {
        "timestamp": runtime_core.now_utc(),
        "session_id": (hook_input or {}).get("session_id"),
        "turn_id": (hook_input or {}).get("turn_id"),
        "decision": result.get("decision"),
        "score": result.get("score"),
        "confidence": result.get("confidence"),
        "query_terms": result.get("query_terms"),
        "concept_expansions": [
            {"term": item.get("term"), "score": item.get("score"), "depth": item.get("depth")}
            for item in result.get("concept_expansions", [])[:5]
        ],
        "cognitive_map": [
            {
                "route_id": item.get("route_id"),
                "landmarks": item.get("landmark_labels"),
                "matched_cues": item.get("matched_cues"),
                "thread_keys": item.get("thread_keys"),
                "score": item.get("score"),
            }
            for item in result.get("cognitive_map", [])[:4]
        ],
        "candidate_threads": [
            {"thread_key": item.get("thread_key"), "title": item.get("title"), "score": item.get("score")}
            for item in result.get("candidates", [])[:3]
        ],
        "working_memory": [
            {"title": item.get("title"), "route": item.get("route"), "score": item.get("score")}
            for item in result.get("working_memory", [])[:3]
        ],
        "semantic_gate": {**{key: semantic_gate.get(key) for key in semantic_debug_keys}, "aliases": semantic_gate.get("query_aliases")}
        if semantic_gate
        else None,
        "evidence": [
            {"thread_key": item.get("thread_key"), "line": item.get("line"), "phase": item.get("phase")}
            for item in result.get("evidence", [])[:5]
        ],
        "ambient_recall": ambient_summary,
        "elapsed_ms": result.get("elapsed_ms"),
    }
    # Redact only at the write boundary; recall scoring still uses raw terms.
    safe_event = runtime_core.sanitize_external_model_payload(event)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(safe_event, ensure_ascii=False) + "\n")
