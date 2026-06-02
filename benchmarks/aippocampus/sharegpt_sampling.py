"""Deterministic ShareGPT clean-source sampling for public benchmark slices.

The public ShareGPT corpora are large ignored local artifacts. Public-quality
benchmark runs need to avoid first-N corpus bias, but smoke/debug runs still
need a cheap explicit first-N mode. This helper keeps that policy local to the
benchmark tree and emits only sanitized ids, hashes, buckets, and counts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DEFAULT_SHAREGPT_SAMPLE_SEED = 218
SEEDED_STRATIFIED = "seeded_stratified"
FIRST_N = "first_n"
SAMPLING_MODES = {SEEDED_STRATIFIED, FIRST_N, "seeded-stratified", "first-n"}

NormalizeRowsFn = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
EligibleRowsFn = Callable[[list[dict[str, Any]]], bool]

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_CODING_RE = re.compile(
    r"\b("
    r"api|async|bug|class|cli|code|compile|database|debug|docker|function|git|"
    r"javascript|json|linux|node|python|react|regex|rust|sql|typescript|unit test"
    r")\b",
    re.IGNORECASE,
)
_SAFE_BUCKET_RE = re.compile(r"[^a-z0-9._,+ -]+")
_CODING_CATEGORY_TERMS = {
    "code",
    "coding",
    "computer",
    "develop",
    "program",
    "software",
}


@dataclass(frozen=True)
class ConversationCandidate:
    source_id: str
    source_id_hash: str
    order: int
    message_count: int
    user_message_count: int
    assistant_message_count: int
    stratum_id: str
    stratum: dict[str, Any]


@dataclass(frozen=True)
class ShareGPTSampleResult:
    conversations: list[list[dict[str, Any]]]
    report: dict[str, Any]


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def canonical_sampling_mode(mode: str | None) -> str:
    raw = (mode or SEEDED_STRATIFIED).strip().lower().replace("-", "_")
    if raw == SEEDED_STRATIFIED:
        return SEEDED_STRATIFIED
    if raw == FIRST_N:
        return FIRST_N
    raise ValueError(f"Unsupported ShareGPT sampling mode: {mode!r}")


def _row_meta(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("_meta")
    return meta if isinstance(meta, dict) else {}


def _first_meta_value(rows: list[dict[str, Any]], key: str) -> str:
    for row in rows:
        value = _row_meta(row).get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _safe_bucket(raw: str, *, max_len: int = 64) -> str:
    value = _SAFE_BUCKET_RE.sub("_", raw.strip().lower()).strip(" _-")
    return (value or "unknown")[:max_len]


def _language_bucket(rows: list[dict[str, Any]]) -> str:
    explicit = _first_meta_value(rows, "language")
    if explicit:
        lowered = explicit.lower()
        if lowered.startswith(("zh", "cn", "chinese")):
            return "zh"
        if lowered.startswith(("en", "english")):
            return "en"
        return _safe_bucket(lowered, max_len=24)
    sample_text = " ".join(str(row.get("text") or "")[:400] for row in rows[:8])
    has_cjk = bool(_CJK_RE.search(sample_text))
    ascii_letters = sum(1 for char in sample_text if char.isascii() and char.isalpha())
    if has_cjk and ascii_letters >= 20:
        return "mixed"
    if has_cjk:
        return "zh"
    if ascii_letters >= 20:
        return "en"
    return "unknown"


def _turn_count(rows: list[dict[str, Any]]) -> int:
    turn_ids = {str(row.get("turn_id") or "") for row in rows if row.get("turn_id")}
    if turn_ids:
        return len(turn_ids)
    turn_indexes = []
    for row in rows:
        try:
            turn_indexes.append(int(row.get("turn_index") or 0))
        except (TypeError, ValueError):
            continue
    if turn_indexes:
        return max(turn_indexes)
    return sum(1 for row in rows if row.get("role") == "user")


def _turn_bucket(turn_count: int) -> str:
    if turn_count <= 1:
        return "1_turn"
    if turn_count == 2:
        return "2_turns"
    if turn_count <= 5:
        return "3_5_turns"
    if turn_count <= 10:
        return "6_10_turns"
    return "11_plus_turns"


def _coding_bucket(rows: list[dict[str, Any]], category_bucket: str) -> str:
    if any(term in category_bucket for term in _CODING_CATEGORY_TERMS):
        return "coding"
    sample_text = " ".join(str(row.get("text") or "")[:300] for row in rows[:6])
    return "coding" if _CODING_RE.search(sample_text) else "non_coding"


def _candidate_from_rows(rows: list[dict[str, Any]], *, order: int) -> ConversationCandidate:
    source_id = str(rows[0].get("source_id") or f"sharegpt-{order}")
    source_hash = sha1_text(source_id)[:16]
    source_file = _first_meta_value(rows, "source_file")
    category = _first_meta_value(rows, "category")
    category_bucket = _safe_bucket(category, max_len=48)
    turn_count = _turn_count(rows)
    stratum = {
        "source_file_sha1": sha1_text(source_file)[:16] if source_file else "unknown",
        "source_file_present": bool(source_file),
        "category_bucket": category_bucket,
        "language_bucket": _language_bucket(rows),
        "turn_count_bucket": _turn_bucket(turn_count),
        "coding_bucket": _coding_bucket(rows, category_bucket),
    }
    key = "|".join(str(stratum[field]) for field in sorted(stratum))
    stratum_id = sha1_text(key)[:16]
    return ConversationCandidate(
        source_id=source_id,
        source_id_hash=source_hash,
        order=order,
        message_count=len(rows),
        user_message_count=sum(1 for row in rows if row.get("role") == "user"),
        assistant_message_count=sum(1 for row in rows if row.get("role") == "assistant"),
        stratum_id=stratum_id,
        stratum={"stratum_id": stratum_id, **stratum},
    )


def _new_stats() -> dict[str, int]:
    return {
        "lines_scanned": 0,
        "messages_scanned": 0,
        "conversations_seen": 0,
        "eligible_conversations": 0,
        "ineligible_conversations": 0,
        "malformed_json_lines": 0,
        "missing_source_id_rows": 0,
        "empty_lines": 0,
    }


def _flush_rows(
    rows: list[dict[str, Any]],
    *,
    normalize_rows: NormalizeRowsFn,
    is_eligible: EligibleRowsFn,
    stats: dict[str, int],
) -> list[dict[str, Any]] | None:
    if not rows:
        return None
    stats["conversations_seen"] += 1
    normalized = normalize_rows(rows)
    if is_eligible(normalized):
        stats["eligible_conversations"] += 1
        return normalized
    stats["ineligible_conversations"] += 1
    return None


def _scan_candidates(
    messages_path: Path,
    *,
    normalize_rows: NormalizeRowsFn,
    is_eligible: EligibleRowsFn,
) -> tuple[list[ConversationCandidate], dict[str, int]]:
    stats = _new_stats()
    candidates: list[ConversationCandidate] = []
    current_source_id = ""
    current_rows: list[dict[str, Any]] = []

    with messages_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stats["lines_scanned"] += 1
            if not line.strip():
                stats["empty_lines"] += 1
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                stats["malformed_json_lines"] += 1
                continue
            if not isinstance(message, dict):
                stats["malformed_json_lines"] += 1
                continue
            source_id = str(message.get("source_id") or "")
            if not source_id:
                stats["missing_source_id_rows"] += 1
                continue
            stats["messages_scanned"] += 1
            if current_source_id and source_id != current_source_id:
                rows = _flush_rows(
                    current_rows,
                    normalize_rows=normalize_rows,
                    is_eligible=is_eligible,
                    stats=stats,
                )
                if rows:
                    candidates.append(_candidate_from_rows(rows, order=len(candidates)))
                current_rows = []
            current_source_id = source_id
            current_rows.append(message)

    rows = _flush_rows(
        current_rows,
        normalize_rows=normalize_rows,
        is_eligible=is_eligible,
        stats=stats,
    )
    if rows:
        candidates.append(_candidate_from_rows(rows, order=len(candidates)))
    return candidates, stats


def _collect_conversations(
    messages_path: Path,
    *,
    selected_source_ids: set[str] | None,
    max_first_n: int | None,
    normalize_rows: NormalizeRowsFn,
    is_eligible: EligibleRowsFn,
) -> tuple[list[list[dict[str, Any]]], dict[str, int]]:
    stats = _new_stats()
    conversations: list[list[dict[str, Any]]] = []
    current_source_id = ""
    current_rows: list[dict[str, Any]] = []

    def maybe_collect(rows: list[dict[str, Any]]) -> bool:
        normalized = _flush_rows(
            rows,
            normalize_rows=normalize_rows,
            is_eligible=is_eligible,
            stats=stats,
        )
        if not normalized:
            return False
        source_id = str(normalized[0].get("source_id") or "")
        if selected_source_ids is not None and source_id not in selected_source_ids:
            return False
        conversations.append(normalized)
        return max_first_n is not None and len(conversations) >= max_first_n

    with messages_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stats["lines_scanned"] += 1
            if not line.strip():
                stats["empty_lines"] += 1
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                stats["malformed_json_lines"] += 1
                continue
            if not isinstance(message, dict):
                stats["malformed_json_lines"] += 1
                continue
            source_id = str(message.get("source_id") or "")
            if not source_id:
                stats["missing_source_id_rows"] += 1
                continue
            stats["messages_scanned"] += 1
            if current_source_id and source_id != current_source_id:
                if maybe_collect(current_rows):
                    return conversations, stats
                current_rows = []
            current_source_id = source_id
            current_rows.append(message)

    maybe_collect(current_rows)
    return conversations, stats


def _allocate_stratified_quotas(
    candidates: list[ConversationCandidate],
    sample_size: int,
) -> dict[str, int]:
    by_stratum: dict[str, list[ConversationCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_stratum[candidate.stratum_id].append(candidate)
    population = len(candidates)
    if sample_size >= population:
        return {stratum_id: len(items) for stratum_id, items in by_stratum.items()}

    quotas: dict[str, int] = {}
    remainders: list[tuple[float, int, str]] = []
    for stratum_id, items in by_stratum.items():
        raw = sample_size * (len(items) / population)
        quota = min(len(items), int(raw))
        quotas[stratum_id] = quota
        remainders.append((raw - quota, len(items), stratum_id))

    remaining = sample_size - sum(quotas.values())
    for _, _, stratum_id in sorted(remainders, reverse=True):
        if remaining <= 0:
            break
        if quotas[stratum_id] >= len(by_stratum[stratum_id]):
            continue
        quotas[stratum_id] += 1
        remaining -= 1
    return quotas


def _select_candidates(
    candidates: list[ConversationCandidate],
    *,
    sample_size: int,
    seed: int,
) -> list[ConversationCandidate]:
    quotas = _allocate_stratified_quotas(candidates, sample_size)
    by_stratum: dict[str, list[ConversationCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_stratum[candidate.stratum_id].append(candidate)

    selected: list[ConversationCandidate] = []
    for stratum_id, items in by_stratum.items():
        quota = quotas.get(stratum_id, 0)
        if quota <= 0:
            continue
        ranked = sorted(
            items,
            key=lambda item: sha1_text(
                f"{seed}|{item.stratum_id}|{item.source_id_hash}|{item.order}"
            ),
        )
        selected.extend(ranked[:quota])
    return selected


def _strata_report(
    candidates: list[ConversationCandidate],
    selected_hashes: set[str],
) -> list[dict[str, Any]]:
    by_stratum: dict[str, list[ConversationCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_stratum[candidate.stratum_id].append(candidate)
    rows: list[dict[str, Any]] = []
    for _stratum_id, items in sorted(by_stratum.items()):
        base = dict(items[0].stratum)
        base.update(
            {
                "eligible_conversations": len(items),
                "selected_conversations": sum(
                    1 for item in items if item.source_id_hash in selected_hashes
                ),
            }
        )
        rows.append(base)
    return rows


def _selected_ids(conversations: list[list[dict[str, Any]]]) -> list[str]:
    return [sha1_text(str(rows[0].get("source_id") or ""))[:16] for rows in conversations if rows]


def _first_n_report(
    *,
    conversations: list[list[dict[str, Any]]],
    stats: dict[str, int],
    target: int,
) -> dict[str, Any]:
    candidates = [
        _candidate_from_rows(rows, order=index) for index, rows in enumerate(conversations)
    ]
    selected_hashes = {candidate.source_id_hash for candidate in candidates}
    return {
        "method": FIRST_N,
        "seed": None,
        "requested_conversation_count": target,
        "selected_conversation_count": len(conversations),
        "selected_conversation_ids": _selected_ids(conversations),
        "population_scan_complete": False,
        "eligible_population_count": None,
        "eligible_population_count_scanned": int(stats["eligible_conversations"]),
        "stratum_fields": [
            "source_file_sha1",
            "category_bucket",
            "language_bucket",
            "turn_count_bucket",
            "coding_bucket",
        ],
        "strata": _strata_report(candidates, selected_hashes),
        "skipped_counts": {
            "ineligible_conversations_scanned": int(stats["ineligible_conversations"]),
            "malformed_json_lines": int(stats["malformed_json_lines"]),
            "missing_source_id_rows": int(stats["missing_source_id_rows"]),
            "empty_lines": int(stats["empty_lines"]),
        },
        "messages_scanned": int(stats["messages_scanned"]),
        "conversations_seen": int(stats["conversations_seen"]),
        "claim_boundary": "explicit_first_n_smoke_not_public_quality_sampling",
    }


def sample_sharegpt_conversations(
    corpus_dir: Path,
    max_conversations: int,
    *,
    normalize_rows: NormalizeRowsFn,
    is_eligible: EligibleRowsFn,
    sampling_mode: str | None = None,
    seed: int = DEFAULT_SHAREGPT_SAMPLE_SEED,
) -> ShareGPTSampleResult:
    messages_path = corpus_dir / "messages.jsonl"
    if not messages_path.exists():
        raise FileNotFoundError(f"ShareGPT clean-source messages not found: {messages_path}")
    target = max(1, int(max_conversations))
    mode = canonical_sampling_mode(sampling_mode)

    if mode == FIRST_N:
        conversations, stats = _collect_conversations(
            messages_path,
            selected_source_ids=None,
            max_first_n=target,
            normalize_rows=normalize_rows,
            is_eligible=is_eligible,
        )
        return ShareGPTSampleResult(
            conversations=conversations,
            report=_first_n_report(conversations=conversations, stats=stats, target=target),
        )

    candidates, scan_stats = _scan_candidates(
        messages_path,
        normalize_rows=normalize_rows,
        is_eligible=is_eligible,
    )
    selected_candidates = _select_candidates(
        candidates,
        sample_size=min(target, len(candidates)),
        seed=int(seed),
    )
    selected_source_ids = {candidate.source_id for candidate in selected_candidates}
    conversations, collect_stats = _collect_conversations(
        messages_path,
        selected_source_ids=selected_source_ids,
        max_first_n=None,
        normalize_rows=normalize_rows,
        is_eligible=is_eligible,
    )
    selected_hashes = set(_selected_ids(conversations))
    report = {
        "method": SEEDED_STRATIFIED,
        "seed": int(seed),
        "requested_conversation_count": target,
        "selected_conversation_count": len(conversations),
        "selected_conversation_ids": _selected_ids(conversations),
        "population_scan_complete": True,
        "eligible_population_count": len(candidates),
        "eligible_population_count_scanned": int(scan_stats["eligible_conversations"]),
        "stratum_fields": [
            "source_file_sha1",
            "category_bucket",
            "language_bucket",
            "turn_count_bucket",
            "coding_bucket",
        ],
        "strata": _strata_report(candidates, selected_hashes),
        "skipped_counts": {
            "ineligible_conversations": int(scan_stats["ineligible_conversations"]),
            "malformed_json_lines": int(scan_stats["malformed_json_lines"]),
            "missing_source_id_rows": int(scan_stats["missing_source_id_rows"]),
            "empty_lines": int(scan_stats["empty_lines"]),
        },
        "messages_scanned": int(scan_stats["messages_scanned"]),
        "conversations_seen": int(scan_stats["conversations_seen"]),
        "second_pass_messages_scanned": int(collect_stats["messages_scanned"]),
        "claim_boundary": "seeded_stratified_public_corpus_sample_not_private_history_quality",
    }
    return ShareGPTSampleResult(conversations=conversations, report=report)
