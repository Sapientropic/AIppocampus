#!/usr/bin/env python3
"""SQLite schema helpers for the rebuildable concept graph cache."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from aippocampus_runtime.registry.api import registry_paths


def default_concept_graph_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "concept_index.sqlite"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "concept_index.sqlite"


def default_project_timeline_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "project_timeline.json"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "project_timeline.json"


def default_subconscious_edges_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "subconscious_edges.jsonl"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "subconscious_edges.jsonl"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS concepts (
            concept_id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            normalized_label TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL DEFAULT 'topic',
            kind_source TEXT NOT NULL DEFAULT 'fallback',
            kind_confidence REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'staging',
            scope_key TEXT NOT NULL DEFAULT 'global',
            hit_count INTEGER NOT NULL DEFAULT 0,
            thread_count INTEGER NOT NULL DEFAULT 0,
            lifecycle_reason TEXT NOT NULL DEFAULT 'staging_default',
            lifecycle_updated_at TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS concept_edges (
            src_concept_id TEXT NOT NULL,
            dst_concept_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            weight REAL NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'staging',
            scope_key TEXT NOT NULL DEFAULT 'global',
            evidence_count INTEGER NOT NULL DEFAULT 0,
            thread_count INTEGER NOT NULL DEFAULT 0,
            lifecycle_reason TEXT NOT NULL DEFAULT 'staging_default',
            lifecycle_updated_at TEXT,
            source_thread_key TEXT,
            source_message_id TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT,
            PRIMARY KEY (src_concept_id, dst_concept_id, edge_type, scope_key)
        );

        CREATE INDEX IF NOT EXISTS idx_concepts_normalized ON concepts(normalized_label);
        CREATE INDEX IF NOT EXISTS idx_concepts_health
            ON concepts(status, scope_key, thread_count, hit_count);
        CREATE INDEX IF NOT EXISTS idx_concept_edges_src ON concept_edges(src_concept_id, weight DESC);
        CREATE INDEX IF NOT EXISTS idx_concept_edges_expand
            ON concept_edges(src_concept_id, status, weight DESC, confidence DESC);
        CREATE INDEX IF NOT EXISTS idx_concept_edges_dst ON concept_edges(dst_concept_id, weight DESC);
        CREATE INDEX IF NOT EXISTS idx_concept_edges_quality
            ON concept_edges(edge_type, status, thread_count, evidence_count, confidence, scope_key);
        """
    )
    ensure_lifecycle_columns(con)


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in con.execute(f"PRAGMA table_info({table})").fetchall()
    }


def ensure_lifecycle_columns(con: sqlite3.Connection) -> None:
    columns = table_columns(con, "concepts")
    if "kind_source" not in columns:
        con.execute("ALTER TABLE concepts ADD COLUMN kind_source TEXT NOT NULL DEFAULT 'fallback'")
    if "kind_confidence" not in columns:
        con.execute("ALTER TABLE concepts ADD COLUMN kind_confidence REAL NOT NULL DEFAULT 0.0")
    if "lifecycle_reason" not in columns:
        con.execute(
            "ALTER TABLE concepts ADD COLUMN lifecycle_reason TEXT NOT NULL DEFAULT 'staging_default'"
        )
    if "lifecycle_updated_at" not in columns:
        con.execute("ALTER TABLE concepts ADD COLUMN lifecycle_updated_at TEXT")
    edge_columns = table_columns(con, "concept_edges")
    if "thread_count" not in edge_columns:
        con.execute("ALTER TABLE concept_edges ADD COLUMN thread_count INTEGER NOT NULL DEFAULT 0")
    if "lifecycle_reason" not in edge_columns:
        con.execute(
            "ALTER TABLE concept_edges "
            "ADD COLUMN lifecycle_reason TEXT NOT NULL DEFAULT 'staging_default'"
        )
    if "lifecycle_updated_at" not in edge_columns:
        con.execute("ALTER TABLE concept_edges ADD COLUMN lifecycle_updated_at TEXT")


def reset_graph(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM concept_edges")
    con.execute("DELETE FROM concepts")
    con.execute("DELETE FROM meta")
