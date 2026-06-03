"""ShareGPT public source-evidence Track B adapter."""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path
from typing import Any

import benchmark_fts5_recall as fts5_benchmark
import sharegpt_sampling
from benchmark_statistics import binomial_rate_report
from build_index import make_sqlite
from retrieval import split_query_terms

from .defaults import (
    CONTINUATION_RE,
    DEFAULT_SHAREGPT_PUBLIC_CASES,
    DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS,
    DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR,
    DEFAULT_SHAREGPT_PUBLIC_MIN_CASES,
    DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE,
    DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE,
    DEFAULT_SHAREGPT_PUBLIC_TOP_K,
    PUBLIC_SOURCE_TERM_STOPWORDS,
    SCHEMA_VERSION,
)
from .reporting import (
    now_utc,
    reciprocal_rank,
    safe_rate,
    sha1_text,
)


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


def load_sharegpt_conversations(
    corpus_dir: Path,
    max_conversations: int,
    *,
    sampling_mode: str | None = sharegpt_sampling.FIRST_N,
    seed: int = sharegpt_sampling.DEFAULT_SHAREGPT_SAMPLE_SEED,
) -> list[list[dict[str, Any]]]:
    return sharegpt_sampling.sample_sharegpt_conversations(
        corpus_dir,
        max_conversations,
        normalize_rows=normalize_sharegpt_rows,
        is_eligible=sharegpt_conversation_is_eligible,
        sampling_mode=sampling_mode,
        seed=seed,
    ).conversations


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
    rate_estimates = {
        f"message_hit_rate_top{top_k}": binomial_rate_report(
            f"message_hit_rate_top{top_k}",
            numerator=message_hits,
            denominator=total,
        ),
        f"turn_hit_rate_top{top_k}": binomial_rate_report(
            f"turn_hit_rate_top{top_k}",
            numerator=turn_hits,
            denominator=total,
        ),
    }
    return {
        "total_cases": total,
        "case_types": case_types,
        f"message_hit_top{top_k}": message_hits,
        f"message_miss_top{top_k}": total - message_hits,
        f"message_hit_rate_top{top_k}": safe_rate(message_hits, total),
        f"turn_hit_top{top_k}": turn_hits,
        f"turn_miss_top{top_k}": total - turn_hits,
        f"turn_hit_rate_top{top_k}": safe_rate(turn_hits, total),
        "rate_estimates": rate_estimates,
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
    sampling_mode: str = sharegpt_sampling.SEEDED_STRATIFIED,
    seed: int = sharegpt_sampling.DEFAULT_SHAREGPT_SAMPLE_SEED,
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
        "sampling_mode": sharegpt_sampling.canonical_sampling_mode(sampling_mode),
        "seed": int(seed),
        "include_private_text": bool(include_private_text),
    }
    try:
        sample = sharegpt_sampling.sample_sharegpt_conversations(
            resolved_corpus_dir,
            conversations,
            normalize_rows=normalize_sharegpt_rows,
            is_eligible=sharegpt_conversation_is_eligible,
            sampling_mode=sampling_mode,
            seed=seed,
        )
    except FileNotFoundError as exc:
        return skipped_sharegpt_public_payload(
            corpus_dir=resolved_corpus_dir,
            started=started,
            reason=str(exc),
            config=config,
        )
    conversations_payload = sample.conversations
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
        "sampling": sample.report,
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
            *(
                ["seeded_stratified_population_sampling"]
                if sample.report.get("method") == sharegpt_sampling.FIRST_N
                else []
            ),
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
