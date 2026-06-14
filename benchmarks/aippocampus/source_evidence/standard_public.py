"""Standard public retrieval-QA Track B adapters for LoCoMo and LongMemEval."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import benchmark_fts5_recall as fts5_benchmark
from aippocampus_runtime.core import compact_text, deepseek_cache_metrics_from_usage
from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    NO_PROVIDER_CACHE_CONTRACT,
)
from aippocampus_runtime.recall.index_builder import make_sqlite
from aippocampus_runtime.recall.retrieval import split_query_terms
from aippocampus_runtime.source.semantic_scope_labels import (
    SEMANTIC_SCOPE_LABELS_FILENAME,
    load_semantic_scope_labels,
    semantic_labels_for_message,
)
from aippocampus_runtime.subconscious.candidate_router import match_working_memory
from aippocampus_runtime.subconscious.runtime import add_usage, call_chat_json, compact_usage
from aippocampus_runtime.subconscious.worker import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    clamp_confidence,
    parse_model_json,
)
from benchmarks.aippocampus.shared.benchmark_statistics import binomial_rate_report

from .capability_provenance import benchmark_capability_provenance
from .defaults import (
    DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    DEFAULT_STANDARD_CASE_CACHE_ROOT,
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
    DEFAULT_STANDARD_SOURCE_SEMANTIC_CACHE_PREWARM_WORKERS,
    SCHEMA_VERSION,
    STANDARD_DATASET_PATHS,
    STANDARD_LINE_RERANKER_MODES,
    STANDARD_QUERY_TERM_STOPWORDS,
    LineRerankerFn,
    PublicSemanticLabelerFn,
)
from .reporting import (
    now_utc,
    reciprocal_rank,
    safe_rate,
    sha1_text,
)
from .semantic_sidecars import (
    SEMANTIC_SCOPE_SIDECAR_MANIFEST_FILENAME,
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZERS,
    materialize_source_semantic_sidecars,
    source_semantic_sidecar_materializer_contract,
)

EVIDENCE_DIAGNOSTIC_CUTOFFS = (1, 3, 5, 10, 20, 50)
SEMANTIC_LINE_RERANKER_ARM = "llm_window_to_line_rerank"
SEMANTIC_LINE_RERANKER_PROMPT_VERSION = "llm-window-to-line-rerank-v1"
SOURCE_SEMANTIC_CACHE_ARM = "aippocampus_source_worker_surface_cache"
SOURCE_SEMANTIC_CACHE_POLICY_VERSION = "aippocampus-source-worker-surface-cache-v6"
SOURCE_SEMANTIC_CACHE_BUILDER_ID = "aippocampus-working-memory-factual-surface-v3"
STANDARD_CASE_CACHE_POLICY_VERSION = "standard-public-case-index-cache-v1"
STANDARD_CASE_ADAPTER_VERSION = "standard-public-case-adapter-v1"
STANDARD_CLEAN_SOURCE_MESSAGES_FILENAME = "messages.jsonl"
LEXICAL_RERANKER_DIRECT_TERMS = {
    "adopt",
    "adopted",
    "bought",
    "buy",
    "called",
    "code",
    "current",
    "drawer",
    "email",
    "favorite",
    "favourite",
    "find",
    "found",
    "located",
    "look",
    "name",
    "number",
    "phone",
    "prefer",
    "prefers",
    "truth",
    "use",
    "uses",
}
LEXICAL_RERANKER_BRIDGE_TERMS = {
    "about",
    "context",
    "discussed",
    "mentioned",
    "notes",
    "question",
    "recall",
    "remember",
    "topic",
}
STRUCTURAL_RERANKER_VALUE_RE = re.compile(
    r"\b\d[\w:./-]*\b|\b[A-Z][A-Za-z0-9_-]{2,}\b|[\"'`][^\"'`]{3,}[\"'`]"
)
STRUCTURAL_RERANKER_ANSWER_CUE_RE = re.compile(
    r"(?i)\b(is|are|was|were|means|called|named|located|found|look|use|uses|"
    r"prefer|prefers|bought|adopted|current|truth|number|code|email|phone|"
    r"drawer|address|date|time|place|location)\b"
)
STRUCTURAL_RERANKER_QUESTION_CUE_RE = re.compile(
    r"(?i)\b(what|where|when|which|who|whose|how|did|does|do|can|could|should|"
    r"question|remind|remember)\b|\?"
)
STRUCTURAL_RERANKER_CONTINUATION_RE = re.compile(
    r"(?i)\b(next line|following line|continues?|continuing|below|above|as follows|"
    r"rest of|pick up|where we left off)\b"
)
SOURCE_SEMANTIC_PREFERENCE_RE = re.compile(
    r"(?i)\b(prefer|prefers|favorite|favourite|like|likes|dislike|avoid|use|uses|"
    r"usually|always|never|rather)\b"
)
SOURCE_SEMANTIC_CURRENTNESS_RE = re.compile(
    r"(?i)\b(current|currently|now|latest|new|old|updated?|changed?|switched|"
    r"before|after|previous|later|today|yesterday|tomorrow)\b"
)
SOURCE_SEMANTIC_TASK_RE = re.compile(
    r"(?i)\b(issue|bug|fix|test|code|repo|branch|pr|pull request|benchmark|"
    r"report|docs?|design|runner|cache|timeout)\b"
)
FACTUAL_ALIAS_RELATION_GROUPS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (
        re.compile(r"(?i)\b(called|named|means|known as|codename|nickname)\b"),
        ("name", "called", "named", "identity", "alias"),
    ),
    (
        re.compile(
            r"(?i)\b(stored|kept|located|found|drawer|shelf|room|address|"
            r"place|location|sits|lives)\b"
        ),
        ("kept", "stored", "located", "location", "place", "lives"),
    ),
    (
        re.compile(r"(?i)\b(prefer|prefers|favorite|favourite|uses?|adopted?)\b"),
        ("preferred", "preference", "favorite", "choice", "uses"),
    ),
    (
        re.compile(r"(?i)\b(number|code|email|phone|contact)\b"),
        ("number", "code", "contact", "email", "phone"),
    ),
    (
        re.compile(r"(?i)\b(date|time|schedule|deadline|appointment|meeting)\b"),
        ("date", "time", "schedule", "deadline"),
    ),
    (
        re.compile(r"(?i)\b(current|currently|latest|status|switched|updated?)\b"),
        ("latest", "status", "currentness", "now"),
    ),
)
FACTUAL_NOUN_ALIAS_TERMS: dict[str, tuple[str, ...]] = {
    "souvenir": ("keepsake", "memento"),
    "keepsake": ("souvenir", "memento"),
    "memento": ("souvenir", "keepsake"),
    "drawer": ("location", "place", "stored", "kept"),
    "shelf": ("location", "place", "stored", "kept"),
    "room": ("location", "place"),
    "address": ("location", "place"),
    "phone": ("contact", "number"),
    "email": ("contact", "address"),
    "nickname": ("name", "alias"),
    "codename": ("name", "alias", "code"),
    "favorite": ("preferred", "choice"),
    "favourite": ("preferred", "choice"),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_sha1(value: Any, *, length: int = 16) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha1_text(encoded)[:length]


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def read_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def standard_case_cache_key(
    *,
    dataset: str,
    corpus_sha256: str,
    max_questions: int,
) -> str:
    # Keep the cache root shared across prefix-sized benchmark runs. A 500-question
    # run should reuse the first 100 prepared clean-source indexes and sidecars
    # instead of treating `max_questions` as part of source identity.
    _ = max_questions
    material = {
        "policy_version": STANDARD_CASE_CACHE_POLICY_VERSION,
        "adapter_version": STANDARD_CASE_ADAPTER_VERSION,
        "dataset": dataset,
        "corpus_sha256": corpus_sha256,
        "question_selection": "first_eligible_questions_in_corpus_order_shared_prefix_cache",
    }
    return stable_json_sha1(material, length=20)


def new_standard_case_cache_metrics(
    *,
    enabled: bool,
    cache_key: str | None,
    rebuild_requested: bool,
) -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "policy_version": STANDARD_CASE_CACHE_POLICY_VERSION,
        "adapter_version": STANDARD_CASE_ADAPTER_VERSION,
        "cache_key": cache_key or "",
        "cache_root_emitted": False,
        "rebuild_requested": bool(rebuild_requested),
        "source_index_hit_count": 0,
        "source_index_miss_count": 0,
        "source_index_rebuild_count": 0,
        "source_index_manifest_mismatch_count": 0,
        "source_index_forced_rebuild_count": 0,
        "source_index_error_rebuild_count": 0,
        "source_index_count": 0,
        "source_index_hit_rate": 0.0,
    }


def finalized_standard_case_cache_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    payload = dict(metrics)
    hit_count = int(payload.get("source_index_hit_count") or 0)
    rebuild_count = int(payload.get("source_index_rebuild_count") or 0)
    total = hit_count + rebuild_count
    payload["source_index_count"] = total
    payload["source_index_hit_rate"] = safe_rate(hit_count, total)
    return payload


def standard_messages_fingerprint(messages: list[dict[str, Any]]) -> str:
    material = [
        {
            "line": int(message.get("line") or 0),
            "timestamp": str(message.get("timestamp") or ""),
            "role": str(message.get("role") or ""),
            "phase": str(message.get("phase") or ""),
            "turn_index": int(message.get("turn_index") or 0),
            "is_final": bool(message.get("is_final")),
            "sha1": str(message.get("sha1") or ""),
        }
        for message in messages
    ]
    return stable_json_sha1(material, length=40)


def source_index_manifest(
    *,
    dataset: str,
    source_id: str,
    question_id: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "standard_public_source_index_manifest",
        "policy_version": STANDARD_CASE_CACHE_POLICY_VERSION,
        "adapter_version": STANDARD_CASE_ADAPTER_VERSION,
        "dataset": dataset,
        "source_id_sha1": sha1_text(source_id)[:16],
        "question_id_sha1": sha1_text(question_id)[:16],
        "message_count": len(messages),
        "messages_fingerprint": standard_messages_fingerprint(messages),
        "builder": "aippocampus_runtime.recall.index_builder.make_sqlite",
    }


def standard_clean_source_message_rows(
    sqlite_path: Path, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return clean-source-compatible rows for benchmark source artifacts.

    The benchmark source index is public fixture data, but source-side semantic
    materializers still need the same stable `message_id` contract as real clean
    source. Keep this identity tied to the source manifest route, not the local
    cache path, so semantic-scope sidecars can be reused across runs.
    """

    source_key = standard_source_route_key(sqlite_path)
    rows: list[dict[str, Any]] = []
    for message in messages:
        try:
            line = int(message.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        if line <= 0:
            continue
        message_id = f"{source_key}:line:{line}"
        rows.append(
            {
                "message_id": message_id,
                "id": message_id,
                "turn_id": message_id,
                "source_line": line,
                "line": line,
                "timestamp": str(message.get("timestamp") or ""),
                "role": str(message.get("role") or ""),
                "phase": str(message.get("phase") or ""),
                "turn_index": int(message.get("turn_index") or 0),
                "is_final": bool(message.get("is_final")),
                "text": str(message.get("text") or ""),
                "scope_labels": list(message.get("scope_labels") or []),
            }
        )
    return rows


def write_standard_clean_source_messages(
    sqlite_path: Path, messages: list[dict[str, Any]]
) -> Path:
    output_path = sqlite_path.with_name(STANDARD_CLEAN_SOURCE_MESSAGES_FILENAME)
    rows = standard_clean_source_message_rows(sqlite_path, messages)
    tmp = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(output_path)
    return output_path


def prepare_standard_sqlite_index(
    sqlite_path: Path,
    *,
    messages: list[dict[str, Any]],
    manifest: dict[str, Any],
    cache_metrics: dict[str, Any],
    rebuild_cache: bool,
) -> None:
    manifest_path = sqlite_path.with_name("source_index_manifest.json")
    cache_enabled = bool(cache_metrics.get("enabled"))
    if cache_enabled and not rebuild_cache and sqlite_path.exists() and manifest_path.exists():
        existing = read_json_dict(manifest_path)
        if existing == manifest:
            cache_metrics["source_index_hit_count"] += 1
            write_standard_clean_source_messages(sqlite_path, messages)
            return
        cache_metrics["source_index_manifest_mismatch_count"] += 1
    elif cache_enabled:
        cache_metrics["source_index_miss_count"] += 1
    if cache_enabled and rebuild_cache and sqlite_path.exists():
        cache_metrics["source_index_forced_rebuild_count"] += 1

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        make_sqlite(sqlite_path, messages, anchors=[], turns=[])
    except Exception:
        if cache_enabled:
            cache_metrics["source_index_error_rebuild_count"] += 1
        raise
    if cache_enabled:
        cache_metrics["source_index_rebuild_count"] += 1
        write_json_atomic(manifest_path, manifest)
        write_standard_clean_source_messages(sqlite_path, messages)


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
    source_id_sha1 = sha1_text(source_id)[:16]
    message_id = f"standard:{source_id_sha1}:line:{int(line)}"
    return {
        "message_id": message_id,
        "source_ref": message_id,
        "source_id_sha1": source_id_sha1,
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
    cache_metrics: dict[str, Any] | None = None,
    rebuild_cache: bool = False,
    case_progress_callback: Callable[[int, dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache_metrics = cache_metrics or new_standard_case_cache_metrics(
        enabled=False,
        cache_key=None,
        rebuild_requested=rebuild_cache,
    )
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
        sqlite_path = (
            root
            / "standard"
            / "locomo"
            / sha1_text(source_id)[:12]
            / "index"
            / "source_index.sqlite"
        )
        prepare_standard_sqlite_index(
            sqlite_path,
            messages=messages,
            manifest=source_index_manifest(
                dataset="locomo",
                source_id=source_id,
                question_id=source_id,
                messages=messages,
            ),
            cache_metrics=cache_metrics,
            rebuild_cache=rebuild_cache,
        )
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
            if case_progress_callback is not None:
                case_progress_callback(len(cases), corpus)
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
    cache_metrics: dict[str, Any] | None = None,
    rebuild_cache: bool = False,
    case_progress_callback: Callable[[int, dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache_metrics = cache_metrics or new_standard_case_cache_metrics(
        enabled=False,
        cache_key=None,
        rebuild_requested=rebuild_cache,
    )
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
        sqlite_path = (
            root
            / "standard"
            / dataset
            / sha1_text(question_id)[:12]
            / "index"
            / "source_index.sqlite"
        )
        prepare_standard_sqlite_index(
            sqlite_path,
            messages=messages,
            manifest=source_index_manifest(
                dataset=dataset,
                source_id=question_id,
                question_id=question_id,
                messages=messages,
            ),
            cache_metrics=cache_metrics,
            rebuild_cache=rebuild_cache,
        )
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
        if case_progress_callback is not None:
            case_progress_callback(len(cases), corpus)
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


def hit_lines(hits: list[dict[str, Any]], *, limit: int | None = None) -> set[int]:
    lines: set[int] = set()
    bounded_hits = hits if limit is None else hits[: max(0, int(limit))]
    for hit in bounded_hits:
        try:
            lines.add(int(hit["line"]))
        except (TypeError, ValueError, KeyError):
            continue
    return lines


def evidence_rank_bucket(rank: int | None) -> str:
    if not rank:
        return "not_retrieved"
    if int(rank) == 1:
        return "rank_1"
    if int(rank) <= 3:
        return "rank_2_3"
    if int(rank) <= 5:
        return "rank_4_5"
    if int(rank) <= 10:
        return "rank_6_10"
    if int(rank) <= 20:
        return "rank_11_20"
    if int(rank) <= 50:
        return "rank_21_50"
    return "rank_below_50"


def nearest_expected_line_distance(
    hits: list[dict[str, Any]],
    *,
    expected_lines: set[int],
    line_to_session: dict[str, str],
    limit: int,
) -> int | None:
    if not expected_lines:
        return None
    best: int | None = None
    for hit in hits[: max(0, int(limit))]:
        try:
            hit_line = int(hit["line"])
        except (TypeError, ValueError, KeyError):
            continue
        hit_session = line_to_session.get(str(hit_line))
        for expected_line in expected_lines:
            expected_session = line_to_session.get(str(expected_line))
            if hit_session and expected_session and hit_session != expected_session:
                continue
            distance = abs(hit_line - int(expected_line))
            if best is None or distance < best:
                best = distance
    return best


def evidence_context_distance_bucket(distance: int | None, *, context_radius: int) -> str:
    if distance is None:
        return "not_visible"
    if int(distance) == 0:
        return "exact_line"
    if int(distance) == 1:
        return "distance_1"
    if int(distance) <= max(1, int(context_radius)):
        return "distance_2_to_context_radius"
    return "outside_context_radius"


def evidence_miss_category(row: dict[str, Any], *, top_k: int) -> str:
    if not row.get("has_line_evidence"):
        return "no_line_evidence"
    exact_hit = bool(row.get(f"evidence_hit_top{top_k}"))
    expected_count = int(row.get("expected_line_count") or 0)
    found_top_k = int(row.get(f"expected_lines_found_top{top_k}") or 0)
    if exact_hit and expected_count > 1 and 0 < found_top_k < expected_count:
        return "multi_evidence_partial_hit"
    if exact_hit:
        return "exact_line_found_top_k"
    if row.get(f"evidence_context_hit_top{top_k}"):
        return "context_visible_exact_line_miss"
    if row.get(f"session_hit_top{top_k}"):
        return "same_session_wrong_line_top_k"
    rank = row.get("evidence_rank")
    if rank:
        if int(rank) <= 20:
            return "gold_line_near_miss_rank_2_20"
        if int(rank) <= 50:
            return "gold_line_low_rank_21_50"
        return "gold_line_rank_below_50"
    if row.get("session_rank"):
        return "session_found_below_top_k"
    return "source_window_not_recovered"


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


def lexical_line_reranker_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for term in split_query_terms([text]):
        clean = term.strip().casefold()
        if not clean or clean in STANDARD_QUERY_TERM_STOPWORDS:
            continue
        if len(clean) < 3 and not re.search(r"\d", clean):
            continue
        terms.add(clean)
        for suffix in ("ing", "ed", "es", "s"):
            if len(clean) > len(suffix) + 3 and clean.endswith(suffix):
                terms.add(clean[: -len(suffix)])
                break
    return terms


def lexical_line_reranker_score(
    question_terms: set[str],
    candidate: dict[str, Any],
) -> float:
    text_terms = lexical_line_reranker_terms(str(candidate.get("text") or ""))
    overlap = len(question_terms & text_terms)
    coverage = overlap / max(1, len(question_terms))
    channels = {str(channel) for channel in candidate.get("query_channels") or []}
    fts_rank = candidate.get("fts_rank")
    nearest_hit_rank = int(candidate.get("nearest_hit_rank") or 10**6)
    context_distance = int(candidate.get("context_distance") or 0)
    score = (overlap * 100.0) + (coverage * 25.0)
    if "content" in channels:
        score += 18.0
    if fts_rank is not None:
        score += max(0.0, 12.0 - float(fts_rank))
    if str(candidate.get("role") or "").casefold() == "user":
        score += 4.0
    if text_terms & LEXICAL_RERANKER_DIRECT_TERMS:
        score += 6.0
    if text_terms & LEXICAL_RERANKER_BRIDGE_TERMS:
        score -= 8.0
    score -= context_distance * 1.5
    score -= nearest_hit_rank * 0.05
    return score


def run_lexical_line_reranker(
    question: str,
    candidates: list[dict[str, Any]],
    **_: object,
) -> dict[str, Any]:
    """Rank visible source lines with local lexical evidence cues only.

    This is a deterministic diagnostic reranker for exact-line recovery. It
    uses question/candidate text and source-window metadata, but never answer
    labels, expected lines, or model summaries. Keep it conservative: the
    surrounding evaluator fuses this ranking with first-stage FTS so a local
    heuristic can promote context-visible evidence without suppressing an
    exact line that FTS already surfaced.
    """

    if not candidates:
        return {"available": False, "ranked_lines": [], "errors": ["empty candidates"]}
    question_terms = lexical_line_reranker_terms(question)
    scored = [
        (
            lexical_line_reranker_score(question_terms, candidate),
            int(candidate.get("session_rank") or 10**6),
            int(candidate.get("nearest_hit_rank") or 10**6),
            int(candidate.get("fts_rank") or 10**6),
            int(candidate.get("context_distance") or 0),
            int(candidate["line"]),
        )
        for candidate in candidates
    ]
    scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3], item[4], item[5]))
    ranked_lines = [int(item[-1]) for item in scored]
    lead = scored[0][0] - scored[1][0] if len(scored) > 1 else scored[0][0]
    return {
        "available": True,
        "ranked_lines": ranked_lines,
        "confidence": clamp_confidence(0.35 + min(0.45, max(0.0, lead) / 120.0)),
        "usage": {"local_scored_candidates": len(candidates)},
    }


def structural_line_reranker_score(
    question_terms: set[str],
    candidate: dict[str, Any],
) -> float:
    """Score candidate lines with source-window structure, without gold labels.

    This is deliberately a packaging heuristic, not an answer oracle. It can use
    adjacent source lines and route metadata because those are what a foreground
    packet can reopen, but it must not depend on expected-line fields. The large
    continuation bonus is there for the LongMemEval failure family where FTS
    lands on a clue/bridge line and the exact answer-bearing row is immediately
    before or after it; removing that turns context-visible misses into broad
    windows again.
    """

    text = str(candidate.get("text") or "")
    text_terms = lexical_line_reranker_terms(text)
    previous_text = str(candidate.get("previous_text") or "")
    next_text = str(candidate.get("next_text") or "")
    previous_terms = lexical_line_reranker_terms(previous_text)
    next_terms = lexical_line_reranker_terms(next_text)
    overlap = len(question_terms & text_terms)
    previous_overlap = len(question_terms & previous_terms)
    next_overlap = len(question_terms & next_terms)
    nearest_hit_line = int(candidate.get("nearest_hit_line") or candidate.get("line") or 0)
    line = int(candidate.get("line") or 0)
    distance = abs(line - nearest_hit_line)
    role = str(candidate.get("role") or "").casefold()
    previous_role = str(candidate.get("previous_role") or "").casefold()
    is_after_hit = bool(line > nearest_hit_line)
    is_before_hit = bool(line < nearest_hit_line)
    value_like = bool(STRUCTURAL_RERANKER_VALUE_RE.search(text))
    answer_like = bool(STRUCTURAL_RERANKER_ANSWER_CUE_RE.search(text))
    question_like = bool(STRUCTURAL_RERANKER_QUESTION_CUE_RE.search(text))
    previous_continuation = bool(STRUCTURAL_RERANKER_CONTINUATION_RE.search(previous_text))
    current_bridge = bool(
        text_terms & LEXICAL_RERANKER_BRIDGE_TERMS
        or STRUCTURAL_RERANKER_CONTINUATION_RE.search(text)
    )
    query_is_question = bool(STRUCTURAL_RERANKER_QUESTION_CUE_RE.search(" ".join(question_terms)))

    score = lexical_line_reranker_score(question_terms, candidate)
    if value_like:
        score += 4.0
    if answer_like:
        score += 6.0
    if role == "assistant" and previous_role == "user":
        score += 4.0
    if distance == 1 and is_after_hit:
        score += 4.0
    elif distance == 1 and is_before_hit:
        score += 2.0
    if previous_overlap and distance <= 2:
        score += min(16.0, previous_overlap * 4.0)
    if next_overlap and distance <= 2:
        score += min(8.0, next_overlap * 3.0)
    if previous_continuation and distance == 1:
        score += 120.0
    if previous_continuation and (value_like or answer_like):
        score += 60.0
    if query_is_question and question_like and not answer_like:
        score -= 12.0
    if current_bridge and not answer_like:
        score -= 110.0
    if overlap == 0 and (value_like or answer_like) and max(previous_overlap, next_overlap) >= 2:
        score += 25.0
    return score


def run_structural_line_reranker(
    question: str,
    candidates: list[dict[str, Any]],
    **_: object,
) -> dict[str, Any]:
    """Rank visible source lines with local structure and adjacent context."""

    if not candidates:
        return {"available": False, "ranked_lines": [], "errors": ["empty candidates"]}
    question_terms = lexical_line_reranker_terms(question)
    scored = [
        (
            structural_line_reranker_score(question_terms, candidate),
            int(candidate.get("session_rank") or 10**6),
            int(candidate.get("nearest_hit_rank") or 10**6),
            int(candidate.get("context_distance") or 0),
            int(candidate["line"]),
        )
        for candidate in candidates
    ]
    scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3], item[4]))
    ranked_lines = [int(item[-1]) for item in scored]
    lead = scored[0][0] - scored[1][0] if len(scored) > 1 else scored[0][0]
    return {
        "available": True,
        "ranked_lines": ranked_lines,
        "confidence": clamp_confidence(0.38 + min(0.42, max(0.0, lead) / 140.0)),
        "usage": {"local_scored_candidates": len(candidates)},
        "metadata": {
            "arm": "deterministic_source_window_structural_rerank",
            "feature_boundary": [
                "question_text",
                "candidate_source_text",
                "adjacent_source_text",
                "route_rank_metadata",
                "source_window_distance",
            ],
            "withheld_from_ranker": [
                "gold_answer",
                "expected_lines",
                "expected_sessions",
                "has_answer_labels",
                "judge_labels",
                "miss_taxonomy",
            ],
        },
    }


