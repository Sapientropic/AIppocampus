"""Synthetic Markdown/note-backed memory drift fixtures.

These #987 fixtures model editable memory notes, generated summaries, topic
notes, and curated note routes that can drift away from clean source. The
report is a companion to the memory decision benchmark: notes may navigate, but
clean source remains the evidence surface and exact claims still require a
source-open or bounded-evidence path.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any

NOTE_DRIFT_CANNOT_CLAIM = [
    "full_obsidian_or_vault_integration",
    "user_authored_notes_forbidden",
    "every_note_is_exact_evidence",
    "live_markdown_vault_quality",
    "note_deletion_deletes_clean_source",
]


@dataclass(frozen=True)
class NoteDriftRow:
    row_id: str
    artifact_kind: str
    status: str
    action_grammar: str
    source_ref: str
    source_available: bool
    display_eligible: bool
    evidence_eligible: bool
    exact_claim_requires_source_open: bool
    note_mutation_rewrites_source: bool
    note: str
    private_text: str


@dataclass(frozen=True)
class NoteDriftCase:
    case_id: str
    scenario: str
    expected_evidence_row_id: str | None
    boundary_note: str
    rows: tuple[NoteDriftRow, ...]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def note_memory_drift_cases() -> list[NoteDriftCase]:
    return [
        NoteDriftCase(
            case_id="memory_md_preference_corrected_by_clean_source",
            scenario="markdown_memory_later_correction",
            expected_evidence_row_id="clean-source-correction-y",
            boundary_note=(
                "A stale MEMORY.md preference can route attention, but the later "
                "clean-source correction is the only evidence row."
            ),
            rows=(
                NoteDriftRow(
                    "memory-md-pref-x",
                    "markdown_memory",
                    "superseded",
                    "direction_only",
                    "note:MEMORY.md#library-x",
                    False,
                    True,
                    False,
                    True,
                    False,
                    "stale note says library X is preferred",
                    "MEMORY.md: user prefers library X.",
                ),
                NoteDriftRow(
                    "clean-source-correction-y",
                    "clean_source",
                    "current_correction",
                    "bounded_evidence",
                    "src:later-correction-library-y",
                    True,
                    True,
                    True,
                    False,
                    False,
                    "later clean source corrects the preference",
                    "Later clean source: do not use X; use library Y.",
                ),
            ),
        ),
        NoteDriftCase(
            case_id="hand_edited_topic_note_without_source_ref",
            scenario="unsourced_hand_edited_topic_note",
            expected_evidence_row_id=None,
            boundary_note="A hand-edited topic note without a source ref is navigation only.",
            rows=(
                NoteDriftRow(
                    "topic-note-unsourced",
                    "topic_note",
                    "unsourced",
                    "direction_only",
                    "",
                    False,
                    True,
                    False,
                    True,
                    False,
                    "unsourced topic note cannot support exact claims",
                    "Topic note: the user always wants framework Z.",
                ),
            ),
        ),
        NoteDriftCase(
            case_id="generated_summary_merges_same_name_entities",
            scenario="generated_summary_same_name_merge",
            expected_evidence_row_id=None,
            boundary_note=(
                "A generated summary that merges same-name entities is an advisory "
                "route, not evidence."
            ),
            rows=(
                NoteDriftRow(
                    "summary-merged-atlas",
                    "generated_summary",
                    "contested",
                    "direction_only",
                    "summary:atlas-merged",
                    False,
                    True,
                    False,
                    True,
                    False,
                    "summary merged two same-name Atlas projects",
                    "Generated summary: Atlas project preference applies everywhere.",
                ),
                NoteDriftRow(
                    "atlas-current-source-route",
                    "clean_source",
                    "route_candidate",
                    "reopenable_route",
                    "src:atlas-current-project",
                    True,
                    True,
                    False,
                    True,
                    False,
                    "current Atlas source can be reopened before claiming",
                    "Clean source distinguishes current AIppocampus Atlas.",
                ),
                NoteDriftRow(
                    "atlas-other-source-route",
                    "clean_source",
                    "route_candidate",
                    "reopenable_route",
                    "src:atlas-other-project",
                    True,
                    True,
                    False,
                    True,
                    False,
                    "other Atlas source can be reopened before claiming",
                    "Clean source distinguishes another dashboard Atlas.",
                ),
            ),
        ),
        NoteDriftCase(
            case_id="deleted_note_preserves_original_clean_source",
            scenario="note_delete_or_edit_preserves_source",
            expected_evidence_row_id="original-clean-source-after-delete",
            boundary_note=(
                "Deleting or editing a note removes note navigation; it must not "
                "delete or rewrite the original clean-source trail."
            ),
            rows=(
                NoteDriftRow(
                    "deleted-memory-note",
                    "markdown_memory",
                    "deleted_or_edited",
                    "ignore_or_blocked",
                    "note:deleted-memory-summary",
                    False,
                    False,
                    False,
                    True,
                    False,
                    "deleted note is not displayed as memory",
                    "Deleted note once summarized a preference.",
                ),
                NoteDriftRow(
                    "original-clean-source-after-delete",
                    "clean_source",
                    "current",
                    "bounded_evidence",
                    "src:original-clean-source-after-note-delete",
                    True,
                    True,
                    True,
                    False,
                    False,
                    "original source remains intact after note deletion",
                    "Original clean source is still reopenable.",
                ),
            ),
        ),
        NoteDriftCase(
            case_id="source_backed_note_routes_to_reopen",
            scenario="source_backed_note_route",
            expected_evidence_row_id=None,
            boundary_note=(
                "A source-backed note may expose a reopen route, but the note body "
                "is not exact evidence by itself."
            ),
            rows=(
                NoteDriftRow(
                    "source-backed-note-route",
                    "curated_note",
                    "source_backed_route",
                    "reopenable_route",
                    "src:curated-note-support",
                    True,
                    True,
                    False,
                    True,
                    False,
                    "source-backed note can route to source reopen",
                    "Curated note points at a supporting source ref.",
                ),
            ),
        ),
        NoteDriftCase(
            case_id="note_ref_cannot_be_reopened",
            scenario="unreopenable_note_ref",
            expected_evidence_row_id=None,
            boundary_note=(
                "A note with a broken or missing source ref is navigation only and "
                "cannot support evidence claims."
            ),
            rows=(
                NoteDriftRow(
                    "broken-source-note",
                    "curated_note",
                    "unreopenable",
                    "direction_only",
                    "src:missing-note-support",
                    False,
                    True,
                    False,
                    True,
                    False,
                    "source ref is present but cannot be reopened",
                    "Curated note points at a missing source ref.",
                ),
            ),
        ),
    ]


def _public_row(row: NoteDriftRow) -> dict[str, Any]:
    return {
        "row_id": row.row_id,
        "artifact_kind": row.artifact_kind,
        "status": row.status,
        "action_grammar": row.action_grammar,
        "source_ref_hash": _hash(row.source_ref) if row.source_ref else "",
        "source_available": row.source_available,
        "display_eligible": row.display_eligible,
        "evidence_eligible": row.evidence_eligible,
        "exact_claim_requires_source_open": row.exact_claim_requires_source_open,
        "note_mutation_rewrites_source": row.note_mutation_rewrites_source,
        "note": row.note,
    }


def evaluate_note_memory_drift_case(
    case: NoteDriftCase,
    *,
    include_private_text: bool = False,
) -> dict[str, Any]:
    evidence_rows = [
        row
        for row in case.rows
        if row.display_eligible
        and row.evidence_eligible
        and row.source_available
        and row.action_grammar == "bounded_evidence"
    ]
    selected = evidence_rows[0] if evidence_rows else None
    unsupported_note_evidence_rows = [
        row.row_id
        for row in case.rows
        if row.artifact_kind != "clean_source"
        and (
            row.evidence_eligible
            or row.action_grammar == "bounded_evidence"
            or not row.exact_claim_requires_source_open
        )
    ]
    unsourced_or_unreopenable_note_rows = [
        row.row_id
        for row in case.rows
        if row.artifact_kind != "clean_source"
        and (not row.source_ref or not row.source_available)
        and row.action_grammar in {"direction_only", "ignore_or_blocked"}
        and not row.evidence_eligible
    ]
    source_route_rows = [
        row.row_id
        for row in case.rows
        if row.artifact_kind != "clean_source"
        and row.source_available
        and row.action_grammar == "reopenable_route"
        and not row.evidence_eligible
        and row.exact_claim_requires_source_open
    ]
    note_mutation_rewrites_source = any(row.note_mutation_rewrites_source for row in case.rows)
    selected_ok = (
        selected.row_id if selected is not None else None
    ) == case.expected_evidence_row_id
    passed = selected_ok and not unsupported_note_evidence_rows and not note_mutation_rewrites_source
    payload: dict[str, Any] = {
        "case_id": case.case_id,
        "scenario": case.scenario,
        "public_pain_family": "markdown_note_memory_drift",
        "expected_evidence_row_id": case.expected_evidence_row_id,
        "selected_evidence_row_id": selected.row_id if selected else None,
        "selected_corrected_clean_source": bool(
            selected is not None
            and selected.artifact_kind == "clean_source"
            and selected.status in {"current", "current_correction"}
        ),
        "selected_evidence_ok": selected_ok,
        "unsupported_note_evidence_row_ids": unsupported_note_evidence_rows,
        "unsourced_or_unreopenable_navigation_row_ids": unsourced_or_unreopenable_note_rows,
        "source_backed_note_reopen_route_row_ids": source_route_rows,
        "note_mutation_rewrites_source": note_mutation_rewrites_source,
        "exact_claim_requires_source_open_count": sum(
            1 for row in case.rows if row.exact_claim_requires_source_open
        ),
        "status_counts": dict(Counter(row.status for row in case.rows)),
        "artifact_kind_counts": dict(Counter(row.artifact_kind for row in case.rows)),
        "boundary_note": case.boundary_note,
        "rows": [_public_row(row) for row in case.rows],
        "passed": passed,
    }
    if include_private_text:
        payload["private_note_text"] = [row.private_text for row in case.rows]
    return payload


def run_note_memory_drift_fixture_report(*, include_private_text: bool = False) -> dict[str, Any]:
    cases = [
        evaluate_note_memory_drift_case(case, include_private_text=include_private_text)
        for case in note_memory_drift_cases()
    ]
    status_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    for case in cases:
        status_counts.update(case["status_counts"])
        kind_counts.update(case["artifact_kind_counts"])
    metrics = {
        "case_count": len(cases),
        "passed_count": sum(1 for case in cases if case["passed"]),
        "failed_count": sum(1 for case in cases if not case["passed"]),
        "status_counts": dict(status_counts),
        "artifact_kind_counts": dict(kind_counts),
        "corrected_clean_source_preferred_count": sum(
            1 for case in cases if case["selected_corrected_clean_source"]
        ),
        "unsupported_note_evidence_count": sum(
            len(case["unsupported_note_evidence_row_ids"]) for case in cases
        ),
        "unsourced_or_unreopenable_navigation_only_count": sum(
            len(case["unsourced_or_unreopenable_navigation_row_ids"]) for case in cases
        ),
        "source_backed_note_reopen_route_count": sum(
            len(case["source_backed_note_reopen_route_row_ids"]) for case in cases
        ),
        "note_mutation_rewrites_source_count": sum(
            1 for case in cases if case["note_mutation_rewrites_source"]
        ),
        "exact_claim_requires_source_open_count": sum(
            int(case["exact_claim_requires_source_open_count"]) for case in cases
        ),
        "delete_or_edit_preserves_source_case_count": sum(
            1
            for case in cases
            if "deleted_or_edited" in case["status_counts"]
            and case["selected_corrected_clean_source"]
            and not case["note_mutation_rewrites_source"]
        ),
    }
    ok = (
        metrics["case_count"] >= 5
        and metrics["passed_count"] == metrics["case_count"]
        and metrics["corrected_clean_source_preferred_count"] >= 2
        and metrics["unsupported_note_evidence_count"] == 0
        and metrics["unsourced_or_unreopenable_navigation_only_count"] >= 2
        and metrics["source_backed_note_reopen_route_count"] >= 1
        and metrics["delete_or_edit_preserves_source_case_count"] >= 1
        and metrics["note_mutation_rewrites_source_count"] == 0
    )
    return {
        "schema_version": 1,
        "kind": "note_memory_drift_fixture_report",
        "source_issue": "https://github.com/Sapientropic/AIppocampus/issues/987",
        "source_map": "docs/research/memory-system-pain-taxonomy.md",
        "ok": ok,
        "metrics": metrics,
        "cases": cases,
        "privacy_boundary": {
            "raw_note_text_emitted": bool(include_private_text),
            "source_ref_values_emitted": False,
            "absolute_paths_emitted": False,
        },
        "claim_boundary": (
            "Synthetic note-backed memory drift fixtures. Editable notes are "
            "navigation unless source-open or bounded clean-source evidence is available."
        ),
        "cannot_claim": NOTE_DRIFT_CANNOT_CLAIM,
    }
