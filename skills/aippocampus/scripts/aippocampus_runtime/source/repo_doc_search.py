"""Current-checkout repo-doc route candidates for registry-wide search."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import shell_quote
from aippocampus_runtime.core import compact_text, stable_text_fingerprint
from aippocampus_runtime.navigation import repo_familiarity
from aippocampus_runtime.source.query_match_gate import match_query_profile


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _hit_selector(route: Mapping[str, Any]) -> str:
    return stable_text_fingerprint(
        json.dumps(route, ensure_ascii=False, sort_keys=True, default=str),
        namespace="registry-search-hit-selector",
        prefix="srchit",
        length=18,
    )


def _repo_file_read_command(path: str) -> str:
    script = (
        "import pathlib,sys; "
        "p=pathlib.Path(sys.argv[1]); "
        "print(p.read_text(encoding='utf-8')[:6000])"
    )
    return f'python -c "{script}" {shell_quote(path)}'


def _row_haystack(row: Mapping[str, Any], path: str) -> str:
    route = row.get("route")
    docs = route.get("docs", []) if isinstance(route, Mapping) else []
    return " ".join(
        str(value or "")
        for value in (
            row.get("landmark"),
            " ".join(str(term) for term in row.get("route_terms") or []),
            row.get("boundary"),
            row.get("why_now"),
            row.get("action_delta_required"),
            path,
            " ".join(str(item) for item in docs),
        )
    )


def _repo_doc_match(
    *,
    row: Mapping[str, Any],
    query_text: str,
    query_gate: Mapping[str, Any],
    cwd: str | Path,
    snippet_chars: int,
) -> dict[str, Any] | None:
    path = str(row.get("first_source_to_reopen") or row.get("source_path") or "").strip()
    if not path or ":" in path or "\\" in path:
        return None
    root = Path(cwd).resolve()
    if not (root / path).is_file():
        return None
    profile = match_query_profile(
        query_text=query_text,
        gate=query_gate,
        haystack=_row_haystack(row, path),
    )
    if (
        int(profile.get("distinctive_anchor_count") or 0) > 0
        and int(profile.get("matched_distinctive_anchor_count") or 0) <= 0
    ):
        return None
    if not profile["accepted"]:
        return None
    line = row.get("source_line") if isinstance(row.get("source_line"), int) else 1
    source_route = {
        "kind": "repo_checkout_doc_hit",
        "path": path,
        "line": line,
        "boundary": "repo_familiarity_navigation_only_until_source_opened",
    }
    command = _repo_file_read_command(path)
    snippet = compact_text(
        " ".join(
            str(value or "")
            for value in (
                f"Repo doc: {path}",
                row.get("landmark"),
                row.get("action_delta_required"),
            )
        ),
        snippet_chars,
    )
    return {
        "hit_selector": _hit_selector(source_route),
        "thread": {
            "thread_key": f"repo:{path}",
            "title": row.get("landmark") or Path(path).name,
            "workspace_name": "current checkout",
        },
        "source": "repo_checkout_doc",
        "message_id": path,
        "line": line,
        "role": "repo_doc",
        "phase": "current_checkout",
        "score": 1000 + int(profile.get("matched_distinctive_anchor_count") or 0),
        "snippet": snippet,
        "query_match_profile": profile,
        "source_route": source_route,
        "reopen_command": command,
        "source_window_command": command,
        "last_search_reopen_command": command,
    }


def repo_checkout_doc_matches(
    *,
    cwd: str | Path | None,
    query_text: str,
    query_gate: Mapping[str, Any],
    limit: int,
    snippet_chars: int,
) -> list[dict[str, Any]]:
    if cwd is None:
        return []
    try:
        rows = repo_familiarity.current_checkout_source_rows(cwd)
    except (OSError, ValueError):
        return []
    matches = [
        match
        for row in rows
        if isinstance(row, Mapping)
        for match in (
            _repo_doc_match(
                row=row,
                query_text=query_text,
                query_gate=query_gate,
                cwd=cwd,
                snippet_chars=snippet_chars,
            ),
        )
        if match
    ]
    matches.sort(key=lambda item: (-_as_float(item.get("score")), str(item.get("message_id") or "")))
    return matches[: max(0, int(limit or 0))]


__all__ = ["repo_checkout_doc_matches"]
