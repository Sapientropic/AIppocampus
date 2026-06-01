#!/usr/bin/env python3
"""Decide whether a long Codex thread should search its external memory."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.health import health_report
from aippocampus_runtime.recall.active_recall_lock import (
    default_active_recall_lock_path,
    find_recall_lock,
    read_recall_lock,
    registry_freshness_fingerprint,
    reopen_lock_sources,
    start_or_update_recall_lock,
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
) -> dict[str, Any]:
    return reopen_lock_sources(
        lock_path,
        lock_id=lock_id,
        registry_path=registry_path,
        max_matches=max_matches,
    )


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
        choices=["legacy", "probe", "read", "reopen"],
        default="legacy",
        help=(
            "legacy keeps the old search decision flow; probe/read expose "
            "navigation-only locks; reopen opens clean source by lock id."
        ),
    )
    parser.add_argument("--use-lock", action="store_true", dest="use_lock")
    parser.add_argument("--use-background-lock", action="store_true", dest="use_lock")
    parser.add_argument("--lock-id")
    parser.add_argument("--lock-path")
    parser.add_argument("--thread-id")
    parser.add_argument("--topic-epoch")
    parser.add_argument("--max", type=int, default=8)
    parser.add_argument("--context", type=int, default=1)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    prompt = read_prompt(args)
    registry_path = _registry_path_from_args(args)
    lock_path = _lock_path_from_args(args, registry_path)
    if args.mode == "reopen":
        if not args.lock_id:
            raise SystemExit("active_recall.py --mode reopen requires --lock-id")
        result = active_recall_reopen_lock(
            lock_path=lock_path,
            lock_id=args.lock_id,
            registry_path=registry_path,
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
            build_segments = not segments.get("exists") or bool(segments.get("stale"))
            search_payload = search_segments_payload(
                SegmentSearchOptions(
                    patterns=search_terms,
                    cwd=cwd,
                    mode="hybrid",
                    max_results=args.max,
                    context=args.context,
                    build_segments=build_segments,
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
