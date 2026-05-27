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

from aippocampuslib import compact_text, parse_anchor_file

RECALL_TRIGGERS = [
    "还记得",
    "之前",
    "前面",
    "刚才",
    "上次",
    "继续",
    "我们说过",
    "你说过",
    "我说过",
    "那篇",
    "这篇",
    "那个",
    "这个",
    "小海马体",
    "外置海马体",
    "checkpoint",
    "anchor",
    "vault",
    "graphify",
    "rag",
    "召回",
    "记忆",
    "压缩",
    "compaction",
]


CONCEPT_TRIGGERS = {
    "外置海马体",
    "小海马体",
    "钩子",
    "触发式联想",
    "被动触发",
    "联想机制",
    "graphify",
    "rag",
    "semantic retrieval",
    "active recall",
    "context compaction",
    "compaction",
}


ALIASES = {
    "外置海马体": ["external hippocampus", "小海马体"],
    "小海马体": ["external hippocampus", "外置海马体"],
    "压缩": ["compaction", "context compaction"],
    "上下文压缩": ["context compaction", "compaction"],
    "主动召回": ["active recall"],
    "语义检索": ["semantic retrieval", "RAG"],
    "图谱": ["graph", "Graphify"],
    "钩子": ["hook", "hooks", "UserPromptSubmit"],
    "触发式联想": ["ambient recall", "active recall", "hook"],
    "被动触发": ["ambient recall", "UserPromptSubmit"],
    "联想机制": ["ambient recall", "active recall"],
}


STOP_TERMS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "about",
    "what",
    "when",
    "where",
    "how",
    "你",
    "我",
    "他",
    "她",
    "它",
    "了",
    "的",
    "是",
    "在",
    "和",
    "就",
    "也",
    "吧",
    "呢",
}


GENERIC_ANCHOR_TERMS = {
    "codex",
    "thread",
    "memory",
    "vault",
    "dashboard",
    "graph",
    "publish",
    "page",
    "skill",
    "skills",
    "note",
    "notes",
    "现在",
    "图谱",
    "页面",
    "线程",
    "记忆",
}


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
        return 18.0
    if role == "user":
        return 3.0
    if phase == "commentary":
        return -5.0
    if role == "tool":
        return -12.0
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


def unique_preserve(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = normalize_term(item)
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term).strip(" \t\r\n\"'`.,;:!?，。；：！？、()[]{}<>《》")


def split_query_terms(patterns: list[str]) -> list[str]:
    terms: list[str] = []
    for pattern in patterns:
        cleaned = normalize_term(pattern)
        if not cleaned:
            continue
        if len(cleaned) <= 32:
            terms.append(cleaned)
        for trigger in RECALL_TRIGGERS:
            if trigger.casefold() in cleaned.casefold() and len(trigger) >= 2:
                terms.append(trigger)
        for key, values in ALIASES.items():
            if key.casefold() in cleaned.casefold():
                terms.append(key)
                terms.extend(values)
        # Keep the full phrase, then add useful Latin subterms. For CJK prose,
        # avoid arbitrary full tokenization, but extract short content chunks so
        # vague prompts like "你还记得我之前说的那个CODEX官方人员的分享吗" still
        # search for CODEX / 官方人员 / 分享 instead of the entire sentence.
        for part in re.split(r"[\s,/|+]+", cleaned):
            part = normalize_term(part)
            if len(part) >= 3 and part.casefold() not in STOP_TERMS:
                terms.append(part)
        terms.extend(re.findall(r"[A-Za-z][A-Za-z0-9_.-]{1,}", cleaned))
        cjk = cleaned
        for trigger in RECALL_TRIGGERS:
            cjk = re.sub(re.escape(trigger), " ", cjk, flags=re.IGNORECASE)
        cjk = re.sub(r"[A-Za-z0-9_.-]+", " ", cjk)
        cjk = re.sub(
            r"(还记得|记得|这和|有关|关系|那段|这段|我|你|他说|她说|说的|说过|说|一个|一下|那个|这个|那篇|这篇|吗|嘛|呢|吧)",
            " ",
            cjk,
        )
        for chunk in re.split(r"[\s的了和与、，。；：！？,.!?/|+]+", cjk):
            chunk = normalize_term(chunk)
            if 2 <= len(chunk) <= 12 and chunk.casefold() not in STOP_TERMS:
                terms.append(chunk)
    return unique_preserve(terms)


def anchor_text(anchor: dict) -> str:
    parts = [
        anchor.get("title") or "",
        " ".join(anchor.get("keywords") or []),
        " ".join(anchor.get("notes") or []),
        " ".join(anchor.get("quotes") or []),
    ]
    return "\n".join(parts)


