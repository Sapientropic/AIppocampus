#!/usr/bin/env python3
"""Shared read-only runtime primitives for subconscious agent and jobs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    ChatClientConfig,
    chat_json,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.source.search import iter_clean_messages, score_message
from aippocampuslib import compact_text
from build_concept_graph import expand_concepts
from registry import load_registry

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

ChatFn = Callable[..., dict[str, Any]]


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
    return {
        key: value for key, value in usage.items() if isinstance(value, (int, float, str, dict))
    }


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
    timeout: float,
    temperature: float,
    *,
    user_id: str | None = None,
    thinking: str | None = None,
    service_name: str = "DeepSeek API",
    response_format_json: bool = True,
    cache_contract: str | None = DEEPSEEK_PREFIX_CACHE_CONTRACT,
) -> dict[str, Any]:
    return chat_json(
        messages,
        ChatClientConfig(
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature,
            service_name=service_name,
            user_id=user_id,
            thinking=thinking,
            response_format_json=response_format_json,
            cache_contract=cache_contract,
        ),
    )


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
            "scope_labels": [
                str(label) for label in turn.get("scope_labels") or [] if str(label).strip()
            ][:12],
            "semantic_scope_labels": [
                str(label)
                for label in turn.get("semantic_scope_labels") or []
                if str(label).strip()
            ][:12],
            "source_refs": [ref for ref in turn.get("source_refs") or [] if isinstance(ref, dict)][
                :8
            ],
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
    return [
        entry
        for entry in registry.get("threads") or []
        if isinstance(entry, dict) and project_matches(entry, project)
    ]


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
    hits.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("updated_at") or ""),
            int(item[2].get("source_line") or 0),
        )
    )
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
    entry = next(
        (
            item
            for item in registry_entries(registry_path, project)
            if item.get("thread_key") == thread_key
        ),
        None,
    )
    if not entry:
        return {"tool": "get_turn_context", "error": "thread not found"}
    messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
    if not messages_path_value:
        return {"tool": "get_turn_context", "error": "clean source missing"}
    messages = []
    for message in iter_clean_messages(Path(messages_path_value)):
        same_turn_id = bool(turn_id and str(message.get("turn_id") or "") == turn_id)
        same_turn_index = turn_index is not None and str(message.get("turn_index") or "") == str(
            turn_index
        )
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
    return {
        "tool": "get_turn_context",
        "thread_key": thread_key,
        "turn_id": turn_id or None,
        "turn_index": turn_index,
        "messages": out,
    }


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
                blob = " ".join(
                    [
                        str(item.get("src") or ""),
                        str(item.get("dst") or ""),
                        str(item.get("why") or ""),
                    ]
                ).casefold()
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
            return tool_search_clean_source(
                registry_path=registry_path, project=project, args=args, state=state
            )
        if name == "get_turn_context":
            return tool_get_turn_context(
                registry_path=registry_path, project=project, args=args, state=state
            )
        if name == "expand_concepts":
            return tool_expand_concepts(concept_graph_path=concept_graph_path, args=args)
        if name == "recent_edges":
            return tool_recent_edges(staging_path=staging_path, args=args)
        return {"tool": name, "error": "unknown tool"}
    except Exception as exc:
        return {"tool": name, "error": f"{type(exc).__name__}: {exc}"}
