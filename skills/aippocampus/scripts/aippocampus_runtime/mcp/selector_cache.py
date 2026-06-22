from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp.recall_navigation import (
    RecallNavigationError,
    normalize_handle,
)
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    LAST_RECALL_CACHE_ENV,
    handle_from_last_recall_cache,
    last_recall_cache_path,
    recall_selector_cache_candidates,
)


def recall_cache_path_for_mcp_recall(
    arguments: dict[str, Any],
    *,
    registry_dir: Path | None,
) -> Path:
    if (
        not arguments.get("last_recall_path")
        and registry_dir is not None
        and not os.environ.get(LAST_RECALL_CACHE_ENV)
        and arguments.get("registry_dir")
    ):
        return registry_dir / "agent" / "last-recall.json"
    return last_recall_cache_path(arguments.get("last_recall_path"))


def _append_selector_candidate(
    candidates: list[Path],
    selector: str,
    *,
    registry_dir_value: Any,
) -> None:
    if not registry_dir_value:
        return
    candidate = Path(str(registry_dir_value)).resolve() / "agent" / "recall-selectors" / f"{selector}.json"
    for existing in candidates:
        try:
            if existing.resolve() == candidate.resolve():
                return
        except OSError:
            if str(existing) == str(candidate):
                return
    candidates.append(candidate)


def handle_from_selector_or_last_recall(
    arguments: dict[str, Any],
    *,
    request_index: int,
) -> tuple[Any, dict[str, Any], str | Path | None]:
    selector_cache_path: str | Path | None = arguments.get("last_recall_path")
    selector = str(arguments.get("recall_selector") or "")
    if not selector:
        handle, cached_context = handle_from_last_recall_cache(
            request_index=request_index,
            path=selector_cache_path,
        )
        return handle, cached_context, selector_cache_path
    last_exc: Exception | None = None
    candidates = recall_selector_cache_candidates(
        selector,
        last_recall_path_value=arguments.get("last_recall_path"),
    )
    # Foreground MCP calls often carry cwd/registry_dir but intentionally avoid
    # leaking a last-recall path. Treat an explicit registry_dir as a same-machine
    # selector namespace so a valid recall selector can still reopen source after
    # env slots change or the caller omits private cache paths.
    _append_selector_candidate(
        candidates,
        selector,
        registry_dir_value=arguments.get("registry_dir"),
    )
    for candidate in candidates:
        try:
            handle, cached_context = handle_from_last_recall_cache(
                request_index=request_index,
                path=candidate,
            )
            if not handle:
                last_exc = ValueError("selector cache did not contain a usable reopen handle")
                continue
            try:
                normalize_handle(handle)
            except RecallNavigationError as exc:
                last_exc = exc
                continue
            return handle, cached_context, candidate
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    raise ValueError("recall selector did not resolve to a cache path")
