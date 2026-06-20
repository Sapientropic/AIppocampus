"""Current-thread clean-source reopen helpers for `aippocampus search`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.core import (
    compact_text,
    default_thread_clean_source_dir,
    resolve_artifact_path,
)
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.search_core import iter_clean_messages

LEGACY_CLEAN_SOURCE_DIR = ".aippocampus/clean-source"
DEFAULT_SOURCE_WINDOW_CHARS = 1800


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolved_clean_source_dir(
    cwd: str | Path, clean_source_dir: str | Path | None = None
) -> Path:
    root = Path(cwd).resolve()
    if clean_source_dir is None:
        global_dir = default_thread_clean_source_dir(root)
        legacy_dir = root / LEGACY_CLEAN_SOURCE_DIR
        return (
            global_dir
            if (global_dir / "messages.jsonl").exists()
            or not (legacy_dir / "messages.jsonl").exists()
            else legacy_dir
        )
    return resolve_artifact_path(clean_source_dir, root, default_thread_clean_source_dir(root))


def _current_source_window_recovery(*, code: str, message: str) -> dict[str, Any]:
    action = foreground_template_action(
        action_id="rerun_current_thread_search",
        label="Rerun current-thread search",
        command_template='aippocampus search "{distinctive_phrase}" --json',
        requires=["distinctive_phrase"],
        why=(
            "The current-thread source selector was unavailable; rerun search for "
            "a fresh bounded source route."
        ),
        mutation_risk="read_only",
        claim_boundary="search_miss_is_not_absence_of_memory",
    )
    payload = {
        "kind": "aippocampus_current_thread_source_window",
        "ok": False,
        "status": "cannot_verify",
        "error": {"code": code, "message": message},
        "metrics": {"source_reopen_success": False},
        "source_boundary": {
            "authority": "direction_only",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claim": True,
        },
        "privacy": {
            "paths_included": False,
            "raw_full_transcript_emitted": False,
        },
    }
    payload.update(canonical_foreground_action_fields(action, safe_next_actions=[action]))
    return redact_sensitive_values(redact_private_paths(payload))


def open_current_thread_source_window(
    *,
    cwd: str | Path,
    clean_source_dir: str | Path | None = None,
    message_id: str | None = None,
    line: int | None = None,
    context_lines: int = 2,
    include_paths: bool = False,
) -> dict[str, Any]:
    if not str(message_id or "").strip() and not line:
        return _current_source_window_recovery(
            code="source_selector_required",
            message="Provide --message-id or --line for current-thread source reopen.",
        )
    source_dir = _resolved_clean_source_dir(cwd, clean_source_dir)
    messages_path = source_dir / "messages.jsonl"
    messages = list(iter_clean_messages(messages_path))
    if not messages:
        return _current_source_window_recovery(
            code="clean_source_missing",
            message="No clean-source messages were available for the current thread.",
        )
    selected_index: int | None = None
    wanted_message = str(message_id or "").strip()
    for index, message in enumerate(messages):
        current_id = str(message.get("message_id") or message.get("id") or "")
        if wanted_message and current_id == wanted_message:
            selected_index = index
            break
        if line and _as_int(message.get("source_line")) == int(line):
            selected_index = index
            break
    if selected_index is None:
        return _current_source_window_recovery(
            code="source_selector_not_found",
            message="The requested current-thread source selector did not match clean source.",
        )
    radius = max(0, int(context_lines or 0))
    start = max(0, selected_index - radius)
    end = min(len(messages), selected_index + radius + 1)
    source_window = []
    for message in messages[start:end]:
        source_window.append(
            {
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "turn_index": message.get("turn_index"),
                "source_line": message.get("source_line"),
                "timestamp": message.get("timestamp"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "text": compact_text(
                    str(message.get("text") or ""),
                    DEFAULT_SOURCE_WINDOW_CHARS,
                ),
            }
        )
    payload = {
        "kind": "aippocampus_current_thread_source_window",
        "ok": True,
        "status": "source_open",
        "source_route": {
            "kind": "current_thread_clean_source_hit",
            "message_id": wanted_message or None,
            "line": int(line) if line else None,
            "boundary": "bounded_source_window_only",
        },
        "source_window": source_window,
        "source_boundary": {
            "authority": "source_open",
            "source_backed_claim_allowed": True,
            "claim_scope": "returned_source_window_only",
            "source_reopen_required_before_claim": False,
            "raw_full_transcript_emitted": False,
        },
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_full_transcript_emitted": False,
        },
        "metrics": {
            "source_reopen_success": True,
            "window_message_count": len(source_window),
            "window_context_lines": radius,
            "source_window_text_is_capped": True,
        },
    }
    if include_paths:
        payload["local_diagnostic"] = {"clean_source_messages_jsonl": str(messages_path)}
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))


def _current_reopen_command(match: Mapping[str, Any]) -> str:
    message_id = str(match.get("message_id") or match.get("id") or "").strip()
    line = match.get("source_line") or match.get("line")
    parts = ["aippocampus search --open-current-source"]
    if message_id:
        parts.append(f"--message-id {shell_quote(message_id)}")
    elif line is not None:
        parts.append(f"--line {int(_as_int(line))}")
    else:
        return ""
    parts.append("--json")
    return " ".join(parts)


def annotate_current_search_reopen_commands(
    matches: list[dict[str, Any]],
    *,
    source_path: str | Path | None,
    include_paths: bool,
) -> None:
    source_arg = ""
    if include_paths and source_path:
        source_dir = Path(source_path).parent
        source_arg = f" --clean-source-dir {shell_quote(str(source_dir.resolve()))}"
    for index, match in enumerate(matches, start=1):
        command = _current_reopen_command(match)
        match["hit_index"] = index
        if command:
            match["reopen_command"] = command
            base_command = command.removesuffix(" --json")
            match["source_window_command"] = (
                f"{base_command}{source_arg} --json" if source_arg else command
            )


def render_current_source_window_text(
    result: Mapping[str, Any], *, snippet_chars: int
) -> str:
    if not result.get("ok"):
        error = result.get("error") if isinstance(result.get("error"), Mapping) else {}
        return "\n".join(
            [
                "AIppocampus current-thread source window",
                f"status: {result.get('status') or 'cannot_verify'}",
                f"error: {error.get('code') or 'unknown'}",
                "boundary: rerun search for a fresh source-backed route before quoting.",
            ]
        )
    lines = [
        "AIppocampus current-thread source window",
        "boundary: source is open only within the returned bounded window.",
    ]
    for row in result.get("source_window") or []:
        if not isinstance(row, Mapping):
            continue
        label = row.get("message_id") or row.get("turn_id") or row.get("source_line")
        text = compact_text(str(row.get("text") or ""), snippet_chars)
        lines.append(f"- {label}: {text}")
    return "\n".join(lines)
