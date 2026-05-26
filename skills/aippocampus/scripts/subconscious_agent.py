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
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aippocampuslib import compact_text, now_utc
from build_concept_graph import concept_is_noise, default_concept_graph_path, expand_concepts
from registry import load_registry, registry_paths, unique_preserve
from retrieval import split_query_terms
from search_clean_source import iter_clean_messages, score_message
from subconscious_worker import (
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
DEFAULT_MAX_STEPS = 16
HARD_MAX_STEPS = 64
DEFAULT_MIN_TOOL_STEPS = 1
DEFAULT_TEMPERATURE = 0.2

AGENT_SYSTEM_PROMPT = """You are AIppocampus subconscious agent.
Your job is to propose source-backed concept edges for long-term recall.
You may inspect clean memory through read-only tools before finalizing.
Never invent facts. Never include secrets, full local paths, API keys, or long quotes.

Return only JSON with one of these shapes:

Tool request:
{
  "action": "tool",
  "tool": "search_clean_source|get_turn_context|expand_concepts|recent_edges",
  "args": {},
  "why": "short reason"
}

Final answer:
{
  "action": "final",
  "edges": [
    {
      "src": "...",
      "dst": "...",
      "edge_type": "alias|same_decision_space|project_topic|decision_about|depends_on|contrasts_with|supersedes|related",
      "confidence": 0.0,
      "why": "short reason",
      "source_refs": [{"ref": "t0"}]
    }
  ]
}

Source rules:
- Use refs from the initial turns (`t0`, `t1`, ...) or tool observations (`o0`, `o1`, ...).
- Every final edge needs at least one source ref.
- Prefer durable concepts, project decisions, libraries, workflows, contrasts, and aliases.
- Avoid generic edges such as "project -> implementation" unless a concrete concept is present.
- If tool observations contain concrete decisions, libraries, workflows, or contrasts, do not return an empty final.
"""


ChatFn = Callable[[list[dict[str, str]], str, str, str, int | None, int, float], dict[str, Any]]


@dataclass
class AgentState:
    source_bank: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_observation_id: int = 0

    def add_observation(self, payload: dict[str, Any]) -> str:
        ref = f"o{self.next_observation_id}"
        self.next_observation_id += 1
        self.source_bank[ref] = {"ref": ref, **payload}
        return ref


def compact_usage(usage: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in usage.items() if isinstance(value, (int, float, str, dict))}


def add_usage(total: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    for key, value in usage.items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value
        elif isinstance(value, dict):
            nested = total.setdefault(key, {})
            if isinstance(nested, dict):
                add_usage(nested, value)
    return total


def call_chat_json(
    messages: list[dict[str, str]],
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc
    return json.loads(response_body)


def effective_step_budget(max_steps: int) -> int:
    if int(max_steps) <= 0:
        return HARD_MAX_STEPS
    return max(1, min(HARD_MAX_STEPS, int(max_steps)))


def parse_action(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("model response has no choices")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        finish_reason = choices[0].get("finish_reason")
        usage = response.get("usage") or {}
        raise ValueError(
            "model response content is empty; "
            f"finish_reason={finish_reason!r}, completion_tokens={usage.get('completion_tokens')!r}. "
            "If --max-tokens was passed, remove or increase it."
        )
    parsed = json.loads(content)
    return parsed if isinstance(parsed, dict) else {}


def source_bank_from_turns(turns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bank: dict[str, dict[str, Any]] = {}
    for turn in turns:
        ref = str(turn.get("turn_ref") or "")
        if not ref:
            continue
        bank[ref] = {
            "ref": ref,
            "turn_ref": ref,
            "thread_key": turn.get("thread_key"),
            "title": turn.get("title"),
            "project_label": turn.get("project_label"),
            "turn_id": turn.get("turn_id"),
            "turn_index": turn.get("turn_index"),
            "user_line": turn.get("user_line"),
            "assistant_line": turn.get("assistant_line"),
            "timestamp": turn.get("timestamp"),
        }
    return bank


def project_matches(entry: dict[str, Any], project: str | None) -> bool:
    if not project:
        return True
    needle = project.casefold().strip()
    blob = " ".join(
        [
            str(entry.get("project_label") or ""),
            str(entry.get("workspace_name") or ""),
            str(entry.get("title") or ""),
            " ".join(str(item) for item in entry.get("project_tags") or []),
        ]
    ).casefold()
    return needle in blob


def registry_entries(registry_path: Path, project: str | None = None) -> list[dict[str, Any]]:
    registry = load_registry(registry_path)
    return [entry for entry in registry.get("threads") or [] if isinstance(entry, dict) and project_matches(entry, project)]


def normalize_tool_terms(args: dict[str, Any]) -> list[str]:
    terms_value = args.get("terms") or args.get("query") or []
    if isinstance(terms_value, str):
        raw_terms = [terms_value]
    elif isinstance(terms_value, list):
        raw_terms = [str(item) for item in terms_value]
    else:
        raw_terms = []
    return split_query_terms(raw_terms)[:12]


def tool_search_clean_source(
    *,
    registry_path: Path,
    project: str | None,
    args: dict[str, Any],
    state: AgentState,
) -> dict[str, Any]:
    terms = normalize_tool_terms(args)
    limit = max(1, min(12, int(args.get("limit") or 6)))
    hits: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for entry in registry_entries(registry_path, project):
        paths = entry.get("paths") or {}
        messages_path_value = paths.get("clean_source_messages_jsonl")
        if not messages_path_value:
            continue
        messages_path = Path(messages_path_value)
        for message in iter_clean_messages(messages_path):
            score = score_message(message, terms)
            if score <= 0:
                continue
            hits.append((score, entry, message))
    hits.sort(key=lambda item: (-item[0], str(item[1].get("updated_at") or ""), int(item[2].get("source_line") or 0)))
    out = []
    for score, entry, message in hits[:limit]:
        ref = state.add_observation(
            {
                "thread_key": entry.get("thread_key"),
                "title": entry.get("title"),
                "project_label": entry.get("project_label"),
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "turn_index": message.get("turn_index"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "is_final": bool(message.get("is_final")),
                "source_line": message.get("source_line"),
                "timestamp": message.get("timestamp"),
            }
        )
        out.append(
            {
                "ref": ref,
                "thread_key": entry.get("thread_key"),
                "title": entry.get("title"),
                "line": message.get("source_line"),
                "turn_index": message.get("turn_index"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "score": round(score, 3),
                "snippet": compact_text(str(message.get("text") or ""), 420),
            }
        )
    return {"tool": "search_clean_source", "query_terms": terms, "hits": out}


def tool_get_turn_context(
    *,
    registry_path: Path,
    project: str | None,
    args: dict[str, Any],
    state: AgentState,
) -> dict[str, Any]:
    source = None
    source_ref = str(args.get("ref") or args.get("turn_ref") or "").strip()
    if source_ref:
        source = state.source_bank.get(source_ref)
    thread_key = str(args.get("thread_key") or (source or {}).get("thread_key") or "")
    turn_id = str(args.get("turn_id") or (source or {}).get("turn_id") or "")
    turn_index = args.get("turn_index", (source or {}).get("turn_index"))
    limit = max(1, min(10, int(args.get("limit") or 6)))
    if not thread_key:
        return {"tool": "get_turn_context", "error": "missing thread_key/ref"}
    entry = next((item for item in registry_entries(registry_path, project) if item.get("thread_key") == thread_key), None)
    if not entry:
        return {"tool": "get_turn_context", "error": "thread not found"}
    messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
    if not messages_path_value:
        return {"tool": "get_turn_context", "error": "clean source missing"}
    messages = []
    for message in iter_clean_messages(Path(messages_path_value)):
        same_turn_id = bool(turn_id and str(message.get("turn_id") or "") == turn_id)
        same_turn_index = turn_index is not None and str(message.get("turn_index") or "") == str(turn_index)
        if not same_turn_id and not same_turn_index:
            continue
        messages.append(message)
    messages.sort(key=lambda item: int(item.get("source_line") or item.get("clean_ordinal") or 0))
    out = []
    for message in messages[:limit]:
        ref = state.add_observation(
            {
                "thread_key": entry.get("thread_key"),
                "title": entry.get("title"),
                "project_label": entry.get("project_label"),
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "turn_index": message.get("turn_index"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "is_final": bool(message.get("is_final")),
                "source_line": message.get("source_line"),
                "timestamp": message.get("timestamp"),
            }
        )
        out.append(
            {
                "ref": ref,
                "line": message.get("source_line"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "turn_index": message.get("turn_index"),
                "snippet": compact_text(str(message.get("text") or ""), 520),
            }
        )
    return {"tool": "get_turn_context", "thread_key": thread_key, "turn_id": turn_id or None, "turn_index": turn_index, "messages": out}


def tool_expand_concepts(*, concept_graph_path: Path, args: dict[str, Any]) -> dict[str, Any]:
    terms = normalize_tool_terms(args)
    depth = max(1, min(2, int(args.get("depth") or 2)))
    limit = max(1, min(24, int(args.get("limit") or 12)))
    rows = expand_concepts(concept_graph_path, terms, depth=depth, max_terms=limit)
    return {"tool": "expand_concepts", "query_terms": terms, "expansions": rows}


def tool_recent_edges(*, staging_path: Path, args: dict[str, Any]) -> dict[str, Any]:
    terms = [term.casefold() for term in normalize_tool_terms(args)]
    limit = max(1, min(20, int(args.get("limit") or 8)))
    rows = []
    if staging_path.exists():
        with staging_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                blob = " ".join([str(item.get("src") or ""), str(item.get("dst") or ""), str(item.get("why") or "")]).casefold()
                if terms and not any(term in blob for term in terms):
                    continue
                rows.append(
                    {
                        "src": item.get("src"),
                        "dst": item.get("dst"),
                        "edge_type": item.get("edge_type"),
                        "confidence": item.get("confidence"),
                        "source": item.get("source"),
                        "why": compact_text(str(item.get("why") or ""), 180),
                    }
                )
    return {"tool": "recent_edges", "query_terms": terms, "edges": rows[-limit:]}


def run_tool(
    name: str,
    args: dict[str, Any],
    *,
    registry_path: Path,
    project: str | None,
    concept_graph_path: Path,
    staging_path: Path,
    state: AgentState,
) -> dict[str, Any]:
    try:
        if name == "search_clean_source":
            return tool_search_clean_source(registry_path=registry_path, project=project, args=args, state=state)
        if name == "get_turn_context":
            return tool_get_turn_context(registry_path=registry_path, project=project, args=args, state=state)
        if name == "expand_concepts":
            return tool_expand_concepts(concept_graph_path=concept_graph_path, args=args)
        if name == "recent_edges":
            return tool_recent_edges(staging_path=staging_path, args=args)
        return {"tool": name, "error": "unknown tool"}
    except Exception as exc:
        return {"tool": name, "error": f"{type(exc).__name__}: {exc}"}


def validate_agent_edges(parsed: dict[str, Any], source_bank: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
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
                ref_id = str(ref_item.get("ref") or ref_item.get("turn_ref") or ref_item.get("obs_ref") or "").strip()
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


def agent_initial_payload(objective: str, turns: list[dict[str, Any]], max_steps: int, min_tool_steps: int) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "objective": objective or "Propose source-backed concept edges for AIppocampus ambient recall.",
        "tool_budget": max_steps,
        "minimum_tool_steps_before_final": min_tool_steps,
        "initial_turns": turns,
        "available_tools": {
            "search_clean_source": {"args": {"terms": ["..."], "limit": 6}},
            "get_turn_context": {"args": {"ref": "t0", "limit": 6}},
            "expand_concepts": {"args": {"terms": ["..."], "depth": 2, "limit": 12}},
            "recent_edges": {"args": {"terms": ["..."], "limit": 8}},
        },
    }
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
            "prompt_preview": compact_text(initial_payload, 2400),
        }
    if not api_key:
        raise RuntimeError("missing DeepSeek API key; set DEEPSEEK_API_KEY or pass --api-key-env")

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": initial_payload},
    ]
    transcript = []
    final_attempts = []
    usage_total: dict[str, Any] = {}
    final_action: dict[str, Any] | None = None
    final_edges: list[dict[str, Any]] | None = None
    tool_count = 0
    for step in range(step_budget):
        response = chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature)
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        action = parse_action(response)
        transcript.append({"step": step + 1, "action": action})
        if action.get("action") == "final":
            final_attempts.append(action)
            if tool_count < max(0, int(min_tool_steps)) and step + 1 < step_budget:
                messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "error": "Call at least one read-only tool before finalizing.",
                                "allowed_tools": ["search_clean_source", "get_turn_context", "expand_concepts", "recent_edges"],
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                continue
            candidate_edges = validate_agent_edges(action, state.source_bank)
            if not candidate_edges and step + 1 < step_budget:
                messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "error": "No valid source-backed edges survived validation. Use source_refs from available refs, or return an empty final only if no durable relation exists.",
                                "instruction": "If observations mention concrete decisions, libraries, workflows, aliases, or contrasts, propose at least one edge with source_refs.",
                                "available_refs": list(state.source_bank.keys())[:24],
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                continue
            final_action = action
            final_edges = candidate_edges
            break
        if action.get("action") != "tool":
            messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
            messages.append({"role": "user", "content": json.dumps({"error": "Return action=tool or action=final only."}, ensure_ascii=False)})
            continue
        tool_name = str(action.get("tool") or "")
        tool_args = action.get("args") if isinstance(action.get("args"), dict) else {}
        observation = run_tool(
            tool_name,
            tool_args,
            registry_path=registry_path,
            project=project,
            concept_graph_path=concept_graph_path,
            staging_path=output_path,
            state=state,
        )
        tool_count += 1
        transcript[-1]["observation"] = observation
        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": (
                    "TOOL_RESULT:" + "\n"
                    + json.dumps(observation, ensure_ascii=False, indent=2)
                    + "\n\nNext: call another tool if needed; otherwise return action=final with source-backed edges. "
                    "Do not return an empty final when the observations contain concrete decisions, libraries, workflows, aliases, or contrasts."
                ),
            }
        )

    if final_action is None:
        final_action = {"edges": []}
    edges = final_edges if final_edges is not None else validate_agent_edges(final_action, state.source_bank)
    if not edges and tool_count > 0:
        repair_messages = messages + [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "repair": "final_only",
                        "instruction": "Use the existing tool observations and available refs to produce source-backed edges. Do not call tools. Return action=final.",
                        "available_refs": list(state.source_bank.keys())[:32],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
        response = chat_fn(repair_messages, api_key, model, base_url, max_tokens, timeout, temperature)
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        repair_action = parse_action(response)
        final_attempts.append(repair_action)
        if repair_action.get("action") == "final":
            repair_edges = validate_agent_edges(repair_action, state.source_bank)
            if repair_edges:
                final_action = repair_action
                edges = repair_edges
    if not no_write:
        append_staging_edges(
            output_path,
            edges,
            model=model,
            batch_id=batch_id,
            usage=usage_total,
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
        "tool_steps": [item for item in transcript if (item.get("action") or {}).get("action") == "tool"],
        "final_attempts": final_attempts,
        "min_tool_steps": min_tool_steps,
        "max_steps": max_steps,
        "effective_step_budget": step_budget,
        "temperature": temperature,
        "usage": usage_total,
        "wrote": False if no_write else True,
        "batch_id": batch_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--timeline")
    parser.add_argument("--concept-graph")
    parser.add_argument("--output")
    parser.add_argument("--project")
    parser.add_argument("--objective", default="Propose source-backed concept edges for AIppocampus ambient recall.")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="Agent step budget. Use 0 for the hard safety cap.")
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

    registry_path = Path(args.registry).resolve() if args.registry else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    timeline_path = Path(args.timeline).resolve() if args.timeline else default_project_timeline_path(registry_path=registry_path)
    concept_graph_path = Path(args.concept_graph).resolve() if args.concept_graph else default_concept_graph_path(registry_path=registry_path)
    output_path = Path(args.output).resolve() if args.output else default_staging_path(registry_path=registry_path)
    result = run_agent(
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
