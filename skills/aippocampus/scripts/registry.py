#!/usr/bin/env python3
"""Machine-wide registry for discoverable thread-memory indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from aippocampuslib import (
    codex_home,
    compact_text,
    default_thread_clean_source_dir,
    default_thread_index_dir,
    is_injected_instruction_text,
    iter_rollouts,
    locate_rollout,
    now_utc,
    parse_anchor_file,
    public_session_meta,
    read_session_meta,
    thread_key_from_rollout as lib_thread_key_from_rollout,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REGISTRY_SCHEMA_VERSION = 1


def default_registry_dir() -> Path:
    env = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
    if env:
        return Path(env)
    legacy_env = os.environ.get("THREAD_MEMORY_REGISTRY_DIR")
    if legacy_env:
        return Path(legacy_env)
    return codex_home() / "aippocampus-registry"


def registry_paths(registry_dir: Path | None = None) -> tuple[Path, Path]:
    root = (registry_dir or default_registry_dir()).resolve()
    return root / "threads.json", root / "threads.md"


def registry_root(registry_dir: Path | None = None) -> Path:
    return (registry_dir or default_registry_dir()).resolve()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def safe_slug(value: str, fallback: str = "thread") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip()
    value = re.sub(r"\s+", "-", value)
    value = value.rstrip(".- ")
    return value[:120] or fallback


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


def project_fields(cwd: Path | None, *, project: str | None = None, tags: list[str] | None = None) -> dict:
    label = project or (cwd.name if cwd else "unknown")
    project_tags = unique_preserve([label, *(tags or [])], limit=24)
    return {
        "project_key": project_key_for(cwd, label),
        "project_label": label,
        "project_tags": project_tags,
    }


def thread_store_dir(thread_key: str, registry_dir: Path | None = None) -> Path:
    return registry_root(registry_dir) / "threads" / safe_slug(thread_key)


def load_registry(path: Path) -> dict:
    registry = load_json(path)
    if not registry:
        registry = {"schema_version": REGISTRY_SCHEMA_VERSION, "updated_at": None, "threads": []}
    registry.setdefault("schema_version", REGISTRY_SCHEMA_VERSION)
    registry.setdefault("threads", [])
    return registry


def upsert_thread(registry: dict, entry: dict) -> dict:
    threads = [item for item in registry.get("threads", []) if item.get("thread_key") != entry.get("thread_key")]
    threads.append(entry)
    threads.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    registry["threads"] = threads
    registry["updated_at"] = now_utc()
    return registry


def render_registry_markdown(registry: dict) -> str:
    lines = [
        "# Thread Memory Registry",
        "",
        "Machine-wide index of local Codex thread memories. Use this as the first discovery step in a new thread.",
        "",
        f"- Updated: `{registry.get('updated_at')}`",
        f"- Threads: `{len(registry.get('threads', []))}`",
        "",
    ]
    for entry in registry.get("threads", []):
        health = entry.get("health") or {}
        caps = entry.get("capabilities") or {}
        paths = entry.get("paths") or {}
        lines.extend([
            f"## {entry.get('title') or entry.get('workspace_name') or entry.get('thread_key')}",
            "",
            f"- Thread key: `{entry.get('thread_key')}`",
            f"- Updated: `{entry.get('updated_at')}`",
            f"- Project: `{entry.get('project_label') or entry.get('workspace_name')}`",
            f"- Workspace: `{paths.get('workspace')}`",
            f"- Messages: `{entry.get('message_count')}`",
            f"- Size: `{entry.get('rollout_size')}` bytes",
            f"- Anchors: `{entry.get('anchor_count')}`",
            f"- Health: `{'OK' if health.get('ok') else 'Needs maintenance'}`",
            f"- RAG-lite chunks: `{caps.get('rag_chunks')}`",
            f"- SQLite: `{paths.get('sqlite')}`",
        ])
        if paths.get("dashboard_html"):
            lines.append(f"- Dashboard HTML: `{paths.get('dashboard_html')}`")
        if paths.get("vault"):
            lines.append(f"- Vault: `{paths.get('vault')}`")
        if entry.get("keywords"):
            lines.extend(["", "Keywords:", ""])
            lines.append(", ".join(f"`{keyword}`" for keyword in entry.get("keywords", [])[:20]))
        if entry.get("project_tags"):
            lines.extend(["", "Project tags:", ""])
            lines.append(", ".join(f"`{tag}`" for tag in entry.get("project_tags", [])[:20]))
        if entry.get("anchor_titles"):
            lines.extend(["", "Anchors:", ""])
            lines.extend(f"- {title}" for title in entry.get("anchor_titles", [])[:10])
        if entry.get("summary"):
            lines.extend(["", entry["summary"]])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def save_registry(registry: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(json_path)
    md_path.write_text(render_registry_markdown(registry), encoding="utf-8", newline="\n")


def anchor_summary(anchors: list[dict]) -> tuple[list[str], list[str], str]:
    titles = unique_preserve([anchor.get("title") or "" for anchor in anchors], limit=20)
    keywords: list[str] = []
    notes: list[str] = []
    for anchor in anchors:
        keywords.extend(anchor.get("keywords") or [])
        notes.extend(anchor.get("notes") or [])
    summary = compact_text(" ".join(notes[:6]), 700) if notes else ""
    return titles, unique_preserve(keywords, limit=32), summary


def thread_key_for(cwd: Path, manifest: dict, rollout: Path | None) -> str:
    session_id = (manifest.get("session_meta") or {}).get("id")
    if not session_id and rollout:
        session_id = (public_session_meta(read_session_meta(rollout)) or {}).get("id")
    if session_id:
        return f"session:{session_id}"
    digest = hashlib.sha1(str(cwd).casefold().encode("utf-8")).hexdigest()[:12]
    return f"workspace:{safe_slug(cwd.name)}:{digest}"


def register_current_thread(
    cwd: Path,
    *,
    vault: Path | None = None,
    dashboard_note: Path | None = None,
    dashboard_html: Path | None = None,
    registry_dir: Path | None = None,
    health: dict | None = None,
    build_index: bool = False,
) -> dict:
    cwd = cwd.resolve()
    try:
        rollout = locate_rollout(cwd, codex_home())
    except Exception:
        rollout = None
    default_index_dir = default_thread_index_dir(cwd, rollout)
    legacy_index_dir = cwd / ".aippocampus"
    index_dir = (
        default_index_dir
        if build_index or (default_index_dir / "manifest.json").exists() or not (legacy_index_dir / "manifest.json").exists()
        else legacy_index_dir
    )
    if build_index and not (index_dir / "manifest.json").exists():
        run_json([sys.executable, str(SCRIPT_DIR / "build_index.py"), "--cwd", str(cwd), "--json"])
    clean_source_dir = default_thread_clean_source_dir(cwd, rollout)
    legacy_clean_source_dir = legacy_index_dir / "clean-source"
    if not build_index and not (clean_source_dir / "manifest.json").exists() and (legacy_clean_source_dir / "manifest.json").exists():
        clean_source_dir = legacy_clean_source_dir
    if build_index and not (clean_source_dir / "manifest.json").exists():
        run_json([sys.executable, str(SCRIPT_DIR / "build_clean_source.py"), "--cwd", str(cwd), "--json"])

    manifest = load_json(index_dir / "manifest.json")
    clean_manifest = load_json(clean_source_dir / "manifest.json")
    if health is None:
        try:
            health = run_json([sys.executable, str(SCRIPT_DIR / "aippocampus_health.py"), "--cwd", str(cwd), "--json"])
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
            rollout = locate_rollout(cwd, codex_home())
        except Exception:
            rollout = None

    thread_key = thread_key_for(cwd, manifest, rollout)
    session_meta = manifest.get("session_meta") or {}
    sqlite_path = Path(manifest.get("outputs", {}).get("sqlite") or index_dir / "source_index.sqlite")
    graph_path = Path(manifest.get("outputs", {}).get("graph_json") or index_dir / "graph.json")
    messages_path = Path(manifest.get("outputs", {}).get("messages_jsonl") or index_dir / "messages.jsonl")
    rag = manifest.get("rag") or (manifest.get("sqlite") or {}).get("rag") or {}

    entry = {
        "thread_key": thread_key,
        "title": cwd.name,
        "workspace_name": cwd.name,
        **project,
        "updated_at": now_utc(),
        "created_at": manifest.get("created_at"),
        "session_meta": session_meta,
        "message_count": manifest.get("message_count") or health.get("rollout", {}).get("message_count"),
        "rollout_size": manifest.get("source_rollout_size") or health.get("rollout", {}).get("size"),
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
            "graphify_corpus": str(index_dir / "graphify-corpus") if (index_dir / "graphify-corpus").exists() else None,
            "clean_source_dir": str(clean_source_dir) if clean_source_dir.exists() else None,
            "clean_source_messages_jsonl": (clean_manifest.get("outputs") or {}).get("messages_jsonl"),
            "clean_source_turns_jsonl": (clean_manifest.get("outputs") or {}).get("turns_jsonl"),
            "vault": str(vault.resolve()) if vault else None,
            "dashboard_note": str(dashboard_note.resolve()) if dashboard_note else None,
            "dashboard_html": str(dashboard_html.resolve()) if dashboard_html else None,
        },
    }

    json_path, md_path = registry_paths(registry_dir)
    registry = upsert_thread(load_registry(json_path), entry)
    save_registry(registry, json_path, md_path)
    return {"entry": entry, "registry_json": str(json_path), "registry_markdown": str(md_path), "thread_count": len(registry["threads"])}


def thread_key_from_rollout(rollout: Path, meta: dict | None = None) -> str:
    return lib_thread_key_from_rollout(rollout, meta)


def register_rollout_thread(
    rollout: Path,
    *,
    cwd: Path | None = None,
    title: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    registry_dir: Path | None = None,
    build_index: bool = False,
) -> dict:
    """Register an arbitrary rollout into the machine-wide memory registry.

    A single workspace can have many Codex sessions. Writing every old session
    back into that workspace's `.aippocampus/` would make them overwrite each
    other, so external rollout registration stores per-thread artifacts under
    the registry. The workspace path remains metadata for project grouping.
    """

    rollout = rollout.resolve()
    meta = public_session_meta(read_session_meta(rollout))
    if cwd is None:
        cwd_value = meta.get("cwd")
        cwd = Path(cwd_value) if cwd_value else rollout.parent
    cwd = cwd.resolve()
    thread_key = thread_key_from_rollout(rollout, meta)
    store = thread_store_dir(thread_key, registry_dir)
    clean_source_dir = store / "clean-source"
    index_dir = store / "index"
    clean_source_dir.mkdir(parents=True, exist_ok=True)

    clean_manifest = run_json([
        sys.executable,
        str(SCRIPT_DIR / "build_clean_source.py"),
        "--cwd",
        str(cwd),
        "--rollout",
        str(rollout),
        "--output-dir",
        str(clean_source_dir),
        "--json",
    ])
    index_manifest: dict = {}
    if build_index:
        index_dir.mkdir(parents=True, exist_ok=True)
        index_manifest = run_json([
            sys.executable,
            str(SCRIPT_DIR / "build_index.py"),
            "--cwd",
            str(cwd),
            "--rollout",
            str(rollout),
            "--output-dir",
            str(index_dir),
            "--json",
        ])
    else:
        index_manifest = load_json(index_dir / "manifest.json")

    anchors_path = cwd / "thread-anchors.md"
    anchors = parse_anchor_file(anchors_path)
    anchor_titles, keywords, summary = anchor_summary(anchors)
    project_meta = project_fields(cwd, project=project, tags=tags)
    timestamp = meta.get("timestamp") or clean_manifest.get("created_at") or ""
    display_title = title or f"{project_meta['project_label']} · {timestamp or thread_key.split(':', 1)[-1][:8]}"
    clean_outputs = clean_manifest.get("outputs") or {}
    index_outputs = index_manifest.get("outputs") or {}
    sqlite_path = Path(index_outputs.get("sqlite") or index_dir / "source_index.sqlite")
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
) -> dict:
    json_path, _ = registry_paths(registry_dir)
    existing = {entry.get("thread_key") for entry in load_registry(json_path).get("threads", [])}
    candidates: list[tuple[float, Path, dict, str]] = []
    for rollout in iter_rollouts(codex_home()):
        meta = public_session_meta(read_session_meta(rollout))
        if cwd_filter and cwd_filter.casefold() not in str(meta.get("cwd") or "").casefold():
            continue
        thread_key = thread_key_from_rollout(rollout, meta)
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
            planned.append({"thread_key": thread_key, "rollout": str(rollout), "cwd": meta.get("cwd"), "timestamp": meta.get("timestamp")})
            continue
        result = register_rollout_thread(
            rollout,
            project=project,
            tags=tags,
            registry_dir=registry_dir,
            build_index=build_index,
        )
        registered.append(result["entry"])
    return {
        "registry": str(json_path),
        "dry_run": dry_run,
        "planned": planned,
        "registered": registered,
        "count": len(planned) if dry_run else len(registered),
    }


def entry_search_score(entry: dict, terms: list[str]) -> float:
    blob = "\n".join([
        entry.get("title") or "",
        entry.get("workspace_name") or "",
        entry.get("project_label") or "",
        entry.get("project_key") or "",
        " ".join(entry.get("project_tags") or []),
        entry.get("summary") or "",
        " ".join(entry.get("anchor_titles") or []),
        " ".join(entry.get("keywords") or []),
        json.dumps(entry.get("session_meta") or {}, ensure_ascii=False),
    ]).casefold()
    score = 0.0
    for term in terms:
        low = term.casefold()
        if not low:
            continue
        if low in (entry.get("title") or "").casefold():
            score += 8.0
        if any(low in str(keyword).casefold() for keyword in entry.get("keywords") or []):
            score += 4.0
        if low in blob:
            score += 1.5
    return score


def search_noise_reason(text: str) -> str | None:
    """Classify repeated runtime carrier text that should not dominate recall.

    This is a ranking boundary, not a deletion rule. Old indexes may already
    contain injected skill or instruction carriers, so registry search must keep
    them auditable while making real user/final-answer evidence win.
    """

    if is_injected_instruction_text(text):
        return "injected_instruction"
    return None


def clean_hit_rank_score(message: dict, score: float) -> tuple[float, str | None]:
    text = str(message.get("text") or "")
    reason = search_noise_reason(text)
    rank_score = float(score)
    if reason:
        rank_score *= 0.05
    if message.get("role") == "assistant" and str(message.get("phase") or "") == "final_answer":
        rank_score *= 1.12
    return rank_score, reason


def _search_warning(stage: str, path: str | Path, exc: Exception) -> dict:
    return {
        "stage": stage,
        "path": str(path),
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


def deep_search_entry_result(entry: dict, terms: list[str], max_hits: int = 3) -> dict:
    paths = entry.get("paths") or {}
    warnings: list[dict] = []
    clean_messages = paths.get("clean_source_messages_jsonl")
    if clean_messages:
        try:
            from search_clean_source import iter_clean_messages, score_message
            from semantic_scope_labels import load_semantic_scope_labels, merged_scope_labels, semantic_labels_for_message

            clean_hits = []
            semantic_sidecar = load_semantic_scope_labels(Path(clean_messages).parent)
            for message in iter_clean_messages(Path(clean_messages)):
                semantic_scope_labels = semantic_labels_for_message(message, semantic_sidecar)
                if semantic_scope_labels:
                    message = dict(message)
                    message["semantic_scope_labels"] = semantic_scope_labels
                    message["scope_labels"] = merged_scope_labels(list(message.get("scope_labels") or []), semantic_scope_labels)
                score = score_message(message, terms)
                if score <= 0:
                    continue
                rank_score, noise_reason = clean_hit_rank_score(message, score)
                clean_hits.append((rank_score, score, noise_reason, message))
            clean_hits.sort(key=lambda item: (-item[0], int(item[3].get("source_line") or 0)))
            if clean_hits:
                compact_hits = [
                    {
                        "source": "clean_source",
                        "id": message.get("message_id") or message.get("id"),
                        "message_id": message.get("message_id") or message.get("id"),
                        "turn_id": message.get("turn_id"),
                        "source_id": message.get("source_id"),
                        "clean_ordinal": message.get("clean_ordinal"),
                        "line": message.get("source_line"),
                        "role": message.get("role"),
                        "phase": message.get("phase") or "",
                        "turn_index": message.get("turn_index"),
                        "is_final": message.get("is_final"),
                        "scope_labels": [
                            label
                            for label in message.get("scope_labels", [])
                            if isinstance(label, str)
                        ],
                        "semantic_scope_labels": [
                            label
                            for label in message.get("semantic_scope_labels", [])
                            if isinstance(label, str)
                        ],
                        "score": round(score, 3),
                        "rank_score": round(rank_score, 3),
                        "search_noise": bool(noise_reason),
                        "noise_reason": noise_reason,
                        "snippet": compact_text(str(message.get("text") or ""), 260),
                    }
                    for rank_score, score, noise_reason, message in clean_hits[:max_hits]
                ]
                return {
                    "score": max(rank_score for rank_score, *_ in clean_hits[:max_hits]) * 0.08,
                    "hits": compact_hits,
                    "warnings": warnings,
                }
        except Exception as exc:
            warnings.append(_search_warning("clean_source", clean_messages, exc))

    sqlite_path = Path(paths.get("sqlite") or "")
    if not sqlite_path.exists():
        return {"score": 0.0, "hits": [], "warnings": warnings}
    # Registry is the low-level catalog imported by many scripts. Keep retrieval
    # as a use-site dependency so a future retrieval helper can refer back to
    # registry data without creating an import-time cycle.
    from retrieval import expanded_terms_from_anchors, match_anchors, search_hybrid_index

    anchors_value = paths.get("anchors")
    anchors_path = Path(anchors_value) if anchors_value else None
    anchors = match_anchors(anchors_path, terms, limit=4) if anchors_path and anchors_path.is_file() else []
    expanded = expanded_terms_from_anchors(terms, anchors, limit=24)
    try:
        hits = search_hybrid_index(
            sqlite_path,
            terms,
            expanded,
            anchors,
            limit=max_hits,
            candidate_limit=80,
            snippet_chars=260,
            context_radius=0,
        )
    except Exception as exc:
        warnings.append(_search_warning("sqlite", sqlite_path, exc))
        return {"score": 0.0, "hits": [], "warnings": warnings}
    score = max((float(hit.get("score") or 0.0) for hit in hits), default=0.0) * 0.08
    compact_hits = [
        {
            "source": "sqlite",
            "line": hit.get("line"),
            "role": hit.get("role"),
            "phase": hit.get("phase") or "",
            "turn_index": hit.get("turn_index"),
            "is_final": hit.get("is_final"),
            "score": hit.get("score"),
            "snippet": hit.get("snippet"),
        }
        for hit in hits
    ]
    return {"score": score, "hits": compact_hits, "warnings": warnings}


def deep_search_entry(entry: dict, terms: list[str], max_hits: int = 3) -> tuple[float, list[dict]]:
    result = deep_search_entry_result(entry, terms, max_hits=max_hits)
    return float(result.get("score") or 0.0), list(result.get("hits") or [])


def print_entries(entries: list[dict]) -> None:
    if not entries:
        print("no registered thread memories")
        return
    for entry in entries:
        size = entry.get("rollout_size") or 0
        size_mb = int(size) / (1024 * 1024) if size else 0
        print(f"- {entry.get('thread_key')} | {entry.get('title')} | {entry.get('message_count')} messages | {size_mb:.1f} MB")
        if entry.get("project_label"):
            print(f"  project: {entry.get('project_label')} ({', '.join(entry.get('project_tags', [])[:8])})")
        print(f"  workspace: {entry.get('paths', {}).get('workspace')}")
        if entry.get("summary"):
            print(f"  summary: {compact_text(entry['summary'], 220)}")
        if entry.get("keywords"):
            print(f"  keywords: {', '.join(entry.get('keywords', [])[:12])}")
        if entry.get("index_hits"):
            print("  index hits:")
            for hit in entry.get("index_hits", [])[:3]:
                print(f"    - line {hit.get('line')} | {hit.get('role')} | score {hit.get('score')}: {hit.get('snippet')}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-dir", help="Defaults to $AIPPOCAMPUS_REGISTRY_DIR or $CODEX_HOME/aippocampus-registry.")
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register")
    register.add_argument("--cwd", default=os.getcwd())
    register.add_argument("--vault")
    register.add_argument("--dashboard-note")
    register.add_argument("--dashboard-html")
    register.add_argument("--build-index", action="store_true")
    register.add_argument("--json", action="store_true", dest="json_output")

    register_rollout = sub.add_parser("register-rollout")
    register_rollout.add_argument("--rollout", required=True)
    register_rollout.add_argument("--cwd", help="Override the workspace/project path stored in session_meta.")
    register_rollout.add_argument("--title")
    register_rollout.add_argument("--project", help="Human project label for grouping related threads.")
    register_rollout.add_argument("--tag", action="append", default=[], help="Extra project/thread tag. Can be repeated.")
    register_rollout.add_argument("--build-index", action="store_true", help="Also build the heavier SQLite/RAG-lite index in the registry thread store.")
    register_rollout.add_argument("--json", action="store_true", dest="json_output")

    scan = sub.add_parser("scan-sessions")
    scan.add_argument("--build-index", action="store_true", help="Also build SQLite/RAG-lite indexes for newly registered sessions.")
    scan.add_argument("--refresh", action="store_true", help="Refresh sessions that are already registered.")
    scan.add_argument("--max", type=int, help="Maximum number of sessions to register, newest first.")
    scan.add_argument("--cwd-filter", help="Only include sessions whose recorded cwd contains this text.")
    scan.add_argument("--project", help="Project label to attach to all matched sessions.")
    scan.add_argument("--tag", action="append", default=[], help="Extra tag to attach to all matched sessions. Can be repeated.")
    scan.add_argument("--dry-run", action="store_true")
    scan.add_argument("--json", action="store_true", dest="json_output")

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--json", action="store_true", dest="json_output")

    search = sub.add_parser("search")
    search.add_argument("terms", nargs="+")
    search.add_argument("--max", type=int, default=8)
    search.add_argument("--metadata-only", action="store_true", help="Only search registry metadata; skip registered SQLite indexes.")
    search.add_argument("--json", action="store_true", dest="json_output")

    show = sub.add_parser("show")
    show.add_argument("thread_key")
    show.add_argument("--json", action="store_true", dest="json_output")

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
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            verb = "would register" if args.dry_run else "registered"
            print(f"{verb}: {result['count']} session(s)")
            print(f"registry: {result['registry']}")
            rows = result["planned"] if args.dry_run else result["registered"]
            for item in rows[:20]:
                print(f"- {item.get('thread_key')} | {item.get('title') or item.get('timestamp')} | {item.get('cwd') or item.get('paths', {}).get('workspace')}")
        return 0

    registry = load_registry(json_path)
    if args.command == "list":
        if args.json_output:
            print(json.dumps(registry, ensure_ascii=False, indent=2))
        else:
            print(f"registry: {json_path}")
            print_entries(registry.get("threads", []))
        return 0

    if args.command == "search":
        from retrieval import split_query_terms

        query_terms = split_query_terms(args.terms)
        scored = []
        warnings = []
        for entry in registry.get("threads", []):
            score = entry_search_score(entry, query_terms)
            index_hits = []
            if not args.metadata_only:
                deep_result = deep_search_entry_result(entry, query_terms)
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
            print(json.dumps({"registry": str(json_path), "matches": scored, "warnings": warnings}, ensure_ascii=False, indent=2))
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
        match = next((entry for entry in registry.get("threads", []) if entry.get("thread_key") == args.thread_key), None)
        if not match:
            print(json.dumps({"error": "thread not found", "thread_key": args.thread_key, "registry": str(json_path)}, ensure_ascii=False, indent=2))
            return 1
        if args.json_output:
            print(json.dumps(match, ensure_ascii=False, indent=2))
        else:
            print_entries([match])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
