#!/usr/bin/env python3
"""Deterministic authority audit for strategy-like activation surfaces.

Activation rows can route attention, slow risky actions, or retire noisy cues.
They are not source. This helper keeps that boundary visible before AAR nudges,
dream hypotheses, semantic triggers, locks, or pruning states become foreground
inputs.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

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
LIFECYCLE_STATE_BY_ACTION = {
    "demote": "demoted",
    "park": "parked",
    "supersede": "superseded",
    "retire": "retired",
}
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
        "rank": rank,
    }


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
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "source_refs_are_id_only": True,
        },
    }


def apply_activation_lifecycle_manifest(surfaces: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build an append-only lifecycle update manifest for activation surfaces.

    The manifest is intentionally a patch surface, not an in-place file mutator.
    It lets the owner of each activation row apply demote/park/supersede/retire
    updates under its normal serial writer while preserving source refs and
    provenance. Source rows, explicit corrections, and clean-source evidence are
    not lifecycle-pruned here.
    """

    rows = [normalize_activation_surface(row) for row in surfaces]
    updates: list[dict[str, Any]] = []
    for row in rows:
        action = str(row.get("pruning_action") or "none")
        if not row["activation_surface"] or action not in LIFECYCLE_STATE_BY_ACTION:
            continue
        updates.append(
            {
                "surface_id": row["surface_id"],
                "surface_kind": row["surface_kind"],
                "conflict_key": row["conflict_key"],
                "action": action,
                "lifecycle_state_after": LIFECYCLE_STATE_BY_ACTION[action],
                "activation_eligible_after": action == "demote",
                "foreground_eligible_after": False,
                "source_refs": row["source_refs"],
                "source_refs_preserved": True,
                "append_only": True,
                "clean_source_mutation": False,
                "truth_status_changed": False,
            }
        )

    return {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "kind": "aippocampus_activation_lifecycle_apply_manifest",
        "ok": True,
        "update_count": len(updates),
        "updates": updates,
        "contract": {
            "append_only_lifecycle_update": True,
            "clean_source_mutation": False,
            "truth_status_changed": False,
            "source_refs_preserved": True,
            "source_rows_are_not_pruned": True,
            "raw_prompts_or_snippets_serialized": False,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "source_refs_are_id_only": True,
        },
    }


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
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        metrics = report["metrics"]
        print(
            "activation authority audit: "
            f"surfaces={report['surface_count']} "
            f"conflicts={metrics['conflict_count']} "
            f"leaks={metrics['activation_surface_authority_leak_count']}"
        )
    return 0


__all__ = [
    "AUTHORITY_AUDIT_KIND",
    "AUTHORITY_LEVELS",
    "AUTHORITY_SCHEMA_VERSION",
    "activation_surface_authority_audit",
    "apply_activation_lifecycle_manifest",
    "fixture_authority_conflict_audit",
    "load_surface_rows",
    "normalize_activation_surface",
]


if __name__ == "__main__":
    raise SystemExit(main())
