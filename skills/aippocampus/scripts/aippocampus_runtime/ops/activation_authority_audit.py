#!/usr/bin/env python3
"""Deterministic authority audit for non-source activation surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from aippocampus_runtime.ops.activation_dead_letter import (
        DEAD_LETTER_REPORT_KIND,
        DEFAULT_FALSE_POSITIVE_THRESHOLD,
        DEFAULT_NO_SOURCE_REOPEN_THRESHOLD,
        DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD,
        activation_dead_letter_candidate_report_from_rows,
        apply_dead_letter_candidate_manifest_from_rows,
    )
    from aippocampus_runtime.ops.activation_lifecycle_manifest import (
        apply_activation_lifecycle_manifest_from_rows,
    )
except ModuleNotFoundError:  # pragma: no cover - direct file execution fallback
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from aippocampus_runtime.ops.activation_dead_letter import (
        DEAD_LETTER_REPORT_KIND,
        DEFAULT_FALSE_POSITIVE_THRESHOLD,
        DEFAULT_NO_SOURCE_REOPEN_THRESHOLD,
        DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD,
        activation_dead_letter_candidate_report_from_rows,
        apply_dead_letter_candidate_manifest_from_rows,
    )
    from aippocampus_runtime.ops.activation_lifecycle_manifest import (
        apply_activation_lifecycle_manifest_from_rows,
    )

AUTHORITY_AUDIT_KIND = "aippocampus_activation_surface_authority_audit"
AUTHORITY_SCHEMA_VERSION = 1

AUTHORITY_LEVELS = {
    "candidate": "Navigation hint only; may seed search or attention.",
    "advisory": "May bias attention or suggest a check; cannot prove a claim.",
    "guardrail": "May block or slow a risky action until source/current state is checked.",
    "source_required": "Requires source reopen or equivalent evidence before claims/actions.",
    "blocked": "Not eligible for foreground use until a later review changes state.",
}

SURFACE_DEFAULT_AUTHORITY = {
    "aar_nudge": "advisory",
    "dream_hypothesis": "candidate",
    "working_memory": "advisory",
    "semantic_trigger": "candidate",
    "ambient_card": "candidate",
    "active_recall_lock": "advisory",
    "pruning_row": "guardrail",
}

SOURCE_EVIDENCE_KINDS = {"source_reopen_evidence", "current_checkout_evidence"}
USER_CORRECTION_KIND = "explicit_user_correction"
ACTIVATION_SURFACE_KINDS = set(SURFACE_DEFAULT_AUTHORITY)
PRUNING_ACTIONS = {"keep", "demote", "park", "supersede", "retire"}
BLOCKING_PRUNING_ACTIONS = {"park", "supersede", "retire"}
FOREGROUND_REDUCTION_ACTIONS = {"demote", "park", "supersede", "retire"}
FRESHNESS_PENALTY = {"stale": 35, "superseded": 80}
SOURCE_REF_KEYS = (
    "source_id",
    "stable_source_id",
    "thread_key",
    "message_id",
    "turn_id",
    "turn_index",
    "line",
    "source_line",
)
PROTECTED_REFERENCE_FIELDS = (
    "referenced_by",
    "promotion_candidate_refs",
    "dream_input_refs",
    "review_artifact_refs",
    "question_link_refs",
    "source_reopen_evidence_refs",
)
SENSITIVE_LABEL_REDACTION = "<redacted-sensitive-label>"
_SECRETISH_RE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})")
_LOCAL_LOCATOR_RE = re.compile(
    r"([A-Za-z]:\\|/" + r"Users/|/" + r"home/[^/]+/|\\\\[^\\]+\\)"
)


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _public_label(value: Any, default: str) -> str:
    text = _text(value, default)
    if _SECRETISH_RE.search(text) or _LOCAL_LOCATOR_RE.search(text):
        return SENSITIVE_LABEL_REDACTION
    return text[:160]


def _public_hash(value: Any, default: str = "unknown") -> str:
    return hashlib.sha1(_public_label(value, default).encode("utf-8")).hexdigest()[:16]


def _safe_ref_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if _SECRETISH_RE.search(value) or _LOCAL_LOCATOR_RE.search(value):
        return SENSITIVE_LABEL_REDACTION
    return value[:160]


def _safe_source_refs(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        items: Iterable[Any] = [value]
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        ref: dict[str, Any] = {}
        for key in SOURCE_REF_KEYS:
            value = item.get(key)
            if value in {None, ""}:
                continue
            out_key = "line" if key == "source_line" else key
            if out_key == "stable_source_id":
                out_key = "source_id"
            ref[out_key] = _safe_ref_value(value)
        if not ref:
            continue
        marker = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(ref)
    return refs


def _as_sequence(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _protected_reference_count(row: Mapping[str, Any]) -> int:
    total = 0
    for key in PROTECTED_REFERENCE_FIELDS:
        total += len(_as_sequence(row.get(key)))
    for key in (
        "promotion_candidate_ref_count",
        "dream_input_ref_count",
        "review_artifact_ref_count",
        "question_link_ref_count",
        "source_reopen_evidence_ref_count",
    ):
        total += _int(row.get(key))
    return total


def _authority_level(row: Mapping[str, Any], surface_kind: str) -> str:
    action = _text(row.get("pruning_action") or row.get("lifecycle_action"))
    if surface_kind == "pruning_row" and action in BLOCKING_PRUNING_ACTIONS:
        return "blocked"
    raw = _text(row.get("authority_level"))
    if raw in AUTHORITY_LEVELS:
        return raw
    return SURFACE_DEFAULT_AUTHORITY.get(surface_kind, "candidate")


def _resolution_class(surface_kind: str, authority_level: str) -> str:
    if surface_kind == USER_CORRECTION_KIND:
        return USER_CORRECTION_KIND
    if surface_kind in SOURCE_EVIDENCE_KINDS:
        return surface_kind
    return authority_level


def _base_rank(surface_kind: str, authority_level: str) -> int:
    if surface_kind == USER_CORRECTION_KIND:
        return 1000
    if surface_kind == "current_checkout_evidence":
        return 900
    if surface_kind == "source_reopen_evidence":
        return 850
    if authority_level == "blocked":
        return 760
    if authority_level == "guardrail":
        return 650
    if authority_level == "source_required":
        return 560
    if authority_level == "advisory":
        return 320
    return 180


def normalize_activation_surface(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a public-safe authority row for audit output."""

    surface_kind = _text(row.get("surface_kind") or row.get("kind"), "unknown")
    authority_level = _authority_level(row, surface_kind)
    source_refs = _safe_source_refs(row.get("source_refs") or row.get("evidence_refs") or [])
    pruning_action = _text(row.get("pruning_action") or row.get("lifecycle_action") or "none")
    if pruning_action not in PRUNING_ACTIONS and pruning_action != "none":
        pruning_action = "none"
    can_support_factual_claim = surface_kind in SOURCE_EVIDENCE_KINDS and bool(source_refs)
    is_activation_surface = surface_kind in ACTIVATION_SURFACE_KINDS
    quoted_or_acted_as_fact = bool(
        row.get("quoted_as_factual_evidence") or row.get("acted_as_factual_evidence")
    )
    authority_leak = quoted_or_acted_as_fact and not can_support_factual_claim
    clean_source_mutation = bool(row.get("clean_source_mutation"))
    truth_status_changed = bool(row.get("truth_status_changed"))
    rank = _base_rank(surface_kind, authority_level)
    freshness = _text(row.get("freshness"), "unknown")
    if is_activation_surface:
        rank -= FRESHNESS_PENALTY.get(freshness, 0)
    return {
        "surface_id": _public_label(row.get("surface_id") or row.get("id"), surface_kind),
        "surface_kind": surface_kind,
        "authority_level": authority_level,
        "resolution_class": _resolution_class(surface_kind, authority_level),
        "conflict_key": _public_label(row.get("conflict_key") or row.get("topic"), "default"),
        "freshness": freshness,
        "pruning_action": pruning_action,
        "eligible_for_foreground": authority_level != "blocked",
        "requires_source_for_claim": not can_support_factual_claim,
        "can_support_factual_claim": can_support_factual_claim,
        "source_refs": source_refs,
        "source_ref_count": len(source_refs),
        "activation_surface": is_activation_surface,
        "quoted_or_acted_as_fact": quoted_or_acted_as_fact,
        "authority_leak": authority_leak,
        "clean_source_mutation": clean_source_mutation,
        "truth_status_changed": truth_status_changed,
        "would_emit_scent": bool(row.get("would_emit_scent")),
        "wrong_route_drag_count": _int(row.get("wrong_route_drag_count")),
        "estimated_verification_tool_calls": _int(row.get("estimated_verification_tool_calls")),
        "recent_helpful_count": _int(row.get("recent_helpful_count")),
        "recent_harmful_count": _int(row.get("recent_harmful_count")),
        "false_positive_count": _int(row.get("false_positive_count")),
        "no_source_reopen_count": _int(
            row.get("no_source_reopen_count")
            or row.get("cycles_without_source_reopen")
            or row.get("source_reopen_miss_count")
        ),
        "source_reopen_attempt_count": _int(row.get("source_reopen_attempt_count")),
        "source_reopen_success_count": _int(row.get("source_reopen_success_count")),
        "protected_reference_count": _protected_reference_count(row),
        "provenance_pointer_hash": _public_hash(
            row.get("provenance_pointer") or row.get("manifest_pointer") or "", "none"
        )
        if row.get("provenance_pointer") or row.get("manifest_pointer")
        else None,
        "rank": rank,
    }


