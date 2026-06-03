"""Standard public retrieval-QA Track B adapters for LoCoMo and LongMemEval."""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

import benchmark_fts5_recall as fts5_benchmark
from aippocampuslib import compact_text
from benchmark_statistics import binomial_rate_report
from build_index import make_sqlite
from retrieval import split_query_terms
from subconscious_runtime import add_usage, call_chat_json, compact_usage
from subconscious_worker import DEFAULT_BASE_URL, DEFAULT_MODEL, clamp_confidence, parse_model_json

from .defaults import (
    DEFAULT_STANDARD_DATASET,
    DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    DEFAULT_STANDARD_LINE_RERANKER_MODE,
    DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    DEFAULT_STANDARD_QA_CASES,
    DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    DEFAULT_STANDARD_QA_MIN_CASES,
    DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    DEFAULT_STANDARD_QA_TOP_K,
    SCHEMA_VERSION,
    STANDARD_DATASET_PATHS,
    STANDARD_LINE_RERANKER_MODES,
    STANDARD_QUERY_TERM_STOPWORDS,
    LineRerankerFn,
)
from .reporting import (
    now_utc,
    reciprocal_rank,
    safe_rate,
    sha1_text,
)


def standard_content_query_terms(question: str, *, limit: int = 24) -> list[str]:
    terms: list[str] = []
    for term in split_query_terms([question]):
        clean = term.strip()
        low = clean.casefold()
        if not clean or low in STANDARD_QUERY_TERM_STOPWORDS:
            continue
        if len(clean) < 3 and not re.search(r"\d", clean):
            continue
        if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", clean):
            continue
        terms.append(clean)
    return fts5_benchmark.unique_preserve(terms, limit=limit)


def iter_json_array_items(path: Path, *, max_items: int | None = None) -> Any:
    """Stream top-level JSON-array objects without loading multi-GB corpora."""

    yielded = 0
    with path.open("r", encoding="utf-8") as handle:
        in_string = False
        escape = False
        depth = 0
        started = False
        buffer: list[str] = []
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            for char in chunk:
                if not started:
                    if char == "{":
                        started = True
                        depth = 1
                        buffer = [char]
                    continue
                buffer.append(char)
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        yield json.loads("".join(buffer))
                        yielded += 1
                        if max_items is not None and yielded >= max_items:
                            return
                        started = False
                        buffer = []


def standard_message_for_sqlite(
    *,
    source_id: str,
    line: int,
    role: str,
    text: str,
    timestamp: str = "",
) -> dict[str, Any]:
    identity = "|".join([source_id, str(line), role, text])
    return {
        "line": line,
        "timestamp": timestamp,
        "role": role,
        "kind": "message",
        "phase": "final_answer" if role == "assistant" else "",
        "turn_index": line,
        "is_final": role == "assistant",
        "sha1": sha1_text(identity),
        "text": text,
    }


def locomo_session_sort_key(key: str) -> int:
    match = re.fullmatch(r"session_(\d+)", key)
    return int(match.group(1)) if match else 0


def build_locomo_messages(sample: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], dict[int, str]]:
    raw_conversation = sample.get("conversation")
    conversation: dict[str, Any] = (
        raw_conversation if isinstance(raw_conversation, dict) else {}
    )
    source_id = str(sample.get("sample_id") or "locomo-sample")
    messages: list[dict[str, Any]] = []
    dialogue_to_line: dict[str, int] = {}
    line_to_session: dict[int, str] = {}
    line = 1
    for session_key in sorted(
        [key for key, value in conversation.items() if key.startswith("session_") and isinstance(value, list)],
        key=locomo_session_sort_key,
    ):
        session_number = locomo_session_sort_key(session_key)
        session_id = f"D{session_number}" if session_number else session_key
        session_date = str(conversation.get(f"{session_key}_date_time") or "")
        for row in conversation.get(session_key) or []:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            speaker = str(row.get("speaker") or "speaker")
            dia_id = str(row.get("dia_id") or f"{session_id}:{line}")
            source_text = f"Session date: {session_date}\n{speaker}: {text}".strip()
            messages.append(
                standard_message_for_sqlite(
                    source_id=source_id,
                    line=line,
                    role=speaker,
                    text=source_text,
                    timestamp=session_date,
                )
            )
            dialogue_to_line[dia_id] = line
            line_to_session[line] = session_id
            line += 1
    return messages, dialogue_to_line, line_to_session


def add_standard_case(
    cases: list[dict[str, Any]],
    *,
    dataset: str,
    case_type: str,
    source_id: str,
    question_id: str,
    question: str,
    sqlite_path: Path,
    expected_lines: list[int],
    expected_sessions: list[str],
    line_to_session: dict[int, str],
    include_answerable_line_metric: bool,
) -> None:
    case_id = sha1_text("\n".join([dataset, source_id, question_id, question]))[:16]
    cases.append(
        {
            "case_id": case_id,
            "dataset": dataset,
            "case_type": case_type,
            "source_id": source_id,
            "source_id_sha1": sha1_text(source_id)[:16],
            "question_id_sha1": sha1_text(question_id)[:16],
            "query": question,
            "query_sha1": sha1_text(question)[:16],
            "query_terms": split_query_terms([question]),
            "sqlite_path": sqlite_path,
            "expected": {
                "lines": sorted({int(line) for line in expected_lines if int(line) > 0}),
                "sessions": sorted({str(session) for session in expected_sessions if session}),
                "line_to_session": {str(key): value for key, value in line_to_session.items()},
                "has_line_evidence": bool(include_answerable_line_metric and expected_lines),
            },
        }
    )


