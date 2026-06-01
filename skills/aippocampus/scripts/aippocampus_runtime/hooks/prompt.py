#!/usr/bin/env python3
"""Codex UserPromptSubmit hook glue for ambient long-thread recall."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aippocampus_runtime import core as runtime_core

DEFAULT_SEARCH_BUDGET_FALLBACK = 3
PROMPT_HOOK_SEMANTIC_TIMEOUT_FALLBACK = float(os.environ.get("AIPPOCAMPUS_PROMPT_SEMANTIC_TIMEOUT", "2.5"))
PROMPT_HOOK_MAX_ELAPSED_MS_FALLBACK = int(os.environ.get("AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS", "4300"))
_RUNTIME_EXPORTS = set(
    "DEFAULT_SEARCH_BUDGET PROMPT_HOOK_SEMANTIC_TIMEOUT SCENT_THRESHOLD association_boost "
    "ambient_debug_summary apply_dream_delivery_boundary assess_prompt context_for_hook "
    "hook_input_from_stdin hook_stdout_payload merge_association_candidates "
    "public_hook_debug_payload".split()
)
_RUNTIME_CACHE: dict[str, Any] | None = None

def _add_dream_delivery_arguments(parser: argparse.ArgumentParser) -> None:
    try:
        from aippocampus_runtime.dream import delivery_policy as dream_delivery  # noqa: PLC0415
    except Exception:
        parser.add_argument("--dream-shadow-ab", action="store_true")
        parser.add_argument("--dream-shadow-log")
        parser.add_argument("--dream-shadow-salt", default=os.environ.get("AIPPOCAMPUS_DREAM_SHADOW_AB_SALT"))
        parser.add_argument("--dream-delivery-mode")
        parser.add_argument("--dream-rollout-rate", type=float, default=None)
    else:
        dream_delivery.add_dream_delivery_arguments(parser)

def _prepare_dream_delivery(*, prompt: str, hook_input: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    try:
        from aippocampus_runtime.dream import delivery_policy as dream_delivery  # noqa: PLC0415
    except Exception:
        return {"mode": "off", "event": None, "allow_dream": False, "dream_hypothesis_limit": 0, "reason": "policy_unavailable"}
    return dream_delivery.prepare_dream_delivery(prompt=prompt, hook_input=hook_input, args=args)

def _load_runtime() -> dict[str, Any]:
    """Load split recall modules lazily so partial installs quietly skip."""
    global _RUNTIME_CACHE
    if _RUNTIME_CACHE is not None:
        return _RUNTIME_CACHE

    from aippocampus_runtime.recall.prompt_context_render import ambient_debug_summary, apply_dream_delivery_boundary, context_for_hook, hook_stdout_payload, public_hook_debug_payload  # noqa: I001, PLC0415
    from aippocampus_runtime.recall.prompt_recall_core import (  # noqa: PLC0415
        DEFAULT_SEARCH_BUDGET,
        PROMPT_HOOK_SEMANTIC_TIMEOUT,
        SCENT_THRESHOLD,
        association_boost,
        hook_input_from_stdin,
        merge_association_candidates,
    )
    from aippocampus_runtime.recall.prompt_recall_decision import assess_prompt  # noqa: PLC0415

    _RUNTIME_CACHE = {
        "DEFAULT_SEARCH_BUDGET": DEFAULT_SEARCH_BUDGET,
        "PROMPT_HOOK_SEMANTIC_TIMEOUT": PROMPT_HOOK_SEMANTIC_TIMEOUT,
        "SCENT_THRESHOLD": SCENT_THRESHOLD,
        "association_boost": association_boost,
        "ambient_debug_summary": ambient_debug_summary,
        "apply_dream_delivery_boundary": apply_dream_delivery_boundary,
        "assess_prompt": assess_prompt,
        "context_for_hook": context_for_hook,
        "hook_input_from_stdin": hook_input_from_stdin,
        "hook_stdout_payload": hook_stdout_payload,
        "merge_association_candidates": merge_association_candidates,
        "public_hook_debug_payload": public_hook_debug_payload,
    }
    return _RUNTIME_CACHE


def __getattr__(name: str) -> Any:
    if name in _RUNTIME_EXPORTS:
        return _load_runtime()[name]
    raise AttributeError(name)


def write_debug_log(
    result: dict[str, Any],
    *,
    hook_input: dict[str, Any] | None = None,
    log_path: Path | None = None,
    include_skip: bool = False,
) -> None:
    if result.get("decision") == "skip" and not include_skip:
        return
    path = log_path or (runtime_core.aippocampus_registry_dir() / "aippocampus_prompt_hook.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    ambient_summary = _load_runtime()["ambient_debug_summary"](result)
    semantic_gate = result.get("semantic_gate") or {}
    semantic_debug_keys = ("available", "decision", "confidence", "cached", "query_aliases", "availability_reason", "diagnostic", "elapsed_ms", "timeout", "budget", "error_buckets")
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
            {
                "thread_key": item.get("thread_key"),
                "title": item.get("title"),
                "score": item.get("score"),
            }
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
            {
                "thread_key": item.get("thread_key"),
                "line": item.get("line"),
                "phase": item.get("phase"),
            }
            for item in result.get("evidence", [])[:5]
        ],
        "ambient_recall": ambient_summary,
        "elapsed_ms": result.get("elapsed_ms"),
    }
    # Redact only at the write boundary; recall scoring still uses raw terms.
    safe_event = runtime_core.sanitize_external_model_payload(event)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(safe_event, ensure_ascii=False) + "\n")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", help="Dry-run prompt text. If omitted, read Codex hook JSON from stdin.")
    parser.add_argument("--cwd", help="Workspace cwd override for dry runs.")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--cognitive-map")
    parser.add_argument("--concept-graph")
    parser.add_argument("--working-memory")
    parser.add_argument("--ambient-policy")
    parser.add_argument("--semantic-triggers")
    parser.add_argument("--semantic-cues")
    parser.add_argument("--semantic-cache")
    parser.add_argument("--ambient-cache")
    warm_group = parser.add_mutually_exclusive_group()
    warm_group.add_argument("--warm-background", action="store_true", dest="warm_background", default=None)
    warm_group.add_argument("--no-warm-background", action="store_false", dest="warm_background")
    parser.add_argument("--warm-job-dir")
    parser.add_argument("--warm-max-workers", type=int, default=None)
    parser.add_argument("--warm-timeout", type=float, default=None)
    parser.add_argument("--warm-quorum", type=int, default=None)
    parser.add_argument("--semantic-gate", choices=["auto", "on", "off"], default=None)
    parser.add_argument("--session-id", help="Dry-run thread/session id for ambient thread cache.")
    parser.add_argument("--topic-epoch", help="Override ambient recall topic epoch for dry runs.")
    parser.add_argument("--semantic-timeout", type=float, default=PROMPT_HOOK_SEMANTIC_TIMEOUT_FALLBACK)
    parser.add_argument(
        "--max-elapsed-ms",
        type=int,
        default=PROMPT_HOOK_MAX_ELAPSED_MS_FALLBACK,
        help="Fail-open budget for the whole prompt hook. Set 0 to disable.",
    )
    parser.add_argument("--no-semantic-gate", action="store_true")
    parser.add_argument("--no-thread-cache", action="store_true")
    parser.add_argument("--no-cognitive-map", action="store_true")
    parser.add_argument("--no-concept-graph", action="store_true")
    parser.add_argument("--search-budget", type=int, default=DEFAULT_SEARCH_BUDGET_FALLBACK)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--log-skip", action="store_true")
    _add_dream_delivery_arguments(parser)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    hook_input: dict[str, Any] = {}
    try:
        runtime = _load_runtime()
        if args.prompt is None:
            hook_input = runtime["hook_input_from_stdin"]()
            prompt = str(hook_input.get("prompt") or "")
            cwd = Path(args.cwd or hook_input.get("cwd") or os.getcwd())
        else:
            prompt = args.prompt
            cwd = Path(args.cwd or os.getcwd())
        thread_id = str(args.session_id or hook_input.get("session_id") or "").strip() or None
        dream_delivery = _prepare_dream_delivery(prompt=prompt, hook_input=hook_input, args=args)
        result = runtime["assess_prompt"](
            prompt,
            cwd=cwd,
            registry_path=Path(args.registry) if args.registry else None,
            registry_dir=Path(args.registry_dir) if args.registry_dir else None,
            cognitive_map_path=Path(args.cognitive_map) if args.cognitive_map else None,
            concept_graph_path=Path(args.concept_graph) if args.concept_graph else None,
            working_memory_path=Path(args.working_memory) if args.working_memory else None,
            ambient_policy_path=Path(args.ambient_policy) if args.ambient_policy else None,
            semantic_triggers_path=Path(args.semantic_triggers) if args.semantic_triggers else None,
            semantic_cues_path=Path(args.semantic_cues) if args.semantic_cues else None,
            semantic_cache_path=Path(args.semantic_cache) if args.semantic_cache else None,
            ambient_cache_path=Path(args.ambient_cache) if args.ambient_cache else None,
            semantic_gate_mode="off" if args.no_semantic_gate else args.semantic_gate,
            semantic_timeout=args.semantic_timeout,
            use_semantic_gate=not args.no_semantic_gate,
            use_cognitive_map=not args.no_cognitive_map,
            use_concept_graph=not args.no_concept_graph,
            search_budget=args.search_budget,
            max_elapsed_ms=args.max_elapsed_ms,
            thread_id=thread_id,
            topic_epoch=args.topic_epoch,
            use_thread_cache=not args.no_thread_cache,
            warm_background=args.warm_background,
            warm_job_dir=Path(args.warm_job_dir) if args.warm_job_dir else None,
            warm_max_workers=args.warm_max_workers,
            warm_timeout=args.warm_timeout,
            warm_quorum=args.warm_quorum,
            dream_hypothesis_limit=dream_delivery["dream_hypothesis_limit"],
        )
        result = runtime["apply_dream_delivery_boundary"](
            result,
            allow_dream=bool(dream_delivery["allow_dream"]),
            max_dream_hypotheses=1,
            reason=str(dream_delivery["reason"]),
        )
        if args.log or args.log_skip:
            write_debug_log(result, hook_input=hook_input, include_skip=args.log_skip)
        if args.json_output:
            print(json.dumps(runtime["public_hook_debug_payload"](result), ensure_ascii=False, indent=2))
            return 0
        payload = runtime["hook_stdout_payload"](result)
        if payload:
            print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        if args.strict:
            raise
        if args.json_output:
            print(json.dumps({"decision": "skip", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