def activation_dead_letter_candidate_report(
    surfaces: Iterable[Mapping[str, Any]],
    *,
    wrong_route_drag_threshold: int = DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD,
    no_source_reopen_threshold: int = DEFAULT_NO_SOURCE_REOPEN_THRESHOLD,
    false_positive_threshold: int = DEFAULT_FALSE_POSITIVE_THRESHOLD,
) -> dict[str, Any]:
    """Return a public-safe, no-write dead-letter candidate report."""

    rows = [normalize_activation_surface(row) for row in surfaces]
    return activation_dead_letter_candidate_report_from_rows(
        rows,
        schema_version=AUTHORITY_SCHEMA_VERSION,
        wrong_route_drag_threshold=wrong_route_drag_threshold,
        no_source_reopen_threshold=no_source_reopen_threshold,
        false_positive_threshold=false_positive_threshold,
    )


def apply_dead_letter_candidate_manifest(
    surfaces: Iterable[Mapping[str, Any]],
    *,
    applied_at: str | None = None,
    wrong_route_drag_threshold: int = DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD,
    no_source_reopen_threshold: int = DEFAULT_NO_SOURCE_REOPEN_THRESHOLD,
    false_positive_threshold: int = DEFAULT_FALSE_POSITIVE_THRESHOLD,
) -> dict[str, Any]:
    """Build an append-only manifest for dead-lettering safe candidates."""

    rows = [normalize_activation_surface(row) for row in surfaces]
    return apply_dead_letter_candidate_manifest_from_rows(
        rows,
        schema_version=AUTHORITY_SCHEMA_VERSION,
        applied_at=applied_at,
        wrong_route_drag_threshold=wrong_route_drag_threshold,
        no_source_reopen_threshold=no_source_reopen_threshold,
        false_positive_threshold=false_positive_threshold,
    )


