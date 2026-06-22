"""Registry metadata thread-candidate routes.

Thread candidates are intentionally weak navigation hints. They may help an
agent choose where to search next, but they must not be treated as source-open
handles until another lane resolves concrete message/turn/line refs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from aippocampus_runtime.registry import api as registry
from aippocampus_runtime.registry.search import entry_search_score

StableId = Callable[..., str]
SafeText = Callable[[Any, int], str]


def registry_thread_candidate_routes(
    *,
    intent_terms: list[str],
    registry_dir: Path | None,
    max_routes: int,
    stable_id: StableId,
    safe_text: SafeText,
) -> list[dict[str, Any]]:
    json_path, _ = registry.registry_paths(registry_dir)
    if not json_path.exists():
        return []
    payload = registry.load_registry(json_path)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for entry in payload.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        score = entry_search_score(entry, intent_terms)
        if score > 0:
            candidates.append((score, entry))
    candidates.sort(key=lambda item: -item[0])
    routes: list[dict[str, Any]] = []
    for score, entry in candidates[:max_routes]:
        route_id = stable_id("registry", entry.get("thread_key"), score)
        routes.append(
            {
                "handle": {
                    "kind": "thread_candidate",
                    "thread_key": entry.get("thread_key"),
                    "route_id": route_id,
                },
                "route_id": route_id,
                "kind": "thread_candidate",
                "title": safe_text(entry.get("title") or entry.get("thread_key"), 120),
                "summary": safe_text(entry.get("summary") or entry.get("workspace_name"), 180),
                "evidence_level": "candidate",
                "support_level": "navigation",
                "source_refs": [{"thread_key": entry.get("thread_key")}],
                "scope_labels": [
                    str(label)
                    for label in entry.get("scope_labels") or []
                    if isinstance(label, str)
                ][:8],
                "reopenable": False,
                "why_this_may_matter": (
                    "A registry thread matched the cue; search or reopen concrete "
                    "source refs before relying on it."
                ),
                "suggested_next": {"tool": "search_memory"},
            }
        )
    return routes


__all__ = ["registry_thread_candidate_routes"]