def build_locomo_standard_cases(
    root: Path,
    *,
    corpus_path: Path,
    max_questions: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    corpus: dict[str, Any] = {
        "dataset": "locomo",
        "samples_scanned": 0,
        "messages_scanned": 0,
        "questions_scanned": 0,
        "eligible_questions": 0,
    }
    for sample in iter_json_array_items(corpus_path):
        if len(cases) >= max_questions:
            break
        if not isinstance(sample, dict):
            continue
        corpus["samples_scanned"] += 1
        source_id = str(sample.get("sample_id") or f"locomo-{corpus['samples_scanned']}")
        messages, dialogue_to_line, line_to_session = build_locomo_messages(sample)
        corpus["messages_scanned"] += len(messages)
        if not messages:
            continue
        sqlite_path = root / "standard" / "locomo" / sha1_text(source_id)[:12] / "index" / "source_index.sqlite"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        make_sqlite(sqlite_path, messages, anchors=[], turns=[])
        for qa_index, qa in enumerate(sample.get("qa") or []):
            if len(cases) >= max_questions:
                break
            if not isinstance(qa, dict):
                continue
            corpus["questions_scanned"] += 1
            question = str(qa.get("question") or "").strip()
            evidence_ids = [str(item) for item in qa.get("evidence") or []]
            expected_lines = [dialogue_to_line[item] for item in evidence_ids if item in dialogue_to_line]
            if not question or not expected_lines:
                continue
            expected_sessions = [str(item).split(":", 1)[0] for item in evidence_ids]
            add_standard_case(
                cases,
                dataset="locomo",
                case_type=f"locomo_category_{qa.get('category', 'unknown')}",
                source_id=source_id,
                question_id=f"{source_id}:{qa_index}",
                question=question,
                sqlite_path=sqlite_path,
                expected_lines=expected_lines,
                expected_sessions=expected_sessions,
                line_to_session=line_to_session,
                include_answerable_line_metric=True,
            )
            corpus["eligible_questions"] += 1
    return cases, corpus


def build_longmemeval_messages(
    item: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[int, str], list[int]]:
    question_id = str(item.get("question_id") or "longmemeval-question")
    session_ids = [str(value) for value in item.get("haystack_session_ids") or []]
    session_dates = [str(value) for value in item.get("haystack_dates") or []]
    sessions = item.get("haystack_sessions") or []
    answer_sessions = {str(value) for value in item.get("answer_session_ids") or []}
    messages: list[dict[str, Any]] = []
    line_to_session: dict[int, str] = {}
    answer_lines: list[int] = []
    line = 1
    for session_index, rows in enumerate(sessions):
        if not isinstance(rows, list):
            continue
        session_id = session_ids[session_index] if session_index < len(session_ids) else f"session-{session_index}"
        session_date = session_dates[session_index] if session_index < len(session_dates) else ""
        for row in rows:
            if not isinstance(row, dict):
                continue
            content = str(row.get("content") or row.get("text") or "").strip()
            if not content:
                continue
            role = str(row.get("role") or "")
            source_text = f"Session date: {session_date}\nSession id: {session_id}\n{role}: {content}".strip()
            messages.append(
                standard_message_for_sqlite(
                    source_id=question_id,
                    line=line,
                    role=role,
                    text=source_text,
                    timestamp=session_date,
                )
            )
            line_to_session[line] = session_id
            if session_id in answer_sessions and bool(row.get("has_answer")):
                answer_lines.append(line)
            line += 1
    return messages, line_to_session, answer_lines


def build_longmemeval_v1_standard_cases(
    root: Path,
    *,
    dataset: str,
    corpus_path: Path,
    max_questions: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    corpus: dict[str, Any] = {
        "dataset": dataset,
        "questions_scanned": 0,
        "eligible_questions": 0,
        "messages_scanned": 0,
        "session_count": 0,
    }
    for item in iter_json_array_items(corpus_path, max_items=max_questions):
        if len(cases) >= max_questions:
            break
        if not isinstance(item, dict):
            continue
        corpus["questions_scanned"] += 1
        question = str(item.get("question") or "").strip()
        answer_sessions = [str(value) for value in item.get("answer_session_ids") or []]
        if not question or not answer_sessions:
            continue
        question_id = str(item.get("question_id") or f"longmem-{corpus['questions_scanned']}")
        messages, line_to_session, answer_lines = build_longmemeval_messages(item)
        if not messages:
            continue
        corpus["messages_scanned"] += len(messages)
        corpus["session_count"] += len(item.get("haystack_sessions") or [])
        sqlite_path = root / "standard" / dataset / sha1_text(question_id)[:12] / "index" / "source_index.sqlite"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        make_sqlite(sqlite_path, messages, anchors=[], turns=[])
        add_standard_case(
            cases,
            dataset=dataset,
            case_type=f"longmemeval_{item.get('question_type', 'unknown')}",
            source_id=question_id,
            question_id=question_id,
            question=question,
            sqlite_path=sqlite_path,
            expected_lines=answer_lines,
            expected_sessions=answer_sessions,
            line_to_session=line_to_session,
            include_answerable_line_metric=bool(answer_lines),
        )
        corpus["eligible_questions"] += 1
    return cases, corpus


def rank_expected_line(hits: list[dict[str, Any]], expected_lines: set[int]) -> int | None:
    if not expected_lines:
        return None
    for idx, hit in enumerate(hits, start=1):
        raw_line = hit.get("line")
        if raw_line is None:
            continue
        try:
            line = int(raw_line)
        except (TypeError, ValueError):
            continue
        if line in expected_lines:
            return idx
    return None


def rank_expected_session(
    hits: list[dict[str, Any]],
    *,
    line_to_session: dict[str, str],
    expected_sessions: set[str],
) -> int | None:
    if not expected_sessions:
        return None
    for idx, hit in enumerate(hits, start=1):
        raw_line = hit.get("line")
        if raw_line is None:
            continue
        try:
            line = str(int(raw_line))
        except (TypeError, ValueError):
            continue
        if line_to_session.get(line) in expected_sessions:
            return idx
    return None


def rank_expected_line_context(
    hits: list[dict[str, Any]],
    *,
    expected_lines: set[int],
    line_to_session: dict[str, str],
    radius: int,
) -> int | None:
    if not expected_lines:
        return None
    bounded_radius = max(0, int(radius))
    for idx, hit in enumerate(hits, start=1):
        raw_line = hit.get("line")
        if raw_line is None:
            continue
        try:
            hit_line = int(raw_line)
        except (TypeError, ValueError):
            continue
        hit_session = line_to_session.get(str(hit_line))
        for expected_line in expected_lines:
            if abs(hit_line - expected_line) > bounded_radius:
                continue
            expected_session = line_to_session.get(str(expected_line))
            if hit_session and expected_session and hit_session != expected_session:
                continue
            return idx
    return None


def load_standard_message_rows(sqlite_path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(sqlite_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, line, role, text FROM messages ORDER BY id"
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def ranked_unique_lines(ranked_lines: list[Any], candidates: list[dict[str, Any]]) -> list[int]:
    candidate_lines = [int(candidate["line"]) for candidate in candidates]
    candidate_set = set(candidate_lines)
    selected: list[int] = []
    seen: set[int] = set()
    for value in ranked_lines:
        try:
            line = int(value)
        except (TypeError, ValueError):
            continue
        if line not in candidate_set or line in seen:
            continue
        selected.append(line)
        seen.add(line)
    for line in candidate_lines:
        if line not in seen:
            selected.append(line)
            seen.add(line)
    return selected


def best_rank(*ranks: int | None) -> int | None:
    present = [int(rank) for rank in ranks if rank]
    return min(present) if present else None


def build_standard_line_reranker_candidates(
    sqlite_path: Path,
    hits: list[dict[str, Any]],
    *,
    extra_hit_lists: list[tuple[str, list[dict[str, Any]]]] | None = None,
    line_to_session: dict[str, str],
    top_k: int,
    context_radius: int,
    top_sessions: int,
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Build source-visible line candidates from top sessions and hit contexts.

    This is deliberately bounded: the second stage can only reorder lines that
    the first-stage retriever already made visible via a top session and nearby
    source context. Do not "helpfully" add answer labels or whole unrelated
    sessions here; that would turn the benchmark into oracle leakage.
    """

    hit_lists: list[tuple[str, list[dict[str, Any]]]] = [("base", hits)]
    hit_lists.extend(extra_hit_lists or [])
    session_first_rank: dict[str, int] = {}
    for _, channel_hits in hit_lists:
        for rank, hit in enumerate(channel_hits, start=1):
            session_id = line_to_session.get(str(hit.get("line")))
            if session_id and (
                session_id not in session_first_rank or rank < session_first_rank[session_id]
            ):
                session_first_rank[session_id] = rank
    selected_sessions: set[str] = set()
    if int(top_sessions) > 0:
        selected_sessions = {
            session_id
            for session_id, _ in sorted(session_first_rank.items(), key=lambda item: item[1])[
                : int(top_sessions)
            ]
        }
    rows = load_standard_message_rows(sqlite_path)
    row_by_line = {int(row["line"]): row for row in rows}
    hit_rank_by_line: dict[int, int] = {}
    for _, channel_hits in hit_lists:
        for rank, hit in enumerate(channel_hits, start=1):
            try:
                line = int(hit["line"])
            except (TypeError, ValueError, KeyError):
                continue
            previous_rank = hit_rank_by_line.get(line)
            if previous_rank is None or rank < previous_rank:
                hit_rank_by_line[line] = rank
    candidate_meta: dict[int, dict[str, Any]] = {}
    for channel, channel_hits in hit_lists:
        for hit_rank, hit in enumerate(channel_hits[:top_k], start=1):
            raw_line = hit.get("line")
            if raw_line is None:
                continue
            try:
                hit_line = int(raw_line)
            except (TypeError, ValueError):
                continue
            session_id = line_to_session.get(str(hit_line))
            if not session_id:
                continue
            if selected_sessions and session_id not in selected_sessions:
                continue
            for line in range(hit_line - context_radius, hit_line + context_radius + 1):
                row = row_by_line.get(line)
                if not row or line_to_session.get(str(line)) != session_id:
                    continue
                distance = abs(line - hit_line)
                rank_tuple = (
                    session_first_rank.get(session_id, 10**6),
                    hit_rank,
                    distance,
                    line,
                )
                previous_meta = candidate_meta.get(line)
                if previous_meta:
                    previous_meta.setdefault("query_channels", set()).add(channel)
                    if tuple(previous_meta["rank_tuple"]) <= rank_tuple:
                        continue
                candidate_meta[line] = {
                    "nearest_hit_rank": hit_rank,
                    "nearest_hit_line": hit_line,
                    "context_distance": distance,
                    "rank_tuple": rank_tuple,
                    "query_channels": {channel},
                }
    candidates: list[dict[str, Any]] = []
    for line, meta in candidate_meta.items():
        row = row_by_line[line]
        session_id = line_to_session.get(str(line)) or ""
        candidates.append(
            {
                "line": line,
                "role": row.get("role") or "",
                "session_id": session_id,
                "session_rank": session_first_rank.get(session_id, 10**6),
                "fts_rank": hit_rank_by_line.get(line),
                "nearest_hit_rank": int(meta["nearest_hit_rank"]),
                "nearest_hit_line": int(meta["nearest_hit_line"]),
                "context_distance": int(meta["context_distance"]),
                "query_channels": sorted(str(item) for item in meta["query_channels"]),
                "text": str(row.get("text") or ""),
            }
        )
    candidates.sort(
        key=lambda item: (
            int(item["session_rank"]),
            int(item["nearest_hit_rank"]),
            int(item["context_distance"]),
            int(item["line"]),
        )
    )
    return candidates[: max(1, int(max_candidates))]


def semantic_line_reranker_available(api_key_env: str = "DEEPSEEK_API_KEY") -> bool:
    return bool(os.environ.get(api_key_env))


def line_reranker_error_kind(error: Any) -> str:
    text = str(error or "").casefold()
    if "length" in text or "max-tokens" in text or "max_tokens" in text:
        return "max_tokens"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "json" in text or "parse" in text or "decode" in text:
        return "parse_error"
    if "401" in text or "403" in text or "auth" in text or "api key" in text:
        return "auth_error"
    if "429" in text or "rate" in text:
        return "rate_limit"
    if "connect" in text or "connection" in text or "network" in text:
        return "connection_error"
    return "line_reranker_error"


def semantic_line_reranker_messages(
    *,
    question: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    candidate_rows = [
        {
            "line": int(candidate["line"]),
            "role": candidate.get("role") or "",
            "session_rank": candidate.get("session_rank"),
            "nearest_hit_rank": candidate.get("nearest_hit_rank"),
            "context_distance": candidate.get("context_distance"),
            "text": compact_text(str(candidate.get("text") or ""), 700),
        }
        for candidate in candidates
    ]
    system = """You are AIppocampus source-line reranker.
Rank only the provided source lines by how directly each line contains the
evidence needed to answer the user's question.

Rules:
- Return JSON only.
- Do not answer the question.
- Do not invent or quote outside information.
- Prefer the original user/source statement over an assistant paraphrase when
  both mention the same fact.
- If a nearby assistant line helps identify the fact, rank the source line that
  actually states the fact first.
- Use only candidate line numbers from the input.
"""
    user = json.dumps(
        {
            "question": question,
            "candidate_lines": candidate_rows,
            "output_shape": {
                "ranked_lines": ["line numbers, best first"],
                "confidence": "0.0-1.0",
            },
        },
        ensure_ascii=False,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def run_semantic_line_reranker(
    question: str,
    candidates: list[dict[str, Any]],
    *,
    timeout: int = DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    api_key_env: str = "DEEPSEEK_API_KEY",
    model: str | None = None,
    base_url: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        return {
            "available": False,
            "ranked_lines": [],
            "errors": ["missing semantic line-reranker api key"],
        }
    if not candidates:
        return {"available": False, "ranked_lines": [], "errors": ["empty candidates"]}
    response = call_chat_json(
        semantic_line_reranker_messages(question=question, candidates=candidates),
        api_key,
        model or os.environ.get("AIPPOCAMPUS_LINE_RERANKER_MODEL") or DEFAULT_MODEL,
        base_url or os.environ.get("AIPPOCAMPUS_LINE_RERANKER_BASE_URL") or DEFAULT_BASE_URL,
        None if max_tokens is None or int(max_tokens) <= 0 else int(max_tokens),
        int(timeout),
        0.0,
    )
    parsed = parse_model_json(response)
    return {
        "available": True,
        "ranked_lines": parsed.get("ranked_lines") or [],
        "confidence": clamp_confidence(parsed.get("confidence")),
        "usage": compact_usage(response.get("usage") or {}),
    }


def evaluate_standard_retrieval_case(
    case: dict[str, Any],
    *,
    top_k: int,
    candidate_limit: int,
    context_radius: int,
    include_private_text: bool,
    line_reranker_mode: str = DEFAULT_STANDARD_LINE_RERANKER_MODE,
    line_reranker_fn: LineRerankerFn | None = None,
    line_reranker_top_sessions: int = DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    line_reranker_max_candidates: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    line_reranker_timeout: int = DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    line_reranker_max_tokens: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
) -> dict[str, Any]:
    expected = case.get("expected") or {}
    hits, warnings = fts5_benchmark.search_fts5_only(
        case["sqlite_path"],
        case["query_terms"],
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
    )
    expected_lines = {int(value) for value in expected.get("lines") or []}
    line_to_session = {
        str(k): str(v) for k, v in (expected.get("line_to_session") or {}).items()
    }
    evidence_rank = rank_expected_line(
        hits,
        expected_lines,
    )
    evidence_context_rank = rank_expected_line_context(
        hits,
        expected_lines=expected_lines,
        line_to_session=line_to_session,
        radius=context_radius,
    )
    session_rank = rank_expected_session(
        hits,
        line_to_session=line_to_session,
        expected_sessions={str(value) for value in expected.get("sessions") or []},
    )
    row: dict[str, Any] = {
        "case_id": case["case_id"],
        "dataset": case["dataset"],
        "case_type": case["case_type"],
        "source_id_sha1": case["source_id_sha1"],
        "question_id_sha1": case["question_id_sha1"],
        "query_sha1": case["query_sha1"],
        "query_terms_count": len(case.get("query_terms") or []),
        "expected_line_count": len(expected.get("lines") or []),
        "expected_session_count": len(expected.get("sessions") or []),
        "has_line_evidence": bool(expected.get("has_line_evidence")),
        "evidence_rank": evidence_rank,
        f"evidence_hit_top{top_k}": bool(evidence_rank and evidence_rank <= top_k),
        "evidence_context_rank": evidence_context_rank,
        f"evidence_context_hit_top{top_k}": bool(
            evidence_context_rank and evidence_context_rank <= top_k
        ),
        "session_rank": session_rank,
        f"session_hit_top{top_k}": bool(session_rank and session_rank <= top_k),
        "warning_count": len(warnings),
    }
    resolved_reranker_mode = line_reranker_mode.strip().casefold()
    if resolved_reranker_mode not in STANDARD_LINE_RERANKER_MODES:
        raise ValueError(f"unsupported line reranker mode: {line_reranker_mode}")
    if resolved_reranker_mode != "off":
        content_hits: list[dict[str, Any]] = []
        content_terms = standard_content_query_terms(str(case.get("query") or ""))
        if content_terms and content_terms != list(case.get("query_terms") or []):
            content_hits, content_warnings = fts5_benchmark.search_fts5_only(
                case["sqlite_path"],
                content_terms,
                limit=max(top_k, candidate_limit),
                candidate_limit=candidate_limit,
            )
            warnings.extend(content_warnings)
            row["warning_count"] = len(warnings)
        candidates = build_standard_line_reranker_candidates(
            case["sqlite_path"],
            hits,
            extra_hit_lists=[("content", content_hits)] if content_hits else None,
            line_to_session=line_to_session,
            top_k=top_k,
            context_radius=context_radius,
            top_sessions=line_reranker_top_sessions,
            max_candidates=line_reranker_max_candidates,
        )
        semantic_lines: list[int] = []
        reranker_payload: dict[str, Any] = {}
        reranker_errors: list[str] = []
        try:
            runner = line_reranker_fn or run_semantic_line_reranker
            reranker_payload = runner(
                str(case.get("query") or ""),
                candidates,
                timeout=line_reranker_timeout,
                max_tokens=line_reranker_max_tokens,
            )
            semantic_lines = ranked_unique_lines(
                list(reranker_payload.get("ranked_lines") or []),
                candidates,
            )
        except Exception as exc:  # pragma: no cover - exercised by live backend failures
            reranker_errors = [line_reranker_error_kind(exc)]
        semantic_only_rank = rank_expected_line(
            [{"line": line} for line in semantic_lines[:top_k]],
            expected_lines,
        )
        # Product-facing second stage is FTS-preserving: semantic ranking can
        # promote exact source rows inside the top-session/top-context boundary,
        # but it should not hide a row already surfaced by first-stage FTS. Keep
        # semantic-only metrics separate so regressions remain visible.
        reranked_rank = best_rank(evidence_rank, semantic_only_rank)
        row.update(
            {
                "line_reranker_mode": resolved_reranker_mode,
                "line_reranker_attempted": True,
                "line_reranker_available": bool(reranker_payload.get("available")),
                "line_reranker_candidate_count": len(candidates),
                "line_reranker_candidate_contains_evidence": bool(
                    expected_lines & {int(candidate["line"]) for candidate in candidates}
                ),
                "line_reranker_query_channels": sorted(
                    {
                        channel
                        for candidate in candidates
                        for channel in (candidate.get("query_channels") or [])
                    }
                ),
                "line_reranker_error_kinds": sorted(
                    {
                        *reranker_errors,
                        *[
                            line_reranker_error_kind(error)
                            for error in (reranker_payload.get("errors") or [])
                        ],
                    }
                ),
                "line_reranker_error_count": len(reranker_errors)
                + len(list(reranker_payload.get("errors") or [])),
                "line_reranker_confidence": clamp_confidence(
                    reranker_payload.get("confidence")
                ),
                "line_reranker_usage": compact_usage(reranker_payload.get("usage") or {}),
                "semantic_only_evidence_rank": semantic_only_rank,
                f"semantic_only_evidence_hit_top{top_k}": bool(
                    semantic_only_rank and semantic_only_rank <= top_k
                ),
                "reranked_evidence_rank": reranked_rank,
                f"reranked_evidence_hit_top{top_k}": bool(
                    reranked_rank and reranked_rank <= top_k
                ),
            }
        )
        if include_private_text:
            row["semantic_top_lines"] = semantic_lines[:top_k]
    if include_private_text:
        row.update(
            {
                "source_id": case.get("source_id"),
                "question": case.get("query"),
                "expected_lines": expected.get("lines") or [],
                "expected_sessions": expected.get("sessions") or [],
                "top_lines": [hit.get("line") for hit in hits[:top_k]],
            }
        )
    return row


def summarize_standard_retrieval_results(
    results: list[dict[str, Any]],
    *,
    top_k: int,
    context_radius: int,
) -> dict[str, Any]:
    total = len(results)
    case_types: dict[str, int] = {}
    for row in results:
        case_types[row["case_type"]] = case_types.get(row["case_type"], 0) + 1
    session_hits = sum(1 for row in results if row.get(f"session_hit_top{top_k}"))
    line_cases = [row for row in results if row.get("has_line_evidence")]
    line_hits = sum(1 for row in line_cases if row.get(f"evidence_hit_top{top_k}"))
    context_hits = sum(
        1 for row in line_cases if row.get(f"evidence_context_hit_top{top_k}")
    )
    context_improved = sum(
        1
        for row in line_cases
        if row.get("evidence_context_rank")
        and (
            not row.get("evidence_rank")
            or int(row["evidence_context_rank"]) < int(row["evidence_rank"])
        )
    )
    context_rescued = sum(
        1
        for row in line_cases
        if row.get(f"evidence_context_hit_top{top_k}")
        and not row.get(f"evidence_hit_top{top_k}")
    )
    evidence_mrr = round(
        sum(reciprocal_rank(row.get("evidence_rank")) for row in line_cases)
        / len(line_cases),
        4,
    ) if line_cases else 0.0
    evidence_context_mrr = round(
        sum(reciprocal_rank(row.get("evidence_context_rank")) for row in line_cases)
        / len(line_cases),
        4,
    ) if line_cases else 0.0
    reranker_cases = [row for row in line_cases if row.get("line_reranker_attempted")]
    semantic_only_hits = sum(
        1 for row in reranker_cases if row.get(f"semantic_only_evidence_hit_top{top_k}")
    )
    reranker_hits = sum(
        1 for row in reranker_cases if row.get(f"reranked_evidence_hit_top{top_k}")
    )
    reranker_usage: dict[str, Any] = {}
    reranker_error_kinds: dict[str, int] = {}
    for row in reranker_cases:
        add_usage(reranker_usage, row.get("line_reranker_usage") or {})
        for kind in row.get("line_reranker_error_kinds") or []:
            reranker_error_kinds[str(kind)] = reranker_error_kinds.get(str(kind), 0) + 1
    metrics = {
        "question_count": total,
        "case_types": case_types,
        f"session_hit_top{top_k}": session_hits,
        f"session_miss_top{top_k}": total - session_hits,
        f"session_hit_rate_top{top_k}": safe_rate(session_hits, total),
        "session_mrr": round(
            sum(reciprocal_rank(row.get("session_rank")) for row in results) / total,
            4,
        ) if total else 0.0,
        "evidence_line_case_count": len(line_cases),
        f"evidence_hit_top{top_k}": line_hits,
        f"evidence_miss_top{top_k}": len(line_cases) - line_hits,
        f"evidence_hit_rate_top{top_k}": safe_rate(line_hits, len(line_cases)),
        "evidence_context_radius": int(context_radius),
        f"evidence_context_hit_top{top_k}": context_hits,
        f"evidence_context_miss_top{top_k}": len(line_cases) - context_hits,
        f"evidence_context_hit_rate_top{top_k}": safe_rate(
            context_hits,
            len(line_cases),
        ),
        "evidence_context_improved_count": context_improved,
        f"evidence_context_rescued_top{top_k}": context_rescued,
        "evidence_mrr": evidence_mrr,
        "evidence_context_mrr": evidence_context_mrr,
        "evidence_context_mrr_delta": round(evidence_context_mrr - evidence_mrr, 4),
        "warning_count": sum(int(row.get("warning_count") or 0) for row in results),
    }
    metrics["rate_estimates"] = {
        f"session_hit_rate_top{top_k}": binomial_rate_report(
            f"session_hit_rate_top{top_k}",
            numerator=session_hits,
            denominator=total,
        ),
        f"evidence_hit_rate_top{top_k}": binomial_rate_report(
            f"evidence_hit_rate_top{top_k}",
            numerator=line_hits,
            denominator=len(line_cases),
        ),
        f"evidence_context_hit_rate_top{top_k}": binomial_rate_report(
            f"evidence_context_hit_rate_top{top_k}",
            numerator=context_hits,
            denominator=len(line_cases),
        ),
    }
    if reranker_cases:
        semantic_only_mrr = round(
            sum(
                reciprocal_rank(row.get("semantic_only_evidence_rank"))
                for row in reranker_cases
            )
            / len(reranker_cases),
            4,
        )
        reranked_mrr = round(
            sum(reciprocal_rank(row.get("reranked_evidence_rank")) for row in reranker_cases)
            / len(reranker_cases),
            4,
        )
        metrics.update(
            {
                "line_reranker_attempted_count": len(reranker_cases),
                "line_reranker_available_count": sum(
                    1 for row in reranker_cases if row.get("line_reranker_available")
                ),
                "line_reranker_error_count": sum(
                    int(row.get("line_reranker_error_count") or 0)
                    for row in reranker_cases
                ),
                "line_reranker_error_kind_counts": reranker_error_kinds,
                "line_reranker_candidate_evidence_coverage": sum(
                    1
                    for row in reranker_cases
                    if row.get("line_reranker_candidate_contains_evidence")
                ),
                "line_reranker_candidate_evidence_coverage_rate": safe_rate(
                    sum(
                        1
                        for row in reranker_cases
                        if row.get("line_reranker_candidate_contains_evidence")
                    ),
                    len(reranker_cases),
                ),
                "line_reranker_candidate_count_avg": round(
                    sum(int(row.get("line_reranker_candidate_count") or 0) for row in reranker_cases)
                    / len(reranker_cases),
                    2,
                ),
                "line_reranker_usage": compact_usage(reranker_usage),
                f"semantic_only_evidence_hit_top{top_k}": semantic_only_hits,
                f"semantic_only_evidence_miss_top{top_k}": len(reranker_cases)
                - semantic_only_hits,
                f"semantic_only_evidence_hit_rate_top{top_k}": safe_rate(
                    semantic_only_hits,
                    len(reranker_cases),
                ),
                "semantic_only_evidence_mrr": semantic_only_mrr,
                "semantic_only_evidence_mrr_delta": round(semantic_only_mrr - evidence_mrr, 4),
                f"reranked_evidence_hit_top{top_k}": reranker_hits,
                f"reranked_evidence_miss_top{top_k}": len(reranker_cases) - reranker_hits,
                f"reranked_evidence_hit_rate_top{top_k}": safe_rate(
                    reranker_hits,
                    len(reranker_cases),
                ),
                "reranked_evidence_mrr": reranked_mrr,
                "reranked_evidence_mrr_delta": round(reranked_mrr - evidence_mrr, 4),
            }
        )
    return metrics


def standard_retrieval_status(
    metrics: dict[str, Any],
    *,
    min_questions: int,
    top_k: int,
    min_session_hit_rate: float,
) -> str:
    if int(metrics.get("question_count") or 0) < min_questions:
        return "diagnostic_only"
    if float(metrics.get(f"session_hit_rate_top{top_k}") or 0.0) < min_session_hit_rate:
        return "insufficient_session_recall"
    return "sufficient"


def skipped_standard_retrieval_payload(
    *,
    dataset: str,
    corpus_path: Path,
    started: float,
    reason: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "standard_public_retrieval_qa_source_evidence",
        "generated_at": now_utc(),
        "status": reason,
        "ok": True,
        "config": config,
        "corpus": {
            "dataset": dataset,
            "corpus_path_sha1": sha1_text(str(corpus_path))[:16],
            "questions_scanned": 0,
            "eligible_questions": 0,
            "messages_scanned": 0,
        },
        "metrics": {
            "question_count": 0,
            "case_types": {},
        },
        "cases": [],
        "privacy_boundary": {
            "raw_text_emitted": False,
            "snippets_emitted": False,
            "absolute_paths_emitted": False,
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_standard_retrieval_qa",
        },
        "cannot_claim": [
            "standard_retrieval_qa_score",
            "answer_generation_quality",
            "decision_gate_quality",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run_standard_retrieval_qa_benchmark(
    *,
    dataset: str = DEFAULT_STANDARD_DATASET,
    corpus_path: Path | str | None = None,
    max_questions: int = DEFAULT_STANDARD_QA_CASES,
    min_questions: int = DEFAULT_STANDARD_QA_MIN_CASES,
    top_k: int = DEFAULT_STANDARD_QA_TOP_K,
    candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    context_radius: int = DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    min_session_hit_rate: float = DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    include_private_text: bool = False,
    line_reranker_mode: str = DEFAULT_STANDARD_LINE_RERANKER_MODE,
    line_reranker_fn: LineRerankerFn | None = None,
    line_reranker_top_sessions: int = DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    line_reranker_max_candidates: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    line_reranker_timeout: int = DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    line_reranker_max_tokens: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    line_reranker_workers: int = DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
) -> dict[str, Any]:
    started = time.perf_counter()
    if dataset not in STANDARD_DATASET_PATHS:
        raise ValueError(f"unsupported standard dataset: {dataset}")
    resolved_path = Path(corpus_path or STANDARD_DATASET_PATHS[dataset]).resolve()
    resolved_line_reranker_mode = line_reranker_mode.strip().casefold()
    if resolved_line_reranker_mode not in STANDARD_LINE_RERANKER_MODES:
        raise ValueError(f"unsupported line reranker mode: {line_reranker_mode}")
    resolved_reranker_workers = (
        max(1, (int(max_questions) + 1) // 2)
        if int(line_reranker_workers) <= 0 and resolved_line_reranker_mode != "off"
        else max(1, int(line_reranker_workers))
    )
    config = {
        "dataset": dataset,
        "corpus_path_sha1": sha1_text(str(resolved_path))[:16],
        "max_questions": int(max_questions),
        "min_questions": int(min_questions),
        "top_k": int(top_k),
        "candidate_limit": int(candidate_limit),
        "context_radius": int(context_radius),
        "min_session_hit_rate": float(min_session_hit_rate),
        "include_private_text": bool(include_private_text),
        "retrieval_query": "question_text_only",
        "line_reranker_mode": resolved_line_reranker_mode,
        "line_reranker_top_sessions": int(line_reranker_top_sessions),
        "line_reranker_max_candidates": int(line_reranker_max_candidates),
        "line_reranker_timeout": int(line_reranker_timeout),
        "line_reranker_max_tokens": int(line_reranker_max_tokens),
        "line_reranker_workers": int(resolved_reranker_workers),
        "line_reranker_external_model": resolved_line_reranker_mode == "semantic",
    }
    if dataset == "longmemeval-v2":
        return skipped_standard_retrieval_payload(
            dataset=dataset,
            corpus_path=resolved_path,
            started=started,
            reason="skipped_no_source_evidence_refs",
            config=config,
        )
    if not resolved_path.exists():
        return skipped_standard_retrieval_payload(
            dataset=dataset,
            corpus_path=resolved_path,
            started=started,
            reason="skipped_missing_standard_corpus",
            config=config,
        )
    with tempfile.TemporaryDirectory(prefix="aippocampus-standard-track-b-") as tmp:
        if dataset == "locomo":
            cases, corpus = build_locomo_standard_cases(
                Path(tmp),
                corpus_path=resolved_path,
                max_questions=max_questions,
            )
        else:
            cases, corpus = build_longmemeval_v1_standard_cases(
                Path(tmp),
                dataset=dataset,
                corpus_path=resolved_path,
                max_questions=max_questions,
            )
        def evaluate(case: dict[str, Any]) -> dict[str, Any]:
            return evaluate_standard_retrieval_case(
                case,
                top_k=top_k,
                candidate_limit=candidate_limit,
                context_radius=context_radius,
                include_private_text=include_private_text,
                line_reranker_mode=resolved_line_reranker_mode,
                line_reranker_fn=line_reranker_fn,
                line_reranker_top_sessions=line_reranker_top_sessions,
                line_reranker_max_candidates=line_reranker_max_candidates,
                line_reranker_timeout=line_reranker_timeout,
                line_reranker_max_tokens=line_reranker_max_tokens,
            )

        if resolved_line_reranker_mode != "off" and resolved_reranker_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=resolved_reranker_workers
            ) as executor:
                results = list(executor.map(evaluate, cases))
        else:
            results = [evaluate(case) for case in cases]
    metrics = summarize_standard_retrieval_results(
        results,
        top_k=top_k,
        context_radius=context_radius,
    )
    status = standard_retrieval_status(
        metrics,
        min_questions=min_questions,
        top_k=top_k,
        min_session_hit_rate=min_session_hit_rate,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "standard_public_retrieval_qa_source_evidence",
        "generated_at": now_utc(),
        "status": status,
        "ok": status == "sufficient",
        "config": config,
        "corpus": corpus,
        "metrics": metrics,
        "cases": results,
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": False,
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_standard_retrieval_qa",
        },
        "cannot_claim": [
            "answer_generation_quality",
            "decision_gate_quality",
            "cross_dataset_model_comparison_without_matching_protocol",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def has_successful_standard_question_arm(payload: dict[str, Any] | None) -> bool:
    if not payload or not payload.get("ok"):
        return False
    if str(payload.get("status") or "").startswith("skipped_"):
        return False
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    question_count = metrics.get("question_count")
    return (
        not isinstance(question_count, bool)
        and isinstance(question_count, (int, float))
        and question_count > 0
    )