def _conflict_reason(winner: Mapping[str, Any]) -> str:
    kind = str(winner.get("surface_kind") or "")
    level = str(winner.get("authority_level") or "")
    if kind == USER_CORRECTION_KIND:
        return "explicit_user_correction_suppresses_strategy_surfaces"
    if kind == "current_checkout_evidence":
        return "current_checkout_evidence_overrides_strategy_surfaces"
    if kind == "source_reopen_evidence":
        return "source_reopened_evidence_overrides_strategy_surfaces"
    if level == "blocked":
        return "blocked_or_retired_surface_is_not_foreground_eligible"
    if level == "guardrail":
        return "guardrail_requires_verification_before_action"
    if level == "source_required":
        return "source_reopen_required_before_claim_or_action"
    return "highest_ranked_activation_hint_is_advisory_only"


def _conflict_groups(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row["conflict_key"])].append(row)

    conflicts: list[dict[str, Any]] = []
    for key, items in sorted(groups.items()):
        if len(items) < 2:
            continue
        ordered = sorted(items, key=lambda item: (int(item["rank"]), str(item["surface_id"])), reverse=True)
        winner = ordered[0]
        conflicts.append(
            {
                "conflict_key": key,
                "winner_surface_id": winner["surface_id"],
                "winner_surface_kind": winner["surface_kind"],
                "winner_resolution_class": winner["resolution_class"],
                "resolution_reason": _conflict_reason(winner),
                "suppressed_surface_ids": [item["surface_id"] for item in ordered[1:]],
                "ordered_surface_ids": [item["surface_id"] for item in ordered],
            }
        )
    return conflicts


def _reduces_foreground_noise(row: Mapping[str, Any]) -> bool:
    return bool(row.get("activation_surface")) and row.get("pruning_action") in FOREGROUND_REDUCTION_ACTIONS


def _likely_false_scent(row: Mapping[str, Any]) -> bool:
    if not bool(row.get("would_emit_scent")):
        return False
    helpful = _int(row.get("recent_helpful_count"))
    harmful = _int(row.get("recent_harmful_count"))
    return (
        str(row.get("freshness") or "") in {"stale", "superseded"}
        or harmful > helpful
        or _int(row.get("false_positive_count")) > 0
    )


