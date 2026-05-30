#!/usr/bin/env python3
"""Conservative agency affordance map and ticket selector.

AIppocampus can propose small source-backed affordances, but the host remains
the executive controller. This module builds a sidecar map and selects bounded
initiative tickets; it never grants permission, sequences work, or executes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampuslib import cli_error_payload, cli_exit_code_for_error_code, compact_text, now_utc
from question_source_refs import source_ref_key
from registry import unique_preserve

SCHEMA_VERSION = 1
PROMPT_VERSION = "aippocampus-agency-affordance-v1"

MAP_KIND = "aippocampus_agency_affordance_map"
AFFORDANCE_KIND = "aippocampus_agency_affordance"
TICKET_KIND = "aippocampus_agency_ticket"
FEEDBACK_KIND = "aippocampus_agency_ticket_feedback"

TRIGGERS = (
    "user_correction",
    "compaction_loss",
    "unfinished_task_reentry",
    "scheduled_revisit",
)
INTERVENTION_LEVELS = (
    "silent",
    "backstage_only",
    "state_check",
    "light_nudge",
    "offer_next_step",
    "warning",
)
FOREGROUND_LEVELS = {"state_check", "light_nudge", "offer_next_step", "warning"}
BACKSTAGE_LEVELS = {"silent", "backstage_only"}
OUTCOME_FEEDBACK = (
    "accepted",
    "ignored",
    "dismissed",
    "corrected",
    "tool_success",
    "tool_failure",
)
SOURCE_THICKNESS_RANK = {"thin": 0, "usable": 1, "strong": 2}
LEVEL_RANK = {
    "warning": 5,
    "offer_next_step": 4,
    "state_check": 3,
    "light_nudge": 2,
    "backstage_only": 1,
    "silent": 0,
}


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return f"{prefix}_{sha1_text(raw)[:length]}"


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def clean_source_ref(ref: Any) -> dict[str, Any] | None:
    if not isinstance(ref, Mapping):
        return None
    thread_key, message_id, turn_id, line = source_ref_key(ref)
    if not thread_key or not (message_id or turn_id or line):
        return None
    clean = {
        "thread_key": thread_key,
        "message_id": ref.get("message_id"),
        "turn_id": ref.get("turn_id"),
        "source_id": ref.get("source_id"),
        "clean_ordinal": ref.get("clean_ordinal"),
        "source_line": ref.get("source_line") or ref.get("line"),
        "role": ref.get("role"),
        "phase": ref.get("phase") or "",
        "timestamp": ref.get("timestamp"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def merge_source_refs(*groups: Sequence[Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for group in groups:
        for item in group or []:
            clean = clean_source_ref(item)
            if not clean:
                continue
            key = source_ref_key(clean)
            if key in seen:
                continue
            seen.add(key)
            refs.append(clean)
    return refs[:12]


def source_ref_fingerprint(refs: Sequence[Mapping[str, Any]]) -> str:
    if not refs:
        return ""
    keys = [source_ref_key(ref) for ref in refs]
    return stable_id("src_refs", keys, length=16)


def source_thickness(refs: Sequence[Mapping[str, Any]], explicit: str | None = None) -> str:
    if explicit in SOURCE_THICKNESS_RANK:
        return str(explicit)
    if len(refs) >= 3:
        return "strong"
    if refs:
        return "usable"
    return "thin"


def visible_ref_keys(refs: Sequence[Mapping[str, Any]]) -> set[tuple[str, str, str, str]]:
    return {source_ref_key(ref) for ref in refs if source_ref_key(ref)[0]}


def is_visible(
    refs: Sequence[Mapping[str, Any]],
    *,
    visible_context_ref_keys: set[tuple[str, str, str, str]],
) -> bool:
    if not visible_context_ref_keys:
        return False
    return any(source_ref_key(ref) in visible_context_ref_keys for ref in refs)


def normalize_trigger(value: Any, fallback: str) -> str:
    text = str(value or fallback)
    aliases = {
        "rejected_route": "compaction_loss",
        "pre_patch": "compaction_loss",
        "session_start": "unfinished_task_reentry",
        "user_correction": "user_correction",
        "compaction_loss": "compaction_loss",
        "unfinished_task": "unfinished_task_reentry",
        "unfinished_task_reentry": "unfinished_task_reentry",
        "scheduled_revisit": "scheduled_revisit",
    }
    return aliases.get(text, fallback if fallback in TRIGGERS else "compaction_loss")


def normalize_level(value: Any, fallback: str) -> str:
    text = str(value or fallback)
    aliases = {
        "surface_warning": "warning",
        "warn": "warning",
        "warning": "warning",
        "remind": "light_nudge",
        "light_nudge": "light_nudge",
        "offer": "offer_next_step",
        "offer_next_step": "offer_next_step",
        "state_check": "state_check",
        "backstage_prepare": "backstage_only",
        "backstage_only": "backstage_only",
        "silent": "silent",
        # First-slice tickets are proposals only. A source row that asks for
        # push-forward is downgraded to an offer so host policy keeps ownership
        # of permission, sequencing, and final execution.
        "push_forward": "offer_next_step",
    }
    return aliases.get(text, fallback if fallback in INTERVENTION_LEVELS else "backstage_only")


def proposed_action_for(level: str, row: Mapping[str, Any]) -> dict[str, str]:
    existing = row.get("proposed_action")
    if isinstance(existing, Mapping):
        verb = str(existing.get("verb") or "")
        obj = str(existing.get("object") or existing.get("target") or "")
        if verb:
            return {"verb": compact_text(verb, 80), "object": compact_text(obj, 180)}
    if level == "warning":
        return {"verb": "warn_route", "object": compact_text(str(row.get("summary") or ""), 180)}
    if level == "offer_next_step":
        return {"verb": "ask_checkin", "object": compact_text(str(row.get("summary") or ""), 180)}
    if level == "state_check":
        return {"verb": "ask_checkin", "object": compact_text(str(row.get("summary") or ""), 180)}
    if level == "light_nudge":
        return {"verb": "summarize_state", "object": compact_text(str(row.get("summary") or ""), 180)}
    if level == "backstage_only":
        return {"verb": "refresh_sources", "object": compact_text(str(row.get("summary") or ""), 180)}
    return {"verb": "stay_silent", "object": ""}


def scope_for(row: Mapping[str, Any], source_kind: str) -> dict[str, Any]:
    scope = row.get("scope") if isinstance(row.get("scope"), Mapping) else {}
    stable = (
        scope.get("stable_id")
        if isinstance(scope, Mapping)
        else None
    ) or row.get("decision_id") or row.get("activation_event_id") or row.get("ticket_id")
    return {
        "kind": str((scope.get("kind") if isinstance(scope, Mapping) else None) or "thread"),
        "stable_id": str(stable or stable_id("scope", source_kind, row.get("summary") or "")),
        "label": compact_text(str((scope.get("label") if isinstance(scope, Mapping) else None) or row.get("title") or ""), 140),
    }


def why_now_explanation(row: Mapping[str, Any], summary: str) -> str:
    raw_why = row.get("why_now")
    if isinstance(raw_why, Mapping):
        value = raw_why.get("explanation") or raw_why.get("reason") or summary
    else:
        value = raw_why or row.get("why_now_explanation") or summary
    return compact_text(str(value or ""), 220)


def affordance_from_row(
    row: Mapping[str, Any],
    *,
    source_kind: str,
    default_trigger: str,
) -> dict[str, Any] | None:
    refs = merge_source_refs(
        row.get("source_refs") or [],
        row.get("evidence_refs") or [],
        row.get("clean_source_refs") or [],
    )
    trigger = normalize_trigger(row.get("trigger") or row.get("why_now_trigger"), default_trigger)
    if trigger not in TRIGGERS:
        return None
    level = normalize_level(
        row.get("intervention_level") or row.get("route") or row.get("level"),
        "backstage_only",
    )
    if row.get("kind") == "aippocampus_coding_continuity_ticket":
        level = normalize_level(row.get("intervention_level"), "warning")
    if row.get("kind") == "correction_active_task_anchor":
        level = "warning" if row.get("adjudication_status") == "valid_ignored" else "light_nudge"
    if source_kind == "unfinished_task":
        level = normalize_level(row.get("intervention_level"), "state_check")
    if source_kind == "scheduled_revisit":
        level = normalize_level(row.get("intervention_level"), "offer_next_step")

    summary = compact_text(str(row.get("summary") or row.get("title") or row.get("instruction") or ""), 520)
    if not summary and not refs:
        return None
    thickness = source_thickness(refs, str(row.get("source_thickness") or ""))
    action = proposed_action_for(level, row)
    affordance_id = stable_id(
        "agency_affordance",
        source_kind,
        trigger,
        level,
        summary,
        source_ref_fingerprint(refs),
        length=20,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": AFFORDANCE_KIND,
        "affordance_id": affordance_id,
        "created_at": row.get("created_at") or now_utc(),
        "source_kind": source_kind,
        "source_ids": unique_preserve(
            [
                str(value)
                for value in [
                    row.get("ticket_id"),
                    row.get("decision_id"),
                    row.get("candidate_id"),
                    row.get("activation_event_id"),
                ]
                if value
            ],
            limit=8,
        ),
        "scope": scope_for(row, source_kind),
        "intervention_level": level,
        "proposed_action": action,
        "why_now": {
            "trigger": trigger,
            "explanation": why_now_explanation(row, summary),
        },
        "evidence_refs": refs,
        "source_thickness": thickness,
        "confidence": round(float(row.get("confidence") or 0.65), 4),
        "annoyance_risk": str(row.get("annoyance_risk") or ("high" if level == "warning" else "medium")),
        "do_not_do": unique_preserve(
            [str(value) for value in row.get("do_not_do") or row.get("do_not_repeat") or [] if value],
            limit=8,
        ),
        "preconditions": unique_preserve(
            [str(value) for value in row.get("preconditions") or [] if value],
            limit=8,
        ),
        "requires_user_confirmation": bool(
            row.get("requires_user_confirmation", level in {"state_check", "offer_next_step", "warning"})
        ),
        "expires_at": str(row.get("expires_at") or "topic_epoch_end"),
        "outcome_feedback_expected": [
            "accepted",
            "ignored",
            "dismissed",
            "corrected",
            "tool_success",
            "tool_failure",
        ],
        "matched_terms_only": bool(row.get("matched_terms_only")),
    }


def build_agency_affordance_map(
    *,
    cognitive_map_inputs: Sequence[Mapping[str, Any]] | None = None,
    correction_windows: Sequence[Mapping[str, Any]] | None = None,
    ambient_recall_cards: Sequence[Mapping[str, Any]] | None = None,
    dream_outputs: Sequence[Mapping[str, Any]] | None = None,
    coding_tickets: Sequence[Mapping[str, Any]] | None = None,
    unfinished_tasks: Sequence[Mapping[str, Any]] | None = None,
    scheduled_revisits: Sequence[Mapping[str, Any]] | None = None,
    topic_epoch: str = "default",
) -> dict[str, Any]:
    groups = [
        ("cognitive_map", "compaction_loss", cognitive_map_inputs or []),
        ("correction_window", "user_correction", correction_windows or []),
        ("ambient_recall", "compaction_loss", ambient_recall_cards or []),
        ("dream_output", "compaction_loss", dream_outputs or []),
        ("coding_ticket", "compaction_loss", coding_tickets or []),
        ("unfinished_task", "unfinished_task_reentry", unfinished_tasks or []),
        ("scheduled_revisit", "scheduled_revisit", scheduled_revisits or []),
    ]
    affordances: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_kind, default_trigger, rows in groups:
        for row in rows:
            affordance = affordance_from_row(
                row,
                source_kind=source_kind,
                default_trigger=default_trigger,
            )
            if not affordance:
                continue
            key = str(affordance.get("affordance_id") or "")
            if key in seen:
                continue
            seen.add(key)
            affordances.append(affordance)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": MAP_KIND,
        "created_at": now_utc(),
        "topic_epoch": topic_epoch,
        "affordance_count": len(affordances),
        "affordances": affordances,
        "artifact_boundary": {
            "host_owns_permission": True,
            "host_owns_priority": True,
            "host_owns_sequencing": True,
            "host_owns_safety_policy": True,
            "ai_action_execution": False,
        },
    }


def recently_surfaced(
    affordance: Mapping[str, Any],
    *,
    topic_epoch: str,
    surface_history: Sequence[Mapping[str, Any]],
) -> bool:
    affordance_id = str(affordance.get("affordance_id") or "")
    source_fp = source_ref_fingerprint(affordance.get("evidence_refs") or [])
    for item in surface_history or []:
        if str(item.get("topic_epoch") or "") != topic_epoch:
            continue
        if str(item.get("affordance_id") or "") == affordance_id:
            return True
        if source_fp and str(item.get("source_ref_fingerprint") or "") == source_fp:
            return True
    return False


def can_surface_foreground(
    affordance: Mapping[str, Any],
    *,
    visible_context_ref_keys: set[tuple[str, str, str, str]],
    topic_epoch: str,
    surface_history: Sequence[Mapping[str, Any]],
) -> bool:
    level = str(affordance.get("intervention_level") or "")
    if level not in FOREGROUND_LEVELS:
        return False
    if affordance.get("matched_terms_only"):
        return False
    refs = affordance.get("evidence_refs") or []
    if is_visible(refs, visible_context_ref_keys=visible_context_ref_keys):
        return False
    if recently_surfaced(affordance, topic_epoch=topic_epoch, surface_history=surface_history):
        return False
    thickness = str(affordance.get("source_thickness") or "thin")
    if level != "state_check" and SOURCE_THICKNESS_RANK.get(thickness, 0) <= 0:
        return False
    if str(affordance.get("annoyance_risk") or "") == "high" and level not in {"warning", "state_check"}:
        return False
    return True


def ticket_from_affordance(
    affordance: Mapping[str, Any],
    *,
    topic_epoch: str,
    foreground: bool,
) -> dict[str, Any]:
    refs = [dict(ref) for ref in affordance.get("evidence_refs") or [] if isinstance(ref, Mapping)]
    ticket_id = stable_id(
        "agency_ticket",
        topic_epoch,
        affordance.get("affordance_id"),
        affordance.get("intervention_level"),
        length=20,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": TICKET_KIND,
        "ticket_id": ticket_id,
        "created_at": now_utc(),
        "topic_epoch": topic_epoch,
        "affordance_id": affordance.get("affordance_id"),
        "scope": affordance.get("scope") or {},
        "intervention_level": affordance.get("intervention_level"),
        "foreground": foreground,
        "proposed_action": affordance.get("proposed_action") or {},
        "why_now": affordance.get("why_now") or {},
        "evidence_refs": refs,
        "source_refs": refs,
        "source_ref_fingerprint": source_ref_fingerprint(refs),
        "source_thickness": affordance.get("source_thickness"),
        "confidence": affordance.get("confidence"),
        "annoyance_risk": affordance.get("annoyance_risk"),
        "do_not_do": affordance.get("do_not_do") or [],
        "preconditions": affordance.get("preconditions") or [],
        "requires_user_confirmation": bool(affordance.get("requires_user_confirmation", True)),
        "expires_at": affordance.get("expires_at"),
        "outcome_feedback_expected": affordance.get("outcome_feedback_expected") or list(OUTCOME_FEEDBACK),
        "host_boundary": {
            "aippocampus_proposes_only": True,
            "host_decides_permission": True,
            "host_decides_priority": True,
            "host_decides_sequence": True,
            "host_decides_safety": True,
        },
    }


def select_agency_tickets(
    affordance_map: Mapping[str, Any],
    *,
    trigger: str,
    topic_epoch: str,
    visible_context_refs: Sequence[Mapping[str, Any]] | None = None,
    surface_history: Sequence[Mapping[str, Any]] | None = None,
    foreground_limit: int = 1,
    backstage_limit: int = 3,
) -> dict[str, Any]:
    if trigger not in TRIGGERS:
        return {
            "ok": True,
            "kind": "aippocampus_agency_ticket_selection",
            "topic_epoch": topic_epoch,
            "trigger": trigger,
            "foreground_tickets": [],
            "backstage_tickets": [],
            "suppressed_count": 0,
        }
    visible_keys = visible_ref_keys(visible_context_refs or [])
    rows = [
        row
        for row in affordance_map.get("affordances") or []
        if isinstance(row, Mapping) and (row.get("why_now") or {}).get("trigger") == trigger
    ]
    rows.sort(
        key=lambda row: (
            LEVEL_RANK.get(str(row.get("intervention_level") or ""), 0),
            SOURCE_THICKNESS_RANK.get(str(row.get("source_thickness") or "thin"), 0),
            float(row.get("confidence") or 0.0),
        ),
        reverse=True,
    )
    foreground: list[dict[str, Any]] = []
    backstage: list[dict[str, Any]] = []
    suppressed = 0
    for row in rows:
        if can_surface_foreground(
            row,
            visible_context_ref_keys=visible_keys,
            topic_epoch=topic_epoch,
            surface_history=surface_history or [],
        ):
            if len(foreground) < foreground_limit:
                foreground.append(ticket_from_affordance(row, topic_epoch=topic_epoch, foreground=True))
            else:
                suppressed += 1
            continue
        level = str(row.get("intervention_level") or "")
        if level in BACKSTAGE_LEVELS and len(backstage) < backstage_limit:
            backstage.append(ticket_from_affordance(row, topic_epoch=topic_epoch, foreground=False))
        else:
            suppressed += 1
    return {
        "ok": True,
        "kind": "aippocampus_agency_ticket_selection",
        "schema_version": SCHEMA_VERSION,
        "topic_epoch": topic_epoch,
        "trigger": trigger,
        "foreground_tickets": foreground,
        "backstage_tickets": backstage,
        "suppressed_count": suppressed,
        "policy": {
            "foreground_limit": foreground_limit,
            "backstage_limit": backstage_limit,
            "source_thickness_rule": "foreground_requires_usable_except_state_check",
            "similar_words_alone_suppressed": True,
        },
    }


def record_ticket_feedback(
    ticket: Mapping[str, Any],
    *,
    outcome: str,
    note: str = "",
    tool_status: str | None = None,
) -> dict[str, Any]:
    if outcome not in OUTCOME_FEEDBACK:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOME_FEEDBACK)}")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": FEEDBACK_KIND,
        "created_at": now_utc(),
        "ticket_id": ticket.get("ticket_id"),
        "affordance_id": ticket.get("affordance_id"),
        "topic_epoch": ticket.get("topic_epoch"),
        "outcome": outcome,
        "tool_status": tool_status,
        "note": compact_text(note, 260),
        "source_refs": ticket.get("source_refs") or [],
    }


def append_feedback_events(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if row.get("kind") != FEEDBACK_KIND:
                raise ValueError(f"unsupported agency feedback row kind: {row.get('kind')}")
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            count += 1
    return count


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON affordance map input or prebuilt map.")
    parser.add_argument("--output")
    parser.add_argument("--trigger", choices=TRIGGERS, default="compaction_loss")
    parser.add_argument("--topic-epoch", default="default")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if raw.get("kind") == MAP_KIND:
            affordance_map = raw
        else:
            affordance_map = build_agency_affordance_map(
                cognitive_map_inputs=raw.get("cognitive_map_inputs") or [],
                correction_windows=raw.get("correction_windows") or [],
                ambient_recall_cards=raw.get("ambient_recall_cards") or [],
                dream_outputs=raw.get("dream_outputs") or [],
                coding_tickets=raw.get("coding_tickets") or [],
                unfinished_tasks=raw.get("unfinished_tasks") or [],
                scheduled_revisits=raw.get("scheduled_revisits") or [],
                topic_epoch=args.topic_epoch,
            )
        result = select_agency_tickets(
            affordance_map,
            trigger=args.trigger,
            topic_epoch=args.topic_epoch,
        )
        payload = {"ok": True, "affordance_map": affordance_map, "selection": result}
        if args.output:
            write_json(Path(args.output).resolve(), payload)
    except Exception as exc:
        if not args.json_output:
            raise
        payload = cli_error_payload(exc)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(payload["error"]["code"])

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        selection = payload["selection"]
        print(f"affordances: {payload['affordance_map']['affordance_count']}")
        print(f"foreground tickets: {len(selection['foreground_tickets'])}")
        print(f"backstage tickets: {len(selection['backstage_tickets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
