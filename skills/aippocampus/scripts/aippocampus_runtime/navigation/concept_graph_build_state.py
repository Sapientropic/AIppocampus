"""Build-local state for concept graph materialization.

The concept graph is a rebuildable navigation cache, but rebuilds still need
to scale with unique concepts and changed inputs. This module owns the small
amount of state required to keep those two contracts explicit instead of
letting edge loops quietly turn into repeated SQLite writes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

CONCEPT_GRAPH_BUILD_POLICY_VERSION = "concept_graph_build_policy_v2"

_STATUS_RANK = {
    "suppressed": 0,
    "parked": 1,
    "staging": 2,
    "verified": 3,
}

NormalizeKey = Callable[[str], str]
UpsertConcept = Callable[..., str | None]


def _path_fingerprint(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {"present": False}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return {
        "present": True,
        "size_bytes": int(stat.st_size),
        "sha256": digest.hexdigest(),
    }


def build_input_manifest(
    *,
    associations_path: Path,
    project_timeline_path: Path | None,
    subconscious_edges_path: Path | None,
    max_related_per_term: int,
    policy_version: str = CONCEPT_GRAPH_BUILD_POLICY_VERSION,
) -> dict[str, Any]:
    return {
        "schema_version": "concept_graph_input_manifest_v1",
        "policy_version": policy_version,
        "max_related_per_term": int(max_related_per_term),
        "inputs": {
            "associations": _path_fingerprint(associations_path),
            "project_timeline": _path_fingerprint(project_timeline_path),
            "subconscious_edges": _path_fingerprint(subconscious_edges_path),
        },
    }


def load_meta_json(con: sqlite3.Connection, key: str) -> dict[str, Any]:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return {}
    try:
        loaded = json.loads(str(row["value"] or "{}"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def graph_counts(con: sqlite3.Connection) -> dict[str, int]:
    concepts = int(con.execute("SELECT COUNT(*) AS count FROM concepts").fetchone()["count"] or 0)
    edges = int(con.execute("SELECT COUNT(*) AS count FROM concept_edges").fetchone()["count"] or 0)
    return {"concept_count": concepts, "edge_count": edges}


def unchanged_input_reuse_payload(
    con: sqlite3.Connection,
    *,
    output_path: Path,
    input_manifest: dict[str, Any],
) -> dict[str, Any] | None:
    previous_manifest = load_meta_json(con, "input_manifest")
    if previous_manifest != input_manifest:
        return None
    counts = graph_counts(con)
    if counts["concept_count"] <= 0 and counts["edge_count"] <= 0:
        return None
    metadata = load_meta_json(con, "build_metadata")
    quality_gate = load_meta_json(con, "quality_gate")
    previous_build_diagnostics = load_meta_json(con, "build_diagnostics")
    build_diagnostics = {
        "schema_version": "concept_graph_build_diagnostics_v1",
        "build_mode": "skipped_unchanged_inputs",
        "previous_build_mode": previous_build_diagnostics.get("build_mode"),
        "incremental_update_deferred": True,
        "reset_graph_called": False,
        "policy_version": input_manifest.get("policy_version"),
        "edge_upsert_attempts": 0,
        "concept_resolve_requests": 0,
        "unique_concept_labels": 0,
        "concept_db_upsert_attempts": 0,
        "concept_cache_hits": 0,
        "concept_cache_refreshes": 0,
        "concept_none_results": 0,
        "previous_concept_count": counts["concept_count"],
        "previous_edge_count": counts["edge_count"],
    }
    return {
        **metadata,
        "output": str(output_path),
        "build_mode": "skipped_unchanged_inputs",
        "input_manifest": input_manifest,
        "previous_graph": counts,
        "concept_count": counts["concept_count"],
        "edge_count": counts["edge_count"],
        "quality_gate": quality_gate,
        "build_diagnostics": build_diagnostics,
    }


class BuildConceptResolver:
    """Resolve concept ids once per useful label/update during a graph build."""

    def __init__(self, *, normalize_key: NormalizeKey, upsert: UpsertConcept) -> None:
        self._normalize_key = normalize_key
        self._upsert = upsert
        self._cache: dict[str, dict[str, Any]] = {}
        self.resolve_requests = 0
        self.cache_hits = 0
        self.db_upsert_attempts = 0
        self.cache_refreshes = 0
        self.none_results = 0

    def resolve(
        self,
        con: sqlite3.Connection,
        label: str,
        *,
        status: str,
        lifecycle_reason: str = "staging_default",
        hit_count: int = 0,
        thread_count: int = 0,
        scope_key: str = "global",
        supplied_kind: Any = None,
        supplied_kind_status: Any = None,
        source_backed_kind: bool = False,
    ) -> str | None:
        self.resolve_requests += 1
        key = self._normalize_key(label)
        if not key:
            self.none_results += 1
            return None
        incoming = {
            "status": str(status or "staging"),
            "lifecycle_reason": lifecycle_reason,
            "hit_count": int(hit_count or 0),
            "thread_count": int(thread_count or 0),
            "scope_key": scope_key,
            "supplied_kind": supplied_kind,
            "supplied_kind_status": supplied_kind_status,
            "source_backed_kind": bool(source_backed_kind),
        }
        cached = self._cache.get(key)
        if cached and not self._should_refresh(cached, incoming):
            self.cache_hits += 1
            return cached.get("concept_id")
        concept_id = self._upsert(
            con,
            label,
            status=status,
            lifecycle_reason=lifecycle_reason,
            hit_count=hit_count,
            thread_count=thread_count,
            scope_key=scope_key,
            supplied_kind=supplied_kind,
            supplied_kind_status=supplied_kind_status,
            source_backed_kind=source_backed_kind,
        )
        self.db_upsert_attempts += 1
        if concept_id is None:
            self.none_results += 1
            self._cache[key] = {**incoming, "concept_id": None}
            return None
        if cached:
            self.cache_refreshes += 1
            incoming = self._merge_cached(cached, incoming)
        self._cache[key] = {**incoming, "concept_id": concept_id}
        return concept_id

    def _should_refresh(self, cached: dict[str, Any], incoming: dict[str, Any]) -> bool:
        if cached.get("concept_id") is None:
            return False
        if _STATUS_RANK.get(str(incoming["status"]), 0) > _STATUS_RANK.get(
            str(cached.get("status") or ""), 0
        ):
            return True
        if int(incoming["hit_count"]) > int(cached.get("hit_count") or 0):
            return True
        if int(incoming["thread_count"]) > int(cached.get("thread_count") or 0):
            return True
        if bool(incoming.get("source_backed_kind")) and not bool(
            cached.get("source_backed_kind")
        ):
            return True
        if incoming.get("supplied_kind") and not cached.get("supplied_kind"):
            return True
        if str(incoming.get("supplied_kind_status") or "").casefold() == "reviewed" and str(
            cached.get("supplied_kind_status") or ""
        ).casefold() != "reviewed":
            return True
        return False

    def _merge_cached(
        self, cached: dict[str, Any], incoming: dict[str, Any]
    ) -> dict[str, Any]:
        if _STATUS_RANK.get(str(cached.get("status") or ""), 0) > _STATUS_RANK.get(
            str(incoming.get("status") or ""), 0
        ):
            incoming["status"] = cached.get("status")
            incoming["lifecycle_reason"] = cached.get("lifecycle_reason")
        incoming["hit_count"] = max(
            int(cached.get("hit_count") or 0), int(incoming.get("hit_count") or 0)
        )
        incoming["thread_count"] = max(
            int(cached.get("thread_count") or 0), int(incoming.get("thread_count") or 0)
        )
        if not incoming.get("supplied_kind"):
            incoming["supplied_kind"] = cached.get("supplied_kind")
        if not incoming.get("supplied_kind_status"):
            incoming["supplied_kind_status"] = cached.get("supplied_kind_status")
        incoming["source_backed_kind"] = bool(
            incoming.get("source_backed_kind") or cached.get("source_backed_kind")
        )
        return incoming

    def diagnostics(self) -> dict[str, int]:
        return {
            "concept_resolve_requests": self.resolve_requests,
            "unique_concept_labels": len(self._cache),
            "concept_db_upsert_attempts": self.db_upsert_attempts,
            "concept_cache_hits": self.cache_hits,
            "concept_cache_refreshes": self.cache_refreshes,
            "concept_none_results": self.none_results,
        }


__all__ = [
    "CONCEPT_GRAPH_BUILD_POLICY_VERSION",
    "BuildConceptResolver",
    "build_input_manifest",
    "graph_counts",
    "load_meta_json",
    "unchanged_input_reuse_payload",
]
