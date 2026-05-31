#!/usr/bin/env python3
"""Unify source-evidence retrieval benchmarks for AIppocampus Track B.

This runner deliberately reuses the mature retrieval evaluators instead of
inventing another scoring layer. Its job is report normalization: keep FTS5
source-line recall and selected source-evidence recall visible in one sanitized
shape, while preserving source refs as the authority.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import _paths

_paths.ensure_paths()

import smoke_source_evidence_recall_eval as source_evidence_eval

import benchmark_fts5_recall as fts5_benchmark
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.semantic_scope_labels import (
    SEMANTIC_SCOPE_LABELS_FILENAME,
    clean_messages_by_id,
    load_semantic_scope_labels,
    semantic_scope_label_rows_from_findings,
    write_semantic_scope_label_sidecar,
)
from aippocampuslib import compact_text
from build_index import make_sqlite
from retrieval import split_query_terms
from subconscious_runtime import add_usage, call_chat_json, compact_usage
from subconscious_worker import DEFAULT_BASE_URL, DEFAULT_MODEL, clamp_confidence, parse_model_json

SCHEMA_VERSION = 1
DEFAULT_FTS5_CASES = 100
DEFAULT_FTS5_MIN_CASES = 50
DEFAULT_SOURCE_MAX_CASES = 100
DEFAULT_SOURCE_MIN_CASES = 50
DEFAULT_SOURCE_MIN_HIT_RATE = 0.85
DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "output"
    / "sharegpt_all_multiturn"
).resolve()
DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS = 100
DEFAULT_SHAREGPT_PUBLIC_CASES = 100
DEFAULT_SHAREGPT_PUBLIC_MIN_CASES = 50
DEFAULT_SHAREGPT_PUBLIC_TOP_K = 10
DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE = 0.85
DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE = 0.9
DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS = 40
DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES = 80
DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES = 48
DEFAULT_PUBLIC_SEMANTIC_MAX_CASES = 24
DEFAULT_PUBLIC_SEMANTIC_MIN_CASES = 3
DEFAULT_PUBLIC_SEMANTIC_TOP_K = 5
DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE = 0.75
DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE = 0.45
DEFAULT_PUBLIC_SEMANTIC_TIMEOUT = 60
DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS = 8192
DEFAULT_STANDARD_CORPUS_ROOT = (_paths.REPO_ROOT / "benchmark_corpus").resolve()
DEFAULT_STANDARD_DATASET = "locomo"
DEFAULT_STANDARD_QA_CASES = 100
DEFAULT_STANDARD_QA_MIN_CASES = 20
DEFAULT_STANDARD_QA_TOP_K = 10
DEFAULT_STANDARD_QA_CONTEXT_RADIUS = 5
DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE = 0.5
DEFAULT_STANDARD_LINE_RERANKER_MODE = "off"
DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS = 0
DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES = 96
DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT = 12
DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS = 0
DEFAULT_STANDARD_LINE_RERANKER_WORKERS = 0
STANDARD_LINE_RERANKER_MODES = {"off", "custom", "semantic"}
STANDARD_DATASET_PATHS = {
    "locomo": DEFAULT_STANDARD_CORPUS_ROOT / "locomo" / "locomo10.json",
    "longmemeval-v1-oracle": (
        DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "longmemeval_oracle.json"
    ),
    "longmemeval-v1-small": (
        DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "longmemeval_s_cleaned.json"
    ),
    "longmemeval-v1-medium": (
        DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "longmemeval_m_cleaned.json"
    ),
    "longmemeval-v2": DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "v2_questions.jsonl",
}
LineRerankerFn = Callable[..., dict[str, Any]]
PublicSemanticLabelerFn = Callable[..., dict[str, Any]]
PUBLIC_SOURCE_TERM_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "before",
    "could",
    "from",
    "have",
    "help",
    "into",
    "just",
    "like",
    "please",
    "that",
    "this",
    "what",
    "when",
    "where",
    "with",
    "would",
}
STANDARD_QUERY_TERM_STOPWORDS = PUBLIC_SOURCE_TERM_STOPWORDS | {
    "after",
    "before",
    "being",
    "been",
    "could",
    "current",
    "did",
    "does",
    "done",
    "during",
    "first",
    "going",
    "here",
    "into",
    "know",
    "last",
    "many",
    "much",
    "next",
    "onto",
    "previous",
    "should",
    "than",
    "then",
    "there",
    "they",
    "the",
    "those",
    "too",
    "toward",
    "to",
    "were",
    "while",
    "whose",
    "your",
    "yours",
}
CONTINUATION_RE = re.compile(
    r"(?i)\b(continue|where\s+we\s+left\s+off|pick\s+up|go\s+on)\b|继续|接着|续写|从.*继续"
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def reciprocal_rank(rank: Any) -> float:
    try:
        value = int(rank)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 / value if value > 0 else 0.0


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def rank_metrics(cases: list[dict[str, Any]], key: str, thresholds: list[int]) -> dict[str, Any]:
    total = len(cases)
    metrics: dict[str, Any] = {"total_cases": total}
    for threshold in sorted(set(thresholds)):
        hits = sum(
            1
            for case in cases
            if 0 < int((case.get(key) or {}).get("rank") or 0) <= threshold
        )
        metrics[f"hit_top{threshold}"] = hits
        metrics[f"miss_top{threshold}"] = total - hits
        metrics[f"hit_rate_top{threshold}"] = safe_rate(hits, total)
    metrics["mrr"] = round(
        sum(reciprocal_rank((case.get(key) or {}).get("rank")) for case in cases) / total,
        4,
    ) if total else 0.0
    return metrics


def sanitize_fts5_case(case: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    raw_fts5 = case.get("fts5")
    fts5: dict[str, Any] = raw_fts5 if isinstance(raw_fts5, dict) else {}
    fts5_rank = fts5.get("rank")
    production = (
        case.get("production_hybrid")
        if isinstance(case.get("production_hybrid"), dict)
        else None
    )
    row: dict[str, Any] = {
        "case_id": case.get("case_id"),
        "case_type": case.get("case_type"),
        "thread_key_sha1": case.get("thread_key_sha1"),
        "clean_source_sha1": case.get("clean_source_sha1"),
        "query_sha1": case.get("query_sha1"),
        "query_terms_count": case.get("query_terms_count"),
        "fts5_rank": fts5_rank,
        f"fts5_hit_top{top_k}": bool(fts5_rank and int(fts5_rank) <= top_k),
        "expected_line_present": fts5.get("expected_line_present"),
    }
    if production is not None:
        row["production_hybrid_rank"] = production.get("rank")
        row[f"production_hybrid_hit_top{top_k}"] = bool(
            production.get("rank") and int(production.get("rank")) <= top_k
        )
    return row


def summarize_fts5_payload(payload: dict[str, Any], *, top_k: int) -> dict[str, Any]:
    cases = [case for case in payload.get("cases") or [] if isinstance(case, dict)]
    thresholds = [1, 3, 5, top_k]
    fts5_metrics = rank_metrics(cases, "fts5", thresholds)
    summary = {
        "kind": payload.get("kind"),
        "ok": bool(payload.get("ok")),
        "total_cases": int((payload.get("metrics") or {}).get("total_cases") or len(cases)),
        "top_k": int(top_k),
        "corpus": payload.get("corpus") or {},
        "case_types": (payload.get("metrics") or {}).get("case_types") or {},
        "hit_top_k": fts5_metrics.get(f"hit_top{top_k}", 0),
        "miss_top_k": fts5_metrics.get(f"miss_top{top_k}", 0),
        "hit_rate_top_k": fts5_metrics.get(f"hit_rate_top{top_k}", 0.0),
        f"hit_rate_top{top_k}": fts5_metrics.get(f"hit_rate_top{top_k}", 0.0),
        "mrr": fts5_metrics.get("mrr", 0.0),
        "fts5": fts5_metrics,
        "miss_categories_top_k": (
            ((payload.get("metrics") or {}).get("fts5") or {}).get("miss_categories_top_k")
            or {}
        ),
        "elapsed_ms": payload.get("elapsed_ms"),
    }
    if any("production_hybrid" in case for case in cases):
        summary["production_hybrid"] = rank_metrics(cases, "production_hybrid", thresholds)
    return summary


def summarize_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "selected_source_evidence_recall_eval",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "claim_level": payload.get("claim_level"),
        "case_count": int(payload.get("case_count") or 0),
        "passed_count": int(payload.get("passed_count") or 0),
        "failed_count": int(payload.get("failed_count") or 0),
        "top_k": int(payload.get("top_k") or 0),
        "top_k_hit_rate": float(payload.get("top_k_hit_rate") or 0.0),
        "min_cases": int(payload.get("min_cases") or 0),
        "min_hit_rate": float(payload.get("min_hit_rate") or 0.0),
        "label_coverage": payload.get("label_coverage") or [],
        "warning_count": int(payload.get("warning_count") or 0),
        "ranking": payload.get("ranking"),
        "prompt_kind": payload.get("prompt_kind"),
        "failure_diagnostics": payload.get("failure_diagnostics") or {},
    }


def summarize_sharegpt_public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": payload.get("kind") or "sharegpt_public_source_evidence_retrieval",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "config": payload.get("config") or {},
        "corpus": payload.get("corpus") or {},
        "metrics": payload.get("metrics") or {},
        "skip_reason": payload.get("skip_reason"),
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "cannot_claim": payload.get("cannot_claim") or [],
    }


def summarize_standard_retrieval_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": payload.get("kind") or "standard_public_retrieval_qa_source_evidence",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "config": payload.get("config") or {},
        "corpus": payload.get("corpus") or {},
        "metrics": payload.get("metrics") or {},
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "cannot_claim": payload.get("cannot_claim") or [],
    }


def normalize_source_line(message: dict[str, Any], fallback: int) -> int:
    raw = message.get("source_line") or message.get("clean_ordinal") or fallback
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return max(1, int(fallback))


def sharegpt_message_for_sqlite(message: dict[str, Any], fallback_line: int) -> dict[str, Any]:
    text = str(message.get("text") or "")
    identity = "|".join(
        [
            str(message.get("source_id") or ""),
            str(message.get("message_id") or ""),
            str(normalize_source_line(message, fallback_line)),
            text,
        ]
    )
    return {
        "line": normalize_source_line(message, fallback_line),
        "timestamp": str((message.get("_meta") or {}).get("timestamp") or ""),
        "role": str(message.get("role") or ""),
        "kind": "message",
        "phase": str(message.get("phase") or ""),
        "turn_index": int(message.get("turn_index") or 0),
        "is_final": bool(message.get("is_final")),
        "sha1": sha1_text(identity),
        "text": text,
    }


def normalize_sharegpt_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        [row for row in rows if isinstance(row, dict)],
        key=lambda item: int(item.get("clean_ordinal") or item.get("source_line") or 0),
    )
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in sorted_rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        key = (
            str(row.get("message_id") or ""),
            str(row.get("source_line") or row.get("clean_ordinal") or ""),
            sha1_text(text),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def sharegpt_conversation_is_eligible(rows: list[dict[str, Any]]) -> bool:
    return (
        sum(1 for row in rows if row.get("role") == "user") >= 1
        and sum(1 for row in rows if row.get("role") == "assistant") >= 1
    )


def load_sharegpt_conversations(corpus_dir: Path, max_conversations: int) -> list[list[dict[str, Any]]]:
    messages_path = corpus_dir / "messages.jsonl"
    if not messages_path.exists():
        raise FileNotFoundError(f"ShareGPT clean-source messages not found: {messages_path}")
    target = max(1, int(max_conversations))
    conversations: list[list[dict[str, Any]]] = []
    current_source_id = ""
    current_rows: list[dict[str, Any]] = []

    def flush_current() -> None:
        nonlocal current_source_id, current_rows
        if not current_source_id:
            return
        rows = normalize_sharegpt_rows(current_rows)
        if sharegpt_conversation_is_eligible(rows):
            conversations.append(rows)
        current_source_id = ""
        current_rows = []

    with messages_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(conversations) >= target:
                break
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            source_id = str(message.get("source_id") or "")
            if not source_id:
                continue
            if current_source_id and source_id != current_source_id:
                flush_current()
                if len(conversations) >= target:
                    break
            current_source_id = source_id
            current_rows.append(message)
    if len(conversations) < target:
        flush_current()
    return conversations


def public_source_terms(*texts: str, limit: int = 5) -> list[str]:
    terms: list[str] = []
    joined = " ".join(str(text or "") for text in texts)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", joined):
        clean = token.strip("._-")
        if len(clean) < 3 or clean.casefold() in PUBLIC_SOURCE_TERM_STOPWORDS:
            continue
        if any(sep in token for sep in ("://", "\\", "/")):
            continue
        terms.append(clean)
    for chunk in re.split(r"[\n\r\t，。！？；：,.!?;:()（）\[\]{}<>《》\"'`]+", joined):
        chunk = re.sub(r"\s+", " ", chunk).strip()
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", chunk))
        if cjk_count < 2 or len(chunk) < 2:
            continue
        terms.append(chunk[:24])
    ranked = sorted(
        fts5_benchmark.unique_preserve(terms),
        key=lambda term: (-min(len(term), 24), term.casefold()),
    )
    return ranked[:limit]


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


def sharegpt_public_prompt(terms: list[str]) -> str:
    cue = " ".join(terms)
    return f"找回之前这段公开 ShareGPT 对话里关于 {cue} 的原始回答"


def previous_user(rows: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    for row in reversed(rows[:index]):
        if row.get("role") == "user":
            return row
    return None


def previous_assistant(rows: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    for row in reversed(rows[:index]):
        if row.get("role") == "assistant":
            return row
    return None


def turn_line_range(rows: list[dict[str, Any]], turn_id: str) -> tuple[int, int]:
    lines = [
        normalize_source_line(row, idx + 1)
        for idx, row in enumerate(rows)
        if str(row.get("turn_id") or "") == turn_id
    ]
    if not lines:
        return (0, 0)
    return (min(lines), max(lines))


def add_sharegpt_public_case(
    cases: list[dict[str, Any]],
    *,
    case_type: str,
    source_id: str,
    query: str,
    query_terms: list[str],
    target: dict[str, Any],
    rows: list[dict[str, Any]],
    sqlite_path: Path,
) -> None:
    target_line = normalize_source_line(target, 1)
    turn_start, turn_end = turn_line_range(rows, str(target.get("turn_id") or ""))
    case_id = sha1_text(
        "\n".join(
            [
                case_type,
                source_id,
                str(target.get("message_id") or ""),
                query,
            ]
        )
    )[:16]
    cases.append(
        {
            "case_id": case_id,
            "case_type": case_type,
            "source_id": source_id,
            "source_id_sha1": sha1_text(source_id)[:16],
            "query": query,
            "query_terms": query_terms,
            "query_sha1": sha1_text(query)[:16],
            "sqlite_path": sqlite_path,
            "expected": {
                "message_id_sha1": sha1_text(str(target.get("message_id") or ""))[:16],
                "turn_id_sha1": sha1_text(str(target.get("turn_id") or ""))[:16],
                "line": target_line,
                "turn_start": turn_start,
                "turn_end": turn_end,
                "role": str(target.get("role") or ""),
                "phase": str(target.get("phase") or ""),
            },
        }
    )


def build_sharegpt_public_cases(
    root: Path,
    *,
    conversations: list[list[dict[str, Any]]],
    max_cases: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    corpus = {
        "conversation_count": len(conversations),
        "messages_scanned": 0,
        "eligible_conversations": 0,
    }
    for conv_index, rows in enumerate(conversations):
        if len(cases) >= max_cases:
            break
        source_id = str(rows[0].get("source_id") or f"sharegpt-{conv_index}")
        corpus["messages_scanned"] += len(rows)
        thread_dir = root / "sharegpt-public" / sha1_text(source_id)[:12]
        sqlite_path = thread_dir / "index" / "source_index.sqlite"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        make_sqlite(
            sqlite_path,
            [
                sharegpt_message_for_sqlite(row, idx + 1)
                for idx, row in enumerate(rows)
            ],
            anchors=[],
            turns=[],
        )
        conversation_case_count = 0
        for idx, row in enumerate(rows):
            if len(cases) >= max_cases:
                break
            if row.get("role") != "assistant":
                continue
            prior_user = previous_user(rows, idx)
            if not prior_user:
                continue
            terms = public_source_terms(
                str(prior_user.get("text") or ""),
                str(row.get("text") or ""),
            )
            if not terms:
                continue
            prompt = sharegpt_public_prompt(terms)
            add_sharegpt_public_case(
                cases,
                case_type="sharegpt_answer_source_evidence",
                source_id=source_id,
                query=prompt,
                query_terms=split_query_terms([prompt]),
                target=row,
                rows=rows,
                sqlite_path=sqlite_path,
            )
            conversation_case_count += 1
            if CONTINUATION_RE.search(str(prior_user.get("text") or "")):
                continued_from = previous_assistant(rows, idx - 1)
                if continued_from:
                    continuation_terms = public_source_terms(
                        str(prior_user.get("text") or ""),
                        str(continued_from.get("text") or ""),
                    )
                    continuation_prompt = sharegpt_public_prompt(continuation_terms)
                    add_sharegpt_public_case(
                        cases,
                        case_type="sharegpt_continuation_source_evidence",
                        source_id=source_id,
                        query=continuation_prompt,
                        query_terms=split_query_terms([continuation_prompt]),
                        target=continued_from,
                        rows=rows,
                        sqlite_path=sqlite_path,
                    )
                    conversation_case_count += 1
        if conversation_case_count:
            corpus["eligible_conversations"] += 1
    return cases, corpus


def rank_line(hits: list[dict[str, Any]], expected_line: int) -> int | None:
    for idx, hit in enumerate(hits, start=1):
        raw_line = hit.get("line")
        if raw_line is None:
            continue
        try:
            line = int(raw_line)
        except (TypeError, ValueError):
            continue
        if line == expected_line:
            return idx
    return None


def rank_turn(hits: list[dict[str, Any]], start: int, end: int) -> int | None:
    if start <= 0 or end <= 0:
        return None
    for idx, hit in enumerate(hits, start=1):
        raw_line = hit.get("line")
        if raw_line is None:
            continue
        try:
            line = int(raw_line)
        except (TypeError, ValueError):
            continue
        if start <= line <= end:
            return idx
    return None


def evaluate_sharegpt_public_case(
    case: dict[str, Any],
    *,
    top_k: int,
    candidate_limit: int,
    include_private_text: bool,
) -> dict[str, Any]:
    expected = case.get("expected") or {}
    hits, warnings = fts5_benchmark.search_fts5_only(
        case["sqlite_path"],
        case["query_terms"],
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
    )
    message_rank = rank_line(hits, int(expected.get("line") or 0))
    turn_rank = rank_turn(
        hits,
        int(expected.get("turn_start") or 0),
        int(expected.get("turn_end") or 0),
    )
    row: dict[str, Any] = {
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "source_id_sha1": case["source_id_sha1"],
        "query_sha1": case["query_sha1"],
        "query_terms_count": len(case.get("query_terms") or []),
        "expected": {
            "message_id_sha1": expected.get("message_id_sha1"),
            "turn_id_sha1": expected.get("turn_id_sha1"),
            "role": expected.get("role"),
            "phase": expected.get("phase"),
        },
        "message_rank": message_rank,
        f"message_hit_top{top_k}": bool(message_rank and message_rank <= top_k),
        "turn_rank": turn_rank,
        f"turn_hit_top{top_k}": bool(turn_rank and turn_rank <= top_k),
        "warning_count": len(warnings),
    }
    if include_private_text:
        row.update(
            {
                "source_id": case.get("source_id"),
                "query": case.get("query"),
                "expected_line": expected.get("line"),
                "expected_turn_range": [expected.get("turn_start"), expected.get("turn_end")],
                "top_lines": [hit.get("line") for hit in hits[:top_k]],
            }
        )
    return row


def summarize_sharegpt_public_results(results: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    total = len(results)
    case_types: dict[str, int] = {}
    for row in results:
        case_types[row["case_type"]] = case_types.get(row["case_type"], 0) + 1
    message_hits = sum(1 for row in results if row.get(f"message_hit_top{top_k}"))
    turn_hits = sum(1 for row in results if row.get(f"turn_hit_top{top_k}"))
    return {
        "total_cases": total,
        "case_types": case_types,
        f"message_hit_top{top_k}": message_hits,
        f"message_miss_top{top_k}": total - message_hits,
        f"message_hit_rate_top{top_k}": safe_rate(message_hits, total),
        f"turn_hit_top{top_k}": turn_hits,
        f"turn_miss_top{top_k}": total - turn_hits,
        f"turn_hit_rate_top{top_k}": safe_rate(turn_hits, total),
        "message_mrr": round(
            sum(reciprocal_rank(row.get("message_rank")) for row in results) / total,
            4,
        ) if total else 0.0,
        "turn_mrr": round(
            sum(reciprocal_rank(row.get("turn_rank")) for row in results) / total,
            4,
        ) if total else 0.0,
        "warning_count": sum(int(row.get("warning_count") or 0) for row in results),
    }


def sharegpt_public_status(
    metrics: dict[str, Any],
    *,
    min_cases: int,
    top_k: int,
    min_message_hit_rate: float,
    min_turn_hit_rate: float,
) -> str:
    if int(metrics.get("total_cases") or 0) < int(min_cases):
        return "diagnostic_only"
    if float(metrics.get(f"message_hit_rate_top{top_k}") or 0.0) < min_message_hit_rate:
        return "insufficient_message_recall"
    if float(metrics.get(f"turn_hit_rate_top{top_k}") or 0.0) < min_turn_hit_rate:
        return "insufficient_turn_recall"
    return "sufficient"


def skipped_sharegpt_public_payload(
    *,
    corpus_dir: Path,
    started: float,
    reason: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "sharegpt_public_source_evidence_retrieval",
        "generated_at": now_utc(),
        "status": "skipped_missing_public_corpus",
        "ok": True,
        "config": config,
        "corpus": {
            "corpus_dir_sha1": sha1_text(str(corpus_dir))[:16],
            "conversation_count": 0,
            "messages_scanned": 0,
            "eligible_conversations": 0,
        },
        "metrics": {
            "total_cases": 0,
            "case_types": {},
        },
        "cases": [],
        "skip_reason": reason,
        "privacy_boundary": {
            "raw_text_emitted": False,
            "snippets_emitted": False,
            "absolute_paths_emitted": False,
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_sharegpt_public_source_evidence",
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run_sharegpt_public_source_evidence_benchmark(
    *,
    corpus_dir: Path | str | None = None,
    conversations: int = DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    max_cases: int = DEFAULT_SHAREGPT_PUBLIC_CASES,
    min_cases: int = DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    top_k: int = DEFAULT_SHAREGPT_PUBLIC_TOP_K,
    candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    min_message_hit_rate: float = DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE,
    min_turn_hit_rate: float = DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE,
    include_private_text: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved_corpus_dir = Path(corpus_dir or DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR).resolve()
    config = {
        "corpus": "sharegpt_public_clean_source",
        "corpus_dir_sha1": sha1_text(str(resolved_corpus_dir))[:16],
        "conversations": int(conversations),
        "max_cases": int(max_cases),
        "min_cases": int(min_cases),
        "top_k": int(top_k),
        "candidate_limit": int(candidate_limit),
        "min_message_hit_rate": float(min_message_hit_rate),
        "min_turn_hit_rate": float(min_turn_hit_rate),
        "include_private_text": bool(include_private_text),
    }
    try:
        conversations_payload = load_sharegpt_conversations(
            resolved_corpus_dir,
            max_conversations=conversations,
        )
    except FileNotFoundError as exc:
        return skipped_sharegpt_public_payload(
            corpus_dir=resolved_corpus_dir,
            started=started,
            reason=str(exc),
            config=config,
        )
    with tempfile.TemporaryDirectory(prefix="aippocampus-sharegpt-track-b-") as tmp:
        cases, corpus = build_sharegpt_public_cases(
            Path(tmp),
            conversations=conversations_payload,
            max_cases=max_cases,
        )
        results = [
            evaluate_sharegpt_public_case(
                case,
                top_k=top_k,
                candidate_limit=candidate_limit,
                include_private_text=include_private_text,
            )
            for case in cases
        ]
    metrics = summarize_sharegpt_public_results(results, top_k=top_k)
    status = sharegpt_public_status(
        metrics,
        min_cases=min_cases,
        top_k=top_k,
        min_message_hit_rate=min_message_hit_rate,
        min_turn_hit_rate=min_turn_hit_rate,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "sharegpt_public_source_evidence_retrieval",
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
            "output_shape": "sanitized_sharegpt_public_source_evidence",
        },
        "cannot_claim": [
            "private_real_history_source_evidence_quality",
            "life_wide_semantic_sidecar_quality",
            "external_baseline_comparison",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def public_semantic_source_ref(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "source_line": message.get("source_line"),
        "role": message.get("role"),
        "phase": message.get("phase") or "",
    }


def public_semantic_turn_rows(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_turn: dict[str, list[dict[str, Any]]] = {}
    for message in messages:
        turn_id = str(message.get("turn_id") or "")
        if not turn_id:
            continue
        by_turn.setdefault(turn_id, []).append(message)
    turns: list[dict[str, Any]] = []
    for turn_id, rows in by_turn.items():
        lines = [normalize_source_line(row, idx + 1) for idx, row in enumerate(rows)]
        turn_indices = [int(row.get("turn_index") or 0) for row in rows]
        turns.append(
            {
                "turn_id": turn_id,
                "turn_index": min(turn_indices) if turn_indices else 0,
                "message_ids": [
                    str(row.get("message_id") or row.get("id") or "")
                    for row in rows
                    if row.get("message_id") or row.get("id")
                ],
                "start_line": min(lines) if lines else None,
                "end_line": max(lines) if lines else None,
            }
        )
    turns.sort(key=lambda item: (int(item.get("turn_index") or 0), str(item.get("turn_id") or "")))
    return turns


def public_semantic_subset_messages(
    conversations: list[list[dict[str, Any]]], *, max_messages: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    source_line = 1
    for rows in conversations:
        for row in rows:
            if len(selected) >= max(1, int(max_messages)):
                return selected
            text = str(row.get("text") or "").strip()
            message_id = str(row.get("message_id") or "").strip()
            turn_id = str(row.get("turn_id") or "").strip()
            if not text or not message_id or not turn_id:
                continue
            selected.append(
                {
                    **row,
                    "source_line": source_line,
                    "clean_ordinal": source_line - 1,
                    "text": text,
                }
            )
            source_line += 1
    return selected


def write_public_semantic_subset_pack(
    *,
    output_dir: Path,
    corpus_dir: Path,
    conversations: list[list[dict[str, Any]]],
    max_messages: int,
) -> dict[str, Any]:
    clean_source_dir = output_dir / "clean-source"
    registry_dir = output_dir / "registry"
    messages_path = clean_source_dir / "messages.jsonl"
    turns_path = clean_source_dir / "turns.jsonl"
    registry_path = registry_dir / "threads.json"
    messages = public_semantic_subset_messages(conversations, max_messages=max_messages)
    turns = public_semantic_turn_rows(messages)
    clean_source_dir.mkdir(parents=True, exist_ok=True)
    registry_dir.mkdir(parents=True, exist_ok=True)
    messages_path.write_text(
        "".join(json.dumps(message, ensure_ascii=False) + "\n" for message in messages),
        encoding="utf-8",
    )
    turns_path.write_text(
        "".join(json.dumps(turn, ensure_ascii=False) + "\n" for turn in turns),
        encoding="utf-8",
    )
    thread_key = f"public-semantic-sidecar:{sha1_text(str(corpus_dir))[:12]}"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": thread_key,
                        "title": "Public semantic sidecar benchmark subset",
                        "workspace_name": "benchmark_corpus",
                        "project_key": "project:public_semantic_sidecar",
                        "project_label": "public_semantic_sidecar",
                        "project_tags": ["benchmark", "public", "semantic-sidecar"],
                        "paths": {
                            "clean_source_messages_jsonl": "clean-source/messages.jsonl",
                            "clean_source_turns_jsonl": "clean-source/turns.jsonl",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "output_dir": output_dir,
        "clean_source_dir": clean_source_dir,
        "messages_path": messages_path,
        "turns_path": turns_path,
        "registry_path": registry_path,
        "messages": messages,
        "turns": turns,
        "thread_key": thread_key,
    }


def public_semantic_candidate_messages(
    messages: list[dict[str, Any]], *, max_candidates: int
) -> list[dict[str, Any]]:
    candidates = []
    for message in messages:
        text = str(message.get("text") or "").strip()
        if not text or not message.get("message_id"):
            continue
        role = str(message.get("role") or "")
        score = min(len(text), 800) / 100.0
        if role == "user":
            score += 3.0
        if "?" in text or "？" in text:
            score += 0.4
        candidates.append((score, message))
    candidates.sort(
        key=lambda item: (
            -item[0],
            normalize_source_line(item[1], 1),
            str(item[1].get("message_id") or ""),
        )
    )
    return [
        {
            "message_id": message.get("message_id") or message.get("id"),
            "turn_id": message.get("turn_id"),
            "source_line": message.get("source_line"),
            "role": message.get("role"),
            "phase": message.get("phase") or "",
            "text": compact_text(str(message.get("text") or ""), 900),
        }
        for _, message in candidates[: max(1, int(max_candidates))]
    ]


def public_semantic_labeler_messages(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    system = """You are labeling public benchmark clean-source messages for AIppocampus.
Return JSON only. Labels are navigation hints, not source truth."""
    user = json.dumps(
        {
            "canonical_scope_labels": list(SCOPE_LABEL_ORDER),
            "task": (
                "For each candidate that genuinely needs a fuzzy semantic scope label, "
                "return one source-backed semantic_scope_labels finding. Omit candidates "
                "that only have keyword matches or ordinary one-off assistant requests."
            ),
            "label_rules": {
                "personal_reflection": "self, feelings, doubts, identity, or meaning",
                "relationship_continuity": "explicit shared history or ongoing relationship arc",
                "reading_notes": "explicit books, papers, essays, articles, or notes",
                "idea_seed": "new direction, metaphor, possibility, or spark to revisit",
                "preference": "stable or situational way something should be done",
                "life_context": "concrete lived circumstance, body, schedule, mood, or day-to-day situation",
                "technical_work": "implementation, tools, architecture, tests, or technical decisions",
                "open_question": "explicit unresolved question, uncertainty, or inquiry to pursue later",
            },
            "required_finding_shape": {
                "finding_kind": "semantic_scope_labels",
                "job": "semantic_scope_labeling",
                "message_id": "candidate message_id",
                "turn_id": "candidate turn_id",
                "scope_labels": ["canonical labels only"],
                "confidence": "0.0-1.0",
                "summary": "short source-grounded summary",
                "source_refs": [
                    {
                        "message_id": "same message_id",
                        "turn_id": "same turn_id",
                        "source_line": "candidate source_line",
                        "role": "candidate role",
                        "phase": "candidate phase",
                    }
                ],
                "label_evidence": [
                    {
                        "label": "canonical label",
                        "reason": "one short reason grounded in this exact message",
                        "confidence": "0.0-1.0",
                    }
                ],
            },
            "candidate_messages": candidates,
        },
        ensure_ascii=False,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def normalize_public_semantic_findings(
    findings: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidate_by_id = {
        str(candidate.get("message_id") or ""): candidate
        for candidate in candidates
        if candidate.get("message_id")
    }
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        message_id = str(finding.get("message_id") or finding.get("id") or "").strip()
        candidate = candidate_by_id.get(message_id)
        if not candidate:
            continue
        item = dict(finding)
        item["message_id"] = message_id
        item["turn_id"] = item.get("turn_id") or candidate.get("turn_id")
        item["job"] = "semantic_scope_labeling"
        item["finding_kind"] = "semantic_scope_labels"
        item["source"] = item.get("source") or "public_semantic_sidecar_labeler"
        exact_refs = [
            ref
            for ref in item.get("source_refs") or []
            if isinstance(ref, dict)
            and str(ref.get("message_id") or "").strip() == message_id
        ]
        if not exact_refs:
            exact_refs = [public_semantic_source_ref(candidate)]
        item["source_refs"] = exact_refs
        normalized.append(item)
    return normalized


def run_public_semantic_labeler(
    candidates: list[dict[str, Any]],
    *,
    api_key_env: str = "DEEPSEEK_API_KEY",
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
) -> dict[str, Any]:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        return {
            "available": False,
            "findings": [],
            "errors": ["missing semantic labeler api key"],
        }
    if not candidates:
        return {"available": False, "findings": [], "errors": ["empty candidate set"]}
    response = call_chat_json(
        public_semantic_labeler_messages(candidates),
        api_key,
        model or os.environ.get("AIPPOCAMPUS_PUBLIC_SEMANTIC_MODEL") or DEFAULT_MODEL,
        base_url or os.environ.get("AIPPOCAMPUS_PUBLIC_SEMANTIC_BASE_URL") or DEFAULT_BASE_URL,
        None if int(max_tokens) <= 0 else int(max_tokens),
        int(timeout),
        0.0,
    )
    parsed = parse_model_json(response)
    raw_findings = parsed.get("findings") if isinstance(parsed, dict) else []
    findings = [item for item in raw_findings or [] if isinstance(item, dict)]
    return {
        "available": True,
        "findings": normalize_public_semantic_findings(findings, candidates),
        "usage": compact_usage(response.get("usage") or {}),
    }


def summarize_public_semantic_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": payload.get("kind") or "public_semantic_sidecar_source_evidence",
        "status": payload.get("status"),
        "ok": bool(payload.get("ok")),
        "config": payload.get("config") or {},
        "corpus": payload.get("corpus") or {},
        "artifacts": payload.get("artifacts") or {},
        "metrics": payload.get("metrics") or {},
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "cannot_claim": payload.get("cannot_claim") or [],
        "skip_reason": payload.get("skip_reason"),
        "elapsed_ms": payload.get("elapsed_ms"),
    }


def public_semantic_status(source_payload: dict[str, Any], *, sidecar_rows: int) -> str:
    if int(sidecar_rows) <= 0:
        return "insufficient_sidecar_rows"
    if str(source_payload.get("status") or "").startswith("insufficient_selected_cases"):
        return "insufficient_selected_cases"
    if not source_payload.get("ok"):
        return str(source_payload.get("status") or "diagnostic_only")
    return "sufficient"


def skipped_public_semantic_sidecar_payload(
    *,
    started: float,
    reason: str,
    status: str,
    config: dict[str, Any],
    corpus_dir: Path,
    include_private_text: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "public_semantic_sidecar_source_evidence",
        "generated_at": now_utc(),
        "status": status,
        "ok": True,
        "config": config,
        "corpus": {
            "corpus_dir_sha1": sha1_text(str(corpus_dir))[:16],
            "conversation_count": 0,
            "subset_message_count": 0,
            "candidate_message_count": 0,
        },
        "artifacts": {
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "absolute_paths_emitted": bool(include_private_text),
        },
        "metrics": {"case_count": 0, "passed_count": 0, "failed_count": 0},
        "cases": [],
        "skip_reason": reason,
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": False,
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_public_semantic_sidecar",
        },
        "cannot_claim": [
            "private_real_history_source_evidence_quality",
            "human_reviewed_semantic_labels",
            "unbounded_public_semantic_sidecar_quality",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run_public_semantic_sidecar_benchmark(
    *,
    corpus_dir: Path | str | None = None,
    output_dir: Path | str | None = None,
    conversations: int = DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    max_messages: int = DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    max_candidates: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    max_cases: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    min_cases: int = DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    top_k: int = DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    min_hit_rate: float = DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    min_confidence: float = DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    include_private_text: bool = False,
    labeler_fn: PublicSemanticLabelerFn | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved_corpus_dir = Path(corpus_dir or DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR).resolve()
    resolved_output_dir = (
        Path(output_dir).resolve()
        if output_dir
        else Path(tempfile.mkdtemp(prefix="aippocampus-public-semantic-sidecar-")).resolve()
    )
    config = {
        "corpus": "sharegpt_public_clean_source",
        "corpus_dir_sha1": sha1_text(str(resolved_corpus_dir))[:16],
        "artifact_dir_sha1": sha1_text(str(resolved_output_dir))[:16],
        "conversations": int(conversations),
        "max_messages": int(max_messages),
        "max_candidates": int(max_candidates),
        "max_cases": int(max_cases),
        "min_cases": int(min_cases),
        "top_k": int(top_k),
        "min_hit_rate": float(min_hit_rate),
        "min_confidence": float(min_confidence),
        "timeout": int(timeout),
        "max_tokens": int(max_tokens),
        "include_private_text": bool(include_private_text),
    }
    try:
        conversations_payload = load_sharegpt_conversations(
            resolved_corpus_dir,
            max_conversations=conversations,
        )
    except FileNotFoundError as exc:
        return skipped_public_semantic_sidecar_payload(
            started=started,
            reason=str(exc),
            status="skipped_missing_public_corpus",
            config=config,
            corpus_dir=resolved_corpus_dir,
            include_private_text=include_private_text,
        )
    subset = write_public_semantic_subset_pack(
        output_dir=resolved_output_dir,
        corpus_dir=resolved_corpus_dir,
        conversations=conversations_payload,
        max_messages=max_messages,
    )
    candidates = public_semantic_candidate_messages(
        list(subset["messages"]),
        max_candidates=max_candidates,
    )
    try:
        if labeler_fn:
            labeler_payload = labeler_fn(candidates)
        else:
            labeler_payload = run_public_semantic_labeler(
                candidates,
                timeout=timeout,
                max_tokens=max_tokens,
            )
    except Exception as exc:
        return skipped_public_semantic_sidecar_payload(
            started=started,
            reason=f"{type(exc).__name__}: {compact_text(str(exc), 360)}",
            status="skipped_semantic_labeler_error",
            config=config,
            corpus_dir=resolved_corpus_dir,
            include_private_text=include_private_text,
        )
    if not labeler_payload.get("available", True):
        return skipped_public_semantic_sidecar_payload(
            started=started,
            reason="; ".join(str(item) for item in labeler_payload.get("errors") or []),
            status="skipped_missing_semantic_backend",
            config=config,
            corpus_dir=resolved_corpus_dir,
            include_private_text=include_private_text,
        )
    messages_by_id = clean_messages_by_id(subset["clean_source_dir"])
    findings = normalize_public_semantic_findings(
        [item for item in labeler_payload.get("findings") or [] if isinstance(item, dict)],
        candidates,
    )
    sidecar_rows = semantic_scope_label_rows_from_findings(
        findings,
        messages_by_id,
        min_confidence=min_confidence,
    )
    write_semantic_scope_label_sidecar(subset["clean_source_dir"], sidecar_rows)
    reviewed_sidecar = load_semantic_scope_labels(subset["clean_source_dir"])
    source_payload = source_evidence_eval.run_source_evidence_recall_eval(
        registry_path=subset["registry_path"],
        max_cases=max_cases,
        min_cases=min_cases,
        top_k=top_k,
        min_hit_rate=min_hit_rate,
        require_semantic_sidecar=True,
        ranking="dynamic_source",
    )
    status = public_semantic_status(source_payload, sidecar_rows=len(sidecar_rows))
    metrics = {
        "case_count": int(source_payload.get("case_count") or 0),
        "passed_count": int(source_payload.get("passed_count") or 0),
        "failed_count": int(source_payload.get("failed_count") or 0),
        "top_k_hit_rate": float(source_payload.get("top_k_hit_rate") or 0.0),
        "warning_count": int(source_payload.get("warning_count") or 0),
        "label_coverage": source_payload.get("label_coverage") or [],
    }
    artifacts = {
        "sidecar_filename": SEMANTIC_SCOPE_LABELS_FILENAME,
        "sidecar_row_count": len(sidecar_rows),
        "reviewed_sidecar_row_count": len(reviewed_sidecar),
        "artifact_dir_sha1": sha1_text(str(resolved_output_dir))[:16],
        "registry_sha1": sha1_text((subset["registry_path"]).read_text(encoding="utf-8"))[:16],
        "messages_sha1": sha1_text((subset["messages_path"]).read_text(encoding="utf-8"))[:16],
        "sidecar_sha1": sha1_text(
            (subset["clean_source_dir"] / SEMANTIC_SCOPE_LABELS_FILENAME).read_text(
                encoding="utf-8"
            )
        )[:16],
        "absolute_paths_emitted": bool(include_private_text),
    }
    if include_private_text:
        artifacts.update(
            {
                "artifact_dir": str(resolved_output_dir),
                "registry_path": str(subset["registry_path"]),
                "sidecar_path": str(subset["clean_source_dir"] / SEMANTIC_SCOPE_LABELS_FILENAME),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "public_semantic_sidecar_source_evidence",
        "generated_at": now_utc(),
        "status": status,
        "ok": status == "sufficient",
        "config": config,
        "corpus": {
            "corpus_dir_sha1": sha1_text(str(resolved_corpus_dir))[:16],
            "conversation_count": len(conversations_payload),
            "subset_message_count": len(subset["messages"]),
            "subset_turn_count": len(subset["turns"]),
            "candidate_message_count": len(candidates),
            "thread_count": 1,
        },
        "artifacts": artifacts,
        "metrics": metrics,
        "cases": [
            dict(case)
            for case in source_payload.get("cases") or []
            if isinstance(case, dict)
        ],
        "labeler": {
            "available": bool(labeler_payload.get("available", True)),
            "finding_count": len(findings),
            "usage": compact_usage(labeler_payload.get("usage") or {}),
            "error_count": len(labeler_payload.get("errors") or []),
        },
        "source_evidence": summarize_source_payload(source_payload),
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": bool(include_private_text),
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_public_semantic_sidecar",
        },
        "cannot_claim": [
            "private_real_history_source_evidence_quality",
            "human_reviewed_semantic_labels",
            "unbounded_public_semantic_sidecar_quality",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


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


def cannot_claim(
    *,
    fts5_payload: dict[str, Any],
    source_payload: dict[str, Any],
    sharegpt_public_payload: dict[str, Any] | None = None,
    standard_public_payload: dict[str, Any] | None = None,
    public_semantic_sidecar_payload: dict[str, Any] | None = None,
) -> list[str]:
    claims = [
        "real_history_gate_quality",
        "live_semantic_model_quality",
        "end_to_end_payload_fidelity_on_private_real_history",
        "external_baseline_comparison",
    ]
    claims.extend(str(item) for item in source_payload.get("cannot_claim") or [])
    if not fts5_payload.get("ok"):
        claims.append("source_line_retrieval_quality")
    if not source_payload.get("ok"):
        claims.append("selected_source_evidence_recall")
    if sharegpt_public_payload:
        claims.extend(str(item) for item in sharegpt_public_payload.get("cannot_claim") or [])
        if not sharegpt_public_payload.get("ok") and sharegpt_public_payload.get(
            "status"
        ) != "skipped_missing_public_corpus":
            claims.append("sharegpt_public_source_evidence_recall")
    if standard_public_payload:
        claims.extend(str(item) for item in standard_public_payload.get("cannot_claim") or [])
        if not standard_public_payload.get("ok") and not str(
            standard_public_payload.get("status") or ""
        ).startswith("skipped_"):
            claims.append("standard_public_retrieval_qa_source_evidence")
    if public_semantic_sidecar_payload:
        claims.extend(str(item) for item in public_semantic_sidecar_payload.get("cannot_claim") or [])
        if not public_semantic_sidecar_payload.get("ok") and not str(
            public_semantic_sidecar_payload.get("status") or ""
        ).startswith("skipped_"):
            claims.append("public_semantic_sidecar_source_evidence")
    return sorted(set(claims))


def run_source_evidence_retrieval_benchmark(
    *,
    registry_path: Path | None = None,
    fts5_cases: int = DEFAULT_FTS5_CASES,
    fts5_min_cases: int = DEFAULT_FTS5_MIN_CASES,
    fts5_seed: int = fts5_benchmark.DEFAULT_SEED,
    fts5_top_k: int = fts5_benchmark.DEFAULT_TOP_K,
    fts5_candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    source_max_cases: int = DEFAULT_SOURCE_MAX_CASES,
    source_min_cases: int = DEFAULT_SOURCE_MIN_CASES,
    source_top_k: int = 5,
    source_min_hit_rate: float = DEFAULT_SOURCE_MIN_HIT_RATE,
    source_ranking: str = "dynamic_source",
    source_require_semantic_sidecar: bool = True,
    source_max_term_frequency: int = 8,
    include_private_text: bool = False,
    include_sharegpt_public: bool = False,
    sharegpt_public_corpus_dir: Path | str | None = None,
    sharegpt_public_conversations: int = DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    sharegpt_public_max_cases: int = DEFAULT_SHAREGPT_PUBLIC_CASES,
    sharegpt_public_min_cases: int = DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    sharegpt_public_top_k: int = DEFAULT_SHAREGPT_PUBLIC_TOP_K,
    sharegpt_public_candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    sharegpt_public_min_message_hit_rate: float = DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE,
    sharegpt_public_min_turn_hit_rate: float = DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE,
    include_standard_public: bool = False,
    standard_dataset: str = DEFAULT_STANDARD_DATASET,
    standard_corpus_path: Path | str | None = None,
    standard_max_questions: int = DEFAULT_STANDARD_QA_CASES,
    standard_min_questions: int = DEFAULT_STANDARD_QA_MIN_CASES,
    standard_top_k: int = DEFAULT_STANDARD_QA_TOP_K,
    standard_candidate_limit: int = fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    standard_context_radius: int = DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    standard_min_session_hit_rate: float = DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    standard_line_reranker_mode: str = DEFAULT_STANDARD_LINE_RERANKER_MODE,
    standard_line_reranker_top_sessions: int = DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    standard_line_reranker_max_candidates: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    standard_line_reranker_timeout: int = DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    standard_line_reranker_max_tokens: int = DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    standard_line_reranker_workers: int = DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    include_public_semantic_sidecar: bool = False,
    public_semantic_corpus_dir: Path | str | None = None,
    public_semantic_output_dir: Path | str | None = None,
    public_semantic_conversations: int = DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    public_semantic_max_messages: int = DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    public_semantic_max_candidates: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    public_semantic_max_cases: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    public_semantic_min_cases: int = DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    public_semantic_top_k: int = DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    public_semantic_min_hit_rate: float = DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    public_semantic_min_confidence: float = DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    public_semantic_timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    public_semantic_max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
) -> dict[str, Any]:
    started = time.perf_counter()
    fts5_payload = fts5_benchmark.run_benchmark(
        registry_path=registry_path,
        sample_size=fts5_cases,
        seed=fts5_seed,
        top_k=fts5_top_k,
        candidate_limit=fts5_candidate_limit,
        min_cases=fts5_min_cases,
        include_private_text=include_private_text,
        compare_production=True,
    )
    source_payload = source_evidence_eval.run_source_evidence_recall_eval(
        registry_path=registry_path,
        max_cases=source_max_cases,
        min_cases=source_min_cases,
        top_k=source_top_k,
        min_hit_rate=source_min_hit_rate,
        require_semantic_sidecar=source_require_semantic_sidecar,
        max_term_frequency=source_max_term_frequency,
        ranking=source_ranking,
    )
    sharegpt_public_payload = None
    if include_sharegpt_public:
        sharegpt_public_payload = run_sharegpt_public_source_evidence_benchmark(
            corpus_dir=sharegpt_public_corpus_dir,
            conversations=sharegpt_public_conversations,
            max_cases=sharegpt_public_max_cases,
            min_cases=sharegpt_public_min_cases,
            top_k=sharegpt_public_top_k,
            candidate_limit=sharegpt_public_candidate_limit,
            min_message_hit_rate=sharegpt_public_min_message_hit_rate,
            min_turn_hit_rate=sharegpt_public_min_turn_hit_rate,
            include_private_text=include_private_text,
        )
    standard_public_payload = None
    if include_standard_public:
        standard_public_payload = run_standard_retrieval_qa_benchmark(
            dataset=standard_dataset,
            corpus_path=standard_corpus_path,
            max_questions=standard_max_questions,
            min_questions=standard_min_questions,
            top_k=standard_top_k,
            candidate_limit=standard_candidate_limit,
            context_radius=standard_context_radius,
            min_session_hit_rate=standard_min_session_hit_rate,
            include_private_text=include_private_text,
            line_reranker_mode=standard_line_reranker_mode,
            line_reranker_top_sessions=standard_line_reranker_top_sessions,
            line_reranker_max_candidates=standard_line_reranker_max_candidates,
            line_reranker_timeout=standard_line_reranker_timeout,
            line_reranker_max_tokens=standard_line_reranker_max_tokens,
            line_reranker_workers=standard_line_reranker_workers,
        )
    public_semantic_sidecar_payload = None
    if include_public_semantic_sidecar:
        public_semantic_sidecar_payload = run_public_semantic_sidecar_benchmark(
            corpus_dir=public_semantic_corpus_dir,
            output_dir=public_semantic_output_dir,
            conversations=public_semantic_conversations,
            max_messages=public_semantic_max_messages,
            max_candidates=public_semantic_max_candidates,
            max_cases=public_semantic_max_cases,
            min_cases=public_semantic_min_cases,
            top_k=public_semantic_top_k,
            min_hit_rate=public_semantic_min_hit_rate,
            min_confidence=public_semantic_min_confidence,
            timeout=public_semantic_timeout,
            max_tokens=public_semantic_max_tokens,
            include_private_text=include_private_text,
        )
    sharegpt_public_ok = (
        True
        if not sharegpt_public_payload
        else bool(sharegpt_public_payload.get("ok"))
        or sharegpt_public_payload.get("status") == "skipped_missing_public_corpus"
    )
    standard_public_ok = (
        True
        if not standard_public_payload
        else bool(standard_public_payload.get("ok"))
        or str(standard_public_payload.get("status") or "").startswith("skipped_")
    )
    public_semantic_ok = (
        True
        if not public_semantic_sidecar_payload
        else bool(public_semantic_sidecar_payload.get("ok"))
        or str(public_semantic_sidecar_payload.get("status") or "").startswith("skipped_")
    )
    ok = (
        bool(fts5_payload.get("ok"))
        and bool(source_payload.get("ok"))
        and sharegpt_public_ok
        and standard_public_ok
        and public_semantic_ok
    )
    status = "sufficient" if ok else "diagnostic_only"
    fts5_cases_payload = [
        sanitize_fts5_case(case, top_k=fts5_top_k)
        for case in fts5_payload.get("cases") or []
        if isinstance(case, dict)
    ]
    source_cases = [
        dict(case) for case in source_payload.get("cases") or [] if isinstance(case, dict)
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_source_evidence_retrieval_benchmark",
        "generated_at": now_utc(),
        "status": status,
        "ok": ok,
        "config": {
            "fts5_cases": int(fts5_cases),
            "fts5_min_cases": int(fts5_min_cases),
            "fts5_seed": int(fts5_seed),
            "fts5_top_k": int(fts5_top_k),
            "fts5_candidate_limit": int(fts5_candidate_limit),
            "source_max_cases": int(source_max_cases),
            "source_min_cases": int(source_min_cases),
            "source_top_k": int(source_top_k),
            "source_min_hit_rate": float(source_min_hit_rate),
            "source_ranking": source_ranking,
            "source_require_semantic_sidecar": bool(source_require_semantic_sidecar),
            "source_max_term_frequency": int(source_max_term_frequency),
            "include_private_text": bool(include_private_text),
            "include_sharegpt_public": bool(include_sharegpt_public),
            "sharegpt_public_conversations": int(sharegpt_public_conversations),
            "sharegpt_public_max_cases": int(sharegpt_public_max_cases),
            "sharegpt_public_min_cases": int(sharegpt_public_min_cases),
            "sharegpt_public_top_k": int(sharegpt_public_top_k),
            "include_standard_public": bool(include_standard_public),
            "standard_dataset": standard_dataset,
            "standard_max_questions": int(standard_max_questions),
            "standard_min_questions": int(standard_min_questions),
            "standard_top_k": int(standard_top_k),
            "standard_context_radius": int(standard_context_radius),
            "standard_line_reranker_mode": standard_line_reranker_mode,
            "standard_line_reranker_top_sessions": int(standard_line_reranker_top_sessions),
            "standard_line_reranker_max_candidates": int(standard_line_reranker_max_candidates),
            "standard_line_reranker_timeout": int(standard_line_reranker_timeout),
            "standard_line_reranker_max_tokens": int(standard_line_reranker_max_tokens),
            "standard_line_reranker_workers": int(standard_line_reranker_workers),
            "include_public_semantic_sidecar": bool(include_public_semantic_sidecar),
            "public_semantic_conversations": int(public_semantic_conversations),
            "public_semantic_max_messages": int(public_semantic_max_messages),
            "public_semantic_max_candidates": int(public_semantic_max_candidates),
            "public_semantic_max_cases": int(public_semantic_max_cases),
            "public_semantic_min_cases": int(public_semantic_min_cases),
            "public_semantic_top_k": int(public_semantic_top_k),
            "public_semantic_min_hit_rate": float(public_semantic_min_hit_rate),
            "public_semantic_min_confidence": float(public_semantic_min_confidence),
            "public_semantic_timeout": int(public_semantic_timeout),
            "public_semantic_max_tokens": int(public_semantic_max_tokens),
        },
        "tracks": {
            "fts5_source_line": summarize_fts5_payload(fts5_payload, top_k=fts5_top_k),
            "source_evidence": summarize_source_payload(source_payload),
        },
        "cases": {
            "fts5": fts5_cases_payload,
            "source_evidence": source_cases,
        },
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": bool(include_private_text),
            "titles_emitted": False,
            "source_reference_details_emitted": bool(include_private_text),
            "absolute_paths_emitted": bool(include_private_text),
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_track_b_retrieval_aggregates",
        },
        "cannot_claim": cannot_claim(
            fts5_payload=fts5_payload,
            source_payload=source_payload,
            sharegpt_public_payload=sharegpt_public_payload,
            standard_public_payload=standard_public_payload,
            public_semantic_sidecar_payload=public_semantic_sidecar_payload,
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if sharegpt_public_payload:
        payload["tracks"]["sharegpt_public_source_evidence"] = (
            summarize_sharegpt_public_payload(sharegpt_public_payload)
        )
        payload["cases"]["sharegpt_public"] = [
            dict(case)
            for case in sharegpt_public_payload.get("cases") or []
            if isinstance(case, dict)
        ]
    if standard_public_payload:
        payload["tracks"]["standard_public_retrieval_qa"] = (
            summarize_standard_retrieval_payload(standard_public_payload)
        )
        payload["cases"]["standard_public_retrieval_qa"] = [
            dict(case)
            for case in standard_public_payload.get("cases") or []
            if isinstance(case, dict)
        ]
    if public_semantic_sidecar_payload:
        payload["tracks"]["public_semantic_sidecar"] = (
            summarize_public_semantic_source_payload(public_semantic_sidecar_payload)
        )
        payload["cases"]["public_semantic_sidecar"] = [
            dict(case)
            for case in public_semantic_sidecar_payload.get("cases") or []
            if isinstance(case, dict)
        ]
    if include_private_text:
        payload["private_debug_payloads"] = {
            "fts5": fts5_payload,
            "source_evidence": source_payload,
        }
        if sharegpt_public_payload:
            payload["private_debug_payloads"]["sharegpt_public"] = sharegpt_public_payload
        if standard_public_payload:
            payload["private_debug_payloads"]["standard_public_retrieval_qa"] = (
                standard_public_payload
            )
        if public_semantic_sidecar_payload:
            payload["private_debug_payloads"]["public_semantic_sidecar"] = (
                public_semantic_sidecar_payload
            )
    return payload


def print_human_summary(payload: dict[str, Any]) -> None:
    fts5 = payload["tracks"]["fts5_source_line"]
    source = payload["tracks"]["source_evidence"]
    fts5_top_k = int(payload["config"]["fts5_top_k"])
    source_top_k = int(payload["config"]["source_top_k"])
    print("AIppocampus source-evidence retrieval benchmark")
    print(f"- status: {payload['status']}")
    print(f"- fts5 cases: {fts5['total_cases']}")
    print(
        f"- fts5 top-{fts5_top_k}: "
        f"{fts5['fts5'].get(f'hit_top{fts5_top_k}', 0)} hit / "
        f"{fts5['fts5'].get(f'miss_top{fts5_top_k}', 0)} miss "
        f"({fts5['fts5'].get(f'hit_rate_top{fts5_top_k}', 0.0):.2%})"
    )
    hybrid = fts5.get("production_hybrid")
    if hybrid:
        print(
            f"- production hybrid top-{fts5_top_k}: "
            f"{hybrid.get(f'hit_top{fts5_top_k}', 0)} hit / "
            f"{hybrid.get(f'miss_top{fts5_top_k}', 0)} miss "
            f"({hybrid.get(f'hit_rate_top{fts5_top_k}', 0.0):.2%})"
        )
    print(
        f"- selected source evidence top-{source_top_k}: "
        f"{source['passed_count']} hit / {source['failed_count']} miss "
        f"({source['top_k_hit_rate']:.2%})"
    )
    sharegpt_public = payload["tracks"].get("sharegpt_public_source_evidence")
    if sharegpt_public:
        metrics = sharegpt_public.get("metrics") or {}
        top_k = int((sharegpt_public.get("config") or {}).get("top_k") or 0)
        print(
            f"- ShareGPT public source evidence top-{top_k}: "
            f"message {metrics.get(f'message_hit_rate_top{top_k}', 0.0):.2%}, "
            f"turn {metrics.get(f'turn_hit_rate_top{top_k}', 0.0):.2%}"
        )
    standard_public = payload["tracks"].get("standard_public_retrieval_qa")
    if standard_public:
        metrics = standard_public.get("metrics") or {}
        config = standard_public.get("config") or {}
        top_k = int(config.get("top_k") or 0)
        dataset = config.get("dataset") or "standard"
        print(
            f"- {dataset} retrieval-QA top-{top_k}: "
            f"session {metrics.get(f'session_hit_rate_top{top_k}', 0.0):.2%}, "
            f"evidence exact {metrics.get(f'evidence_hit_rate_top{top_k}', 0.0):.2%}, "
            f"context-visible {metrics.get(f'evidence_context_hit_rate_top{top_k}', 0.0):.2%}"
        )
        if int(metrics.get("line_reranker_attempted_count") or 0):
            print(
                f"  line reranker exact MRR "
                f"{metrics.get('reranked_evidence_mrr', 0.0):.4f}, "
                f"top-{top_k} {metrics.get(f'reranked_evidence_hit_rate_top{top_k}', 0.0):.2%}"
            )
    public_semantic = payload["tracks"].get("public_semantic_sidecar")
    if public_semantic:
        metrics = public_semantic.get("metrics") or {}
        artifacts = public_semantic.get("artifacts") or {}
        config = public_semantic.get("config") or {}
        print(
            f"- public semantic sidecar top-{int(config.get('top_k') or 0)}: "
            f"{metrics.get('passed_count', 0)} hit / {metrics.get('failed_count', 0)} miss "
            f"({metrics.get('top_k_hit_rate', 0.0):.2%}); "
            f"sidecar rows {artifacts.get('reviewed_sidecar_row_count', 0)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--fts5-cases", type=int, default=DEFAULT_FTS5_CASES)
    parser.add_argument("--fts5-min-cases", type=int, default=DEFAULT_FTS5_MIN_CASES)
    parser.add_argument("--fts5-seed", type=int, default=fts5_benchmark.DEFAULT_SEED)
    parser.add_argument("--fts5-top-k", type=int, default=fts5_benchmark.DEFAULT_TOP_K)
    parser.add_argument(
        "--fts5-candidate-limit",
        type=int,
        default=fts5_benchmark.DEFAULT_CANDIDATE_LIMIT,
    )
    parser.add_argument("--source-max-cases", type=int, default=DEFAULT_SOURCE_MAX_CASES)
    parser.add_argument("--source-min-cases", type=int, default=DEFAULT_SOURCE_MIN_CASES)
    parser.add_argument("--source-top-k", type=int, default=5)
    parser.add_argument("--source-min-hit-rate", type=float, default=DEFAULT_SOURCE_MIN_HIT_RATE)
    parser.add_argument(
        "--source-ranking",
        choices=["dynamic_source", "registry"],
        default="dynamic_source",
    )
    parser.add_argument("--source-max-term-frequency", type=int, default=8)
    parser.add_argument("--allow-deterministic-labels", action="store_true")
    parser.add_argument("--include-sharegpt-public", action="store_true")
    parser.add_argument("--sharegpt-public-corpus-dir", type=Path, default=None)
    parser.add_argument(
        "--sharegpt-public-conversations",
        type=int,
        default=DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    )
    parser.add_argument("--sharegpt-public-cases", type=int, default=DEFAULT_SHAREGPT_PUBLIC_CASES)
    parser.add_argument(
        "--sharegpt-public-min-cases",
        type=int,
        default=DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    )
    parser.add_argument("--sharegpt-public-top-k", type=int, default=DEFAULT_SHAREGPT_PUBLIC_TOP_K)
    parser.add_argument("--include-standard-public", action="store_true")
    parser.add_argument(
        "--standard-dataset",
        choices=sorted(STANDARD_DATASET_PATHS),
        default=DEFAULT_STANDARD_DATASET,
    )
    parser.add_argument("--standard-corpus-path", type=Path, default=None)
    parser.add_argument("--standard-questions", type=int, default=DEFAULT_STANDARD_QA_CASES)
    parser.add_argument(
        "--standard-min-questions",
        type=int,
        default=DEFAULT_STANDARD_QA_MIN_CASES,
    )
    parser.add_argument("--standard-top-k", type=int, default=DEFAULT_STANDARD_QA_TOP_K)
    parser.add_argument(
        "--standard-context-radius",
        type=int,
        default=DEFAULT_STANDARD_QA_CONTEXT_RADIUS,
    )
    parser.add_argument(
        "--standard-min-session-hit-rate",
        type=float,
        default=DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE,
    )
    parser.add_argument(
        "--standard-line-reranker",
        choices=sorted(STANDARD_LINE_RERANKER_MODES - {"custom"}),
        default=DEFAULT_STANDARD_LINE_RERANKER_MODE,
    )
    parser.add_argument(
        "--standard-line-reranker-top-sessions",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS,
    )
    parser.add_argument(
        "--standard-line-reranker-max-candidates",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES,
    )
    parser.add_argument(
        "--standard-line-reranker-timeout",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    )
    parser.add_argument(
        "--standard-line-reranker-max-tokens",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS,
    )
    parser.add_argument(
        "--standard-line-reranker-workers",
        type=int,
        default=DEFAULT_STANDARD_LINE_RERANKER_WORKERS,
    )
    parser.add_argument("--include-public-semantic-sidecar", action="store_true")
    parser.add_argument("--public-semantic-corpus-dir", type=Path, default=None)
    parser.add_argument("--public-semantic-output-dir", type=Path, default=None)
    parser.add_argument(
        "--public-semantic-conversations",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS,
    )
    parser.add_argument(
        "--public-semantic-max-messages",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES,
    )
    parser.add_argument(
        "--public-semantic-max-candidates",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    )
    parser.add_argument(
        "--public-semantic-cases",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_CASES,
    )
    parser.add_argument(
        "--public-semantic-min-cases",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MIN_CASES,
    )
    parser.add_argument(
        "--public-semantic-top-k",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_TOP_K,
    )
    parser.add_argument(
        "--public-semantic-min-hit-rate",
        type=float,
        default=DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE,
    )
    parser.add_argument(
        "--public-semantic-min-confidence",
        type=float,
        default=DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    )
    parser.add_argument(
        "--public-semantic-timeout",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    )
    parser.add_argument(
        "--public-semantic-max-tokens",
        type=int,
        default=DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    )
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    payload = run_source_evidence_retrieval_benchmark(
        registry_path=args.registry,
        fts5_cases=args.fts5_cases,
        fts5_min_cases=args.fts5_min_cases,
        fts5_seed=args.fts5_seed,
        fts5_top_k=args.fts5_top_k,
        fts5_candidate_limit=args.fts5_candidate_limit,
        source_max_cases=args.source_max_cases,
        source_min_cases=args.source_min_cases,
        source_top_k=args.source_top_k,
        source_min_hit_rate=args.source_min_hit_rate,
        source_ranking=args.source_ranking,
        source_require_semantic_sidecar=not args.allow_deterministic_labels,
        source_max_term_frequency=args.source_max_term_frequency,
        include_private_text=args.include_private_text,
        include_sharegpt_public=args.include_sharegpt_public,
        sharegpt_public_corpus_dir=args.sharegpt_public_corpus_dir,
        sharegpt_public_conversations=args.sharegpt_public_conversations,
        sharegpt_public_max_cases=args.sharegpt_public_cases,
        sharegpt_public_min_cases=args.sharegpt_public_min_cases,
        sharegpt_public_top_k=args.sharegpt_public_top_k,
        include_standard_public=args.include_standard_public,
        standard_dataset=args.standard_dataset,
        standard_corpus_path=args.standard_corpus_path,
        standard_max_questions=args.standard_questions,
        standard_min_questions=args.standard_min_questions,
        standard_top_k=args.standard_top_k,
        standard_context_radius=args.standard_context_radius,
        standard_min_session_hit_rate=args.standard_min_session_hit_rate,
        standard_line_reranker_mode=args.standard_line_reranker,
        standard_line_reranker_top_sessions=args.standard_line_reranker_top_sessions,
        standard_line_reranker_max_candidates=args.standard_line_reranker_max_candidates,
        standard_line_reranker_timeout=args.standard_line_reranker_timeout,
        standard_line_reranker_max_tokens=args.standard_line_reranker_max_tokens,
        standard_line_reranker_workers=args.standard_line_reranker_workers,
        include_public_semantic_sidecar=args.include_public_semantic_sidecar,
        public_semantic_corpus_dir=args.public_semantic_corpus_dir,
        public_semantic_output_dir=args.public_semantic_output_dir,
        public_semantic_conversations=args.public_semantic_conversations,
        public_semantic_max_messages=args.public_semantic_max_messages,
        public_semantic_max_candidates=args.public_semantic_max_candidates,
        public_semantic_max_cases=args.public_semantic_cases,
        public_semantic_min_cases=args.public_semantic_min_cases,
        public_semantic_top_k=args.public_semantic_top_k,
        public_semantic_min_hit_rate=args.public_semantic_min_hit_rate,
        public_semantic_min_confidence=args.public_semantic_min_confidence,
        public_semantic_timeout=args.public_semantic_timeout,
        public_semantic_max_tokens=args.public_semantic_max_tokens,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
