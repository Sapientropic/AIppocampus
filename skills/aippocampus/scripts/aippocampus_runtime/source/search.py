#!/usr/bin/env python3
"""Search AIppocampus clean-source messages without touching raw rollout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    foreground_recovery_card,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.core import (
    compact_text,
    default_thread_clean_source_dir,
    resolve_artifact_path,
)
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.semantic_scope_labels import (
    load_semantic_scope_labels,
    merged_scope_labels,
    semantic_labels_for_message,
)

LEGACY_CLEAN_SOURCE_DIR = ".aippocampus/clean-source"
PROCESS_NOISE_PREFIXES = (
    ("<subagent_notification>", "process_notification"),
    ("<tool", "tool_process"),
)
DEFAULT_HUMAN_SNIPPET_CHARS = 220


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return parsed


def iter_clean_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if not path.exists():
        return messages
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("text"):
                messages.append(item)
    return messages


def score_message(message: dict[str, Any], terms: list[str]) -> float:
    text = str(message.get("text") or "")
    low = text.casefold()
    score = 0.0
    matched = False
    for term in terms:
        needle = term.casefold()
        if not needle:
            continue
        count = low.count(needle)
        if count:
            matched = True
            score += 8.0 + count * min(len(term), 20)
    if not matched:
        return 0.0
    if message.get("is_final") or message.get("phase") == "final_answer":
        score += 18.0
    elif message.get("role") == "user":
        score += 3.0
    elif message.get("phase") == "commentary":
        score -= 2.0
    return score


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


def process_noise_reason(text: str) -> str:
    """Mark agent/tool plumbing so it does not outrank real source receipts.

    Clean source is still source-reachable audit material, but foreground search
    should not make process notifications look like remembered user context.
    Keep the marker in JSON for diagnostics while demoting it in default cards.
    """

    snippet = str(text or "").lstrip().casefold()
    for prefix, reason in PROCESS_NOISE_PREFIXES:
        if snippet.startswith(prefix):
            return reason
    return ""


def search_clean_source(
    cwd: str | Path,
    patterns: list[str],
    *,
    clean_source_dir: str | Path | None = None,
    limit: int = 10,
    snippet_chars: int = 700,
    scope_labels: list[str] | None = None,
) -> dict[str, Any]:
    cwd = Path(cwd).resolve()
    if clean_source_dir is None:
        global_dir = default_thread_clean_source_dir(cwd)
        legacy_dir = cwd / LEGACY_CLEAN_SOURCE_DIR
        source_dir = (
            global_dir
            if (global_dir / "messages.jsonl").exists()
            or not (legacy_dir / "messages.jsonl").exists()
            else legacy_dir
        )
    else:
        source_dir = resolve_artifact_path(
            clean_source_dir, cwd, default_thread_clean_source_dir(cwd)
        )
    messages_path = source_dir / "messages.jsonl"
    semantic_sidecar = load_semantic_scope_labels(source_dir)
    terms = split_query_terms(patterns)
    label_filter = [str(label).strip() for label in scope_labels or [] if str(label).strip()]
    known_scope_labels = set(SCOPE_LABEL_ORDER)
    warnings: list[dict[str, Any]] = [
        {
            "code": "unknown_scope_label",
            "scope_label": label,
            "message": f"Unknown scope label: {label}",
        }
        for label in label_filter
        if label not in known_scope_labels
    ]
    missing_scope_label_count = 0

    matches: list[dict[str, Any]] = []
    for message in iter_clean_messages(messages_path):
        message_text = str(message.get("text") or "")
        if "scope_labels" not in message:
            missing_scope_label_count += 1
        base_scope_labels = [
            str(label) for label in message.get("scope_labels", []) if isinstance(label, str)
        ]
        semantic_scope_labels = semantic_labels_for_message(message, semantic_sidecar)
        message_scope_labels = merged_scope_labels(base_scope_labels, semantic_scope_labels)
        if label_filter and not set(label_filter).intersection(message_scope_labels):
            continue
        score = score_message(message, terms)
        if score <= 0:
            continue
        noise_reason = process_noise_reason(message_text)
        match = {
            "id": message.get("message_id") or message.get("id"),
            "message_id": message.get("message_id") or message.get("id"),
            "turn_id": message.get("turn_id"),
            "source_id": message.get("source_id"),
            "source_ref": message.get("source_ref"),
            "clean_ordinal": message.get("clean_ordinal"),
            "source_line": message.get("source_line"),
            "raw_start_line": message.get("raw_start_line") or message.get("source_line"),
            "raw_end_line": message.get("raw_end_line") or message.get("source_line"),
            "timestamp": message.get("timestamp"),
            "role": message.get("role"),
            "phase": message.get("phase") or "",
            "turn_index": message.get("turn_index"),
            "is_final": bool(message.get("is_final")),
            "scope_labels": message_scope_labels,
            "semantic_scope_labels": semantic_scope_labels,
            "score": round(score, 3),
            "snippet": compact_text(message_text, snippet_chars) if snippet_chars else "",
            "snippet_omitted": snippet_chars == 0,
        }
        if noise_reason:
            match["search_noise"] = True
            match["noise_reason"] = noise_reason
        matches.append(match)
    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") else 0,
            -as_float(item.get("score")),
            as_int(item.get("source_line")),
        )
    )
    if label_filter and missing_scope_label_count:
        warnings.append(
            {
                "code": "missing_scope_labels",
                "count": missing_scope_label_count,
                "message": "Some clean-source messages predate scope_labels; rebuild clean source before treating filtered results as complete.",
            }
        )
    return {
        "source": str(messages_path),
        "query_terms": terms,
        "scope_labels": label_filter,
        "warnings": warnings,
        "matches": matches[:limit],
    }


def source_label_for_match(match: dict[str, Any]) -> str:
    for key in ("source_ref", "source_id"):
        value = match.get(key)
        if value:
            return compact_text(str(value), 80)
    source_line = match.get("source_line")
    return f"clean source line {source_line}" if source_line else "clean source"


def date_for_match(match: dict[str, Any]) -> str:
    timestamp = str(match.get("timestamp") or "").strip()
    return timestamp[:10] if timestamp else "unknown date"


def turn_for_match(match: dict[str, Any]) -> str:
    for key in ("turn_index", "turn_id"):
        value = match.get(key)
        if value is not None and str(value).strip():
            return f"turn {value}"
    source_line = match.get("source_line")
    return f"line {source_line}" if source_line else "unknown turn"


def first_recall_mode_lines() -> list[str]:
    return [
        "- exact phrase: search distinctive old wording when you remember it.",
        "- project cue: search a repo, feature, object, person, or topic name.",
        "- time cue: search a remembered period such as recent, last month, or a known date.",
    ]


def render_human_search_result(result: dict[str, Any]) -> str:
    terms = result.get("query_terms") or []
    query = " ".join(str(term) for term in terms).strip() or "(empty query)"
    matches = list(result.get("matches") or [])
    lines: list[str] = []
    if matches:
        lines.append("Source-backed action cards")
        lines.append("Source-backed snippets are receipts; reopen before relying on exact wording.")
        lines.append(f"query: {query}")
        for index, match in enumerate(matches, start=1):
            source = source_label_for_match(match)
            date = date_for_match(match)
            turn = turn_for_match(match)
            lines.append(f"{index}. Source: {source} · {date} · {turn}")
            lines.append("   boundary: source-backed receipt; reopen before quoting or strong claims")
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
        lines.append(
            "Next: reopen source before quoting beyond these snippets, or refine with "
            "a project cue / time cue if this is not the thread you meant."
        )
    else:
        lines.append(f"No source-backed snippet found for: {query}")
        lines.append("Possible routes, not yet evidence:")
        lines.extend(first_recall_mode_lines())
        lines.append(
            "Next: refine the cue, search an exact phrase, or run "
            "`aippocampus onboard --status` to check whether local history is registered."
        )
        lines.append(
            "Boundary: candidate routes are navigation only until a source-backed snippet appears."
        )
    for warning in result.get("warnings") or []:
        lines.append(f"warning: {warning.get('code')}: {warning.get('message')}")
    return "\n".join(lines)


def public_search_result(
    result: dict[str, Any],
    *,
    include_paths: bool = False,
    metadata_only: bool = False,
    query_text: str | None = None,
) -> dict[str, Any]:
    public = dict(result) if include_paths else redact_sensitive_values(redact_private_paths(result))
    original_matches = [item for item in result.get("matches") or [] if isinstance(item, dict)]
    if metadata_only:
        matches: list[dict[str, Any]] = []
        for index, match in enumerate(public.get("matches") or [], start=1):
            timestamp = str(match.get("timestamp") or "")
            matches.append(
                {
                    "match_index": index,
                    "score": match.get("score"),
                    "role": match.get("role"),
                    "phase": match.get("phase") or "",
                    "is_final": bool(match.get("is_final")),
                    "scope_labels": match.get("scope_labels") or [],
                    "semantic_scope_labels": match.get("semantic_scope_labels") or [],
                    "date": timestamp[:10] if timestamp else None,
                    "snippet_omitted": True,
                    "source_refs_omitted": True,
                    "search_noise": bool(match.get("search_noise")),
                    "noise_reason": match.get("noise_reason"),
                }
            )
        public["matches"] = matches
        if not include_paths:
            public["source"] = LOCAL_PATH_REDACTION
            public["source_omitted"] = True
        public["output_boundary"] = "public_metadata_only_no_source_snippets_or_reopen_refs"
    else:
        public["output_boundary"] = (
            "local_private_source_snippets"
            if public.get("matches")
            else "public_safe_no_source_snippets"
        )
    if not public.get("matches"):
        public["decision"] = "no_source_backed_snippet_found"
        public["agent_next_action"] = (
            "Refine the cue with exact wording, a project/object name, or a time clue; "
            "run `aippocampus onboard --status` if local history may not be registered."
        )
        public["recovery_actions"] = [
            'aippocampus search "distinctive exact phrase" --json',
            'aippocampus agent recall "vague old cue" --json',
            "aippocampus onboard --status --json",
        ]
        public["source_boundary"] = {
            "source_backed_claim_allowed": False,
            "candidate_routes_are_navigation_only": True,
            "reopen_required_before_quoting": True,
        }
    public["privacy"] = {
        "paths_included": include_paths,
        "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
        "metadata_only": metadata_only,
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
    return public


def _query_text(query_terms: list[str], query_text: str | None) -> str:
    explicit = str(query_text or "").strip()
    if explicit:
        return explicit
    return " ".join(str(term) for term in query_terms if str(term).strip()).strip()


def _first_match_selector(matches: list[dict[str, Any]]) -> dict[str, Any]:
    if not matches:
        return {}
    first = matches[0]
    for key in ("message_id", "id", "turn_id", "turn_index"):
        value = first.get(key)
        if value not in (None, ""):
            return {key: value}
    return {}


def search_foreground_authority(
    *,
    matches: list[dict[str, Any]],
    query_terms: list[str],
    metadata_only: bool,
    query_text: str | None = None,
) -> dict[str, Any]:
    """Project clean-source search into the shared foreground authority posture.

    Search may expose local snippets in CLI JSON, or metadata-only cards through
    public/MCP surfaces. Both are useful first-touch routes, but neither should
    be mistaken for permission to quote or make broad claims without reopening
    the clean source window. Keep the action machine-readable so foreground
    agents do not have to parse prose like "reopen before quoting".
    """

    query = _query_text(query_terms, query_text)
    has_matches = bool(matches)
    if has_matches and metadata_only:
        return {
            "kind": "aippocampus_search_result",
            "ok": True,
            "status": "ok",
            "entry_state": "explicit_search_invoked",
            "route_state": "reopenable_route",
            "usefulness": "useful_for_next_action",
            "claim_permission": "metadata_only_no_claim_before_reopen",
            "source_boundary": {
                "authority": "reopenable_route",
                "source_backed_claim_allowed": False,
                "metadata_only": True,
                "source_reopen_required_before_claim": True,
                "snippets_are_source_open": False,
            },
            "foreground_action": {
                "action_id": "recall_context_from_search",
                "tool_name": "recall_context",
                "arguments": {"intent": query, "max": min(max(len(matches), 1), 5)},
                "claim_boundary": "source_reopen_required_before_claim",
                "why": "Metadata-only search found matching clean-source shape; reopen context before quoting or relying on exact wording.",
            },
            "forbidden_claims": [
                "exact wording",
                "sensitive/stale/disputed facts",
                "absence of other source matches",
            ],
        }
    if has_matches:
        return {
            "kind": "aippocampus_search_result",
            "ok": True,
            "status": "ok",
            "entry_state": "explicit_search_invoked",
            "route_state": "source_refs_available",
            "usefulness": "useful_for_next_action",
            "claim_permission": "bounded_search_receipt_requires_reopen",
            "source_boundary": {
                "authority": "bounded_evidence",
                "source_backed_claim_allowed": True,
                "metadata_only": False,
                "source_reopen_required_before_claim": True,
                "snippets_are_bounded_receipts": True,
            },
            "foreground_action": {
                "action_id": "reopen_search_match_source",
                "tool_name": "get_turn_context",
                "arguments": _first_match_selector(matches),
                "claim_boundary": "source_reopen_required_before_claim",
                "why": "Use the selected clean-source match as a route, then reopen the surrounding turn before quoting or making strong claims.",
            },
            "forbidden_claims": [
                "exact wording beyond the emitted snippet",
                "sensitive/stale/disputed facts",
                "absence of other source matches",
            ],
        }
    return {
        "kind": "aippocampus_search_result",
        "ok": False,
        "status": "no_matches",
        "entry_state": "explicit_search_invoked",
        "route_state": "no_useful_route",
        "usefulness": "needs_refined_cue",
        "claim_permission": "no_claim_before_source_match",
        "source_boundary": {
            "authority": "direction_only",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claim": True,
            "search_miss_is_not_absence_of_memory": True,
        },
        "foreground_action": {
            "action_id": "refine_or_recall",
            "tool_name": "agent_recall",
            "arguments": {"query": query or "old decision or handoff cue"},
            "claim_boundary": "no_claim_before_reopen",
            "why": "Search found no source-backed snippet; use a richer continuity cue or exact wording before claiming from memory.",
        },
        "forbidden_claims": [
            "source-backed fact",
            "absence of memory",
            "exact wording",
        ],
    }


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus search",
        usage='aippocampus search "cue or exact phrase" [--json|--public]',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Search local clean source.

Use search when you have a remembered phrase, a project/object cue, or a time
cue and want source-backed snippets/routes. Use `agent recall` when the cue is
vague and you need route help before choosing search terms.

Workflows:
  exact phrase: aippocampus search "distinctive old wording"
  fuzzy cue:    aippocampus search "repo feature last month"
  agent JSON:   aippocampus search "project cue" --json
  vague route:  aippocampus agent recall "old decision about setup" --json

No match: refine the cue, try exact wording, or run
`aippocampus onboard --provider auto --status` if local history may not be
registered. Search snippets are source-backed receipts, not permission to quote
or make strong claims beyond the reopened source boundary.""",
        epilog=(
            "Advanced output controls: --public omits snippets and local reopen refs; "
            "--include-paths is local diagnostic only."
        ),
    )
    parser.add_argument("patterns", nargs="*")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(
        "--clean-source-dir",
        default=None,
        help="Defaults to global clean source, with project-local legacy fallback.",
    )
    parser.add_argument("--max", type=positive_int, default=10)
    parser.add_argument("--snippet-chars", type=non_negative_int, default=700)
    parser.add_argument(
        "--scope-label",
        action="append",
        default=None,
        help="Filter to clean-source messages carrying this scope label. Repeat for OR semantics.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--include-paths",
        action="store_true",
        help="Local diagnostic opt-in: include filesystem paths in output.",
    )
    parser.add_argument(
        "--public",
        "--metadata-only",
        action="store_true",
        dest="metadata_only",
        help="Emit public-safe metadata only: no snippets, source refs, message ids, or local reopen ids.",
    )
    args = parser.parse_args(argv)
    if not args.patterns:
        payload = search_recovery_payload()
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_search_recovery_text(payload))
        return 2

    result = search_clean_source(
        args.cwd,
        args.patterns,
        clean_source_dir=args.clean_source_dir,
        limit=args.max,
        snippet_chars=args.snippet_chars,
        scope_labels=args.scope_label,
    )
    public_result = public_search_result(
        result,
        include_paths=bool(args.include_paths),
        metadata_only=bool(args.metadata_only),
    )
    if args.json_output:
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
    else:
        print(render_human_search_result(public_result))
    return 0 if result["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
