#!/usr/bin/env python3
"""Generic tool-using conversation loop for subconscious model passes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from aippocampus_runtime.subconscious.runtime import ChatFn, add_usage, compact_usage
from aippocampuslib import sanitize_external_model_payload


@dataclass
class ToolLoopResult:
    transcript: list[dict[str, Any]]
    final_attempts: list[dict[str, Any]]
    final_action: dict[str, Any]
    final_items: list[dict[str, Any]]
    usage_total: dict[str, Any]
    tool_count: int

    @property
    def tool_steps(self) -> list[dict[str, Any]]:
        return [
            item for item in self.transcript if (item.get("action") or {}).get("action") == "tool"
        ]


FeedbackFn = Callable[[], dict[str, Any]]
ParseResponseFn = Callable[[dict[str, Any]], dict[str, Any]]
RunToolActionFn = Callable[[str, dict[str, Any]], dict[str, Any]]
ValidateFinalFn = Callable[[dict[str, Any]], list[dict[str, Any]]]


def _assistant_message(action: dict[str, Any]) -> dict[str, str]:
    return {"role": "assistant", "content": json.dumps(action, ensure_ascii=False)}


def _user_feedback(payload: dict[str, Any]) -> dict[str, str]:
    return {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}


def _tool_args(action: dict[str, Any]) -> dict[str, Any]:
    raw_tool_args = action.get("args")
    return (
        {str(key): value for key, value in raw_tool_args.items()}
        if isinstance(raw_tool_args, dict)
        else {}
    )


def run_tool_using_loop(
    *,
    messages: list[dict[str, str]],
    step_budget: int,
    min_tool_steps: int,
    chat_fn: ChatFn,
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int | None,
    timeout: float,
    temperature: float,
    parse_response: ParseResponseFn,
    validate_final: ValidateFinalFn,
    run_tool_action: RunToolActionFn,
    min_tool_feedback: FeedbackFn,
    invalid_final_feedback: FeedbackFn,
    repair_feedback: FeedbackFn,
    tool_result_instruction: str,
    invalid_action_feedback: FeedbackFn | None = None,
    parse_error_feedback: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    chat_kwargs: dict[str, Any] | None = None,
) -> ToolLoopResult:
    """Drive the shared tool/final loop while callers own validation semantics.

    This helper deliberately does not know about edges, findings, job specs, or
    write behavior. Those remain in the agent/job modules so future changes
    cannot accidentally make one final schema validate like the other.
    """
    transcript: list[dict[str, Any]] = []
    final_attempts: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    final_action: dict[str, Any] | None = None
    final_items: list[dict[str, Any]] | None = None
    tool_count = 0
    chat_kwargs = chat_kwargs or {}
    fallback_invalid_action = invalid_action_feedback or (
        lambda: {"error": "Return action=tool or action=final only."}
    )

    for step in range(step_budget):
        response = chat_fn(
            sanitize_external_model_payload(messages),
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
            **chat_kwargs,
        )
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        action = parse_response(response)
        transcript.append({"step": step + 1, "action": action})

        if action.get("action") == "parse_error":
            if parse_error_feedback and step + 1 < step_budget:
                messages.append({"role": "assistant", "content": action.get("raw_preview") or ""})
                messages.append(_user_feedback(parse_error_feedback(action)))
                continue
            break

        if action.get("action") == "final":
            final_attempts.append(action)
            if tool_count < max(0, int(min_tool_steps)) and step + 1 < step_budget:
                messages.append(_assistant_message(action))
                messages.append(_user_feedback(min_tool_feedback()))
                continue
            candidate_items = validate_final(action)
            if not candidate_items and step + 1 < step_budget:
                messages.append(_assistant_message(action))
                messages.append(_user_feedback(invalid_final_feedback()))
                continue
            final_action = action
            final_items = candidate_items
            break

        if action.get("action") != "tool":
            messages.append(_assistant_message(action))
            messages.append(_user_feedback(fallback_invalid_action()))
            continue

        tool_name = str(action.get("tool") or "")
        observation = run_tool_action(tool_name, _tool_args(action))
        tool_count += 1
        transcript[-1]["observation"] = observation
        messages.append(_assistant_message(action))
        messages.append(
            {
                "role": "user",
                "content": (
                    "TOOL_RESULT:"
                    + "\n"
                    + json.dumps(observation, ensure_ascii=False, indent=2)
                    + "\n\n"
                    + tool_result_instruction
                ),
            }
        )

    if final_action is None:
        final_action = {}
    items = final_items if final_items is not None else validate_final(final_action)
    if not items and tool_count > 0:
        repair_messages = messages + [_user_feedback(repair_feedback())]
        response = chat_fn(
            sanitize_external_model_payload(repair_messages),
            api_key,
            model,
            base_url,
            max_tokens,
            timeout,
            temperature,
            **chat_kwargs,
        )
        add_usage(usage_total, compact_usage(response.get("usage") or {}))
        repair_action = parse_response(response)
        final_attempts.append(repair_action)
        if repair_action.get("action") == "final":
            repair_items = validate_final(repair_action)
            if repair_items:
                final_action = repair_action
                items = repair_items

    return ToolLoopResult(
        transcript=transcript,
        final_attempts=final_attempts,
        final_action=final_action,
        final_items=items,
        usage_total=usage_total,
        tool_count=tool_count,
    )
