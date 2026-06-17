"""Trace/replay feedback adapters for Skill-to-AIppo observed use."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text

TRACE_BACKED_ORIGINS = {"trace_backed", "replay_backed"}
TRACE_POSITIVE_SIGNALS = {
    "source_reopen_success",
    "reopened_deepened",
    "user_confirmed",
    "prevented_failure",
}
TRACE_NO_HELP_SIGNALS = {
    "ignored",
    "wrong_route_drag",
    "blocked",
    "superseded",
    "expired",
    "corrected",
    "unsupported_or_too_specific",
}


def _text(value: Any, limit: int = 240) -> str:
    return compact_text(str(value or "").strip(), limit)


def _mapping_field(row: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = row.get(key)
    return value if isinstance(value, Mapping) else {}


def _first_text_field(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        text = _text(row.get(key), 240)
        if text:
            return text
    return ""


def _nested_text_field(
    row: Mapping[str, Any],
    keys: Sequence[str],
    nested_keys: Sequence[str],
) -> str:
    direct = _first_text_field(row, keys)
    if direct:
        return direct
    for nested_key in nested_keys:
        nested_text = _first_text_field(_mapping_field(row, nested_key), keys)
        if nested_text:
            return nested_text
    return ""


def _clause_id_from_feedback_row(row: Mapping[str, Any]) -> str:
    clause_id = _nested_text_field(
        row,
        ("clause_id", "target_clause_id", "skill_clause_id"),
        ("observed_use", "target", "skill_observed_use"),
    )
    if clause_id:
        return clause_id
    for key in ("route_id", "candidate_id", "activation_id"):
        value = _text(row.get(key), 240)
        if value.startswith("skill_clause:"):
            return value.split("skill_clause:", 1)[1].strip()
    return ""


def _feedback_signal(row: Mapping[str, Any]) -> str:
    return _nested_text_field(
        row,
        ("signal", "outcome", "outcome_signal", "feedback_outcome"),
        ("observed_use", "target", "skill_observed_use"),
    )


def _feedback_origin(row: Mapping[str, Any], default_origin: str) -> str:
    origin = _nested_text_field(
        row,
        ("evidence_origin", "origin"),
        ("observed_use", "target", "skill_observed_use"),
    )
    if origin in TRACE_BACKED_ORIGINS:
        return origin
    return default_origin if default_origin in TRACE_BACKED_ORIGINS else ""


def _feedback_source_ref(row: Mapping[str, Any]) -> str:
    return _nested_text_field(
        row,
        ("source_ref", "source_id", "event_id", "created_at"),
        ("observed_use", "target", "skill_observed_use"),
    )


def load_jsonl_rows(path: str | Path | None) -> tuple[list[dict[str, Any]], int]:
    if not path:
        return [], 0
    source = Path(path).expanduser().resolve()
    if not source.exists():
        return [], 0
    rows: list[dict[str, Any]] = []
    invalid = 0
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if isinstance(value, Mapping):
                rows.append(dict(value))
            else:
                invalid += 1
    return rows, invalid


def observed_use_rows_from_foreground_feedback(
    seed: Mapping[str, Any],
    feedback_rows: Sequence[Mapping[str, Any]],
    *,
    evidence_origin: str = "",
) -> list[dict[str, Any]]:
    """Project explicit trace/replay feedback events into observed-use rows.

    Ordinary low-authority `agent feedback` rows are routing calibration only.
    This adapter accepts rows only when they explicitly claim a trace/replay
    origin and carry a source/replay reference, so feedback cannot silently
    become source truth or ripen unrelated skill clauses.
    """

    seed_id = _text(seed.get("seed_id"), 180)
    skill_id = _text(seed.get("skill_id"), 180)
    clauses = {
        str(clause.get("clause_id") or ""): clause
        for clause in seed.get("clauses", [])
        if isinstance(clause, Mapping)
    }
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, feedback in enumerate(feedback_rows, start=1):
        if not isinstance(feedback, Mapping):
            continue
        row_skill_id = _nested_text_field(
            feedback,
            ("skill_id", "target_skill_id"),
            ("observed_use", "target", "skill_observed_use"),
        )
        if row_skill_id and skill_id and row_skill_id != skill_id:
            continue
        clause_id = _clause_id_from_feedback_row(feedback)
        if clause_id not in clauses:
            continue
        signal = _feedback_signal(feedback)
        origin = _feedback_origin(feedback, evidence_origin)
        support_payload = _mapping_field(feedback, "source_support")
        source_ref = _feedback_source_ref(feedback)
        if (
            origin not in TRACE_BACKED_ORIGINS
            or not source_ref
            or bool(support_payload.get("self_report_only"))
            or support_payload.get("feedback_is_source_backed") is False
        ):
            continue
        if signal in TRACE_POSITIVE_SIGNALS:
            agent_action = "used"
            outcome_signal = "helped"
            usefulness_row = {
                "next_action_was_clear": True,
                "manual_search_avoided": True,
                "unnecessary_deepen_avoided": True,
            }
        elif signal in TRACE_NO_HELP_SIGNALS:
            agent_action = (
                "corrected" if signal in {"wrong_route_drag", "blocked", "corrected"} else "ignored"
            )
            outcome_signal = "unsupported_or_too_specific"
            usefulness_row = {
                "next_action_was_clear": False,
                "manual_search_avoided": False,
                "unnecessary_deepen_avoided": False,
            }
        else:
            continue
        dedupe_key = (clause_id, signal, source_ref)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        clause = clauses[clause_id]
        rows.append(
            {
                "kind": "aippo_skill_observed_use",
                "activation_id": f"act_skill_trace_observed_{index:03d}",
                "seed_id": seed_id,
                "skill_id": skill_id,
                "clause_id": clause_id,
                "clause_kind": clause.get("clause_kind"),
                "packet_mode": "working_contract_seed",
                "evidence_origin": origin,
                "foreground_feedback_kind": feedback.get("kind") or "replay_event",
                "foreground_feedback_signal": signal,
                "agent_action": agent_action,
                "outcome_signal": outcome_signal,
                "source_support": {
                    "feedback_is_source_backed": True,
                    "self_report_only": False,
                    "source_ref_count": 1,
                    "source_ref": source_ref,
                },
                "usefulness": usefulness_row,
            }
        )
    return rows


__all__ = [
    "TRACE_BACKED_ORIGINS",
    "load_jsonl_rows",
    "observed_use_rows_from_foreground_feedback",
]
