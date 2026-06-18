#!/usr/bin/env python3
"""Local hybrid retrieval helpers for aippocampus.

This module intentionally stays dependency-free so the skill remains portable.
It combines three cheap signals that work on private local transcripts:

- SQLite FTS5 trigram search for exact and fuzzy phrase recall.
- Human-curated anchors for query expansion and durable-topic boosting.
- Small context windows around matched messages so agents can recover the turn,
  not only a single isolated line.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.recall import scoring_policy
from aippocampus_runtime.recall.life_cues import life_wide_recall_terms, profile_recall_terms
from aippocampus_runtime.recall.query_policy import ALIASES as ALIASES
from aippocampus_runtime.recall.query_policy import (
    CONCEPT_TRIGGERS,
    RECALL_TRIGGERS,
    STOP_TERMS,
    cjk_query_sidecar_terms,
    fts_query,
    normalize_term,
    score_anchor,
    unique_preserve,
)
from aippocampus_runtime.recall.query_policy import (
    GENERIC_ANCHOR_TERMS as GENERIC_ANCHOR_TERMS,
)
from aippocampus_runtime.recall.query_policy import anchor_text as anchor_text
from aippocampus_runtime.recall.query_policy import (
    expanded_terms_from_anchors as expanded_terms_from_anchors,
)
from aippocampus_runtime.recall.query_policy import match_anchors as match_anchors
from aippocampus_runtime.recall.query_policy import split_query_terms as split_query_terms
from aippocampus_runtime.recall.result_diversity import diversify_results as diversify_results
from aippocampus_runtime.recall.score_fusion import rag_chunk_text_score, retrieval_text_score
from aippocampus_runtime.recall.structure_time import (
    load_message_feature,
    search_structure_time_connection,
    structure_signals,
    temporal_signals,
)
from aippocampus_runtime.recall.structure_time import (
    parse_structure_cues as parse_structure_cues,
)
from aippocampus_runtime.recall.structure_time import (
    parse_temporal_cue as parse_temporal_cue,
)
from aippocampus_runtime.text import cjk_ngrams, iter_cjk_sequences


def sqlite_has_table(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'virtual table') AND name = ?",
        (name,),
    ).fetchone()
    return bool(row)


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def message_select_columns(con: sqlite3.Connection, alias: str | None = None) -> str:
    cols = table_columns(con, "messages")
    prefix = f"{alias}." if alias else ""
    base = [
        f"{prefix}id",
        f"{prefix}line",
        f"{prefix}timestamp",
        f"{prefix}role",
        f"{prefix}kind",
    ]
    if "phase" in cols:
        base.append(f"{prefix}phase")
    else:
        base.append("'' AS phase")
    if "turn_index" in cols:
        base.append(f"{prefix}turn_index")
    else:
        base.append("NULL AS turn_index")
    if "is_final" in cols:
        base.append(f"{prefix}is_final")
    else:
        base.append("0 AS is_final")
    base.append(f"{prefix}text")
    return ", ".join(base)


def phase_weight(row: sqlite3.Row) -> float:
    phase = str(row["phase"] or "")
    role = str(row["role"] or "")
    if phase == "final_answer" or int(row["is_final"] or 0):
        return scoring_policy.PHASE_WEIGHT_POLICY.final_answer
    if role == "user":
        return scoring_policy.PHASE_WEIGHT_POLICY.user
    if phase == "commentary":
        return scoring_policy.PHASE_WEIGHT_POLICY.commentary
    if role == "tool":
        return scoring_policy.PHASE_WEIGHT_POLICY.tool
    return 0.0


def row_message_payload(
    row: sqlite3.Row, snippet_chars: int, *, score: float | None = None, signals: dict | None = None
) -> dict:
    payload = {
        "id": row["id"],
        "line": row["line"],
        "timestamp": row["timestamp"],
        "role": row["role"],
        "kind": row["kind"],
        "phase": row["phase"] or "",
        "turn_index": row["turn_index"],
        "is_final": bool(row["is_final"]),
        "snippet": compact_text(row["text"], snippet_chars),
    }
    if score is not None:
        payload["score"] = round(score, 3)
    if signals is not None:
        payload["signals"] = signals
    return payload


def load_message_by_id(con: sqlite3.Connection, row_id: int) -> dict | None:
    row = con.execute(
        f"SELECT {message_select_columns(con)} FROM messages WHERE id = ?",
        (row_id,),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def context_window(
    con: sqlite3.Connection, row_id: int, radius: int, snippet_chars: int
) -> list[dict]:
    if radius <= 0:
        return []
    rows = con.execute(
        """
        SELECT {columns}
        FROM messages
        WHERE id BETWEEN ? AND ? AND id != ?
        ORDER BY id
        """.format(columns=message_select_columns(con)),
        (row_id - radius, row_id + radius, row_id),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "line": row["line"],
            "timestamp": row["timestamp"],
            "role": row["role"],
            "kind": row["kind"],
            "phase": row["phase"] or "",
            "turn_index": row["turn_index"],
            "is_final": bool(row["is_final"]),
            "snippet": compact_text(row["text"], snippet_chars),
        }
        for row in rows
    ]


def literal_hit_count(text: str, terms: list[str]) -> int:
    low = text.casefold()
    return sum(1 for term in terms if term.casefold() in low)


def anchor_hit_count(text: str, anchor_matches: list[dict]) -> int:
    low = text.casefold()
    count = 0
    for anchor in anchor_matches:
        title = str(anchor.get("title") or "").casefold()
        if title and title in low:
            count += 2
        for keyword in anchor.get("keywords") or []:
            key = str(keyword).casefold()
            if key and key in low:
                count += 1
    return count


def extract_rag_terms(text: str, limit: int = 80) -> dict[str, int]:
    """Build a tiny sparse vector for dependency-free semantic-ish recall.

    This is intentionally lexical rather than embedding-based. The skill should
    be shareable on machines without API keys, GPUs, or vector DBs. Latin tokens
    cover code/docs; CJK n-grams cover Chinese concepts where whitespace is not
    reliable. Do not replace this with an opaque model call unless the optional
    backend is explicitly enabled.
    """

    terms: list[str] = []
    low = text.casefold()
    for token in re.findall(r"[a-z][a-z0-9_.-]{1,}", low):
        if token not in STOP_TERMS and len(token) >= 2:
            terms.append(token)

    for chunk in iter_cjk_sequences(text, min_len=2, max_len=32):
        if len(chunk) <= 12:
            terms.append(chunk)
        terms.extend(cjk_ngrams(chunk, sizes=(2, 3, 4)))

    counts = Counter(term for term in terms if normalize_term(term))
    ranked = sorted(
        counts.items(),
        key=lambda item: (item[1] * min(len(item[0]), 8), item[1], len(item[0])),
        reverse=True,
    )
    return dict(ranked[:limit])


def build_rag_chunks(
    messages: list[dict],
    anchors: list[dict] | None = None,
    *,
    max_chars: int = 2800,
    overlap_messages: int = 1,
) -> list[dict]:
    """Create periodic RAG-lite chunks from normalized messages.

    Chunks are a retrieval cache, not a new source of truth. They point back to
    message ids and rollout lines so answers can still cite raw transcript hits.
    """

    anchors = anchors or []
    indexed = list(enumerate(messages, start=1))

    # For normal recall, a turn is best represented by the user's request and
    # the final answer. Commentary is still indexed in messages for audit-like
    # search, but it should not dilute RAG-lite context when a final answer is
    # available for the same user turn.
    if any(message.get("turn_index") for message in messages):
        turn_groups: dict[int, list[tuple[int, dict]]] = {}
        for msg_id, message in indexed:
            turn_index = message.get("turn_index")
            if turn_index is None:
                continue
            turn_groups.setdefault(int(turn_index), []).append((msg_id, message))
        selected_pairs: list[tuple[int, dict]] = []
        for turn_index in sorted(turn_groups):
            group = turn_groups[turn_index]
            users = [item for item in group if item[1].get("role") == "user"]
            finals = [
                item
                for item in group
                if item[1].get("role") == "assistant"
                and (item[1].get("phase") == "final_answer" or item[1].get("is_final"))
            ]
            if finals:
                assistants = finals
            else:
                assistant_items = [item for item in group if item[1].get("role") == "assistant"]
                assistants = assistant_items[-1:] if assistant_items else []
            selected_pairs.extend(sorted(users + assistants, key=lambda item: item[0]))
        indexed = selected_pairs or indexed
        overlap_messages = 0

    chunks: list[dict] = []
    batch: list[tuple[int, dict]] = []
    batch_chars = 0
    last_flushed_end_id = 0

    def flush() -> None:
        nonlocal batch, batch_chars, last_flushed_end_id
        if not batch:
            return
        text_parts = []
        roles = []
        for msg_id, message in batch:
            roles.append(str(message.get("role") or ""))
            phase = str(message.get("phase") or "")
            turn = message.get("turn_index")
            marker = f"{message.get('role')}"
            if phase:
                marker += f"/{phase}"
            if turn is not None:
                marker += f" turn {turn}"
            text_parts.append(
                f"[{msg_id} {marker} line {message.get('line')}] {message.get('text') or ''}"
            )
        text = "\n".join(text_parts)
        query_terms = list(extract_rag_terms(text, limit=64).keys())
        matched = []
        for anchor in anchors:
            score, _ = score_anchor(anchor, query_terms)
            if score >= 4:
                matched.append(anchor.get("title") or "")
        first_id, first = batch[0]
        last_id, last = batch[-1]
        last_flushed_end_id = last_id
        chunks.append(
            {
                "id": len(chunks) + 1,
                "start_message_id": first_id,
                "end_message_id": last_id,
                "start_line": first.get("line"),
                "end_line": last.get("line"),
                "roles": ",".join(sorted(set(role for role in roles if role))),
                "anchor_titles": unique_preserve([title for title in matched if title], limit=8),
                "summary": compact_text(text, 360),
                "text": text,
                "terms": extract_rag_terms(text, limit=96),
            }
        )
        if overlap_messages > 0:
            batch = batch[-overlap_messages:]
            batch_chars = sum(len(str(message.get("text") or "")) for _, message in batch)
        else:
            batch = []
            batch_chars = 0

    for msg_id, message in indexed:
        text = str(message.get("text") or "")
        if batch and batch_chars + len(text) > max_chars:
            flush()
        batch.append((msg_id, message))
        batch_chars += len(text)
        if batch_chars >= max_chars:
            flush()
    if batch and any(msg_id > last_flushed_end_id for msg_id, _ in batch):
        overlap_messages = 0
        flush()
    return chunks


def search_rag_chunks_connection(
    con: sqlite3.Connection,
    query_terms: list[str],
    expanded_terms: list[str],
    anchor_matches: list[dict],
    *,
    limit: int = 6,
    candidate_limit: int = 80,
    snippet_chars: int = 900,
) -> list[dict]:
    if not sqlite_has_table(con, "rag_chunks"):
        return []

    candidates: dict[int, dict] = {}
    query = fts_query(expanded_terms)
    if query and sqlite_has_table(con, "rag_chunks_fts"):
        try:
            rows = con.execute(
                """
                SELECT c.id, c.start_message_id, c.end_message_id, c.start_line, c.end_line,
                       c.roles, c.anchor_titles, c.summary, c.text, c.terms_json,
                       bm25(rag_chunks_fts) AS rank
                FROM rag_chunks_fts f
                JOIN rag_chunks c ON c.id = f.rowid
                WHERE rag_chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, candidate_limit),
            ).fetchall()
            for pos, row in enumerate(rows):
                candidates[row["id"]] = {
                    "row": row,
                    "signals": {
                        "chunk_fts": scoring_policy.RAG_CHUNK_FTS_POLICY.score_position(pos),
                        "chunk_fts_rank": float(row["rank"]),
                    },
                }
        except sqlite3.Error:
            pass

    like_terms = unique_preserve(query_terms + expanded_terms, limit=18)
    if like_terms:
        where = " OR ".join(["text LIKE ?" for _ in like_terms])
        params = [f"%{term}%" for term in like_terms] + [candidate_limit]
        try:
            rows = con.execute(
                f"""
                SELECT id, start_message_id, end_message_id, start_line, end_line,
                       roles, anchor_titles, summary, text, terms_json
                FROM rag_chunks
                WHERE {where}
                ORDER BY id
                LIMIT ?
                """,
                params,
            ).fetchall()
            for row in rows:
                item = candidates.setdefault(row["id"], {"row": row, "signals": {}})
                item["signals"]["chunk_literal_scan"] = (
                    scoring_policy.RAG_CHUNK_TEXT_POLICY.literal_scan_signal
                )
        except sqlite3.Error:
            pass

    out: list[dict] = []
    for row_id, item in candidates.items():
        row = item["row"]
        text = row["text"]
        literal = literal_hit_count(text, query_terms)
        expanded = literal_hit_count(text, expanded_terms)
        anchor_hits = anchor_hit_count(text, anchor_matches)
        try:
            anchor_titles = json.loads(row["anchor_titles"] or "[]")
        except Exception:
            anchor_titles = []
        signals = item["signals"]
        score = rag_chunk_text_score(
            signals,
            literal_hits=literal,
            expanded_hits=expanded,
            anchor_hits=anchor_hits,
        )
        out.append(
            {
                "id": row_id,
                "start_message_id": row["start_message_id"],
                "end_message_id": row["end_message_id"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "roles": row["roles"],
                "anchor_titles": anchor_titles,
                "score": round(score, 3),
                "signals": {
                    **signals,
                    "literal_hits": literal,
                    "expanded_hits": expanded,
                    "anchor_hits": anchor_hits,
                },
                "summary": row["summary"],
                "snippet": compact_text(text, snippet_chars),
            }
        )

    out.sort(key=lambda item: (-item["score"], item["start_message_id"]))
    return out[:limit]


def search_rag_chunks(
    index: Path,
    query_terms: list[str],
    expanded_terms: list[str],
    anchor_matches: list[dict],
    *,
    limit: int = 6,
    candidate_limit: int = 80,
    snippet_chars: int = 900,
) -> list[dict]:
    con = sqlite3.connect(index)
    con.row_factory = sqlite3.Row
    try:
        return search_rag_chunks_connection(
            con,
            query_terms,
            expanded_terms,
            anchor_matches,
            limit=limit,
            candidate_limit=candidate_limit,
            snippet_chars=snippet_chars,
        )
    finally:
        con.close()


def search_hybrid_index(
    index: Path,
    query_terms: list[str],
    expanded_terms: list[str],
    anchor_matches: list[dict],
    *,
    limit: int = 20,
    candidate_limit: int = 160,
    snippet_chars: int = 700,
    context_radius: int = 0,
    use_rag_chunks: bool = True,
    structure_cues: dict[str, bool] | None = None,
    temporal_cue: dict[str, Any] | None = None,
) -> list[dict]:
    # CJK sidecar terms are default query-navigation material, not source
    # evidence or semantic aliases. They only broaden lexical matching for
    # no-space Chinese cues; source-backed claims still come from returned
    # message/chunk rows.
    default_expanded_terms = unique_preserve(
        list(expanded_terms) + cjk_query_sidecar_terms(" ".join(query_terms)),
        limit=64,
    )
    con = sqlite3.connect(index)
    con.row_factory = sqlite3.Row
    try:
        candidates: dict[int, dict] = {}
        query = fts_query(default_expanded_terms)
        if query:
            try:
                rows = con.execute(
                    f"""
                    SELECT {message_select_columns(con, "m")},
                           bm25(messages_fts) AS rank
                    FROM messages_fts f
                    JOIN messages m ON m.id = f.rowid
                    WHERE messages_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, candidate_limit),
                ).fetchall()
                for pos, row in enumerate(rows):
                    candidates[row["id"]] = {
                        "row": row,
                        "signals": {
                            "fts": scoring_policy.MESSAGE_FTS_POLICY.score_position(pos),
                            "fts_rank": float(row["rank"]),
                        },
                    }
            except sqlite3.Error:
                pass

        # LIKE fallback also adds candidates that FTS missed, especially when
        # a SQLite build lacks trigram support or the query contains punctuation.
        like_terms = unique_preserve(query_terms + default_expanded_terms, limit=18)
        if like_terms:
            where = " OR ".join(["text LIKE ?" for _ in like_terms])
            params = [f"%{term}%" for term in like_terms] + [candidate_limit]
            try:
                rows = con.execute(
                    f"""
                    SELECT {message_select_columns(con)}
                    FROM messages
                    WHERE {where}
                    ORDER BY id
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
                for row in rows:
                    item = candidates.setdefault(row["id"], {"row": row, "signals": {}})
                    item["signals"]["literal_scan"] = (
                        scoring_policy.RETRIEVAL_TEXT_POLICY.literal_scan_signal
                    )
            except sqlite3.Error:
                pass

        if use_rag_chunks:
            for chunk in search_rag_chunks_connection(
                con,
                query_terms,
                default_expanded_terms,
                anchor_matches,
                limit=12,
                candidate_limit=max(24, candidate_limit // 2),
                snippet_chars=snippet_chars,
            ):
                where = " OR ".join(["text LIKE ?" for _ in unique_preserve(query_terms, limit=8)])
                params = [f"%{term}%" for term in unique_preserve(query_terms, limit=8)]
                if where:
                    rows = con.execute(
                        f"""
                        SELECT {message_select_columns(con)}
                        FROM messages
                        WHERE id BETWEEN ? AND ? AND ({where})
                        ORDER BY is_final DESC, role = 'user' DESC, id
                        LIMIT 4
                        """,
                        [chunk["start_message_id"], chunk["end_message_id"], *params],
                    ).fetchall()
                else:
                    rows = []
                if not rows:
                    rows = con.execute(
                        """
                        SELECT {columns}
                        FROM messages
                        WHERE id BETWEEN ? AND ?
                        ORDER BY is_final DESC, role = 'user' DESC, id
                        LIMIT 2
                        """.format(columns=message_select_columns(con)),
                        (chunk["start_message_id"], chunk["end_message_id"]),
                    ).fetchall()
                for row in rows:
                    item = candidates.setdefault(row["id"], {"row": row, "signals": {}})
                    item["signals"]["rag_chunk"] = max(
                        float(item["signals"].get("rag_chunk", 0.0)),
                        chunk["score"] * scoring_policy.RETRIEVAL_TEXT_POLICY.rag_chunk_multiplier,
                    )
                    item["signals"]["rag_chunk_id"] = chunk["id"]

        if structure_cues or temporal_cue:
            for row in search_structure_time_connection(
                con,
                message_select_columns(con, "m"),
                structure_cues,
                temporal_cue,
                candidate_limit=candidate_limit,
            ):
                item = candidates.setdefault(row["id"], {"row": row, "signals": {}})
                if structure_cues:
                    item["signals"]["structure_lane_candidate"] = 1.0
                if temporal_cue:
                    item["signals"]["temporal_lane_candidate"] = 1.0

        results: list[dict] = []
        for row_id, item in candidates.items():
            row = item["row"]
            text = row["text"]
            literal = literal_hit_count(text, query_terms)
            expanded = literal_hit_count(text, default_expanded_terms)
            anchor_hits = anchor_hit_count(text, anchor_matches)
            signals = dict(item["signals"])
            weight = phase_weight(row)
            text_score = retrieval_text_score(
                signals,
                literal_hits=literal,
                expanded_hits=expanded,
                anchor_hits=anchor_hits,
                phase_weight=weight,
            )
            score = text_score
            if structure_cues or temporal_cue:
                feature = load_message_feature(con, row_id)
                signals.update(structure_signals(feature, structure_cues))
                signals.update(temporal_signals(row, feature, temporal_cue))
                score += float(signals.get("structure_match_score") or 0.0)
                score += float(signals.get("temporal_affinity_score") or 0.0)
                signals["text_score"] = round(text_score, 3)
            result = {
                "id": row["id"],
                "line": row["line"],
                "timestamp": row["timestamp"],
                "role": row["role"],
                "kind": row["kind"],
                "phase": row["phase"] or "",
                "turn_index": row["turn_index"],
                "is_final": bool(row["is_final"]),
                "score": round(score, 3),
                "signals": {
                    **signals,
                    "literal_hits": literal,
                    "expanded_hits": expanded,
                    "anchor_hits": anchor_hits,
                    "phase_weight": weight,
                },
                "snippet": compact_text(text, snippet_chars),
            }
            if context_radius > 0:
                result["context"] = context_window(
                    con, row_id, context_radius, max(180, snippet_chars // 3)
                )
            results.append(result)

        results.sort(key=lambda item: (-item["score"], item["id"]))
        return results[:limit]
    finally:
        con.close()


def graph_neighbors(graph_path: Path, terms: list[str], limit: int = 12) -> list[dict]:
    if not graph_path.exists():
        return []
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    nodes = {node.get("id"): node for node in graph.get("nodes", [])}
    matched_ids: set[str] = set()
    for node_id, node in nodes.items():
        label = str(node.get("label") or "").casefold()
        if any(term.casefold() in label for term in terms):
            matched_ids.add(str(node_id))
    neighbors: list[dict] = []
    seen: set[str] = set()
    for edge in graph.get("edges", []):
        src = str(edge.get("source"))
        dst = str(edge.get("target"))
        if src in matched_ids:
            seen.add(dst)
        if dst in matched_ids:
            seen.add(src)
    for node_id in list(matched_ids) + list(seen):
        node = nodes.get(node_id)
        if not node:
            continue
        neighbors.append(
            {
                "id": node_id,
                "type": node.get("type"),
                "label": node.get("label"),
                "matched": node_id in matched_ids,
            }
        )
        if len(neighbors) >= limit:
            break
    return neighbors


def active_recall_decision(
    prompt: str, anchor_matches: list[dict], health: dict | None = None
) -> dict:
    low = prompt.casefold()
    reasons: list[str] = []
    policy = scoring_policy.ACTIVE_RECALL_POLICY
    score = 0.0

    matched_triggers = [trigger for trigger in RECALL_TRIGGERS if trigger.casefold() in low]
    if matched_triggers:
        score += min(policy.recall_trigger_cap, len(matched_triggers) * policy.recall_trigger_weight)
        reasons.append(
            "message contains recall/deictic trigger(s): " + ", ".join(matched_triggers[:6])
        )

    matched_concepts = [trigger for trigger in CONCEPT_TRIGGERS if trigger.casefold() in low]
    if matched_concepts:
        score += min(policy.concept_trigger_cap, len(matched_concepts) * policy.concept_trigger_weight)
        reasons.append(
            "message mentions durable concept trigger(s): " + ", ".join(matched_concepts[:6])
        )

    if profile_recall_terms(prompt):
        # Profile/resume prompts are personal by nature, but this is still only
        # a search-route decision. Source-backed claims remain gated by the
        # downstream clean-source evidence path.
        score += policy.profile_cue_bonus
        reasons.append("message contains personal-profile recall cue")

    if life_wide_recall_terms(prompt):
        # Life-wide routes intentionally require recency plus a scope cue in
        # life_cues.py. This only opens deterministic search terms for the
        # explicit active_recall command; source-backed claims still need
        # downstream clean-source or registry evidence.
        score += policy.life_wide_cue_bonus
        reasons.append("message contains life-wide recall cue")

    if anchor_matches:
        anchor_score = sum(float(item.get("score") or 0) for item in anchor_matches[:3])
        score += min(policy.anchor_overlap_cap, anchor_score / policy.anchor_score_divisor)
        reasons.append(
            "message overlaps existing anchors: "
            + ", ".join(item["title"] for item in anchor_matches[:3])
        )

    if health:
        if health.get("index", {}).get("stale"):
            score += policy.stale_index_bonus
            reasons.append("thread index is stale")
        if health.get("checkpoint", {}).get("due"):
            score += policy.checkpoint_due_bonus
            reasons.append("checkpoint is due")
        if any(
            item.get("id") == "consider_graphify" for item in health.get("recommended_actions", [])
        ):
            score += policy.graphify_recommendation_bonus
            reasons.append("thread crossed the deep graph threshold")

    decision = "search" if score >= policy.search_threshold else "skip"
    confidence = (
        "high"
        if score >= policy.high_threshold
        else "medium"
        if score >= policy.search_threshold
        else "low"
    )
    return {
        "decision": decision,
        "score": round(score, 3),
        "confidence": confidence,
        "reasons": reasons or ["no strong long-thread recall trigger detected"],
    }
