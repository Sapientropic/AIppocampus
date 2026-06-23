#!/usr/bin/env python3
"""Compensatory dream Phase 1 over source-backed extraction output.

This helper is deliberately conservative: it emits dream-synthesized candidates
for background adjudication, not facts, formal memories, or foreground hook
payloads. Every substantive bridge claim must carry thread-scoped source refs
so a later worker or operator can re-open clean source before discarding,
correcting, or routing the candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.dream.working_memory import (
    adjudicated_dream_findings_to_working_memory,  # noqa: F401
    reviewed_dream_findings_to_working_memory,  # noqa: F401
)
from aippocampus_runtime.source.io_kernel import source_ref_identity_key

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_compensatory_dream_report"
DREAM_FINDING_KIND = "dream_synthesized"
DREAM_FUNCTION = "compensatory"
REVIEW_STATE = "needs_review"
SUPPORT_LEVEL = "candidate"

CompensatoryKind = Literal[
    "approach_bias",
    "blind_spot",
    "unresolved_edge",
    "silently_recurring",
]

TECHNICAL_TERMS = {
    "api",
    "benchmark",
    "build",
    "cli",
    "code",
    "compile",
    "database",
    "debug",
    "implementation",
    "mypy",
    "runtime",
    "schema",
    "test",
    "typescript",
    "verification",
}
VERIFICATION_TERMS = {
    "acceptance",
    "benchmark",
    "evidence",
    "mypy",
    "review",
    "smoke",
    "source",
    "test",
    "verify",
}
LIFE_WIDE_LABELS = {
    "personal_reflection",
    "relationship_continuity",
    "life_context",
    "idea_seed",
    "open_question",
    "reading_notes",
    "preference",
}
LOW_SIGNAL_TERMS = {
    "question",
    "candidate",
    "thread",
    "source",
    "summary",
    "user",
    "work",
    "project",
}


@dataclass(frozen=True)
class DreamInputRow:
    row_id: str
    extraction_kind: str
    title: str
    summary: str
    source_refs: tuple[dict[str, Any], ...]
    scope_labels: tuple[str, ...]
    concepts: tuple[str, ...]
    question_text: str = ""
    frontier_type: str = ""


def stable_digest(*parts: object, prefix: str, length: int = 16) -> str:
    raw = "\n".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def source_ref_thread(ref: Mapping[str, Any]) -> str:
    return str(ref.get("thread_key") or ref.get("thread_id") or "")


def is_present(value: object) -> bool:
    return value is not None and value != ""


def normalize_source_refs(value: object, *, thread_key: str | None = None) -> tuple[dict[str, Any], ...]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    elif isinstance(value, str) and value.strip():
        raw_items = [{"source_ref": value.strip()}]
    else:
        raw_items = []

    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        ref = dict(item)
        if thread_key and not ref.get("thread_key") and not ref.get("thread_id"):
            ref["thread_key"] = thread_key
        key = source_ref_identity_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in ref.items() if is_present(v)})
    return tuple(refs)


def string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if is_present(item))
    return ()


def unique_preserve(values: Iterable[object], *, limit: int = 12) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = compact_text(str(value or ""), 90)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return tuple(out)


def text_terms(text: str) -> list[str]:
    terms = [
        token.casefold()
        for token in re.findall(r"[\w\u4e00-\u9fff]+", text, flags=re.UNICODE)
        if len(token) >= 3
    ]
    return [term for term in terms if term not in LOW_SIGNAL_TERMS]


def row_id(row: Mapping[str, Any]) -> str:
    for key in ("fingerprint", "source_finding_id", "id", "question_id"):
        value = row.get(key)
        if value:
            return str(value)
    return stable_digest(row, prefix="dreamrow", length=16)


def input_row_from_mapping(row: Mapping[str, Any], *, thread_key: str) -> DreamInputRow | None:
    refs = normalize_source_refs(row.get("source_refs") or row.get("source_ref"), thread_key=thread_key)
    refs = tuple(ref for ref in refs if source_ref_thread(ref) == thread_key)
    if not refs:
        return None
    extraction_kind = str(row.get("finding_kind") or row.get("kind") or "")
    if extraction_kind == DREAM_FINDING_KIND or extraction_kind.startswith("dream_"):
        return None
    title = compact_text(str(row.get("title") or row.get("question_short") or ""), 160)
    summary = compact_text(
        str(row.get("summary") or row.get("question_text") or row.get("boundary_reason") or ""),
        360,
    )
    labels = unique_preserve([*string_values(row.get("scope_labels")), *string_values(row.get("semantic_scope_labels"))])
    concepts = unique_preserve([*string_values(row.get("concepts")), *string_values(row.get("what_features"))])
    return DreamInputRow(
        row_id=row_id(row),
        extraction_kind=extraction_kind,
        title=title,
        summary=summary,
        source_refs=refs,
        scope_labels=labels,
        concepts=concepts,
        question_text=compact_text(str(row.get("question_text") or ""), 240),
        frontier_type=compact_text(str(row.get("frontier_type") or ""), 80),
    )


def merge_refs(rows: Iterable[DreamInputRow], *, limit: int = 10) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        for ref in row.source_refs:
            key = source_ref_identity_key(ref)
            if key in seen:
                continue
            seen.add(key)
            refs.append(dict(ref))
            if len(refs) >= limit:
                return tuple(refs)
    return tuple(refs)


def row_text(row: DreamInputRow) -> str:
    return " ".join([row.title, row.summary, row.question_text, " ".join(row.concepts), " ".join(row.scope_labels)])


def source_ref_audit(refs: Iterable[Mapping[str, Any]], *, thread_key: str) -> dict[str, Any]:
    ref_items = tuple(refs)
    thread_scoped = all(source_ref_thread(ref) == thread_key for ref in ref_items)
    return {
        "status": "structural_thread_scoped" if ref_items and thread_scoped else "failed",
        "checks": [
            "source_refs_present",
            "source_refs_thread_scoped",
            "bridge_claims_carry_source_refs",
        ],
        "ref_count": len(ref_items),
        "thread_key": thread_key,
        "clean_source_resolution": "not_checked_without_registry_index",
    }


def make_dream_finding(
    *,
    thread_key: str,
    compensatory_kind: CompensatoryKind,
    title: str,
    summary: str,
    rows: Iterable[DreamInputRow],
    bridge_claims: Iterable[str],
) -> dict[str, Any]:
    source_rows = tuple(rows)
    refs = merge_refs(source_rows)
    if not refs:
        raise ValueError("dream finding requires source refs")
    claims = [
        {
            "claim": compact_text(claim, 240),
            "source_refs": list(refs),
        }
        for claim in bridge_claims
        if str(claim).strip()
    ]
    if not claims:
        raise ValueError("dream finding requires source-ref-carried bridge claims")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_dream_finding",
        "finding_kind": DREAM_FINDING_KIND,
        "dream_function": DREAM_FUNCTION,
        "dream_phase": "phase1_compensatory",
        "compensatory_kind": compensatory_kind,
        "support_level": SUPPORT_LEVEL,
        "review_state": REVIEW_STATE,
        "foreground_eligible": False,
        "thread_key": thread_key,
        "title": compact_text(title, 140),
        "summary": compact_text(summary, 420),
        "source_refs": list(refs),
        "source_ref_audit": source_ref_audit(refs, thread_key=thread_key),
        "source_extraction_ids": [row.row_id for row in source_rows],
        "source_extraction_kinds": sorted({row.extraction_kind for row in source_rows if row.extraction_kind}),
        "bridge_claims": claims,
        "downstream_use": ["review_queue"],
        "truth_boundary": "dream_synthesized_candidate_not_fact",
    }


def build_compensatory_findings(thread_key: str, rows: Iterable[DreamInputRow]) -> list[dict[str, Any]]:
    source_rows = tuple(rows)
    if not source_rows:
        return []
    text_blob = "\n".join(row_text(row) for row in source_rows).casefold()
    term_counts = Counter(term for row in source_rows for term in text_terms(row_text(row)))
    common_terms = [term for term, count in term_counts.most_common(8) if count >= 2]
    technical = bool(set(text_terms(text_blob)) & TECHNICAL_TERMS)
    has_verification = bool(set(text_terms(text_blob)) & VERIFICATION_TERMS)
    life_wide = bool({label for row in source_rows for label in row.scope_labels} & LIFE_WIDE_LABELS)
    frontier_rows = tuple(
        row
        for row in source_rows
        if row.extraction_kind == "frontier_marker"
        or row.frontier_type in {"unresolved", "blocked", "deferred"}
    )
    question_rows = tuple(row for row in source_rows if row.extraction_kind == "question_candidate")

    findings: list[dict[str, Any]] = []
    if technical and frontier_rows and not has_verification:
        findings.append(
            make_dream_finding(
                thread_key=thread_key,
                compensatory_kind="approach_bias",
                title="Compensatory check: implementation angle lacks verification boundary",
                summary=(
                    "The thread appears to stay in implementation/problem-solving mode while an "
                    "unresolved frontier remains. Review whether a verification or acceptance "
                    "boundary is missing before this influences recall."
                ),
                rows=frontier_rows,
                bridge_claims=[
                    "A technical unresolved frontier is present in the source-backed extraction output.",
                    "The compensatory candidate should stay adjudication-only until verification evidence is attached.",
                ],
            )
        )

    if life_wide and question_rows and (common_terms or len(question_rows) >= 2):
        signal = ", ".join(common_terms[:4]) if common_terms else "repeated personal/open-question rows"
        findings.append(
            make_dream_finding(
                thread_key=thread_key,
                compensatory_kind="silently_recurring",
                title="Compensatory check: life-wide question may be recurring quietly",
                summary=(
                    f"The extraction output carries life-wide/open-question labels and repeated cues ({signal}). "
                    "Treat this as a dream-synthesized candidate for review, not as a user-profile fact."
                ),
                rows=question_rows,
                bridge_claims=[
                    "Life-wide or open-question labels appear on source-backed extraction rows.",
                    "Repeated cues suggest a possible quietly recurring question, but this remains a dream candidate.",
                ],
            )
        )

    if frontier_rows and not findings:
        findings.append(
            make_dream_finding(
                thread_key=thread_key,
                compensatory_kind="unresolved_edge",
                title="Compensatory check: unresolved edge needs review",
                summary=(
                    "The source-backed extraction output contains an unresolved boundary, but there is "
                    "not enough signal to infer a richer dream pattern."
                ),
                rows=frontier_rows,
                bridge_claims=[
                    "A frontier marker exists in the extraction output.",
                    "No broader compensatory story should be imposed from this single boundary.",
                ],
            )
        )
    return findings


def trigger_policy() -> dict[str, Any]:
    return {
        "default_frequency": "lower_than_extraction",
        "run_after_extraction_passes": 3,
        "min_source_backed_rows": 1,
        "foreground_hooks": False,
        "default_destination": "review_queue",
        "requires_adjudication_before_recall_or_reflection": True,
        # Compatibility key for older tests/callers; this means background
        # adjudication, not default human review.
        "requires_review_before_recall_or_reflection": True,
    }


def run_compensatory_dream(
    *,
    thread_key: str,
    extraction_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    raw_rows = tuple(extraction_rows)
    rows = tuple(
        item
        for item in (input_row_from_mapping(row, thread_key=thread_key) for row in raw_rows)
        if item is not None
    )
    findings = build_compensatory_findings(thread_key, rows)
    missing_source_count = 0
    for row in raw_rows:
        refs = normalize_source_refs(row.get("source_refs") or row.get("source_ref"), thread_key=thread_key)
        if not refs and str(row.get("thread_key") or row.get("thread_id") or "") == thread_key:
            missing_source_count += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "created_at": now_utc(),
        "thread_key": thread_key,
        "dream_function": DREAM_FUNCTION,
        "dream_phase": "phase1_compensatory",
        "support_level": SUPPORT_LEVEL,
        "review_state": REVIEW_STATE,
        "foreground_eligible": False,
        "status": "candidate_emitted" if findings else "no_source_backed_pattern",
        "input": {
            "source_backed_row_count": len(rows),
            "missing_source_row_count": missing_source_count,
            "extraction_kinds": sorted({row.extraction_kind for row in rows if row.extraction_kind}),
        },
        "trigger_policy": trigger_policy(),
        "findings": findings,
        "can_claim": [
            "phase1_compensatory_dream_candidates_carry_thread_scoped_source_refs",
        ],
        "cannot_claim": [
            "dream_output_is_fact",
            "clean_source_ref_resolution_without_registry_index",
            "formal_memory_promotion_without_review",
            "foreground_hook_eligibility",
            "prospective_analysis",
            "amplification",
            "active_imagination",
            "private_real_history_dream_quality",
        ],
    }


def fixture_rows(case: str) -> tuple[str, list[dict[str, Any]]]:
    if case == "empty":
        return "session:empty", []
    if case == "technical":
        return "session:technical", [
            {
                "fingerprint": "sf_frontier_technical",
                "finding_kind": "frontier_marker",
                "thread_key": "session:technical",
                "title": "Runtime implementation blocked",
                "summary": "The implementation path is blocked on CLI behavior.",
                "frontier_type": "blocked",
                "concepts": ["runtime", "implementation", "CLI"],
                "source_refs": [{"thread_key": "session:technical", "message_id": "msg-tech-1"}],
            }
        ]
    if case == "personal":
        return "session:personal", [
            {
                "fingerprint": "sf_question_personal_1",
                "finding_kind": "question_candidate",
                "thread_key": "session:personal",
                "question_text": "Why does this anxiety keep returning when the work changes shape?",
                "question_short": "recurring anxiety around changing work",
                "scope_labels": ["personal_reflection", "open_question"],
                "concepts": ["anxiety", "change", "continuity"],
                "source_refs": [{"thread_key": "session:personal", "message_id": "msg-personal-1"}],
            },
            {
                "fingerprint": "sf_question_personal_2",
                "finding_kind": "question_candidate",
                "thread_key": "session:personal",
                "question_text": "The same anxiety returns, but now it appears as an idea about continuity.",
                "question_short": "anxiety becoming continuity idea",
                "scope_labels": ["personal_reflection", "idea_seed", "open_question"],
                "concepts": ["anxiety", "continuity", "idea"],
                "source_refs": [{"thread_key": "session:personal", "message_id": "msg-personal-2"}],
            },
        ]
    raise ValueError(f"unknown fixture case: {case}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run compensatory dream Phase 1 helper.")
    parser.add_argument("--fixture", choices=("empty", "technical", "personal"), default="technical")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path, help="Optional output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    thread_key, rows = fixture_rows(args.fixture)
    payload = run_compensatory_dream(thread_key=thread_key, extraction_rows=rows)
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
