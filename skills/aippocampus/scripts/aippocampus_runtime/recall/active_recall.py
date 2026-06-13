#!/usr/bin/env python3
"""Decide whether a long Codex thread should search its external memory."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.health import health_report
from aippocampus_runtime.recall.active_recall_lock import (
    default_active_recall_lock_path,
    find_recall_lock,
    read_recall_lock,
    registry_freshness_fingerprint,
    reopen_lock_sources,
    start_or_update_recall_lock,
    summarize_lock_roi,
)
from aippocampus_runtime.recall.ambient_cards import ambient_recall_from_decision
from aippocampus_runtime.recall.continuity_domains import (
    SNAPSHOT_DIR_NAME,
    default_continuity_domains_latest_path,
    load_continuity_domains_snapshot,
)
from aippocampus_runtime.recall.continuity_route_projection import (
    active_continuity_route_projection,
)
from aippocampus_runtime.recall.life_cues import (
    life_wide_recall_terms,
    profile_recall_terms,
)
from aippocampus_runtime.recall.retrieval import (
    active_recall_decision,
    expanded_terms_from_anchors,
    match_anchors,
    split_query_terms,
    unique_preserve,
)
from aippocampus_runtime.recall.rollout_search import RolloutSearchOptions, search_rollout_payload
from aippocampus_runtime.recall.segment_search import SegmentSearchOptions, search_segments_payload
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.source.agent_self_notes import (
    default_agent_self_notes_path,
    load_agent_self_notes,
    public_agent_self_note_surface,
    search_agent_self_notes,
)
from aippocampus_runtime.source_shape import (
    apply_source_shape_priority_to_active_recall_context,
    load_source_shape_diagnostics,
)
from aippocampus_runtime.subconscious.candidate_router import (
    default_working_memory_path,
    load_working_memory,
    match_working_memory,
    strip_for_hook,
)


def read_prompt(args: argparse.Namespace) -> str:
    parts = list(args.prompt or [])
    if args.stdin:
        parts.append(sys.stdin.read())
    return " ".join(parts).strip()


def resolve_anchor_path(cwd: Path, anchors: str) -> Path:
    path = Path(anchors)
    if not path.is_absolute():
        path = cwd / path
    return path


def search_terms_from_query(query_terms: list[str], prompt: str) -> list[str]:
    noise = {
        "还记得",
        "记得",
        "之前",
        "前面",
        "刚才",
        "上次",
        "那个",
        "这个",
        "那篇",
        "这篇",
        "我说过",
        "你说过",
        "之前那个",
        "的说法",
        "那段有关系",
    }
    out: list[str] = []
    for term in query_terms:
        low = term.casefold().strip()
        if low in noise:
            continue
        # Long prompts with deictic words are useful for deciding to recall but
        # poor FTS clauses. Keep their extracted content terms instead.
        if len(term) > 20 and any(
            marker in prompt for marker in ("之前", "还记得", "那个", "这个", "那篇", "这篇")
        ):
            continue
        out.append(term)
    return out or [prompt]


def active_recall_query_terms(prompt: str) -> list[str]:
    return unique_preserve(
        split_query_terms([prompt])
        + profile_recall_terms(prompt)
        + life_wide_recall_terms(prompt),
        limit=32,
    )


def _registry_path_from_args(args: argparse.Namespace) -> Path | None:
    if getattr(args, "registry", None):
        return Path(args.registry).resolve()
    registry_dir = Path(args.registry_dir).resolve() if getattr(args, "registry_dir", None) else None
    if registry_dir is not None:
        return registry_paths(registry_dir)[0]
    return registry_paths(None)[0]


def _lock_path_from_args(args: argparse.Namespace, registry_path: Path | None) -> Path:
    if getattr(args, "lock_path", None):
        return Path(args.lock_path).resolve()
    return default_active_recall_lock_path(
        registry_path=registry_path,
        registry_dir=Path(args.registry_dir).resolve() if getattr(args, "registry_dir", None) else None,
    )


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _lock_probe_payload(*, mode: str, lock: dict[str, Any]) -> dict[str, Any]:
    state = str(lock.get("state") or "missing")
    if state == "ready":
        suggested_next = "reopen_source"
    elif state == "pending":
        suggested_next = "wait_or_probe_lock"
    else:
        suggested_next = "start_lock"
    return {
        "mode": mode,
        "support_level": "scent",
        "lock": {
            "state": state,
            "lock_id": lock.get("lock_id"),
            "lock_version": _safe_nonnegative_int(lock.get("lock_version")),
            "enrichment_generation": _safe_nonnegative_int(lock.get("enrichment_generation")),
            "state_transition": lock.get("state_transition"),
            "route_handle": True,
            "candidate_ref_count": _safe_nonnegative_int(lock.get("candidate_ref_count")),
            "reopenable_ref_count": _safe_nonnegative_int(lock.get("reopenable_ref_count")),
        },
        "candidate_refs": lock.get("candidate_refs") or [],
        "query_aliases": lock.get("query_aliases") or [],
        "route_reasons": lock.get("route_reasons") or [],
        "conflict_flags": lock.get("conflict_flags") or [],
        "source_reopen_required": True,
        "suggested_next": suggested_next,
        "diagnostics": lock.get("diagnostics") or {},
        "freshness_vector": lock.get("freshness_vector") or {},
        "consumer_metrics": lock.get("consumer_metrics") or {},
        "enrichment_timing": lock.get("enrichment_timing") or {},
        "roi_metrics": lock.get("roi_metrics") or {},
        "source_boundary": {
            "lock_is_navigation_only": True,
            "probe_read_returns_no_facts": True,
            "source_backed_claims_require_reopen": True,
        },
    }


def active_recall_probe(
    *,
    prompt: str,
    cwd: Path,
    lock_path: Path,
    registry_path: Path | None,
    thread_id: str | None,
    topic_epoch: str | None,
    use_lock: bool,
) -> dict[str, Any]:
    query_terms = active_recall_query_terms(prompt)
    lock = find_recall_lock(
        lock_path,
        prompt=prompt,
        thread_id=thread_id,
        workspace=cwd,
        topic_epoch=topic_epoch,
        registry_path=registry_path,
        query_aliases=query_terms,
    )
    if use_lock and lock.get("state") in {"missing", "expired", "failed"}:
        lock = start_or_update_recall_lock(
            lock_path,
            prompt=prompt,
            thread_id=thread_id,
            workspace=cwd,
            topic_epoch=topic_epoch,
            registry_path=registry_path,
            query_aliases=query_terms,
            route_reasons=["active_recall_probe_started_lock"],
            diagnostics={
                "cold_model_call": False,
                "fast_scout_used": False,
                "thinking_enrichment_pending": True,
            },
            state="pending",
    )
    payload = _lock_probe_payload(mode="probe", lock=lock)
    payload["registry_freshness_fingerprint"] = registry_freshness_fingerprint(registry_path)
    return payload


def active_recall_read_lock(
    *,
    lock_path: Path,
    lock_id: str,
    topic_epoch: str | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    registry_fp = registry_freshness_fingerprint(registry_path) if registry_path else None
    lock = read_recall_lock(
        lock_path,
        lock_id,
        topic_epoch=topic_epoch,
        registry_freshness_fingerprint=registry_fp,
    )
    return _lock_probe_payload(mode="read", lock=lock)


def active_recall_reopen_lock(
    *,
    lock_path: Path,
    lock_id: str,
    registry_path: Path | None,
    max_matches: int,
    topic_epoch: str | None = None,
    expected_lock_version: int | None = None,
) -> dict[str, Any]:
    return reopen_lock_sources(
        lock_path,
        lock_id=lock_id,
        registry_path=registry_path,
        topic_epoch=topic_epoch,
        expected_lock_version=expected_lock_version,
        max_matches=max_matches,
    )


def active_recall_lock_metrics(*, lock_path: Path) -> dict[str, Any]:
    return summarize_lock_roi(lock_path)


def _safe_route_ref(ref: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "thread_key",
        "source_id",
        "message_id",
        "turn_id",
        "turn_index",
        "line",
        "phase",
        "title",
    )
    route: dict[str, Any] = {}
    for key in allowed:
        value = ref.get(key)
        if value in (None, "", []):
            continue
        route[key] = _public_text(value, chars=180) if isinstance(value, str) else value
    return route


def _public_text(value: Any, *, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized or "<redacted:sensitive-text>", chars)


def _source_reopen_routes_from_surfaces(
    surfaces: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for surface in surfaces:
        for ref in surface.get("source_refs") or []:
            if not isinstance(ref, dict):
                continue
            route = _safe_route_ref(ref)
            if not route:
                continue
            route["source_reopen_required_before_claim"] = True
            marker = tuple(sorted((key, str(value)) for key, value in route.items()))
            if marker in seen:
                continue
            seen.add(marker)
            routes.append(route)
            if len(routes) >= limit:
                return routes
    return routes


def _public_working_memory_cards(rows: list[dict[str, Any]], *, max_cards: int) -> list[dict[str, Any]]:
    if not rows:
        return []
    payload = ambient_recall_from_decision(
        {
            "decision": "scent",
            "confidence": "medium",
            "evidence": [],
            "working_memory": strip_for_hook(rows),
            "cognitive_map": [],
            "candidates": [],
        },
        max_cards=max_cards,
    )
    cards: list[dict[str, Any]] = []
    rows_by_ref = {
        str(row.get("candidate_key") or row.get("title") or ""): row
        for row in rows
    }
    for card in payload.get("cards") or []:
        if not isinstance(card, dict):
            continue
        public = dict(card)
        source_key = str(public.get("candidate_key") or "")
        if not source_key:
            source_key = str(public.get("theme") or "")
        source_row = rows_by_ref.get(source_key) or {}
        if source_row.get("candidate_type"):
            public["candidate_type"] = source_row.get("candidate_type")
        public["active_recall_surface"] = "working_memory"
        public["retrieval_role"] = "working_continuity_brief"
        public["source_refs"] = [
            route for ref in public.get("source_refs") or [] if (route := _safe_route_ref(ref))
        ][:4]
        cards.append(public)
    return cards


def _continuity_domain_clean_source_dir(
    *,
    cwd: Path,
    snapshot_path: Path,
) -> Path | None:
    if snapshot_path.parent.name == SNAPSHOT_DIR_NAME:
        candidate = snapshot_path.parent.parent / "clean-source"
        if (candidate / "messages.jsonl").exists():
            return candidate
    legacy = cwd / ".aippocampus" / "clean-source"
    if (legacy / "messages.jsonl").exists():
        return legacy
    return None


def active_recall_context(
    *,
    prompt: str,
    cwd: Path,
    registry_path: Path | None = None,
    agent_self_notes_path: Path | None = None,
    working_memory_path: Path | None = None,
    continuity_domains_snapshot_path: Path | None = None,
    source_shape_diagnostics: list[dict[str, Any]] | None = None,
    max_matches: int = 4,
) -> dict[str, Any]:
    """Return explicit agent-initiated continuity context.

    This path is intentionally separate from prompt-time hooks: it may surface
    direction-only atmosphere rows when the agent asks to remember, but every
    source-backed or exact claim still has to reopen clean source through the
    returned route refs.
    """

    cwd_path = Path(cwd)
    notes_path = agent_self_notes_path or default_agent_self_notes_path(registry_path)
    self_note_matches = (
        search_agent_self_notes(
            prompt,
            load_agent_self_notes(notes_path),
            limit=max_matches,
        )
        if notes_path.exists()
        else []
    )
    memory_atmosphere = [public_agent_self_note_surface(row) for row in self_note_matches]
    wm_path = working_memory_path or default_working_memory_path(registry_path=registry_path)
    working_rows = (
        match_working_memory(
            prompt,
            load_working_memory(wm_path),
            limit=max_matches,
        )
        if wm_path.exists()
        else []
    )
    working_brief = _public_working_memory_cards(working_rows, max_cards=max_matches)
    domain_snapshot_path = continuity_domains_snapshot_path or default_continuity_domains_latest_path(cwd_path)
    domain_snapshot = load_continuity_domains_snapshot(domain_snapshot_path)
    domain_clean_source_dir = _continuity_domain_clean_source_dir(
        cwd=cwd_path,
        snapshot_path=domain_snapshot_path,
    )
    continuity_projection = active_continuity_route_projection(
        prompt=prompt,
        snapshot_path=domain_snapshot_path,
        snapshot=domain_snapshot,
        clean_source_dir=domain_clean_source_dir,
        max_matches=max_matches,
    )
    domain_pointers = continuity_projection["domain_pointers"]
    domain_brief = continuity_projection["domain_brief"]
    pathlet_brief = continuity_projection["pathlet_brief"]
    routes = _source_reopen_routes_from_surfaces(
        [*self_note_matches, *working_rows, *domain_pointers, *continuity_projection["pathlet_pointers"]],
        limit=max_matches,
    )
    for pointer in domain_pointers:
        handle = ((pointer.get("reopen_plan") or {}).get("arguments") or {}).get("handle")
        if isinstance(handle, dict):
            routes.append(
                {
                    "kind": "continuity_domain",
                    "domain_id": pointer.get("domain_id"),
                    "handle": handle,
                    "source_reopen_required_before_claim": True,
                    "recommended_tool": "recall_deepen",
                }
            )
    routes.extend(continuity_projection["pathlet_source_reopen_routes"])
    dream_count = sum(1 for row in working_rows if row.get("candidate_type") == "dream_hypothesis")
    route_status = continuity_projection["continuity_route_status"]
    fresh_thread_route_packet = continuity_projection["fresh_thread_route_packet"]
    suggested_next = (
        "reopen_source"
        if routes
        else "publish_continuity_domains_snapshot"
        if route_status["snapshot_status"] in {"missing", "unreadable"}
        else "search_clean_source"
    )
    result = {
        "kind": "aippocampus_agent_initiated_recall_context",
        "schema_version": 1,
        "decision": "context" if memory_atmosphere or working_brief or domain_brief or pathlet_brief or routes else "empty",
        "agent_initiated_recall": True,
        "memory_atmosphere": memory_atmosphere,
        "working_continuity_brief": [*domain_brief, *pathlet_brief, *working_brief],
        "source_reopen_routes": routes,
        "fresh_thread_route_packet": fresh_thread_route_packet,
        "continuity_route_status": route_status,
        "surface_counts": {
            "agent_self_notes": len(memory_atmosphere),
            "working_memory": len(working_brief),
            "continuity_domains": len(domain_brief),
            "continuity_pathlets": len(pathlet_brief),
            "dream": dream_count,
            "atmosphere": len(memory_atmosphere),
        },
        "source_boundary": {
            "passive_hook_required": False,
            "hook_auto_injection_unchanged": True,
            "direction_only_is_not_evidence": True,
            "source_reopen_required_for_facts": True,
            "raw_prompt_serialized": False,
            "local_paths_serialized": False,
        },
        "suggested_next": suggested_next,
    }
    return apply_source_shape_priority_to_active_recall_context(result, source_shape_diagnostics)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="*", help="Current user message or task description.")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read prompt text from stdin and append it to positional text.",
    )
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument("--search", choices=["auto", "always", "never"], default="auto")
    parser.add_argument(
        "--mode",
        choices=["legacy", "probe", "read", "reopen", "metrics", "context"],
        default="legacy",
        help=(
            "legacy keeps the old search decision flow; context returns explicit "
            "agent-initiated direction-only route material; probe/read expose "
            "navigation-only locks; reopen opens clean source by lock id; metrics "
            "reports public-safe aggregate lock ROI."
        ),
    )
    parser.add_argument("--agent-self-notes")
    parser.add_argument("--working-memory")
    parser.add_argument("--continuity-domains-snapshot")
    parser.add_argument(
        "--source-shape-diagnostics",
        help="Optional JSON/JSONL source-shape descriptors or runtime_recheck_event rows.",
    )
    parser.add_argument("--use-lock", action="store_true", dest="use_lock")
    parser.add_argument("--use-background-lock", action="store_true", dest="use_lock")
    parser.add_argument("--lock-id")
    parser.add_argument("--lock-path")
    parser.add_argument("--thread-id")
    parser.add_argument("--topic-epoch")
    parser.add_argument("--expected-lock-version", type=int)
    parser.add_argument("--max", type=int, default=8)
    parser.add_argument("--context", type=int, default=1)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    prompt = read_prompt(args)
    registry_path = _registry_path_from_args(args)
    lock_path = _lock_path_from_args(args, registry_path)
    if args.mode == "metrics":
        result = active_recall_lock_metrics(lock_path=lock_path)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"locks: {result.get('lock_count', 0)}")
            print(f"pulls: {result.get('lock_pull_count', 0)}")
            print(f"reopens: {result.get('lock_reopen_attempt_count', 0)}")
            print(f"source hits: {result.get('source_backed_hit_count', 0)}")
        return 0

    if args.mode == "reopen":
        if not args.lock_id:
            raise SystemExit("active_recall.py --mode reopen requires --lock-id")
        result = active_recall_reopen_lock(
            lock_path=lock_path,
            lock_id=args.lock_id,
            registry_path=registry_path,
            topic_epoch=args.topic_epoch,
            expected_lock_version=args.expected_lock_version,
            max_matches=args.max,
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"reopen: {'ok' if result.get('ok') else 'unavailable'}")
            for match in result.get("matches") or []:
                print(
                    f"- {match.get('thread_key')} line {match.get('line')}: "
                    f"{match.get('text')}"
                )
        return 0 if result.get("ok") else 1

    if args.mode == "read":
        if not args.lock_id:
            raise SystemExit("active_recall.py --mode read requires --lock-id")
        result = active_recall_read_lock(
            lock_path=lock_path,
            lock_id=args.lock_id,
            topic_epoch=args.topic_epoch,
            registry_path=registry_path,
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            lock = result.get("lock") or {}
            print(f"lock: {lock.get('state')} {lock.get('lock_id') or ''}".strip())
            print(f"suggested next: {result.get('suggested_next')}")
        return 0

    if not prompt:
        raise SystemExit("active_recall.py requires prompt text or --stdin")
    if args.mode == "context":
        result = active_recall_context(
            prompt=prompt,
            cwd=cwd,
            registry_path=registry_path,
            agent_self_notes_path=Path(args.agent_self_notes).resolve()
            if args.agent_self_notes
            else None,
            working_memory_path=Path(args.working_memory).resolve()
            if args.working_memory
            else None,
            continuity_domains_snapshot_path=Path(args.continuity_domains_snapshot).resolve()
            if args.continuity_domains_snapshot
            else None,
            source_shape_diagnostics=load_source_shape_diagnostics(args.source_shape_diagnostics)
            if args.source_shape_diagnostics
            else None,
            max_matches=args.max,
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"active recall context: {result.get('decision')}")
            for row in result.get("memory_atmosphere") or []:
                print(f"- [direction_only] {row.get('note_text')}")
        return 0
    if args.mode == "probe":
        result = active_recall_probe(
            prompt=prompt,
            cwd=cwd,
            lock_path=lock_path,
            registry_path=registry_path,
            thread_id=args.thread_id,
            topic_epoch=args.topic_epoch,
            use_lock=bool(args.use_lock),
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            lock = result.get("lock") or {}
            print(f"lock: {lock.get('state')} {lock.get('lock_id') or ''}".strip())
            print(f"suggested next: {result.get('suggested_next')}")
        return 0

    health = health_report(cwd)
    anchor_path = resolve_anchor_path(cwd, args.anchors)
    query_terms = active_recall_query_terms(prompt)
    anchors = match_anchors(anchor_path, query_terms) if anchor_path.exists() else []
    expanded_terms = expanded_terms_from_anchors(query_terms, anchors, limit=24)
    decision = active_recall_decision(prompt, anchors, health)

    should_search = args.search == "always" or (
        args.search == "auto" and decision["decision"] == "search"
    )
    search_payload = None
    if should_search:
        # Pass the user's extracted clues to search_rollout and let that command
        # do its own anchor expansion once. Passing already-expanded anchor terms
        # here caused broad anchors such as "vault" to be expanded twice, which
        # made maintenance/dashboard hits crowd out the original remembered turn.
        search_terms = search_terms_from_query(query_terms, prompt)[:10]
        segments = health.get("segments") or {}
        use_segments = bool(segments.get("exists")) or bool(segments.get("needed"))
        if use_segments:
            search_payload = search_segments_payload(
                SegmentSearchOptions(
                    patterns=search_terms,
                    cwd=cwd,
                    mode="hybrid",
                    max_results=args.max,
                    context=args.context,
                    # Foreground recall must never turn a user prompt into a
                    # segment rebuild. Missing or stale shards are reported as
                    # structured availability and owned by maintenance hooks.
                    build_segments=False,
                )
            )
        else:
            search_payload = search_rollout_payload(
                RolloutSearchOptions(
                    patterns=search_terms,
                    cwd=cwd,
                    build_index=True,
                    mode="hybrid",
                    max_results=args.max,
                    context=args.context,
                )
            )

    result = {
        "prompt": prompt,
        "decision": decision,
        "query_terms": query_terms,
        "suggested_terms": expanded_terms,
        "matched_anchors": anchors,
        "health_summary": {
            "status": health.get("status"),
            "index_stale": health.get("index", {}).get("stale"),
            "segments": health.get("segments"),
            "checkpoint_due": health.get("checkpoint", {}).get("due"),
            "graphify_stale": health.get("graphify", {}).get("stale"),
            "recommended_actions": health.get("recommended_actions", []),
        },
        "searched": bool(search_payload),
        "search": search_payload,
    }

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"decision: {decision['decision']} (score={decision['score']}, confidence={decision['confidence']})"
        )
        for reason in decision["reasons"]:
            print(f"- {reason}")
        print(f"suggested terms: {', '.join(expanded_terms[:12]) or '(none)'}")
        if search_payload:
            print("\nsearch hits:")
            for hit in search_payload.get("matches", [])[: args.max]:
                print(
                    f"- score {hit.get('score')} | line {hit.get('line')} | {hit.get('role')}: {hit.get('snippet')}"
                )
        else:
            print("search: skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
