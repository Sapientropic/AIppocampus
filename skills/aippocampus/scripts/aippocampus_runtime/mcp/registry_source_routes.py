"""Build deepenable MCP routes from concrete registry clean-source refs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp.source_ref_matching import message_matches_ref
from aippocampus_runtime.mcp.source_ref_registry import source_candidate_dirs_for_ref
from aippocampus_runtime.recall.query_policy import semantic_trigger_terms
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows
from aippocampus_runtime.source.registry_search import search_registry_sources
from aippocampus_runtime.source.registry_search_evidence import match_has_direct_source_open_route
from aippocampus_runtime.source.search import iter_clean_messages

CleanRef = Callable[[dict[str, Any]], dict[str, Any]]
RouteHandle = Callable[..., str]
StableId = Callable[..., str]
SafeText = Callable[[Any, int], str]


def source_ref_from_registry_match(
    match: Mapping[str, Any],
    *,
    clean_ref: CleanRef,
) -> dict[str, Any]:
    raw_route = match.get("source_route")
    route = raw_route if isinstance(raw_route, Mapping) else {}
    if route.get("kind") != "registry_clean_source_hit":
        return {}
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    ref = {
        "thread_key": route.get("thread_key") or thread_map.get("thread_key"),
        "message_id": route.get("message_id") or match.get("message_id"),
        "turn_id": match.get("turn_id"),
        "turn_index": match.get("turn_index"),
        "line": route.get("line") or match.get("line"),
        "phase": match.get("phase") or "",
    }
    clean = clean_ref({key: value for key, value in ref.items() if value not in (None, "")})
    if not clean.get("thread_key"):
        return {}
    if not any(clean.get(key) for key in ("message_id", "turn_id", "turn_index", "line")):
        return {}
    return clean


def source_ref_exists(
    ref: Mapping[str, Any],
    *,
    clean_source_dir: Path,
    registry_dir: Path | None,
) -> bool:
    ref_dict = dict(ref)
    candidate_dirs = source_candidate_dirs_for_ref(
        ref_dict,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
    )
    for candidate_dir in candidate_dirs:
        messages = iter_clean_messages(candidate_dir / "messages.jsonl")
        if any(message_matches_ref(message, ref_dict) for message in messages):
            return True
    return False


def reviewed_semantic_seed_path() -> Path:
    return Path(__file__).resolve().parents[3] / "references" / "reviewed-semantic-triggers.seed.jsonl"


def dedupe_routes_by_source_ref(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped_routes: list[dict[str, Any]] = []
    seen_route_refs: set[str] = set()
    for route in routes:
        refs = route.get("source_refs") or []
        ref = refs[0] if refs and isinstance(refs[0], Mapping) else {}
        key = "|".join(
            str(ref.get(part) or "")
            for part in ("thread_key", "message_id", "turn_id", "turn_index", "line")
        )
        key = key or str(route.get("route_id") or "")
        if key and key in seen_route_refs:
            continue
        if key:
            seen_route_refs.add(key)
        deduped_routes.append(route)
    return deduped_routes


def route_from_source_ref(
    source_ref: Mapping[str, Any],
    *,
    source_dir: Path,
    clean_ref: CleanRef,
    route_handle: RouteHandle,
    stable_id: StableId,
    safe_text: SafeText,
    route_id_prefix: str,
    title: Any,
    summary: Any,
    scope_labels: list[str] | None = None,
    scope_bucket: str = "registry_source",
    matched_cue_family: str = "registry_source_search",
    route_topic: str = "",
    route_label: str = "registry_source route",
    reason_codes: list[str] | None = None,
    source_chain_role: str = "",
) -> dict[str, Any] | None:
    ref = clean_ref(dict(source_ref))
    if not ref or not ref.get("thread_key"):
        return None
    route_id = stable_id(route_id_prefix, ref, source_chain_role)
    handle = route_handle(
        source_dir=source_dir,
        route_id=route_id,
        source_refs=[ref],
        evidence_level="needs_reopen",
    )
    reason = list(reason_codes or [])
    if not reason:
        reason = ["registry_clean_source_reopenable", "source_reopen_required"]
    return {
        "handle": handle,
        "route_id": route_id,
        "kind": "source_window",
        "title": safe_text(title, 90),
        "summary": safe_text(summary, 220),
        "evidence_level": "needs_reopen",
        "support_level": "navigation",
        "source_refs": [ref],
        "scope_labels": list(dict.fromkeys(scope_labels or []))[:8],
        "scope_bucket": scope_bucket,
        "matched_cue_family": matched_cue_family,
        "route_topic": route_topic,
        "source_chain_role": source_chain_role,
        "label_granularity": "topic_label" if route_topic else "source_ref",
        "route_label_specificity_score": 1.0 if route_topic else 0.85,
        "route_label": route_label,
        "triage_rank_reason_codes": reason[:4],
        "reopenable": True,
        "why_this_may_matter": (
            "This registry clean-source route has a concrete source ref; "
            "deepen it before using details."
        ),
        "suggested_next": {
            "tool": "recall_deepen",
            "arguments": {"handle": handle},
        },
        "source_reopen_path": {
            "tool": "get_turn_context",
            "arguments": {
                key: ref[key]
                for key in ("thread_key", "message_id", "turn_id", "turn_index")
                if key in ref
            },
        },
    }


def route_from_registry_match(
    match: Mapping[str, Any],
    *,
    source_dir: Path,
    registry_dir: Path | None,
    clean_ref: CleanRef,
    route_handle: RouteHandle,
    stable_id: StableId,
    safe_text: SafeText,
    route_id_prefix: str = "registry_source",
    route_topic: str = "",
    matched_cue_family: str = "registry_source_search",
    route_label: str = "registry_source route",
    reason_codes: list[str] | None = None,
    source_chain_role: str = "",
) -> dict[str, Any] | None:
    if not match_has_direct_source_open_route(match):
        return None
    source_ref = source_ref_from_registry_match(match, clean_ref=clean_ref)
    if not source_ref:
        return None
    if not source_ref_exists(
        source_ref,
        clean_source_dir=source_dir,
        registry_dir=registry_dir,
    ):
        return None
    scope_labels = [
        str(label)
        for label in [*(match.get("scope_labels") or []), *(match.get("semantic_scope_labels") or [])]
        if isinstance(label, str)
    ]
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    title = thread_map.get("title") or thread_map.get("thread_key") or route_label
    return route_from_source_ref(
        source_ref,
        source_dir=source_dir,
        clean_ref=clean_ref,
        route_handle=route_handle,
        stable_id=stable_id,
        safe_text=safe_text,
        route_id_prefix=route_id_prefix,
        title=title,
        summary=match.get("snippet"),
        scope_labels=scope_labels,
        scope_bucket="registry_source",
        matched_cue_family=matched_cue_family,
        route_topic=route_topic,
        route_label=route_label,
        reason_codes=reason_codes,
        source_chain_role=source_chain_role,
    )


def registry_clean_source_routes(
    *,
    intent: str,
    cwd: Path,
    source_dir: Path,
    registry_dir: Path | None,
    max_routes: int,
    clean_ref: CleanRef,
    route_handle: RouteHandle,
    stable_id: StableId,
    safe_text: SafeText,
    search_patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    if registry_dir is None:
        return []
    patterns = search_patterns or [intent]
    try:
        payload = search_registry_sources(
            patterns,
            registry_dir=registry_dir,
            limit=max(1, max_routes),
            per_thread_limit=2,
            cwd=cwd,
        )
    except Exception:
        # aippocampus-debt-ok: broad-exception-boundary
        # Registry clean-source routes are an optional navigation supplement.
        # If broad registry search trips over a stale local index, fail closed
        # to no supplemental route; primary current-source and deepen paths
        # remain available and must not inherit this exception as evidence.
        return []
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in payload.get("matches") or []:
        if not isinstance(match, Mapping):
            continue
        route = route_from_registry_match(
            match,
            source_dir=source_dir,
            registry_dir=registry_dir,
            clean_ref=clean_ref,
            route_handle=route_handle,
            stable_id=stable_id,
            safe_text=safe_text,
        )
        if route is None:
            continue
        ref = route["source_refs"][0]
        key = "|".join(
            str(ref.get(part) or "") for part in ("thread_key", "message_id", "line")
        )
        if key in seen:
            continue
        seen.add(key)
        routes.append(route)
        if len(routes) >= max_routes:
            break
    return routes


def semantic_trigger_source_routes(
    *,
    intent: str,
    source_dir: Path,
    registry_dir: Path | None,
    semantic_triggers_path: Path | None,
    max_routes: int,
    clean_ref: CleanRef,
    route_handle: RouteHandle,
    stable_id: StableId,
    safe_text: SafeText,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if semantic_triggers_path is None or not semantic_triggers_path.exists():
        return [], {"trigger_source_routes": 0, "seed_trigger_match_count": 0}
    intent_low = str(intent or "").casefold()
    routes: list[dict[str, Any]] = []
    source_free_matches = 0
    source_matches = 0
    matched_terms: list[str] = []
    matched_trigger_ids: list[str] = []
    rows = load_jsonl_dict_rows(semantic_triggers_path).rows
    for row in rows:
        terms = semantic_trigger_terms([row], limit=12)
        if not any(term.casefold() in intent_low for term in terms if term):
            continue
        matched_terms.extend(term for term in terms if term and term.casefold() in intent_low)
        trigger_id = str(row.get("trigger_id") or "")
        if trigger_id:
            matched_trigger_ids.append(trigger_id)
        refs = [ref for ref in row.get("source_refs") or [] if isinstance(ref, dict)]
        if not refs:
            source_free_matches += 1
            continue
        source_matches += 1
        for ref in refs[:3]:
            if not source_ref_exists(ref, clean_source_dir=source_dir, registry_dir=registry_dir):
                continue
            route = route_from_source_ref(
                ref,
                source_dir=source_dir,
                clean_ref=clean_ref,
                route_handle=route_handle,
                stable_id=stable_id,
                safe_text=safe_text,
                route_id_prefix="semantic_trigger",
                title=row.get("title") or row.get("concept") or "semantic trigger source",
                summary=row.get("review_note") or row.get("when_to_use") or "",
                scope_labels=["semantic_trigger"],
                scope_bucket="semantic_trigger",
                matched_cue_family="semantic_trigger_source",
                route_topic="semantic_trigger",
                route_label="semantic_trigger source route",
                reason_codes=["semantic_trigger_source_ref", "source_reopen_required"],
                source_chain_role="semantic_trigger_source",
            )
            if route:
                routes.append(route)
                if len(routes) >= max_routes:
                    break
        if len(routes) >= max_routes:
            break
    return routes, {
        "trigger_source_routes": len(routes),
        "source_backed_trigger_match_count": source_matches,
        "source_free_trigger_match_count": source_free_matches,
        "seed_trigger_match_count": source_free_matches,
        "seed_triggers_are_query_scent_only": source_free_matches > 0,
        "matched_trigger_terms": list(dict.fromkeys(matched_terms))[:8],
        "matched_trigger_ids": list(dict.fromkeys(matched_trigger_ids))[:8],
    }


__all__ = [
    "dedupe_routes_by_source_ref",
    "registry_clean_source_routes",
    "reviewed_semantic_seed_path",
    "route_from_registry_match",
    "route_from_source_ref",
    "semantic_trigger_source_routes",
    "source_ref_exists",
    "source_ref_from_registry_match",
]
