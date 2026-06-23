#!/usr/bin/env python3
"""Build dynamic semantic recall triggers from source-backed candidates.

Hard-coded cue lists are only safety rails. This script turns reviewed
subconscious promotion candidates into a small data layer consumed by
`semantic_recall_gate.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.navigation.associations import (
    normalize_term,
    source_text_is_noise,
    term_is_noise,
)
from aippocampus_runtime.recall import feedback_events
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.recall.semantic_recall_gate import default_semantic_triggers_path
from aippocampus_runtime.registry.api import registry_paths, unique_preserve
from aippocampus_runtime.subconscious.candidate_router import (
    SOURCE_SEMANTIC_TYPES,
    activation_cue_terms_for,
    activation_cues_for,
    default_candidates_path,
    iter_jsonl,
    write_jsonl,
)
from aippocampus_runtime.subconscious.candidate_router_feedback import (
    apply_alias_merge_feedback,
    apply_context_suppression_feedback,
)

TRIGGER_SCHEMA_VERSION = 1
TRIGGER_TYPES = {"hook_trigger", "project_memory", "concept_edge", *SOURCE_SEMANTIC_TYPES}
MIN_CONFIDENCE = 0.62
TRIGGER_ID_DIGEST_LENGTH = 24
MAX_PROMOTED_ALIASES = 16
MAX_SEED_ALIASES = 24
DEFAULT_SEED_TRIGGERS_PATH = (
    Path(__file__).resolve().parents[3] / "references" / "reviewed-semantic-triggers.seed.jsonl"
)
GENERIC_ALIASES = {
    "agent",
    "but",
    "core",
    "full",
    "has",
    "local",
    "memory",
    "not",
    "recall",
    "project",
    "runtime",
    "system",
    "candidate",
    "trigger",
    "cue",
    "source",
    "backed",
    "decision",
    "context",
    "routing",
    "记忆",
    "项目",
    "候选",
    "触发",
    "来源",
    "决策",
}
SEMI_GENERIC_ALIAS_PHRASES = {
    "memory continuity",
    "memory context",
    "memory project",
    "project context",
    "project memory",
    "project recall",
    "recall context",
    "source backed memory",
    "source memory",
    "trigger context",
    "项目记忆",
    "项目上下文",
    "记忆项目",
}


def default_seed_triggers_path() -> Path:
    return DEFAULT_SEED_TRIGGERS_PATH


def _hash_id(parts: list[str]) -> str:
    raw = "\n".join(parts)
    return "st_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:TRIGGER_ID_DIGEST_LENGTH]


def trigger_key(candidate: dict[str, Any]) -> str:
    return _hash_id(
        [
            str(candidate.get("candidate_type") or ""),
            normalize_term(str(candidate.get("title") or "")).casefold(),
            "|".join(sorted(str(value) for value in candidate.get("source_finding_ids") or [])),
        ]
    )


def seed_trigger_key(trigger: dict[str, Any], aliases: list[str]) -> str:
    return _hash_id(
        [
            "reviewed_seed",
            normalize_term(str(trigger.get("title") or trigger.get("concept") or "")).casefold(),
            "|".join(_alias_key(alias) for alias in aliases),
        ]
    )


def source_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in candidate.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        line = (
            ref.get("source_line")
            or ref.get("assistant_line")
            or ref.get("user_line")
            or ref.get("line")
        )
        clean = {
            "thread_key": ref.get("thread_key"),
            "title": ref.get("title"),
            "project_label": ref.get("project_label"),
            "turn_index": ref.get("turn_index"),
            "line": line,
            "message_id": ref.get("message_id"),
        }
        key = (
            str(clean.get("thread_key") or ""),
            str(clean.get("line") or ""),
            str(clean.get("message_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in clean.items() if v not in {None, ""}})
    return refs[:8]


def _alias_key(alias: str) -> str:
    normalized = normalize_term(alias).casefold()
    normalized = normalized.replace("source-backed", "source backed")
    normalized = re.sub(r"[-_/]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _drop_alias(alias: str) -> bool:
    key = _alias_key(alias)
    if not key:
        return True
    if key in GENERIC_ALIASES or key in SEMI_GENERIC_ALIAS_PHRASES:
        return True
    if len(alias) > 72 or source_text_is_noise(alias) or term_is_noise(alias):
        return True
    return False


def clean_aliases(
    aliases: list[str], *, limit: int, diagnostics: dict[str, Any] | None = None
) -> list[str]:
    clean: list[str] = []
    seen: set[str] = set()
    dropped = 0
    for raw in aliases:
        alias = normalize_term(str(raw or ""))
        key = _alias_key(alias)
        if _drop_alias(alias) or key in seen:
            dropped += 1
            continue
        if len(clean) >= limit:
            dropped += 1
            continue
        seen.add(key)
        clean.append(alias)
    if diagnostics is not None:
        diagnostics["dropped_alias_count"] = int(diagnostics.get("dropped_alias_count") or 0) + dropped
    return clean


def alias_candidates(
    candidate: dict[str, Any], *, diagnostics: dict[str, Any] | None = None
) -> list[str]:
    activation_terms = activation_cue_terms_for(candidate, limit=24)
    if activation_terms:
        # Model/subconscious-authored activation cues are the semantic route
        # surface. Title/summary prose remains human-readable context, not a
        # prompt matcher, because fuzzy frustration/annoyance judgment belongs
        # in the sidecar that produced these cues.
        return clean_aliases(
            activation_terms,
            limit=MAX_SEED_ALIASES,
            diagnostics=diagnostics,
        )
    if str(candidate.get("candidate_type") or "") in SOURCE_SEMANTIC_TYPES:
        semantic_aliases = [
            str(candidate.get("canonical_label") or ""),
            *(str(value) for value in candidate.get("aliases") or []),
        ]
        return clean_aliases(
            semantic_aliases,
            limit=MAX_PROMOTED_ALIASES,
            diagnostics=diagnostics,
        )
    text = "\n".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("summary") or ""),
            str(candidate.get("recommendation") or ""),
        ]
    )
    aliases: list[str] = []
    aliases.append(str(candidate.get("title") or ""))
    aliases.extend(split_query_terms([text]))
    aliases.extend(str(value) for value in candidate.get("concepts") or [])
    return clean_aliases(
        aliases,
        limit=MAX_PROMOTED_ALIASES,
        diagnostics=diagnostics,
    )


def _seed_review_skip_reason(row: dict[str, Any]) -> str | None:
    if not row.get("reviewed_at"):
        return "missing_reviewed_at"
    if not (row.get("reviewer") or row.get("review_source")):
        return "missing_reviewer_or_review_source"
    if not row.get("review_note"):
        return "missing_review_note"
    seed_refs = [ref for ref in row.get("source_refs") or [] if isinstance(ref, dict)]
    if not seed_refs and not row.get("reviewed_seed_rationale"):
        return "missing_source_refs_or_seed_rationale"
    return None


def _record_skipped_seed(diagnostics: dict[str, Any] | None, reason: str) -> None:
    if diagnostics is None:
        return
    diagnostics["skipped_seed_count"] = int(diagnostics.get("skipped_seed_count") or 0) + 1
    if reason == "missing_source_refs_or_seed_rationale" or reason.startswith("missing_"):
        diagnostics["skipped_missing_review_or_source_count"] = int(
            diagnostics.get("skipped_missing_review_or_source_count") or 0
        ) + 1
    reasons = diagnostics.setdefault("skipped_seed_reasons", {})
    if isinstance(reasons, dict):
        reasons[reason] = int(reasons.get(reason) or 0) + 1


def _migrate_trigger_id(row: dict[str, Any], new_id: str) -> None:
    old_id = str(row.get("trigger_id") or "")
    legacy_ids = [str(value) for value in row.get("legacy_trigger_ids") or [] if value]
    if old_id and old_id != new_id:
        legacy_ids.insert(0, old_id)
    row["trigger_id"] = new_id
    if legacy_ids:
        row["legacy_trigger_ids"] = unique_preserve(legacy_ids, limit=8)


def iter_seed_triggers(
    path: Path | None, *, diagnostics: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for row in iter_jsonl(path):
        if row.get("kind") != "aippocampus_semantic_trigger":
            continue
        if row.get("status") != "active":
            continue
        skip_reason = _seed_review_skip_reason(row)
        if skip_reason:
            _record_skipped_seed(diagnostics, skip_reason)
            continue
        aliases = clean_aliases(
            [str(alias or "") for alias in row.get("aliases") or []],
            limit=MAX_SEED_ALIASES,
            diagnostics=diagnostics,
        )
        if not aliases:
            _record_skipped_seed(diagnostics, "no_aliases_after_hygiene")
            continue
        trigger = dict(row)
        trigger.setdefault("schema_version", TRIGGER_SCHEMA_VERSION)
        trigger.setdefault("source", "reviewed_seed")
        _migrate_trigger_id(trigger, seed_trigger_key(trigger, aliases))
        trigger["aliases"] = unique_preserve(aliases, limit=24)
        trigger["confidence"] = round(float(trigger.get("confidence") or 0.8), 4)
        rows.append(trigger)
    return rows


def route_candidate(
    candidate: dict[str, Any],
    *,
    diagnostics: dict[str, Any] | None = None,
    feedback_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if candidate.get("kind") != "aippocampus_promotion_candidate":
        return None
    if candidate.get("status") not in {None, "staging", "active"}:
        return None
    candidate_type = str(candidate.get("candidate_type") or "")
    confidence = float(candidate.get("confidence") or 0.0)
    if candidate_type not in TRIGGER_TYPES or confidence < MIN_CONFIDENCE:
        return None
    refs = source_refs(candidate)
    if not refs:
        return None
    aliases = alias_candidates(candidate, diagnostics=diagnostics)
    if not aliases:
        return None
    negative_cues = clean_aliases(
        [str(value or "") for value in candidate.get("negative_cues") or []],
        limit=10,
        diagnostics=diagnostics,
    )
    when_not_to_use = compact_text(str(candidate.get("when_not_to_use") or ""), 220)
    if not when_not_to_use:
        if negative_cues:
            when_not_to_use = (
                "Do not activate for: " + "; ".join(negative_cues[:4])
                + ". Reopen source before presenting exact claims as facts."
            )
        else:
            when_not_to_use = (
                "Use as a semantic recall hint only; search clean source before "
                "presenting exact claims as facts."
            )
    if diagnostics is not None:
        diagnostics["promoted_candidate_count"] = (
            int(diagnostics.get("promoted_candidate_count") or 0) + 1
        )
    trigger = {
        "schema_version": TRIGGER_SCHEMA_VERSION,
        "kind": "aippocampus_semantic_trigger",
        "trigger_id": trigger_key(candidate),
        "created_at": now_utc(),
        "status": "active",
        "source": "semantic_trigger_router",
        "source_candidate_type": candidate_type,
        "title": compact_text(str(candidate.get("title") or ""), 100),
        "concept": compact_text(
            str(candidate.get("canonical_label") or candidate.get("title") or ""), 100
        ),
        "aliases": aliases,
        "when_to_use": compact_text(str(candidate.get("summary") or ""), 320),
        "when_not_to_use": when_not_to_use,
        "confidence": round(confidence, 4),
        "activation_cues": activation_cues_for(candidate),
        "negative_cues": negative_cues,
        "claim_authority": str(candidate.get("claim_authority") or "navigation_only"),
        "foreground_policy": str(candidate.get("foreground_policy") or "reopenable_route"),
        "semantic_candidate": bool(candidate.get("semantic_candidate"))
        or candidate_type in SOURCE_SEMANTIC_TYPES,
        "term_type": candidate.get("term_type"),
        "surface_status": candidate.get("surface_status"),
        "source_refs": refs,
    }
    apply_feedback_adjustment(trigger, candidate, feedback_rows or [])
    return trigger


def _feedback_ids_for_trigger(trigger: dict[str, Any], candidate: dict[str, Any]) -> set[str]:
    ids = {
        str(trigger.get("trigger_id") or ""),
        str(candidate.get("candidate_id") or ""),
        str(candidate.get("route_id") or ""),
    }
    ids.update(str(value) for value in candidate.get("source_finding_ids") or [])
    return {value for value in ids if value}


def apply_feedback_adjustment(
    trigger: dict[str, Any], candidate: dict[str, Any], rows: list[dict[str, Any]]
) -> None:
    ids = _feedback_ids_for_trigger(trigger, candidate)
    relevant = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("route_id") or row.get("candidate_id") or "") in ids
    ]
    apply_alias_merge_feedback(trigger, candidate, relevant)
    apply_context_suppression_feedback(trigger, candidate, relevant)
    if trigger.get("routing_diagnostics", {}).get("feedback_alias_merged"):
        trigger["aliases"] = unique_preserve(
            clean_aliases(
                [str(alias or "") for alias in trigger.get("aliases") or []],
                limit=MAX_PROMOTED_ALIASES,
            ),
            limit=MAX_PROMOTED_ALIASES,
        )
    if trigger.get("routing_diagnostics", {}).get("feedback_context_suppressed"):
        trigger["negative_cues"] = unique_preserve(
            clean_aliases(
                [str(cue or "") for cue in trigger.get("negative_cues") or []],
                limit=10,
            ),
            limit=10,
        )
        if trigger["negative_cues"]:
            trigger["when_not_to_use"] = compact_text(
                "Do not activate for: "
                + "; ".join(trigger["negative_cues"][:4])
                + ". "
                + str(trigger.get("when_not_to_use") or ""),
                220,
            )
    prior_adjustment = dict(trigger.get("feedback_adjustment") or {})
    if not relevant:
        return
    report = feedback_events.active_flow_activation_report(relevant)
    routes = report.get("routes") or []
    if not routes:
        return
    route = routes[0]
    score = float(route.get("activation_score") or 0.0)
    trigger["feedback_adjustment"] = {
        **prior_adjustment,
        "activation_score": route.get("activation_score"),
        "event_count": route.get("event_count"),
        "signal_counts": route.get("signal_counts") or {},
        "foreground_eligible": bool(route.get("foreground_eligible")),
        "reason_codes": route.get("reason_codes") or [],
        "source_refs_preserved": True,
        "source_truth_changed": False,
    }
    if not route.get("foreground_eligible") and score <= 0:
        trigger["status"] = "parked"
        trigger["feedback_suppressed"] = True
        trigger["when_not_to_use"] = compact_text(
            "Suppressed by same-route feedback; source refs remain auditable. "
            + str(trigger.get("when_not_to_use") or ""),
            220,
        )
    elif score > 0:
        trigger["feedback_promoted"] = True
        trigger["confidence"] = round(min(1.0, float(trigger.get("confidence") or 0.0) + 0.05), 4)


def build_semantic_triggers(
    *,
    candidates_path: Path,
    output_path: Path,
    seed_triggers_path: Path | None = None,
    feedback_path: Path | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    diagnostics: dict[str, Any] = {
        "promoted_candidate_count": 0,
        "dropped_alias_count": 0,
        "skipped_seed_count": 0,
        "skipped_missing_review_or_source_count": 0,
        "skipped_seed_reasons": {},
    }
    seed_triggers = iter_seed_triggers(seed_triggers_path, diagnostics=diagnostics)
    feedback_rows = iter_jsonl(feedback_path) if feedback_path else []
    for trigger in seed_triggers:
        by_key[str(trigger.get("trigger_id"))] = trigger
    for candidate in iter_jsonl(candidates_path):
        routed = route_candidate(
            candidate,
            diagnostics=diagnostics,
            feedback_rows=feedback_rows,
        )
        if not routed:
            continue
        key = str(routed.get("trigger_id"))
        existing = by_key.get(key)
        if existing and float(existing.get("confidence") or 0.0) >= float(
            routed.get("confidence") or 0.0
        ):
            continue
        by_key[key] = routed
    rows = sorted(
        by_key.values(),
        key=lambda row: (float(row.get("confidence") or 0.0), str(row.get("title") or "")),
        reverse=True,
    )
    write_jsonl(output_path, rows)
    summary = {
        "schema_version": TRIGGER_SCHEMA_VERSION,
        "kind": "aippocampus_semantic_trigger_routing",
        "created_at": now_utc(),
        "source_candidates": str(candidates_path),
        "seed_triggers": str(seed_triggers_path) if seed_triggers_path else None,
        "source_feedback": str(feedback_path) if feedback_path else "",
        "seed_trigger_count": len(seed_triggers),
        "promoted_candidate_count": diagnostics["promoted_candidate_count"],
        "dropped_alias_count": diagnostics["dropped_alias_count"],
        "skipped_seed_count": diagnostics["skipped_seed_count"],
        "skipped_missing_review_or_source_count": diagnostics[
            "skipped_missing_review_or_source_count"
        ],
        "skipped_seed_reasons": diagnostics["skipped_seed_reasons"],
        "trigger_count": len(rows),
        "feedback_changed_count": sum(
            1 for row in rows if isinstance(row.get("feedback_adjustment"), dict)
        ),
        "feedback_alias_merge_count": sum(
            int((row.get("feedback_adjustment") or {}).get("alias_merge_count") or 0)
            for row in rows
            if isinstance(row.get("feedback_adjustment"), dict)
        ),
        "feedback_context_suppression_count": sum(
            int((row.get("feedback_adjustment") or {}).get("context_suppression_count") or 0)
            for row in rows
            if isinstance(row.get("feedback_adjustment"), dict)
        ),
        "output": str(output_path),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--candidates")
    parser.add_argument("--output")
    parser.add_argument("--seed-triggers")
    parser.add_argument("--no-seed-triggers", action="store_true")
    parser.add_argument("--feedback-jsonl")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    candidates = (
        Path(args.candidates).resolve()
        if args.candidates
        else default_candidates_path(registry_path=registry_path)
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else default_semantic_triggers_path(registry_path=registry_path)
    )
    seed_triggers_path = (
        None
        if args.no_seed_triggers
        else Path(args.seed_triggers).resolve()
        if args.seed_triggers
        else default_seed_triggers_path()
    )
    result = build_semantic_triggers(
        candidates_path=candidates,
        output_path=output,
        seed_triggers_path=seed_triggers_path,
        feedback_path=Path(args.feedback_jsonl).resolve() if args.feedback_jsonl else None,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"semantic triggers: {result['trigger_count']}")
        print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
