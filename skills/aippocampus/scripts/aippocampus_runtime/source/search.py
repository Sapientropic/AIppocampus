#!/usr/bin/env python3
"""Search AIppocampus clean-source messages without touching raw rollout."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    compact_text,
)
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION as LOCAL_PATH_REDACTION
from aippocampus_runtime.source.artifact_role import artifact_role_profile
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.clean_source_resolver import resolve_clean_source_dir
from aippocampus_runtime.source.current_source_window import (
    open_current_thread_source_window,
)
from aippocampus_runtime.source.io_kernel import jsonl_loss_warning
from aippocampus_runtime.source.query_match_gate import (
    match_query_profile,
    query_match_gate,
)
from aippocampus_runtime.source.registry_search import (
    add_registry_search_arguments,
    run_registry_search_cli,
)
from aippocampus_runtime.source.route_note_search import search_route_notes
from aippocampus_runtime.source.route_topics import route_topic_low_coverage_acceptance
from aippocampus_runtime.source.search_core import (
    iter_clean_messages,  # noqa: F401 - public aggregate import used by runtime callers.
    load_clean_messages_with_loss,
    score_message,
)
from aippocampus_runtime.source.search_output import (
    date_for_match as date_for_match,
)
from aippocampus_runtime.source.search_output import (
    first_recall_mode_lines as first_recall_mode_lines,
)
from aippocampus_runtime.source.search_output import (
    public_search_result,
    render_human_search_result,
    render_search_recovery_text,
    search_recovery_payload,
)
from aippocampus_runtime.source.search_output import (
    source_label_for_match as source_label_for_match,
)
from aippocampus_runtime.source.search_output import (
    turn_for_match as turn_for_match,
)
from aippocampus_runtime.source.search_terms import search_query_terms
from aippocampus_runtime.source.semantic_scope_labels import (
    load_semantic_scope_labels,
    merged_scope_labels,
    semantic_labels_for_message,
)

PROCESS_NOISE_PREFIXES = (
    ("<subagent_notification>", "process_notification"),
    ("<tool", "tool_process"),
)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
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


def current_search_profile_accepted(profile: dict[str, Any]) -> bool:
    if profile.get("accepted"):
        return True
    matched = [str(item) for item in profile.get("matched_distinctive_anchors") or []]
    cjk_matched = [item for item in matched if CJK_RE.search(item)]
    return (
        bool(cjk_matched)
        and int(profile.get("matched_distinctive_anchor_count") or 0) >= 3
        and float(profile.get("distinctive_anchor_coverage") or 0.0) >= 0.5
    )


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
    source_dir = resolve_clean_source_dir(cwd, clean_source_dir)
    messages_path = source_dir / "messages.jsonl"
    semantic_sidecar = load_semantic_scope_labels(source_dir)
    terms = search_query_terms(patterns)
    query_text = " ".join(str(pattern) for pattern in patterns)
    query_gate_text = " ".join(str(term) for term in terms) or query_text
    gate = query_match_gate(query_gate_text)
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

    messages, jsonl_loss = load_clean_messages_with_loss(messages_path)
    warning = jsonl_loss_warning(
        jsonl_loss,
        stage="clean_source",
        path_label=messages_path.name,
    )
    if warning:
        warnings.append(warning)

    matches: list[dict[str, Any]] = []
    suppressed_low_coverage_match_count = 0
    for message in messages:
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
        query_profile = match_query_profile(
            query_text=query_gate_text,
            gate=gate,
            haystack=message_text,
        )
        if not current_search_profile_accepted(query_profile):
            topic_acceptance = route_topic_low_coverage_acceptance(
                {
                    "role": message.get("role"),
                    "phase": message.get("phase") or "",
                    "snippet": message_text,
                    "scope_labels": message_scope_labels,
                    "semantic_scope_labels": semantic_scope_labels,
                },
                intent=query_gate_text,
                query_profile=query_profile,
            )
            if topic_acceptance:
                query_profile = {**query_profile, **topic_acceptance}
            else:
                suppressed_low_coverage_match_count += 1
                continue
        if not query_profile.get("accepted"):
            query_profile = dict(query_profile)
            query_profile["accepted"] = True
            query_profile["acceptance_reason"] = "cjk_sidecar_anchor_cluster"
        noise_reason = process_noise_reason(message_text)
        artifact_role = artifact_role_profile(
            text=message_text,
            query_text=" ".join(str(pattern) for pattern in patterns),
            metadata={
                "role": message.get("role"),
                "phase": message.get("phase"),
                "material_class": message.get("material_class"),
                "source_claim_policy": message.get("source_claim_policy"),
                "scope_labels": message_scope_labels,
                "semantic_scope_labels": semantic_scope_labels,
            },
        )
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
            "material_class": message.get("material_class"),
            "source_claim_policy": message.get("source_claim_policy"),
            "scope_labels": message_scope_labels,
            "semantic_scope_labels": semantic_scope_labels,
            "score": round(score, 3),
            "query_match_profile": query_profile,
            "snippet": compact_text(message_text, snippet_chars) if snippet_chars else "",
            "snippet_omitted": snippet_chars == 0,
        }
        if artifact_role.get("role") != "topic_candidate":
            match["artifact_role"] = artifact_role
        if artifact_role.get("demote"):
            match["artifact_demoted"] = True
        if noise_reason:
            match["search_noise"] = True
            match["noise_reason"] = noise_reason
        matches.append(match)
    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") or item.get("artifact_demoted") else 0,
            -as_float(item.get("score")),
            as_int(item.get("source_line")),
        )
    )
    route_notes_path = source_dir / "route-notes.jsonl"
    if route_notes_path.exists():
        route_note_matches, route_note_loss = search_route_notes(
            route_notes_path,
            terms,
            limit=limit,
            snippet_chars=snippet_chars,
        )
        if label_filter:
            route_note_matches = [
                item
                for item in route_note_matches
                if set(label_filter).intersection(item.get("scope_labels") or [])
            ]
        warning = jsonl_loss_warning(
            route_note_loss,
            stage="route_notes",
            path_label=route_notes_path.name,
        )
        if warning:
            warnings.append(warning)
        matches.extend(route_note_matches)
        matches.sort(
            key=lambda item: (
                1 if item.get("search_noise") or item.get("artifact_demoted") else 0,
                -as_float(item.get("rank_score") or item.get("score")),
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
        "search_scope": "current_thread_clean_source",
        "scope_description": (
            "current resolved thread clean-source directory plus joined route-note "
            "navigation; this is not a registry-wide memory search"
        ),
        "query_terms": terms,
        "scope_labels": label_filter,
        "warnings": warnings,
        "jsonl_loss": jsonl_loss,
        "suppressed_low_coverage_match_count": suppressed_low_coverage_match_count,
        "matches": matches[:limit],
    }


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
  all sources:   aippocampus search --all "distinctive old wording" --json
  recall route:  aippocampus search --from-last-recall --recall-selector <emitted-selector> "distinctive old wording" --json
  fuzzy cue:    aippocampus search "repo feature last month"
  agent JSON:   aippocampus search "project cue" --json
  vague route:  aippocampus agent recall "old decision about setup" --json

After `agent recall`, prefer `--from-last-recall --recall-selector <id>` for
stable same-recall source narrowing. Bare `--from-last-recall` is a mutable
same-machine fallback for compatibility when the selector is unavailable.

No match: the default search only checked the current resolved thread clean
source. Refine the cue, use `--all` for registered sources, or run
`aippocampus agent recall` when the cue is vague. Search snippets are
source-backed receipts, not permission to quote or make strong claims beyond
the reopened source boundary.""",
        epilog=(
            "Advanced output controls: --public keeps capped snippets but omits local reopen refs; "
            "--include-paths is local diagnostic only."
        ),
    )
    parser.add_argument("patterns", nargs="*")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(
        "--clean-source-dir",
        default=None,
        help=(
            "Search one explicit clean-source directory. By default search uses "
            "the current resolved thread clean-source directory only; use --all "
            "for registry-wide source search."
        ),
    )
    add_registry_search_arguments(parser)
    parser.add_argument("--from-last-recall", action="store_true", help=(
        "Search only source candidates from an agent recall route set; pair with "
        "--recall-selector when available."
    ))
    parser.add_argument("--request", type=positive_int, default=None, help=(
        "With --from-last-recall, search one numbered recall route."
    ))
    parser.add_argument("--recall-selector", default=None, help=(
        "With --from-last-recall, use an isolated recall selector snapshot instead "
        "of the mutable same-machine fallback cache."
    ))
    parser.add_argument("--last-recall-path", default=None, help=(
        "Local diagnostic override for the same-machine last-recall cache path."
    ))
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
        "--detail",
        choices=("compact", "full"),
        default="compact",
        help="JSON detail level. Default compact is a foreground action card; full includes diagnostics.",
    )
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
        help="Emit public-safe compact output: capped snippets, no source refs, message ids, or local reopen ids.",
    )
    parser.add_argument(
        "--open-current-source",
        action="store_true",
        help="Open a bounded source window from the current thread clean-source directory.",
    )
    args = parser.parse_args(argv)
    if args.open_source and args.from_last_recall:
        if args.hit or args.last_search or args.registry_search or args.thread_key:
            parser.error(
                "--from-last-recall --open-source cannot be combined with registry source-window options"
            )
        if args.patterns:
            parser.error("--from-last-recall --open-source does not take search patterns")
        from importlib import import_module

        module = import_module("aippocampus_runtime.source.last_recall_source_window")
        return int(module.run_last_recall_source_window_cli(args))
    if args.open_current_source:
        if args.open_source or args.hit or args.last_search or args.registry_search:
            parser.error("--open-current-source cannot be combined with registry source-window options")
        if args.from_last_recall or args.request or args.recall_selector:
            parser.error("--open-current-source cannot be combined with last-recall search options")
        if args.patterns:
            parser.error("--open-current-source does not take search patterns")
        payload = open_current_thread_source_window(
            cwd=args.cwd,
            clean_source_dir=args.clean_source_dir,
            message_id=args.message_id,
            line=args.line,
            context_lines=args.context_lines,
            include_paths=bool(args.include_paths),
        )
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_human_search_result(payload))
        return 0 if payload.get("ok") else 1
    if args.open_source or args.hit:
        if args.hit and not args.last_search:
            parser.error("--hit requires --last-search")
        if args.last_search and not args.hit:
            parser.error("--last-search requires --hit")
        if args.source_ref_index and not args.hit:
            parser.error("--source-ref-index requires --hit --last-search")
        if args.patterns:
            parser.error("source-window reopen does not take search patterns")
        return run_registry_search_cli(args, render_human_search_result)
    if not args.patterns:
        payload = search_recovery_payload()
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_search_recovery_text(payload))
        return 2
    if not search_query_terms(args.patterns):
        payload = search_recovery_payload()
        payload["status"] = "needs_input"
        payload["query_text"] = ""
        payload["query_terms"] = []
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_search_recovery_text(payload))
        return 2

    if args.registry_search:
        if args.clean_source_dir:
            parser.error("--clean-source-dir searches one directory; use --all without it")
        if args.from_last_recall:
            parser.error("--from-last-recall searches recall candidates; use it without --all")
        if args.request or args.recall_selector:
            parser.error("--request and --recall-selector require --from-last-recall")
        return run_registry_search_cli(args, render_human_search_result)
    if args.from_last_recall:
        if args.clean_source_dir:
            parser.error("--clean-source-dir searches one directory; use --from-last-recall without it")
        from importlib import import_module

        module = import_module("aippocampus_runtime.source.last_recall_search")
        return int(module.run_last_recall_search_cli(args))
    if args.request or args.recall_selector:
        parser.error("--request and --recall-selector require --from-last-recall")

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
        query_text=" ".join(str(pattern) for pattern in args.patterns),
        detail=args.detail if args.json_output else "full",
    )
    if args.json_output:
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
    else:
        print(render_human_search_result(public_result))
    return 0 if result["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
