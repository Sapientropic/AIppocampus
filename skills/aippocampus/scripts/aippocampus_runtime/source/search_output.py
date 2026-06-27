"""Public and human output projection for clean-source search."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_recovery_card,
    foreground_shell_action,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.core import compact_text
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.current_source_window import (
    annotate_current_search_reopen_commands,
    render_current_source_window_text,
)
from aippocampus_runtime.source.search_projection import search_foreground_authority
from aippocampus_runtime.source.search_terms import search_query_terms

DEFAULT_HUMAN_SNIPPET_CHARS = 220
DEFAULT_PUBLIC_SNIPPET_CHARS = 260


def source_label_for_match(match: dict[str, Any]) -> str:
    thread = match.get("thread")
    if isinstance(thread, Mapping):
        label = thread.get("title") or thread.get("thread_key")
        line = match.get("source_line") or match.get("line")
        if label:
            suffix = f" line {line}" if line else ""
            return compact_text(f"{label}{suffix}", 100)
    for key in ("source_ref", "source_id"):
        value = match.get(key)
        if value:
            return compact_text(str(value), 80)
    source_line = match.get("source_line") or match.get("line")
    return f"clean source line {source_line}" if source_line else "clean source"


def date_for_match(match: dict[str, Any]) -> str:
    timestamp = str(match.get("timestamp") or "").strip()
    return timestamp[:10] if timestamp else ""


def turn_for_match(match: dict[str, Any]) -> str:
    for key in ("turn_index", "turn_id"):
        value = match.get(key)
        if value is not None and str(value).strip():
            return f"turn {value}"
    source_line = match.get("source_line") or match.get("line")
    return f"line {source_line}" if source_line else "unknown turn"


def first_recall_mode_lines() -> list[str]:
    return [
        "- exact phrase: search distinctive old wording when you remember it.",
        "- project cue: search a repo, feature, object, person, or topic name.",
        "- time cue: search a remembered period such as recent, last month, or a known date.",
    ]


_LOW_SIGNAL_SEARCH_TERMS = {
    "agent",
    "claim",
    "compact",
    "continuity",
    "foreground",
    "memory",
    "navigation",
    "recall",
    "route",
    "safe",
    "search",
    "source",
}


def _no_match_anchor_queries(query: str, terms: list[Any]) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for raw in terms or search_query_terms([query]):
        term = str(raw or "").strip()
        key = term.casefold()
        if len(term) < 4 or key in seen or key in _LOW_SIGNAL_SEARCH_TERMS:
            continue
        seen.add(key)
        anchors.append(term)
        if len(anchors) >= 6:
            break
    if len(anchors) >= 4:
        return [" ".join(anchors[:3]), " ".join(anchors[3:6])][:2]
    if len(anchors) >= 2:
        return [" ".join(anchors)]
    clean_query = compact_text(query, 120)
    return [clean_query] if clean_query and clean_query != "(empty query)" else []


def _no_match_warning_line(warning: Mapping[str, Any]) -> str:
    code = str(warning.get("code") or "").strip()
    message = str(warning.get("message") or "").strip()
    if "unable to open database file" in message.casefold():
        return (
            "source index note: one registered index was unavailable; run "
            "`aippocampus onboard --provider auto --status --json` if expected sources are missing."
        )
    label = code or "source warning"
    return f"{label}: {compact_text(message, 160)}" if message else label


def render_human_search_result(result: dict[str, Any]) -> str:
    if result.get("kind") in {
        "aippocampus_current_thread_source_window",
        "aippocampus_last_recall_source_window",
    }:
        return render_current_source_window_text(
            result, snippet_chars=DEFAULT_HUMAN_SNIPPET_CHARS
        )
    terms = result.get("query_terms") or []
    query = str(result.get("query_text") or "").strip()
    if not query:
        query = " ".join(str(term) for term in terms).strip() or "(empty query)"
    matches = list(result.get("matches") or [])
    lines: list[str] = []
    if matches:
        lines.append("Source-backed matches")
        lines.append(f"query: {query}")
        for index, match in enumerate(matches, start=1):
            source = source_label_for_match(match)
            date = date_for_match(match)
            turn = turn_for_match(match)
            meta = " · ".join(part for part in (source, date, turn) if part)
            lines.append(f"{index}. Source: {meta}")
            if match.get("snippet_omitted"):
                lines.append("   snippet omitted in public mode; reopen source for exact text.")
            elif match.get("search_noise"):
                lines.append("   process snippet omitted; JSON keeps search_noise for audit.")
            else:
                snippet = compact_text(
                    str(match.get("snippet") or ""),
                    DEFAULT_HUMAN_SNIPPET_CHARS,
                )
                if snippet:
                    lines.append(f'   match: "{snippet}"')
                else:
                    lines.append("   match omitted; reopen source for exact text.")
            command = str(match.get("reopen_command") or "").strip()
            if command:
                lines.append(f"   reopen: {command}")
            duplicate_count = int(match.get("duplicate_count") or 0)
            if duplicate_count:
                lines.append(f"   mirrored in {duplicate_count + 1} source rows; representative shown.")
        lines.append(
            "Next: reopen source before quoting beyond these snippets, or refine with "
            "a project cue / time cue if this is not the thread you meant."
        )
        lines.append("Boundary: source-backed snippets are receipts; reopen before strong claims.")
    else:
        if result.get("status") == "no_phrase_like_matches":
            lines.append(f"No exact or phrase-like source match found for: {query}")
            suppressed_count = int(result.get("suppressed_low_coverage_match_count") or 0)
            if suppressed_count:
                lines.append(
                    f"suppressed low-coverage broad matches: {suppressed_count}"
                )
        else:
            lines.append(f"No source-backed snippet found for: {query}")
        scope = str(
            result.get("scope_description")
            or "current resolved thread clean-source directory only"
        )
        lines.append(f"searched scope: {scope}")
        anchor_queries = _no_match_anchor_queries(query, terms)
        search_prefix = (
            "aippocampus search --all"
            if result.get("registry_wide_search")
            or result.get("search_scope") == "registered_clean_source_and_indexes"
            else "aippocampus search"
        )
        if anchor_queries:
            lines.append("Next: try a shorter source search from the original cue:")
            for anchor in anchor_queries[:3]:
                lines.append(f"- {search_prefix} {shell_quote(anchor)} --json")
        else:
            lines.append(
                "Next: use `aippocampus agent recall \"<cue>\" --json` with a sharper cue, "
                "or inspect source registration if expected sources are missing."
            )
        lines.append("Boundary: a search miss is not proof that no memory exists.")
    for warning in result.get("warnings") or []:
        if isinstance(warning, Mapping):
            lines.append(_no_match_warning_line(warning))
    return "\n".join(lines)


def public_search_result(
    result: dict[str, Any],
    *,
    include_paths: bool = False,
    metadata_only: bool = False,
    query_text: str | None = None,
    detail: str = "full",
) -> dict[str, Any]:
    original_matches = [item for item in result.get("matches") or [] if isinstance(item, dict)]
    annotate_current_search_reopen_commands(
        original_matches,
        source_path=result.get("source"),
        include_paths=include_paths,
    )
    if detail == "compact":
        return _compact_public_search_result(
            result,
            original_matches=original_matches,
            include_paths=include_paths,
            metadata_only=metadata_only,
            query_text=query_text,
        )
    public = dict(result) if include_paths else redact_sensitive_values(redact_private_paths(result))
    if query_text is not None:
        public["query_text"] = (
            str(query_text)
            if include_paths
            else str(redact_sensitive_values(redact_private_paths(str(query_text))))
        )
    public_matches = [
        dict(item) if include_paths else redact_sensitive_values(redact_private_paths(dict(item)))
        for item in original_matches
    ]
    if not metadata_only:
        public["matches"] = [dict(item) for item in public_matches]
    if metadata_only:
        matches: list[dict[str, Any]] = []
        for index, match in enumerate(public_matches, start=1):
            timestamp = str(match.get("timestamp") or "")
            raw_snippet = "" if match.get("search_noise") else str(match.get("snippet") or "")
            snippet = compact_text(raw_snippet, DEFAULT_PUBLIC_SNIPPET_CHARS) if raw_snippet else ""
            public_match = {
                "match_index": index,
                "score": match.get("score"),
                "role": match.get("role"),
                "phase": match.get("phase") or "",
                "is_final": bool(match.get("is_final")),
                "scope_labels": match.get("scope_labels") or [],
                "semantic_scope_labels": match.get("semantic_scope_labels") or [],
                "date": timestamp[:10] if timestamp else None,
                "snippet": snippet,
                "snippet_omitted": not bool(snippet),
                "source_refs_omitted": True,
                "hit_index": index,
                "search_noise": bool(match.get("search_noise")),
                "noise_reason": match.get("noise_reason"),
                "artifact_role": match.get("artifact_role"),
                "artifact_demoted": bool(match.get("artifact_demoted")),
            }
            if include_paths:
                public_match["reopen_command"] = match.get("reopen_command")
            matches.append(public_match)
        public["matches"] = matches
        if not include_paths:
            public["source"] = LOCAL_PATH_REDACTION
            public["source_omitted"] = True
        public["output_boundary"] = "public_metadata_with_capped_source_snippets_no_reopen_refs"
    else:
        public["output_boundary"] = (
            "local_private_source_snippets"
            if public.get("matches")
            else "public_safe_no_source_snippets"
        )
    if not public.get("matches"):
        public["decision"] = "no_source_backed_snippet_found"
        public["recovery_guidance"] = (
            "Refine the current-thread cue, run `aippocampus search --all` for "
            "registered sources, or use `agent recall` for vague continuity cues."
        )
        public["recovery_actions"] = [
            'aippocampus search "distinctive exact phrase" --json',
            'aippocampus search --all "distinctive exact phrase" --json',
            'aippocampus agent recall "vague old cue" --json',
            "aippocampus onboard --status --json",
        ]
        public["searched_scope"] = public.get("scope_description")
        public["source_boundary"] = {
            "source_backed_claim_allowed": False,
            "candidate_routes_are_navigation_only": True,
            "reopen_required_before_quoting": True,
            "search_miss_is_not_absence_of_memory": True,
        }
    capped_public_snippets_emitted = any(
        bool(match.get("snippet")) and not match.get("snippet_omitted")
        for match in public.get("matches") or []
        if isinstance(match, dict)
    )
    public["privacy"] = {
        "paths_included": include_paths,
        "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
        "metadata_only": metadata_only,
        "capped_source_snippets_emitted": bool(metadata_only and capped_public_snippets_emitted),
        "raw_source_snippets_emitted": bool(public.get("matches")) and not metadata_only,
        "local_reopen_refs_emitted": bool(public.get("matches")) and not metadata_only,
    }
    public["match_count"] = len(public.get("matches") or [])
    public.update(
        search_foreground_authority(
            matches=original_matches,
            query_terms=[str(term) for term in public.get("query_terms") or []],
            metadata_only=metadata_only,
            query_text=query_text,
        )
    )
    foreground_action = public.get("foreground_action")
    if isinstance(foreground_action, Mapping):
        public.update(canonical_foreground_action_fields(foreground_action))
    return public if include_paths else redact_sensitive_values(redact_private_paths(public))


def _compact_match(
    match: Mapping[str, Any],
    *,
    index: int,
    metadata_only: bool,
    include_paths: bool,
) -> dict[str, Any]:
    timestamp = str(match.get("timestamp") or "")
    snippet = ""
    if not match.get("search_noise"):
        snippet = compact_text(str(match.get("snippet") or ""), DEFAULT_PUBLIC_SNIPPET_CHARS)
    source_line = match.get("source_line") or match.get("line")
    source_label = (
        f"clean source line {source_line}" if metadata_only and source_line else source_label_for_match(dict(match))
    )
    item: dict[str, Any] = {
        "match_index": index,
        "source_label": source_label,
        "role": match.get("role"),
        "phase": match.get("phase") or "",
        "date": timestamp[:10] if timestamp else None,
        "line": source_line,
        "snippet": snippet,
        "snippet_omitted": not bool(snippet),
    }
    if include_paths and match.get("reopen_command"):
        item["reopen_command"] = match.get("reopen_command")
    elif not metadata_only and match.get("reopen_command"):
        item["reopen_command"] = match.get("reopen_command")
    if metadata_only:
        item["source_refs_omitted"] = True
    if match.get("search_noise"):
        item["search_noise"] = True
        item["noise_reason"] = match.get("noise_reason")
    if match.get("artifact_demoted"):
        item["artifact_demoted"] = True
    # `snippet: ""` is deliberate when callers choose `--snippet-chars 0`.
    # Keep it paired with `snippet_omitted` so downstream agents can distinguish
    # "snippet intentionally withheld" from "match payload malformed".
    return {
        key: value
        for key, value in item.items()
        if key == "snippet" or value not in (None, "", [])
    }


def _compact_public_search_result(
    result: dict[str, Any],
    *,
    original_matches: list[dict[str, Any]],
    include_paths: bool,
    metadata_only: bool,
    query_text: str | None,
) -> dict[str, Any]:
    query = str(query_text or "").strip()
    if not query:
        query = " ".join(str(term) for term in result.get("query_terms") or []).strip()
    authority = search_foreground_authority(
        matches=original_matches,
        query_terms=[str(term) for term in result.get("query_terms") or []],
        metadata_only=metadata_only,
        query_text=query,
    )
    suppressed_count = int(result.get("suppressed_low_coverage_match_count") or 0)
    status = str(authority.get("status") or "ok")
    ok = bool(authority.get("ok"))
    if not original_matches and suppressed_count:
        status = "no_phrase_like_matches"
        ok = False
    payload: dict[str, Any] = {
        "kind": "aippocampus_search_result",
        "detail": "compact",
        "ok": ok,
        "status": status,
        "query_text": redact_sensitive_values(redact_private_paths(query)),
        "search_scope": result.get("search_scope"),
        "scope_description": result.get("scope_description"),
        "match_count": len(original_matches),
        "matches": [
            _compact_match(
                match,
                index=index,
                metadata_only=metadata_only,
                include_paths=include_paths,
            )
            for index, match in enumerate(original_matches, start=1)
        ],
        "claim_boundary": authority.get("claim_permission")
        or "source_reopen_required_before_claims",
        "source_reopen_boundary": (
            "reopen_selected_match_before_exact_or_sensitive_claims"
            if original_matches
            else "search_miss_is_not_absence_of_memory"
        ),
        "foreground_action": authority.get("foreground_action") or {},
    }
    capped_public_snippets_emitted = any(
        bool(match.get("snippet")) and not match.get("snippet_omitted")
        for match in payload.get("matches") or []
        if isinstance(match, dict)
    )
    if metadata_only:
        payload["output_boundary"] = "public_metadata_with_capped_source_snippets_no_reopen_refs"
        payload["privacy"] = {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "metadata_only": True,
            "capped_source_snippets_emitted": capped_public_snippets_emitted,
            "raw_source_snippets_emitted": False,
            "local_reopen_refs_emitted": False,
        }
    if suppressed_count:
        payload["suppressed_low_coverage_match_count"] = suppressed_count
    if not original_matches:
        payload["decision"] = "no_source_backed_snippet_found"
        payload["recovery_guidance"] = (
            "Refine the current-thread cue, run registry-wide search, or use "
            "`agent recall` for vague continuity cues."
        )
        payload["fallback_command_template"] = 'aippocampus agent recall "{cue}" --json'
        payload["detail_command_template"] = 'aippocampus search "{exact_phrase}" --json --detail full'
        payload["searched_scope"] = payload.get("scope_description")
    if include_paths:
        payload["source"] = result.get("source")
    elif metadata_only:
        payload["source"] = LOCAL_PATH_REDACTION
        payload["source_omitted"] = True
    if not original_matches and suppressed_count:
        payload["suppression_boundary"] = "phrase_like_low_coverage_suppressed"
    foreground_action = payload.get("foreground_action")
    if isinstance(foreground_action, Mapping):
        payload.update(
            canonical_foreground_action_fields(
                foreground_action,
                max_safe_next_actions=1,
                safe_next_read_only_only=True,
            )
        )
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))


def search_recovery_payload() -> dict[str, Any]:
    return foreground_recovery_card(
        kind="aippocampus_search_recovery",
        error_code="search_cue_required",
        message="Provide a cue or exact phrase before running clean-source search.",
        safe_next_actions=[
            foreground_template_action(
                action_id="search_exact_phrase",
                label="Search exact remembered wording",
                command_template='aippocampus search "{exact_phrase}" --json',
                requires=["exact_phrase"],
                why="Use search when the user or issue includes concrete source wording.",
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_quoting",
            ),
            foreground_template_action(
                action_id="recall_vague_cue",
                label="Recall from a vague continuity cue",
                command_template='aippocampus agent recall "{cue}" --json',
                requires=["cue"],
                why="Use recall first when the cue is fuzzy and needs route selection.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
            foreground_shell_action(
                action_id="check_onboarding_status",
                label="Check whether local history is registered",
                command="aippocampus onboard --provider auto --status --json",
                why="Use this if search misses and local history may not be registered.",
                mutation_risk="read_only",
                claim_boundary="host_status_not_source_evidence",
            ),
        ],
        source_boundary={
            "source_backed_claim_allowed": False,
            "search_did_not_run": True,
            "source_reopen_required_before_claims": True,
        },
    )


def render_search_recovery_text(payload: dict[str, Any]) -> str:
    actions = [item for item in payload.get("safe_next_actions") or [] if isinstance(item, dict)]
    lines = [
        "AIppocampus search",
        "what happened: no cue or exact phrase was provided.",
        "decision: choose exact search, vague recall, or onboarding status.",
    ]
    for action in actions[:3]:
        label = action.get("label") or action.get("id")
        lines.append(f"- {label}: {action.get('command')}")
    lines.append("boundary: search only supports source-backed claims after a real match/reopen.")
    return "\n".join(lines)