def score_anchor(anchor: dict, terms: list[str]) -> tuple[float, list[str]]:
    title = (anchor.get("title") or "").casefold()
    keywords = [str(k).casefold() for k in anchor.get("keywords") or []]
    blob = anchor_text(anchor).casefold()
    score = 0.0
    matched: list[str] = []
    for term in terms:
        low = term.casefold()
        if not low:
            continue
        local = 0.0
        if low in title:
            local += 5.0
        if any(low in keyword or keyword in low for keyword in keywords):
            local += 4.0
        if low in blob:
            local += 1.5
        if local:
            score += local
            matched.append(term)
    return score, unique_preserve(matched)


def match_anchors(anchor_path: Path, terms: list[str], limit: int = 6) -> list[dict]:
    anchors = parse_anchor_file(anchor_path)
    matches: list[dict] = []
    for idx, anchor in enumerate(anchors, start=1):
        score, matched = score_anchor(anchor, terms)
        if score <= 0:
            continue
        specific = [
            term
            for term in matched
            if term.casefold() not in GENERIC_ANCHOR_TERMS and len(term) > 2
        ]
        if not specific and score < 12:
            continue
        expanded = [anchor.get("title") or ""]
        expanded.extend(anchor.get("keywords") or [])
        expanded.extend(anchor.get("quotes") or [])
        matches.append(
            {
                "index": idx,
                "title": anchor.get("title") or f"Anchor {idx}",
                "score": round(score, 3),
                "matched_terms": matched,
                "keywords": anchor.get("keywords") or [],
                "expanded_terms": unique_preserve(expanded, limit=16),
                "notes": anchor.get("notes") or [],
                "sources": anchor.get("sources") or [],
            }
        )
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit]


def expanded_terms_from_anchors(
    query_terms: list[str], anchor_matches: list[dict], limit: int = 28
) -> list[str]:
    expanded = list(query_terms)
    for anchor in anchor_matches:
        expanded.extend(anchor.get("expanded_terms") or [])
    # Very long preserved quotes can make FTS queries brittle; keep them as
    # snippets for humans, not as search terms.
    return unique_preserve([term for term in expanded if len(term) <= 80], limit=limit)


