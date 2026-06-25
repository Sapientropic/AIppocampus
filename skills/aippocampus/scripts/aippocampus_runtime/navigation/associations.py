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

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.io_integrity import atomic_write_json
from aippocampus_runtime.io_mtime_cache import load_json_object
from aippocampus_runtime.navigation.association_phrase_mining import (
    corpus_cjk_terms_for_text,
    mine_corpus_cjk_phrases,
)
from aippocampus_runtime.navigation.association_terms import (
    ASCII_BOUNDARY_CHARS,
    ascii_term_is_simple,
    extract_terms_from_text,
    normalize_term,
    term_is_noise,
)
from aippocampus_runtime.navigation.association_terms import (
    source_text_is_noise as source_text_is_noise,  # re-export for older runtime modules
)
from aippocampus_runtime.registry.api import load_registry, registry_paths, unique_preserve
from aippocampus_runtime.text import has_cjk_ideograph

ASSOCIATION_SCHEMA_VERSION = 1
DEFAULT_MAX_MESSAGES_PER_THREAD = 120
DEFAULT_MAX_PHRASE_MINING_MESSAGES_PER_THREAD = 24
DEFAULT_MAX_PHRASE_MINING_ROWS = 24000
DEFAULT_CORPUS_CJK_PHRASE_LIMIT = 400
MAX_TERMS_PER_SOURCE = 18
MAX_RELATED_TERMS = 12


ASCII_TERM_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
NUMERIC_TERM_RE = re.compile(r"\d+")
LOCAL_PATH_TERM_RE = re.compile(r"[A-Za-z]:\\|/(Users|home|tmp|var)/")


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
        data = load_json_object(path)
    except Exception:
        return {"schema_version": ASSOCIATION_SCHEMA_VERSION, "updated_at": None, "terms": {}}
    if not isinstance(data, dict):
        return {"schema_version": ASSOCIATION_SCHEMA_VERSION, "updated_at": None, "terms": {}}
    data.setdefault("schema_version", ASSOCIATION_SCHEMA_VERSION)
    data.setdefault("terms", {})
    return data


def save_associations(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data, indent=2)


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


