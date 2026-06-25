"""Shared registry source-window route and command helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import shell_quote


def registry_clean_source_route(
    *,
    thread_key: str,
    message_id: str | None = None,
    line: Any = None,
    boundary: str = "reopen_source_before_quoting_or_strong_claims",
) -> dict[str, Any]:
    route = {
        "kind": "registry_clean_source_hit",
        "thread_key": str(thread_key or "").strip(),
        "message_id": str(message_id or "").strip(),
        "line": line,
        "boundary": boundary,
    }
    return {key: value for key, value in route.items() if value not in (None, "", [], {})}


def registry_source_window_command(
    route_or_ref: Mapping[str, Any],
    *,
    registry_dir: str | Path | None = None,
    include_registry_dir: bool = False,
) -> str:
    thread_key = str(route_or_ref.get("thread_key") or "").strip()
    message_id = str(route_or_ref.get("message_id") or route_or_ref.get("id") or "").strip()
    line = route_or_ref.get("line") or route_or_ref.get("source_line")
    if not thread_key:
        return ""
    line_arg = ""
    if line is not None and str(line).isdigit():
        line_arg = f"--line {int(str(line))}"
    registry_arg = ""
    if include_registry_dir and registry_dir:
        registry_arg = f"--registry-dir {shell_quote(str(Path(registry_dir).resolve()))}"
    parts = [
        "aippocampus search --open-source",
        f"--thread-key {shell_quote(thread_key)}",
        f"--message-id {shell_quote(message_id)}" if message_id else "",
        line_arg,
        registry_arg,
        "--json",
    ]
    return " ".join(part for part in parts if part)


__all__ = ["registry_clean_source_route", "registry_source_window_command"]
