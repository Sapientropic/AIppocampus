#!/usr/bin/env python3
"""Build a lightweight dynamic association index for ambient recall hooks.

The prompt hook must stay cheap and quiet, so it should not mine old SQLite
indexes or clean-source files while the user is typing. This script runs during
lifecycle maintenance and writes a small `associations.json` beside the global
registry. It deliberately treats automatically mined terms as staging hints;
curated anchors/keywords are the only verified source in v1.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from aippocampuslib import now_utc
from registry import load_registry, registry_paths, unique_preserve

ASSOCIATION_SCHEMA_VERSION = 1
DEFAULT_MAX_MESSAGES_PER_THREAD = 120
MAX_TERMS_PER_SOURCE = 18
MAX_RELATED_TERMS = 12


ASCII_STOP_TERMS = {
    "and",
    "are",
    "codex",
    "for",
    "from",
    "goal",
    "mode",
    "status",
    "that",
    "the",
    "this",
    "thread",
    "token",
    "true",
    "false",
    "with",
}

TRIVIAL_PHRASES = {
    "好",
    "好的",
    "好开干",
    "开干",
    "再想想",
    "继续",
    "好继续",
    "开始吧",
    "嗯",
    "关于",
    "当前线程",
    "前线程",
    "主题是什么",
    "ok",
    "okay",
}

SOURCE_NOISE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"#\s*AGENTS\.md instructions",
        r"<permissions instructions>",
        r"<environment_context>",
        r"\bcurrent goal\b",
        r"\btoken budget\b",
        r"\bremaining token\b",
        r"\bgoal mode\b",
        r"\bstatus\s+(active|paused|complete)\b",
        r"\bhookSpecificOutput\b",
    ]
]

CJK_BOUNDARY_WORDS = [
    "UserPromptSubmit",
    "associations",
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "一种",
    "一个",
    "把",
    "靠",
    "通过",
    "读取",
    "做成",
    "变成",
    "需要",
    "可以",
    "已经",
    "以及",
    "然后",
    "接着",
    "最后",
    "和",
    "与",
    "的",
    "了",
]

CJK_GLUE_NOISE = {
    "我们",
    "你们",
    "他们",
    "这个",
    "那个",
    "把",
    "靠",
    "读取",
    "做成",
    "通过",
    "更像",
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "或",
    "而",
    "但",
}

# This is not a user-facing alias table. It is a coarse source-side salience
# filter for CJK n-grams, so automatic extraction does not turn every ordinary
# sentence into hundreds of association terms.
DURABLE_CJK_HINTS = {
    "记忆",
    "联想",
    "召回",
    "海马",
    "触发",
    "钩子",
    "生命",
    "自我",
    "连续",
    "线程",
    "索引",
    "压缩",
    "归档",
    "证据",
    "结论",
    "轮次",
    "阶段",
    "工具",
}


def default_associations_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / "associations.json"
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / "associations.json"


def load_associations(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": ASSOCIATION_SCHEMA_VERSION, "updated_at": None, "terms": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": ASSOCIATION_SCHEMA_VERSION, "updated_at": None, "terms": {}}
    if not isinstance(data, dict):
        return {"schema_version": ASSOCIATION_SCHEMA_VERSION, "updated_at": None, "terms": {}}
    data.setdefault("schema_version", ASSOCIATION_SCHEMA_VERSION)
    data.setdefault("terms", {})
    return data


def save_associations(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def normalize_term(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value)).strip(" \t\r\n\"'`.,;:!?，。；：！？、()[]{}<>《》")
    return value


def source_text_is_noise(text: str) -> bool:
    stripped = re.sub(r"\s+", "", text).casefold()
    if stripped in TRIVIAL_PHRASES:
        return True
    return any(pattern.search(text) for pattern in SOURCE_NOISE_PATTERNS)


def term_is_noise(term: str) -> bool:
    term = normalize_term(term)
    if not term:
        return True
    low = term.casefold()
    squashed = re.sub(r"\s+", "", low)
    if squashed in TRIVIAL_PHRASES:
        return True
    if low in ASCII_STOP_TERMS:
        return True
    if low in {"goals", "budget", "remaining", "active", "paused", "complete"}:
        return True
    if any("\u4e00" <= ch <= "\u9fff" for ch in term) and any(
        marker in term for marker in CJK_GLUE_NOISE
    ):
        return True
    if len(term) < 3 and not any("\u4e00" <= ch <= "\u9fff" for ch in term):
        return True
    if re.fullmatch(r"\d+", term):
        return True
    if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", term):
        return True
    return False


def extract_ascii_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", text):
        if not term_is_noise(token):
            terms.append(token)
        # Domain/repo-like terms often appear in retrieved final answers as
        # `gogram.fun`, `gotd-runtime-spike`, or `foo_bar.py`, while the user's
        # later prompt naturally says only `gogram` or `gotd`. Add conservative
        # component aliases so ambient recall can smell those proper nouns
        # without hand-maintained query aliases.
        if re.search(r"[._-]", token):
            for part in re.split(r"[._-]+", token):
                part = normalize_term(part)
                if len(part) >= 4 and not term_is_noise(part):
                    terms.append(part)
    return terms


def component_aliases(term: str) -> list[str]:
    if not re.search(r"[._-]", term):
        return []
    aliases: list[str] = []
    for part in re.split(r"[._-]+", term):
        part = normalize_term(part)
        if len(part) >= 4 and not term_is_noise(part):
            aliases.append(part)
    return unique_preserve(aliases, limit=6)


def extract_cjk_terms(text: str) -> list[str]:
    terms: list[str] = []
    sequences = re.findall(r"[\u4e00-\u9fff]{3,32}", text)
    boundary_pattern = "|".join(
        re.escape(word) for word in sorted(CJK_BOUNDARY_WORDS, key=len, reverse=True)
    )
    for seq in sequences:
        if source_text_is_noise(seq):
            continue
        for phrase in re.split(boundary_pattern, seq):
            phrase = normalize_term(phrase)
            if 3 <= len(phrase) <= 12 and any(hint in phrase for hint in DURABLE_CJK_HINTS):
                if not term_is_noise(phrase):
                    terms.append(phrase)
        for size in range(3, min(8, len(seq)) + 1):
            for idx in range(0, len(seq) - size + 1):
                term = seq[idx : idx + size]
                if not any(hint in term for hint in DURABLE_CJK_HINTS):
                    continue
                if not term_is_noise(term):
                    terms.append(term)
    return terms


def term_rank(term: str) -> tuple[int, int, str]:
    cjk_bonus = 3 if any("\u4e00" <= ch <= "\u9fff" for ch in term) else 0
    durable_bonus = 4 if any(hint in term for hint in DURABLE_CJK_HINTS) else 0
    tech_bonus = 2 if re.search(r"[A-Z][A-Za-z]+|[._-]", term) else 0
    return (durable_bonus + tech_bonus + cjk_bonus, min(len(term), 24), term.casefold())


def extract_terms_from_text(text: str, *, limit: int = MAX_TERMS_PER_SOURCE) -> list[str]:
    if not text or source_text_is_noise(text):
        return []
    terms = extract_ascii_terms(text) + extract_cjk_terms(text)
    terms = unique_preserve([term for term in terms if not term_is_noise(term)], limit=None)
    terms.sort(key=term_rank, reverse=True)
    selected = terms[:limit]
    aliases: list[str] = []
    for term in selected:
        aliases.extend(component_aliases(term))
    return unique_preserve(selected + aliases, limit=limit + 8)


def source_record(
    entry: dict[str, Any],
    *,
    source: str,
    line: int | None = None,
    phase: str | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    record = {
        "thread_key": entry.get("thread_key"),
        "title": entry.get("title") or entry.get("workspace_name") or entry.get("thread_key"),
        "source": source,
    }
    if line is not None:
        record["line"] = line
    if phase:
        record["phase"] = phase
    if turn_index is not None:
        record["turn_index"] = turn_index
    return record


def add_association(
    terms: dict[str, dict[str, Any]],
    term: str,
    *,
    related_terms: list[str],
    entry: dict[str, Any],
    source: str,
    status: str,
    confidence: float,
    line: int | None = None,
    phase: str | None = None,
    turn_index: int | None = None,
) -> None:
    term = normalize_term(term)
    if term_is_noise(term):
        return
    key = term.casefold()
    item = terms.get(key)
    if not item:
        item = {
            "term": term,
            "status": status,
            "confidence": confidence,
            "hit_count": 0,
            "related_terms": [],
            "threads": [],
        }
        terms[key] = item
    elif status == "verified":
        item["status"] = "verified"
        item["confidence"] = max(float(item.get("confidence") or 0.0), confidence)
    else:
        item["confidence"] = max(float(item.get("confidence") or 0.0), confidence)

    item["hit_count"] = int(item.get("hit_count") or 0) + 1
    related = [
        normalize_term(value)
        for value in related_terms
        if normalize_term(value) and normalize_term(value).casefold() != key
    ]
    item["related_terms"] = unique_preserve(
        list(item.get("related_terms") or [])
        + [value for value in related if not term_is_noise(value)],
        limit=MAX_RELATED_TERMS,
    )

    record = source_record(entry, source=source, line=line, phase=phase, turn_index=turn_index)
    existing = {
        (
            source_item.get("thread_key"),
            source_item.get("source"),
            source_item.get("line"),
            source_item.get("phase"),
        )
        for source_item in item.get("threads") or []
    }
    ident = (
        record.get("thread_key"),
        record.get("source"),
        record.get("line"),
        record.get("phase"),
    )
    if ident not in existing:
        item.setdefault("threads", []).append(record)
        item["threads"] = item["threads"][:8]


def sqlite_final_messages(sqlite_path: Path, limit: int) -> list[dict[str, Any]]:
    if not sqlite_path.is_file():
        return []
    con = sqlite3.connect(sqlite_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT line, role, phase, turn_index, text
            FROM messages
            WHERE role = 'assistant'
              AND (phase = 'final_answer' OR is_final = 1)
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def clean_source_final_messages(messages_path: Path, limit: int) -> list[dict[str, Any]]:
    if not messages_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with messages_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("role") != "assistant":
                continue
            if not (item.get("is_final") or item.get("phase") == "final_answer"):
                continue
            rows.append(
                {
                    "line": item.get("source_line"),
                    "role": item.get("role"),
                    "phase": item.get("phase") or "final_answer",
                    "turn_index": item.get("turn_index"),
                    "text": item.get("text") or "",
                    "source": "clean_source_final_answer",
                }
            )
    rows.sort(key=lambda item: int(item.get("line") or 0), reverse=True)
    return rows[: max(1, int(limit))]


def collect_from_entry(
    entry: dict[str, Any], terms: dict[str, dict[str, Any]], *, max_messages_per_thread: int
) -> None:
    curated = unique_preserve(
        list(entry.get("anchor_titles") or []) + list(entry.get("keywords") or []),
        limit=80,
    )
    for term in curated:
        related = [item for item in curated if item != term]
        add_association(
            terms,
            term,
            related_terms=related,
            entry=entry,
            source="registry_anchor",
            status="verified",
            confidence=0.95,
        )

    paths = entry.get("paths") or {}
    sqlite_path = Path(paths.get("sqlite") or "")
    messages = sqlite_final_messages(sqlite_path, max_messages_per_thread)
    if not messages:
        clean_messages = paths.get("clean_source_messages_jsonl")
        messages = (
            clean_source_final_messages(Path(clean_messages), max_messages_per_thread)
            if clean_messages
            else []
        )
    for message in messages:
        source_terms = extract_terms_from_text(str(message.get("text") or ""))
        if not source_terms:
            continue
        for term in source_terms:
            add_association(
                terms,
                term,
                related_terms=[item for item in source_terms if item != term],
                entry=entry,
                source=message.get("source") or "final_answer",
                status="staging",
                confidence=0.62,
                line=message.get("line"),
                phase=message.get("phase") or "final_answer",
                turn_index=message.get("turn_index"),
            )


def build_associations(
    registry_path: Path, *, max_messages_per_thread: int = DEFAULT_MAX_MESSAGES_PER_THREAD
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    terms: dict[str, dict[str, Any]] = {}
    for entry in registry.get("threads") or []:
        collect_from_entry(entry, terms, max_messages_per_thread=max_messages_per_thread)

    sorted_terms = sorted(
        terms.values(),
        key=lambda item: (
            0 if item.get("status") == "verified" else 1,
            -float(item.get("confidence") or 0.0),
            -int(item.get("hit_count") or 0),
            str(item.get("term") or "").casefold(),
        ),
    )
    return {
        "schema_version": ASSOCIATION_SCHEMA_VERSION,
        "updated_at": now_utc(),
        "source_registry": str(registry_path),
        "thread_count": len(registry.get("threads") or []),
        "term_count": len(sorted_terms),
        "terms": {item["term"]: item for item in sorted_terms},
    }


def term_in_text(term: str, text: str) -> bool:
    term = normalize_term(term)
    if not term:
        return False
    if any("\u4e00" <= ch <= "\u9fff" for ch in term):
        return term in text
    return (
        re.search(
            rf"(?<![A-Za-z0-9_.-]){re.escape(term)}(?![A-Za-z0-9_.-])", text, flags=re.IGNORECASE
        )
        is not None
    )


def match_associations(
    prompt: str, associations: dict[str, Any], *, limit: int = 6
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if not prompt:
        return matches
    for item in (associations.get("terms") or {}).values():
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "")
        matched = []
        if not term_is_noise(term) and term_in_text(term, prompt):
            matched.append(term)
        if not matched:
            continue
        copy = dict(item)
        copy["matched_terms"] = unique_preserve(matched, limit=4)
        matches.append(copy)
    matches.sort(
        key=lambda item: (
            0 if item.get("status") == "verified" else 1,
            -float(item.get("confidence") or 0.0),
            -int(item.get("hit_count") or 0),
            str(item.get("term") or "").casefold(),
        )
    )
    return matches[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--output")
    parser.add_argument(
        "--max-messages-per-thread", type=int, default=DEFAULT_MAX_MESSAGES_PER_THREAD
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    output_path = (
        Path(args.output).resolve() if args.output else default_associations_path(registry_path)
    )
    result = build_associations(registry_path, max_messages_per_thread=args.max_messages_per_thread)
    save_associations(output_path, result)
    payload = {"output": str(output_path), **result}
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"associations: {output_path}")
        print(f"terms: {result['term_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
