#!/usr/bin/env python3
"""Deterministic AAR v2 action-time nudge prototype.

This first slice is intentionally narrow: it turns source-backed corrections or
postmortems into advisory records for one high-risk action class, then matches
those records when a foreground action is about to make a specific memory/source
claim from weak context. It does not install live hooks, mutate source, or let a
counterfactual hypothesis become causal truth on its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, sanitize_external_model_text
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 1
AAR_V2_REPORT_KIND = "aippocampus_aar_v2_report"
AAR_V2_RECORD_KIND = "aippocampus_aar_v2_candidate_record"
AAR_V2_NUDGE_KIND = "aippocampus_aar_v2_action_time_nudge"
SOURCE_CLAIM_ACTION_CLASS = "specific_memory_source_claim"
WEAK_SUPPORT_LEVELS = ("scent", "candidate", "dream")
SOURCE_BACKED_INPUT_KINDS = {
    "explicit_correction",
    "source_backed_correction",
    "source_backed_postmortem",
    "postmortem",
}
SUPPORTED_COUNTERFACTUAL_EVIDENCE_KINDS = {
    "replay",
    "sandbox_ablation",
    "source_reopen",
    "explicit_user_correction",
    "retrospective_outcome",
}
FEEDBACK_VALUES = {"useful", "ignored", "false_positive", "prevented_failure", "stale"}
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


def _stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def _safe_text(value: Any, *, max_chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, max_chars)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _source_refs(value: Any, *, limit: int = 12) -> list[dict[str, Any]]:
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
            raw = item.get(key)
            if raw in {None, ""}:
                continue
            out_key = "line" if key == "source_line" else key
            if out_key == "stable_source_id":
                out_key = "source_id"
            ref[out_key] = _safe_text(raw, max_chars=180)
        if not ref:
            continue
        marker = tuple(sorted((str(key), str(val)) for key, val in ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def _supported_counterfactual_evidence(row: Mapping[str, Any]) -> list[str]:
    kinds: list[str] = []
    for item in row.get("counterfactual_support") or row.get("supporting_evidence") or []:
        if not isinstance(item, Mapping):
            continue
        kind = _safe_text(item.get("kind"), max_chars=64)
        if kind not in SUPPORTED_COUNTERFACTUAL_EVIDENCE_KINDS:
            continue
        refs = _source_refs(item.get("source_refs") or item.get("evidence_refs") or [], limit=4)
        if refs:
            kinds.append(kind)
    return unique_preserve(kinds, limit=len(SUPPORTED_COUNTERFACTUAL_EVIDENCE_KINDS))


def _counterfactual_hypothesis(row: Mapping[str, Any]) -> dict[str, Any]:
    supporting_kinds = _supported_counterfactual_evidence(row)
    status = "supported" if supporting_kinds else "provisional"
    return {
        "status": status,
        "summary": _safe_text(row.get("counterfactual") or row.get("hypothesis"), max_chars=260),
        "supporting_evidence_kinds": supporting_kinds,
        "requires_replay_or_source_outcome_before_claim": status == "provisional",
        "still_not_causal_truth": True,
    }


def _candidate_from_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    source_refs = _source_refs(row.get("source_refs") or row.get("evidence_refs") or [])
    action_class = _safe_text(row.get("action_class") or row.get("target_action_class"), max_chars=80)
    if action_class != SOURCE_CLAIM_ACTION_CLASS:
        return None
    if not source_refs:
        return None
    input_kind = _safe_text(row.get("kind") or row.get("source_kind"), max_chars=80)
    if input_kind not in SOURCE_BACKED_INPUT_KINDS:
        return None
    pattern_id = _safe_text(row.get("pattern_id") or row.get("id"), max_chars=100)
    summary = _safe_text(row.get("summary") or row.get("correction_surface"), max_chars=360)
    record_id = _stable_id("aar_v2", input_kind, pattern_id, action_class, source_refs, summary)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": AAR_V2_RECORD_KIND,
        "record_id": record_id,
        "created_at": _safe_text(row.get("created_at") or now_utc(), max_chars=40),
        "source_kind": input_kind,
        "pattern_id": pattern_id or record_id,
        "action_class": SOURCE_CLAIM_ACTION_CLASS,
        "failure_pattern": summary or "Specific memory/source claim risk from weak context.",
        "trigger": {
            "action_class": SOURCE_CLAIM_ACTION_CLASS,
            "claim_support_levels": list(WEAK_SUPPORT_LEVELS),
            "requires_specific_memory_claim": True,
            "suppress_when_visible_source_present": True,
        },
        "nudge": {
            "delivery": "action_time_advisory",
            "recommended_action": "reopen_source_before_specific_claim",
            "default_estimated_tool_calls": _int(row.get("estimated_reopen_tool_calls") or 1),
        },
        "counterfactual_hypothesis": _counterfactual_hypothesis(row),
        "feedback_contract": {
            "allowed_feedback": sorted(FEEDBACK_VALUES),
            "feeds_pruning_later": True,
            "feedback_is_strategy_signal_not_truth": True,
        },
        "source_refs": source_refs,
        "advisory_only": True,
        "can_support_factual_claim": False,
        "clean_source_mutation": False,
        "truth_status_changed": False,
    }


def build_aar_v2_report(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Inspect public-safe correction/postmortem rows and propose AAR v2 records."""

    candidates: list[dict[str, Any]] = []
    ignored = 0
    for row in rows:
        candidate = _candidate_from_row(row)
        if candidate is None:
            ignored += 1
            continue
        candidates.append(candidate)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": AAR_V2_REPORT_KIND,
        "no_write": True,
        "input_count": len(candidates) + ignored,
        "candidate_count": len(candidates),
        "ignored_count": ignored,
        "candidate_records": candidates,
        "metrics": {
            "source_claim_record_count": sum(
                1 for item in candidates if item["action_class"] == SOURCE_CLAIM_ACTION_CLASS
            ),
            "provisional_counterfactual_count": sum(
                1
                for item in candidates
                if item["counterfactual_hypothesis"]["status"] == "provisional"
            ),
            "supported_counterfactual_count": sum(
                1 for item in candidates if item["counterfactual_hypothesis"]["status"] == "supported"
            ),
        },
        "contract": {
            "nudges_are_advisory": True,
            "counterfactuals_are_not_causal_truth": True,
            "source_truth_unchanged": True,
            "clean_source_mutation": False,
            "truth_status_changed": False,
        },
        "privacy_boundary": {
            "raw_prompts_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "source_refs_are_id_only": True,
        },
    }