def fts_query(terms: list[str], limit: int = 24) -> str:
    phrases = []
    for term in unique_preserve(terms, limit=limit):
        cleaned = term.replace('"', '""')
        if cleaned:
            phrases.append(f'"{cleaned}"')
    return " OR ".join(phrases)


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

    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(chunk) <= 12:
            terms.append(chunk)
        for n in (2, 3, 4):
            if len(chunk) < n:
                continue
            terms.extend(chunk[i : i + n] for i in range(0, len(chunk) - n + 1))

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
                        "chunk_fts": max(1.0, 60.0 - pos * 0.7),
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
                item["signals"]["chunk_literal_scan"] = 12.0
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
        score = (
            float(signals.get("chunk_fts", 0.0))
            + float(signals.get("chunk_literal_scan", 0.0))
            + literal * 16.0
            + max(0, expanded - literal) * 2.0
            + anchor_hits * 3.0
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


def _result_bucket(result: dict, anchor_matches: list[dict]) -> str:
    snippet = str(result.get("snippet") or "").casefold()
    for anchor in anchor_matches:
        title = str(anchor.get("title") or "")
        if title and title.casefold() in snippet:
            return "anchor:" + title
        for keyword in anchor.get("keywords") or []:
            key = str(keyword)
            if key and key.casefold() in snippet:
                return "anchor:" + title
    line = int(result.get("line") or 0)
    return f"{result.get('role') or 'unknown'}:{line // 200}"


def diversify_results(
    results: list[dict],
    limit: int,
    anchor_matches: list[dict] | None = None,
    *,
    mode: str = "balanced",
) -> list[dict]:
    """Return a source-diverse ordering for recall snippets.

    Long threads often contain later recaps that score higher than the original
    turn. Diversity keeps the best hit, then makes room for early/source hits
    and different buckets before filling the rest by score. This should stay a
    ranking policy, not a filter that hides evidence.
    """

    if mode == "none" or len(results) <= 2:
        return results[:limit]
    anchor_matches = anchor_matches or []
    pool = list(results)
    selected: list[dict] = []
    selected_ids: set[int] = set()

    def add(item: dict | None) -> None:
        if not item:
            return
        item_id = int(item.get("id") or item.get("line") or len(selected_ids) + 1)
        if item_id in selected_ids:
            return
        selected.append(item)
        selected_ids.add(item_id)

    add(pool[0])
    literal_hits = [item for item in pool if (item.get("signals") or {}).get("literal_hits", 0) > 0]
    add(
        min(
            (item for item in literal_hits if item.get("role") == "user"),
            key=lambda item: item.get("line") or 10**12,
            default=None,
        )
    )
    add(min(literal_hits, key=lambda item: item.get("line") or 10**12, default=None))
    add(
        max(
            (item for item in pool if item.get("role") == "assistant"),
            key=lambda item: item.get("score") or 0,
            default=None,
        )
    )

    while len(selected) < min(limit, len(pool)):
        best = None
        best_value = None
        selected_buckets = {_result_bucket(item, anchor_matches) for item in selected}
        selected_lines = [int(item.get("line") or 0) for item in selected]
        for item in pool:
            item_id = int(item.get("id") or item.get("line") or 0)
            if item_id in selected_ids:
                continue
            value = float(item.get("score") or 0)
            bucket = _result_bucket(item, anchor_matches)
            if bucket in selected_buckets:
                value -= 12.0
            line = int(item.get("line") or 0)
            if any(abs(line - other) < 25 for other in selected_lines):
                value -= 10.0
            if mode == "early" and (item.get("signals") or {}).get("literal_hits", 0) > 0:
                value += max(0.0, 8.0 - line / 250.0)
            if best_value is None or value > best_value:
                best = item
                best_value = value
        add(best)
        if best is None:
            break
    return selected[:limit]


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
) -> list[dict]:
    con = sqlite3.connect(index)
    con.row_factory = sqlite3.Row
    try:
        candidates: dict[int, dict] = {}
        query = fts_query(expanded_terms)
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
                            "fts": max(1.0, 80.0 - pos * 0.5),
                            "fts_rank": float(row["rank"]),
                        },
                    }
            except sqlite3.Error:
                pass

        # LIKE fallback also adds candidates that FTS missed, especially when
        # a SQLite build lacks trigram support or the query contains punctuation.
        like_terms = unique_preserve(query_terms + expanded_terms, limit=18)
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
                    item["signals"]["literal_scan"] = 15.0
            except sqlite3.Error:
                pass

        if use_rag_chunks:
            for chunk in search_rag_chunks_connection(
                con,
                query_terms,
                expanded_terms,
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
                        float(item["signals"].get("rag_chunk", 0.0)), chunk["score"] * 0.35
                    )
                    item["signals"]["rag_chunk_id"] = chunk["id"]

        results: list[dict] = []
        for row_id, item in candidates.items():
            row = item["row"]
            text = row["text"]
            literal = literal_hit_count(text, query_terms)
            expanded = literal_hit_count(text, expanded_terms)
            anchor_hits = anchor_hit_count(text, anchor_matches)
            score = 0.0
            signals = item["signals"]
            score += float(signals.get("fts", 0.0))
            score += float(signals.get("rag_chunk", 0.0))
            score += literal * 14.0
            # Expanded anchor terms are a recall aid, not permission for broad
            # anchors like "Codex" or "vault" to drown the user's actual clue.
            # Keep exact query terms dominant, then use anchors as a tie-breaker.
            score += max(0, expanded - literal) * 1.5
            score += anchor_hits * 2.0
            weight = phase_weight(row)
            score += weight
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
    score = 0.0

    matched_triggers = [trigger for trigger in RECALL_TRIGGERS if trigger.casefold() in low]
    if matched_triggers:
        score += min(6.0, len(matched_triggers) * 1.5)
        reasons.append(
            "message contains recall/deictic trigger(s): " + ", ".join(matched_triggers[:6])
        )

    matched_concepts = [trigger for trigger in CONCEPT_TRIGGERS if trigger.casefold() in low]
    if matched_concepts:
        score += min(4.0, len(matched_concepts) * 2.0)
        reasons.append(
            "message mentions durable concept trigger(s): " + ", ".join(matched_concepts[:6])
        )

    if anchor_matches:
        anchor_score = sum(float(item.get("score") or 0) for item in anchor_matches[:3])
        score += min(5.0, anchor_score / 4.0)
        reasons.append(
            "message overlaps existing anchors: "
            + ", ".join(item["title"] for item in anchor_matches[:3])
        )

    if health:
        if health.get("index", {}).get("stale"):
            score += 1.5
            reasons.append("thread index is stale")
        if health.get("checkpoint", {}).get("due"):
            score += 1.0
            reasons.append("checkpoint is due")
        if any(
            item.get("id") == "consider_graphify" for item in health.get("recommended_actions", [])
        ):
            score += 0.5
            reasons.append("thread crossed the deep graph threshold")

    decision = "search" if score >= 3.0 else "skip"
    confidence = "high" if score >= 6.0 else "medium" if score >= 3.0 else "low"
    return {
        "decision": decision,
        "score": round(score, 3),
        "confidence": confidence,
        "reasons": reasons or ["no strong long-thread recall trigger detected"],
    }
