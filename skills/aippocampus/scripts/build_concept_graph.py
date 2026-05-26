#!/usr/bin/env python3
"""Build and query a lightweight AIppocampus concept graph.

The graph is an expansion layer for ambient recall. It is not evidence: it can
add query terms or improve candidate scent, but exact claims still need
clean-source or raw-rollout support.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any

from build_associations import default_associations_path, load_associations, normalize_term, term_is_noise
from registry import registry_paths, unique_preserve
from aippocampuslib import now_utc


CONCEPT_GRAPH_SCHEMA_VERSION = 1
DEFAULT_MAX_RELATED_PER_TERM = 10
DEFAULT_MAX_DEGREE = 12
DEFAULT_MAX_TERMS = 18

GENERIC_CONCEPT_TERMS = {
    "关于",
    "当前",
    "当前线程",
    "前线程",
    "线程",
    "这个",
    "那个",
    "问题",
    "实现",
    "方案",
    "主题是什么",
}

EDGE_TYPE_MULTIPLIER = {
    "alias": 1.0,
    "verified_related": 0.85,
    "same_decision_space": 0.82,
    "decision_about": 0.78,
    "project_topic": 0.72,
    "depends_on": 0.68,
    "contrasts_with": 0.65,
    "supersedes": 0.62,
    "related": 0.58,
    "co_occurs": 0.55,
}

BIDIRECTIONAL_EDGE_TYPES = {
    "alias",
    "same_decision_space",
    "contrasts_with",
    "project_topic",
    "related",
}


def default_concept_graph_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "concept_index.sqlite"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "concept_index.sqlite"


def default_project_timeline_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "project_timeline.json"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "project_timeline.json"


def default_subconscious_edges_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "subconscious_edges.jsonl"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "subconscious_edges.jsonl"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def concept_normalized(value: str) -> str:
    return normalize_term(value).casefold()


def concept_is_noise(value: str) -> bool:
    term = normalize_term(value)
    if not term:
        return True
    if term.casefold() in {item.casefold() for item in GENERIC_CONCEPT_TERMS}:
        return True
    return term_is_noise(term)


def concept_id_for(label: str) -> str:
    normalized = concept_normalized(label)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:20]
    return f"cpt_{digest}"


def infer_concept_kind(label: str) -> str:
    if re_like_project(label):
        return "project"
    if any(ch in label for ch in "/."):
        return "library"
    if any(ch.isupper() for ch in label) and any(ch.islower() for ch in label):
        return "topic"
    return "topic"


def re_like_project(label: str) -> bool:
    low = label.casefold()
    return low in {"t-sense", "aippocampus"} or low.startswith("project:")


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
            status TEXT NOT NULL DEFAULT 'staging',
            scope_key TEXT NOT NULL DEFAULT 'global',
            hit_count INTEGER NOT NULL DEFAULT 0,
            thread_count INTEGER NOT NULL DEFAULT 0,
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
            source_thread_key TEXT,
            source_message_id TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT,
            PRIMARY KEY (src_concept_id, dst_concept_id, edge_type, scope_key)
        );

        CREATE INDEX IF NOT EXISTS idx_concepts_normalized ON concepts(normalized_label);
        CREATE INDEX IF NOT EXISTS idx_concept_edges_src ON concept_edges(src_concept_id, weight DESC);
        CREATE INDEX IF NOT EXISTS idx_concept_edges_dst ON concept_edges(dst_concept_id, weight DESC);
        """
    )


