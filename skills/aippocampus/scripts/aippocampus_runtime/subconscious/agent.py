#!/usr/bin/env python3
"""Minimal tool-using subconscious agent for AIppocampus.

This layer lets a cheap model inspect clean memory before proposing concept
edges. It is intentionally small: tools are read-only, outputs are bounded, and
final edges still land only in staging for `build_concept_graph.py` to ingest.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    deepseek_cache_metrics_from_usage,
    sanitize_external_model_payload,
)
from aippocampus_runtime.navigation.concept_graph import default_concept_graph_path
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_REASONING_EFFORT,
    DEFAULT_DEEPSEEK_THINKING,
)
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.subconscious.edge_validation import (
    AGENT_EDGE_POLICY,
    validate_source_backed_edges,
)
from aippocampus_runtime.subconscious.runtime import (
    AGENT_SYSTEM_PROMPT,
    DEFAULT_MAX_STEPS,
    DEFAULT_MIN_TOOL_STEPS,
    DEFAULT_TEMPERATURE,
    TOOL_CONTRACT_VERSION,
    AgentState,
    ChatFn,
    available_tools_payload,
    call_chat_json,
    effective_step_budget,
    parse_action,
    read_only_tool_names,
    run_tool,
    source_bank_from_turns,
)
from aippocampus_runtime.subconscious.tool_loop import run_tool_using_loop
from aippocampus_runtime.subconscious.worker import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    append_staging_edges,
    default_project_timeline_path,
    default_staging_path,
    load_json,
    select_timeline_turns,
)

PROMPT_VERSION = "aippocampus-subconscious-agent-v0"


@dataclass(frozen=True)
class AgentRunConfig:
    registry_path: Path
    timeline_path: Path
    concept_graph_path: Path
    output_path: Path
    project: str | None
    objective: str
    max_turns: int
    max_steps: int
    min_tool_steps: int
    model: str
    base_url: str
    api_key: str | None
    max_tokens: int | None
    timeout: int
    temperature: float
    dry_run: bool = False
    no_write: bool = False


def agent_run_config_from_args(args: Any) -> AgentRunConfig:
    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    timeline_path = (
        Path(args.timeline).resolve()
        if args.timeline
        else default_project_timeline_path(registry_path=registry_path)
    )
    concept_graph_path = (
        Path(args.concept_graph).resolve()
        if args.concept_graph
        else default_concept_graph_path(registry_path=registry_path)
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else default_staging_path(registry_path=registry_path)
    )
    return AgentRunConfig(
        registry_path=registry_path,
        timeline_path=timeline_path,
        concept_graph_path=concept_graph_path,
        output_path=output_path,
        project=args.project,
        objective=args.objective,
        max_turns=args.max_turns,
        max_steps=args.max_steps,
        min_tool_steps=args.min_tool_steps,
        model=args.model,
        base_url=args.base_url,
        api_key=os.environ.get(args.api_key_env),
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        temperature=args.temperature,
        dry_run=args.dry_run,
        no_write=args.no_write,
    )


def validate_agent_edges(
    parsed: dict[str, Any], source_bank: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    def agent_source_ref(ref_id: str, source: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "ref": ref_id,
            "turn_ref": source.get("turn_ref"),
            "thread_key": source.get("thread_key"),
            "title": source.get("title"),
            "project_label": source.get("project_label"),
            "turn_id": source.get("turn_id"),
            "turn_index": source.get("turn_index"),
            "user_line": source.get("user_line"),
            "assistant_line": source.get("assistant_line"),
            "source_line": source.get("source_line"),
            "message_id": source.get("message_id"),
            "timestamp": source.get("timestamp"),
        }

    return validate_source_backed_edges(
        parsed,
        source_bank,
        policy=AGENT_EDGE_POLICY,
        project_source_ref=agent_source_ref,
    )


def _source_ref_id(ref_item: Any) -> str:
    if isinstance(ref_item, str):
        return ref_item.strip()
    if isinstance(ref_item, dict):
        return str(
            ref_item.get("ref") or ref_item.get("turn_ref") or ref_item.get("obs_ref") or ""
        ).strip()
    return ""


def _edge_ref_ids(edge: dict[str, Any]) -> set[str]:
    return {
        ref
        for ref in (_source_ref_id(item) for item in edge.get("source_refs") or [])
        if ref
    }


def _observation_refs_from_bank(source_bank: dict[str, dict[str, Any]]) -> list[str]:
    return [ref for ref in source_bank if ref.startswith("o")]


def _initial_refs_from_bank(source_bank: dict[str, dict[str, Any]]) -> list[str]:
    return [ref for ref in source_bank if not ref.startswith("o")]


def _feedback_refs(source_bank: dict[str, dict[str, Any]], *, limit: int) -> dict[str, list[str]]:
    refs = list(source_bank.keys())
    return {
        "available_refs": refs[:limit],
        "observation_refs": _observation_refs_from_bank(source_bank)[:limit],
        "initial_refs": _initial_refs_from_bank(source_bank)[:limit],
    }


def _collect_payload_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("ref")
        if isinstance(ref, str) and ref.startswith("o"):
            refs.add(ref)
        for item in value.values():
            refs.update(_collect_payload_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_payload_refs(item))
    return refs


def _useless_tool_reason(step: dict[str, Any]) -> str | None:
    action = step.get("action") or {}
    observation = step.get("observation") or {}
    tool = str(observation.get("tool") or action.get("tool") or "")
    if observation.get("error"):
        return "unknown_tool" if observation.get("error") == "unknown tool" else "tool_error"
    if _collect_payload_refs(observation):
        return None
    if tool == "search_clean_source" and not observation.get("hits"):
        return "empty_search"
    if tool == "get_turn_context" and not observation.get("messages"):
        return "empty_context"
    if tool == "recent_edges" and not observation.get("edges"):
        return "empty_recent_edges"
    if tool == "expand_concepts" and not observation.get("expansions"):
        return "empty_expansion"
    return None


def tool_grounding_diagnostics(
    *,
    edges: list[dict[str, Any]],
    source_bank: dict[str, dict[str, Any]],
    loop: Any,
    min_tool_steps: int,
) -> dict[str, Any]:
    observation_refs = set(_observation_refs_from_bank(source_bank))
    initial_refs = set(_initial_refs_from_bank(source_bank))
    final_edges_with_observation_refs = 0
    final_edges_with_initial_refs = 0
    final_observation_refs: set[str] = set()
    for edge in edges:
        refs = _edge_ref_ids(edge)
        obs_refs = refs & observation_refs
        if obs_refs:
            final_edges_with_observation_refs += 1
            final_observation_refs.update(obs_refs)
        if refs & initial_refs:
            final_edges_with_initial_refs += 1

    # This is deliberately diagnostic by default. A valid initial-turn ref should
    # not be rejected merely because a required tool step returned no useful refs.
    if final_edges_with_observation_refs:
        status = "tool_grounded"
    elif loop.tool_count > 0 and edges:
        status = "initial_only_after_tool"
    else:
        status = "ungrounded"

    useless_tool_calls = []
    for step in loop.tool_steps:
        reason = _useless_tool_reason(step)
        if reason:
            action = step.get("action") or {}
            observation = step.get("observation") or {}
            useless_tool_calls.append(
                {
                    "step": step.get("step"),
                    "tool": str(observation.get("tool") or action.get("tool") or ""),
                    "reason": reason,
                }
            )

    return {
        "status": status,
        "min_tool_steps": max(0, int(min_tool_steps)),
        "tool_call_count": loop.tool_count,
        "tool_observation_ref_count": len(observation_refs),
        "final_edge_count": len(edges),
        "final_edges_with_observation_refs": final_edges_with_observation_refs,
        "final_edges_with_initial_refs": final_edges_with_initial_refs,
        "final_observation_refs": sorted(final_observation_refs),
        "useless_tool_call_count": len(useless_tool_calls),
        "useless_tool_calls": useless_tool_calls,
        "policy": (
            "diagnostic_by_default; observation refs should be cited when they "
            "support a finding, but initial refs remain valid when tools added no useful source refs"
        ),
    }


def agent_initial_payload(
    objective: str, turns: list[dict[str, Any]], max_steps: int, min_tool_steps: int
) -> str:
    # Keep static tool/budget contract before source turns, then put the
    # run-specific objective last. That gives broad runs a reusable prefix while
    # still letting repeated samples over the same source reuse the source block.
    payload = {
        "prompt_version": PROMPT_VERSION,
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "available_tools": available_tools_payload(),
        "tool_budget": max_steps,
        "minimum_tool_steps_before_final": min_tool_steps,
        "initial_turns": turns,
        "objective": objective
        or "Propose source-backed concept edges for AIppocampus ambient recall.",
    }
    payload = sanitize_external_model_payload(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run_agent(
    *,
    registry_path: Path,
    timeline_path: Path,
    concept_graph_path: Path,
    output_path: Path,
    project: str | None,
    objective: str,
    max_turns: int,
    max_steps: int,
    min_tool_steps: int,
    model: str,
    base_url: str,
    api_key: str | None,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    chat_fn: ChatFn = call_chat_json,
    dry_run: bool = False,
    no_write: bool = False,
) -> dict[str, Any]:
    timeline = load_json(timeline_path)
    turns = select_timeline_turns(timeline, project=project, max_turns=max_turns)
    state = AgentState(source_bank=source_bank_from_turns(turns))
    batch_id = f"subconscious-agent-{int(time.time())}"
    step_budget = effective_step_budget(max_steps)
    initial_payload = agent_initial_payload(objective, turns, step_budget, min_tool_steps)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "timeline": str(timeline_path),
            "turn_count": len(turns),
            "max_steps": max_steps,
            "effective_step_budget": step_budget,
            "temperature": temperature,
            "tool_contract_version": TOOL_CONTRACT_VERSION,
            "prompt_preview": compact_text(initial_payload, 2400),
        }
    if not api_key:
        raise RuntimeError("missing DeepSeek API key; set DEEPSEEK_API_KEY or pass --api-key-env")

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": initial_payload},
    ]

    def invalid_final_feedback() -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": (
                "No valid source-backed edges survived validation. Use source_refs from "
                "available refs, or return an empty final only if no durable relation exists."
            ),
            "instruction": (
                "If observations mention concrete decisions, libraries, workflows, aliases, "
                "or contrasts, propose at least one edge with source_refs."
            ),
            "grounding_instruction": (
                "Cite observation_refs when they support the finding; keep initial refs when "
                "tools added no useful source refs. Do not cite o* refs merely to satisfy metrics."
            ),
        }
        payload.update(_feedback_refs(state.source_bank, limit=24))
        return payload

    def repair_feedback() -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repair": "final_only",
            "instruction": (
                "Use the existing tool observations and available refs to produce "
                "source-backed edges. Do not call tools. Return action=final."
            ),
            "grounding_instruction": (
                "Prefer observation_refs for findings supported by tool hits; use initial_refs "
                "only when they are the real source support."
            ),
        }
        payload.update(_feedback_refs(state.source_bank, limit=32))
        return payload

    loop = run_tool_using_loop(
        messages=messages,
        step_budget=step_budget,
        min_tool_steps=min_tool_steps,
        chat_fn=chat_fn,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        parse_response=parse_action,
        validate_final=lambda action: validate_agent_edges(action, state.source_bank),
        run_tool_action=lambda tool_name, tool_args: run_tool(
            tool_name,
            tool_args,
            registry_path=registry_path,
            project=project,
            concept_graph_path=concept_graph_path,
            staging_path=output_path,
            state=state,
        ),
        min_tool_feedback=lambda: {
            "error": "Call at least one read-only tool before finalizing.",
            "allowed_tools": list(read_only_tool_names()),
        },
        invalid_final_feedback=invalid_final_feedback,
        repair_feedback=repair_feedback,
        tool_result_instruction=(
            "Next: call another tool if needed; otherwise return action=final with source-backed edges. "
            "Do not return an empty final when the observations contain concrete decisions, libraries, workflows, aliases, or contrasts."
        ),
        chat_kwargs={
            "thinking": DEFAULT_DEEPSEEK_THINKING,
            "reasoning_effort": DEFAULT_DEEPSEEK_REASONING_EFFORT,
        }
        if chat_fn is call_chat_json
        else None,
    )
    edges = loop.final_items
    grounding = tool_grounding_diagnostics(
        edges=edges,
        source_bank=state.source_bank,
        loop=loop,
        min_tool_steps=min_tool_steps,
    )
    if not no_write:
        append_staging_edges(
            output_path,
            edges,
            model=model,
            batch_id=batch_id,
            usage=loop.usage_total,
            prompt_version=PROMPT_VERSION,
            source="deepseek_subconscious_agent",
        )
    return {
        "ok": True,
        "dry_run": False,
        "model": model,
        "timeline": str(timeline_path),
        "concept_graph": str(concept_graph_path),
        "output": str(output_path),
        "turn_count": len(turns),
        "edge_count": len(edges),
        "edges": edges,
        "tool_grounding": grounding,
        "tool_steps": loop.tool_steps,
        "final_attempts": loop.final_attempts,
        "min_tool_steps": min_tool_steps,
        "max_steps": max_steps,
        "effective_step_budget": step_budget,
        "temperature": temperature,
        "thinking": DEFAULT_DEEPSEEK_THINKING,
        "reasoning_effort": DEFAULT_DEEPSEEK_REASONING_EFFORT,
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "usage": loop.usage_total,
        "cache": deepseek_cache_metrics_from_usage(loop.usage_total),
        "wrote": False if no_write else True,
        "batch_id": batch_id,
    }


def run_agent_with_config(
    config: AgentRunConfig, *, chat_fn: ChatFn = call_chat_json
) -> dict[str, Any]:
    return run_agent(
        registry_path=config.registry_path,
        timeline_path=config.timeline_path,
        concept_graph_path=config.concept_graph_path,
        output_path=config.output_path,
        project=config.project,
        objective=config.objective,
        max_turns=config.max_turns,
        max_steps=config.max_steps,
        min_tool_steps=config.min_tool_steps,
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key,
        max_tokens=config.max_tokens,
        timeout=config.timeout,
        temperature=config.temperature,
        chat_fn=chat_fn,
        dry_run=config.dry_run,
        no_write=config.no_write,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--timeline")
    parser.add_argument("--concept-graph")
    parser.add_argument("--output")
    parser.add_argument("--project")
    parser.add_argument(
        "--objective", default="Propose source-backed concept edges for AIppocampus ambient recall."
    )
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=DEFAULT_MAX_STEPS,
        help="Agent step budget. Use 0 for the hard safety cap.",
    )
    parser.add_argument("--min-tool-steps", type=int, default=DEFAULT_MIN_TOOL_STEPS)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        result = run_agent_with_config(agent_run_config_from_args(args))
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result.get("dry_run"):
            print(f"dry run: {result['turn_count']} turn(s)")
            print(result["prompt_preview"])
        else:
            print(f"subconscious agent edges: {result['edge_count']}")
            print(f"tool steps: {len(result.get('tool_steps') or [])}")
            print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
