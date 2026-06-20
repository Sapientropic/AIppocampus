#!/usr/bin/env python3
"""Return the latest assistant final answer from a Codex rollout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    command_value_needs_input,
    foreground_shell_action,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.source.host_internal_filter import contains_host_internal_material
from aippocampus_runtime.source.rollout import normalize_rollout

LOCAL_PATH_REDACTION = "<local-path-redacted>"
MAX_EXECUTABLE_RECOVERY_CUE_CHARS = 160
MAX_COMPACT_FINAL_ANSWER_CHARS = 1600


def latest_reply(rollout: Path) -> dict:
    messages, turns = normalize_rollout(rollout)
    assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]
    final_messages = [
        msg
        for msg in assistant_messages
        if msg.get("phase") == "final_answer" or msg.get("is_final")
    ]
    if final_messages:
        msg = final_messages[-1]
        status = "final_answer"
        warning = None
    elif assistant_messages:
        msg = assistant_messages[-1]
        status = "only_commentary_found"
        warning = "[⚠️] only_commentary_found"
    else:
        msg = None
        status = "no_assistant_reply_found"
        warning = "[⚠️] no_assistant_reply_found"

    turn = None
    if msg and msg.get("turn_index") is not None:
        turn = next((item for item in turns if item.get("id") == msg.get("turn_index")), None)
    user_cues = [
        item
        for item in messages
        if item.get("role") == "user"
        and (not msg or item.get("turn_index") == msg.get("turn_index"))
    ]
    if not user_cues:
        user_cues = [item for item in messages if item.get("role") == "user"]

    return {
        "status": status,
        "warning": warning,
        "rollout": str(rollout),
        "message": msg,
        "recovery_cue": user_cues[-1].get("text") if user_cues else "",
        "turn": turn,
        "message_count": len(messages),
        "turn_count": len(turns),
    }


def _message_card(
    message: dict[str, Any] | None,
    *,
    include_text: bool,
    include_preview: bool = True,
    include_bounded_final_text: bool = False,
) -> dict[str, Any] | None:
    if not message:
        return None
    card: dict[str, Any] = {
        "line": message.get("line"),
        "timestamp": message.get("timestamp"),
        "turn_index": message.get("turn_index"),
        "phase": message.get("phase") or "",
        "is_final": bool(message.get("is_final")),
    }
    if include_text:
        card["text"] = message.get("text") or ""
    elif include_bounded_final_text:
        card["text"] = core.compact_text(str(message.get("text") or ""), MAX_COMPACT_FINAL_ANSWER_CHARS)
        card["text_char_limit"] = MAX_COMPACT_FINAL_ANSWER_CHARS
        card["text_bounded"] = len(str(message.get("text") or "")) > MAX_COMPACT_FINAL_ANSWER_CHARS
    else:
        card["text_omitted"] = True
        if include_preview:
            card["preview"] = core.compact_text(str(message.get("text") or ""), 120)
    return redact_sensitive_values(redact_private_paths(card))


def _latest_reply_full_action() -> dict[str, Any]:
    action = foreground_shell_action(
        action_id="open_full_latest_reply",
        label="Open full latest reply",
        command="aippocampus latest-reply --detail full",
        why="Use this when the compact closeout is truncated or exact full wording is needed.",
        mutation_risk="read_only",
        claim_boundary="source_open_within_latest_final_answer_scope",
    )
    action["authority_after_running"] = "source_open_within_latest_final_answer_scope"
    return action


def latest_reply_tool_action() -> dict[str, Any]:
    return {
        "id": "open_full_latest_reply",
        "tool_name": "latest_reply",
        "arguments": {"detail": "full"},
        "claim_boundary": "source_open_within_latest_final_answer_scope",
        "mutation_risk": "read_only",
        "authority_after_running": "source_open_within_latest_final_answer_scope",
        "why": "Use this when the compact closeout is truncated or exact full wording is needed.",
    }


def _latest_reply_recall_action(cue: Any = None) -> dict[str, Any]:
    raw_cue = str(cue or "").strip()
    clean_cue = str(redact_sensitive_values(redact_private_paths(raw_cue)) or "")
    cue_reason = ""
    if contains_host_internal_material(raw_cue):
        cue_reason = "host_internal_cue_omitted"
    elif "\n" in raw_cue or "\r" in raw_cue:
        cue_reason = "multi_line_cue_omitted"
    elif len(clean_cue) > MAX_EXECUTABLE_RECOVERY_CUE_CHARS:
        cue_reason = "long_cue_omitted"
    elif command_value_needs_input(clean_cue):
        cue_reason = "cue_requires_caller_input"

    if clean_cue and not cue_reason:
        return foreground_shell_action(
            action_id="recall_current_thread_context",
            label="Recall current-thread context",
            command=f"aippocampus agent recall {shell_quote(clean_cue)} --json",
            why="Use the latest user turn as the continuity cue when no final-answer closeout is available.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
    action = foreground_template_action(
        action_id="recall_current_thread_context",
        label="Recall current-thread context",
        command_template='aippocampus agent recall "{cue}" --json',
        requires=["cue"],
        why="Use a real cue from the user/task when no final-answer closeout is available from latest-reply.",
        mutation_risk="read_only",
        claim_boundary="no_claim_before_reopen",
    )
    if raw_cue:
        action["cue_omitted_from_executable_command"] = True
        action["cue_omission_reason"] = cue_reason or "cue_not_safe_as_primary_command"
        action["safe_cue_strategy"] = "supply a short, current, human task cue before running recall"
    return action


def public_latest_reply_result(result: dict[str, Any], *, detail: str = "compact") -> dict[str, Any]:
    status = str(result.get("status") or "unknown")
    full = detail == "full"
    message = result.get("message") if isinstance(result.get("message"), dict) else None
    closeout_available = status == "final_answer"
    payload: dict[str, Any] = {
        "kind": "aippocampus_latest_reply",
        "ok": closeout_available,
        "status": status,
        "detail": detail,
        "closeout_available": closeout_available,
        "message": _message_card(
            message,
            include_text=full and closeout_available,
            include_bounded_final_text=closeout_available and not full,
        ),
        "message_count": result.get("message_count", 0),
        "turn_count": result.get("turn_count", 0),
        "rollout": LOCAL_PATH_REDACTION,
        "local_private_fields": ["rollout"] if closeout_available else ["rollout", "message.text"],
        "privacy_boundary": {
            "local_path_serialized": False,
            "commentary_text_serialized": bool(full and not closeout_available),
            "final_answer_text_serialized": bool(closeout_available),
            "final_answer_text_char_limit": (
                MAX_COMPACT_FINAL_ANSWER_CHARS if closeout_available and not full else None
            ),
        },
    }
    if closeout_available:
        actions = [_latest_reply_full_action()]
        payload.update(canonical_foreground_action_fields(actions[0], safe_next_actions=actions))
        if full:
            payload["message"] = _message_card(message, include_text=True)
    elif status == "only_commentary_found":
        payload["diagnostic_only"] = True
        payload["not_final_closeout"] = True
        actions = [_latest_reply_recall_action(result.get("recovery_cue")), _latest_reply_full_action()]
        payload.update(canonical_foreground_action_fields(actions[0], safe_next_actions=actions))
        payload["message"] = _message_card(
            message,
            include_text=full,
            include_preview=False,
        )
    else:
        payload["diagnostic_only"] = True
        payload["not_final_closeout"] = True
        actions = [_latest_reply_recall_action(result.get("recovery_cue"))]
        payload.update(canonical_foreground_action_fields(actions[0], safe_next_actions=actions))
    return payload


def latest_reply_unavailable_payload(exc: Exception, *, detail: str = "compact") -> dict[str, Any]:
    actions = [
        _latest_reply_recall_action(),
        foreground_shell_action(
            action_id="check_latest_reply_from_current_scope",
            label="Retry latest-reply in current scope",
            command="aippocampus latest-reply --json",
            why="Use this after changing to the project scope that owns the current rollout.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        ),
    ]
    payload = {
        "kind": "aippocampus_latest_reply",
        "ok": False,
        "status": "no_latest_reply_source_found",
        "detail": detail,
        "closeout_available": False,
        "diagnostic_only": True,
        "error": {
            "code": "no_rollout_for_cwd",
            "message": str(exc),
            "path_redacted": True,
        },
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        "examples": ["aippocampus latest-reply --json"],
        "cannot_claim": [
            "latest_final_answer_available",
            "source_backed_claim",
            "exact_prior_wording",
        ],
        "privacy_boundary": {
            "local_path_serialized": False,
            "rollout_text_serialized": False,
            "source_reopen_required_for_claims": True,
        },
    }
    return redact_sensitive_values(redact_private_paths(payload))


def render_latest_reply_text(payload: dict[str, Any]) -> str:
    lines = [f"status: {payload.get('status')}"]
    if payload.get("not_final_closeout"):
        lines.append("boundary: not a final assistant closeout")
    if payload.get("status") == "no_latest_reply_source_found":
        lines.append("boundary: no rollout/current-thread source was found")
    message = payload.get("message") if isinstance(payload.get("message"), dict) else None
    if message and payload.get("closeout_available"):
        lines.append(
            f"line {message.get('line')} | {message.get('timestamp')} | "
            f"turn={message.get('turn_index')} | phase={message.get('phase') or '(none)'}"
        )
        if message.get("text"):
            lines.append(str(message.get("text") or ""))
        else:
            lines.append(f"preview: {message.get('preview')}")
    elif message:
        lines.append(
            f"commentary line {message.get('line')} | turn={message.get('turn_index')} "
            "(text omitted)"
        )
    action = payload.get("foreground_action")
    if isinstance(action, dict):
        lines.append("next: " + str(action.get("command") or action.get("label") or "use recall/search"))
    else:
        lines.append("next: " + str(action or "use recall/search"))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus latest-reply",
        description=(
            "Latest final-answer closeout recovery card.\n\n"
            "Use this after context loss when you need the latest final assistant closeout, "
            "not in-progress commentary. Compact output is orientation only: reopen clean "
            "source before quoting exact wording or making high-risk claims.\n\n"
            "Common:\n"
            "  aippocampus latest-reply --json\n"
            "  aippocampus latest-reply --cwd <project> --json\n"
            "  aippocampus latest-reply --rollout <rollout.jsonl> --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--rollout")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--detail", choices=["compact", "full"], default="compact")
    parser.add_argument(
        "--operator-json",
        "--full-json",
        action="store_true",
        dest="operator_json",
        help="Emit full diagnostic text and local operator fields.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    cwd = Path(args.cwd).resolve()
    detail = "full" if args.operator_json else args.detail
    try:
        rollout = Path(args.rollout) if args.rollout else core.locate_rollout(cwd, core.codex_home())
        result = latest_reply(rollout)
    except (FileNotFoundError, OSError, ValueError) as exc:
        public = latest_reply_unavailable_payload(exc, detail=detail)
        if args.operator_json:
            diagnostic = {
                "ok": False,
                "status": "no_latest_reply_source_found",
                "public_projection": public,
            }
            print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        elif args.json_output:
            print(json.dumps(public, ensure_ascii=False, indent=2))
        else:
            print(render_latest_reply_text(public))
        return 2
    public = public_latest_reply_result(result, detail=detail)

    if args.operator_json:
        diagnostic = dict(result)
        diagnostic["public_projection"] = public
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
    elif args.json_output:
        print(json.dumps(public, ensure_ascii=False, indent=2))
    else:
        print(render_latest_reply_text(public))
    return 0 if public.get("closeout_available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