def _duplicate_route_collapse_count(rows: Sequence[dict[str, Any]]) -> int:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("activation_surface"):
            groups[str(row.get("conflict_key") or "default")].append(row)
    collapses = 0
    for items in groups.values():
        if len(items) < 2:
            continue
        if any(_reduces_foreground_noise(item) for item in items):
            collapses += 1
    return collapses


def _foreground_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    activation_rows = [row for row in rows if row["activation_surface"]]
    reduced_rows = [row for row in activation_rows if _reduces_foreground_noise(row)]
    return {
        "false_scent_reduction_count": sum(1 for row in reduced_rows if _likely_false_scent(row)),
        "wrong_route_drag_reduction_count": sum(
            1 for row in reduced_rows if _int(row.get("wrong_route_drag_count")) > 0
        ),
        "duplicate_route_collapse_count": _duplicate_route_collapse_count(rows),
        "foreground_budget_saved_tool_calls": sum(
            _int(row.get("estimated_verification_tool_calls")) for row in reduced_rows
        ),
        "recent_helpfulness_count": sum(_int(row.get("recent_helpful_count")) for row in activation_rows),
        "recent_harmfulness_count": sum(_int(row.get("recent_harmful_count")) for row in activation_rows),
        "active_surface_count_before_pruning": len(activation_rows),
        "active_surface_count_after_pruning": sum(
            1
            for row in activation_rows
            if row["pruning_action"] not in FOREGROUND_REDUCTION_ACTIONS
            and row["eligible_for_foreground"]
        ),
    }