def sqlite_source_messages(sqlite_path: Path, limit: int) -> list[dict[str, Any]]:
    if not sqlite_path.is_file():
        return []
    con = sqlite3.connect(sqlite_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT line, role, phase, turn_index, text
            FROM messages
            WHERE role = 'user'
               OR (role = 'assistant' AND (phase = 'final_answer' OR is_final = 1))
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


def clean_source_messages(messages_path: Path, limit: int) -> list[dict[str, Any]]:
    if not messages_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with messages_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = item.get("role")
            if role != "user" and not (
                role == "assistant" and (item.get("is_final") or item.get("phase") == "final_answer")
            ):
                continue
            rows.append(
                {
                    "line": item.get("source_line"),
                    "role": item.get("role"),
                    "phase": item.get("phase") or ("user" if role == "user" else "final_answer"),
                    "turn_index": item.get("turn_index"),
                    "text": item.get("text") or "",
                    "source": "clean_source_user_turn" if role == "user" else "clean_source_final_answer",
                }
            )
    rows.sort(key=lambda item: int(item.get("line") or 0), reverse=True)
    return rows[: max(1, int(limit))]


def source_messages_for_entry(entry: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    paths = entry.get("paths") or {}
    sqlite_path = Path(paths.get("sqlite") or "")
    messages = sqlite_source_messages(sqlite_path, limit)
    if messages:
        return messages
    clean_messages = paths.get("clean_source_messages_jsonl")
    return clean_source_messages(Path(clean_messages), limit) if clean_messages else []


def phrase_mining_rows(
    entry_messages: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    *,
    max_messages_per_thread: int = DEFAULT_MAX_PHRASE_MINING_MESSAGES_PER_THREAD,
    max_rows: int = DEFAULT_MAX_PHRASE_MINING_ROWS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry, messages in entry_messages:
        thread_key = str(entry.get("thread_key") or entry.get("title") or "")
        for index, message in enumerate(messages[: max(0, int(max_messages_per_thread))]):
            if len(rows) >= max_rows:
                return rows
            text = str(message.get("text") or "")
            if not text:
                continue
            doc_line = message.get("line") or message.get("turn_index") or index
            rows.append(
                {
                    "text": text,
                    "thread_key": thread_key,
                    "document_id": f"{thread_key}:{doc_line}",
                    "role": message.get("role"),
                }
            )
    return rows


def collect_from_entry(
    entry: dict[str, Any],
    terms: dict[str, dict[str, Any]],
    *,
    max_messages_per_thread: int,
    diagnostics: dict[str, int] | None = None,
    messages: list[dict[str, Any]] | None = None,
    corpus_cjk_phrases: dict[str, dict[str, Any]] | None = None,
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

    if messages is None:
        messages = source_messages_for_entry(entry, max_messages_per_thread)
    for message in messages:
        role = str(message.get("role") or "")
        source_terms = extract_terms_from_text(
            str(message.get("text") or ""),
            diagnostics=diagnostics,
            source_role="user" if role == "user" else "assistant",
        )
        mined_terms = corpus_cjk_terms_for_text(
            str(message.get("text") or ""),
            corpus_cjk_phrases,
            limit=6,
        )
        if mined_terms and diagnostics is not None:
            diagnostics["cjk_phrase_miner_attached_count"] = int(
                diagnostics.get("cjk_phrase_miner_attached_count") or 0
            ) + len(mined_terms)
        source_terms = unique_preserve(source_terms + mined_terms, limit=MAX_TERMS_PER_SOURCE + 8)
        if not source_terms:
            continue
        for term in source_terms:
            add_association(
                terms,
                term,
                related_terms=[item for item in source_terms if item != term],
                entry=entry,
                source=message.get("source")
                or ("user_turn" if role == "user" else "final_answer"),
                status="staging",
                confidence=0.62,
                line=message.get("line"),
                phase=message.get("phase") or "final_answer",
                turn_index=message.get("turn_index"),
            )


def build_associations(
    registry_path: Path,
    *,
    max_messages_per_thread: int = DEFAULT_MAX_MESSAGES_PER_THREAD,
    max_phrase_mining_messages_per_thread: int = DEFAULT_MAX_PHRASE_MINING_MESSAGES_PER_THREAD,
    max_phrase_mining_rows: int = DEFAULT_MAX_PHRASE_MINING_ROWS,
    corpus_cjk_phrase_limit: int = DEFAULT_CORPUS_CJK_PHRASE_LIMIT,
    include_phrase_report: bool = False,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    terms: dict[str, dict[str, Any]] = {}
    diagnostics: dict[str, int] = {
        "user_turn_term_count": 0,
        "assistant_final_term_count": 0,
        "salient_cjk_phrase_count": 0,
        "cjk_fragment_suppressed_count": 0,
        "cjk_phrase_miner_attached_count": 0,
    }
    registry_entries = list(registry.get("threads") or [])
    entry_messages = [
        (entry, source_messages_for_entry(entry, max_messages_per_thread))
        for entry in registry_entries
    ]
    corpus_cjk_phrases = mine_corpus_cjk_phrases(
        phrase_mining_rows(
            entry_messages,
            max_messages_per_thread=max_phrase_mining_messages_per_thread,
            max_rows=max_phrase_mining_rows,
        ),
        diagnostics=diagnostics,
        limit=corpus_cjk_phrase_limit,
    )
    for entry in registry.get("threads") or []:
        messages = next(
            (items for candidate, items in entry_messages if candidate is entry),
            None,
        )
        collect_from_entry(
            entry,
            terms,
            max_messages_per_thread=max_messages_per_thread,
            diagnostics=diagnostics,
            messages=messages,
            corpus_cjk_phrases=corpus_cjk_phrases,
        )

    sorted_terms = sorted(
        terms.values(),
        key=lambda item: (
            0 if item.get("status") == "verified" else 1,
            -float(item.get("confidence") or 0.0),
            -int(item.get("hit_count") or 0),
            str(item.get("term") or "").casefold(),
        ),
    )
    result = {
        "schema_version": ASSOCIATION_SCHEMA_VERSION,
        "updated_at": now_utc(),
        "source_registry": str(registry_path),
        "thread_count": len(registry.get("threads") or []),
        "term_count": len(sorted_terms),
        "diagnostics": diagnostics,
        "terms": {item["term"]: item for item in sorted_terms},
    }
    if include_phrase_report:
        result["phrase_mining_report"] = {
            "schema_version": 1,
            "candidate_count": diagnostics.get("cjk_phrase_miner_candidate_count", 0),
            "accepted_count": diagnostics.get("cjk_phrase_miner_accepted_count", 0),
            "phrases": corpus_cjk_phrases,
        }
    return result


def ascii_tokens_for_match(text: str) -> set[str]:
    tokens: set[str] = set()
    start: int | None = None
    for index, ch in enumerate(text):
        if ch in ASCII_BOUNDARY_CHARS:
            if start is None:
                start = index
            continue
        if start is not None:
            tokens.add(text[start:index].casefold())
            start = None
    if start is not None:
        tokens.add(text[start:].casefold())
    return tokens


def ascii_literal_with_boundary(term: str, text_casefold: str) -> bool:
    needle = term.casefold()
    start = 0
    while True:
        index = text_casefold.find(needle, start)
        if index < 0:
            return False
        before_ok = index == 0 or text_casefold[index - 1] not in ASCII_BOUNDARY_CHARS
        after_index = index + len(needle)
        after_ok = (
            after_index >= len(text_casefold)
            or text_casefold[after_index] not in ASCII_BOUNDARY_CHARS
        )
        if before_ok and after_ok:
            return True
        start = index + 1


def term_in_text(
    term: str,
    text: str,
    *,
    text_casefold: str | None = None,
    ascii_tokens: set[str] | None = None,
) -> bool:
    term = normalize_term(term)
    if not term:
        return False
    if has_cjk_ideograph(term):
        return term in text
    if ascii_term_is_simple(term):
        tokens = ascii_tokens if ascii_tokens is not None else ascii_tokens_for_match(text)
        return term.casefold() in tokens
    return ascii_literal_with_boundary(term, text_casefold or text.casefold())


def match_associations(
    prompt: str, associations: dict[str, Any], *, limit: int = 6
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if not prompt:
        return matches
    prompt_casefold = prompt.casefold()
    ascii_tokens = ascii_tokens_for_match(prompt)
    for item in (associations.get("terms") or {}).values():
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "")
        matched = []
        if not term_is_noise(term) and term_in_text(
            term,
            prompt,
            text_casefold=prompt_casefold,
            ascii_tokens=ascii_tokens,
        ):
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


def association_thread_count(item: dict[str, Any]) -> int:
    return len(
        {
            str(source.get("thread_key") or "")
            for source in item.get("threads") or []
            if isinstance(source, dict) and source.get("thread_key")
        }
    )


def association_is_prompt_noise(item: dict[str, Any], *, total_threads: int = 0) -> bool:
    """Return whether a matched association should stay out of prompt ranking.

    Association rows are staging navigation hints. A rare but clause-shaped CJK
    fragment can look excellent under IDF, so the prompt path rechecks phrase
    quality and broad fanout before `merge_association_candidates()` can boost a
    thread. Verified curated anchors still pass unless they are explicit noise.
    """

    term = str(item.get("term") or "")
    if term_is_noise(term):
        return True
    if item.get("status") == "verified":
        return False
    thread_count = association_thread_count(item)
    hit_count = int(item.get("hit_count") or 0)
    broad_floor = max(8, int(max(total_threads, 1) * 0.25))
    if total_threads and thread_count >= broad_floor and hit_count >= broad_floor:
        return True
    if has_cjk_ideograph(term) and len("".join(term.split())) >= 7:
        related = [str(value) for value in item.get("related_terms") or []]
        if not related and thread_count <= 1:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--output")
    parser.add_argument(
        "--max-messages-per-thread", type=int, default=DEFAULT_MAX_MESSAGES_PER_THREAD
    )
    parser.add_argument(
        "--max-phrase-mining-messages-per-thread",
        type=int,
        default=DEFAULT_MAX_PHRASE_MINING_MESSAGES_PER_THREAD,
    )
    parser.add_argument(
        "--max-phrase-mining-rows",
        type=int,
        default=DEFAULT_MAX_PHRASE_MINING_ROWS,
    )
    parser.add_argument(
        "--corpus-cjk-phrase-limit",
        type=int,
        default=DEFAULT_CORPUS_CJK_PHRASE_LIMIT,
    )
    parser.add_argument("--phrase-report-output")
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
    result = build_associations(
        registry_path,
        max_messages_per_thread=args.max_messages_per_thread,
        max_phrase_mining_messages_per_thread=args.max_phrase_mining_messages_per_thread,
        max_phrase_mining_rows=args.max_phrase_mining_rows,
        corpus_cjk_phrase_limit=args.corpus_cjk_phrase_limit,
        include_phrase_report=bool(args.phrase_report_output),
    )
    saved_result = dict(result)
    saved_result.pop("phrase_mining_report", None)
    save_associations(output_path, saved_result)
    if args.phrase_report_output:
        report_path = Path(args.phrase_report_output).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(result.get("phrase_mining_report") or {}, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
    payload = {"output": str(output_path), **result}
    if args.phrase_report_output:
        payload["phrase_report_output"] = str(Path(args.phrase_report_output).resolve())
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"associations: {output_path}")
        print(f"terms: {result['term_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
