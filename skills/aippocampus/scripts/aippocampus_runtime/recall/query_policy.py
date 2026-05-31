#!/usr/bin/env python3
"""Query expansion and anchor policy for local retrieval.

This module owns lexical policy: trigger words, aliases, anchor scoring, and
FTS query construction. Keep SQLite/RAG execution in `retrieval.py` so ranking
tuning can be reviewed without also editing storage access.
"""

from __future__ import annotations

import re
from pathlib import Path

from aippocampuslib import parse_anchor_file

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

# Keep these static concept and alias tables as a small bootstrap/fallback
# surface only. Multilingual or domain-specific semantic paraphrases should be
# learned into `semantic_cues.jsonl` or reviewed into `semantic_triggers.jsonl`
# and consumed through `semantic_trigger_terms()`; adding them here recreates
# the phrase-list sprawl this layer is meant to retire.
CONCEPT_TRIGGERS = {
    "钩子",
    "graphify",
    "rag",
    "context compaction",
    "compaction",
}

ALIASES = {
    "压缩": ["compaction", "context compaction"],
    "上下文压缩": ["context compaction", "compaction"],
    "图谱": ["graph", "Graphify"],
    "钩子": ["hook", "hooks", "UserPromptSubmit"],
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


def semantic_trigger_terms(rows: list[dict], limit: int = 24) -> list[str]:
    """Return query terms from dynamic semantic cue/trigger rows.

    Reviewed triggers and learned semantic cues are the replacement path for
    multilingual/domain-specific alias growth. Keep extraction here instead of
    adding those aliases back to `ALIASES`, so future tuning can inspect a data
    sidecar rather than editing a Python phrase table.
    """

    def iter_values(value: object) -> list[str]:
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                out.extend(iter_values(item))
            return out
        if isinstance(value, tuple):
            out = []
            for item in value:
                out.extend(iter_values(item))
            return out
        if isinstance(value, str):
            return [value]
        return []

    terms: list[str] = []
    for row in rows:
        values = [
            row.get("title"),
            row.get("matched_terms") or [],
            row.get("aliases") or [],
        ]
        for value in iter_values(values):
            term = normalize_term(str(value or ""))
            if not term or len(term) > 96:
                continue
            if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", term):
                continue
            terms.append(term)
    return unique_preserve(terms, limit=limit)


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