def activation_surface_authority_audit(surfaces: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Audit strategy-surface authority without changing any source or state."""

    rows = [normalize_activation_surface(row) for row in surfaces]
    conflicts = _conflict_groups(rows)
    activation_rows = [row for row in rows if row["activation_surface"]]
    foreground_metrics = _foreground_metrics(rows)
    dead_letter_report = activation_dead_letter_candidate_report_from_rows(
        rows,
        schema_version=AUTHORITY_SCHEMA_VERSION,
    )
    return {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "kind": AUTHORITY_AUDIT_KIND,
        "authority_levels": dict(AUTHORITY_LEVELS),
        "precedence": [
            USER_CORRECTION_KIND,
            "current_checkout_evidence",
            "source_reopen_evidence",
            "blocked",
            "guardrail",
            "source_required",
            "advisory",
            "candidate",
        ],
        "surface_count": len(rows),
        "activation_surface_count": len(activation_rows),
        "surfaces": rows,
        "conflicts": conflicts,
        "dead_letter_report": dead_letter_report,
        "metrics": {
            "conflict_count": len(conflicts),
            "activation_surface_authority_leak_count": sum(1 for row in rows if row["authority_leak"]),
            "activation_truth_status_mutation_attempt_count": sum(
                1 for row in activation_rows if row["truth_status_changed"]
            ),
            "activation_clean_source_mutation_attempt_count": sum(
                1 for row in activation_rows if row["clean_source_mutation"]
            ),
            "pruning_demote_count": sum(1 for row in rows if row["pruning_action"] == "demote"),
            "pruning_park_count": sum(1 for row in rows if row["pruning_action"] == "park"),
            "pruning_retire_count": sum(1 for row in rows if row["pruning_action"] == "retire"),
            "source_or_current_evidence_override_count": sum(
                1
                for conflict in conflicts
                if conflict["winner_surface_kind"] in SOURCE_EVIDENCE_KINDS
            ),
            "explicit_user_correction_override_count": sum(
                1
                for conflict in conflicts
                if conflict["winner_surface_kind"] == USER_CORRECTION_KIND
            ),
            **dead_letter_report["metrics"],
            **foreground_metrics,
        },
        "contract": {
            "activation_rows_are_not_factual_memory_store": True,
            "pruning_changes_activation_eligibility_only": True,
            "pruning_optimizes_foreground_usefulness_not_source_retention": True,
            "aar_nudges_and_dream_hypotheses_cannot_upgrade_to_evidence": True,
            "source_or_current_checkout_wins_truth_conflicts": True,
            "explicit_user_correction_wins_strategy_conflicts": True,
            "clean_source_mutation": False,
            "foreground_hook_mutation": False,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "source_refs_are_id_only": True,
        },
    }


def apply_activation_lifecycle_manifest(surfaces: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build an append-only lifecycle update manifest for activation surfaces."""

    rows = [normalize_activation_surface(row) for row in surfaces]
    return apply_activation_lifecycle_manifest_from_rows(
        rows,
        schema_version=AUTHORITY_SCHEMA_VERSION,
    )


def fixture_authority_conflict_audit() -> dict[str, Any]:
    """Small public-safe fixture covering the #498 conflict contract."""

    return activation_surface_authority_audit(
        [
            {
                "surface_id": "aar_specific_claim_guard",
                "surface_kind": "aar_nudge",
                "authority_level": "guardrail",
                "conflict_key": "memory-claim",
                "freshness": "current",
            },
            {
                "surface_id": "dream_bridge_candidate",
                "surface_kind": "dream_hypothesis",
                "conflict_key": "memory-claim",
                "freshness": "current",
            },
            {
                "surface_id": "lock_route_handle",
                "surface_kind": "active_recall_lock",
                "conflict_key": "memory-claim",
                "freshness": "current",
            },
            {
                "surface_id": "semantic_trigger_route",
                "surface_kind": "semantic_trigger",
                "conflict_key": "memory-claim",
                "freshness": "current",
            },
            {
                "surface_id": "current_repo_evidence",
                "surface_kind": "current_checkout_evidence",
                "conflict_key": "memory-claim",
                "source_refs": [{"source_id": "clean:repo", "thread_key": "session:repo"}],
            },
            {
                "surface_id": "corrected_strategy",
                "surface_kind": "explicit_user_correction",
                "conflict_key": "user-corrected-path",
                "source_refs": [{"source_id": "clean:correction", "thread_key": "session:fix"}],
            },
            {
                "surface_id": "plausible_old_nudge",
                "surface_kind": "aar_nudge",
                "authority_level": "advisory",
                "conflict_key": "user-corrected-path",
                "freshness": "stale",
            },
        ]
    )


def load_surface_rows(path: Path) -> list[dict[str, Any]]:
    """Load sanitized surface rows from JSON or JSONL for no-write audit runs."""

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if isinstance(value, dict):
                rows.append(value)
        return rows
    value = json.loads(text or "[]")
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        surfaces = value.get("surfaces") or value.get("rows") or []
        return [row for row in surfaces if isinstance(row, dict)]
    return []


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        help="JSON or JSONL file with public-safe activation surface rows.",
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Emit the built-in public-safe #498 conflict fixture audit.",
    )
    parser.add_argument(
        "--apply-output",
        type=Path,
        help="Write an append-only activation lifecycle update manifest.",
    )
    parser.add_argument(
        "--dead-letter-apply-output",
        type=Path,
        help="Write an append-only dead-letter lifecycle update manifest for safe candidates.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.input is not None:
        rows = load_surface_rows(args.input)
    else:
        rows = [
            item
            for item in fixture_authority_conflict_audit().get("surfaces", [])
            if isinstance(item, dict)
        ]
    report = activation_surface_authority_audit(rows)
    if args.apply_output is not None:
        manifest = apply_activation_lifecycle_manifest(rows)
        args.apply_output.parent.mkdir(parents=True, exist_ok=True)
        args.apply_output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report["apply_manifest"] = {
            "written": True,
            "update_count": manifest["update_count"],
            "append_only_lifecycle_update": True,
            "path_serialized": False,
        }
    if args.dead_letter_apply_output is not None:
        manifest = apply_dead_letter_candidate_manifest(rows)
        args.dead_letter_apply_output.parent.mkdir(parents=True, exist_ok=True)
        args.dead_letter_apply_output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        report["dead_letter_apply_manifest"] = {
            "written": True,
            "update_count": manifest["update_count"],
            "skipped_count": manifest["skipped_count"],
            "append_only_lifecycle_update": True,
            "path_serialized": False,
        }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        metrics = report["metrics"]
        print(
            "activation authority audit: "
            f"surfaces={report['surface_count']} "
            f"conflicts={metrics['conflict_count']} "
            f"leaks={metrics['activation_surface_authority_leak_count']} "
            f"dead_letter_candidates={metrics['dead_letter_candidate_count']}"
        )
    return 0


__all__ = [
    "AUTHORITY_AUDIT_KIND",
    "AUTHORITY_LEVELS",
    "AUTHORITY_SCHEMA_VERSION",
    "DEAD_LETTER_REPORT_KIND",
    "activation_dead_letter_candidate_report",
    "activation_surface_authority_audit",
    "apply_activation_lifecycle_manifest",
    "apply_dead_letter_candidate_manifest",
    "fixture_authority_conflict_audit",
    "load_surface_rows",
    "normalize_activation_surface",
]


if __name__ == "__main__":
    raise SystemExit(main())
