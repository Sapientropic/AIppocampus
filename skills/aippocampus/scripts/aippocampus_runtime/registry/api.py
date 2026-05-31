#!/usr/bin/env python3
"""Machine-wide registry for discoverable thread-memory indexes."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
from aippocampus_runtime.core import (
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
from aippocampus_runtime.registry.provider import current_thread_build_cmd, thread_key_for
from aippocampus_runtime.registry.search import (
    REGISTRY_SEARCH_DEEP_BUDGET,
    clean_hit_rank_score,
    deep_search_entry,
    deep_search_entry_result,
    entry_search_score,
    search_noise_reason,
)
from aippocampus_runtime.registry.store import (
    REGISTRY_SCHEMA_VERSION,
    RegistryReadError,
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
    upsert_thread,
)
from conversation_sources import (
    PROVIDER_CHOICES,
    ConversationProvider,
    create_conversation_provider,
)

__all__ = [
    "REGISTRY_SCHEMA_VERSION",
    "RegistryReadError",
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
    "scan_session_rollouts",
    "entry_search_score",
    "search_noise_reason",
    "clean_hit_rank_score",
    "deep_search_entry",
    "deep_search_entry_result",
]

SCRIPT_DIR = Path(__file__).resolve().parents[2]


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def unique_preserve(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = re.sub(r"\s+", " ", str(item)).strip()
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def project_key_for(cwd: Path | None, label: str | None = None) -> str:
    if cwd:
        digest = hashlib.sha1(str(cwd).casefold().encode("utf-8")).hexdigest()[:12]
        return f"project:{safe_slug(label or cwd.name or 'workspace')}:{digest}"
    digest = hashlib.sha1((label or "unknown").casefold().encode("utf-8")).hexdigest()[:12]
    return f"project:{safe_slug(label or 'unknown')}:{digest}"


def project_fields(
    cwd: Path | None, *, project: str | None = None, tags: list[str] | None = None
) -> dict:
    label = project or (cwd.name if cwd else "unknown")
    project_tags = unique_preserve([label, *(tags or [])], limit=24)
    return {
        "project_key": project_key_for(cwd, label),
        "project_label": label,
        "project_tags": project_tags,
    }


def anchor_summary(anchors: list[dict]) -> tuple[list[str], list[str], str]:
    titles = unique_preserve([anchor.get("title") or "" for anchor in anchors], limit=20)
    keywords: list[str] = []
    notes: list[str] = []
    for anchor in anchors:
        keywords.extend(anchor.get("keywords") or [])
        notes.extend(anchor.get("notes") or [])
    summary = compact_text(" ".join(notes[:6]), 700) if notes else ""
    return titles, unique_preserve(keywords, limit=32), summary


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
        "source_provider": session_meta.get("source") or clean_manifest.get("source_provider") or active_provider.name,
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
    registry = upsert_thread(load_registry(json_path), entry)
    save_registry(registry, json_path, md_path)
    return {
        "entry": entry,
        "registry_json": str(json_path),
        "registry_markdown": str(md_path),
        "thread_count": len(registry["threads"]),
    }


def register_rollout_thread(
    rollout: Path,
    *,
    cwd: Path | None = None,
    title: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    registry_dir: Path | None = None,
    build_index: bool = False,
    provider: ConversationProvider | None = None,
) -> dict:
    """Register an arbitrary rollout into the machine-wide memory registry.

    A single workspace can have many Codex sessions. Writing every old session
    back into that workspace's `.aippocampus/` would make them overwrite each
    other, so external rollout registration stores per-thread artifacts under
    the registry. The workspace path remains metadata for project grouping.
    """

    rollout = rollout.resolve()
    active_provider = provider or codex_provider(codex_home())
    meta = active_provider.read_metadata(rollout) or {}
    if cwd is None:
        cwd_value = meta.get("cwd")
        cwd = Path(cwd_value) if cwd_value else rollout.parent
    cwd = cwd.resolve()
    thread_key = active_provider.thread_key(rollout, meta)
    store = thread_store_dir(thread_key, registry_dir)
    clean_source_dir = store / "clean-source"
    index_dir = store / "index"
    clean_source_dir.mkdir(parents=True, exist_ok=True)

    clean_manifest = run_json(
        [
            sys.executable,
            str(SCRIPT_DIR / "build_clean_source.py"),
            "--cwd",
            str(cwd),
            "--provider",
            active_provider.name,
            "--rollout",
            str(rollout),
            "--output-dir",
            str(clean_source_dir),
            "--json",
        ]
    )
    index_manifest: dict = {}
    if build_index:
        index_dir.mkdir(parents=True, exist_ok=True)
        index_manifest = run_json(
            [
                sys.executable,
                str(SCRIPT_DIR / "build_index.py"),
                "--cwd",
                str(cwd),
                "--provider",
                active_provider.name,
                "--rollout",
                str(rollout),
                "--output-dir",
                str(index_dir),
                "--json",
            ]
        )
    else:
        index_manifest = load_json(index_dir / "manifest.json")

    anchors_path = cwd / "thread-anchors.md"
    anchors = parse_anchor_file(anchors_path)
    anchor_titles, keywords, summary = anchor_summary(anchors)
    project_meta = project_fields(cwd, project=project, tags=tags)
    timestamp = meta.get("timestamp") or clean_manifest.get("created_at") or ""
    display_title = (
        title
        or f"{project_meta['project_label']} · {timestamp or thread_key.split(':', 1)[-1][:8]}"
    )
    clean_outputs = clean_manifest.get("outputs") or {}
    index_outputs = index_manifest.get("outputs") or {}
    sqlite_path = resolve_sqlite_index_path(
        Path(index_outputs.get("sqlite_current") or index_outputs.get("sqlite") or index_dir / "source_index.sqlite")
    )
    graph_path = Path(index_outputs.get("graph_json") or index_dir / "graph.json")
    messages_path = Path(index_outputs.get("messages_jsonl") or index_dir / "messages.jsonl")
    rag = index_manifest.get("rag") or (index_manifest.get("sqlite") or {}).get("rag") or {}
    stat = rollout.stat()

    entry = {
        "thread_key": thread_key,
        "title": display_title,
        "workspace_name": cwd.name,
        **project_meta,
        "updated_at": now_utc(),
        "created_at": clean_manifest.get("created_at"),
        "source_provider": meta.get("source") or clean_manifest.get("source_provider") or active_provider.name,
        "session_meta": meta,
        "artifact_scope": "registry_thread_store",
        "message_count": index_manifest.get("message_count") or clean_manifest.get("message_count"),
        "clean_message_count": clean_manifest.get("message_count"),
        "clean_turn_count": clean_manifest.get("turn_count"),
        "rollout_size": stat.st_size,
        "anchor_count": len(anchors),
        "anchor_titles": anchor_titles,
        "keywords": keywords,
        "summary": summary,
        "health": {
            "ok": True,
            "index_stale": False if index_manifest else None,
            "checkpoint_due": None,
            "graphify_stale": None,
            "recommended_actions": [],
        },
        "capabilities": {
            "clean_source": True,
            "clean_source_schema": clean_manifest.get("schema_version"),
            "sqlite_fts": (index_manifest.get("sqlite") or {}).get("fts_enabled"),
            "rag_chunks": rag.get("chunk_count"),
            "rag_fts": rag.get("fts_enabled"),
            "graph_nodes": (index_manifest.get("graph") or {}).get("node_count"),
            "graph_edges": (index_manifest.get("graph") or {}).get("edge_count"),
        },
        "paths": {
            "workspace": str(cwd),
            "rollout": str(rollout),
            "anchors": str(anchors_path) if anchors_path.exists() else None,
            "index_dir": str(index_dir) if index_dir.exists() else None,
            "messages_jsonl": str(messages_path) if messages_path.exists() else None,
            "sqlite": str(sqlite_path) if sqlite_path.exists() else None,
            "graph_json": str(graph_path) if graph_path.exists() else None,
            "clean_source_dir": str(clean_source_dir),
            "clean_source_messages_jsonl": clean_outputs.get("messages_jsonl"),
            "clean_source_turns_jsonl": clean_outputs.get("turns_jsonl"),
            "registry_thread_store": str(store),
            "vault": None,
            "dashboard_note": None,
            "dashboard_html": None,
        },
    }

    json_path, md_path = registry_paths(registry_dir)
    registry = upsert_thread(load_registry(json_path), entry)
    save_registry(registry, json_path, md_path)
    return {
        "entry": entry,
        "registry_json": str(json_path),
        "registry_markdown": str(md_path),
        "thread_count": len(registry["threads"]),
        "created_artifacts": {
            "clean_source": str(clean_source_dir),
            "index": str(index_dir) if build_index else None,
        },
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
    provider: ConversationProvider | None = None,
) -> dict:
    json_path, _ = registry_paths(registry_dir)
    existing = {entry.get("thread_key") for entry in load_registry(json_path).get("threads", [])}
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
        "planned": planned,
        "registered": registered,
        "count": len(planned) if dry_run else len(registered),
    }


def print_entries(entries: list[dict]) -> None:
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
            print("  index hits:")
            for hit in entry.get("index_hits", [])[:3]:
                print(
                    f"    - line {hit.get('line')} | {hit.get('role')} | score {hit.get('score')}: {hit.get('snippet')}"
                )


def main() -> int:
    parser = argparse.ArgumentParser()
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
    register_rollout.add_argument(
        "--cwd", help="Override the workspace/project path stored in session_meta."
    )
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
    scan.add_argument("--json", action="store_true", dest="json_output")

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
    search.add_argument("--json", action="store_true", dest="json_output")
    search.add_argument("--redact-paths", action="store_true")

    show = sub.add_parser("show")
    show.add_argument("thread_key")
    show.add_argument("--json", action="store_true", dest="json_output")
    show.add_argument("--redact-paths", action="store_true")

    args = parser.parse_args()
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    json_path, md_path = registry_paths(registry_dir)

    if args.command == "register":
        result = register_current_thread(
            Path(args.cwd),
            vault=Path(args.vault) if args.vault else None,
            dashboard_note=Path(args.dashboard_note) if args.dashboard_note else None,
            dashboard_html=Path(args.dashboard_html) if args.dashboard_html else None,
            registry_dir=registry_dir,
            build_index=args.build_index,
            provider=create_conversation_provider(args.provider, codex_home_dir=codex_home()),
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"registered: {result['entry']['thread_key']}")
            print(f"registry: {result['registry_json']}")
            print(f"markdown: {result['registry_markdown']}")
        return 0

    if args.command == "register-rollout":
        result = register_rollout_thread(
            Path(args.rollout),
            cwd=Path(args.cwd) if args.cwd else None,
            title=args.title,
            project=args.project,
            tags=args.tag,
            registry_dir=registry_dir,
            build_index=args.build_index,
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"registered rollout: {result['entry']['thread_key']}")
            print(f"project: {result['entry'].get('project_label')}")
            print(f"registry: {result['registry_json']}")
            print(f"clean source: {result['entry'].get('paths', {}).get('clean_source_dir')}")
        return 0

    if args.command == "scan-sessions":
        result = scan_session_rollouts(
            registry_dir=registry_dir,
            build_index=args.build_index,
            refresh=args.refresh,
            max_count=args.max,
            cwd_filter=args.cwd_filter,
            project=args.project,
            tags=args.tag,
            dry_run=args.dry_run,
            provider=create_conversation_provider(args.provider, codex_home_dir=codex_home()),
        )
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
            payload = {"registry": str(json_path), "matches": scored, "warnings": warnings}
            if args.redact_paths:
                payload = redact_private_paths(payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"registry: {json_path}")
            print_entries(scored)
            if warnings:
                print("search warnings:")
                for warning in warnings[:8]:
                    print(
                        f"- {warning.get('thread_key') or '(unknown)'} | "
                        f"{warning.get('stage')} | {warning.get('error_type')}: {warning.get('message')}"
                    )
        return 0 if scored else 1

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
