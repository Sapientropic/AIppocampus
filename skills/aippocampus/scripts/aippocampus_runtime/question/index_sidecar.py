#!/usr/bin/env python3
"""Optional SQLite sidecar evaluator for question-tracking lookup scale.

The sidecar is a rebuildable cache, not a source of truth. It stores only
stable question ids, compact term keys, and source-ref fingerprints. The
tracking runner must still re-open the current `question_candidate` rows and
their clean-source refs before accepting a link.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_exit_code_for_error_code,
    compact_text,
    now_utc,
)
from aippocampus_runtime.io_integrity import prepared_atomic_replace
from aippocampus_runtime.question.source_refs import build_source_ref_index, source_ref_key
from aippocampus_runtime.question.tracking import (
    DEFAULT_STRONG_THRESHOLD,
    ConfirmationFn,
    decide_pair,
    default_jobs_path,
    default_registry_path,
    load_tracking_inputs,
    pair_is_trackable,
)
from aippocampus_runtime.question.tracking_types import QuestionCandidate, axis_tokens
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 2
DEFAULT_MAX_PAIRS = 50000
DEFAULT_INDEX_NAME = "question_index.sqlite"
DEFAULT_PREFILTER_PAIR_THRESHOLD = 10000
TRUTH_BOUNDARY = "question_index_sidecar_is_rebuildable_hint_cache_requiring_source_ref_join"


@dataclass(frozen=True)
class QuestionIndexRecord:
    source_id: str
    finding_id: str
    terms: tuple[str, ...]
    source_ref_keys: tuple[str, ...]
    payload: dict[str, Any]

    def signature_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "finding_id": self.finding_id,
            "terms": list(self.terms),
            "source_ref_keys": list(self.source_ref_keys),
        }


def compact_term(term: str) -> str:
    text = compact_text(str(term or "").casefold().strip(), 80)
    return text if len(text) >= 3 else ""


def record_from_candidate(candidate: QuestionCandidate) -> QuestionIndexRecord | None:
    source_ref_keys = tuple(
        unique_preserve(
            ["|".join(source_ref_key(ref)) for ref in candidate.source_refs],
            limit=12,
        )
    )
    if not source_ref_keys:
        return None
    terms = tuple(
        unique_preserve(
            [term for term in (compact_term(token) for token in axis_tokens(candidate)) if term],
            limit=32,
        )
    )
    if not terms:
        return None
    return QuestionIndexRecord(
        source_id=candidate.question_id,
        finding_id=candidate.finding_id,
        terms=terms,
        source_ref_keys=source_ref_keys,
        payload={
            "first_seen": candidate.first_seen,
            "salience": {
                "score": candidate.salience.score,
                "trackable": candidate.salience.trackable,
            },
        },
    )


def records_from_candidates(candidates: Iterable[QuestionCandidate]) -> list[QuestionIndexRecord]:
    records = [record_from_candidate(candidate) for candidate in candidates]
    return sorted((record for record in records if record is not None), key=lambda item: item.source_id)


def question_index_signature(records: Iterable[QuestionIndexRecord]) -> str:
    payload = [record.signature_payload() for record in records]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def write_question_index(
    path: Path,
    records: Iterable[QuestionIndexRecord],
    *,
    source_signature: str,
) -> int:
    record_list = list(records)
    with prepared_atomic_replace(path) as tmp_path:
        with closing(sqlite3.connect(tmp_path)) as conn:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute(
                "CREATE TABLE question_record ("
                "source_id TEXT PRIMARY KEY, "
                "finding_id TEXT NOT NULL, "
                "source_ref_keys_json TEXT NOT NULL, "
                "payload_json TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE question_term ("
                "term TEXT NOT NULL, "
                "source_id TEXT NOT NULL, "
                "PRIMARY KEY (term, source_id))"
            )
            conn.execute("CREATE INDEX question_term_source_idx ON question_term(source_id)")
            metadata = {
                "schema_version": str(SCHEMA_VERSION),
                "kind": "aippocampus_question_index_sidecar",
                "built_at": now_utc(),
                "source_signature": source_signature,
                "record_count": str(len(record_list)),
                "truth_boundary": TRUTH_BOUNDARY,
            }
            conn.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
            conn.executemany(
                "INSERT INTO question_record(source_id, finding_id, source_ref_keys_json, payload_json) "
                "VALUES (?, ?, ?, ?)",
                [
                    (
                        record.source_id,
                        record.finding_id,
                        json.dumps(list(record.source_ref_keys), ensure_ascii=False),
                        json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
                    )
                    for record in record_list
                ],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO question_term(term, source_id) VALUES (?, ?)",
                [(term, record.source_id) for record in record_list for term in record.terms],
            )
            conn.commit()
    return len(record_list)


def load_question_index_metadata(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("SELECT key, value FROM metadata").fetchall()
    return {str(key): str(value) for key, value in rows}


def question_index_is_fresh(path: Path, *, source_signature: str) -> bool:
    try:
        metadata = load_question_index_metadata(path)
    except sqlite3.DatabaseError:
        return False
    return (
        metadata.get("schema_version") == str(SCHEMA_VERSION)
        and metadata.get("truth_boundary") == TRUTH_BOUNDARY
        and metadata.get("source_signature") == source_signature
    )


def candidate_pairs_from_index(
    path: Path,
    *,
    allow_source_ids: Iterable[str] | None = None,
    max_pairs: int = DEFAULT_MAX_PAIRS,
    min_shared_terms: int = 1,
) -> list[tuple[str, str, int]]:
    if not path.exists():
        return []
    allowed = sorted(set(str(value) for value in allow_source_ids or [] if str(value)))
    limit = max(0, int(max_pairs))
    if limit == 0:
        return []
    with closing(sqlite3.connect(path)) as conn:
        if allowed:
            conn.execute("CREATE TEMP TABLE allowed_source(source_id TEXT PRIMARY KEY)")
            conn.executemany(
                "INSERT OR IGNORE INTO allowed_source(source_id) VALUES (?)",
                [(source_id,) for source_id in allowed],
            )
            allow_join = (
                "JOIN allowed_source la ON la.source_id = l.source_id "
                "JOIN allowed_source ra ON ra.source_id = r.source_id "
            )
        else:
            allow_join = ""
        rows = conn.execute(
            "SELECT l.source_id, r.source_id, COUNT(*) AS shared_terms "
            "FROM question_term l "
            "JOIN question_term r ON l.term = r.term AND l.source_id < r.source_id "
            f"{allow_join}"
            "GROUP BY l.source_id, r.source_id "
            "HAVING shared_terms >= ? "
            "ORDER BY shared_terms DESC, l.source_id, r.source_id "
            "LIMIT ?",
            (max(1, int(min_shared_terms)), limit),
        ).fetchall()
    return [(str(left), str(right), int(shared)) for left, right, shared in rows]


def load_index_source_ref_keys(path: Path, source_ids: Iterable[str]) -> dict[str, set[str]]:
    ids = sorted(set(str(value) for value in source_ids if str(value)))
    if not path.exists() or not ids:
        return {}
    result: dict[str, set[str]] = {}
    chunk_size = 800
    with closing(sqlite3.connect(path)) as conn:
        for offset in range(0, len(ids), chunk_size):
            chunk = ids[offset : offset + chunk_size]
            placeholders = ",".join("?" for _item in chunk)
            rows = conn.execute(
                "SELECT source_id, source_ref_keys_json "
                "FROM question_record "
                f"WHERE source_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for source_id, keys_json in rows:
                try:
                    values = json.loads(str(keys_json))
                except json.JSONDecodeError:
                    values = []
                result[str(source_id)] = {str(value) for value in values if str(value)}
    return result


def pair_key(left_id: str, right_id: str) -> tuple[str, str]:
    return (left_id, right_id) if left_id <= right_id else (right_id, left_id)


def build_sidecar_adoption_report(
    *,
    index_requested: bool,
    status: str,
    all_pair_count: int,
    coverage: float,
    source_ref_join_survived: bool,
    evidence_level: str,
) -> dict[str, Any]:
    """Explain whether the optional sidecar is adoption evidence.

    This report is deliberately more conservative than the raw lookup metrics:
    synthetic scale evidence can prove source-ref joins and degradation behavior,
    but it cannot by itself justify making `question_index.sqlite` the default
    prefilter for real registries.
    """

    required_before_default = [
        "run against a real registry or selected real-history pack",
        "prove baseline strong-pair coverage stays complete",
        "prove every sidecar candidate joins back to current source-backed rows",
        "compare wall-clock and output parity against the pair-scan baseline",
    ]
    decision = "candidate_for_optional_lookup_cache"
    recommendation = "candidate_for_optional_lookup_cache"
    reason = "pair count is large enough to evaluate the optional cache, but default routing still needs real-history parity evidence."
    sidecar_needed_now = all_pair_count >= DEFAULT_PREFILTER_PAIR_THRESHOLD
    default_prefilter_recommended = False

    if not index_requested:
        decision = "no_sidecar_requested"
        recommendation = "no_sidecar_requested"
        reason = "no index path was provided, so the current pair-scan baseline remains the only active path."
        sidecar_needed_now = False
        required_before_default = [
            "run the evaluator with an explicit index path",
            *required_before_default,
        ]
    elif status.endswith("degraded_to_baseline"):
        decision = "degrade_to_baseline"
        recommendation = "baseline_safe_sidecar_unavailable"
        reason = "the sidecar is missing, stale, or unavailable; the current baseline must remain authoritative."
        sidecar_needed_now = False
        required_before_default = [
            "rebuild or refresh the sidecar",
            *required_before_default,
        ]
    elif not source_ref_join_survived:
        decision = "blocked_source_ref_join_gap"
        recommendation = "do_not_enable_index_prefilter_until_source_ref_join_is_complete"
        reason = "some sidecar candidates failed to join back to current source-backed question rows."
        sidecar_needed_now = False
        required_before_default = [
            "fix source-ref join coverage before using index candidates",
            *required_before_default,
        ]
    elif coverage < 1.0:
        decision = "blocked_candidate_coverage_gap"
        recommendation = "do_not_enable_index_prefilter_until_coverage_gap_is_understood"
        reason = "the sidecar missed at least one baseline strong pair."
        sidecar_needed_now = False
        required_before_default = [
            "explain and close the baseline strong-pair coverage gap",
            *required_before_default,
        ]
    elif all_pair_count < DEFAULT_PREFILTER_PAIR_THRESHOLD:
        decision = "not_needed_now"
        recommendation = "not_needed_now_current_baseline_pair_count_is_small"
        reason = "the current pair-scan size is below the threshold where a lookup cache is worth adding to the default path."
        sidecar_needed_now = False
    elif evidence_level == "synthetic_scale_smoke":
        decision = "evaluation_only_not_default"
        recommendation = "synthetic_smoke_not_default_adoption_evidence"
        reason = "synthetic scale smoke proves lookup boundaries, but it does not prove real-registry need or answer-quality impact."
        sidecar_needed_now = False
        required_before_default = [
            "repeat the sidecar evaluation on real-history or selected registry data",
            *required_before_default,
        ]

    reason_codes = [decision, evidence_level]
    if status.endswith("degraded_to_baseline"):
        reason_codes.append(status)
    if evidence_level == "synthetic_scale_smoke":
        reason_codes.extend(["synthetic_only_smoke", "real_registry_runtime_unmeasured"])
    if not default_prefilter_recommended:
        reason_codes.append("default_prefilter_not_enabled")
    safe_as_optional_cache = decision in {
        "not_needed_now",
        "evaluation_only_not_default",
        "candidate_for_optional_lookup_cache",
    }
    return {
        "decision": decision,
        "recommendation": recommendation,
        "reason": reason,
        "evidence_level": evidence_level,
        "reason_codes": unique_preserve(reason_codes, limit=12),
        "sidecar_needed_now": sidecar_needed_now,
        "needed_now": sidecar_needed_now,
        "default_prefilter_recommended": default_prefilter_recommended,
        "safe_to_enable_by_default": default_prefilter_recommended,
        "safe_as_optional_cache": safe_as_optional_cache,
        "pair_threshold": DEFAULT_PREFILTER_PAIR_THRESHOLD,
        "scale_trigger_pair_count": DEFAULT_PREFILTER_PAIR_THRESHOLD,
        "observed_pair_count": all_pair_count,
        "requires_source_ref_key_join": True,
        "required_before_default": unique_preserve(required_before_default, limit=12),
    }


def baseline_strong_pairs(
    candidates: list[QuestionCandidate],
    *,
    confirmation_fn: ConfirmationFn | None = None,
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            if not pair_is_trackable(left, right):
                continue
            decision = decide_pair(
                left,
                right,
                strong_threshold=DEFAULT_STRONG_THRESHOLD,
                borderline_threshold=1.0,
                confirmation_fn=confirmation_fn,
            )
            if decision and decision.decision == "accepted":
                pairs.add(pair_key(left.question_id, right.question_id))
    return pairs


def evaluate_question_index_sidecar(
    *,
    jobs_path: Path,
    registry_path: Path | None = None,
    index_path: Path | None = None,
    no_write: bool = False,
    max_pairs: int = DEFAULT_MAX_PAIRS,
    evidence_level: str = "current_input_structural",
) -> dict[str, Any]:
    source_index = build_source_ref_index(registry_path)
    candidates, _frontiers, input_diagnostics, _rows = load_tracking_inputs(
        jobs_path, source_index=source_index
    )
    records = records_from_candidates(candidates)
    source_signature = question_index_signature(records)
    all_pair_count = len(candidates) * max(0, len(candidates) - 1) // 2
    trackable_pair_count = sum(
        1
        for left_index, left in enumerate(candidates)
        for right in candidates[left_index + 1 :]
        if pair_is_trackable(left, right)
    )
    status = "not_requested"
    wrote = False
    sidecar_pairs: list[tuple[str, str, int]] = []
    error = ""
    if index_path:
        try:
            fresh = question_index_is_fresh(index_path, source_signature=source_signature)
            if fresh:
                status = "reused"
            elif no_write:
                status = "missing_degraded_to_baseline" if not index_path.exists() else "stale_degraded_to_baseline"
            else:
                old_exists = index_path.exists()
                write_question_index(index_path, records, source_signature=source_signature)
                status = "rebuilt_stale" if old_exists else "rebuilt_missing"
                wrote = True
            if status in {"reused", "rebuilt_stale", "rebuilt_missing"}:
                sidecar_pairs = candidate_pairs_from_index(
                    index_path,
                    allow_source_ids=[record.source_id for record in records],
                    max_pairs=max_pairs,
                )
        except (OSError, sqlite3.DatabaseError, ValueError) as exc:
            status = "error_degraded_to_baseline"
            error = compact_text(f"{type(exc).__name__}: {exc}", 260)
    by_id = {candidate.question_id: candidate for candidate in candidates}
    joined_pairs = [
        (left, right, shared)
        for left, right, shared in sidecar_pairs
        if left in by_id and right in by_id and by_id[left].source_refs and by_id[right].source_refs
    ]
    joined_pair_source_ids = sorted({source_id for pair in joined_pairs for source_id in pair[:2]})
    indexed_ref_keys = (
        load_index_source_ref_keys(index_path, joined_pair_source_ids)
        if index_path and joined_pair_source_ids
        else {}
    )
    current_ref_keys = {
        source_id: {"|".join(source_ref_key(ref)) for ref in by_id[source_id].source_refs}
        for source_id in joined_pair_source_ids
        if source_id in by_id
    }
    source_ref_key_mismatch_ids = [
        source_id
        for source_id in joined_pair_source_ids
        if not indexed_ref_keys.get(source_id)
        or not indexed_ref_keys[source_id].issubset(current_ref_keys.get(source_id, set()))
    ]
    source_ref_key_joined_pairs = [
        (left, right, shared)
        for left, right, shared in joined_pairs
        if left not in source_ref_key_mismatch_ids and right not in source_ref_key_mismatch_ids
    ]
    sidecar_pair_ids = {pair_key(left, right) for left, right, _shared in joined_pairs}
    strong_pairs = baseline_strong_pairs(candidates)
    coverage = (
        round(len(strong_pairs & sidecar_pair_ids) / len(strong_pairs), 4)
        if strong_pairs and sidecar_pairs
        else (1.0 if not strong_pairs else 0.0)
    )
    adoption_report = build_sidecar_adoption_report(
        index_requested=bool(index_path),
        status=status,
        all_pair_count=all_pair_count,
        coverage=coverage,
        source_ref_join_survived=len(source_ref_key_joined_pairs) == len(sidecar_pairs),
        evidence_level=evidence_level,
    )
    return {
        "ok": True,
        "kind": "aippocampus_question_index_sidecar_eval",
        "jobs_input": str(jobs_path),
        "registry": str(registry_path) if registry_path else None,
        "index": str(index_path) if index_path else None,
        "question_index_status": status,
        "question_index_error": error,
        "wrote": wrote,
        "candidate_count": input_diagnostics["candidate_count"],
        "stale_candidate_count": input_diagnostics["stale_candidate_count"],
        "record_count": len(records),
        "all_pair_count": all_pair_count,
        "trackable_pair_count": trackable_pair_count,
        "sidecar_pair_count": len(sidecar_pairs),
        "source_joined_pair_count": len(joined_pairs),
        "source_ref_key_joined_pair_count": len(source_ref_key_joined_pairs),
        "source_ref_key_mismatch_count": len(source_ref_key_mismatch_ids),
        "baseline_strong_pair_count": len(strong_pairs),
        "baseline_strong_pair_coverage": coverage,
        "source_ref_join_survived": len(joined_pairs) == len(sidecar_pairs),
        "source_ref_key_join_survived": len(source_ref_key_joined_pairs) == len(sidecar_pairs),
        "source_signature": source_signature,
        "max_pairs": max_pairs,
        "truth_boundary": TRUTH_BOUNDARY,
        "recommendation": adoption_report["recommendation"],
        "sidecar_adoption": adoption_report,
        "default_enablement": adoption_report,
    }


def default_index_path(registry_dir: str | None, index: str | None) -> Path | None:
    if index:
        return Path(index).resolve()
    if registry_dir:
        return Path(registry_dir).resolve() / DEFAULT_INDEX_NAME
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--jobs-input")
    parser.add_argument("--index")
    parser.add_argument("--max-pairs", type=int, default=DEFAULT_MAX_PAIRS)
    parser.add_argument("--evidence-level", default="current_input_structural")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    jobs_path = (
        Path(args.jobs_input).resolve()
        if args.jobs_input
        else default_jobs_path(args.registry, args.registry_dir)
    )
    registry_path = default_registry_path(args.registry, args.registry_dir)
    index_path = default_index_path(args.registry_dir, args.index)
    try:
        result = evaluate_question_index_sidecar(
            jobs_path=jobs_path,
            registry_path=registry_path,
            index_path=index_path,
            no_write=args.no_write,
            max_pairs=args.max_pairs,
            evidence_level=args.evidence_level,
        )
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"question candidates: {result['candidate_count']}")
        print(f"all pairs: {result['all_pair_count']}")
        print(f"sidecar pairs: {result['sidecar_pair_count']}")
        print(f"status: {result['question_index_status']}")
        print(f"recommendation: {result['recommendation']}")
        print(f"default prefilter recommended: {result['sidecar_adoption']['default_prefilter_recommended']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