def reset_graph(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM concept_edges")
    con.execute("DELETE FROM concepts")
    con.execute("DELETE FROM meta")


def upsert_concept(
    con: sqlite3.Connection,
    label: str,
    *,
    status: str,
    hit_count: int = 0,
    thread_count: int = 0,
    scope_key: str = "global",
) -> str | None:
    label = normalize_term(label)
    if concept_is_noise(label):
        return None
    concept_id = concept_id_for(label)
    normalized = concept_normalized(label)
    now = now_utc()
    existing = con.execute("SELECT concept_id, status, hit_count, thread_count FROM concepts WHERE concept_id = ?", (concept_id,)).fetchone()
    if existing:
        best_status = "verified" if status == "verified" or existing["status"] == "verified" else "staging"
        con.execute(
            """
            UPDATE concepts
            SET label = ?, status = ?, hit_count = MAX(hit_count, ?),
                thread_count = MAX(thread_count, ?), updated_at = ?
            WHERE concept_id = ?
            """,
            (label, best_status, int(hit_count or 0), int(thread_count or 0), now, concept_id),
        )
    else:
        con.execute(
            """
            INSERT INTO concepts
            (concept_id, label, normalized_label, kind, status, scope_key, hit_count, thread_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                concept_id,
                label,
                normalized,
                infer_concept_kind(label),
                status,
                scope_key,
                int(hit_count or 0),
                int(thread_count or 0),
                now,
                now,
            ),
        )
    return concept_id


def edge_weight(confidence: float, edge_type: str, evidence_count: int) -> float:
    multiplier = EDGE_TYPE_MULTIPLIER.get(edge_type, 0.5)
    evidence_bonus = min(0.18, math.log(max(1, evidence_count), 10) * 0.08)
    return round(max(0.01, min(1.0, confidence * multiplier + evidence_bonus)), 4)


def upsert_edge(
    con: sqlite3.Connection,
    src_id: str,
    dst_id: str,
    *,
    edge_type: str,
    confidence: float,
    status: str,
    evidence_count: int,
    scope_key: str = "global",
    source_thread_key: str | None = None,
    source_message_id: str | None = None,
) -> None:
    if src_id == dst_id:
        return
    now = now_utc()
    weight = edge_weight(confidence, edge_type, evidence_count)
    existing = con.execute(
        """
        SELECT confidence, status, evidence_count, first_seen_at
        FROM concept_edges
        WHERE src_concept_id = ? AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
        """,
        (src_id, dst_id, edge_type, scope_key),
    ).fetchone()
    if existing:
        best_status = "verified" if status == "verified" or existing["status"] == "verified" else "staging"
        best_confidence = max(float(existing["confidence"] or 0.0), confidence)
        best_evidence = max(int(existing["evidence_count"] or 0), int(evidence_count or 0))
        con.execute(
            """
            UPDATE concept_edges
            SET weight = ?, confidence = ?, status = ?, evidence_count = ?,
                source_thread_key = COALESCE(source_thread_key, ?),
                source_message_id = COALESCE(source_message_id, ?),
                last_seen_at = ?
            WHERE src_concept_id = ? AND dst_concept_id = ? AND edge_type = ? AND scope_key = ?
            """,
            (
                edge_weight(best_confidence, edge_type, best_evidence),
                best_confidence,
                best_status,
                best_evidence,
                source_thread_key,
                source_message_id,
                now,
                src_id,
                dst_id,
                edge_type,
                scope_key,
            ),
        )
    else:
        con.execute(
            """
            INSERT INTO concept_edges
            (src_concept_id, dst_concept_id, edge_type, weight, confidence, status, scope_key,
             evidence_count, source_thread_key, source_message_id, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                src_id,
                dst_id,
                edge_type,
                weight,
                confidence,
                status,
                scope_key,
                int(evidence_count or 0),
                source_thread_key,
                source_message_id,
                now,
                now,
            ),
        )


def add_bidirectional_edge(
    con: sqlite3.Connection,
    a: str,
    b: str,
    *,
    edge_type: str,
    confidence: float,
    status: str,
    evidence_count: int,
    source_thread_key: str | None,
) -> None:
    a_id = upsert_concept(con, a, status=status, hit_count=evidence_count, thread_count=0)
    b_id = upsert_concept(con, b, status=status, hit_count=evidence_count, thread_count=0)
    if not a_id or not b_id:
        return
    upsert_edge(
        con,
        a_id,
        b_id,
        edge_type=edge_type,
        confidence=confidence,
        status=status,
        evidence_count=evidence_count,
        source_thread_key=source_thread_key,
    )
    upsert_edge(
        con,
        b_id,
        a_id,
        edge_type=edge_type,
        confidence=confidence,
        status=status,
        evidence_count=evidence_count,
        source_thread_key=source_thread_key,
    )


def collect_timeline_edges(con: sqlite3.Connection, timeline_path: Path | None) -> int:
    if not timeline_path or not timeline_path.exists():
        return 0
    timeline = load_json(timeline_path)
    edge_count = 0
    for project in (timeline.get("projects") or {}).values():
        if not isinstance(project, dict):
            continue
        project_label = str(project.get("project_label") or "").strip()
        project_terms = unique_preserve(
            [project_label, *list(project.get("project_tags") or [])],
            limit=8,
        )
        for turn in project.get("latest_turns") or []:
            if not isinstance(turn, dict):
                continue
            topic_terms = unique_preserve(project_terms + list(turn.get("topic_terms") or []), limit=18)
            topic_terms = [term for term in topic_terms if not concept_is_noise(term)]
            if len(topic_terms) < 2:
                continue
            source_thread_key = turn.get("thread_key")
            for idx, term in enumerate(topic_terms):
                for related in topic_terms[idx + 1 :]:
                    add_bidirectional_edge(
                        con,
                        term,
                        related,
                        edge_type="project_topic",
                        confidence=0.9,
                        status="staging",
                        evidence_count=1,
                        source_thread_key=source_thread_key,
                    )
                    edge_count += 2
    return edge_count


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def collect_subconscious_edges(con: sqlite3.Connection, staging_path: Path | None) -> int:
    if not staging_path or not staging_path.exists():
        return 0
    inserted = 0
    for item in iter_jsonl(staging_path):
        if item.get("kind") != "aippocampus_subconscious_edge":
            continue
        if item.get("status") not in {None, "staging"}:
            continue
        src = str(item.get("src") or "")
        dst = str(item.get("dst") or "")
        if concept_is_noise(src) or concept_is_noise(dst):
            continue
        confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        if confidence < 0.45:
            continue
        refs = [ref for ref in item.get("source_refs") or [] if isinstance(ref, dict)]
        if not refs:
            continue
        edge_type = str(item.get("edge_type") or "related")
        source_thread_key = refs[0].get("thread_key")
        src_id = upsert_concept(con, src, status="staging", hit_count=len(refs), thread_count=1)
        dst_id = upsert_concept(con, dst, status="staging", hit_count=len(refs), thread_count=1)
        if not src_id or not dst_id:
            continue
        upsert_edge(
            con,
            src_id,
            dst_id,
            edge_type=edge_type,
            confidence=confidence,
            status="staging",
            evidence_count=len(refs),
            source_thread_key=source_thread_key,
        )
        inserted += 1
        if edge_type in BIDIRECTIONAL_EDGE_TYPES:
            upsert_edge(
                con,
                dst_id,
                src_id,
                edge_type=edge_type,
                confidence=confidence,
                status="staging",
                evidence_count=len(refs),
                source_thread_key=source_thread_key,
            )
            inserted += 1
    return inserted


def build_concept_graph(
    associations_path: Path,
    output_path: Path,
    *,
    project_timeline_path: Path | None = None,
    subconscious_edges_path: Path | None = None,
    max_related_per_term: int = DEFAULT_MAX_RELATED_PER_TERM,
) -> dict[str, Any]:
    associations = load_associations(associations_path)
    con = connect(output_path)
    try:
        init_schema(con)
        reset_graph(con)
        term_items = list((associations.get("terms") or {}).values())
        for item in term_items:
            if not isinstance(item, dict):
                continue
            term = normalize_term(str(item.get("term") or ""))
            if concept_is_noise(term):
                continue
            status = "verified" if item.get("status") == "verified" else "staging"
            confidence = float(item.get("confidence") or 0.0)
            sources = item.get("threads") or []
            source_threads = unique_preserve([str(source.get("thread_key") or "") for source in sources if source.get("thread_key")])
            term_id = upsert_concept(
                con,
                term,
                status=status,
                hit_count=int(item.get("hit_count") or 0),
                thread_count=len(source_threads),
            )
            if not term_id:
                continue
            edge_type = "verified_related" if status == "verified" else "co_occurs"
            for related in list(item.get("related_terms") or [])[: max(0, int(max_related_per_term))]:
                add_bidirectional_edge(
                    con,
                    term,
                    str(related),
                    edge_type=edge_type,
                    confidence=confidence,
                    status=status,
                    evidence_count=int(item.get("hit_count") or 0),
                    source_thread_key=source_threads[0] if source_threads else None,
                )
        timeline_edge_count = collect_timeline_edges(con, project_timeline_path)
        subconscious_edge_count = collect_subconscious_edges(con, subconscious_edges_path)
        metadata = {
            "schema_version": CONCEPT_GRAPH_SCHEMA_VERSION,
            "kind": "aippocampus_concept_graph",
            "created_at": now_utc(),
            "source_associations": str(associations_path),
            "source_project_timeline": str(project_timeline_path) if project_timeline_path else None,
            "source_subconscious_edges": str(subconscious_edges_path) if subconscious_edges_path else None,
            "max_related_per_term": max_related_per_term,
        }
        for key, value in metadata.items():
            con.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
        con.commit()
        concepts = con.execute("SELECT COUNT(*) AS count FROM concepts").fetchone()["count"]
        edges = con.execute("SELECT COUNT(*) AS count FROM concept_edges").fetchone()["count"]
        return {
            **metadata,
            "output": str(output_path),
            "concept_count": concepts,
            "edge_count": edges,
            "timeline_edge_count": timeline_edge_count,
            "subconscious_edge_count": subconscious_edge_count,
        }
    finally:
        con.close()


def concept_ids_for_terms(con: sqlite3.Connection, terms: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for term in terms:
        normalized = concept_normalized(str(term))
        if not normalized or normalized in seen or concept_is_noise(normalized):
            continue
        seen.add(normalized)
        row = con.execute(
            "SELECT concept_id, label FROM concepts WHERE normalized_label = ?",
            (normalized,),
        ).fetchone()
        if row:
            out.append((row["concept_id"], row["label"]))
    return out


def edge_rows(con: sqlite3.Connection, src_id: str, *, max_degree: int, depth: int) -> list[sqlite3.Row]:
    rows = con.execute(
        """
        SELECT e.*, c.label AS dst_label, c.normalized_label AS dst_normalized
        FROM concept_edges e
        JOIN concepts c ON c.concept_id = e.dst_concept_id
        WHERE e.src_concept_id = ?
          AND e.status IN ('verified', 'staging')
        ORDER BY
          CASE e.status WHEN 'verified' THEN 0 ELSE 1 END,
          e.weight DESC,
          e.confidence DESC
        LIMIT ?
        """,
        (src_id, max(1, int(max_degree))),
    ).fetchall()
    if depth <= 1:
        return rows
    # Depth-2 expansion is where semantic drift usually appears. Keep it to
    # verified or very high-confidence edges so a broad co-occurrence chain
    # cannot turn one vague word into a personal-memory flood.
    return [row for row in rows if row["status"] == "verified" or float(row["confidence"] or 0.0) >= 0.88]


def expand_concepts(
    db_path: Path,
    seed_terms: list[str],
    *,
    depth: int = 2,
    max_degree: int = DEFAULT_MAX_DEGREE,
    max_terms: int = DEFAULT_MAX_TERMS,
    min_score: float = 0.15,
) -> list[dict[str, Any]]:
    if not db_path.exists() or depth <= 0:
        return []
    try:
        con = sqlite3.connect(db_path, timeout=2)
    except sqlite3.Error:
        return []
    con.row_factory = sqlite3.Row
    try:
        seeds = concept_ids_for_terms(con, seed_terms)
        if not seeds:
            return []
        seed_norms = {concept_normalized(label) for _, label in seeds}
        queue: list[tuple[str, float, int, list[str], list[str]]] = [
            (concept_id, 1.0, 0, [label], [])
            for concept_id, label in seeds
        ]
        best: dict[str, dict[str, Any]] = {}
        visited: set[tuple[str, int]] = set()
        while queue:
            concept_id, score, current_depth, path, edge_types = queue.pop(0)
            if current_depth >= depth:
                continue
            if (concept_id, current_depth) in visited:
                continue
            visited.add((concept_id, current_depth))
            next_depth = current_depth + 1
            for edge in edge_rows(con, concept_id, max_degree=max_degree, depth=next_depth):
                label = str(edge["dst_label"] or "")
                normalized = concept_normalized(label)
                if not label or normalized in seed_norms or concept_is_noise(label):
                    continue
                depth_decay = 1.0 if next_depth == 1 else 0.45
                next_score = score * float(edge["weight"] or 0.0) * depth_decay
                if next_score < min_score:
                    continue
                existing = best.get(normalized)
                row = {
                    "term": label,
                    "score": round(next_score, 4),
                    "depth": next_depth,
                    "path": path + [label],
                    "edge_types": edge_types + [edge["edge_type"]],
                    "status": edge["status"],
                }
                if not existing or next_score > float(existing.get("score") or 0.0):
                    best[normalized] = row
                queue.append((edge["dst_concept_id"], next_score, next_depth, path + [label], edge_types + [edge["edge_type"]]))
        rows = sorted(best.values(), key=lambda item: (-float(item.get("score") or 0.0), int(item.get("depth") or 0), str(item.get("term") or "").casefold()))
        return rows[: max(1, int(max_terms))]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--associations")
    parser.add_argument("--project-timeline")
    parser.add_argument("--subconscious-edges")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--output")
    parser.add_argument("--max-related-per-term", type=int, default=DEFAULT_MAX_RELATED_PER_TERM)
    parser.add_argument("--expand", nargs="*", help="Dry-run concept expansion for seed terms.")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve() if args.registry else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    associations_path = Path(args.associations).resolve() if args.associations else default_associations_path(registry_path=registry_path)
    project_timeline_path = Path(args.project_timeline).resolve() if args.project_timeline else default_project_timeline_path(registry_path=registry_path)
    subconscious_edges_path = Path(args.subconscious_edges).resolve() if args.subconscious_edges else default_subconscious_edges_path(registry_path=registry_path)
    output_path = Path(args.output).resolve() if args.output else default_concept_graph_path(registry_path=registry_path)

    if args.expand:
        rows = expand_concepts(output_path, args.expand, depth=args.depth)
        payload = {"concept_graph": str(output_path), "seed_terms": args.expand, "expansions": rows}
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            for row in rows:
                print(f"- {row['term']} | score {row['score']} | depth {row['depth']} | {' -> '.join(row['path'])}")
        return 0

    result = build_concept_graph(
        associations_path,
        output_path,
        project_timeline_path=project_timeline_path if project_timeline_path.exists() else None,
        subconscious_edges_path=subconscious_edges_path if subconscious_edges_path.exists() else None,
        max_related_per_term=args.max_related_per_term,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"concept graph: {output_path}")
        print(f"concepts: {result['concept_count']}")
        print(f"edges: {result['edge_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
