"""Recent recall route materialization for action-time hints."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_iso_unix(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _recent_recall_anchor_probe(
    *,
    selector_path: Path,
    request_index: int,
    query: str,
) -> dict[str, Any]:
    try:
        from aippocampus_runtime.recall import agent_continuity as agent
        from aippocampus_runtime.recall.agent_recall_cache import handle_from_last_recall_cache
        from aippocampus_runtime.recall.source_anchor_gate import distinctive_query_anchors
        from aippocampus_runtime.source.artifact_role import artifact_role_profile
    except Exception as exc:  # pragma: no cover - defensive intake metadata
        return {"status": "blocked", "reason": "probe_unavailable", "error": type(exc).__name__}

    anchors = distinctive_query_anchors(query)
    if not anchors:
        return {
            "status": "blocked",
            "reason": "no_distinctive_query_anchors",
            "anchor_count": 0,
            "opened_anchor_hits": 0,
        }
    try:
        handle, cached_context = handle_from_last_recall_cache(
            request_index=request_index,
            path=selector_path,
        )
        gate_context_value = cached_context.get("recall_gate_context")
        gate_context: Mapping[str, Any] = (
            gate_context_value if isinstance(gate_context_value, Mapping) else cached_context
        )
        cached_gate_value = gate_context.get("source_anchor_gate")
        cached_gate: Mapping[str, Any] = (
            cached_gate_value if isinstance(cached_gate_value, Mapping) else {}
        )
        payload = agent.deepen(
            handle,
            cwd=cached_context.get("cwd"),
            clean_source_dir=cached_context.get("clean_source_dir"),
            registry_dir=cached_context.get("registry_dir"),
            macro_state_path=cached_context.get("macro_state_jsonl"),
            project=str(cached_context.get("project") or "AIppocampus"),
            max_matches=int(cached_context.get("max") or agent.MAX_ROUTES),
        )
    except Exception as exc:  # pragma: no cover - local source corruption guard
        return {"status": "blocked", "reason": "source_reopen_failed", "error": type(exc).__name__}
    if payload.get("status") != "ok":
        return {
            "status": "blocked",
            "reason": "source_reopen_not_ok",
            "anchor_count": len(anchors),
            "opened_anchor_hits": 0,
        }
    result = payload.get("result")
    result_map: Mapping[str, Any] = result if isinstance(result, Mapping) else {}
    source_window = result_map.get("source_window")
    source_map: Mapping[str, Any] = source_window if isinstance(source_window, Mapping) else {}
    source_text = json.dumps(source_map, ensure_ascii=False, sort_keys=True).casefold()
    hits = [anchor for anchor in anchors if anchor.casefold() in source_text]
    required = 2 if len(anchors) >= 3 else 1
    artifact_role = artifact_role_profile(text=source_text, query_text=query)
    artifact_blocked = bool(artifact_role.get("demote"))
    cached_gate_passed = bool(
        cached_gate.get("status") == "passed"
        and (
            cached_gate.get("target_source_matched") is True
            or gate_context.get("target_source_matched") is True
            or str(
                cached_gate.get("source_chain_role")
                or gate_context.get("source_chain_role")
                or ""
            ).strip()
        )
    )
    passed = (len(hits) >= required or cached_gate_passed) and not artifact_blocked
    return {
        "status": "passed" if passed else "blocked",
        "reason": (
            "opened_source_validation_artifact"
            if artifact_blocked
            else str(cached_gate.get("reason") or "cached_source_anchor_gate")
            if cached_gate_passed and len(hits) < required
            else "opened_source_anchor_coverage"
        ),
        "anchor_count": len(anchors),
        "opened_anchor_hits": len(hits),
        "required_anchor_hits": required,
        "target_source_matched": passed,
        "cached_source_anchor_gate": {
            key: value
            for key, value in cached_gate.items()
            if key
            in {
                "status",
                "reason",
                "target_source_matched",
                "source_chain_role",
            }
            and value not in (None, "", [], {})
        }
        if cached_gate
        else None,
        "artifact_role": artifact_role if artifact_role.get("role") != "topic_candidate" else None,
    }


def load_default_recent_recall_routes(
    *,
    now_unix: float,
    max_age_seconds: int = 24 * 60 * 60,
    max_snapshots: int = 40,
    max_routes: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load same-machine source-opened recall selector routes for hot hints.

    The action-time hook needs a cache it can read without doing recall work.
    Recent selector snapshots give it that cache material only after the agent
    already followed recall -> deepen. This keeps the hot path useful without
    converting dogfood fixtures or source-free semantic guidance into live
    foreground nudges.
    """

    try:
        from aippocampus_runtime.recall.agent_recall_cache import recall_selector_cache_dir
    except Exception as exc:  # pragma: no cover - defensive provider metadata
        return [], {
            "status": "unavailable",
            "source": "recent_recall_selector_snapshots",
            "route_count": 0,
            "error": type(exc).__name__,
        }

    try:
        selector_dir = recall_selector_cache_dir()
        paths = sorted(
            selector_dir.glob("sel_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:max_snapshots]
    except OSError:
        return [], {
            "status": "not_found",
            "source": "recent_recall_selector_snapshots",
            "route_count": 0,
        }

    rows: list[dict[str, Any]] = []
    stale_count = 0
    unopened_count = 0
    malformed_count = 0
    anchor_blocked_count = 0
    source_reopen_failed_count = 0
    seen: set[tuple[str, int, str]] = set()
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            malformed_count += 1
            continue
        if not isinstance(payload, Mapping):
            malformed_count += 1
            continue
        selector = str(payload.get("selector_id") or path.stem).strip()
        context_value = payload.get("context")
        context: Mapping[str, Any] = context_value if isinstance(context_value, Mapping) else {}
        query = str(context.get("query") or "").strip()
        for request in payload.get("requests") or []:
            if not isinstance(request, Mapping):
                continue
            try:
                request_index = int(request.get("request_index") or 0)
            except (TypeError, ValueError):
                request_index = 0
            route_id = str(request.get("route_id") or "").strip()
            if not selector or request_index <= 0 or not route_id:
                continue
            if not request.get("opened"):
                unopened_count += 1
                continue
            opened_at_unix = _parse_iso_unix(request.get("opened_at"))
            if opened_at_unix and now_unix - opened_at_unix > max_age_seconds:
                stale_count += 1
                continue
            key = (selector, request_index, route_id)
            if key in seen:
                continue
            anchor_probe = _recent_recall_anchor_probe(
                selector_path=path,
                request_index=request_index,
                query=query,
            )
            if anchor_probe.get("status") != "passed":
                if str(anchor_probe.get("reason") or "").startswith("source_reopen"):
                    source_reopen_failed_count += 1
                else:
                    anchor_blocked_count += 1
                continue
            seen.add(key)
            rows.append(
                {
                    "record_id": f"recent-recall:{selector}:{request_index}",
                    "route_id": route_id,
                    "deepen_route_id": request.get("deepen_route_id") or route_id,
                    "request_index": request_index,
                    "recall_selector": selector,
                    "query": query,
                    "matched_cue_anchors": request.get("matched_cue_anchors") or [],
                    "opened_at": request.get("opened_at"),
                    "opened_count": int(request.get("opened_count") or 1),
                    "source_anchor_probe": {
                        key: value
                        for key, value in anchor_probe.items()
                        if key not in {"error"} and value not in (None, "", [], {})
                    },
                    "reason_codes": ["recent_recall_source_anchor_checked"],
                    "confidence": "high",
                }
            )
            if len(rows) >= max_routes:
                break
        if len(rows) >= max_routes:
            break
    return rows, {
        "status": "found" if rows else "not_found",
        "source": "recent_recall_selector_snapshots",
        "snapshot_count": len(paths),
        "route_count": len(rows),
        "stale_route_count": stale_count,
        "unopened_route_count": unopened_count,
        "anchor_blocked_route_count": anchor_blocked_count,
        "source_reopen_failed_count": source_reopen_failed_count,
        "malformed_snapshot_count": malformed_count,
        "max_age_seconds": max_age_seconds,
    }