def _action_matches_record(record: Mapping[str, Any], action: Mapping[str, Any]) -> bool:
    if str(record.get("action_class") or "") != SOURCE_CLAIM_ACTION_CLASS:
        return False
    if str(action.get("action_class") or "") != SOURCE_CLAIM_ACTION_CLASS:
        return False
    if not bool(action.get("specific_memory_claim")):
        return False
    if bool(action.get("visible_context_has_source")):
        return False
    support_level = str(action.get("support_level") or "")
    trigger = _mapping(record.get("trigger"))
    return support_level in set(trigger.get("claim_support_levels") or WEAK_SUPPORT_LEVELS)


def _nudge_cost(action: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, int]:
    default_calls = _mapping(record.get("nudge")).get("default_estimated_tool_calls")
    return {
        "estimated_tool_calls": _int(action.get("estimated_reopen_tool_calls") or default_calls or 1),
        "estimated_tokens": _int(action.get("estimated_nudge_tokens") or 0),
    }


def match_action_time_nudges(
    candidate_records: Sequence[Mapping[str, Any]],
    action: Mapping[str, Any],
) -> dict[str, Any]:
    """Match AAR v2 records to one foreground action without changing state."""

    nudges: list[dict[str, Any]] = []
    for record in candidate_records:
        if not _action_matches_record(record, action):
            continue
        cost = _nudge_cost(action, record)
        nudges.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": AAR_V2_NUDGE_KIND,
                "record_id": record.get("record_id"),
                "action_class": SOURCE_CLAIM_ACTION_CLASS,
                "recommended_action": "reopen_source_before_specific_claim",
                "message": "Reopen clean source before making this specific memory/source claim.",
                "evidence_boundary": "nudge_routes_attention_not_truth",
                "counterfactual_hypothesis": record.get("counterfactual_hypothesis") or {},
                "source_refs": record.get("source_refs") or [],
                "nudge_cost": cost,
                "prevented_failure_signal": True,
                "advisory_only": True,
                "can_support_factual_claim": False,
                "clean_source_mutation": False,
                "truth_status_changed": False,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_aar_v2_action_match",
        "action_class": _safe_text(action.get("action_class"), max_chars=80),
        "nudge_count": len(nudges),
        "nudges": nudges,
        "metrics": {
            "prevented_failure_signal_count": sum(
                1 for item in nudges if item["prevented_failure_signal"]
            ),
            "estimated_nudge_tool_calls": sum(
                _int(item.get("nudge_cost", {}).get("estimated_tool_calls")) for item in nudges
            ),
        },
        "contract": {
            "advisory_only": True,
            "source_reopen_required_before_specific_claim": bool(nudges),
            "source_truth_unchanged": True,
        },
    }


def summarize_feedback_metrics(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize AAR v2 outcome feedback for later pruning/demotion decisions."""

    feedback_rows = [row for row in rows if str(row.get("feedback") or "") in FEEDBACK_VALUES]
    useful = sum(1 for row in feedback_rows if row.get("feedback") in {"useful", "prevented_failure"})
    ignored = sum(1 for row in feedback_rows if row.get("feedback") == "ignored")
    false_positive = sum(1 for row in feedback_rows if row.get("feedback") == "false_positive")
    stale = sum(1 for row in feedback_rows if row.get("feedback") == "stale")
    prevented = sum(1 for row in feedback_rows if bool(row.get("prevented_failure_signal")))
    tool_calls = sum(_int(_mapping(row.get("nudge_cost")).get("tool_calls")) for row in feedback_rows)
    tokens = sum(_int(_mapping(row.get("nudge_cost")).get("tokens")) for row in feedback_rows)
    total = len(feedback_rows)
    return {
        "feedback_count": total,
        "useful_nudge_count": useful,
        "ignored_nudge_count": ignored,
        "false_positive_nudge_count": false_positive,
        "stale_nudge_count": stale,
        "prevented_failure_signal_count": prevented,
        "false_positive_nudge_rate": false_positive / total if total else 0.0,
        "nudge_cost": {
            "tool_calls": tool_calls,
            "tokens": tokens,
        },
        "feeds_pruning_later": True,
        "clean_source_mutation": False,
        "truth_status_changed": False,
    }


def load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        out: list[dict[str, Any]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            value = json.loads(stripped)
            if isinstance(value, dict):
                out.append(value)
        return out
    value = json.loads(text or "[]")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows = value.get("rows") or value.get("postmortems") or value.get("corrections") or []
        return [item for item in rows if isinstance(item, dict)]
    return []


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSON/JSONL public-safe correction rows.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = build_aar_v2_report(load_rows(args.input))
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "AAR v2 no-write report: "
            f"inputs={report['input_count']} candidates={report['candidate_count']}"
        )
    return 0


__all__ = [
    "AAR_V2_REPORT_KIND",
    "build_aar_v2_report",
    "match_action_time_nudges",
    "summarize_feedback_metrics",
]


if __name__ == "__main__":
    raise SystemExit(main())
