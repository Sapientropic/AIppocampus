#!/usr/bin/env python3
"""Benchmark SQLite FTS5 recall against source-backed clean-source cases.

This benchmark is intentionally local and source-backed: it builds evaluation
cases from clean-source messages already registered in the machine registry,
then asks whether the per-thread SQLite FTS5 index can return the expected
source line. Model-generated labels and future semantic sidecars can help
create richer benchmark cases, but the pass/fail target here remains the clean
source line, not a synthetic summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import (
    benchmark_text_is_sensitive,
    compact_text,
    is_injected_instruction_text,
    now_utc,
)
from aippocampus_runtime.recall.index_builder import make_sqlite
from aippocampus_runtime.recall.retrieval import (
    fts_query,
    message_select_columns,
    normalize_term,
    search_hybrid_index,
    split_query_terms,
    sqlite_has_table,
    unique_preserve,
)
from aippocampus_runtime.registry.api import load_registry as load_thread_registry
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.source.search import iter_clean_messages

DEFAULT_CASES = 80
DEFAULT_SEED = 20260527
DEFAULT_TOP_K = 10
DEFAULT_CANDIDATE_LIMIT = 120
MIN_QUERY_CHARS = 6
MIN_TEXT_CHARS = 36
CJK_FIXTURE_TOP_K = 5

STOP_TERMS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "before",
    "could",
    "from",
    "have",
    "into",
    "just",
    "like",
    "memory",
    "message",
    "note",
    "notes",
    "project",
    "really",
    "source",
    "that",
    "this",
    "thread",
    "with",
    "would",
}

STRUCTURAL_NOISE_PREFIXES = (
    "System trigger. This message stays backstage",
    "This message stays backstage and is not visible",
)

CJK_QUERY_SIDE_CAR_STOP = {
    "上次",
    "之前",
    "那个",
    "这个",
    "记忆",
    "召回",
    "继续",
    "说过",
    "说的",
    "我们",
    "一下",
    "不要",
}


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def load_registry(path: Path | str | None = None) -> dict[str, Any]:
    if path is None:
        path = registry_paths()[0]
    return load_thread_registry(Path(path).resolve())


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    case_type: str
    thread_key: str
    sqlite_path: Path
    clean_source_path: Path
    query: str
    query_terms: list[str]
    expected_message_id: str
    expected_line_start: int
    expected_line_end: int
    role: str
    phase: str
    snippet: str

    def expected_lines(self) -> tuple[int, int]:
        return self.expected_line_start, self.expected_line_end

    def to_result_stub(self, *, include_private_text: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "thread_key_sha1": sha1_text(self.thread_key)[:16],
            "clean_source_sha1": sha1_text(str(self.clean_source_path))[:16],
            "query_sha1": sha1_text(self.query)[:16],
            "query_terms_count": len(self.query_terms),
            "expected": {
                "message_id": self.expected_message_id,
                "line_start": self.expected_line_start,
                "line_end": self.expected_line_end,
                "role": self.role,
                "phase": self.phase,
            },
        }
        if include_private_text:
            payload.update(
                {
                    "thread_key": self.thread_key,
                    "query": self.query,
                    "snippet": compact_text(self.snippet, 260),
                    "clean_source": str(self.clean_source_path),
                    "sqlite": str(self.sqlite_path),
                }
            )
        return payload


@dataclass(frozen=True)
class PublicCjkFixtureCase:
    case_id: str
    case_type: str
    query: str
    expected_message_id: str | None
    expected_line_start: int | None
    expected_line_end: int | None

    def is_positive(self) -> bool:
        return bool(self.expected_message_id)

    def expected_lines(self) -> tuple[int, int] | None:
        if self.expected_line_start is None or self.expected_line_end is None:
            return None
        return self.expected_line_start, self.expected_line_end


def looks_sensitive(text: str) -> bool:
    return benchmark_text_is_sensitive(text)


def is_benchmark_noise(text: str) -> bool:
    stripped = str(text or "").lstrip()
    return is_injected_instruction_text(stripped) or any(
        prefix in stripped for prefix in STRUCTURAL_NOISE_PREFIXES
    )


def latin_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{3,}", text):
        clean = token.strip("._-").casefold()
        if clean in STOP_TERMS or len(clean) < 4:
            continue
        if any(sep in token for sep in ("://", "\\", "/")):
            continue
        terms.append(token)
    terms.sort(key=lambda item: (-min(len(item), 24), item.casefold()))
    return unique_preserve(terms, limit=5)


def cjk_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    for segment in re.split(r"[\n\r\t，。！？；：,.!?;:()（）\[\]{}<>《》\"'`]+", text):
        segment = re.sub(r"\s+", " ", segment).strip()
        if len(segment) < MIN_QUERY_CHARS:
            continue
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", segment))
        if cjk_count < 4:
            continue
        if looks_sensitive(segment):
            continue
        chunks.append(segment[:28])
    chunks.sort(key=lambda item: (-len(set(item)), len(item)))
    return unique_preserve(chunks, limit=5)


def query_from_text(text: str) -> str | None:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < MIN_TEXT_CHARS or looks_sensitive(text):
        return None
    terms = latin_terms(text)
    chunks = cjk_chunks(text)
    if chunks and (not terms or len(chunks[0]) >= 8):
        return chunks[0]
    if len(terms) >= 2:
        return " ".join(terms[:4])
    if terms and chunks:
        return f"{terms[0]} {chunks[0]}"
    if terms:
        return terms[0]
    if chunks:
        return chunks[0]
    words = [word for word in re.findall(r"\S+", text) if len(word) >= 4]
    if len(words) >= 3:
        return " ".join(words[:5])
    return None


def normalized_recall_query(query: str) -> str | None:
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", query))
    if cjk_count < 4:
        return None
    normalized = re.sub(r"\s+", "", query)
    if normalized == query or len(normalized) < MIN_QUERY_CHARS:
        return None
    return normalized


def message_line_range(message: dict[str, Any]) -> tuple[int, int] | None:
    start = message.get("raw_start_line") or message.get("source_line")
    end = message.get("raw_end_line") or message.get("source_line") or start
    if start is None or end is None:
        return None
    try:
        start_int = int(start)
        end_int = int(end)
    except (TypeError, ValueError):
        return None
    return min(start_int, end_int), max(start_int, end_int)


def case_quality(message: dict[str, Any], query: str) -> float:
    score = min(len(query), 40) / 4.0
    if message.get("role") == "user":
        score += 4.0
    if message.get("is_final") or message.get("phase") == "final_answer":
        score += 3.0
    score += min(len(message.get("scope_labels") or []), 3)
    score += min(len(set(query.casefold().split())), 4)
    return score


def case_from_message(
    *,
    thread_key: str,
    sqlite_path: Path,
    clean_source_path: Path,
    message: dict[str, Any],
    case_type: str = "source_phrase",
    query_override: str | None = None,
) -> EvalCase | None:
    text = str(message.get("text") or "")
    if is_benchmark_noise(text):
        return None
    line_range = message_line_range(message)
    if not line_range:
        return None
    query = query_override or query_from_text(text)
    if not query:
        return None
    query_terms = split_query_terms([query])
    if not query_terms:
        return None
    message_id = str(message.get("message_id") or message.get("id") or "")
    if not message_id:
        return None
    case_id = sha1_text(f"{case_type}\n{thread_key}\n{message_id}\n{query}")[:16]
    return EvalCase(
        case_id=case_id,
        case_type=case_type,
        thread_key=thread_key,
        sqlite_path=sqlite_path,
        clean_source_path=clean_source_path,
        query=query,
        query_terms=query_terms,
        expected_message_id=message_id,
        expected_line_start=line_range[0],
        expected_line_end=line_range[1],
        role=str(message.get("role") or ""),
        phase=str(message.get("phase") or ""),
        snippet=text,
    )


def case_variants_from_message(
    *,
    thread_key: str,
    sqlite_path: Path,
    clean_source_path: Path,
    message: dict[str, Any],
) -> list[EvalCase]:
    exact = case_from_message(
        thread_key=thread_key,
        sqlite_path=sqlite_path,
        clean_source_path=clean_source_path,
        message=message,
    )
    if not exact:
        return []
    variants = [exact]
    normalized = normalized_recall_query(exact.query)
    if normalized:
        variant = case_from_message(
            thread_key=thread_key,
            sqlite_path=sqlite_path,
            clean_source_path=clean_source_path,
            message=message,
            case_type="normalized_source_phrase",
            query_override=normalized,
        )
        if variant:
            variants.append(variant)
    return variants


def public_cjk_fixture_messages() -> list[dict[str, Any]]:
    rows = [
        (
            "cjk-exact",
            10,
            "user",
            "",
            "湖蓝色灯塔提醒我把 AIppocampus 路线写进清单。",
        ),
        (
            "cjk-short-cue",
            20,
            "assistant",
            "final_answer",
            "短词锚点在这条中文消息里指向源头恢复路线。",
        ),
        (
            "cjk-mixed-code",
            30,
            "user",
            "",
            "中文加代码：TypeScript 的 useReducer 卡在状态机分支。",
        ),
        (
            "cjk-deictic",
            40,
            "assistant",
            "final_answer",
            "未干的地图要保留源头气味，后续再接续。",
        ),
        (
            "cjk-paraphrase",
            50,
            "assistant",
            "final_answer",
            "轻量分词边车只作为候选评估，不默认开启。",
        ),
    ]
    return [
        {
            "message_id": message_id,
            "turn_id": f"turn-{line}",
            "line": line,
            "timestamp": None,
            "role": role,
            "kind": "message",
            "phase": phase,
            "turn_index": index,
            "is_final": phase == "final_answer",
            "sha1": sha1_text(text),
            "text": text,
        }
        for index, (message_id, line, role, phase, text) in enumerate(rows, start=1)
    ]


def public_cjk_fixture_cases() -> list[PublicCjkFixtureCase]:
    return [
        PublicCjkFixtureCase(
            case_id="exact-chinese-phrase",
            case_type="exact_phrase",
            query="湖蓝色灯塔",
            expected_message_id="cjk-exact",
            expected_line_start=10,
            expected_line_end=10,
        ),
        PublicCjkFixtureCase(
            case_id="short-two-character-cue",
            case_type="short_cjk_cue",
            query="锚点",
            expected_message_id="cjk-short-cue",
            expected_line_start=20,
            expected_line_end=20,
        ),
        PublicCjkFixtureCase(
            case_id="mixed-chinese-code-cue",
            case_type="mixed_cjk_code",
            query="之前那个 useReducer 状态机",
            expected_message_id="cjk-mixed-code",
            expected_line_start=30,
            expected_line_end=30,
        ),
        PublicCjkFixtureCase(
            case_id="deictic-specific-cue",
            case_type="deictic_specific_cue",
            query="上次那个未干的地图",
            expected_message_id="cjk-deictic",
            expected_line_start=40,
            expected_line_end=40,
        ),
        PublicCjkFixtureCase(
            case_id="mild-paraphrase-cue",
            case_type="mild_paraphrase",
            query="中文 tokenizer 候选 默认 开关",
            expected_message_id="cjk-paraphrase",
            expected_line_start=50,
            expected_line_end=50,
        ),
        PublicCjkFixtureCase(
            case_id="generic-deictic-negative",
            case_type="negative_generic_cue",
            query="之前 那个 记忆",
            expected_message_id=None,
            expected_line_start=None,
            expected_line_end=None,
        ),
    ]


def candidate_cjk_query_sidecar_terms(query: str, limit: int = 24) -> list[str]:
    """Benchmark-only CJK query sidecar candidate.

    This deliberately stays outside the default retrieval path. The fixture uses
    it to measure whether shorter CJK query chunks would help before promoting
    any tokenizer or sidecar behavior to production.
    """

    terms: list[str] = []
    for chunk in re.findall(r"[\u3400-\u9fff]{2,}", query):
        normalized = chunk
        for stop in CJK_QUERY_SIDE_CAR_STOP:
            normalized = normalized.replace(stop, " ")
        for part in re.split(r"[\s的了和与、，。；：！？,.!?/|+]+", normalized):
            part = normalize_term(part)
            if len(part) < 2:
                continue
            terms.append(part)
            for n in (2, 3, 4):
                if len(part) < n:
                    continue
                terms.extend(part[i : i + n] for i in range(0, len(part) - n + 1))
    return unique_preserve(terms, limit=limit)


def _public_cjk_mode_result(
    hits: list[dict[str, Any]],
    case: PublicCjkFixtureCase,
    *,
    top_k: int,
) -> dict[str, Any]:
    expected = case.expected_lines()
    rank = expected_rank(hits, expected) if expected else None
    return {
        "rank": rank,
        "hit_top_k": bool(rank and rank <= top_k),
        "negative_false_positive": bool(not case.is_positive() and hits),
        "top_lines": [int(hit["line"]) for hit in hits[:top_k] if hit.get("line") is not None],
    }


def evaluate_public_cjk_case(
    case: PublicCjkFixtureCase,
    sqlite_path: Path,
    *,
    top_k: int = CJK_FIXTURE_TOP_K,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    query_terms = split_query_terms([case.query])
    sidecar_terms = candidate_cjk_query_sidecar_terms(case.query)
    fts_hits, warnings = search_fts5_only(
        sqlite_path,
        query_terms,
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
    )
    hybrid_no_rag_hits = search_hybrid_index(
        sqlite_path,
        query_terms,
        query_terms,
        [],
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
        snippet_chars=1,
        context_radius=0,
        use_rag_chunks=False,
    )
    production_hits = search_hybrid_index(
        sqlite_path,
        query_terms,
        query_terms,
        [],
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
        snippet_chars=1,
        context_radius=0,
        use_rag_chunks=True,
    )
    candidate_sidecar_hits = search_hybrid_index(
        sqlite_path,
        query_terms,
        unique_preserve(query_terms + sidecar_terms, limit=36),
        [],
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
        snippet_chars=1,
        context_radius=0,
        use_rag_chunks=True,
    )
    return {
        "case_id": case.case_id,
        "case_type": case.case_type,
        "expected_positive": case.is_positive(),
        "query_terms": query_terms,
        "candidate_cjk_sidecar_terms": sidecar_terms,
        "expected": {
            "message_id": case.expected_message_id,
            "line_start": case.expected_line_start,
            "line_end": case.expected_line_end,
        },
        "fts5_trigram": {
            **_public_cjk_mode_result(fts_hits, case, top_k=top_k),
            "warnings": warnings,
        },
        "hybrid_without_rag_chunks": _public_cjk_mode_result(
            hybrid_no_rag_hits,
            case,
            top_k=top_k,
        ),
        "production_hybrid": _public_cjk_mode_result(
            production_hits,
            case,
            top_k=top_k,
        ),
        "candidate_cjk_sidecar": _public_cjk_mode_result(
            candidate_sidecar_hits,
            case,
            top_k=top_k,
        ),
    }


def summarize_public_cjk_fixture(results: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    modes = (
        "fts5_trigram",
        "hybrid_without_rag_chunks",
        "production_hybrid",
        "candidate_cjk_sidecar",
    )
    positives = [case for case in results if case["expected_positive"]]
    negatives = [case for case in results if not case["expected_positive"]]
    metrics: dict[str, Any] = {
        "case_count": len(results),
        "positive_case_count": len(positives),
        "negative_case_count": len(negatives),
        "by_case_type": {},
    }
    for mode in modes:
        hits = sum(1 for case in positives if case[mode]["hit_top_k"])
        false_positives = sum(1 for case in negatives if case[mode]["negative_false_positive"])
        metrics[mode] = {
            f"positive_hit_top{top_k}": hits,
            f"positive_miss_top{top_k}": len(positives) - hits,
            f"positive_hit_rate_top{top_k}": round(hits / len(positives), 4)
            if positives
            else 0.0,
            "negative_false_positive_count": false_positives,
        }
    for case_type in sorted({str(case["case_type"]) for case in results}):
        subset = [case for case in results if case["case_type"] == case_type]
        metrics["by_case_type"][case_type] = {
            "case_count": len(subset),
            "positive_case_count": sum(1 for case in subset if case["expected_positive"]),
            "negative_case_count": sum(1 for case in subset if not case["expected_positive"]),
            f"production_hybrid_hit_top{top_k}": sum(
                1 for case in subset if case["production_hybrid"]["hit_top_k"]
            ),
            "production_hybrid_negative_false_positive_count": sum(
                1
                for case in subset
                if case["production_hybrid"]["negative_false_positive"]
            ),
        }
    return metrics


def run_public_cjk_recall_fixture(
    *,
    top_k: int = CJK_FIXTURE_TOP_K,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sqlite_path = root / "source_index.sqlite"
        make_sqlite(
            sqlite_path,
            public_cjk_fixture_messages(),
            anchors=[],
            turns=[],
            publish_lock=False,
        )
        results = [
            evaluate_public_cjk_case(
                case,
                sqlite_path,
                top_k=top_k,
                candidate_limit=candidate_limit,
            )
            for case in public_cjk_fixture_cases()
        ]

    metrics = summarize_public_cjk_fixture(results, top_k=top_k)
    production = metrics["production_hybrid"]
    ok = (
        production[f"positive_hit_top{top_k}"] == metrics["positive_case_count"]
        and production["negative_false_positive_count"] == 0
    )
    return {
        "schema_version": 1,
        "kind": "aippocampus_public_cjk_local_recall_fixture",
        "generated_at": now_utc(),
        "status": "fixture_passed" if ok else "fixture_diagnostic",
        "ok": ok,
        "config": {
            "top_k": top_k,
            "candidate_limit": candidate_limit,
        },
        "comparison_modes": {
            "fts5_trigram": {
                "default_component": True,
                "description": "SQLite FTS5 trigram over split query terms.",
            },
            "hybrid_without_rag_chunks": {
                "default_component": True,
                "description": "Current lexical FTS plus LIKE fallback without RAG-lite chunks.",
            },
            "production_hybrid": {
                "default_component": True,
                "description": "Current lexical-structural local retrieval with RAG-lite enabled.",
            },
            "candidate_cjk_sidecar": {
                "default_component": False,
                "measured_only": True,
                "description": "Benchmark-only lightweight CJK query chunks; not default behavior.",
            },
        },
        "privacy_boundary": {
            "source_text": "public_synthetic_fixture",
            "raw_private_text_emitted": False,
            "external_vector_db_required": False,
            "embedding_model_required": False,
        },
        "metrics": metrics,
        "cases": results,
        "can_claim": [
            "public_fixture_covers_exact_short_mixed_deictic_paraphrase_and_negative_cjk_cases",
            "production_hybrid_fixture_hit_behavior_is_measured_for_this_case_pack",
            "candidate_cjk_sidecar_is_measured_without_becoming_default",
        ],
        "cannot_claim": [
            "broad_chinese_recall_quality",
            "semantic_chinese_search_from_trigram_alone",
            "no_dense_vector_default_claim",
            "private_history_cjk_quality",
            "heavy_tokenizer_or_embedding_requirement",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def build_eval_cases(
    registry: dict[str, Any],
    *,
    sample_size: int = DEFAULT_CASES,
    seed: int = DEFAULT_SEED,
    max_cases_per_thread: int = 4,
) -> tuple[list[EvalCase], dict[str, Any]]:
    rng = random.Random(seed)
    thread_cases: list[list[EvalCase]] = []
    corpus = {
        "registry_threads": len(registry.get("threads") or []),
        "clean_source_threads": 0,
        "sqlite_threads": 0,
        "eligible_threads": 0,
        "messages_scanned": 0,
        "messages_skipped_sensitive": 0,
        "eligible_messages": 0,
    }
    for entry in registry.get("threads") or []:
        paths = entry.get("paths") or {}
        clean_source_path = Path(paths.get("clean_source_messages_jsonl") or "")
        sqlite_path = Path(paths.get("sqlite") or "")
        if clean_source_path.exists():
            corpus["clean_source_threads"] += 1
        if sqlite_path.exists():
            corpus["sqlite_threads"] += 1
        if not clean_source_path.exists() or not sqlite_path.exists():
            continue
        messages = iter_clean_messages(clean_source_path)
        corpus["messages_scanned"] += len(messages)
        candidates: list[tuple[float, EvalCase]] = []
        for message in messages:
            if looks_sensitive(str(message.get("text") or "")):
                corpus["messages_skipped_sensitive"] += 1
                continue
            variants = case_variants_from_message(
                thread_key=str(entry.get("thread_key") or ""),
                sqlite_path=sqlite_path,
                clean_source_path=clean_source_path,
                message=message,
            )
            if not variants:
                continue
            corpus["eligible_messages"] += 1
            for case in variants:
                candidates.append((case_quality(message, case.query), case))
        if not candidates:
            continue
        corpus["eligible_threads"] += 1
        candidates.sort(key=lambda item: (-item[0], item[1].case_id))
        limited = [case for _, case in candidates[:max_cases_per_thread]]
        rng.shuffle(limited)
        thread_cases.append(limited)

    rng.shuffle(thread_cases)
    selected: list[EvalCase] = []
    for depth in range(max_cases_per_thread):
        for per_thread_cases in thread_cases:
            if depth >= len(per_thread_cases):
                continue
            selected.append(per_thread_cases[depth])
            if len(selected) >= sample_size:
                return selected, corpus
    return selected, corpus


def search_fts5_only(
    index: Path,
    query_terms: list[str],
    *,
    limit: int,
    candidate_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    query = fts_query(query_terms)
    if not query:
        return [], [{"code": "empty_fts_query"}]
    con = sqlite3.connect(index)
    con.row_factory = sqlite3.Row
    try:
        if not sqlite_has_table(con, "messages_fts"):
            return [], [{"code": "missing_messages_fts"}]
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
            (query, max(limit, candidate_limit)),
        ).fetchall()
    except sqlite3.Error as exc:
        return [], [{"code": "fts_query_error", "message": str(exc)}]
    finally:
        con.close()
    hits = [
        {
            "line": int(row["line"]),
            "id": int(row["id"]),
            "role": row["role"],
            "phase": row["phase"] or "",
            "rank_score": float(row["rank"]),
        }
        for row in rows[:limit]
    ]
    return hits, warnings


def expected_rank(hits: list[dict[str, Any]], expected: tuple[int, int]) -> int | None:
    start, end = expected
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


def expected_line_present(index: Path, expected: tuple[int, int]) -> bool:
    con = sqlite3.connect(index)
    try:
        row = con.execute(
            "SELECT 1 FROM messages WHERE line BETWEEN ? AND ? LIMIT 1",
            expected,
        ).fetchone()
        return bool(row)
    except sqlite3.Error:
        return False
    finally:
        con.close()


def evaluate_case(
    case: EvalCase,
    *,
    top_k: int = DEFAULT_TOP_K,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    include_private_text: bool = False,
    compare_production: bool = True,
) -> dict[str, Any]:
    fts_hits, warnings = search_fts5_only(
        case.sqlite_path,
        case.query_terms,
        limit=max(top_k, candidate_limit),
        candidate_limit=candidate_limit,
    )
    line_present = expected_line_present(case.sqlite_path, case.expected_lines())
    fts_rank = expected_rank(fts_hits, case.expected_lines())
    result = case.to_result_stub(include_private_text=include_private_text)
    result["fts5"] = {
        "rank": fts_rank,
        "hit_top_k": bool(fts_rank and fts_rank <= top_k),
        "expected_line_present": line_present,
        "top_lines": [hit["line"] for hit in fts_hits[:top_k]],
        "warnings": warnings,
    }
    if compare_production:
        production_hits = search_hybrid_index(
            case.sqlite_path,
            case.query_terms,
            case.query_terms,
            [],
            limit=max(top_k, candidate_limit),
            candidate_limit=candidate_limit,
            snippet_chars=160 if include_private_text else 1,
            context_radius=0,
            use_rag_chunks=True,
        )
        production_rank = expected_rank(production_hits, case.expected_lines())
        result["production_hybrid"] = {
            "rank": production_rank,
            "hit_top_k": bool(production_rank and production_rank <= top_k),
            "top_lines": [int(hit["line"]) for hit in production_hits[:top_k]],
        }
    return result


def summarize_results(results: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    total = len(results)
    by_type: dict[str, int] = {}
    for result in results:
        by_type[result["case_type"]] = by_type.get(result["case_type"], 0) + 1
    thresholds = sorted({1, 5, top_k})
    fts_metrics: dict[str, Any] = {}
    for threshold in thresholds:
        hits = sum(
            1 for result in results if (result.get("fts5", {}).get("rank") or 10**12) <= threshold
        )
        fts_metrics[f"hit_top{threshold}"] = hits
        fts_metrics[f"miss_top{threshold}"] = total - hits
        fts_metrics[f"hit_rate_top{threshold}"] = round(hits / total, 4) if total else 0.0
    miss_categories = {
        "expected_line_absent_from_sqlite": 0,
        "no_fts_hits": 0,
        "rank_below_top_k": 0,
        "production_recovered": 0,
        "production_missed": 0,
    }
    for result in results:
        rank = result.get("fts5", {}).get("rank")
        if rank and rank <= top_k:
            continue
        if not result.get("fts5", {}).get("expected_line_present", True):
            miss_categories["expected_line_absent_from_sqlite"] += 1
        elif result.get("fts5", {}).get("top_lines"):
            miss_categories["rank_below_top_k"] += 1
        else:
            miss_categories["no_fts_hits"] += 1
        if result.get("production_hybrid", {}).get("hit_top_k"):
            miss_categories["production_recovered"] += 1
        elif "production_hybrid" in result:
            miss_categories["production_missed"] += 1
    fts_metrics["miss_categories_top_k"] = miss_categories
    present_results = [
        result for result in results if result.get("fts5", {}).get("expected_line_present", True)
    ]
    present_hits = sum(
        1 for result in present_results if (result.get("fts5", {}).get("rank") or 10**12) <= top_k
    )
    fts_metrics["expected_line_present_cases"] = len(present_results)
    fts_metrics[f"hit_rate_top{top_k}_when_expected_line_present"] = (
        round(present_hits / len(present_results), 4) if present_results else 0.0
    )
    metrics: dict[str, Any] = {
        "total_cases": total,
        "case_types": by_type,
        "fts5": fts_metrics,
        "by_case_type": {},
    }
    for case_type in sorted(by_type):
        subset = [result for result in results if result["case_type"] == case_type]
        subset_total = len(subset)
        fts_hits = sum(
            1 for result in subset if (result.get("fts5", {}).get("rank") or 10**12) <= top_k
        )
        metrics["by_case_type"][case_type] = {
            "total": subset_total,
            f"fts5_hit_top{top_k}": fts_hits,
            f"fts5_miss_top{top_k}": subset_total - fts_hits,
            f"fts5_hit_rate_top{top_k}": round(fts_hits / subset_total, 4) if subset_total else 0.0,
        }
    if any("production_hybrid" in result for result in results):
        hybrid_metrics: dict[str, Any] = {}
        for threshold in thresholds:
            hits = sum(
                1
                for result in results
                if (result.get("production_hybrid", {}).get("rank") or 10**12) <= threshold
            )
            hybrid_metrics[f"hit_top{threshold}"] = hits
            hybrid_metrics[f"miss_top{threshold}"] = total - hits
            hybrid_metrics[f"hit_rate_top{threshold}"] = round(hits / total, 4) if total else 0.0
        metrics["production_hybrid"] = hybrid_metrics
    return metrics


def run_benchmark(
    *,
    registry_path: Path | None,
    sample_size: int,
    seed: int,
    top_k: int,
    candidate_limit: int,
    min_cases: int,
    include_private_text: bool,
    compare_production: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved_registry_path = (registry_path or registry_paths()[0]).resolve()
    registry = load_registry(resolved_registry_path)
    cases, corpus = build_eval_cases(registry, sample_size=sample_size, seed=seed)
    results = [
        evaluate_case(
            case,
            top_k=top_k,
            candidate_limit=candidate_limit,
            include_private_text=include_private_text,
            compare_production=compare_production,
        )
        for case in cases
    ]
    payload = {
        "schema_version": 1,
        "kind": "aippocampus_fts5_recall_benchmark",
        "generated_at": now_utc(),
        "registry": str(resolved_registry_path),
        "config": {
            "requested_cases": sample_size,
            "min_cases": min_cases,
            "seed": seed,
            "top_k": top_k,
            "candidate_limit": candidate_limit,
            "include_private_text": include_private_text,
            "compare_production": compare_production,
        },
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "snippets_emitted": bool(include_private_text),
            "absolute_paths_emitted": bool(include_private_text),
            "case_selection_filters_active": True,
            "case_selection_filter_policy": (
                "aippocampus_runtime.safety.benchmark_sensitive_text_policy"
            ),
            "case_selection_action": "skip_sensitive_candidates",
            "include_private_text_scope": "local_debug_only",
            "output_shape": "sanitized_fts5_recall_cases",
        },
        "corpus": corpus,
        "metrics": summarize_results(results, top_k=top_k),
        "cases": results,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "ok": len(results) >= min_cases,
    }
    if len(results) < min_cases:
        payload["error"] = f"Only built {len(results)} cases; required at least {min_cases}."
    return payload


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    fts = metrics["fts5"]
    top_k = payload["config"]["top_k"]
    print("AIppocampus FTS5 recall benchmark")
    print(f"- registry_threads: {payload['corpus']['registry_threads']}")
    print(f"- eligible_threads: {payload['corpus']['eligible_threads']}")
    print(f"- messages_scanned: {payload['corpus']['messages_scanned']}")
    print(f"- cases: {metrics['total_cases']}")
    print(
        f"- fts5 top-{top_k}: {fts[f'hit_top{top_k}']} hit / "
        f"{fts[f'miss_top{top_k}']} miss "
        f"({fts[f'hit_rate_top{top_k}']:.2%})"
    )
    hybrid = metrics.get("production_hybrid")
    if hybrid:
        print(
            f"- production hybrid top-{top_k}: {hybrid[f'hit_top{top_k}']} hit / "
            f"{hybrid[f'miss_top{top_k}']} miss "
            f"({hybrid[f'hit_rate_top{top_k}']:.2%})"
        )
    if not payload.get("ok"):
        print(f"error: {payload.get('error')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--public-cjk-fixture",
        action="store_true",
        help="Run the checked-in public CJK local-recall fixture instead of registry sampling.",
    )
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    parser.add_argument("--min-cases", type=int, default=50)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--no-production-compare", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.public_cjk_fixture:
        top_k = args.top_k if args.top_k is not None else CJK_FIXTURE_TOP_K
        payload = run_public_cjk_recall_fixture(
            top_k=top_k,
            candidate_limit=args.candidate_limit,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            metrics = payload["metrics"]
            production = metrics["production_hybrid"]
            print("AIppocampus public CJK local recall fixture")
            print(f"- status: {payload.get('status')}")
            print(
                f"- production hybrid top-{top_k}: "
                f"{production[f'positive_hit_top{top_k}']} / "
                f"{metrics['positive_case_count']} positive hits"
            )
            print(
                "- negative false positives: "
                f"{production['negative_false_positive_count']}"
            )
        return 0 if payload.get("ok") else 1

    top_k = args.top_k if args.top_k is not None else DEFAULT_TOP_K
    payload = run_benchmark(
        registry_path=args.registry,
        sample_size=args.cases,
        seed=args.seed,
        top_k=top_k,
        candidate_limit=args.candidate_limit,
        min_cases=args.min_cases,
        include_private_text=args.include_private_text,
        compare_production=not args.no_production_compare,
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
