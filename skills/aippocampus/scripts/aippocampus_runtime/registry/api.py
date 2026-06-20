#!/usr/bin/env python3
"""Machine-wide registry for discoverable thread-memory indexes."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import (
    cli_exit_code_for_error_code,
    codex_home,
    codex_provider,
    compact_text,
    default_thread_clean_source_dir,
    default_thread_index_dir,
    now_utc,
    parse_anchor_file,
    public_session_meta,
)
from aippocampus_runtime.privacy import redact_private_paths
from aippocampus_runtime.registry.common import (
    SCRIPT_DIR,
    anchor_summary,
    project_fields,
    run_json,
    unique_preserve,
)
from aippocampus_runtime.registry.hook_seen_reconciliation import reconcile_hook_seen_threads
from aippocampus_runtime.registry.provider import current_thread_build_cmd, thread_key_for
from aippocampus_runtime.registry.search import (
    REGISTRY_SEARCH_DEEP_BUDGET,
    clean_hit_rank_score,
    deep_search_entry,
    deep_search_entry_result,
    entry_search_score,
    search_noise_reason,
)
from aippocampus_runtime.registry.source_registration import (
    generic_validation_error_payload,
    provider_for_explicit_source,
    register_rollout_thread,
    register_source_thread,
)
from aippocampus_runtime.registry.store import (
    REGISTRY_SCHEMA_VERSION,
    RegistryReadError,
    RegistryWriteBusyError,
    default_registry_dir,
    load_existing_json_object,
    load_json,
    load_registry,
    registry_paths,
    registry_root,
    render_registry_markdown,
    safe_slug,
    save_registry,
    thread_store_dir,
    update_registry,
    upsert_thread,
)
from aippocampus_runtime.warm_ambient.hook_seen_threads import (
    DEFAULT_HOOK_SEEN_STALE_AFTER_SECONDS,
    hook_seen_ledger_path_for_registry,
    hook_seen_thread_ref,
    hook_seen_thread_refs,
)
from conversation_sources import (
    PROVIDER_CHOICES,
    ConversationProvider,
    GenericJsonlValidationError,
    create_conversation_provider,
)

__all__ = [
    "REGISTRY_SCHEMA_VERSION",
    "RegistryReadError",
    "RegistryWriteBusyError",
    "default_registry_dir",
    "registry_paths",
    "registry_root",
    "load_json",
    "load_existing_json_object",
    "safe_slug",
    "thread_store_dir",
    "load_registry",
    "upsert_thread",
    "render_registry_markdown",
    "save_registry",
    "unique_preserve",
    "register_current_thread",
    "register_rollout_thread",
    "register_source_thread",
    "scan_session_rollouts",
    "entry_search_score",
    "search_noise_reason",
    "clean_hit_rank_score",
    "deep_search_entry",
    "deep_search_entry_result",
]


def registry_writer_busy_payload(exc: RegistryWriteBusyError) -> dict:
    return {
        "ok": False,
        "error": {
            "code": exc.code,
            "class": "retryable_contention",
            "message": str(exc),
            "retryable": exc.retryable,
            "registry": str(exc.registry_path),
            "wait_timeout_seconds": exc.wait_timeout_seconds,
        },
        "data": None,
    }


def report_registry_writer_busy(exc: RegistryWriteBusyError, *, json_output: bool) -> int:
    payload = registry_writer_busy_payload(exc)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["error"]["message"], file=sys.stderr)
    return cli_exit_code_for_error_code(exc.code)


def _arg_present(args: list[str], names: set[str]) -> bool:
    return any(item in names or any(item.startswith(name + "=") for name in names) for item in args)


def _subcommand_index(args: list[str], command: str) -> int | None:
    try:
        return args.index(command)
    except ValueError:
        return None


def import_conversation_usage_payload(missing: list[str]) -> dict:
    normalized_missing = [
        "input_path" if item == "--input/--source" else "format_or_provider"
        for item in missing
    ]
    actions: list[dict[str, Any]] = [
        {
            "id": "show_import_chooser",
            "kind": "shell_command",
            "command": "aippocampus import --json",
            "mutation_risk": "read_only",
            "claim_boundary": "import_recovery_no_write",
            "reason": "show machine-readable import choices without writing registry data",
        },
        {
            "id": "preview_generic_jsonl",
            "kind": "shell_command_template",
            "command_template": (
                "aippocampus import conversation --format generic-jsonl "
                '--input "{input_path}" --dry-run --json'
            ),
            "requires": ["input_path"],
            "mutation_risk": "read_only_preview",
            "claim_boundary": "import_preview_before_write",
            "reason": "validate the transcript before any registry write",
        },
    ]
    return {
        "kind": "aippocampus_import_conversation_recovery",
        "ok": False,
        "status": "needs_input",
        "missing": normalized_missing,
        "error": {
            "code": "usage_error",
            "class": "usage_error",
            "message": "import conversation needs an input file and a provider/format.",
            "missing": missing,
            "written": False,
            "path_redacted": True,
            "next_action": "Choose an import path or provide fields for a dry-run preview.",
        },
        "input_schema": {
            "required": normalized_missing,
            "supported_providers": list(PROVIDER_CHOICES),
            "supported_formats": ["generic-jsonl"],
            "preview_first": True,
        },
        "source_boundary": {
            "explicit_input_required": True,
            "preview_before_write": True,
            "local_paths_redacted_by_default": True,
        },
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        "data": None,
    }


def render_import_conversation_error(payload: dict) -> str:
    error = payload.get("error") or {}
    lines = [
        "AIppocampus import conversation",
        f"error: {error.get('message')}",
    ]
    missing = error.get("missing") or []
    if missing:
        lines.append("missing: " + ", ".join(str(item) for item in missing))
    actions = payload.get("safe_next_actions") or []
    chooser = next((item for item in actions if item.get("command")), None)
    template = next((item for item in actions if item.get("command_template")), None)
    if chooser:
        lines.append(f"next: {chooser.get('command')}")
    if template:
        lines.append(f"preview template: {template.get('command_template')}")
    if not chooser and not template and error.get("next_action"):
        lines.append(f"next: {error.get('next_action')}")
    lines.append("written: false")
    lines.append("privacy: local input paths are redacted by default")
    lines.append("boundary: preview/dry-run first; register only after the input is explicit.")
    return "\n".join(lines)


def maybe_handle_import_conversation_usage(raw_args: list[str]) -> int | None:
    index = _subcommand_index(raw_args, "register-source")
    if index is None or any(item in {"-h", "--help"} for item in raw_args):
        return None
    register_args = raw_args[index + 1 :]
    missing: list[str] = []
    if not _arg_present(register_args, {"--input", "--source"}):
        missing.append("--input/--source")
    if not _arg_present(register_args, {"--provider", "--format"}):
        missing.append("--provider/--format")
    if not missing:
        return None
    payload = import_conversation_usage_payload(missing)
    if "--json" in register_args:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_import_conversation_error(payload), file=sys.stderr)
    return cli_exit_code_for_error_code("usage_error")


def register_current_thread(
    cwd: Path,
    *,
    vault: Path | None = None,
    dashboard_note: Path | None = None,
    dashboard_html: Path | None = None,
    registry_dir: Path | None = None,
    health: dict | None = None,
    build_index: bool = False,
    provider: ConversationProvider | None = None,
) -> dict:
    cwd = cwd.resolve()
    # Fallback is only for legacy in-process callers during provider migration.
    active_provider = provider or codex_provider(codex_home())
    try:
        rollout = active_provider.locate_current(cwd).path
    except Exception:
        rollout = None
    default_index_dir = default_thread_index_dir(cwd, rollout)
    legacy_index_dir = cwd / ".aippocampus"
    index_dir = (
        default_index_dir
        if build_index
        or (default_index_dir / "manifest.json").exists()
        or not (legacy_index_dir / "manifest.json").exists()
        else legacy_index_dir
    )
    if build_index and not (index_dir / "manifest.json").exists():
        run_json(current_thread_build_cmd(SCRIPT_DIR, "build_index.py", cwd, rollout, active_provider.name))
    clean_source_dir = default_thread_clean_source_dir(cwd, rollout)
    legacy_clean_source_dir = legacy_index_dir / "clean-source"
    if (
        not build_index
        and not (clean_source_dir / "manifest.json").exists()
        and (legacy_clean_source_dir / "manifest.json").exists()
    ):
        clean_source_dir = legacy_clean_source_dir
    if build_index and not (clean_source_dir / "manifest.json").exists():
        run_json(current_thread_build_cmd(SCRIPT_DIR, "build_clean_source.py", cwd, rollout, active_provider.name))

    manifest = load_json(index_dir / "manifest.json")
    clean_manifest = load_json(clean_source_dir / "manifest.json")
    if health is None:
        try:
            health_module = importlib.import_module("aippocampus_runtime.health")
            health = health_module.health_report(cwd)
        except Exception:
            health = {}
    anchors_path = cwd / "thread-anchors.md"
    anchors = parse_anchor_file(anchors_path)
    anchor_titles, keywords, summary = anchor_summary(anchors)
    project = project_fields(cwd)

    if manifest.get("source_rollout"):
        rollout = Path(manifest["source_rollout"])
    else:
        try:
            rollout = active_provider.locate_current(cwd).path
        except Exception:
            rollout = None

    thread_key = thread_key_for(cwd, manifest, rollout)
    session_meta = manifest.get("session_meta") or {}
    index_outputs = manifest.get("outputs", {})
    sqlite_path = resolve_sqlite_index_path(
        Path(index_outputs.get("sqlite_current") or index_outputs.get("sqlite") or index_dir / "source_index.sqlite")
    )
    graph_path = Path(manifest.get("outputs", {}).get("graph_json") or index_dir / "graph.json")
    messages_path = Path(
        manifest.get("outputs", {}).get("messages_jsonl") or index_dir / "messages.jsonl"
    )
    rag = manifest.get("rag") or (manifest.get("sqlite") or {}).get("rag") or {}

    entry = {
        "thread_key": thread_key,
        "title": cwd.name,
        "workspace_name": cwd.name,
        **project,
        "updated_at": now_utc(),
        "created_at": manifest.get("created_at"),
        "source_provider": clean_manifest.get("source_provider") or session_meta.get("source") or active_provider.name,
        "session_meta": session_meta,
        "message_count": manifest.get("message_count")
        or health.get("rollout", {}).get("message_count"),
        "rollout_size": manifest.get("source_rollout_size")
        or health.get("rollout", {}).get("size"),
        "anchor_count": len(anchors),
        "anchor_titles": anchor_titles,
        "keywords": keywords,
        "summary": summary,
        "health": {
            "ok": health.get("ok"),
            "index_stale": health.get("index", {}).get("stale"),
            "checkpoint_due": health.get("checkpoint", {}).get("due"),
            "graphify_stale": health.get("graphify", {}).get("stale"),
            "recommended_actions": health.get("recommended_actions", []),
        },
        "capabilities": {
            "sqlite_fts": (manifest.get("sqlite") or {}).get("fts_enabled"),
            "rag_chunks": rag.get("chunk_count"),
            "rag_fts": rag.get("fts_enabled"),
            "graph_nodes": (manifest.get("graph") or {}).get("node_count"),
            "graph_edges": (manifest.get("graph") or {}).get("edge_count"),
        },
        "paths": {
            "workspace": str(cwd),
            "rollout": str(rollout) if rollout else manifest.get("source_rollout"),
            "anchors": str(anchors_path) if anchors_path.exists() else None,
            "index_dir": str(index_dir),
            "messages_jsonl": str(messages_path) if messages_path.exists() else None,
            "sqlite": str(sqlite_path) if sqlite_path.exists() else None,
            "graph_json": str(graph_path) if graph_path.exists() else None,
            "graphify_corpus": str(index_dir / "graphify-corpus")
            if (index_dir / "graphify-corpus").exists()
            else None,
            "clean_source_dir": str(clean_source_dir) if clean_source_dir.exists() else None,
            "clean_source_messages_jsonl": (clean_manifest.get("outputs") or {}).get(
                "messages_jsonl"
            ),
            "clean_source_turns_jsonl": (clean_manifest.get("outputs") or {}).get("turns_jsonl"),
            "clean_source_events_jsonl": (clean_manifest.get("outputs") or {}).get("events_jsonl"),
            "vault": str(vault.resolve()) if vault else None,
            "dashboard_note": str(dashboard_note.resolve()) if dashboard_note else None,
            "dashboard_html": str(dashboard_html.resolve()) if dashboard_html else None,
        },
    }

    json_path, md_path = registry_paths(registry_dir)
    registry = update_registry(
        json_path,
        md_path,
        lambda current: upsert_thread(current, entry),
    )
    return {
        "entry": entry,
        "registry_json": str(json_path),
        "registry_markdown": str(md_path),
        "thread_count": len(registry["threads"]),
    }


def scan_session_rollouts(
    *,
    registry_dir: Path | None = None,
    build_index: bool = False,
    refresh: bool = False,
    max_count: int | None = None,
    cwd_filter: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    dry_run: bool = False,
    hook_seen_only: bool = False,
    hook_seen_ledger: Path | None = None,
    provider: ConversationProvider | None = None,
) -> dict:
    json_path, _ = registry_paths(registry_dir)
    existing = {entry.get("thread_key") for entry in load_registry(json_path).get("threads", [])}
    hook_seen_filter_refs: set[str] = set()
    hook_seen_filter_path = hook_seen_ledger or hook_seen_ledger_path_for_registry(json_path)
    if hook_seen_only:
        hook_seen_filter_refs = hook_seen_thread_refs(hook_seen_filter_path)
    candidates: list[tuple[float, Path, dict, str]] = []
    # CLI/onboarding call sites pass a provider explicitly. This fallback is
    # kept only for legacy in-process callers during the provider migration.
    active_provider = provider or codex_provider(codex_home())
    for source in active_provider.discover_sessions():
        rollout = source.path
        meta = dict(source.metadata or {})
        if not meta:
            meta = public_session_meta(active_provider.read_metadata(source))
        if cwd_filter and cwd_filter.casefold() not in str(meta.get("cwd") or "").casefold():
            continue
        thread_key = active_provider.thread_key(source, meta)
        if hook_seen_only and hook_seen_thread_ref(thread_key) not in hook_seen_filter_refs:
            continue
        if not refresh and thread_key in existing:
            continue
        try:
            mtime = rollout.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, rollout, meta, thread_key))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if max_count is not None:
        candidates = candidates[:max_count]

    registered = []
    planned = []
    for _, rollout, meta, thread_key in candidates:
        if dry_run:
            planned.append(
                {
                    "thread_key": thread_key,
                    "rollout": str(rollout),
                    "cwd": meta.get("cwd"),
                    "timestamp": meta.get("timestamp"),
                }
            )
            continue
        result = register_rollout_thread(
            rollout,
            project=project,
            tags=tags,
            registry_dir=registry_dir,
            build_index=build_index,
            provider=active_provider,
        )
        registered.append(result["entry"])
    return {
        "registry": str(json_path),
        "dry_run": dry_run,
        "hook_seen_filter": {
            "enabled": hook_seen_only,
            "ledger": str(hook_seen_filter_path),
            "seen_thread_count": len(hook_seen_filter_refs),
        },
        "planned": planned,
        "registered": registered,
        "count": len(planned) if dry_run else len(registered),
    }


def _search_receipt_snippet(text: object, *, limit: int = 120) -> str:
    snippet = " ".join(str(text or "").split())
    return compact_text(snippet, limit)


def print_entries(entries: list[dict], *, receipt_mode: bool = False) -> None:
    if not entries:
        print("no registered thread memories")
        return
    for entry in entries:
        size = entry.get("rollout_size") or 0
        size_mb = int(size) / (1024 * 1024) if size else 0
        print(
            f"- {entry.get('thread_key')} | {entry.get('title')} | {entry.get('message_count')} messages | {size_mb:.1f} MB"
        )
        if entry.get("project_label"):
            print(
                f"  project: {entry.get('project_label')} ({', '.join(entry.get('project_tags', [])[:8])})"
            )
        print(f"  workspace: {entry.get('paths', {}).get('workspace')}")
        if entry.get("summary"):
            print(f"  summary: {compact_text(entry['summary'], 220)}")
        if entry.get("keywords"):
            print(f"  keywords: {', '.join(entry.get('keywords', [])[:12])}")
        if entry.get("index_hits"):
            print("  source receipts:" if receipt_mode else "  index hits:")
            for hit in entry.get("index_hits", [])[:3]:
                if receipt_mode:
                    snippet = _search_receipt_snippet(hit.get("snippet"))
                    print(
                        f"    - line {hit.get('line')} | {hit.get('role')}: {snippet}"
                    )
                else:
                    print(
                        f"    - line {hit.get('line')} | {hit.get('role')} | score {hit.get('score')}: {hit.get('snippet')}"
                    )
            if receipt_mode:
                print("  next: reopen/deepen source before quoting or making claims.")


def safe_registry_search_payload(
    *,
    registry_path: Path,
    query_terms: list[str],
    matches: list[dict],
    warnings: list[dict],
) -> dict[str, Any]:
    safe_matches: list[dict[str, Any]] = []
    for entry in matches:
        index_hits = [
            hit for hit in entry.get("index_hits") or [] if isinstance(hit, dict)
        ][:3]
        safe_matches.append(
            {
                "thread": {
                    key: value
                    for key, value in {
                        "thread_key": entry.get("thread_key"),
                        "title": compact_text(str(entry.get("title") or ""), 120),
                        "workspace_name": compact_text(str(entry.get("workspace_name") or ""), 90),
                        "source_provider": entry.get("source_provider"),
                    }.items()
                    if value not in (None, "", [])
                },
                "score": entry.get("score"),
                "index_hit_count": len(index_hits),
                "index_hits": [
                    {
                        key: value
                        for key, value in {
                            "source": hit.get("source"),
                            "message_id": hit.get("message_id") or hit.get("id"),
                            "line": hit.get("line"),
                            "role": hit.get("role"),
                            "phase": hit.get("phase") or "",
                            "score": hit.get("rank_score") or hit.get("score"),
                            "snippet": compact_text(str(hit.get("snippet") or ""), 220),
                            "source_route": {
                                "kind": "registry_search_diagnostic_hit",
                                "thread_key": entry.get("thread_key"),
                                "message_id": hit.get("message_id") or hit.get("id"),
                                "line": hit.get("line"),
                                "boundary": "use_aippocampus_search_all_for_foreground_reopen_action",
                            },
                        }.items()
                        if value not in (None, "", [], {})
                    }
                    for hit in index_hits
                ],
            }
        )
    return redact_private_paths(
        {
            "kind": "aippocampus_registry_search_diagnostic",
            "ok": bool(safe_matches),
            "status": "ok" if safe_matches else "no_matches",
            "registry": str(registry_path),
            "search_scope": "registry_metadata_and_index_diagnostic",
            "query_terms": query_terms,
            "matches": safe_matches,
            "match_count": len(safe_matches),
            "warnings": warnings,
            "safe_alternative_command": (
                'aippocampus search --all "' + " ".join(query_terms) + '" --json'
                if query_terms
                else 'aippocampus search --all "{distinctive_phrase}" --json'
            ),
            "diagnostic_entries_command": (
                'aippocampus registry search "'
                + " ".join(query_terms)
                + '" --json --redact-paths --diagnostic-entries'
                if query_terms
                else 'aippocampus registry search "{distinctive_phrase}" --json --redact-paths --diagnostic-entries'
            ),
            "output_boundary": "diagnostic_summary_not_foreground_recall",
            "source_boundary": {
                "authority": "direction_only",
                "registry_search_is_diagnostic": True,
                "source_reopen_required_before_claim": True,
                "use_search_all_for_foreground_reopen": True,
                "search_miss_is_not_absence_of_memory": not bool(safe_matches),
            },
            "privacy": {
                "raw_registry_entries_emitted": False,
                "paths_included": False,
                "session_meta_emitted": False,
                "raw_source_snippets_emitted": False,
                "capped_source_snippets_emitted": bool(safe_matches),
            },
        }
    )


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    public_import_conversation = _subcommand_index(raw_args, "register-source") is not None
    usage_exit = maybe_handle_import_conversation_usage(raw_args)
    if usage_exit is not None:
        return usage_exit
    parser = argparse.ArgumentParser(
        prog="aippocampus import conversation"
        if public_import_conversation
        else "aippocampus registry"
    )
    parser.add_argument(
        "--registry-dir",
        help="Defaults to $AIPPOCAMPUS_REGISTRY_DIR or $CODEX_HOME/aippocampus-registry.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register")
    register.add_argument("--cwd", default=os.getcwd())
    register.add_argument("--vault")
    register.add_argument("--dashboard-note")
    register.add_argument("--dashboard-html")
    register.add_argument("--build-index", action="store_true")
    register.add_argument("--provider", choices=PROVIDER_CHOICES, default="codex")
    register.add_argument("--json", action="store_true", dest="json_output")

    register_rollout = sub.add_parser("register-rollout")
    register_rollout.add_argument("--rollout", required=True)
    register_rollout.add_argument("--provider", choices=PROVIDER_CHOICES, default="codex")
    register_rollout.add_argument("--cwd", help="Override the workspace/project path stored in session_meta.")
    register_rollout.add_argument("--title")
    register_rollout.add_argument(
        "--project", help="Human project label for grouping related threads."
    )
    register_rollout.add_argument(
        "--tag", action="append", default=[], help="Extra project/thread tag. Can be repeated."
    )
    register_rollout.add_argument(
        "--build-index",
        action="store_true",
        help="Also build the heavier SQLite/RAG-lite index in the registry thread store.",
    )
    register_rollout.add_argument("--json", action="store_true", dest="json_output")

    register_source = sub.add_parser(
        "register-source",
        prog="aippocampus import conversation",
        description=(
            "Preview an explicit conversation transcript before registering it as "
            "source-backed memory. Start with --dry-run --json; no registry write "
            "happens until you rerun without --dry-run."
        ),
        epilog=(
            "Safe first step:\n"
            "  aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --dry-run --json\n\n"
            "Boundary:\n"
            "  The input file stays local operator material. AIppocampus stores a "
            "source-backed clean-source import only after the explicit non-dry-run "
            "command, and local paths are redacted by default in foreground output."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    register_source.add_argument("--input", "--source", dest="source", required=True)
    register_source.add_argument(
        "--provider",
        "--format",
        dest="provider",
        choices=PROVIDER_CHOICES,
        required=True,
    )
    register_source.add_argument("--cwd", help="Override the workspace/project path stored in session_meta.")
    register_source.add_argument("--title")
    register_source.add_argument(
        "--project", help="Human project label for grouping related threads."
    )
    register_source.add_argument(
        "--tag", action="append", default=[], help="Extra project/thread tag. Can be repeated."
    )
    register_source.add_argument(
        "--build-index",
        action="store_true",
        help="Also build the heavier SQLite/RAG-lite index in the registry thread store.",
    )
    register_source.add_argument("--dry-run", action="store_true")
    register_source.add_argument("--json", action="store_true", dest="json_output")

    scan = sub.add_parser("scan-sessions")
    scan.add_argument(
        "--build-index",
        action="store_true",
        help="Also build SQLite/RAG-lite indexes for newly registered sessions.",
    )
    scan.add_argument(
        "--refresh", action="store_true", help="Refresh sessions that are already registered."
    )
    scan.add_argument(
        "--max", type=int, help="Maximum number of sessions to register, newest first."
    )
    scan.add_argument(
        "--cwd-filter", help="Only include sessions whose recorded cwd contains this text."
    )
    scan.add_argument("--project", help="Project label to attach to all matched sessions.")
    scan.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Extra tag to attach to all matched sessions. Can be repeated.",
    )
    scan.add_argument("--provider", choices=PROVIDER_CHOICES, default="codex")
    scan.add_argument("--dry-run", action="store_true")
    scan.add_argument(
        "--hook-seen-only",
        action="store_true",
        help="Only include sessions previously observed by the prompt hook ledger.",
    )
    scan.add_argument(
        "--hook-seen-ledger",
        help="Private hook-seen thread ledger path. Defaults beside the registry JSON.",
    )
    scan.add_argument("--json", action="store_true", dest="json_output")

    reconcile_hook_seen = sub.add_parser("reconcile-hook-seen")
    reconcile_hook_seen.add_argument(
        "--build-index", action="store_true",
        help="Also build heavier SQLite/RAG-lite indexes. Default is clean-source only."
    )
    reconcile_hook_seen.add_argument("--max", type=int)
    reconcile_hook_seen.add_argument("--provider", choices=PROVIDER_CHOICES, default="codex")
    reconcile_hook_seen.add_argument("--dry-run", action="store_true")
    reconcile_hook_seen.add_argument("--hook-seen-ledger")
    reconcile_hook_seen.add_argument(
        "--stale-after-seconds", type=int, default=DEFAULT_HOOK_SEEN_STALE_AFTER_SECONDS,
        help="Mark non-discoverable hook-seen rows older than this as stale.",
    )
    reconcile_hook_seen.add_argument(
        "--include-private-keys", action="store_true",
        help="Local diagnostic: include raw thread keys and local paths in output.",
    )
    reconcile_hook_seen.add_argument("--json", action="store_true", dest="json_output")

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--json", action="store_true", dest="json_output")
    list_cmd.add_argument("--redact-paths", action="store_true")

    search = sub.add_parser("search")
    search.add_argument("terms", nargs="+")
    search.add_argument("--max", type=int, default=8)
    search.add_argument(
        "--metadata-only",
        action="store_true",
        help="Only search registry metadata; skip registered SQLite indexes.",
    )
    search.add_argument(
        "--search-budget", choices=("default", "deep"), default="default",
        help="Use the bounded default search budget or the larger diagnostic budget.",
    )
    search.add_argument(
        "--diagnostic-entries",
        action="store_true",
        help="Local diagnostic: emit raw registry-entry shaped matches. Default JSON is a compact safe summary.",
    )
    search.add_argument("--json", action="store_true", dest="json_output")
    search.add_argument("--redact-paths", action="store_true")

    audit = sub.add_parser("audit")
    audit.add_argument("--json", action="store_true", dest="json_output")
    audit.add_argument("--include-paths", action="store_true")

    show = sub.add_parser("show")
    show.add_argument("thread_key")
    show.add_argument("--json", action="store_true", dest="json_output")
    show.add_argument("--redact-paths", action="store_true")

    args = parser.parse_args(raw_args)
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    json_path, md_path = registry_paths(registry_dir)

    if args.command == "register":
        try:
            result = register_current_thread(
                Path(args.cwd),
                vault=Path(args.vault) if args.vault else None,
                dashboard_note=Path(args.dashboard_note) if args.dashboard_note else None,
                dashboard_html=Path(args.dashboard_html) if args.dashboard_html else None,
                registry_dir=registry_dir,
                build_index=args.build_index,
                provider=create_conversation_provider(args.provider, codex_home_dir=codex_home()),
            )
        except RegistryWriteBusyError as exc:
            return report_registry_writer_busy(exc, json_output=args.json_output)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"registered: {result['entry']['thread_key']}")
            print(f"registry: {result['registry_json']}")
            print(f"markdown: {result['registry_markdown']}")
        return 0

    if args.command == "register-rollout":
        try:
            result = register_rollout_thread(
                Path(args.rollout),
                cwd=Path(args.cwd) if args.cwd else None,
                title=args.title,
                project=args.project,
                tags=args.tag,
                registry_dir=registry_dir,
                build_index=args.build_index,
                provider=provider_for_explicit_source(args.provider, Path(args.rollout)),
            )
        except RegistryWriteBusyError as exc:
            return report_registry_writer_busy(exc, json_output=args.json_output)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"registered rollout: {result['entry']['thread_key']}")
            print(f"project: {result['entry'].get('project_label')}")
            print(f"registry: {result['registry_json']}")
            print(f"clean source: {result['entry'].get('paths', {}).get('clean_source_dir')}")
        return 0

    if args.command == "register-source":
        source = Path(args.source)
        try:
            result = register_source_thread(
                source,
                provider=provider_for_explicit_source(args.provider, source),
                cwd=Path(args.cwd) if args.cwd else None,
                title=args.title,
                project=args.project,
                tags=args.tag,
                registry_dir=registry_dir,
                build_index=args.build_index,
                dry_run=args.dry_run,
            )
        except RegistryWriteBusyError as exc:
            return report_registry_writer_busy(exc, json_output=args.json_output)
        except GenericJsonlValidationError as exc:
            payload = generic_validation_error_payload(exc)
            if args.json_output:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(render_import_conversation_error(payload), file=sys.stderr)
            return cli_exit_code_for_error_code(exc.code)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            verb = "would register source" if args.dry_run else "registered source"
            print(f"{verb}: {result['thread_key']}")
            print(f"provider: {result['source_provider']}")
            print(f"registry: {result['registry_json']}")
            if not args.dry_run:
                print(f"clean source: {result['entry'].get('paths', {}).get('clean_source_dir')}")
        return 0

    if args.command == "scan-sessions":
        try:
            result = scan_session_rollouts(
                registry_dir=registry_dir,
                build_index=args.build_index,
                refresh=args.refresh,
                max_count=args.max,
                cwd_filter=args.cwd_filter,
                project=args.project,
                tags=args.tag,
                dry_run=args.dry_run,
                hook_seen_only=args.hook_seen_only,
                hook_seen_ledger=Path(args.hook_seen_ledger) if args.hook_seen_ledger else None,
                provider=create_conversation_provider(args.provider, codex_home_dir=codex_home()),
            )
        except RegistryWriteBusyError as exc:
            return report_registry_writer_busy(exc, json_output=args.json_output)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            verb = "would register" if args.dry_run else "registered"
            print(f"{verb}: {result['count']} session(s)")
            print(f"registry: {result['registry']}")
            rows = result["planned"] if args.dry_run else result["registered"]
            for item in rows[:20]:
                print(
                    f"- {item.get('thread_key')} | {item.get('title') or item.get('timestamp')} | {item.get('cwd') or item.get('paths', {}).get('workspace')}"
                )
        return 0

    if args.command == "reconcile-hook-seen":
        try:
            result = reconcile_hook_seen_threads(
                registry_dir=registry_dir,
                build_index=args.build_index,
                max_count=args.max,
                dry_run=args.dry_run,
                hook_seen_ledger=Path(args.hook_seen_ledger) if args.hook_seen_ledger else None,
                stale_after_seconds=args.stale_after_seconds,
                include_private_keys=args.include_private_keys,
                provider=create_conversation_provider(args.provider, codex_home_dir=codex_home()),
            )
        except RegistryWriteBusyError as exc:
            return report_registry_writer_busy(exc, json_output=args.json_output)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            verb = "would register" if args.dry_run else "registered"
            count = (
                result["metrics"]["planned_clean_source_registration_count"]
                if args.dry_run
                else result["metrics"]["automatic_clean_source_registration_count"]
            )
            print(f"{verb}: {count} hook-seen session(s)")
            print(f"registry: {result['registry']}")
            print(f"ledger: {result['ledger']}")
            print(
                "states: "
                + ", ".join(
                    f"{key}={value}"
                    for key, value in result["metrics"]["state_counts"].items()
                )
            )
            if result["candidates"]:
                print("remaining attention:")
                for item in result["candidates"][:20]:
                    print(
                        f"- {item.get('thread_ref')} | {item.get('state')} | {item.get('diagnostic')}"
                    )
        return 0

    registry = load_registry(json_path)
    if args.command == "list":
        if args.redact_paths:
            registry = redact_private_paths(registry)
        if args.json_output:
            print(json.dumps(registry, ensure_ascii=False, indent=2))
        else:
            print(f"registry: {json_path}")
            print_entries(registry.get("threads", []))
        return 0

    if args.command == "search":
        from aippocampus_runtime.recall.query_policy import split_query_terms

        query_terms = split_query_terms(args.terms)
        search_budget = REGISTRY_SEARCH_DEEP_BUDGET if args.search_budget == "deep" else None
        scored = []
        warnings = []
        for entry in registry.get("threads", []):
            score = entry_search_score(entry, query_terms)
            index_hits = []
            if not args.metadata_only:
                deep_result = deep_search_entry_result(entry, query_terms, search_budget=search_budget)
                score += float(deep_result.get("score") or 0.0)
                index_hits = list(deep_result.get("hits") or [])
                for warning in deep_result.get("warnings") or []:
                    item = dict(warning)
                    item["thread_key"] = entry.get("thread_key")
                    warnings.append(item)
            if score > 0:
                item = dict(entry)
                item["score"] = round(score, 3)
                item["index_hits"] = index_hits
                scored.append(item)
        scored.sort(key=lambda item: (-item["score"], item.get("updated_at") or ""))
        scored = scored[: args.max]
        if args.json_output:
            if args.diagnostic_entries:
                payload = {
                    "kind": "aippocampus_registry_search_diagnostic_entries",
                    "output_boundary": "local_operator_diagnostic_raw_registry_entries",
                    "safe_alternative_command": 'aippocampus search --all "' + " ".join(query_terms) + '" --json',
                    "privacy": {
                        "raw_registry_entries_emitted": True,
                        "paths_included": not args.redact_paths,
                        "session_meta_emitted": True,
                    },
                    "registry": str(json_path),
                    "matches": scored,
                    "warnings": warnings,
                }
            else:
                payload = safe_registry_search_payload(
                    registry_path=json_path,
                    query_terms=query_terms,
                    matches=scored,
                    warnings=warnings,
                )
            if args.redact_paths or not args.diagnostic_entries:
                payload = redact_private_paths(payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"registry: {json_path}")
            print_entries(scored, receipt_mode=True)
            if warnings:
                print("search warnings:")
                for warning in warnings[:8]:
                    print(
                        f"- {warning.get('thread_key') or '(unknown)'} | "
                        f"{warning.get('stage')} | {warning.get('error_type')}: {warning.get('message')}"
                    )
        return 0 if scored else 1

    if args.command == "audit":
        from aippocampus_runtime.registry.reachability_audit import (
            registry_source_reachability_audit,
            render_reachability_audit,
        )

        report = registry_source_reachability_audit(
            registry_dir=registry_dir,
            include_paths=bool(args.include_paths),
        )
        if args.json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_reachability_audit(report))
        return 0

    if args.command == "show":
        match = next(
            (
                entry
                for entry in registry.get("threads", [])
                if entry.get("thread_key") == args.thread_key
            ),
            None,
        )
        if not match:
            print(
                json.dumps(
                    {
                        "error": "thread not found",
                        "thread_key": args.thread_key,
                        "registry": str(json_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        if args.json_output:
            if args.redact_paths:
                match = redact_private_paths(match)
            print(json.dumps(match, ensure_ascii=False, indent=2))
        else:
            print_entries([match])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