def source_semantic_cache_public_contract() -> dict[str, Any]:
    return {
        "arm": SOURCE_SEMANTIC_CACHE_ARM,
        "builder": "aippocampus_worker_surface",
        "builder_id": SOURCE_SEMANTIC_CACHE_BUILDER_ID,
        "prompt_version": None,
        "cache_policy_version": SOURCE_SEMANTIC_CACHE_POLICY_VERSION,
        "provider": "local_aippocampus_runtime",
        "model": "none",
        "base_url_sha1": "",
        "cache_contract": NO_PROVIDER_CACHE_CONTRACT,
        "cost_status": "no_provider_calls",
        "input_boundary": {
            "offline_build_visible": [
                "source_line_number",
                "source_role",
                "source_text",
                "adjacent_source_text_in_same_session",
                "source_session_id",
                "source_backed_semantic_scope_label_terms",
                "deterministic_factual_alias_terms",
                "answer_bearing_source_terms",
            ],
            "hot_query_visible": [
                "query_terms",
                "aippocampus_working_memory_trigger_terms",
                "source_side_factual_alias_terms",
                "candidate_line_number",
                "candidate_route_rank_metadata",
                "candidate_context_distance",
            ],
            "withheld_from_builder_and_hot_path": [
                "gold_answer",
                "expected_lines",
                "expected_sessions",
                "has_answer_labels",
                "judge_labels",
                "miss_taxonomy",
                "raw_report_cases",
            ],
        },
        "output_boundary": {
            "source_side_search_allowed": True,
            "ranked_lines_filtered_to_source_side_candidate_set": True,
            "question_answering_allowed": False,
            "local_factual_aliases_are_navigation_only": True,
            "working_memory_rows_are_navigation_only": True,
            "source_reopen_required_for_claims": True,
            "cache_values_emitted": False,
            "raw_source_text_emitted": False,
        },
    }


def source_semantic_line_labels(text: str) -> list[str]:
    labels: list[str] = []
    if SOURCE_SEMANTIC_PREFERENCE_RE.search(text):
        labels.append("preference")
    if SOURCE_SEMANTIC_CURRENTNESS_RE.search(text):
        labels.append("currentness_or_temporal")
    if SOURCE_SEMANTIC_TASK_RE.search(text):
        labels.append("technical_or_task")
    if STRUCTURAL_RERANKER_ANSWER_CUE_RE.search(text):
        labels.append("answer_like_statement")
    if STRUCTURAL_RERANKER_QUESTION_CUE_RE.search(text):
        labels.append("question_like")
    if STRUCTURAL_RERANKER_CONTINUATION_RE.search(text):
        labels.append("continuation_bridge")
    if STRUCTURAL_RERANKER_VALUE_RE.search(text):
        labels.append("value_like")
    return sorted(set(labels))


def source_semantic_query_labels(question: str) -> set[str]:
    labels = set(source_semantic_line_labels(question))
    if "question_like" in labels:
        labels.remove("question_like")
    return labels


def source_semantic_scope_terms(item: dict[str, Any]) -> set[str]:
    """Extract ranking hints from source-backed semantic sidecar prose.

    These terms help source-side warming shape route selection, but they remain
    navigation hints. The foreground path must still reopen the clean-source row
    before making any factual claim from the selected line.
    """

    if not isinstance(item, dict) or not item:
        return set()
    fragments: list[str] = []
    for key in ("rationale", "summary", "why"):
        value = str(item.get(key) or "").strip()
        if value:
            fragments.append(value)
    for evidence in item.get("label_evidence") or []:
        if not isinstance(evidence, dict):
            continue
        reason = str(
            evidence.get("reason")
            or evidence.get("rationale")
            or evidence.get("summary")
            or evidence.get("why")
            or ""
        ).strip()
        if reason:
            fragments.append(reason)
    return lexical_line_reranker_terms(compact_text(" ".join(fragments), 1200))


def source_factual_alias_terms(
    text: str,
    *,
    previous_text: str = "",
    next_text: str = "",
) -> set[str]:
    """Return deterministic factual-query aliases for source-side retrieval.

    This is a deliberately small local bridge from source wording to ordinary
    factual question wording. It must not learn from gold answers, expected
    lines, miss taxonomies, or query-time model calls. The aliases are local
    navigation handles only; source reopen is still required before any claim.
    """

    # Keep aliases line-local. Adjacent context can help answer-bearing terms
    # after the current row is already factual-looking, but letting neighbor
    # relations create aliases makes whole sessions look answer-bearing.
    _ = (previous_text, next_text)
    source_text = compact_text(source_factual_surface_text(text), 1200)
    source_terms = lexical_line_reranker_terms(source_text)
    aliases: set[str] = set()
    for pattern, values in FACTUAL_ALIAS_RELATION_GROUPS:
        if pattern.search(source_text):
            aliases.update(values)
    for term in source_terms:
        aliases.update(FACTUAL_NOUN_ALIAS_TERMS.get(term, ()))
    return {
        alias.casefold()
        for alias in aliases
        if alias
        and alias.casefold() not in STANDARD_QUERY_TERM_STOPWORDS
        and (len(alias) >= 3 or re.search(r"\d", alias))
    }


def source_answer_bearing_terms(
    text: str,
    *,
    previous_text: str = "",
    next_text: str = "",
) -> set[str]:
    """Return local terms that make a row worth reopening for factual claims."""

    clean_text = source_factual_surface_text(text)
    clean_previous = source_factual_surface_text(previous_text)
    clean_next = source_factual_surface_text(next_text)
    factual_labels = set(source_semantic_line_labels(clean_text))
    if not factual_labels & {
        "answer_like_statement",
        "value_like",
        "preference",
        "currentness_or_temporal",
    }:
        return set()
    terms = lexical_line_reranker_terms(clean_text)
    if factual_labels & {"answer_like_statement", "value_like"}:
        terms.update(lexical_line_reranker_terms(clean_previous))
        terms.update(lexical_line_reranker_terms(clean_next))
    return {
        term
        for term in terms
        if term and term not in STANDARD_QUERY_TERM_STOPWORDS
    }


