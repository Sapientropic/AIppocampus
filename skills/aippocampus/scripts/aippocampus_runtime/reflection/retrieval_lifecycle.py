#!/usr/bin/env python3
"""Append-only retrieval lifecycle diagnostics.

This module records that source-routed material was retrieved, reopened, or
later acted on. It deliberately stops before reconsolidation: repeated
retrieval is an observation, not a truth update, and these rows must never
rewrite clean source, raw rollout, or formal memory by themselves.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
    safe_path_name,
    sanitize_external_model_text,
    stable_text_fingerprint,
)
from aippocampus_runtime.question.source_refs import compact_source_refs, source_ref_key
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-retrieval-lifecycle-v1"

RETRIEVAL_KIND = "retrieval_lifecycle_event"
OUTCOME_KIND = "retrieval_lifecycle_outcome_event"
RECONSOLIDATION_CANDIDATE_KIND = "retrieval_reconsolidation_candidate"
EVENT_KINDS = {RETRIEVAL_KIND, OUTCOME_KIND, RECONSOLIDATION_CANDIDATE_KIND}

RETRIEVAL_ROUTES = {
    "ambient_scent",
    "prompt_hook_scent",
    "prompt_hook_evidence",
    "active_recall",
    "active_recall_context",
    "active_recall_lock",
    "recall_context",
    "recall_deepen",
    "deepen",
    "source_reopen",
    "mcp_tool",
    "source_court_reopen",
}
ACTION_GRAMMARS = {
    "direction_only",
    "direction_with_ref",
    "reopenable_route",
    "bounded_evidence",
    "source_open",
    "ignore_or_blocked",
}
OUTCOME_CATEGORIES = {
    "opened",
    "ignored",
    "corrected",
    "conflicted",
    "contradicted",
    "pinned",
    "refuted",
    "superseded",
    "blocked",
    "stale",
    "still_current",
    "unclear",
}
RECONSOLIDATION_OUTCOME_CATEGORIES = {
    "conflicted",
    "contradicted",
    "corrected",
    "pinned",
    "refuted",
    "stale",
    "still_current",
    "superseded",
}
CONFLICT_OUTCOME_CATEGORIES = {
    "conflicted",
    "contradicted",
    "corrected",
    "refuted",
    "stale",
    "superseded",
}
USED_OUTCOME_CATEGORIES = {"opened", "pinned", "still_current"}

LOCAL_PATH_RE = re.compile(
    r"(?i)(^[a-z]:[\\/])|(^/(Users|home|root|tmp|var|mnt|Volumes|private)/)|(^~[\\/])"
)
FAKE_TEST_SECRET_RE = re.compile(r"FAKE_TEST_(SECRET|PASSWORD|TOKEN|KEY)_VALUE_[A-Za-z0-9_:-]+")


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return stable_text_fingerprint(
        raw,
        namespace="retrieval-lifecycle-id",
        prefix=prefix,
        length=length,
    )


def _sanitize_text(
    value: Any,
    *,
    max_chars: int,
    policies: list[dict[str, Any]],
) -> str:
    sanitized, policy = sanitize_external_model_text(str(value or ""))
    sanitized = FAKE_TEST_SECRET_RE.sub("<redacted:test-secret>", sanitized)
    policies.append(policy)
    return compact_text(sanitized, max_chars)


def _privacy_scan(policies: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    redaction_types: list[str] = []
    redaction_count = 0
    hard_block = False
    for policy in policies:
        redaction_count += int(policy.get("redaction_count") or 0)
        hard_block = hard_block or bool(policy.get("hard_block"))
        redaction_types.extend(str(item) for item in policy.get("redaction_types") or [])
    return {
        "raw_text_stored": False,
        "raw_prompt_stored": False,
        "raw_source_text_stored": False,
        "raw_tool_payloads_stored": False,
        "local_paths_stored": False,
        "secrets_stored": False,
        "redacted": bool(redaction_count or hard_block),
        "redaction_count": redaction_count,
        "redaction_types": unique_preserve(redaction_types, limit=8),
        "hard_block": hard_block,
    }


def _workspace_fields(workspace: str | None, policies: list[dict[str, Any]]) -> dict[str, Any]:
    raw = str(workspace or "").strip()
    if not raw:
        return {"workspace": ""}
    sanitized = _sanitize_text(raw, max_chars=160, policies=policies)
    path_like = bool(LOCAL_PATH_RE.search(raw) or "\\" in raw or "/" in raw)
    if not path_like:
        return {"workspace": sanitized}
    normalized = raw.replace("\\", "/").rstrip("/")
    label = safe_path_name(normalized.rsplit("/", 1)[-1] or "workspace", "workspace")
    return {
        "workspace": label,
        "workspace_sha1": stable_text_fingerprint(
            normalized.casefold(),
            namespace="retrieval-lifecycle-workspace",
            length=16,
        ),
        "workspace_privacy": "local_path_redacted_to_label_and_hash",
    }


def sanitize_source_refs(
    values: Any,
    *,
    policies: list[dict[str, Any]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ref in compact_source_refs(values, limit=limit):
        clean: dict[str, Any] = {}
        for key, value in ref.items():
            if isinstance(value, str):
                clean[key] = _sanitize_text(value, max_chars=220, policies=policies)
            else:
                clean[key] = value
        out.append(clean)
    return out


def source_key_for_refs(
    refs: Sequence[Mapping[str, Any]] | None = None,
    *,
    fallback_key: str | None = None,
) -> str:
    keys = [source_ref_key(ref) for ref in refs or [] if isinstance(ref, Mapping)]
    payload: Any = keys if keys else str(fallback_key or "")
    if not payload:
        raise ValueError("retrieval lifecycle rows require source_refs or source_key")
    return stable_text_fingerprint(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        namespace="retrieval-lifecycle-source",
        prefix="source",
        length=18,
    )


def _source_anchor_from_payload(item: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    refs: list[dict[str, Any]] = []
    raw_refs = item.get("source_refs") or item.get("refs") or []
    if isinstance(raw_refs, Mapping):
        raw_refs = [raw_refs]
    if isinstance(raw_refs, Sequence) and not isinstance(raw_refs, (str, bytes)):
        refs.extend(dict(ref) for ref in raw_refs if isinstance(ref, Mapping))
    direct_ref = {
        "thread_key": item.get("thread_key"),
        "message_id": item.get("message_id") or item.get("id"),
        "turn_id": item.get("turn_id"),
        "turn_index": item.get("turn_index"),
        "source_line": item.get("source_line") or item.get("line"),
        "title": item.get("title"),
        "project_label": item.get("project_label"),
    }
    def present(value: Any) -> bool:
        return value is not None and value != "" and value != []

    if any(present(value) for key, value in direct_ref.items() if key != "title"):
        refs.append({key: value for key, value in direct_ref.items() if present(value)})
    fallback = (
        item.get("source_key")
        or item.get("thread_key")
        or item.get("route_id")
        or item.get("handle")
        or item.get("lock_id")
        or item.get("title")
    )
    return refs, str(fallback) if fallback else None


def _source_confirmed(action_grammar: str, source_opened: bool) -> bool:
    return bool(source_opened and action_grammar in {"bounded_evidence", "source_open"})


def build_retrieval_event(
    *,
    thread_id: str,
    workspace: str,
    route: str,
    action_grammar: str,
    source_refs: Sequence[Mapping[str, Any]] | None = None,
    source_key: str | None = None,
    source_handle: str | None = None,
    retrieval_summary: str | None = None,
    source_opened: bool = False,
    created_at: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    if route not in RETRIEVAL_ROUTES:
        raise ValueError(f"route must be one of {', '.join(sorted(RETRIEVAL_ROUTES))}")
    if action_grammar not in ACTION_GRAMMARS:
        raise ValueError(f"action_grammar must be one of {', '.join(sorted(ACTION_GRAMMARS))}")
    policies: list[dict[str, Any]] = []
    refs = sanitize_source_refs(source_refs or [], policies=policies)
    fingerprint = source_key_for_refs(refs, fallback_key=source_key or source_handle)
    opened = bool(source_opened or action_grammar == "source_open")
    thread = _sanitize_text(thread_id, max_chars=140, policies=policies)
    summary = _sanitize_text(retrieval_summary or "", max_chars=360, policies=policies)
    handle_sha1 = (
        stable_text_fingerprint(
            str(source_handle),
            namespace="retrieval-lifecycle-handle",
            length=16,
        )
        if source_handle
        else ""
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": RETRIEVAL_KIND,
        "created_at": created_at or now_utc(),
        "prompt_version": PROMPT_VERSION,
        "event_id": event_id
        or stable_id("retr", thread, route, action_grammar, fingerprint, created_at or ""),
        "thread_id": thread,
        **_workspace_fields(workspace, policies),
        "source_key": fingerprint,
        "source_refs": refs,
        "source_handle_sha1": handle_sha1,
        "route": route,
        "action_grammar": action_grammar,
        "retrieval_summary": summary,
        "source_opened": opened,
        "source_confirmed_evidence": _source_confirmed(action_grammar, opened),
        "truth_status": "retrieval_observation_not_memory_truth",
        "status": "diagnostic",
        "source": "deterministic_retrieval_lifecycle",
        "append_only": True,
        "formal_memory_promoted": False,
        "clean_source_mutated": False,
        "raw_rollout_mutated": False,
        "review_required_before_reconsolidation": True,
    }
    payload["privacy_scan"] = _privacy_scan(policies)
    return payload


def build_outcome_event(
    *,
    retrieval_event_id: str,
    thread_id: str,
    workspace: str,
    source_refs: Sequence[Mapping[str, Any]] | None = None,
    source_key: str | None = None,
    outcome_category: str,
    outcome_summary: str | None = None,
    created_at: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    if outcome_category not in OUTCOME_CATEGORIES:
        raise ValueError(f"outcome_category must be one of {', '.join(sorted(OUTCOME_CATEGORIES))}")
    policies: list[dict[str, Any]] = []
    refs = sanitize_source_refs(source_refs or [], policies=policies)
    fingerprint = source_key_for_refs(refs, fallback_key=source_key)
    thread = _sanitize_text(thread_id, max_chars=140, policies=policies)
    retrieval_id = _sanitize_text(retrieval_event_id, max_chars=140, policies=policies)
    summary = _sanitize_text(outcome_summary or "", max_chars=360, policies=policies)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": OUTCOME_KIND,
        "created_at": created_at or now_utc(),
        "prompt_version": PROMPT_VERSION,
        "event_id": event_id
        or stable_id("retr_out", retrieval_id, outcome_category, fingerprint, created_at or ""),
        "retrieval_event_id": retrieval_id,
        "thread_id": thread,
        **_workspace_fields(workspace, policies),
        "source_key": fingerprint,
        "source_refs": refs,
        "outcome_category": outcome_category,
        "outcome_summary": summary,
        "truth_status": "post_retrieval_observation_not_memory_truth",
        "status": "diagnostic",
        "source": "deterministic_retrieval_lifecycle",
        "append_only": True,
        "formal_memory_promoted": False,
        "clean_source_mutated": False,
        "raw_rollout_mutated": False,
    }
    payload["privacy_scan"] = _privacy_scan(policies)
    return payload


def append_events(path: Path, events: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for event in events:
            if event.get("kind") not in EVENT_KINDS:
                raise ValueError(f"unsupported retrieval lifecycle event kind: {event.get('kind')}")
            fh.write(json.dumps(dict(event), ensure_ascii=False) + "\n")
            count += 1
    return count


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _empty_source_stats(source_key: str) -> dict[str, Any]:
    return {
        "source_key": source_key,
        "retrieval_count": 0,
        "last_retrieved_at": None,
        "routes": [],
        "action_grammars": [],
        "source_open_count": 0,
        "source_confirmed_evidence_count": 0,
        "outcome_categories": {},
    }


def lifecycle_projection(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stats: dict[str, dict[str, Any]] = {}
    route_sets: dict[str, list[str]] = defaultdict(list)
    grammar_sets: dict[str, list[str]] = defaultdict(list)
    outcome_counts: dict[str, Counter[str]] = defaultdict(Counter)
    retrieval_event_count = 0
    outcome_event_count = 0
    for event in events:
        source_key = str(event.get("source_key") or "")
        if not source_key:
            continue
        source_stats = stats.setdefault(source_key, _empty_source_stats(source_key))
        kind = event.get("kind")
        if kind == RETRIEVAL_KIND:
            retrieval_event_count += 1
            source_stats["retrieval_count"] += 1
            created_at = str(event.get("created_at") or "")
            if created_at and (
                source_stats["last_retrieved_at"] is None
                or created_at > str(source_stats["last_retrieved_at"])
            ):
                source_stats["last_retrieved_at"] = created_at
            route_sets[source_key].append(str(event.get("route") or ""))
            grammar_sets[source_key].append(str(event.get("action_grammar") or ""))
            if event.get("source_opened"):
                source_stats["source_open_count"] += 1
                outcome_counts[source_key]["opened"] += 1
            if event.get("source_confirmed_evidence"):
                source_stats["source_confirmed_evidence_count"] += 1
        elif kind == OUTCOME_KIND:
            outcome_event_count += 1
            category = str(event.get("outcome_category") or "unclear")
            outcome_counts[source_key][category] += 1

    sources: list[dict[str, Any]] = []
    for source_key, source_stats in stats.items():
        source_stats["routes"] = unique_preserve(route_sets[source_key], limit=12)
        source_stats["action_grammars"] = unique_preserve(grammar_sets[source_key], limit=8)
        source_stats["outcome_categories"] = dict(sorted(outcome_counts[source_key].items()))
        sources.append(source_stats)
    sources.sort(
        key=lambda item: (
            str(item.get("last_retrieved_at") or ""),
            int(item.get("retrieval_count") or 0),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "kind": "aippocampus_retrieval_lifecycle_report",
        "schema_version": SCHEMA_VERSION,
        "source_count": len(sources),
        "retrieval_event_count": retrieval_event_count,
        "outcome_event_count": outcome_event_count,
        "sources": sources,
        "privacy_boundary": {
            "public_projection_omits_source_refs": True,
            "public_projection_omits_raw_prompt": True,
            "public_projection_omits_source_text": True,
            "public_projection_omits_local_paths": True,
        },
        "cannot_claim": [
            "general_retrieval_reconsolidation_implemented",
            "formal_memory_promotion",
            "memory_correctness",
            "retrieval_count_is_not_memory_correctness",
        ],
    }


def lifecycle_report(*, events_path: Path) -> dict[str, Any]:
    return lifecycle_projection(iter_jsonl(events_path))


def events_from_prompt_recall_result(
    result: Mapping[str, Any],
    *,
    thread_id: str,
    workspace: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    evidence = [item for item in result.get("evidence") or [] if isinstance(item, Mapping)]
    if evidence:
        for item in evidence[:8]:
            refs, fallback = _source_anchor_from_payload(item)
            events.append(
                build_retrieval_event(
                    thread_id=thread_id,
                    workspace=workspace,
                    route="prompt_hook_evidence",
                    action_grammar="bounded_evidence",
                    source_refs=refs,
                    source_key=fallback,
                    retrieval_summary=item.get("summary") or item.get("snippet"),
                    source_opened=True,
                    created_at=created_at,
                )
            )
        return events

    candidates = [item for item in result.get("candidates") or [] if isinstance(item, Mapping)]
    for item in candidates[:3]:
        refs, fallback = _source_anchor_from_payload(item)
        events.append(
            build_retrieval_event(
                thread_id=thread_id,
                workspace=workspace,
                route="prompt_hook_scent",
                action_grammar="direction_only",
                source_refs=refs,
                source_key=fallback,
                retrieval_summary=item.get("title") or item.get("summary"),
                source_opened=False,
                created_at=created_at,
            )
        )
    return events


def events_from_active_recall_result(
    result: Mapping[str, Any],
    *,
    thread_id: str,
    workspace: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    kind = str(result.get("kind") or "")
    if kind == "aippocampus_agent_initiated_recall_context":
        for route in result.get("source_reopen_routes") or []:
            if not isinstance(route, Mapping):
                continue
            refs, fallback = _source_anchor_from_payload(route)
            events.append(
                build_retrieval_event(
                    thread_id=thread_id,
                    workspace=workspace,
                    route="active_recall_context",
                    action_grammar="reopenable_route",
                    source_refs=refs,
                    source_key=fallback,
                    source_opened=False,
                    created_at=created_at,
                )
            )
        return events

    matches = [item for item in result.get("matches") or [] if isinstance(item, Mapping)]
    if result.get("ok") and matches:
        for item in matches[:8]:
            refs, fallback = _source_anchor_from_payload(item)
            events.append(
                build_retrieval_event(
                    thread_id=thread_id,
                    workspace=workspace,
                    route="source_reopen",
                    action_grammar="source_open",
                    source_refs=refs,
                    source_key=fallback,
                    source_opened=True,
                    created_at=created_at,
                )
            )
        return events

    lock_obj = result.get("lock") if isinstance(result.get("lock"), Mapping) else result
    lock = lock_obj if isinstance(lock_obj, Mapping) else {}
    candidate_refs = lock.get("candidate_refs") or []
    lock_id = str(lock.get("lock_id") or "")
    for item in candidate_refs[:8]:
        if not isinstance(item, Mapping):
            continue
        refs, fallback = _source_anchor_from_payload(item)
        events.append(
            build_retrieval_event(
                thread_id=thread_id,
                workspace=workspace,
                route="active_recall_lock",
                action_grammar="reopenable_route",
                source_refs=refs,
                source_key=fallback or lock_id,
                source_handle=lock_id or None,
                source_opened=False,
                created_at=created_at,
            )
        )
    return events


def events_from_mcp_recall_result(
    tool_name: str,
    result: Mapping[str, Any],
    *,
    thread_id: str,
    workspace: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if tool_name == "recall_context":
        for route in result.get("routes") or []:
            if not isinstance(route, Mapping):
                continue
            refs, fallback = _source_anchor_from_payload(route)
            events.append(
                build_retrieval_event(
                    thread_id=thread_id,
                    workspace=workspace,
                    route="recall_context",
                    action_grammar="reopenable_route",
                    source_refs=refs,
                    source_key=fallback,
                    source_handle=str(route.get("handle") or ""),
                    source_opened=False,
                    created_at=created_at,
                )
            )
        return events

    if tool_name == "recall_deepen":
        source_opened = bool(
            result.get("support_level") == "evidence"
            or result.get("evidence_level") in {"source_backed", "source_backed_domain_brief"}
            or (result.get("source_boundary") or {}).get("clean_source_reopened")
        )
        for item in result.get("source_refs") or []:
            if not isinstance(item, Mapping):
                continue
            refs, fallback = _source_anchor_from_payload(item)
            events.append(
                build_retrieval_event(
                    thread_id=thread_id,
                    workspace=workspace,
                    route="recall_deepen",
                    action_grammar="source_open" if source_opened else "reopenable_route",
                    source_refs=refs,
                    source_key=fallback or result.get("route_id"),
                    source_opened=source_opened,
                    created_at=created_at,
                )
            )
        return events

    if tool_name == "get_turn_context":
        for item in result.get("messages") or []:
            if not isinstance(item, Mapping):
                continue
            refs, fallback = _source_anchor_from_payload(item)
            events.append(
                build_retrieval_event(
                    thread_id=thread_id,
                    workspace=workspace,
                    route="source_reopen",
                    action_grammar="source_open",
                    source_refs=refs,
                    source_key=fallback,
                    source_opened=True,
                    created_at=created_at,
                )
            )
        return events

    return events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument(
        "--reconsolidation-review",
        action="store_true",
        help="Project retrieval lifecycle rows into source-backed review candidates.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        events_path = Path(args.events_input).resolve()
        if args.reconsolidation_review:
            from aippocampus_runtime.reflection import retrieval_reconsolidation

            output_path = Path(args.output).resolve() if args.output else None
            report = retrieval_reconsolidation.run_reconsolidation_review(
                events_path=events_path,
                output_path=output_path,
                no_write=args.no_write,
            )
        else:
            report = lifecycle_report(events_path=events_path)
    except Exception as exc:
        if not args.json_output:
            raise
        report = cli_error_payload(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(report["error"]["code"])
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if args.reconsolidation_review:
            print(f"reconsolidation candidates: {report['candidate_count']}")
            print(f"wrote: {report['wrote_count']}")
        else:
            print(f"sources: {report['source_count']}")
            print(f"retrieval events: {report['retrieval_event_count']}")
            print(f"outcome events: {report['outcome_event_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
