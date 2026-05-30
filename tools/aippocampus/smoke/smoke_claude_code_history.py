#!/usr/bin/env python3
"""Privacy-preserving Claude Code local history parser smoke."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from _paths import repo_root
except ImportError:  # pragma: no cover - direct script fallback
    repo_root = None  # type: ignore[assignment]


def _bootstrap_paths() -> Path:
    root = repo_root() if repo_root else Path(__file__).resolve().parents[3]
    scripts = root / "skills" / "aippocampus" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return root


_bootstrap_paths()

from conversation_sources import ClaudeCodeConversationProvider  # noqa: E402


def _session_sort_key(source: Any) -> tuple[float, str]:
    try:
        mtime = source.path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (-mtime, source.path.name)


def summarize_source(provider: ClaudeCodeConversationProvider, source: Any) -> dict[str, Any]:
    try:
        messages, turns = provider.read_normalized_messages(source)
        return {
            "provider": provider.name,
            "status": "parsed",
            "session_id_present": bool(source.session_id),
            "path_exists": source.path.exists(),
            "cwd_present": bool(source.cwd),
            "timestamp_present": bool(source.timestamp),
            "message_count": len(messages),
            "turn_count": len(turns),
        }
    except Exception as exc:  # pragma: no cover - defensive live-history guard
        return {
            "provider": provider.name,
            "status": "parse_failed",
            "session_id_present": bool(getattr(source, "session_id", None)),
            "path_exists": bool(getattr(source, "path", Path()).exists()),
            "cwd_present": bool(getattr(source, "cwd", None)),
            "timestamp_present": bool(getattr(source, "timestamp", None)),
            "message_count": 0,
            "turn_count": 0,
            "error_code": type(exc).__name__,
        }


def run_smoke(
    *,
    home: Path | None = None,
    cwd: Path | None = None,
    max_sessions: int = 3,
) -> dict[str, Any]:
    provider = ClaudeCodeConversationProvider(home)
    projects = provider.home / "projects"
    home_exists = provider.home.exists()
    projects_exists = projects.exists()
    sessions = sorted(list(provider.discover_sessions()), key=_session_sort_key)
    target_cwd = (cwd or Path.cwd()).resolve()
    try:
        provider.locate_current(target_cwd)
        current_cwd_match = True
    except FileNotFoundError:
        current_cwd_match = False

    samples = [summarize_source(provider, source) for source in sessions[:max(0, max_sessions)]]
    parsed_nonempty = [
        item
        for item in samples
        if item.get("status") == "parsed"
        and int(item.get("message_count") or 0) > 0
        and int(item.get("turn_count") or 0) > 0
    ]
    if not home_exists:
        status = "blocked_missing_home"
    elif not projects_exists:
        status = "blocked_missing_projects"
    elif not sessions:
        status = "blocked_missing_history"
    elif not parsed_nonempty:
        status = "failed_parse_or_empty"
    else:
        status = "passed"

    return {
        "ok": status == "passed",
        "status": status,
        "provider": provider.name,
        "home_exists": home_exists,
        "projects_exists": projects_exists,
        "session_count": len(sessions),
        "current_cwd_match": current_cwd_match,
        "sample_count": len(samples),
        "samples": samples,
        "privacy": "This smoke reports booleans and counts only; transcript text and local paths are intentionally omitted.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--cwd", type=Path, default=None)
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_smoke(home=args.home, cwd=args.cwd, max_sessions=args.max_sessions)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Claude Code local history: {result['status']}")
        print(f"sessions: {result['session_count']}")
        print(f"samples: {result['sample_count']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