def source_factual_surface_text(text: str) -> str:
    """Remove dataset boilerplate that would otherwise look like factual content."""

    lines = [
        line
        for line in str(text or "").splitlines()
        if not line.strip().casefold().startswith("session date:")
    ]
    return "\n".join(lines).strip()


def line_to_session_fingerprint(line_to_session: dict[str, str]) -> str:
    return stable_json_sha1(
        sorted((str(key), str(value)) for key, value in line_to_session.items()),
        length=40,
    )


def source_index_manifest_fingerprint(sqlite_path: Path) -> str:
    manifest = read_json_dict(sqlite_path.with_name("source_index_manifest.json"))
    if manifest:
        return stable_json_sha1(manifest, length=40)
    digest = hashlib.sha1()
    with sqlite_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_scope_sidecar_fingerprint(sqlite_path: Path) -> str:
    sidecar_path = sqlite_path.with_name(SEMANTIC_SCOPE_LABELS_FILENAME)
    if not sidecar_path.exists():
        return ""
    digest = hashlib.sha1()
    for path in (sidecar_path, sqlite_path.with_name(SEMANTIC_SCOPE_SIDECAR_MANIFEST_FILENAME)):
        if not path.exists():
            continue
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def standard_source_route_key(sqlite_path: Path) -> str:
    """Return a path-stable source route key for benchmark-derived sources.

    Source-side benchmark artifacts need the same identity discipline as real
    clean source. If this key depends on the temporary/cache SQLite path, repeat
    runs over the same public source look like different memory routes and
    cannot safely join later semantic-scope sidecars or warm-route artifacts.
    """

    manifest = read_json_dict(sqlite_path.with_name("source_index_manifest.json")) or {}
    dataset = str(manifest.get("dataset") or "standard_public")
    source_id_sha1 = str(manifest.get("source_id_sha1") or "").strip()
    question_id_sha1 = str(manifest.get("question_id_sha1") or "").strip()
    if source_id_sha1 or question_id_sha1:
        return ":".join(
            [
                "standard_public",
                dataset,
                f"source:{source_id_sha1 or 'unknown'}",
                f"question:{question_id_sha1 or 'unknown'}",
            ]
        )
    return "standard_public:manifest:" + source_index_manifest_fingerprint(sqlite_path)[:20]


def source_semantic_artifact_cache_key(
    sqlite_path: Path,
    *,
    line_to_session: dict[str, str],
) -> str:
    material = {
        "policy_version": SOURCE_SEMANTIC_CACHE_POLICY_VERSION,
        "builder_id": SOURCE_SEMANTIC_CACHE_BUILDER_ID,
        "source_index_manifest_sha1": source_index_manifest_fingerprint(sqlite_path),
        "semantic_scope_sidecar_sha1": semantic_scope_sidecar_fingerprint(sqlite_path),
        "line_to_session_sha1": line_to_session_fingerprint(line_to_session),
    }
    return stable_json_sha1(material, length=20)


