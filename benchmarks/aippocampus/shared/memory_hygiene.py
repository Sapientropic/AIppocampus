"""Synthetic stale/update/delete/dedup memory hygiene fixtures.

This module is a Track A companion report, not a live learning engine. It keeps
#990's multi-turn failure modes as public-safe fixture rows so the memory
decision benchmark can prove stale, superseded, duplicate, suppressed, and fuzzy
navigation surfaces remain below source evidence unless a current clean-source
route is available.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.aippocampus.shared.benchmark_entrypoints import library_only_main

MEMORY_HYGIENE_CANNOT_CLAIM = [
    "online_memory_update_learning",
    "physical_source_row_deletion",
    "similarity_dedup_as_truth_source",
    "real_history_memory_hygiene_quality",
    "full_evidence_drawer_ux",
]
REQUIRED_STATUSES = {
    "current",
    "stale",
    "superseded",
    "duplicate",
    "suppressed",
    "fuzzy_navigation",
}


@dataclass(frozen=True)
class HygieneRow:
    row_id: str
    status: str
    action_grammar: str
    source_ref: str
    duplicate_key: str
    display_eligible: bool
    evidence_eligible: bool
    source_available: bool
    note: str
    private_text: str


@dataclass(frozen=True)
class HygieneCase:
    case_id: str
    scenario: str
    query_shape: str
    expected_evidence_row_id: str | None
    boundary_note: str
    rows: tuple[HygieneRow, ...]


def _sha256_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def memory_hygiene_cases() -> list[HygieneCase]:
    return [
        HygieneCase(
            case_id="stale_preference_corrected_later",
            scenario="preference_update_chain",
            query_shape="old lexical match competes with later correction",
            expected_evidence_row_id="pref-b-current",
            boundary_note=(
                "A later clean-source correction must outrank a lexically matching "
                "superseded preference."
            ),
            rows=(
                HygieneRow(
                    "pref-a-old",
                    "superseded",
                    "ignore_or_blocked",
                    "src:preference-a",
                    "",
                    False,
                    False,
                    True,
                    "old preference is retained as provenance only",
                    "User first preferred library X.",
                ),
                HygieneRow(
                    "pref-b-current",
                    "current",
                    "bounded_evidence",
                    "src:preference-b-correction",
                    "",
                    True,
                    True,
                    True,
                    "later source-backed correction is the only evidence row",
                    "User later corrected the preference: do not use X; use Y.",
                ),
            ),
        ),
        HygieneCase(
            case_id="duplicate_paraphrase_cluster_collapses_display",
            scenario="duplicate_semantic_memory",
            query_shape="four paraphrases of one source-backed fact",
            expected_evidence_row_id="runtime-pref-canonical",
            boundary_note=(
                "Duplicate display rows collapse, but every source ref remains in "
                "the duplicate provenance group."
            ),
            rows=(
                HygieneRow(
                    "runtime-pref-canonical",
                    "current",
                    "bounded_evidence",
                    "src:runtime-pref-canonical",
                    "runtime-pref",
                    True,
                    True,
                    True,
                    "canonical route selected for display and evidence",
                    "User chose the runtime sidecar path.",
                ),
                HygieneRow(
                    "runtime-pref-para-1",
                    "duplicate",
                    "direction_with_ref",
                    "src:runtime-pref-para-1",
                    "runtime-pref",
                    True,
                    False,
                    True,
                    "duplicate paraphrase retained as provenance",
                    "The sidecar runtime direction was favored.",
                ),
                HygieneRow(
                    "runtime-pref-para-2",
                    "duplicate",
                    "direction_with_ref",
                    "src:runtime-pref-para-2",
                    "runtime-pref",
                    True,
                    False,
                    True,
                    "duplicate paraphrase retained as provenance",
                    "Runtime helper approach was preferred.",
                ),
                HygieneRow(
                    "runtime-pref-para-3",
                    "duplicate",
                    "direction_with_ref",
                    "src:runtime-pref-para-3",
                    "runtime-pref",
                    True,
                    False,
                    True,
                    "duplicate paraphrase retained as provenance",
                    "The Go-style helper path stayed attractive.",
                ),
            ),
        ),
        HygieneCase(
            case_id="deterministic_constraint_beats_fuzzy_hint",
            scenario="deterministic_vs_fuzzy_route",
            query_shape="deterministic constraint competes with fuzzy semantic hint",
            expected_evidence_row_id="typed-routing-constraint",
            boundary_note=(
                "A deterministic source-backed constraint can be evidence; a fuzzy "
                "semantic vibe remains direction_only."
            ),
            rows=(
                HygieneRow(
                    "typed-routing-constraint",
                    "current",
                    "bounded_evidence",
                    "src:typed-routing-constraint",
                    "",
                    True,
                    True,
                    True,
                    "deterministic constraint is current and source-backed",
                    "User said TypeScript/Rust are preferred main languages.",
                ),
                HygieneRow(
                    "atlas-vibe-fuzzy",
                    "fuzzy_navigation",
                    "direction_only",
                    "sidecar:fuzzy-atlas-vibe",
                    "",
                    True,
                    False,
                    False,
                    "fuzzy hint can route attention but cannot support a claim",
                    "The project feels Atlas-like and dashboard-shaped.",
                ),
            ),
        ),
        HygieneCase(
            case_id="suppressed_recall_with_pin_boundary",
            scenario="suppress_correct_pin",
            query_shape="user suppresses a recalled memory and pins a correction",
            expected_evidence_row_id="pin-current-boundary",
            boundary_note=(
                "Suppression blocks the recalled row; the pinned correction carries "
                "the reopenable boundary."
            ),
            rows=(
                HygieneRow(
                    "old-recalled-memory",
                    "suppressed",
                    "ignore_or_blocked",
                    "src:old-recalled-memory",
                    "",
                    False,
                    False,
                    True,
                    "explicit user suppression prevents foreground use",
                    "A recalled memory suggested the old project name.",
                ),
                HygieneRow(
                    "pin-current-boundary",
                    "current",
                    "bounded_evidence",
                    "src:user-pinned-correction",
                    "",
                    True,
                    True,
                    True,
                    "pin/correction is represented as the current boundary",
                    "User pinned the correction: do not use the old project name.",
                ),
            ),
        ),
        HygieneCase(
            case_id="stale_candidate_without_refresh_abstains",
            scenario="stale_review_after_expired",
            query_shape="stale candidate has no recent source reopen",
            expected_evidence_row_id=None,
            boundary_note=(
                "A stale row with no refresh route may remain navigation at most; "
                "it should not become evidence by itself."
            ),
            rows=(
                HygieneRow(
                    "stale-without-refresh",
                    "stale",
                    "direction_only",
                    "src:stale-candidate",
                    "",
                    True,
                    False,
                    False,
                    "review_after expired and no reopenable source is available",
                    "Old note says the release date is tomorrow.",
                ),
            ),
        ),
        HygieneCase(
            case_id="deleted_note_keeps_clean_source_trail",
            scenario="delete_note_preserve_source",
            query_shape="edited/deleted note should not delete clean source provenance",
            expected_evidence_row_id="clean-source-after-note-delete",
            boundary_note=(
                "Deleting a note removes the note from display, not the original "
                "clean-source trail."
            ),
            rows=(
                HygieneRow(
                    "deleted-note",
                    "suppressed",
                    "ignore_or_blocked",
                    "note:deleted-preference-summary",
                    "",
                    False,
                    False,
                    False,
                    "deleted note is absent from foreground display",
                    "A hand-edited note summary was deleted.",
                ),
                HygieneRow(
                    "clean-source-after-note-delete",
                    "current",
                    "bounded_evidence",
                    "src:original-clean-source",
                    "",
                    True,
                    True,
                    True,
                    "original clean source remains reopenable",
                    "Original source row still records the user's correction.",
                ),
            ),
        ),
    ]


def _public_row(row: HygieneRow) -> dict[str, Any]:
    return {
        "row_id": row.row_id,
        "status": row.status,
        "action_grammar": row.action_grammar,
        "source_ref_hash": _sha256_short(row.source_ref),
        "duplicate_key_hash": _sha256_short(row.duplicate_key) if row.duplicate_key else "",
        "display_eligible": row.display_eligible,
        "evidence_eligible": row.evidence_eligible,
        "source_available": row.source_available,
        "note": row.note,
    }


def _display_rows(rows: tuple[HygieneRow, ...]) -> tuple[list[HygieneRow], int]:
    display: list[HygieneRow] = []
    seen_duplicate_keys: set[str] = set()
    collapsed = 0
    for row in rows:
        if not row.display_eligible:
            continue
        if row.duplicate_key:
            if row.duplicate_key in seen_duplicate_keys:
                collapsed += 1
                continue
            seen_duplicate_keys.add(row.duplicate_key)
        display.append(row)
    return display, collapsed


def _duplicate_provenance(rows: tuple[HygieneRow, ...]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.duplicate_key:
            grouped[row.duplicate_key].append(_sha256_short(row.source_ref))
    return {key: refs for key, refs in grouped.items() if len(refs) > 1}


def evaluate_memory_hygiene_case(
    case: HygieneCase,
    *,
    include_private_text: bool = False,
) -> dict[str, Any]:
    display_rows, collapsed_duplicate_count = _display_rows(case.rows)
    evidence_rows = [
        row
        for row in display_rows
        if row.evidence_eligible and row.source_available and row.action_grammar == "bounded_evidence"
    ]
    selected = evidence_rows[0] if evidence_rows else None
    stale_or_superseded_dominance_failure = any(
        row.evidence_eligible and row.status in {"stale", "superseded"}
        for row in case.rows
    )
    unsupported_evidence_rows = [
        row.row_id
        for row in case.rows
        if row.evidence_eligible
        and (
            row.status in {"stale", "superseded", "duplicate", "suppressed", "fuzzy_navigation"}
            or row.action_grammar != "bounded_evidence"
            or not row.source_available
        )
    ]
    evidence_winner_ok = (
        selected.row_id if selected is not None else None
    ) == case.expected_evidence_row_id
    duplicate_provenance = _duplicate_provenance(case.rows)
    source_refs = {_sha256_short(row.source_ref) for row in case.rows if row.source_ref}
    payload: dict[str, Any] = {
        "case_id": case.case_id,
        "scenario": case.scenario,
        "query_shape": case.query_shape,
        "public_pain_family": "stale_update_delete_dedup",
        "expected_evidence_row_id": case.expected_evidence_row_id,
        "selected_evidence_row_id": selected.row_id if selected else None,
        "evidence_winner_ok": evidence_winner_ok,
        "passed": evidence_winner_ok
        and not stale_or_superseded_dominance_failure
        and not unsupported_evidence_rows,
        "status_counts": dict(Counter(row.status for row in case.rows)),
        "display_row_ids": [row.row_id for row in display_rows],
        "display_collapsed_duplicate_count": collapsed_duplicate_count,
        "duplicate_provenance_ref_hashes": duplicate_provenance,
        "source_provenance_hash_count": len(source_refs),
        "source_provenance_intact": bool(source_refs),
        "stale_or_superseded_evidence_dominance_failure": (
            stale_or_superseded_dominance_failure
        ),
        "unsupported_evidence_row_ids": unsupported_evidence_rows,
        "boundary_note": case.boundary_note,
        "rows": [_public_row(row) for row in case.rows],
    }
    if include_private_text:
        payload["private_timeline_text"] = [row.private_text for row in case.rows]
    return payload


def run_memory_hygiene_fixture_report(*, include_private_text: bool = False) -> dict[str, Any]:
    cases = [
        evaluate_memory_hygiene_case(case, include_private_text=include_private_text)
        for case in memory_hygiene_cases()
    ]
    status_counts: Counter[str] = Counter()
    for case in cases:
        status_counts.update(case["status_counts"])
    metrics = {
        "case_count": len(cases),
        "multi_turn_case_count": len(cases),
        "passed_count": sum(1 for case in cases if case["passed"]),
        "failed_count": sum(1 for case in cases if not case["passed"]),
        "status_counts": dict(status_counts),
        "required_statuses_covered": REQUIRED_STATUSES <= set(status_counts),
        "stale_or_superseded_evidence_dominance_failures": sum(
            1 for case in cases if case["stale_or_superseded_evidence_dominance_failure"]
        ),
        "unsupported_evidence_row_count": sum(
            len(case["unsupported_evidence_row_ids"]) for case in cases
        ),
        "duplicate_display_collapse_count": sum(
            int(case["display_collapsed_duplicate_count"]) for case in cases
        ),
        "duplicate_provenance_retained_case_count": sum(
            1 for case in cases if case["duplicate_provenance_ref_hashes"]
        ),
        "suppressed_or_pinned_boundary_case_count": sum(
            1
            for case in cases
            if {"suppressed", "current"} <= set(case["status_counts"])
            and "pin" in str(case["boundary_note"]).casefold()
        ),
        "source_provenance_intact_case_count": sum(
            1 for case in cases if case["source_provenance_intact"]
        ),
    }
    ok = (
        metrics["case_count"] >= 5
        and metrics["passed_count"] == metrics["case_count"]
        and metrics["required_statuses_covered"]
        and metrics["stale_or_superseded_evidence_dominance_failures"] == 0
        and metrics["unsupported_evidence_row_count"] == 0
        and metrics["duplicate_display_collapse_count"] >= 1
        and metrics["duplicate_provenance_retained_case_count"] >= 1
        and metrics["suppressed_or_pinned_boundary_case_count"] >= 1
    )
    return {
        "schema_version": 1,
        "kind": "memory_hygiene_fixture_report",
        "source_issue": "https://github.com/Sapientropic/AIppocampus/issues/990",
        "source_map": "docs/research/memory-system-pain-taxonomy.md",
        "ok": ok,
        "metrics": metrics,
        "cases": cases,
        "privacy_boundary": {
            "raw_timeline_text_emitted": bool(include_private_text),
            "source_ref_values_emitted": False,
            "absolute_paths_emitted": False,
        },
        "claim_boundary": (
            "Synthetic multi-turn hygiene fixtures for report/evidence boundaries; "
            "not a live online-learning, deletion, or real-history quality claim."
        ),
        "cannot_claim": MEMORY_HYGIENE_CANNOT_CLAIM,
    }


if __name__ == "__main__":
    raise SystemExit(
        library_only_main(
            module_path="benchmarks/aippocampus/shared/memory_hygiene.py",
            supported_runner="benchmarks/aippocampus/benchmark_memory_decision_gate.py",
            summary="It provides #990 memory-hygiene companion fixtures.",
        )
    )
