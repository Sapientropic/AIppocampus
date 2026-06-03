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
from typing import Any

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    deepseek_cache_metrics_from_usage,
    sanitize_external_model_payload,
)
from aippocampus_runtime.navigation.concept_graph import (
    concept_is_noise,
    default_concept_graph_path,
)
from aippocampus_runtime.registry.api import registry_paths
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
    ALLOWED_EDGE_TYPES,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    append_staging_edges,
    clamp_confidence,
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
    out: list[dict[str, Any]] = []
    for edge in parsed.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("src") or "").strip()
        dst = str(edge.get("dst") or "").strip()
        edge_type = str(edge.get("edge_type") or "related").strip()
        confidence = clamp_confidence(edge.get("confidence"))
        if edge_type not in ALLOWED_EDGE_TYPES:
            edge_type = "related"
        if not src or not dst or src.casefold() == dst.casefold():
            continue
        if concept_is_noise(src) or concept_is_noise(dst):
            continue
        refs: list[dict[str, Any]] = []
        for ref_item in edge.get("source_refs") or []:
            if isinstance(ref_item, str):
                ref_id = ref_item.strip()
            elif isinstance(ref_item, dict):
                ref_id = str(
                    ref_item.get("ref") or ref_item.get("turn_ref") or ref_item.get("obs_ref") or ""
                ).strip()
            else:
                continue
            source = source_bank.get(ref_id)
            if not source:
                continue
            refs.append(
                {
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
            )
        if not refs or confidence < 0.45:
            continue
        out.append(
            {
                "src": src,
                "dst": dst,
                "edge_type": edge_type,
                "confidence": round(confidence, 4),
                "why": compact_text(str(edge.get("why") or ""), 220),
                "source_refs": refs[:4],
            }
        )
    return out


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
        invalid_final_feedback=lambda: {
            "error": "No valid source-backed edges survived validation. Use source_refs from available refs, or return an empty final only if no durable relation exists.",
            "instruction": "If observations mention concrete decisions, libraries, workflows, aliases, or contrasts, propose at least one edge with source_refs.",
            "available_refs": list(state.source_bank.keys())[:24],
        },
        repair_feedback=lambda: {
            "repair": "final_only",
            "instruction": "Use the existing tool observations and available refs to produce source-backed edges. Do not call tools. Return action=final.",
            "available_refs": list(state.source_bank.keys())[:32],
        },
        tool_result_instruction=(
            "Next: call another tool if needed; otherwise return action=final with source-backed edges. "
            "Do not return an empty final when the observations contain concrete decisions, libraries, workflows, aliases, or contrasts."
        ),
    )
    edges = loop.final_items
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
        "tool_steps": loop.tool_steps,
        "final_attempts": loop.final_attempts,
        "min_tool_steps": min_tool_steps,
        "max_steps": max_steps,
        "effective_step_budget": step_budget,
        "temperature": temperature,
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
