"""Registration helpers for explicit provider transcript sources."""

from __future__ import annotations

import sys
from pathlib import Path

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
from aippocampus_runtime.core import (
    cli_error_class_for_error_code,
    codex_home,
    codex_provider,
    now_utc,
    parse_anchor_file,
)
from aippocampus_runtime.registry.common import (
    anchor_summary,
    project_fields,
    run_json,
)
from aippocampus_runtime.registry.store import (
    load_json,
    load_registry,
    registry_paths,
    thread_store_dir,
    update_registry,
    upsert_thread,
)
from conversation_sources import (
    ConversationProvider,
    GenericConversationProvider,
    GenericJsonlValidationError,
    create_conversation_provider,
    normalize_provider_name,
)


def provider_for_explicit_source(provider_name: str, source: Path) -> ConversationProvider:
    provider = normalize_provider_name(provider_name)
    if provider == "generic-jsonl":
        return GenericConversationProvider(source)
    return create_conversation_provider(provider, codex_home_dir=codex_home())


def generic_validation_error_payload(exc: GenericJsonlValidationError) -> dict:
    return {
        "ok": False,
        "error": {
            "code": exc.code,
            "class": cli_error_class_for_error_code(exc.code),
            "message": str(exc),
            "line": exc.line,
            "details": exc.details,
        },
        "data": None,
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
    """Register an explicit provider source into the machine-wide registry.

    The historical name says "rollout" because Codex was the first provider.
    The implementation is provider-aware; new CLI surfaces should prefer
    `register-source` / `aippocampus import conversation`.
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
            "-m", "aippocampus_runtime.source.clean_source",
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
                "-m", "aippocampus_runtime.recall.index_builder",
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
        Path(
            index_outputs.get("sqlite_current")
            or index_outputs.get("sqlite")
            or index_dir / "source_index.sqlite"
        )
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
        "source_provider": clean_manifest.get("source_provider")
        or meta.get("source")
        or active_provider.name,
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
        "created_artifacts": {
            "clean_source": str(clean_source_dir),
            "index": str(index_dir) if build_index else None,
        },
    }


def register_source_thread(
    source: Path,
    *,
    provider: ConversationProvider,
    cwd: Path | None = None,
    title: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    registry_dir: Path | None = None,
    build_index: bool = False,
    dry_run: bool = False,
) -> dict:
    """Validate and optionally register an explicit provider transcript."""

    source = source.resolve()
    meta = provider.read_metadata(source) or {}
    messages, turns = provider.read_normalized_messages(source, include_tools=False)
    if cwd is None:
        cwd_value = meta.get("cwd")
        cwd = Path(cwd_value) if cwd_value else source.parent
    cwd = cwd.resolve()
    thread_key = provider.thread_key(source, meta)
    json_path, _ = registry_paths(registry_dir)
    existing = {
        entry.get("thread_key")
        for entry in load_registry(json_path).get("threads", [])
    }
    plan = {
        "ok": True,
        "dry_run": dry_run,
        "source": str(source),
        "source_provider": provider.name,
        "thread_key": thread_key,
        "cwd": str(cwd),
        "project": project or cwd.name,
        "message_count": len(messages),
        "turn_count": len(turns),
        "already_registered": thread_key in existing,
        "registry_json": str(json_path),
    }
    if dry_run:
        return plan
    result = register_rollout_thread(
        source,
        cwd=cwd,
        title=title,
        project=project,
        tags=tags,
        registry_dir=registry_dir,
        build_index=build_index,
        provider=provider,
    )
    return {**plan, "dry_run": False, **result}