def source_semantic_cache_for_json(cache: dict[str, Any]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for raw_line, raw_profile in (cache.get("profiles") or {}).items():
        if not isinstance(raw_profile, dict):
            continue
        profile = dict(raw_profile)
        for key in (
            "source_terms",
            "previous_terms",
            "next_terms",
            "route_terms",
            "labels",
            "context_labels",
            "semantic_scope_labels",
            "semantic_scope_terms",
            "factual_alias_terms",
            "answer_bearing_terms",
        ):
            value = profile.get(key)
            if isinstance(value, set):
                profile[key] = sorted(str(item) for item in value)
        profiles[str(raw_line)] = profile
    return {
        "schema_version": 1,
        "kind": "source_semantic_cache_artifact",
        "manifest": dict(cache.get("manifest") or {}),
        "profiles": profiles,
        "working_memory_rows": [
            row for row in (cache.get("working_memory_rows") or []) if isinstance(row, dict)
        ],
    }


def source_semantic_cache_from_json(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("kind") != "source_semantic_cache_artifact":
        return None
    profiles: dict[int, dict[str, Any]] = {}
    for raw_line, raw_profile in (payload.get("profiles") or {}).items():
        if not isinstance(raw_profile, dict):
            continue
        try:
            line = int(raw_line)
        except (TypeError, ValueError):
            continue
        profiles[line] = dict(raw_profile)
    working_rows = [
        row for row in (payload.get("working_memory_rows") or []) if isinstance(row, dict)
    ]
    return {
        "manifest": dict(payload.get("manifest") or {}),
        "profiles": profiles,
        "working_memory_rows": working_rows,
    }


def build_source_semantic_cache(
    sqlite_path: Path,
    *,
    line_to_session: dict[str, str],
) -> dict[str, Any]:
    """Build AIppocampus source-side worker surfaces for a local hot path.

    This deliberately does not see query text or gold labels. It materializes
    the same navigation-only row shape read by the foreground AIppocampus
    working-memory/semantic-trigger surfaces, then the hot path uses existing
    matchers to reopen candidate source lines. Do not replace this with
    query/candidate provider calls; #1323 is about source-side prewarmed
    surfaces, not foreground LLM reranking.
    """

    started = time.perf_counter()
    rows = load_standard_message_rows(sqlite_path)
    row_by_line = {int(row["line"]): row for row in rows}
    profiles: dict[int, dict[str, Any]] = {}
    working_memory_rows: list[dict[str, Any]] = []
    failed_count = 0
    source_key = standard_source_route_key(sqlite_path)
    semantic_scope_sidecar = load_semantic_scope_labels(sqlite_path.parent)
    semantic_scope_label_row_count = 0
    factual_alias_profile_count = 0
    factual_alias_term_count = 0
    created_at = now_utc()
    for row in rows:
        try:
            line = int(row["line"])
            message_id = f"{source_key}:line:{line}"
            session_id = line_to_session.get(str(line)) or ""
            previous_row = row_by_line.get(line - 1)
            next_row = row_by_line.get(line + 1)
            previous_text = (
                str(previous_row.get("text") or "")
                if previous_row and line_to_session.get(str(line - 1)) == session_id
                else ""
            )
            next_text = (
                str(next_row.get("text") or "")
                if next_row and line_to_session.get(str(line + 1)) == session_id
                else ""
            )
            text = str(row.get("text") or "")
            source_terms = lexical_line_reranker_terms(text)
            previous_terms = lexical_line_reranker_terms(previous_text)
            next_terms = lexical_line_reranker_terms(next_text)
            labels = source_semantic_line_labels(text)
            semantic_scope_item = semantic_scope_sidecar.get(message_id) or {}
            semantic_labels = semantic_labels_for_message(
                {"message_id": message_id}, semantic_scope_sidecar
            )
            semantic_scope_terms = source_semantic_scope_terms(semantic_scope_item)
            if semantic_labels:
                semantic_scope_label_row_count += 1
                labels = fts5_benchmark.unique_preserve([*labels, *semantic_labels])
            label_set = set(labels)
            factual_alias_terms = source_factual_alias_terms(
                text,
                previous_text=previous_text,
                next_text=next_text,
            )
            answer_bearing_terms = source_answer_bearing_terms(
                text,
                previous_text=previous_text,
                next_text=next_text,
            )
            if factual_alias_terms:
                factual_alias_profile_count += 1
                factual_alias_term_count += len(factual_alias_terms)
            context_labels = set(source_semantic_line_labels(previous_text))
            context_labels.update(source_semantic_line_labels(next_text))
            route_terms = set(source_terms)
            route_terms.update(previous_terms)
            route_terms.update(next_terms)
            route_terms.update(str(label).casefold() for label in labels)
            route_terms.update(str(label).casefold() for label in context_labels)
            route_terms.update(semantic_scope_terms)
            route_terms.update(factual_alias_terms)
            route_terms.update(answer_bearing_terms)
            route_terms_list = [
                term
                for term in sorted(route_terms)
                if term and term not in STANDARD_QUERY_TERM_STOPWORDS
            ][:48]
            source_ref = {
                "ref": f"{source_key}:line:{line}",
                "thread_key": source_key,
                "message_id": message_id,
                "turn_id": message_id,
                "source_line": line,
                "line": line,
                "role": str(row.get("role") or ""),
                "phase": str(row.get("phase") or ""),
            }
            working_memory_row = {
                "schema_version": 1,
                "kind": "aippocampus_working_memory",
                "created_at": created_at,
                "status": "active",
                "route": "use_with_source",
                "ask_policy": "source_required",
                "risk": "low",
                "route_reason": "longmemeval_source_side_worker_surface",
                "candidate_key": "lm_worker_surface_"
                + sha1_text(f"{source_key}\n{line}\n{text}")[:18],
                "candidate_type": "project_memory",
                "title": f"source line {line}",
                "summary": (
                    "Source-side route surface; reopen the clean-source "
                    "line before using it as evidence."
                ),
                "recommendation": (
                    "Use as navigation only; reopen the clean-source line "
                    "before making factual claims."
                ),
                "confidence": 0.7,
                "trigger_terms": route_terms_list,
                "activation_cues": route_terms_list[:12],
                "concepts": route_terms_list[:16],
                "source_refs": [source_ref],
                "source_strength": {
                    "level": "visible_source",
                    "score": 1.0,
                    "source_ref_count": 1,
                },
            }
            if semantic_labels:
                working_memory_row["scope_labels"] = semantic_labels
                working_memory_row["semantic_scope_labels"] = semantic_labels
            if semantic_scope_terms:
                working_memory_row["semantic_scope_terms"] = sorted(semantic_scope_terms)[:24]
            if factual_alias_terms:
                working_memory_row["factual_alias_terms"] = sorted(factual_alias_terms)[:32]
            if answer_bearing_terms:
                working_memory_row["answer_bearing_terms"] = sorted(answer_bearing_terms)[:32]
            working_memory_rows.append(working_memory_row)
            profiles[line] = {
                "line": line,
                "role": str(row.get("role") or "").casefold(),
                "session_id_sha1": sha1_text(session_id)[:16] if session_id else "",
                "source_terms": source_terms,
                "previous_terms": previous_terms,
                "next_terms": next_terms,
                "route_terms": route_terms,
                "labels": label_set,
                "context_labels": context_labels,
                "semantic_scope_labels": set(semantic_labels),
                "semantic_scope_terms": semantic_scope_terms,
                "factual_alias_terms": factual_alias_terms,
                "answer_bearing_terms": answer_bearing_terms,
                "source_text_sha1": sha1_text(text)[:16],
                "previous_text_sha1": sha1_text(previous_text)[:16],
                "next_text_sha1": sha1_text(next_text)[:16],
                "route_profile_sha1": sha1_text(
                    " ".join(
                        [
                            " ".join(sorted(source_terms))[:256],
                            " ".join(labels),
                            " ".join(sorted(semantic_scope_terms))[:256],
                            " ".join(sorted(factual_alias_terms))[:256],
                        ]
                    )
                )[:16],
            }
        except Exception:  # pragma: no cover - defensive for malformed corpora
            failed_count += 1
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "profiles": profiles,
        "working_memory_rows": working_memory_rows,
        "manifest": {
            "schema_version": 1,
            "kind": "source_side_semantic_cache_manifest",
            "builder": "aippocampus_worker_surface",
            "builder_id": SOURCE_SEMANTIC_CACHE_BUILDER_ID,
            "cache_policy_version": SOURCE_SEMANTIC_CACHE_POLICY_VERSION,
            "source_index_sha1": source_index_manifest_fingerprint(sqlite_path)[:16],
            "source_identity": {
                "kind": "standard_public_manifest_route_key",
                "route_key_sha1": sha1_text(source_key)[:16],
                "stable_across_cache_roots": True,
            },
            "message_count": len(rows),
            "span_count": len(profiles),
            "working_memory_row_count": len(working_memory_rows),
            "complete_count": len(profiles),
            "failed_count": failed_count,
            "complete_rate": safe_rate(len(profiles), len(rows)),
            "build_latency_ms": elapsed_ms,
            "provider_call_count": 0,
            "provider_total_tokens": 0,
            "hot_query_provider_call_count": 0,
            "raw_source_text_emitted": False,
            "cache_values_emitted": False,
            "line_to_session_sha1": line_to_session_fingerprint(line_to_session),
            "source_index_manifest_sha1": source_index_manifest_fingerprint(sqlite_path),
            "semantic_scope_sidecar_sha1": semantic_scope_sidecar_fingerprint(sqlite_path),
            "semantic_scope_sidecar_loaded": bool(semantic_scope_sidecar),
            "semantic_scope_sidecar_row_count": len(semantic_scope_sidecar),
            "semantic_scope_label_row_count": semantic_scope_label_row_count,
            "factual_alias_profile_count": factual_alias_profile_count,
            "factual_alias_term_count": factual_alias_term_count,
            "factual_alias_artifact_contract": {
                "kind": "source_side_factual_alias_terms",
                "source": "deterministic_local_source_text_and_adjacent_context",
                "authority": "navigation_only",
                "claim_permission": "none",
                "source_reopen_required": True,
            },
        },
    }


class SourceSemanticCacheStore:
    def __init__(
        self,
        *,
        artifact_cache_dir: Path | str | None = None,
        rebuild_artifact_cache: bool = False,
    ) -> None:
        self._lock = threading.Lock()
        self._caches: dict[str, dict[str, Any]] = {}
        self._artifact_cache_dir = (
            Path(artifact_cache_dir).resolve() if artifact_cache_dir else None
        )
        self._rebuild_artifact_cache = bool(rebuild_artifact_cache)
        self._artifact_hits = 0
        self._artifact_misses = 0
        self._artifact_rebuilds = 0
        self._artifact_mismatches = 0

    def _artifact_path(
        self,
        sqlite_path: Path,
        *,
        line_to_session: dict[str, str],
    ) -> Path | None:
        if self._artifact_cache_dir is None:
            return None
        key = source_semantic_artifact_cache_key(
            sqlite_path,
            line_to_session=line_to_session,
        )
        return self._artifact_cache_dir / f"{key}.json"

    def _load_artifact(self, artifact_path: Path) -> dict[str, Any] | None:
        payload = read_json_dict(artifact_path)
        if not payload:
            self._artifact_misses += 1
            return None
        cache = source_semantic_cache_from_json(payload)
        if cache is None:
            self._artifact_mismatches += 1
            return None
        manifest = cache.get("manifest") or {}
        if (
            manifest.get("cache_policy_version") != SOURCE_SEMANTIC_CACHE_POLICY_VERSION
            or manifest.get("builder_id") != SOURCE_SEMANTIC_CACHE_BUILDER_ID
        ):
            self._artifact_mismatches += 1
            return None
        self._artifact_hits += 1
        return cache

    def _write_artifact(self, artifact_path: Path, cache: dict[str, Any]) -> None:
        write_json_atomic(artifact_path, source_semantic_cache_for_json(cache))
        self._artifact_rebuilds += 1

    def get(
        self,
        sqlite_path: Path,
        *,
        line_to_session: dict[str, str],
    ) -> dict[str, Any]:
        key = str(Path(sqlite_path).resolve())
        with self._lock:
            cached = self._caches.get(key)
        if cached is not None:
            return cached
        artifact_path = self._artifact_path(
            Path(sqlite_path),
            line_to_session=line_to_session,
        )
        if artifact_path is not None and not self._rebuild_artifact_cache:
            loaded = self._load_artifact(artifact_path)
            if loaded is not None:
                with self._lock:
                    return self._caches.setdefault(key, loaded)
        built = build_source_semantic_cache(
            Path(sqlite_path),
            line_to_session=line_to_session,
        )
        if artifact_path is not None:
            self._write_artifact(artifact_path, built)
        with self._lock:
            return self._caches.setdefault(key, built)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            caches = list(self._caches.values())
        manifests = [cache.get("manifest") or {} for cache in caches]
        build_latencies = [
            float(manifest.get("build_latency_ms") or 0.0)
            for manifest in manifests
            if isinstance(manifest.get("build_latency_ms"), int | float)
        ]
        message_count = sum(int(manifest.get("message_count") or 0) for manifest in manifests)
        span_count = sum(int(manifest.get("span_count") or 0) for manifest in manifests)
        working_memory_row_count = sum(
            int(manifest.get("working_memory_row_count") or 0)
            for manifest in manifests
        )
        semantic_scope_sidecar_count = sum(
            1 for manifest in manifests if manifest.get("semantic_scope_sidecar_loaded")
        )
        semantic_scope_sidecar_row_count = sum(
            int(manifest.get("semantic_scope_sidecar_row_count") or 0)
            for manifest in manifests
        )
        semantic_scope_label_row_count = sum(
            int(manifest.get("semantic_scope_label_row_count") or 0)
            for manifest in manifests
        )
        factual_alias_profile_count = sum(
            int(manifest.get("factual_alias_profile_count") or 0)
            for manifest in manifests
        )
        factual_alias_term_count = sum(
            int(manifest.get("factual_alias_term_count") or 0)
            for manifest in manifests
        )
        failed_count = sum(int(manifest.get("failed_count") or 0) for manifest in manifests)
        return {
            "status": "measured_source_side_cache_build" if manifests else "not_measured",
            "arm": SOURCE_SEMANTIC_CACHE_ARM,
            "builder_id": SOURCE_SEMANTIC_CACHE_BUILDER_ID,
            "cache_policy_version": SOURCE_SEMANTIC_CACHE_POLICY_VERSION,
            "source_artifact_cache": {
                "enabled": self._artifact_cache_dir is not None,
                "cache_root_emitted": False,
                "hit_count": self._artifact_hits,
                "miss_count": self._artifact_misses,
                "rebuild_count": self._artifact_rebuilds,
                "manifest_mismatch_count": self._artifact_mismatches,
                "rebuild_requested": self._rebuild_artifact_cache,
            },
            "source_cache_count": len(manifests),
            "message_count": message_count,
            "span_count": span_count,
            "working_memory_row_count": working_memory_row_count,
            "semantic_scope_sidecar_count": semantic_scope_sidecar_count,
            "semantic_scope_sidecar_row_count": semantic_scope_sidecar_row_count,
            "semantic_scope_label_row_count": semantic_scope_label_row_count,
            "factual_alias_profile_count": factual_alias_profile_count,
            "factual_alias_term_count": factual_alias_term_count,
            "factual_alias_profile_rate": safe_rate(
                factual_alias_profile_count,
                span_count,
            ),
            "complete_count": span_count,
            "failed_count": failed_count,
            "cache_key_complete_rate": safe_rate(span_count, message_count),
            "build_latency_ms": {
                "count": len(build_latencies),
                "total": round(sum(build_latencies), 2) if build_latencies else 0.0,
                "avg": round(sum(build_latencies) / len(build_latencies), 2)
                if build_latencies
                else 0.0,
                "max": round(max(build_latencies), 2) if build_latencies else 0.0,
            },
            "provider_call_count": 0,
            "provider_total_tokens": 0,
            "hot_query_provider_call_count": 0,
            "cost_status": "no_provider_calls",
            "raw_source_text_emitted": False,
            "cache_values_emitted": False,
            "default_hook_path": False,
        }


def source_semantic_cache_score(
    question_terms: set[str],
    query_labels: set[str],
    candidate: dict[str, Any],
    profile: dict[str, Any],
) -> float:
    source_terms = set(profile.get("source_terms") or set())
    previous_terms = set(profile.get("previous_terms") or set())
    next_terms = set(profile.get("next_terms") or set())
    labels = set(profile.get("labels") or set())
    context_labels = set(profile.get("context_labels") or set())
    semantic_scope_terms = set(profile.get("semantic_scope_terms") or set())
    factual_alias_terms = set(profile.get("factual_alias_terms") or set())
    answer_bearing_terms = set(profile.get("answer_bearing_terms") or set())
    source_overlap = len(question_terms & source_terms)
    previous_overlap = len(question_terms & previous_terms)
    next_overlap = len(question_terms & next_terms)
    context_overlap = previous_overlap + next_overlap
    semantic_scope_overlap = len(question_terms & semantic_scope_terms)
    factual_alias_overlap = len(question_terms & factual_alias_terms)
    answer_bearing_overlap = len(question_terms & answer_bearing_terms)
    coverage = source_overlap / max(1, len(question_terms))
    label_overlap = len(query_labels & labels)
    context_label_overlap = len(query_labels & context_labels)
    nearest_hit_rank = int(candidate.get("nearest_hit_rank") or 10**6)
    context_distance = int(candidate.get("context_distance") or 0)
    fts_rank = candidate.get("fts_rank")
    role = str(profile.get("role") or "")

    score = source_overlap * 100.0
    score += coverage * 30.0
    score += context_overlap * 34.0
    score += label_overlap * 12.0
    score += context_label_overlap * 5.0
    score += semantic_scope_overlap * 32.0
    score += factual_alias_overlap * 112.0
    score += answer_bearing_overlap * 12.0
    if "content" in {str(channel) for channel in candidate.get("query_channels") or []}:
        score += 16.0
    if fts_rank is not None:
        score += max(0.0, 12.0 - float(fts_rank))
    if role == "user":
        score += 4.0
    if "answer_like_statement" in labels:
        score += 8.0
    if "value_like" in labels:
        score += 6.0
    if "question_like" in labels and "answer_like_statement" not in labels:
        score -= 12.0
    if "continuation_bridge" in labels and source_overlap == 0:
        score -= 22.0
    if source_terms & LEXICAL_RERANKER_BRIDGE_TERMS and source_overlap < max(1, context_overlap):
        score -= 18.0
    if context_overlap and ("answer_like_statement" in labels or "value_like" in labels):
        score += min(36.0, context_overlap * 8.0)
    if semantic_scope_overlap and labels:
        score += min(12.0, semantic_scope_overlap * 3.0)
    if factual_alias_overlap and ("answer_like_statement" in labels or "value_like" in labels):
        # Factual aliases are source-local route handles, not source truth. When
        # a query asks with a paraphrase such as "keepsake kept" and the source
        # line says "souvenir stored", this boost lets the bounded candidate
        # reranker prefer the answer-bearing row over a nearby topical row
        # without widening the foreground source window.
        score += min(64.0, factual_alias_overlap * 24.0)
    score -= context_distance * 1.25
    score -= nearest_hit_rank * 0.05
    return score


def source_semantic_cache_search_score(
    question_terms: set[str],
    query_labels: set[str],
    profile: dict[str, Any],
) -> float:
    """Score source-side cached profiles before candidate construction.

    This is the hot-query retrieval half of the source-side arm. It can inspect
    only cached source-derived route terms/labels and the current query terms.
    It deliberately cannot inspect gold evidence, miss categories, or any
    benchmark answer labels; that boundary is what lets source prewarm stay a
    product-shaped path instead of a query-specific oracle.
    """

    source_terms = set(profile.get("source_terms") or set())
    previous_terms = set(profile.get("previous_terms") or set())
    next_terms = set(profile.get("next_terms") or set())
    route_terms = set(profile.get("route_terms") or set())
    labels = set(profile.get("labels") or set())
    context_labels = set(profile.get("context_labels") or set())
    semantic_scope_terms = set(profile.get("semantic_scope_terms") or set())
    factual_alias_terms = set(profile.get("factual_alias_terms") or set())
    answer_bearing_terms = set(profile.get("answer_bearing_terms") or set())
    source_overlap = len(question_terms & source_terms)
    context_overlap = len(question_terms & previous_terms) + len(question_terms & next_terms)
    route_overlap = len(question_terms & route_terms)
    semantic_scope_overlap = len(question_terms & semantic_scope_terms)
    factual_alias_overlap = len(question_terms & factual_alias_terms)
    answer_bearing_overlap = len(question_terms & answer_bearing_terms)
    label_overlap = len(query_labels & labels)
    context_label_overlap = len(query_labels & context_labels)
    coverage = route_overlap / max(1, len(question_terms))
    overlap_signal = (
        route_overlap
        + semantic_scope_overlap
        + factual_alias_overlap
        + answer_bearing_overlap
        + label_overlap
        + context_label_overlap
    )
    if overlap_signal <= 0:
        return 0.0

    score = route_overlap * 80.0
    score += source_overlap * 34.0
    score += context_overlap * 24.0
    score += coverage * 30.0
    score += label_overlap * 18.0
    score += context_label_overlap * 7.0
    score += semantic_scope_overlap * 16.0
    score += factual_alias_overlap * 62.0
    score += answer_bearing_overlap * 14.0
    if str(profile.get("role") or "") == "user":
        score += 3.0
    if "answer_like_statement" in labels:
        score += 8.0
    if "value_like" in labels:
        score += 5.0
    if "question_like" in labels and "answer_like_statement" not in labels:
        score -= 10.0
    if "continuation_bridge" in labels and route_overlap == 0:
        score -= 18.0
    return score


def search_source_semantic_cache(
    question: str,
    cache: dict[str, Any],
    *,
    limit: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    working_rows = [
        row
        for row in (cache.get("working_memory_rows") or [])
        if isinstance(row, dict)
    ]
    profiles: dict[int, dict[str, Any]] = {
        int(line): profile
        for line, profile in (cache.get("profiles") or {}).items()
    }
    if not working_rows and not profiles:
        return {
            "available": False,
            "hits": [],
            "errors": ["empty source worker surface cache"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 4),
        }

    def source_ref_lines(row: dict[str, Any]) -> list[int]:
        lines: list[int] = []
        for ref in row.get("source_refs") or []:
            if not isinstance(ref, dict):
                continue
            raw = ref.get("line") if ref.get("line") is not None else ref.get("source_line")
            try:
                line = int(raw)
            except (TypeError, ValueError):
                continue
            lines.append(line)
        return lines

    matched_rows = match_working_memory(
        question,
        working_rows,
        limit=max(1, int(limit)),
    )
    scored_by_line: dict[int, float] = {}
    for rank, row in enumerate(matched_rows, start=1):
        matched_terms = [str(term) for term in row.get("matched_terms") or []]
        base_score = float(row.get("score") or 0.0) * 10.0
        base_score += len(matched_terms) * 5.0
        base_score += max(0.0, float(row.get("confidence") or 0.0) * 4.0)
        base_score += max(0.0, 4.0 - rank * 0.02)
        for line in source_ref_lines(row):
            scored_by_line[line] = max(scored_by_line.get(line, 0.0), base_score)
    question_terms = lexical_line_reranker_terms(question)
    query_labels = source_semantic_query_labels(question)
    profile_match_count = 0
    factual_alias_query_overlap_count = 0
    for line, profile in profiles.items():
        profile_score = source_semantic_cache_search_score(
            question_terms,
            query_labels,
            profile,
        )
        if profile_score <= 0:
            continue
        profile_match_count += 1
        if question_terms & set(profile.get("factual_alias_terms") or set()):
            factual_alias_query_overlap_count += 1
        scored_by_line[line] = max(scored_by_line.get(line, 0.0), profile_score)
    scored = sorted(scored_by_line.items(), key=lambda item: (-item[1], item[0]))
    hits = [
        {
            "line": int(line),
            "rank_score": round(-score, 6),
            "source_semantic_score": round(score, 6),
        }
        for line, score in scored[: max(1, int(limit))]
    ]
    manifest = cache.get("manifest") or {}
    return {
        "available": True,
        "hits": hits,
        "latency_ms": round((time.perf_counter() - started) * 1000, 4),
        "cache": {
            "available": True,
            "kind": SOURCE_SEMANTIC_CACHE_POLICY_VERSION,
            "source_cache_message_count": int(manifest.get("message_count") or 0),
            "source_cache_span_count": int(manifest.get("span_count") or 0),
            "working_memory_row_count": int(manifest.get("working_memory_row_count") or 0),
            "working_memory_match_count": len(matched_rows),
            "profile_match_count": profile_match_count,
            "factual_alias_query_overlap_count": factual_alias_query_overlap_count,
            "semantic_trigger_projection_count": 0,
            "cache_key_complete_rate": manifest.get("complete_rate"),
            "hot_query_provider_call_count": 0,
        },
    }


def run_source_semantic_cache_line_reranker(
    question: str,
    candidates: list[dict[str, Any]],
    *,
    source_semantic_cache: dict[str, Any] | None = None,
    **_: object,
) -> dict[str, Any]:
    """Rank candidate lines from source-side AIppocampus worker surfaces.

    The hot path receives query text, but it does not call a provider. The cold
    build has already published navigation-only working-memory rows with source
    refs; this stage only reorders candidate lines and still requires source
    reopen before any factual claim.
    """

    started = time.perf_counter()
    if not candidates:
        return {"available": False, "ranked_lines": [], "errors": ["empty candidates"]}
    cache = source_semantic_cache or {}
    profiles: dict[int, dict[str, Any]] = {
        int(line): profile
        for line, profile in (cache.get("profiles") or {}).items()
    }
    question_terms = lexical_line_reranker_terms(question)
    query_labels = source_semantic_query_labels(question)
    scored: list[tuple[float, int, int, int, int]] = []
    hit_count = 0
    miss_count = 0
    semantic_scope_profile_count = 0
    semantic_scope_label_overlap_count = 0
    semantic_scope_label_overlap_total = 0
    semantic_scope_term_profile_count = 0
    semantic_scope_term_overlap_count = 0
    semantic_scope_term_overlap_total = 0
    factual_alias_profile_count = 0
    factual_alias_overlap_count = 0
    factual_alias_overlap_total = 0
    answer_bearing_profile_count = 0
    answer_bearing_overlap_count = 0
    answer_bearing_overlap_total = 0
    for candidate in candidates:
        line = int(candidate["line"])
        profile = profiles.get(line)
        if profile is None:
            miss_count += 1
            profile = {
                "source_terms": set(),
                "previous_terms": set(),
                "next_terms": set(),
                "labels": set(),
                "context_labels": set(),
                "semantic_scope_terms": set(),
                "factual_alias_terms": set(),
                "answer_bearing_terms": set(),
            }
        else:
            hit_count += 1
        semantic_scope_labels = set(profile.get("semantic_scope_labels") or set())
        if semantic_scope_labels:
            semantic_scope_profile_count += 1
            semantic_scope_overlap = query_labels & semantic_scope_labels
            if semantic_scope_overlap:
                semantic_scope_label_overlap_count += 1
                semantic_scope_label_overlap_total += len(semantic_scope_overlap)
        semantic_scope_terms = set(profile.get("semantic_scope_terms") or set())
        if semantic_scope_terms:
            semantic_scope_term_profile_count += 1
            semantic_scope_term_overlap = question_terms & semantic_scope_terms
            if semantic_scope_term_overlap:
                semantic_scope_term_overlap_count += 1
                semantic_scope_term_overlap_total += len(semantic_scope_term_overlap)
        factual_alias_terms = set(profile.get("factual_alias_terms") or set())
        if factual_alias_terms:
            factual_alias_profile_count += 1
            factual_alias_overlap = question_terms & factual_alias_terms
            if factual_alias_overlap:
                factual_alias_overlap_count += 1
                factual_alias_overlap_total += len(factual_alias_overlap)
        answer_bearing_terms = set(profile.get("answer_bearing_terms") or set())
        if answer_bearing_terms:
            answer_bearing_profile_count += 1
            answer_bearing_overlap = question_terms & answer_bearing_terms
            if answer_bearing_overlap:
                answer_bearing_overlap_count += 1
                answer_bearing_overlap_total += len(answer_bearing_overlap)
        scored.append(
            (
                source_semantic_cache_score(
                    question_terms,
                    query_labels,
                    candidate,
                    profile,
                ),
                int(candidate.get("session_rank") or 10**6),
                int(candidate.get("nearest_hit_rank") or 10**6),
                int(candidate.get("context_distance") or 0),
                line,
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3], item[4]))
    lead = scored[0][0] - scored[1][0] if len(scored) > 1 else scored[0][0]
    manifest = cache.get("manifest") or {}
    return {
        "available": True,
        "ranked_lines": [int(item[-1]) for item in scored],
        "confidence": clamp_confidence(0.4 + min(0.4, max(0.0, lead) / 150.0)),
        "usage": {
            "local_scored_candidates": len(candidates),
            "source_semantic_profile_lookups": len(candidates),
            "provider_call_count": 0,
            "provider_total_tokens": 0,
            "hot_query_provider_call_count": 0,
            "semantic_scope_profile_count": semantic_scope_profile_count,
            "semantic_scope_query_label_overlap_count": (
                semantic_scope_label_overlap_count
            ),
            "semantic_scope_query_label_overlap_total": (
                semantic_scope_label_overlap_total
            ),
            "semantic_scope_term_profile_count": semantic_scope_term_profile_count,
            "semantic_scope_query_term_overlap_count": (
                semantic_scope_term_overlap_count
            ),
            "semantic_scope_query_term_overlap_total": (
                semantic_scope_term_overlap_total
            ),
            "factual_alias_profile_count": factual_alias_profile_count,
            "factual_alias_query_overlap_count": factual_alias_overlap_count,
            "factual_alias_query_overlap_total": factual_alias_overlap_total,
            "answer_bearing_profile_count": answer_bearing_profile_count,
            "answer_bearing_query_overlap_count": answer_bearing_overlap_count,
            "answer_bearing_query_overlap_total": answer_bearing_overlap_total,
        },
        "latency_ms": round((time.perf_counter() - started) * 1000, 4),
        "cache": {
            "available": True,
            "kind": SOURCE_SEMANTIC_CACHE_POLICY_VERSION,
            "hit_count": hit_count,
            "miss_count": miss_count,
            "hit_rate": safe_rate(hit_count, hit_count + miss_count),
            "source_cache_message_count": int(manifest.get("message_count") or 0),
            "source_cache_span_count": int(manifest.get("span_count") or 0),
            "working_memory_row_count": int(manifest.get("working_memory_row_count") or 0),
            "cache_key_complete_rate": manifest.get("complete_rate"),
        },
        "metadata": source_semantic_cache_public_contract(),
    }


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
    hit_context_limit: int | None = None,
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
    context_hit_limit = max(1, int(hit_context_limit if hit_context_limit is not None else top_k))
    for channel, channel_hits in hit_lists:
        for hit_rank, hit in enumerate(channel_hits[:context_hit_limit], start=1):
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
        previous_row = row_by_line.get(line - 1)
        next_row = row_by_line.get(line + 1)
        session_id = line_to_session.get(str(line)) or ""
        candidates.append(
            {
                "line": line,
                "role": row.get("role") or "",
                "previous_role": (
                    previous_row.get("role") or ""
                    if previous_row and line_to_session.get(str(line - 1)) == session_id
                    else ""
                ),
                "next_role": (
                    next_row.get("role") or ""
                    if next_row and line_to_session.get(str(line + 1)) == session_id
                    else ""
                ),
                "session_id": session_id,
                "session_rank": session_first_rank.get(session_id, 10**6),
                "fts_rank": hit_rank_by_line.get(line),
                "nearest_hit_rank": int(meta["nearest_hit_rank"]),
                "nearest_hit_line": int(meta["nearest_hit_line"]),
                "context_distance": int(meta["context_distance"]),
                "query_channels": sorted(str(item) for item in meta["query_channels"]),
                "text": str(row.get("text") or ""),
                "previous_text": (
                    str(previous_row.get("text") or "")
                    if previous_row and line_to_session.get(str(line - 1)) == session_id
                    else ""
                ),
                "next_text": (
                    str(next_row.get("text") or "")
                    if next_row and line_to_session.get(str(line + 1)) == session_id
                    else ""
                ),
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


def _positive_rank(value: Any) -> int | None:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return None
    return rank if rank > 0 else None


def source_window_coverage_diagnostic(
    rows: list[dict[str, Any]],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Return sanitized coverage diagnostics for source-window/candidate misses.

    Candidate rows remain navigation routes. This report intentionally avoids
    source text, answer text, and case ids; it only separates first-stage misses
    from candidate-packaging and line-selection misses so later agents do not
    chase online reranking when the gold line was never in the candidate pack.
    """

    fused_miss_count = 0
    candidate_missing = 0
    reranker_visible = 0
    candidate_coverage = 0
    factual_alias_candidate_lift = 0
    factual_alias_fused_lift = 0
    factual_alias_candidate_missing_miss = 0
    factual_alias_reranker_visible_miss = 0
    fused_regression_count = 0
    miss_family_counts: dict[str, int] = {}
    reranker_attempted_count = 0
    for row in rows:
        evidence_rank = _positive_rank(row.get("evidence_rank"))
        reranked_rank = _positive_rank(row.get("reranked_evidence_rank")) or evidence_rank
        baseline_hit = bool(evidence_rank and evidence_rank <= top_k)
        fused_hit = bool(reranked_rank and reranked_rank <= top_k)
        factual_alias_candidate_contains = bool(
            row.get("source_semantic_factual_alias_candidate_evidence_contains")
        )
        if baseline_hit and not fused_hit:
            fused_regression_count += 1
        if not baseline_hit and factual_alias_candidate_contains:
            factual_alias_candidate_lift += 1
            if fused_hit:
                factual_alias_fused_lift += 1
        if row.get("line_reranker_attempted"):
            reranker_attempted_count += 1
            if row.get("line_reranker_candidate_contains_evidence"):
                candidate_coverage += 1
        if not reranked_rank or reranked_rank > top_k:
            fused_miss_count += 1
            if row.get("line_reranker_attempted"):
                if row.get("line_reranker_candidate_contains_evidence"):
                    reranker_visible += 1
                    if factual_alias_candidate_contains:
                        factual_alias_reranker_visible_miss += 1
                else:
                    candidate_missing += 1
                    if int(row.get("source_semantic_factual_alias_line_count") or 0) > 0:
                        factual_alias_candidate_missing_miss += 1
            if row.get(f"same_session_wrong_line_top{top_k}"):
                miss_family_counts["same_session_wrong_line_top_k"] = (
                    miss_family_counts.get("same_session_wrong_line_top_k", 0) + 1
                )
            if row.get("session_found_below_top_k"):
                miss_family_counts["session_found_below_top_k"] = (
                    miss_family_counts.get("session_found_below_top_k", 0) + 1
                )
            rank = (
                _positive_rank(row.get("source_joined_candidate_evidence_rank"))
                or evidence_rank
            )
            if rank is None:
                miss_family_counts["gold_line_not_retrieved"] = (
                    miss_family_counts.get("gold_line_not_retrieved", 0) + 1
                )
            elif 21 <= rank <= 50:
                miss_family_counts["gold_line_low_rank_21_50"] = (
                    miss_family_counts.get("gold_line_low_rank_21_50", 0) + 1
                )
            elif rank > 50:
                miss_family_counts["gold_line_rank_below_50"] = (
                    miss_family_counts.get("gold_line_rank_below_50", 0) + 1
                )
    return {
        "status": "measured_from_sanitized_rows",
        "top_k": int(top_k),
        "evidence_line_case_count": len(rows),
        "reranker_attempted_count": reranker_attempted_count,
        "fused_miss_count": fused_miss_count,
        "candidate_missing_miss_count": candidate_missing,
        "reranker_visible_miss_count": reranker_visible,
        "factual_alias_candidate_lift_count": factual_alias_candidate_lift,
        "factual_alias_fused_lift_count": factual_alias_fused_lift,
        "factual_alias_candidate_missing_miss_count": factual_alias_candidate_missing_miss,
        "factual_alias_reranker_visible_miss_count": factual_alias_reranker_visible_miss,
        "fused_regression_count": fused_regression_count,
        "miss_family_counts": dict(sorted(miss_family_counts.items())),
        "line_reranker_candidate_evidence_coverage": {
            "numerator": candidate_coverage,
            "denominator": reranker_attempted_count,
            "rate": safe_rate(candidate_coverage, reranker_attempted_count),
        },
        "candidate_rows_are_routes_not_claims": True,
        "foreground_window_growth_policy": "bounded_candidate_routes_only",
        "raw_text_emitted": False,
    }


def standard_line_reranker_candidate_pack_sha1(
    candidates: list[dict[str, Any]],
) -> str:
    """Hash the source-window candidate pack without serializing source text.

    Query/candidate caches must invalidate when the actual source spans change,
    not merely when candidate counts stay the same. Keep the raw text out of
    reports, but include text hashes plus line/routing metadata in the pack
    digest so warm-cache readouts can distinguish real candidate windows from
    weaker source-id/count surrogates.
    """

    material = []
    for candidate in candidates:
        material.append(
            {
                "line": int(candidate.get("line") or 0),
                "role": str(candidate.get("role") or ""),
                "session_rank": candidate.get("session_rank"),
                "nearest_hit_rank": candidate.get("nearest_hit_rank"),
                "context_distance": candidate.get("context_distance"),
                "query_channels": sorted(
                    str(channel) for channel in (candidate.get("query_channels") or [])
                ),
                "text_sha1": sha1_text(str(candidate.get("text") or ""))[:16],
                "previous_text_sha1": sha1_text(
                    str(candidate.get("previous_text") or "")
                )[:16],
                "next_text_sha1": sha1_text(str(candidate.get("next_text") or ""))[:16],
            }
        )
    return sha1_text(json.dumps(material, ensure_ascii=False, sort_keys=True))[:16]


def semantic_line_reranker_available(api_key_env: str = "DEEPSEEK_API_KEY") -> bool:
    return bool(os.environ.get(api_key_env))


def semantic_line_reranker_provider(*, model: str, base_url: str) -> str:
    text = " ".join([model, base_url]).casefold()
    return "deepseek" if "deepseek" in text else "openai_compatible"


def semantic_line_reranker_cache_contract(provider: str) -> str:
    return (
        DEEPSEEK_PREFIX_CACHE_CONTRACT
        if provider == "deepseek"
        else NO_PROVIDER_CACHE_CONTRACT
    )


def semantic_line_reranker_cache_metrics(
    usage: dict[str, Any],
    *,
    provider: str,
) -> dict[str, Any]:
    kind = semantic_line_reranker_cache_contract(provider)
    if kind == DEEPSEEK_PREFIX_CACHE_CONTRACT:
        result = deepseek_cache_metrics_from_usage(usage)
        result["kind"] = kind
        return result
    return {"available": False, "kind": kind}


def summarize_line_reranker_latency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(row["line_reranker_latency_ms"])
        for row in rows
        if isinstance(row.get("line_reranker_latency_ms"), int | float)
    ]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "max": round(max(values), 2),
    }


def summarize_numeric_latency(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [
        float(row[key])
        for row in rows
        if isinstance(row.get(key), int | float)
    ]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 4),
        "max": round(max(values), 4),
    }


def summarize_line_reranker_cache(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kind_counts: dict[str, int] = {}
    available_count = 0
    hit_tokens = 0
    miss_tokens = 0
    hit_count = 0
    miss_count = 0
    for row in rows:
        cache = row.get("line_reranker_cache")
        if not isinstance(cache, dict) or not cache:
            continue
        kind = str(cache.get("kind") or "unknown")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if cache.get("available"):
            available_count += 1
        hit_tokens += int(cache.get("hit_tokens") or 0)
        miss_tokens += int(cache.get("miss_tokens") or 0)
        hit_count += int(cache.get("hit_count") or 0)
        miss_count += int(cache.get("miss_count") or 0)
    total = hit_tokens + miss_tokens
    local_total = hit_count + miss_count
    return {
        "available_count": available_count,
        "kind_counts": kind_counts,
        "hit_tokens": hit_tokens,
        "miss_tokens": miss_tokens,
        "hit_rate": round(hit_tokens / total, 4) if total else 0.0,
        "profile_hit_count": hit_count,
        "profile_miss_count": miss_count,
        "profile_hit_rate": round(hit_count / local_total, 4) if local_total else 0.0,
    }


def summarize_line_reranker_metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    variants: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        metadata = row.get("line_reranker_metadata")
        if not isinstance(metadata, dict):
            continue
        key = json.dumps(metadata, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        variants.append(metadata)
    if not variants:
        return {}
    first = variants[0]
    if len(variants) == 1:
        return first
    return {
        "variant_count": len(variants),
        "variants": variants,
    }


def semantic_line_reranker_public_contract(
    *,
    api_key_env: str = "DEEPSEEK_API_KEY",
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    resolved_model = model or os.environ.get("AIPPOCAMPUS_LINE_RERANKER_MODEL") or DEFAULT_MODEL
    resolved_base_url = (
        base_url or os.environ.get("AIPPOCAMPUS_LINE_RERANKER_BASE_URL") or DEFAULT_BASE_URL
    )
    provider = semantic_line_reranker_provider(
        model=resolved_model,
        base_url=resolved_base_url,
    )
    return {
        "arm": SEMANTIC_LINE_RERANKER_ARM,
        "prompt_version": SEMANTIC_LINE_RERANKER_PROMPT_VERSION,
        "provider": provider,
        "model": resolved_model,
        "base_url_sha1": sha1_text(resolved_base_url)[:16],
        "api_key_env": api_key_env,
        "cache_contract": semantic_line_reranker_cache_contract(provider),
        "timeout": int(timeout),
        "max_tokens": None if max_tokens is None or int(max_tokens) <= 0 else int(max_tokens),
        "temperature": 0.0,
        "cost_status": "provider_cost_not_reported",
        "tracked_cost_fields": ["usage", "latency_ms", "cache"],
        "input_boundary": {
            "visible_to_model": [
                "question_text",
                "candidate_line_number",
                "candidate_role",
                "candidate_session_rank",
                "candidate_nearest_hit_rank",
                "candidate_context_distance",
                "candidate_source_text",
            ],
            "withheld_from_model": [
                "gold_answer",
                "expected_lines",
                "expected_sessions",
                "has_answer_labels",
                "judge_labels",
                "miss_taxonomy",
                "raw_report_cases",
            ],
        },
        "output_boundary": {
            "ranked_lines_filtered_to_candidate_set": True,
            "question_answering_allowed": False,
            "raw_model_response_persisted": False,
        },
    }


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
            "prompt_version": SEMANTIC_LINE_RERANKER_PROMPT_VERSION,
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
    contract = semantic_line_reranker_public_contract(
        api_key_env=api_key_env,
        model=model,
        base_url=base_url,
        timeout=timeout,
        max_tokens=max_tokens,
    )
    api_key = os.environ.get(api_key_env)
    if not api_key:
        return {
            "available": False,
            "ranked_lines": [],
            "errors": ["missing semantic line-reranker api key"],
            "metadata": contract,
        }
    if not candidates:
        return {
            "available": False,
            "ranked_lines": [],
            "errors": ["empty candidates"],
            "metadata": contract,
        }
    resolved_model = str(contract["model"])
    resolved_base_url = (
        base_url or os.environ.get("AIPPOCAMPUS_LINE_RERANKER_BASE_URL") or DEFAULT_BASE_URL
    )
    started = time.perf_counter()
    response = call_chat_json(
        semantic_line_reranker_messages(question=question, candidates=candidates),
        api_key,
        resolved_model,
        resolved_base_url,
        None if max_tokens is None or int(max_tokens) <= 0 else int(max_tokens),
        int(timeout),
        0.0,
        service_name=(
            "DeepSeek line reranker API"
            if contract["provider"] == "deepseek"
            else "OpenAI-compatible line reranker API"
        ),
        cache_contract=str(contract["cache_contract"]),
    )
    parsed = parse_model_json(response)
    usage = compact_usage(response.get("usage") or {})
    return {
        "available": True,
        "ranked_lines": parsed.get("ranked_lines") or [],
        "confidence": clamp_confidence(parsed.get("confidence")),
        "usage": usage,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "cache": semantic_line_reranker_cache_metrics(
            usage,
            provider=str(contract["provider"]),
        ),
        "metadata": contract,
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
    source_semantic_cache_store: SourceSemanticCacheStore | None = None,
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
    evidence_hit_top_k = bool(evidence_rank and evidence_rank <= top_k)
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
    expected_lines_found_top_k = len(expected_lines & hit_lines(hits, limit=top_k))
    expected_lines_found_all_rank = len(expected_lines & hit_lines(hits))
    nearest_context_distance_top_k = nearest_expected_line_distance(
        hits,
        expected_lines=expected_lines,
        line_to_session=line_to_session,
        limit=top_k,
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
        "evidence_rank_bucket": evidence_rank_bucket(evidence_rank),
        f"evidence_hit_top{top_k}": evidence_hit_top_k,
        "evidence_context_rank": evidence_context_rank,
        f"evidence_context_hit_top{top_k}": bool(
            evidence_context_rank and evidence_context_rank <= top_k
        ),
        f"expected_lines_found_top{top_k}": expected_lines_found_top_k,
        "expected_lines_found_all_rank": expected_lines_found_all_rank,
        f"multi_evidence_partial_hit_top{top_k}": bool(
            len(expected_lines) > 1 and 0 < expected_lines_found_top_k < len(expected_lines)
        ),
        f"same_session_wrong_line_top{top_k}": bool(
            session_rank and session_rank <= top_k and not evidence_hit_top_k
        ),
        f"evidence_context_rescue_top{top_k}": bool(
            evidence_context_rank
            and evidence_context_rank <= top_k
            and not evidence_hit_top_k
        ),
        f"gold_line_near_miss_top{top_k}_to_20": bool(
            evidence_rank and top_k < evidence_rank <= 20
        ),
        f"evidence_context_distance_bucket_top{top_k}": (
            evidence_context_distance_bucket(
                nearest_context_distance_top_k,
                context_radius=context_radius,
            )
        ),
        "session_rank": session_rank,
        f"session_hit_top{top_k}": bool(session_rank and session_rank <= top_k),
        "warning_count": len(warnings),
    }
    row["evidence_miss_category"] = evidence_miss_category(row, top_k=top_k)
    resolved_reranker_mode = line_reranker_mode.strip().casefold()
    if resolved_reranker_mode not in STANDARD_LINE_RERANKER_MODES:
        raise ValueError(f"unsupported line reranker mode: {line_reranker_mode}")
    if resolved_reranker_mode != "off":
        content_hits: list[dict[str, Any]] = []
        source_semantic_cache: dict[str, Any] | None = None
        source_semantic_cache_hits: list[dict[str, Any]] = []
        source_semantic_search_payload: dict[str, Any] = {}
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
        if resolved_reranker_mode == "source_semantic_cache":
            cache_store = source_semantic_cache_store or SourceSemanticCacheStore()
            source_semantic_cache = cache_store.get(
                Path(case["sqlite_path"]),
                line_to_session=line_to_session,
            )
            source_semantic_search_payload = search_source_semantic_cache(
                str(case.get("query") or ""),
                source_semantic_cache,
                limit=max(top_k, candidate_limit),
            )
            source_semantic_cache_hits = [
                dict(hit)
                for hit in (source_semantic_search_payload.get("hits") or [])
                if isinstance(hit, dict)
            ]
        extra_hit_lists: list[tuple[str, list[dict[str, Any]]]] = []
        if content_hits:
            extra_hit_lists.append(("content", content_hits))
        if source_semantic_cache_hits:
            extra_hit_lists.append(("source_semantic_cache", source_semantic_cache_hits))
        candidates = build_standard_line_reranker_candidates(
            case["sqlite_path"],
            hits,
            extra_hit_lists=extra_hit_lists or None,
            line_to_session=line_to_session,
            top_k=top_k,
            context_radius=context_radius,
            top_sessions=line_reranker_top_sessions,
            max_candidates=line_reranker_max_candidates,
            hit_context_limit=(
                max(top_k, candidate_limit)
                if resolved_reranker_mode == "source_semantic_cache"
                else None
            ),
        )
        semantic_lines: list[int] = []
        reranker_payload: dict[str, Any] = {}
        reranker_errors: list[str] = []
        reranker_metadata: dict[str, Any] = (
            semantic_line_reranker_public_contract(
                timeout=line_reranker_timeout,
                max_tokens=line_reranker_max_tokens,
            )
            if resolved_reranker_mode == "semantic" and line_reranker_fn is None
            else {}
        )
        source_joined_candidate_rank = rank_expected_line(candidates, expected_lines)
        source_joined_candidate_contains_evidence = bool(
            expected_lines & {int(candidate["line"]) for candidate in candidates}
        )
        candidate_pack_sha1 = standard_line_reranker_candidate_pack_sha1(candidates)
        try:
            if line_reranker_fn is not None:
                runner = line_reranker_fn
            elif resolved_reranker_mode == "lexical":
                runner = run_lexical_line_reranker
            elif resolved_reranker_mode == "structural":
                runner = run_structural_line_reranker
            elif resolved_reranker_mode == "source_semantic_cache":
                runner = run_source_semantic_cache_line_reranker
            else:
                runner = run_semantic_line_reranker
            runner_kwargs = {
                "timeout": line_reranker_timeout,
                "max_tokens": line_reranker_max_tokens,
            }
            if resolved_reranker_mode == "source_semantic_cache":
                runner_kwargs["source_semantic_cache"] = source_semantic_cache
            reranker_payload = runner(
                str(case.get("query") or ""),
                candidates,
                **runner_kwargs,
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
        semantic_only_full_rank = rank_expected_line(
            [{"line": line} for line in semantic_lines],
            expected_lines,
        )
        semantic_only_hit_top_k = bool(semantic_only_rank and semantic_only_rank <= top_k)
        wrong_stance_lines = {
            int(value) for value in expected.get("wrong_stance_lines") or []
        }
        wrong_stance_semantic_rank = rank_expected_line(
            [{"line": line} for line in semantic_lines],
            wrong_stance_lines,
        )
        wrong_stance_ranked_above_evidence = bool(
            wrong_stance_semantic_rank
            and (
                not semantic_only_rank
                or int(wrong_stance_semantic_rank) < int(semantic_only_rank)
            )
        )
        # Issue #309 measures whether an auxiliary source-joined route rescues a
        # top-k lexical miss. This stays diagnostic: candidates are source rows,
        # not user-visible evidence, until the owning path reopens clean source.
        semantic_bridge_lift = bool(
            not evidence_hit_top_k
            and semantic_only_hit_top_k
            and source_joined_candidate_contains_evidence
        )
        # Product-facing second stage is FTS-preserving: semantic ranking can
        # promote exact source rows inside the top-session/top-context boundary,
        # but it should not hide a row already surfaced by first-stage FTS. Keep
        # semantic-only metrics separate so regressions remain visible.
        reranked_rank = best_rank(evidence_rank, semantic_only_rank)
        source_semantic_cache_rank = rank_expected_line(
            source_semantic_cache_hits,
            expected_lines,
        ) if source_semantic_cache_hits else None
        source_semantic_cache_hit_top_k = bool(
            source_semantic_cache_rank and source_semantic_cache_rank <= top_k
        )
        semantic_scope_profile_lines: set[int] = set()
        if source_semantic_cache:
            for raw_line, profile in (source_semantic_cache.get("profiles") or {}).items():
                if not isinstance(profile, dict):
                    continue
                if not profile.get("semantic_scope_labels"):
                    continue
                try:
                    semantic_scope_profile_lines.add(int(raw_line))
                except (TypeError, ValueError):
                    continue
        semantic_scope_profile_hits = [
            {"line": line} for line in sorted(semantic_scope_profile_lines)
        ]
        semantic_scope_sidecar_evidence_rank = rank_expected_line(
            semantic_scope_profile_hits,
            expected_lines,
        )
        semantic_scope_sidecar_context_rank = rank_expected_line_context(
            semantic_scope_profile_hits,
            expected_lines=expected_lines,
            line_to_session=line_to_session,
            radius=context_radius,
        )
        semantic_scope_candidate_lines = {
            int(candidate["line"])
            for candidate in candidates
            if int(candidate["line"]) in semantic_scope_profile_lines
        }
        candidate_evidence_lines = {
            int(candidate["line"])
            for candidate in candidates
            if int(candidate["line"]) in expected_lines
        }
        semantic_scope_gold_candidate_label_count = 0
        semantic_scope_gold_candidate_term_count = 0
        semantic_scope_gold_candidate_query_term_overlap_count = 0
        if source_semantic_cache and candidate_evidence_lines:
            question_terms = lexical_line_reranker_terms(str(case.get("query") or ""))
            source_profiles = source_semantic_cache.get("profiles") or {}
            for line in sorted(candidate_evidence_lines):
                profile = source_profiles.get(line) or source_profiles.get(str(line)) or {}
                if not isinstance(profile, dict):
                    continue
                if profile.get("semantic_scope_labels"):
                    semantic_scope_gold_candidate_label_count += 1
                semantic_scope_terms = set(profile.get("semantic_scope_terms") or set())
                if semantic_scope_terms:
                    semantic_scope_gold_candidate_term_count += 1
                    if question_terms & semantic_scope_terms:
                        semantic_scope_gold_candidate_query_term_overlap_count += 1
        semantic_scope_candidate_hits = [
            {"line": line} for line in sorted(semantic_scope_candidate_lines)
        ]
        semantic_scope_candidate_evidence_rank = rank_expected_line(
            semantic_scope_candidate_hits,
            expected_lines,
        )
        factual_alias_profile_lines: set[int] = set()
        factual_alias_query_overlap_lines: set[int] = set()
        answer_bearing_profile_lines: set[int] = set()
        factual_gold_candidate_alias_count = 0
        factual_gold_candidate_query_overlap_count = 0
        factual_gold_candidate_answer_bearing_count = 0
        if source_semantic_cache:
            question_terms = lexical_line_reranker_terms(str(case.get("query") or ""))
            for raw_line, profile in (source_semantic_cache.get("profiles") or {}).items():
                if not isinstance(profile, dict):
                    continue
                try:
                    line = int(raw_line)
                except (TypeError, ValueError):
                    continue
                factual_alias_terms = set(profile.get("factual_alias_terms") or set())
                answer_bearing_terms = set(profile.get("answer_bearing_terms") or set())
                if factual_alias_terms:
                    factual_alias_profile_lines.add(line)
                    if question_terms & factual_alias_terms:
                        factual_alias_query_overlap_lines.add(line)
                if answer_bearing_terms:
                    answer_bearing_profile_lines.add(line)
                if line not in candidate_evidence_lines:
                    continue
                if factual_alias_terms:
                    factual_gold_candidate_alias_count += 1
                    if question_terms & factual_alias_terms:
                        factual_gold_candidate_query_overlap_count += 1
                if answer_bearing_terms:
                    factual_gold_candidate_answer_bearing_count += 1
        factual_alias_profile_hits = [
            {"line": line} for line in sorted(factual_alias_profile_lines)
        ]
        factual_alias_query_overlap_hits = [
            {"line": line} for line in sorted(factual_alias_query_overlap_lines)
        ]
        answer_bearing_profile_hits = [
            {"line": line} for line in sorted(answer_bearing_profile_lines)
        ]
        factual_alias_candidate_lines = {
            int(candidate["line"])
            for candidate in candidates
            if int(candidate["line"]) in factual_alias_profile_lines
        }
        factual_alias_candidate_hits = [
            {"line": line} for line in sorted(factual_alias_candidate_lines)
        ]
        row.update(
            {
                "line_reranker_mode": resolved_reranker_mode,
                "line_reranker_attempted": True,
                "line_reranker_available": bool(reranker_payload.get("available")),
                "line_reranker_candidate_count": len(candidates),
                "line_reranker_candidate_pack_sha1": candidate_pack_sha1,
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
                "line_reranker_latency_ms": reranker_payload.get("latency_ms"),
                "line_reranker_cache": reranker_payload.get("cache") or {},
                "line_reranker_metadata": (
                    reranker_payload.get("metadata") or reranker_metadata
                ),
                "source_semantic_cache_search_available": bool(
                    source_semantic_search_payload.get("available")
                ),
                "source_semantic_cache_hit_count": len(source_semantic_cache_hits),
                "source_semantic_cache_latency_ms": source_semantic_search_payload.get(
                    "latency_ms"
                ),
                "source_semantic_cache_evidence_rank": source_semantic_cache_rank,
                f"source_semantic_cache_evidence_hit_top{top_k}": (
                    source_semantic_cache_hit_top_k
                ),
                "source_semantic_cache_hot_path": (
                    source_semantic_search_payload.get("cache") or {}
                ),
                "source_semantic_scope_sidecar_line_count": (
                    len(semantic_scope_profile_lines)
                ),
                "source_semantic_scope_sidecar_evidence_rank": (
                    semantic_scope_sidecar_evidence_rank
                ),
                "source_semantic_scope_sidecar_evidence_contains": bool(
                    semantic_scope_sidecar_evidence_rank
                ),
                "source_semantic_scope_sidecar_context_rank": (
                    semantic_scope_sidecar_context_rank
                ),
                "source_semantic_scope_sidecar_context_contains": bool(
                    semantic_scope_sidecar_context_rank
                ),
                "source_semantic_scope_sidecar_candidate_line_count": (
                    len(semantic_scope_candidate_lines)
                ),
                "source_semantic_scope_sidecar_candidate_evidence_rank": (
                    semantic_scope_candidate_evidence_rank
                ),
                "source_semantic_scope_sidecar_candidate_evidence_contains": bool(
                    semantic_scope_candidate_evidence_rank
                ),
                "source_semantic_scope_gold_candidate_label_count": (
                    semantic_scope_gold_candidate_label_count
                ),
                "source_semantic_scope_gold_candidate_term_count": (
                    semantic_scope_gold_candidate_term_count
                ),
                "source_semantic_scope_gold_candidate_query_term_overlap_count": (
                    semantic_scope_gold_candidate_query_term_overlap_count
                ),
                "source_semantic_factual_alias_line_count": len(
                    factual_alias_profile_lines
                ),
                "source_semantic_factual_alias_evidence_rank": rank_expected_line(
                    factual_alias_profile_hits,
                    expected_lines,
                ),
                "source_semantic_factual_alias_evidence_contains": bool(
                    rank_expected_line(factual_alias_profile_hits, expected_lines)
                ),
                "source_semantic_factual_alias_query_overlap_line_count": len(
                    factual_alias_query_overlap_lines
                ),
                "source_semantic_factual_alias_query_overlap_evidence_rank": (
                    rank_expected_line(factual_alias_query_overlap_hits, expected_lines)
                ),
                "source_semantic_answer_bearing_line_count": len(
                    answer_bearing_profile_lines
                ),
                "source_semantic_answer_bearing_evidence_rank": rank_expected_line(
                    answer_bearing_profile_hits,
                    expected_lines,
                ),
                "source_semantic_factual_alias_candidate_line_count": len(
                    factual_alias_candidate_lines
                ),
                "source_semantic_factual_alias_candidate_evidence_rank": (
                    rank_expected_line(factual_alias_candidate_hits, expected_lines)
                ),
                "source_semantic_factual_alias_candidate_evidence_contains": bool(
                    rank_expected_line(factual_alias_candidate_hits, expected_lines)
                ),
                "source_semantic_factual_gold_candidate_alias_count": (
                    factual_gold_candidate_alias_count
                ),
                "source_semantic_factual_gold_candidate_query_overlap_count": (
                    factual_gold_candidate_query_overlap_count
                ),
                "source_semantic_factual_gold_candidate_answer_bearing_count": (
                    factual_gold_candidate_answer_bearing_count
                ),
                "source_joined_candidate_contains_evidence": (
                    source_joined_candidate_contains_evidence
                ),
                "source_joined_candidate_evidence_rank": source_joined_candidate_rank,
                "semantic_only_evidence_rank": semantic_only_rank,
                "semantic_only_evidence_full_rank": semantic_only_full_rank,
                f"semantic_only_evidence_hit_top{top_k}": semantic_only_hit_top_k,
                f"semantic_bridge_lift_top{top_k}": semantic_bridge_lift,
                "wrong_stance_line_count": len(wrong_stance_lines),
                "wrong_stance_semantic_rank": wrong_stance_semantic_rank,
                "wrong_stance_ranked_above_evidence": wrong_stance_ranked_above_evidence,
                f"wrong_stance_rerank_top{top_k}": bool(
                    wrong_stance_ranked_above_evidence
                    and wrong_stance_semantic_rank
                    and int(wrong_stance_semantic_rank) <= top_k
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
    diagnostic_cutoffs = sorted({*EVIDENCE_DIAGNOSTIC_CUTOFFS, int(top_k)})
    evidence_recall_by_k: dict[str, dict[str, Any]] = {}
    evidence_rank_bucket_counts: dict[str, int] = {}
    evidence_line_taxonomy_counts: dict[str, int] = {}
    evidence_miss_taxonomy_counts: dict[str, int] = {}
    context_rescue_distance_counts: dict[str, int] = {}
    for row in line_cases:
        bucket = str(row.get("evidence_rank_bucket") or "not_retrieved")
        evidence_rank_bucket_counts[bucket] = evidence_rank_bucket_counts.get(bucket, 0) + 1
        line_category = str(row.get("evidence_miss_category") or "unknown")
        evidence_line_taxonomy_counts[line_category] = (
            evidence_line_taxonomy_counts.get(line_category, 0) + 1
        )
        if not row.get(f"evidence_hit_top{top_k}"):
            evidence_miss_taxonomy_counts[line_category] = (
                evidence_miss_taxonomy_counts.get(line_category, 0) + 1
            )
        if row.get(f"evidence_context_rescue_top{top_k}"):
            distance_bucket = str(
                row.get(f"evidence_context_distance_bucket_top{top_k}") or "unknown"
            )
            context_rescue_distance_counts[distance_bucket] = (
                context_rescue_distance_counts.get(distance_bucket, 0) + 1
            )
    for cutoff in diagnostic_cutoffs:
        hits = sum(
            1
            for row in line_cases
            if row.get("evidence_rank") and int(row["evidence_rank"]) <= cutoff
        )
        evidence_recall_by_k[str(cutoff)] = {
            "hit": hits,
            "miss": len(line_cases) - hits,
            "hit_rate": safe_rate(hits, len(line_cases)),
        }
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
        "evidence_line_recall_by_k": evidence_recall_by_k,
        "evidence_rank_bucket_counts": evidence_rank_bucket_counts,
        "evidence_line_taxonomy_counts": evidence_line_taxonomy_counts,
        "evidence_miss_taxonomy_counts": evidence_miss_taxonomy_counts,
        f"evidence_context_rescue_distance_counts_top{top_k}": (
            context_rescue_distance_counts
        ),
        f"same_session_wrong_line_top{top_k}": sum(
            1 for row in line_cases if row.get(f"same_session_wrong_line_top{top_k}")
        ),
        f"multi_evidence_partial_hit_top{top_k}": sum(
            1
            for row in line_cases
            if row.get(f"multi_evidence_partial_hit_top{top_k}")
        ),
        f"gold_line_near_miss_top{top_k}_to_20": sum(
            1 for row in line_cases if row.get(f"gold_line_near_miss_top{top_k}_to_20")
        ),
        "source_window_coverage_diagnostic": source_window_coverage_diagnostic(
            line_cases,
            top_k=top_k,
        ),
        "warning_count": sum(int(row.get("warning_count") or 0) for row in results),
    }
    for cutoff_label, recall in evidence_recall_by_k.items():
        metrics[f"evidence_hit_top{cutoff_label}"] = recall["hit"]
        metrics[f"evidence_miss_top{cutoff_label}"] = recall["miss"]
        metrics[f"evidence_hit_rate_top{cutoff_label}"] = recall["hit_rate"]
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
        source_joined_candidate_coverage = sum(
            1
            for row in reranker_cases
            if row.get("source_joined_candidate_contains_evidence")
        )
        semantic_bridge_lifts = sum(
            1 for row in reranker_cases if row.get(f"semantic_bridge_lift_top{top_k}")
        )
        wrong_stance_cases = [
            row
            for row in reranker_cases
            if int(row.get("wrong_stance_line_count") or 0) > 0
        ]
        wrong_stance_reranks = sum(
            1
            for row in wrong_stance_cases
            if row.get(f"wrong_stance_rerank_top{top_k}")
        )
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
        source_semantic_cache_cases = [
            row
            for row in reranker_cases
            if row.get("line_reranker_mode") == "source_semantic_cache"
        ]
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
                "source_joined_candidate_evidence_coverage": (
                    source_joined_candidate_coverage
                ),
                "source_joined_candidate_evidence_coverage_rate": safe_rate(
                    source_joined_candidate_coverage,
                    len(reranker_cases),
                ),
                "line_reranker_usage": compact_usage(reranker_usage),
                "line_reranker_latency_ms": summarize_line_reranker_latency(
                    reranker_cases
                ),
                "line_reranker_cache": summarize_line_reranker_cache(reranker_cases),
                "line_reranker_metadata": summarize_line_reranker_metadata(
                    reranker_cases
                ),
                f"semantic_only_evidence_hit_top{top_k}": semantic_only_hits,
                f"semantic_only_evidence_miss_top{top_k}": len(reranker_cases)
                - semantic_only_hits,
                f"semantic_only_evidence_hit_rate_top{top_k}": safe_rate(
                    semantic_only_hits,
                    len(reranker_cases),
                ),
                "semantic_only_evidence_mrr": semantic_only_mrr,
                "semantic_only_evidence_mrr_delta": round(semantic_only_mrr - evidence_mrr, 4),
                f"semantic_bridge_lift_top{top_k}": semantic_bridge_lifts,
                f"semantic_bridge_lift_rate_top{top_k}": safe_rate(
                    semantic_bridge_lifts,
                    len(reranker_cases),
                ),
                "wrong_stance_control_case_count": len(wrong_stance_cases),
                f"wrong_stance_rerank_top{top_k}": wrong_stance_reranks,
                f"wrong_stance_rerank_rate_top{top_k}": safe_rate(
                    wrong_stance_reranks,
                    len(wrong_stance_cases),
                ),
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
        if source_semantic_cache_cases:
            source_search_hits = sum(
                1
                for row in source_semantic_cache_cases
                if row.get(f"source_semantic_cache_evidence_hit_top{top_k}")
            )
            source_only_hits = sum(
                1
                for row in source_semantic_cache_cases
                if row.get(f"semantic_only_evidence_hit_top{top_k}")
            )
            source_fused_hits = sum(
                1
                for row in source_semantic_cache_cases
                if row.get(f"reranked_evidence_hit_top{top_k}")
            )
            source_search_mrr = round(
                sum(
                    reciprocal_rank(row.get("source_semantic_cache_evidence_rank"))
                    for row in source_semantic_cache_cases
                )
                / len(source_semantic_cache_cases),
                4,
            )
            source_only_mrr = round(
                sum(
                    reciprocal_rank(row.get("semantic_only_evidence_rank"))
                    for row in source_semantic_cache_cases
                )
                / len(source_semantic_cache_cases),
                4,
            )
            source_fused_mrr = round(
                sum(
                    reciprocal_rank(row.get("reranked_evidence_rank"))
                    for row in source_semantic_cache_cases
                )
                / len(source_semantic_cache_cases),
                4,
            )
            source_scope_sidecar_case_count = sum(
                1
                for row in source_semantic_cache_cases
                if int(row.get("source_semantic_scope_sidecar_line_count") or 0) > 0
            )
            source_scope_sidecar_evidence_coverage = sum(
                1
                for row in source_semantic_cache_cases
                if row.get("source_semantic_scope_sidecar_evidence_contains")
            )
            source_scope_sidecar_context_coverage = sum(
                1
                for row in source_semantic_cache_cases
                if row.get("source_semantic_scope_sidecar_context_contains")
            )
            source_scope_sidecar_candidate_evidence_coverage = sum(
                1
                for row in source_semantic_cache_cases
                if row.get("source_semantic_scope_sidecar_candidate_evidence_contains")
            )
            source_scope_gold_candidate_label_cases = sum(
                1
                for row in source_semantic_cache_cases
                if int(row.get("source_semantic_scope_gold_candidate_label_count") or 0)
                > 0
            )
            source_scope_gold_candidate_term_cases = sum(
                1
                for row in source_semantic_cache_cases
                if int(row.get("source_semantic_scope_gold_candidate_term_count") or 0)
                > 0
            )
            source_scope_gold_candidate_query_overlap_cases = sum(
                1
                for row in source_semantic_cache_cases
                if int(
                    row.get(
                        "source_semantic_scope_gold_candidate_query_term_overlap_count"
                    )
                    or 0
                )
                > 0
            )
            source_factual_alias_case_count = sum(
                1
                for row in source_semantic_cache_cases
                if int(row.get("source_semantic_factual_alias_line_count") or 0) > 0
            )
            source_factual_alias_evidence_coverage = sum(
                1
                for row in source_semantic_cache_cases
                if row.get("source_semantic_factual_alias_evidence_contains")
            )
            source_factual_alias_candidate_evidence_coverage = sum(
                1
                for row in source_semantic_cache_cases
                if row.get("source_semantic_factual_alias_candidate_evidence_contains")
            )
            source_factual_gold_candidate_alias_cases = sum(
                1
                for row in source_semantic_cache_cases
                if int(row.get("source_semantic_factual_gold_candidate_alias_count") or 0)
                > 0
            )
            source_factual_gold_candidate_query_overlap_cases = sum(
                1
                for row in source_semantic_cache_cases
                if int(
                    row.get(
                        "source_semantic_factual_gold_candidate_query_overlap_count"
                    )
                    or 0
                )
                > 0
            )
            source_factual_answer_bearing_cases = sum(
                1
                for row in source_semantic_cache_cases
                if int(row.get("source_semantic_answer_bearing_line_count") or 0) > 0
            )
            source_factual_alias_candidate_lifts = sum(
                1
                for row in source_semantic_cache_cases
                if not row.get(f"evidence_hit_top{top_k}")
                and row.get("source_semantic_factual_alias_candidate_evidence_contains")
            )
            source_factual_alias_fused_lifts = sum(
                1
                for row in source_semantic_cache_cases
                if not row.get(f"evidence_hit_top{top_k}")
                and row.get(f"reranked_evidence_hit_top{top_k}")
                and row.get("source_semantic_factual_alias_candidate_evidence_contains")
            )
            source_fused_regressions = sum(
                1
                for row in source_semantic_cache_cases
                if row.get(f"evidence_hit_top{top_k}")
                and not row.get(f"reranked_evidence_hit_top{top_k}")
            )
            metrics.update(
                {
                    "source_semantic_cache_case_count": len(source_semantic_cache_cases),
                    "source_semantic_cache_search_available_count": sum(
                        1
                        for row in source_semantic_cache_cases
                        if row.get("source_semantic_cache_search_available")
                    ),
                    "source_semantic_cache_search_hit_count_avg": round(
                        sum(
                            int(row.get("source_semantic_cache_hit_count") or 0)
                            for row in source_semantic_cache_cases
                        )
                        / len(source_semantic_cache_cases),
                        2,
                    ),
                    "source_semantic_cache_hot_path_latency_ms": (
                        summarize_numeric_latency(
                            source_semantic_cache_cases,
                            "source_semantic_cache_latency_ms",
                        )
                    ),
                    f"source_semantic_cache_search_evidence_hit_top{top_k}": (
                        source_search_hits
                    ),
                    f"source_semantic_cache_search_evidence_hit_rate_top{top_k}": (
                        safe_rate(source_search_hits, len(source_semantic_cache_cases))
                    ),
                    "source_semantic_cache_search_evidence_mrr": source_search_mrr,
                    f"source_semantic_cache_only_evidence_hit_top{top_k}": (
                        source_only_hits
                    ),
                    f"source_semantic_cache_only_evidence_hit_rate_top{top_k}": (
                        safe_rate(source_only_hits, len(source_semantic_cache_cases))
                    ),
                    "source_semantic_cache_only_evidence_mrr": source_only_mrr,
                    f"source_semantic_cache_fused_evidence_hit_top{top_k}": (
                        source_fused_hits
                    ),
                    f"source_semantic_cache_fused_evidence_hit_rate_top{top_k}": (
                        safe_rate(source_fused_hits, len(source_semantic_cache_cases))
                    ),
                    "source_semantic_cache_fused_evidence_mrr": source_fused_mrr,
                    "source_semantic_cache_hot_query_provider_call_count": 0,
                    "source_semantic_scope_sidecar_case_count": (
                        source_scope_sidecar_case_count
                    ),
                    "source_semantic_scope_sidecar_case_rate": safe_rate(
                        source_scope_sidecar_case_count,
                        len(source_semantic_cache_cases),
                    ),
                    "source_semantic_scope_sidecar_line_count_avg": round(
                        sum(
                            int(
                                row.get(
                                    "source_semantic_scope_sidecar_line_count"
                                )
                                or 0
                            )
                            for row in source_semantic_cache_cases
                        )
                        / len(source_semantic_cache_cases),
                        2,
                    ),
                    "source_semantic_scope_sidecar_evidence_coverage": (
                        source_scope_sidecar_evidence_coverage
                    ),
                    "source_semantic_scope_sidecar_evidence_coverage_rate": (
                        safe_rate(
                            source_scope_sidecar_evidence_coverage,
                            len(source_semantic_cache_cases),
                        )
                    ),
                    "source_semantic_scope_sidecar_context_coverage": (
                        source_scope_sidecar_context_coverage
                    ),
                    "source_semantic_scope_sidecar_context_coverage_rate": (
                        safe_rate(
                            source_scope_sidecar_context_coverage,
                            len(source_semantic_cache_cases),
                        )
                    ),
                    "source_semantic_scope_sidecar_candidate_evidence_coverage": (
                        source_scope_sidecar_candidate_evidence_coverage
                    ),
                    "source_semantic_scope_sidecar_candidate_evidence_coverage_rate": (
                        safe_rate(
                            source_scope_sidecar_candidate_evidence_coverage,
                            len(source_semantic_cache_cases),
                        )
                    ),
                    "source_semantic_scope_gold_candidate_label_case_count": (
                        source_scope_gold_candidate_label_cases
                    ),
                    "source_semantic_scope_gold_candidate_term_case_count": (
                        source_scope_gold_candidate_term_cases
                    ),
                    "source_semantic_scope_gold_candidate_query_term_overlap_case_count": (
                        source_scope_gold_candidate_query_overlap_cases
                    ),
                    "source_semantic_factual_alias_case_count": (
                        source_factual_alias_case_count
                    ),
                    "source_semantic_factual_alias_case_rate": safe_rate(
                        source_factual_alias_case_count,
                        len(source_semantic_cache_cases),
                    ),
                    "source_semantic_factual_alias_line_count_avg": round(
                        sum(
                            int(
                                row.get("source_semantic_factual_alias_line_count")
                                or 0
                            )
                            for row in source_semantic_cache_cases
                        )
                        / len(source_semantic_cache_cases),
                        2,
                    ),
                    "source_semantic_factual_alias_evidence_coverage": (
                        source_factual_alias_evidence_coverage
                    ),
                    "source_semantic_factual_alias_evidence_coverage_rate": (
                        safe_rate(
                            source_factual_alias_evidence_coverage,
                            len(source_semantic_cache_cases),
                        )
                    ),
                    "source_semantic_factual_alias_candidate_evidence_coverage": (
                        source_factual_alias_candidate_evidence_coverage
                    ),
                    "source_semantic_factual_alias_candidate_evidence_coverage_rate": (
                        safe_rate(
                            source_factual_alias_candidate_evidence_coverage,
                            len(source_semantic_cache_cases),
                        )
                    ),
                    "source_semantic_factual_gold_candidate_alias_case_count": (
                        source_factual_gold_candidate_alias_cases
                    ),
                    "source_semantic_factual_gold_candidate_query_overlap_case_count": (
                        source_factual_gold_candidate_query_overlap_cases
                    ),
                    "source_semantic_answer_bearing_case_count": (
                        source_factual_answer_bearing_cases
                    ),
                    f"source_semantic_factual_alias_candidate_lift_top{top_k}": (
                        source_factual_alias_candidate_lifts
                    ),
                    f"source_semantic_factual_alias_candidate_lift_rate_top{top_k}": (
                        safe_rate(
                            source_factual_alias_candidate_lifts,
                            len(source_semantic_cache_cases),
                        )
                    ),
                    f"source_semantic_factual_alias_fused_lift_top{top_k}": (
                        source_factual_alias_fused_lifts
                    ),
                    f"source_semantic_factual_alias_fused_lift_rate_top{top_k}": (
                        safe_rate(
                            source_factual_alias_fused_lifts,
                            len(source_semantic_cache_cases),
                        )
                    ),
                    f"source_semantic_cache_fused_regression_top{top_k}": (
                        source_fused_regressions
                    ),
                    f"source_semantic_cache_fused_regression_rate_top{top_k}": (
                        safe_rate(source_fused_regressions, len(source_semantic_cache_cases))
                    ),
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
        "capability_provenance": config.get("capability_provenance", {}),
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


def should_emit_progress(count: int, total: int, every: int) -> bool:
    if int(every) <= 0:
        return False
    return int(count) == int(total) or int(count) % int(every) == 0


def emit_standard_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    *,
    started: float,
    phase: str,
    config: dict[str, Any],
    cases_built: int = 0,
    cases_evaluated: int = 0,
    total_cases: int | None = None,
    corpus: dict[str, Any] | None = None,
) -> None:
    if progress_callback is None:
        return
    elapsed_seconds = max(0.0, time.perf_counter() - started)
    event: dict[str, Any] = {
        "kind": "standard_public_retrieval_progress",
        "generated_at": now_utc(),
        "dataset": config["dataset"],
        "phase": phase,
        "corpus_path_sha1": config["corpus_path_sha1"],
        "max_questions": int(config["max_questions"]),
        "cases_built": int(cases_built),
        "cases_evaluated": int(cases_evaluated),
        "elapsed_ms": round(elapsed_seconds * 1000, 2),
    }
    if total_cases is not None:
        event["total_cases"] = int(total_cases)
    if int(cases_evaluated) > 0:
        event["average_seconds_per_case"] = round(
            elapsed_seconds / int(cases_evaluated),
            4,
        )
    if corpus:
        event["corpus"] = {
            key: int(value)
            for key, value in corpus.items()
            if key.endswith("_scanned")
            or key in {"eligible_questions", "session_count", "samples_scanned"}
            if isinstance(value, int)
        }
    progress_callback(event)


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
    progress_every: int = 0,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    standard_cache_dir: Path | str | None = None,
    use_standard_cache: bool = True,
    rebuild_standard_cache: bool = False,
    source_semantic_sidecar_materializer: str = SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    source_semantic_sidecar_max_candidates: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    source_semantic_sidecar_max_provider_calls: int = 0,
    source_semantic_sidecar_workers: int = 1,
    source_semantic_sidecar_timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    source_semantic_sidecar_max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    source_semantic_sidecar_min_confidence: float = DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    source_semantic_sidecar_labeler_fn: PublicSemanticLabelerFn | None = None,
    rebuild_source_semantic_sidecars: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    if dataset not in STANDARD_DATASET_PATHS:
        raise ValueError(f"unsupported standard dataset: {dataset}")
    resolved_path = Path(corpus_path or STANDARD_DATASET_PATHS[dataset]).resolve()
    resolved_line_reranker_mode = line_reranker_mode.strip().casefold()
    if resolved_line_reranker_mode not in STANDARD_LINE_RERANKER_MODES:
        raise ValueError(f"unsupported line reranker mode: {line_reranker_mode}")
    resolved_sidecar_materializer = (
        str(source_semantic_sidecar_materializer or "").strip().casefold()
    )
    if resolved_sidecar_materializer not in SOURCE_SEMANTIC_SIDECAR_MATERIALIZERS:
        raise ValueError(
            f"unsupported source semantic sidecar materializer: {source_semantic_sidecar_materializer}"
        )
    if (
        resolved_sidecar_materializer != SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF
        and resolved_line_reranker_mode != "source_semantic_cache"
    ):
        raise ValueError(
            "source semantic sidecar materialization requires line_reranker_mode=source_semantic_cache"
        )
    resolved_reranker_workers = (
        max(1, (int(max_questions) + 1) // 2)
        if int(line_reranker_workers) <= 0 and resolved_line_reranker_mode != "off"
        else max(1, int(line_reranker_workers))
    )
    corpus_sha256 = file_sha256(resolved_path) if resolved_path.exists() else ""
    case_cache_key = (
        standard_case_cache_key(
            dataset=dataset,
            corpus_sha256=corpus_sha256,
            max_questions=max_questions,
        )
        if corpus_sha256
        else ""
    )
    standard_case_cache = new_standard_case_cache_metrics(
        enabled=bool(use_standard_cache and corpus_sha256),
        cache_key=case_cache_key,
        rebuild_requested=bool(rebuild_standard_cache),
    )
    config = {
        "dataset": dataset,
        "corpus_path_sha1": sha1_text(str(resolved_path))[:16],
        "corpus_sha256": corpus_sha256,
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
        "source_semantic_sidecar_materializer": resolved_sidecar_materializer,
        "source_semantic_sidecar_max_candidates": int(
            source_semantic_sidecar_max_candidates
        ),
        "source_semantic_sidecar_max_provider_calls": int(
            source_semantic_sidecar_max_provider_calls
        ),
        "source_semantic_sidecar_workers": int(source_semantic_sidecar_workers),
        "source_semantic_sidecar_timeout": int(source_semantic_sidecar_timeout),
        "source_semantic_sidecar_max_tokens": int(source_semantic_sidecar_max_tokens),
        "source_semantic_sidecar_min_confidence": float(
            source_semantic_sidecar_min_confidence
        ),
        "rebuild_source_semantic_sidecars": bool(rebuild_source_semantic_sidecars),
        "standard_case_cache": {
            "enabled": bool(standard_case_cache["enabled"]),
            "policy_version": STANDARD_CASE_CACHE_POLICY_VERSION,
            "adapter_version": STANDARD_CASE_ADAPTER_VERSION,
            "cache_key": case_cache_key,
            "cache_root_emitted": False,
            "rebuild_requested": bool(rebuild_standard_cache),
        },
        "capability_provenance": benchmark_capability_provenance(
            resolved_line_reranker_mode,
            source_semantic_sidecar_materializer=resolved_sidecar_materializer,
        ),
    }
    if resolved_line_reranker_mode == "semantic":
        config["line_reranker_metadata"] = semantic_line_reranker_public_contract(
            timeout=line_reranker_timeout,
            max_tokens=line_reranker_max_tokens,
        )
    if resolved_line_reranker_mode == "source_semantic_cache":
        config["line_reranker_metadata"] = source_semantic_cache_public_contract()
        config["source_semantic_cache_prewarmed"] = True
        config["source_semantic_cache_prewarm_workers"] = int(
            DEFAULT_STANDARD_SOURCE_SEMANTIC_CACHE_PREWARM_WORKERS
        )
        if resolved_sidecar_materializer != SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF:
            config["source_semantic_sidecar_materializer_contract"] = (
                source_semantic_sidecar_materializer_contract(
                    materializer=resolved_sidecar_materializer,
                    max_candidates=source_semantic_sidecar_max_candidates,
                    max_provider_calls=source_semantic_sidecar_max_provider_calls,
                    workers=source_semantic_sidecar_workers,
                    timeout=source_semantic_sidecar_timeout,
                    max_tokens=source_semantic_sidecar_max_tokens,
                    min_confidence=source_semantic_sidecar_min_confidence,
                )
            )
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
    emit_standard_progress(
        progress_callback,
        started=started,
        phase="dataset_verified",
        config=config,
    )

    def emit_case_building_progress(count: int, corpus: dict[str, Any]) -> None:
        if should_emit_progress(count, int(max_questions), progress_every):
            emit_standard_progress(
                progress_callback,
                started=started,
                phase="cases_building",
                config=config,
                cases_built=count,
                total_cases=int(max_questions),
                corpus=corpus,
            )

    tmp_context: tempfile.TemporaryDirectory[str] | None = None
    if standard_case_cache["enabled"]:
        base_cache_dir = Path(
            standard_cache_dir or DEFAULT_STANDARD_CASE_CACHE_ROOT
        ).resolve()
        case_root = base_cache_dir / case_cache_key
        case_root.mkdir(parents=True, exist_ok=True)
    else:
        tmp_context = tempfile.TemporaryDirectory(prefix="aippocampus-standard-track-b-")
        case_root = Path(tmp_context.name)
    try:
        if dataset == "locomo":
            cases, corpus = build_locomo_standard_cases(
                case_root,
                corpus_path=resolved_path,
                max_questions=max_questions,
                cache_metrics=standard_case_cache,
                rebuild_cache=bool(rebuild_standard_cache),
                case_progress_callback=emit_case_building_progress,
            )
        else:
            cases, corpus = build_longmemeval_v1_standard_cases(
                case_root,
                dataset=dataset,
                corpus_path=resolved_path,
                max_questions=max_questions,
                cache_metrics=standard_case_cache,
                rebuild_cache=bool(rebuild_standard_cache),
                case_progress_callback=emit_case_building_progress,
            )
        corpus["case_cache"] = finalized_standard_case_cache_metrics(
            standard_case_cache
        )
        emit_standard_progress(
            progress_callback,
            started=started,
            phase="cases_built",
            config=config,
            cases_built=len(cases),
            total_cases=len(cases),
            corpus=corpus,
        )
        source_semantic_sidecar_materialization = None
        if resolved_sidecar_materializer != SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF:
            source_semantic_sidecar_materialization = materialize_source_semantic_sidecars(
                cases,
                materializer=resolved_sidecar_materializer,
                max_candidates=source_semantic_sidecar_max_candidates,
                max_provider_calls=source_semantic_sidecar_max_provider_calls,
                workers=source_semantic_sidecar_workers,
                timeout=source_semantic_sidecar_timeout,
                max_tokens=source_semantic_sidecar_max_tokens,
                min_confidence=source_semantic_sidecar_min_confidence,
                labeler_fn=source_semantic_sidecar_labeler_fn,
                rebuild_sidecars=bool(rebuild_source_semantic_sidecars),
            )
            emit_standard_progress(
                progress_callback,
                started=started,
                phase="source_semantic_sidecars_materialized",
                config=config,
                cases_built=len(cases),
                total_cases=len(cases),
                corpus=corpus,
            )
        source_artifact_cache_dir = (
            # Store source artifacts under the shared benchmark cache root, not
            # the per-prefix case root, so 25/100/500 growth runs can reuse the
            # same content-addressed worker surfaces.
            base_cache_dir / "source_artifacts" / SOURCE_SEMANTIC_CACHE_POLICY_VERSION
            if standard_case_cache["enabled"]
            else None
        )
        source_semantic_cache_store = (
            SourceSemanticCacheStore(
                artifact_cache_dir=source_artifact_cache_dir,
                # Source artifact keys already include source/sidecar/session
                # fingerprints. Standard SQLite rebuilds should not discard a
                # matching semantic worker surface unless its content changes.
                rebuild_artifact_cache=False,
            )
            if resolved_line_reranker_mode == "source_semantic_cache"
            else None
        )
        if source_semantic_cache_store is not None:
            prewarm_workers = min(
                max(1, int(DEFAULT_STANDARD_SOURCE_SEMANTIC_CACHE_PREWARM_WORKERS)),
                max(1, len(cases)),
            )

            def prewarm(case: dict[str, Any]) -> None:
                expected = case.get("expected") or {}
                source_semantic_cache_store.get(
                    Path(case["sqlite_path"]),
                    line_to_session={
                        str(k): str(v)
                        for k, v in (expected.get("line_to_session") or {}).items()
                    },
                )

            if prewarm_workers > 1:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=prewarm_workers
                ) as executor:
                    list(executor.map(prewarm, cases))
            else:
                for case in cases:
                    prewarm(case)
            emit_standard_progress(
                progress_callback,
                started=started,
                phase="source_semantic_cache_prewarmed",
                config=config,
                cases_built=len(cases),
                total_cases=len(cases),
                corpus=corpus,
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
                source_semantic_cache_store=source_semantic_cache_store,
            )

        if resolved_line_reranker_mode != "off" and resolved_reranker_workers > 1:
            indexed_results: list[dict[str, Any] | None] = [None] * len(cases)
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=resolved_reranker_workers
            ) as executor:
                future_to_index = {
                    executor.submit(evaluate, case): index
                    for index, case in enumerate(cases)
                }
                for completed, future in enumerate(
                    concurrent.futures.as_completed(future_to_index),
                    start=1,
                ):
                    index = future_to_index[future]
                    indexed_results[index] = future.result()
                    if should_emit_progress(completed, len(cases), progress_every):
                        emit_standard_progress(
                            progress_callback,
                            started=started,
                            phase="cases_evaluated",
                            config=config,
                            cases_built=len(cases),
                            cases_evaluated=completed,
                            total_cases=len(cases),
                            corpus=corpus,
                        )
                results = [row for row in indexed_results if row is not None]
        else:
            results = []
            for completed, case in enumerate(cases, start=1):
                results.append(evaluate(case))
                if should_emit_progress(completed, len(cases), progress_every):
                    emit_standard_progress(
                        progress_callback,
                        started=started,
                        phase="cases_evaluated",
                        config=config,
                        cases_built=len(cases),
                        cases_evaluated=completed,
                        total_cases=len(cases),
                        corpus=corpus,
                    )
    finally:
        if tmp_context is not None:
            tmp_context.cleanup()
    metrics = summarize_standard_retrieval_results(
        results,
        top_k=top_k,
        context_radius=context_radius,
    )
    if "source_semantic_sidecar_materialization" in locals() and source_semantic_sidecar_materialization:
        metrics["source_semantic_sidecar_materialization"] = (
            source_semantic_sidecar_materialization
        )
    if resolved_line_reranker_mode == "source_semantic_cache":
        metrics["source_semantic_cache"] = (
            source_semantic_cache_store.summary()
            if source_semantic_cache_store is not None
            else SourceSemanticCacheStore().summary()
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
        "capability_provenance": config["capability_provenance"],
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
