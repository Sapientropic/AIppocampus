#!/usr/bin/env python3
"""Codex UserPromptSubmit hook glue for ambient long-thread recall."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.hooks.prompt_fallbacks import (
    _has_final_diagnostic_budget,
    add_dream_delivery_arguments,
    fallback_payload,
    prepare_dream_delivery,
    prompt_hook_audit_status,
    write_debug_log,
    write_prompt_hook_audit_status,
    write_skip_telemetry,
)

__all__ = ["prompt_hook_audit_status", "write_debug_log", "write_prompt_hook_audit_status", "write_skip_telemetry"]

DEFAULT_SEARCH_BUDGET_FALLBACK = 3
PROMPT_HOOK_SEMANTIC_TIMEOUT_FALLBACK = float(os.environ.get("AIPPOCAMPUS_PROMPT_SEMANTIC_TIMEOUT", "1.2"))
PROMPT_HOOK_MAX_ELAPSED_MS_FALLBACK = int(os.environ.get("AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS", "3500"))
_RUNTIME_EXPORTS = set(
    "DEFAULT_SEARCH_BUDGET PROMPT_HOOK_SEMANTIC_TIMEOUT SCENT_THRESHOLD association_boost ambient_debug_summary apply_dream_delivery_boundary assess_prompt context_for_hook "
    "hook_input_from_stdin hook_stdout_payload merge_association_candidates "
    "public_hook_debug_payload".split()
)
_RUNTIME_CACHE: dict[str, Any] | None = None


def _add_dream_delivery_arguments(parser: argparse.ArgumentParser) -> None:
    add_dream_delivery_arguments(parser)

def _prepare_dream_delivery(*, prompt: str, hook_input: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return prepare_dream_delivery(prompt=prompt, hook_input=hook_input, args=args)


def _emit_json(payload: Any, *, indent: int | None = None) -> None:
    from aippocampus_runtime.core import sanitize_external_model_payload  # noqa: PLC0415
    from aippocampus_runtime.public_output import emit_public_text  # noqa: PLC0415

    emit_public_text(
        json.dumps(sanitize_external_model_payload(payload), ensure_ascii=False, indent=indent)
    )


def _append_detail_warning(result: dict[str, Any], *, code: str, exc: BaseException) -> None:
    warnings = result.setdefault("degraded_warnings", [])
    if isinstance(warnings, list):
        warnings.append(
            {
                "code": code,
                "message": str(exc) or exc.__class__.__name__,
                "surface": "prompt_hook_final_diagnostics",
                "foreground_action_required": False,
            }
        )


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


def main(argv: list[str] | None = None) -> int:
    main_start = time.perf_counter()
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
    parser.add_argument("--living-cues")
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
    parser.add_argument("--max-elapsed-ms", type=int, default=PROMPT_HOOK_MAX_ELAPSED_MS_FALLBACK, help="Fail-open budget for the whole prompt hook. Set 0 to disable.")
    parser.add_argument("--no-semantic-gate", action="store_true")
    parser.add_argument("--no-thread-cache", action="store_true")
    parser.add_argument("--no-cognitive-map", action="store_true")
    parser.add_argument("--no-concept-graph", action="store_true")
    parser.add_argument("--search-budget", type=int, default=DEFAULT_SEARCH_BUDGET_FALLBACK)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--log-skip", action="store_true")
    parser.add_argument("--audit-status-path")
    parser.add_argument("--no-audit-status", action="store_true")
    parser.add_argument("--skip-telemetry-path")
    parser.add_argument("--no-skip-telemetry", action="store_true")
    _add_dream_delivery_arguments(parser)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    hook_input: dict[str, Any] = {}
    runtime_load_ms = 0.0
    try:
        runtime_load_start = time.perf_counter()
        runtime = _load_runtime()
        runtime_load_ms = round((time.perf_counter() - runtime_load_start) * 1000, 2)
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
            living_cues_path=Path(args.living_cues) if args.living_cues else None,
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
            dream_hypothesis_limit=dream_delivery.get("dream_hypothesis_limit", 0),
            dream_delivery_prefilter_reason=str(
                dream_delivery.get("prefilter_reason") or "budget_zero"
            ),
            dream_delivery_task_mode=str(dream_delivery.get("task_mode") or "unknown"),
            detail="trace" if args.json_output else None,
        )
        result = runtime["apply_dream_delivery_boundary"](
            result,
            allow_dream=bool(dream_delivery["allow_dream"]),
            max_dream_hypotheses=1,
            reason=str(dream_delivery["reason"]),
        )
        can_write_final_diagnostics = _has_final_diagnostic_budget(started=main_start, max_elapsed_ms=args.max_elapsed_ms)
        try:
            # Diagnostic telemetry must never block Codex prompt submission.
            if can_write_final_diagnostics:
                telemetry_start = time.perf_counter()
                write_skip_telemetry(
                    result,
                    hook_input=hook_input,
                    telemetry_path=Path(args.skip_telemetry_path) if args.skip_telemetry_path else None,
                    enabled=False if args.no_skip_telemetry else None,
                    hook_budget_ms=args.max_elapsed_ms,
                    semantic_timeout=args.semantic_timeout,
                    runtime_load_ms=runtime_load_ms,
                    hook_total_ms=round((time.perf_counter() - main_start) * 1000, 2),
                    telemetry_write_ms=round((time.perf_counter() - telemetry_start) * 1000, 2),
                )
        except Exception as exc:
            if args.strict:
                raise
            _append_detail_warning(result, code="skip_telemetry_write_failed", exc=exc)
        if not args.no_audit_status:
            try:
                if _has_final_diagnostic_budget(
                    started=main_start,
                    max_elapsed_ms=args.max_elapsed_ms,
                ):
                    write_prompt_hook_audit_status(
                        result,
                        status_path=Path(args.audit_status_path) if args.audit_status_path else None,
                    )
            except Exception as exc:
                if args.strict:
                    raise
                _append_detail_warning(result, code="audit_status_write_failed", exc=exc)
        if args.log or args.log_skip:
            write_debug_log(result, hook_input=hook_input, include_skip=args.log_skip)
        if args.json_output:
            _emit_json(runtime["public_hook_debug_payload"](result), indent=2)
            return 0
        payload = runtime["hook_stdout_payload"](result)
        if payload:
            _emit_json(payload)
        return 0
    except Exception as exc:
        if args.strict:
            raise
        if args.json_output:
            _emit_json(fallback_payload(exc), indent=2)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
