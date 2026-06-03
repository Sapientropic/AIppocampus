#!/usr/bin/env python3
"""Shared read-only runtime primitives for subconscious agent and jobs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    ChatClientConfig,
    chat_json,
)
from aippocampus_runtime.navigation.concept_graph import expand_concepts
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import load_registry
from aippocampus_runtime.source.search import iter_clean_messages, score_message

DEFAULT_MAX_STEPS = 16
HARD_MAX_STEPS = 64
DEFAULT_MIN_TOOL_STEPS = 1
DEFAULT_TEMPERATURE = 0.2
TOOL_CONTRACT_VERSION = "aippocampus-subconscious-read-only-tools-v1"

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


@dataclass(frozen=True)
class ToolRuntimeContext:
    registry_path: Path
    project: str | None
    concept_graph_path: Path
    staging_path: Path
    state: AgentState


ToolDispatcher = Callable[[ToolRuntimeContext, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ReadOnlyToolSpec:
    name: str
    args: dict[str, Any]
    purpose: str
    prompt_description: str
    dispatcher: ToolDispatcher
    safety_class: str = "read_only"
    limits: dict[str, int] = field(default_factory=dict)


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


def _dispatch_search_clean_source(
    context: ToolRuntimeContext, args: dict[str, Any]
) -> dict[str, Any]:
    return tool_search_clean_source(
        registry_path=context.registry_path,
        project=context.project,
        args=args,
        state=context.state,
    )


def _dispatch_get_turn_context(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    return tool_get_turn_context(
        registry_path=context.registry_path,
        project=context.project,
        args=args,
        state=context.state,
    )


def _dispatch_expand_concepts(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    return tool_expand_concepts(concept_graph_path=context.concept_graph_path, args=args)


def _dispatch_recent_edges(context: ToolRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    return tool_recent_edges(staging_path=context.staging_path, args=args)


# The model-facing contract, initial payload, and dispatcher all read this
# registry. Keep it static and read-only so future tool additions do not drift
# into dynamic discovery or accidentally widen the subconscious authority.
READ_ONLY_TOOL_REGISTRY: dict[str, ReadOnlyToolSpec] = {
    "search_clean_source": ReadOnlyToolSpec(
        name="search_clean_source",
        args={"terms": ["..."], "limit": 6},
        purpose="Search registered clean-source messages for source-backed memory hits.",
        prompt_description="search clean-source messages by terms; limit is clamped to 12.",
        dispatcher=_dispatch_search_clean_source,
        limits={"terms": 12, "limit": 12},
    ),
    "get_turn_context": ReadOnlyToolSpec(
        name="get_turn_context",
        args={"ref": "t0", "limit": 6},
        purpose="Inspect clean messages around an initial or observed turn reference.",
        prompt_description="reopen one source turn by ref/thread id; limit is clamped to 10.",
        dispatcher=_dispatch_get_turn_context,
        limits={"limit": 10},
    ),
    "expand_concepts": ReadOnlyToolSpec(
        name="expand_concepts",
        args={"terms": ["..."], "depth": 2, "limit": 12},
        purpose="Inspect nearby concepts in the concept graph.",
        prompt_description="expand concept graph terms; depth is clamped to 2 and limit to 24.",
        dispatcher=_dispatch_expand_concepts,
        limits={"terms": 12, "depth": 2, "limit": 24},
    ),
    "recent_edges": ReadOnlyToolSpec(
        name="recent_edges",
        args={"terms": ["..."], "limit": 8},
        purpose="Inspect recent staging concept edges.",
        prompt_description="search recent staging edges; limit is clamped to 20.",
        dispatcher=_dispatch_recent_edges,
        limits={"terms": 12, "limit": 20},
    ),
}


def read_only_tool_names() -> tuple[str, ...]:
    return tuple(READ_ONLY_TOOL_REGISTRY)


def dispatchable_tool_names() -> tuple[str, ...]:
    return tuple(name for name, spec in READ_ONLY_TOOL_REGISTRY.items() if spec.dispatcher)


def available_tools_payload() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "args": spec.args,
            "purpose": spec.purpose,
            "safety_class": spec.safety_class,
            "limits": spec.limits,
        }
        for name, spec in READ_ONLY_TOOL_REGISTRY.items()
    }


def build_agent_system_prompt() -> str:
    tool_union = "|".join(read_only_tool_names())
    tool_descriptions = "\n".join(
        f"- {name}: {spec.prompt_description}"
        for name, spec in READ_ONLY_TOOL_REGISTRY.items()
    )
    return f"""You are AIppocampus subconscious agent.
Your job is to propose source-backed concept edges for long-term recall.
You may inspect clean memory through read-only tools before finalizing.
Never invent facts. Never include secrets, full local paths, API keys, or long quotes.

Tool contract version: {TOOL_CONTRACT_VERSION}

Available read-only tools:
{tool_descriptions}

Return only JSON with one of these shapes:

Tool request:
{{
  "action": "tool",
  "tool": "{tool_union}",
  "args": {{}},
  "why": "short reason"
}}

Final answer:
{{
  "action": "final",
  "edges": [
    {{
      "src": "...",
      "dst": "...",
      "edge_type": "alias|same_decision_space|project_topic|decision_about|depends_on|contrasts_with|supersedes|related",
      "confidence": 0.0,
      "why": "short reason",
      "source_refs": [{{"ref": "t0"}}]
    }}
  ]
}}

Source rules:
- Use refs from the initial turns (`t0`, `t1`, ...) or tool observations (`o0`, `o1`, ...).
- Every final edge needs at least one source ref.
- Prefer durable concepts, project decisions, libraries, workflows, contrasts, and aliases.
- Avoid generic edges such as "project -> implementation" unless a concrete concept is present.
- If tool observations contain concrete decisions, libraries, workflows, or contrasts, do not return an empty final.
"""


AGENT_SYSTEM_PROMPT = build_agent_system_prompt()


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
    context = ToolRuntimeContext(
        registry_path=registry_path,
        project=project,
        concept_graph_path=concept_graph_path,
        staging_path=staging_path,
        state=state,
    )
    try:
        spec = READ_ONLY_TOOL_REGISTRY.get(name)
        if not spec:
            return {"tool": name, "error": "unknown tool"}
        return spec.dispatcher(context, args)
    except Exception as exc:
        return {"tool": name, "error": f"{type(exc).__name__}: {exc}"}
