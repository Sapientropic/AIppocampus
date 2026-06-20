"""Foreground-safe registry-wide source search projection."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.core import compact_text
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.search_terms import search_query_terms

DEFAULT_PUBLIC_SNIPPET_CHARS = 260


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def add_registry_search_arguments(parser: Any) -> None:
    parser.add_argument(
        "--all",
        "--registry",
        action="store_true",
        dest="registry_search",
        help="Search registered clean-source/index entries across the local registry.",
    )
    parser.add_argument(
        "--registry-dir",
        default=None,
        help="Registry directory for --all. Defaults to the configured AIppocampus registry.",
    )
    parser.add_argument(
        "--search-budget",
        choices=("default", "deep"),
        default="default",
        help="Registry search budget for --all; deep is a local diagnostic mode.",
    )


def _registry_entry_ref(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "thread_key": entry.get("thread_key"),
            "title": compact_text(str(entry.get("title") or ""), 90),
            "workspace_name": compact_text(str(entry.get("workspace_name") or ""), 90),
            "source_provider": entry.get("source_provider"),
        }.items()
        if value not in (None, "", [])
    }


def _registry_match(
    *,
    entry: Mapping[str, Any],
    hit: Mapping[str, Any],
    include_paths: bool,
) -> dict[str, Any]:
    paths = entry.get("paths") if isinstance(entry.get("paths"), Mapping) else {}
    thread_key = str(entry.get("thread_key") or "").strip()
    match = {
        "thread": _registry_entry_ref(entry),
        "source": hit.get("source"),
        "message_id": hit.get("message_id") or hit.get("id"),
        "turn_id": hit.get("turn_id"),
        "line": hit.get("line"),
        "role": hit.get("role"),
        "phase": hit.get("phase") or "",
        "turn_index": hit.get("turn_index"),
        "is_final": bool(hit.get("is_final")),
        "scope_labels": hit.get("scope_labels") or [],
        "semantic_scope_labels": hit.get("semantic_scope_labels") or [],
        "score": hit.get("rank_score") or hit.get("score"),
        "snippet": compact_text(str(hit.get("snippet") or ""), DEFAULT_PUBLIC_SNIPPET_CHARS),
        "search_noise": bool(hit.get("search_noise")),
        "noise_reason": hit.get("noise_reason"),
        "source_route": {
            "kind": "registry_clean_source_hit",
            "thread_key": thread_key,
            "line": hit.get("line"),
            "message_id": hit.get("message_id") or hit.get("id"),
            "boundary": "reopen_source_before_quoting_or_strong_claims",
        },
        "reopen_command": f'aippocampus registry show "{thread_key}" --json --redact-paths'
        if thread_key
        else None,
    }
    if include_paths:
        match["local_diagnostic"] = {
            "workspace": paths.get("workspace"),
            "clean_source_messages_jsonl": paths.get("clean_source_messages_jsonl"),
            "sqlite": paths.get("sqlite"),
        }
    return {key: value for key, value in match.items() if value not in (None, "", [], {})}


def _registry_search_actions(
    *,
    query: str,
    has_matches: bool,
    first_match: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if has_matches and first_match:
        command = str(first_match.get("reopen_command") or "").strip()
        actions = [
            foreground_shell_action(
                action_id="inspect_registry_search_thread",
                label="Inspect the first registry search route",
                command=command,
                why=(
                    "Registry search found capped snippets; inspect the selected "
                    "thread route before quoting or making strong claims."
                ),
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claim",
            ),
            foreground_template_action(
                action_id="diagnostic_registry_search_with_paths",
                label="Rerun registry search with local paths",
                command_template='aippocampus search --all "{exact_phrase}" --include-paths --json',
                requires=["exact_phrase"],
                why="Local diagnostic opt-in for finding the exact clean-source artifact.",
                mutation_risk="read_only",
                claim_boundary="local_paths_are_operator_diagnostics",
            ),
        ]
        return [
            action for action in actions if action.get("command") or action.get("command_template")
        ]
    return [
        foreground_template_action(
            action_id="refine_registry_exact_search",
            label="Refine registry exact search",
            command_template='aippocampus search --all "{distinctive_phrase}" --json',
            requires=["distinctive_phrase"],
            why="No registry snippet matched; try a more distinctive phrase or term set.",
            mutation_risk="read_only",
            claim_boundary="search_miss_is_not_absence_of_memory",
        ),
        foreground_template_action(
            action_id="recall_before_exact_search",
            label="Use recall for vague continuity cues",
            command_template='aippocampus agent recall "{cue}" --json',
            requires=["cue"],
            why="Use recall when the user remembers the situation but not exact wording.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        ),
        foreground_shell_action(
            action_id="check_registered_sources",
            label="Check registered source status",
            command="aippocampus onboard --provider auto --status --json",
            why="Use this if the expected old source may not be registered locally.",
            mutation_risk="read_only",
            claim_boundary="host_status_not_source_evidence",
        ),
    ]


def search_registry_sources(
    patterns: list[str],
    *,
    registry_dir: str | Path | None = None,
    limit: int = 10,
    per_thread_limit: int = 3,
    include_paths: bool = False,
    search_budget: str = "default",
) -> dict[str, Any]:
    """Search registered clean-source/index entries without exposing raw paths by default."""

    from aippocampus_runtime.registry.search import (
        REGISTRY_SEARCH_DEEP_BUDGET,
        deep_search_entry_result,
    )
    from aippocampus_runtime.registry.store import load_registry, registry_paths

    registry_root = Path(registry_dir).resolve() if registry_dir else None
    registry_json, _ = registry_paths(registry_root)
    registry_payload = load_registry(registry_json)
    terms = search_query_terms(patterns)
    budget = REGISTRY_SEARCH_DEEP_BUDGET if search_budget == "deep" else None
    matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    searched_entry_count = 0
    unavailable_source_count = 0

    for entry in registry_payload.get("threads") or []:
        if not isinstance(entry, Mapping):
            continue
        searched_entry_count += 1
        result = deep_search_entry_result(
            dict(entry),
            terms,
            max_hits=per_thread_limit,
            search_budget=budget,
        )
        entry_warnings = []
        for warning in result.get("warnings") or []:
            item = dict(warning) if isinstance(warning, Mapping) else {"message": str(warning)}
            item["thread_key"] = entry.get("thread_key")
            entry_warnings.append(item)
        if entry_warnings:
            warnings.extend(entry_warnings)
            unavailable_source_count += 1
        for hit in result.get("hits") or []:
            if isinstance(hit, Mapping):
                matches.append(
                    _registry_match(
                        entry=entry,
                        hit=hit,
                        include_paths=include_paths,
                    )
                )

    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") else 0,
            -as_float(item.get("score")),
            str((item.get("thread") or {}).get("thread_key") or ""),
            as_int(item.get("line")),
        )
    )
    matches = matches[:limit]
    query_text = " ".join(str(pattern) for pattern in patterns).strip()
    actions = _registry_search_actions(
        query=query_text,
        has_matches=bool(matches),
        first_match=matches[0] if matches else None,
    )
    payload: dict[str, Any] = {
        "kind": "aippocampus_registry_source_search",
        "ok": bool(matches),
        "status": "ok" if matches else "no_matches",
        "search_scope": "registered_clean_source_and_indexes",
        "scope_description": (
            "registered clean-source/index entries across the local registry; "
            "a miss is not proof that no memory exists"
        ),
        "registry": str(registry_json),
        "query_text": query_text,
        "query_terms": terms,
        "matches": matches,
        "match_count": len(matches),
        "searched_entry_count": searched_entry_count,
        "unavailable_source_count": unavailable_source_count,
        "warnings": warnings,
        "output_boundary": (
            "local_private_source_routes_with_paths"
            if include_paths
            else "foreground_safe_registry_source_routes"
        ),
        "source_boundary": {
            "authority": "bounded_evidence" if matches else "direction_only",
            "registry_wide_search": True,
            "source_backed_claim_allowed": bool(matches),
            "source_reopen_required_before_claim": True,
            "search_miss_is_not_absence_of_memory": not bool(matches),
        },
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_source_snippets_emitted": False,
            "capped_source_snippets_emitted": bool(matches),
            "full_session_metadata_emitted": False,
        },
    }
    payload.update(
        canonical_foreground_action_fields(
            actions[0] if actions else None,
            safe_next_actions=actions,
        )
    )
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))


def run_registry_search_cli(args: Any, render_human_search_result: Any) -> int:
    result = search_registry_sources(
        list(args.patterns),
        registry_dir=args.registry_dir,
        limit=args.max,
        include_paths=bool(args.include_paths),
        search_budget=args.search_budget,
    )
    if args.json_output:
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_human_search_result(result))
    return 0 if result["matches"] else 1
