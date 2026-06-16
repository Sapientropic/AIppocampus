#!/usr/bin/env python3
"""Opt-in local Telepathy handoff workflow over public-safe coordination cards."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.ops import coordination_topology
from aippocampus_runtime.ops import telepathy_coordination_packet as packets
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

SCHEMA_VERSION = 1
EVENT_KIND = "aippocampus_telepathy_handoff_event"
CARD_KIND = "aippocampus_telepathy_handoff_card"
LIST_KIND = "aippocampus_telepathy_handoff_list"
DEEPEN_KIND = "aippocampus_telepathy_handoff_deepen"
DIAGNOSE_KIND = "aippocampus_telepathy_handoff_diagnostic"
ERROR_KIND = "aippocampus_telepathy_handoff_error"

HANDOFF_PRESETS: dict[str, dict[str, Any]] = {
    "handoff": {
        "coordination_mode": "handoff",
        "source_support": "reopenable_route",
        "status": "ready_for_handoff",
        "handoff_readiness": "route_ready",
        "boundary_flags": [],
        "label": "another agent can continue after reopening source",
    },
    "soft-lock": {
        "coordination_mode": "soft_lock",
        "source_support": "reopenable_route",
        "status": "active",
        "handoff_readiness": "blocked",
        "boundary_flags": ["task_boundary"],
        "label": "keep attention on a scope without claiming distributed locking",
    },
    "human-needed": {
        "coordination_mode": "human_needed",
        "source_support": "candidate_only",
        "status": "blocked",
        "handoff_readiness": "needs_human",
        "boundary_flags": ["candidate_only_not_fact", "source_reopen_required"],
        "label": "mark a local handoff that needs human judgment before action",
    },
    "source-reopen": {
        "coordination_mode": "handoff",
        "source_support": "reopenable_route",
        "status": "active",
        "handoff_readiness": "route_ready",
        "boundary_flags": ["source_reopen_required"],
        "label": "leave a navigation-only route that must be reopened before claims",
    },
}

ACTIVE_LIFECYCLE_STATUSES = {"active", "ready_for_handoff", "blocked"}
SAFE_SOURCE_REF_KEYS = {
    "claim_id",
    "doc",
    "issue",
    "message_id",
    "pr",
    "route_id",
    "source_id",
    "source_line",
    "source_line_end",
    "source_line_start",
    "thread_key",
    "turn_id",
    "url",
}
PRIVATE_MARKERS = (
    "PRIVATE_TELEPATHY_TEXT",
    "CHAIN_OF_THOUGHT_SENTINEL",
    "raw_private_source_text",
    "source://private",
    "source://",
    "C:\\",
    "/Users/",
    "\\",
)


def default_store_path(cwd: str | Path | None = None) -> Path:
    """Return the registry-local Telepathy handoff event log path.

    Handoff cards are coordination state, not project source. Keep the implicit
    default in the same thread registry as generated recall artifacts so a repo
    checkout does not silently collect private local memory. Tests and public
    fixtures should pass ``--store-path`` explicitly.
    """

    cwd_path = core.canonical_path(cwd or os.getcwd())
    return core.default_thread_store_dir(cwd_path) / "telepathy" / "handoffs.jsonl"


def resolve_store_path(
    store_path: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> Path:
    cwd_path = core.canonical_path(cwd or os.getcwd())
    return core.resolve_artifact_path(store_path, cwd_path, default_store_path(cwd_path))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_event_id(card_id: str, event_type: str, event_time: str, ordinal: int) -> str:
    return "telepathy_event_" + packets.stable_hash(card_id, event_type, event_time, ordinal)


def _looks_private_or_path_like(value: str) -> bool:
    text = str(value)
    if any(marker in text for marker in PRIVATE_MARKERS):
        return True
    return (
        len(text) > 240
        or text.startswith("/")
        or text.startswith("~")
        or bool(text[:3].endswith(":\\"))
        or text.endswith((".jsonl", ".json", ".sqlite", ".md", ".txt"))
    )


def _scope_preview(value: str) -> dict[str, str]:
    text = _text(value)
    if text and not _looks_private_or_path_like(text):
        safe = redact_sensitive_values(redact_private_paths({"scope": text})).get("scope")
        if isinstance(safe, str) and safe == text and safe:
            return {
                "scope_label": safe[:120],
                "scope_visibility": "operator_supplied_public_safe",
            }
    return {
        "scope_label": "",
        "scope_visibility": "redacted_hash_only",
    }


def _source_ref_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return core.stable_text_fingerprint(
        raw,
        namespace="telepathy-source-ref",
        prefix="source_ref",
    )


def _safe_source_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    text = _text(value)
    if not text or _looks_private_or_path_like(text):
        return None
    return text


def sanitize_source_ref(value: Any) -> dict[str, Any]:
    """Return a reopenable-but-public-safe source ref projection.

    The store may be shared with another local agent through MCP read tools, so
    raw handles and paths are reduced to stable fingerprints unless they are
    already clean selector fields such as message ids, turn ids, issue numbers,
    or public URLs. This keeps the card useful for source reopen without letting
    "handoff" become a covert channel for private source text.
    """

    source_ref: dict[str, Any] = {"source_ref_hash": _source_ref_hash(value)}
    if not isinstance(value, Mapping):
        source_ref["source_ref_kind"] = "opaque"
        return source_ref
    for key, item in value.items():
        key_text = str(key)
        if key_text not in SAFE_SOURCE_REF_KEYS:
            continue
        safe_value = _safe_source_value(item)
        if safe_value not in (None, ""):
            source_ref[key_text] = safe_value
    if len(source_ref) == 1:
        source_ref["source_ref_kind"] = "redacted"
    return source_ref


def sanitize_source_refs(values: Iterable[Any] | None) -> list[dict[str, Any]]:
    return [sanitize_source_ref(item) for item in values or []]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def load_events(store_path: str | Path) -> list[dict[str, Any]]:
    return _read_jsonl(Path(store_path))


def _append_event(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _card_with_lifecycle(card: Mapping[str, Any], *, status: str, event_time: str) -> dict[str, Any]:
    row = dict(card)
    row["status"] = status
    row["updated_at"] = event_time
    row["handoff_readiness"] = "released" if status == "released" else row["handoff_readiness"]
    row["source_reopen_required_before_claim"] = True
    row["claim_permission"] = "navigation_only_not_fact"
    if status == "released":
        row["released_at"] = event_time
        row["next_safe_action"] = "ignore_released_lock_unless_source_changes"
        foreground = dict(row.get("foreground_projection") or {})
        foreground["status"] = "released"
        foreground["handoff_readiness"] = "released"
        foreground["next_safe_action"] = row["next_safe_action"]
        row["foreground_projection"] = foreground
        handoff_card = dict(row.get("handoff_card") or {})
        handoff_card["handoff_readiness"] = "released"
        handoff_card["continuation_allowed"] = False
        row["handoff_card"] = handoff_card
    return row


def current_handoff_cards(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for event in events:
        card_id = _text(event.get("card_id"))
        if not card_id:
            continue
        event_type = _text(event.get("event_type"))
        raw_card = event.get("card")
        event_time = _text(event.get("event_time")) or core.now_utc()
        if event_type == "create" and isinstance(raw_card, Mapping):
            cards[card_id] = dict(raw_card)
        elif event_type == "release":
            if isinstance(raw_card, Mapping):
                cards[card_id] = dict(raw_card)
            elif card_id in cards:
                cards[card_id] = _card_with_lifecycle(
                    cards[card_id],
                    status="released",
                    event_time=event_time,
                )
    return cards


def _public_projection(payload: Any, *, include_private_paths: bool = False) -> Any:
    redacted = redact_sensitive_values(payload)
    if include_private_paths:
        return redacted
    return redact_private_paths(redacted)


def _card_summary(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": CARD_KIND,
        "schema_version": SCHEMA_VERSION,
        "card_id": card.get("card_id"),
        "scope": card.get("scope"),
        "scope_label": card.get("scope_label"),
        "scope_visibility": card.get("scope_visibility"),
        "scope_hash": card.get("scope_hash"),
        "coordination_mode": card.get("coordination_mode"),
        "owner_ref": card.get("owner_ref"),
        "status": card.get("status"),
        "source_support": card.get("source_support"),
        "handoff_readiness": card.get("handoff_readiness"),
        "claim_permission": card.get("claim_permission"),
        "source_reopen_required_before_claim": card.get(
            "source_reopen_required_before_claim"
        ),
        "next_safe_action": card.get("next_safe_action"),
        "source_ref_count": card.get("source_ref_count", 0),
        "created_at": card.get("created_at"),
        "updated_at": card.get("updated_at"),
        "released_at": card.get("released_at"),
        "foreground_projection": card.get("foreground_projection"),
    }


def _status_matches(card: Mapping[str, Any], status: str | None) -> bool:
    if not status:
        return True
    card_status = _text(card.get("status"))
    if status == "active":
        return card_status in ACTIVE_LIFECYCLE_STATUSES
    return card_status == status


def _ordered_cards(cards: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(card) for card in cards),
        key=lambda item: (_text(item.get("updated_at")), _text(item.get("card_id"))),
        reverse=True,
    )


def create_handoff(
    *,
    scope: str,
    owner: str,
    coordination_mode: str = "handoff",
    source_support: str = "reopenable_route",
    status: str | None = None,
    handoff_readiness: str | None = None,
    boundary_flags: Iterable[str] | None = None,
    source_refs: Iterable[Any] | None = None,
    case_id: str | None = None,
    cwd: str | Path | None = None,
    store_path: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_store_path(store_path, cwd=cwd)
    now = core.now_utc()
    sanitized_refs = sanitize_source_refs(source_refs)
    packet_row = {
        "case_id": case_id
        or "handoff_"
        + packets.stable_hash(scope, owner, coordination_mode, source_support, length=12),
        "scope": scope,
        "coordination_mode": coordination_mode,
        "owner": owner,
        "status": status or ("ready_for_handoff" if coordination_mode == "handoff" else "active"),
        "source_support": source_support,
        "handoff_readiness": handoff_readiness,
        "boundary_flags": list(boundary_flags or []),
        "source_ref_count": len(sanitized_refs),
    }
    packet = packets.normalize_coordination_packet(packet_row)
    scope_preview = _scope_preview(scope)
    card_id = packet["packet_id"]
    card = {
        **packet,
        **scope_preview,
        "kind": CARD_KIND,
        "card_id": card_id,
        "created_at": now,
        "updated_at": now,
        "source_refs": sanitized_refs,
        "source_ref_count": len(sanitized_refs),
        "store_lifecycle": "append_only_event_log",
    }
    event_count = len(load_events(path))
    event = {
        "kind": EVENT_KIND,
        "schema_version": SCHEMA_VERSION,
        "event_id": _stable_event_id(card_id, "create", now, event_count),
        "event_type": "create",
        "event_time": now,
        "card_id": card_id,
        "card": card,
    }
    _append_event(path, event)
    return {
        "ok": True,
        "kind": "aippocampus_telepathy_handoff_created",
        "schema_version": SCHEMA_VERSION,
        "write_mode": "explicit_cli_append_only",
        "store_path": str(path),
        "event": event,
        "card": _card_summary(card),
    }


def _error_payload(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "kind": ERROR_KIND,
        "schema_version": SCHEMA_VERSION,
        "error": {
            "code": code,
            "message": message,
            "details": {key: value for key, value in details.items() if value is not None},
        },
    }


def list_handoffs_payload(
    *,
    cwd: str | Path | None = None,
    store_path: str | Path | None = None,
    scope: str | None = None,
    status: str | None = "active",
    limit: int = 20,
) -> dict[str, Any]:
    path = resolve_store_path(store_path, cwd=cwd)
    cards = _ordered_cards(current_handoff_cards(load_events(path)).values())
    if scope:
        scope_hash = packets.stable_hash(scope)
        cards = [
            card
            for card in cards
            if card.get("scope") == scope or card.get("scope_hash") == scope_hash
        ]
    cards = [card for card in cards if _status_matches(card, status)]
    limited = cards[: max(1, min(int(limit or 20), 100))]
    empty_state: dict[str, Any] | None = None
    if not cards:
        empty_state = {
            "state": "no_matching_telepathy_handoffs",
            "meaning": "No active opt-in handoff card is waiting for this filter.",
            "agent_next_action": (
                "Continue with normal recall/search, or create a handoff only when a "
                "human or upstream agent explicitly wants local coordination."
            ),
            "create_examples": [
                'aippocampus telepathy create --preset handoff --scope "issue:#123" --owner codex',
                'aippocampus telepathy create --preset human-needed --scope "release decision" --owner codex',
            ],
            "privacy_boundary": "Telepathy cards are navigation-only and not source-backed truth.",
        }
    return {
        "ok": True,
        "kind": LIST_KIND,
        "schema_version": SCHEMA_VERSION,
        "write_mode": "no_write_list",
        "store_path": str(path),
        "status_filter": status or "all",
        "scope_filter": scope,
        "cards": [_card_summary(card) for card in limited],
        "count": len(limited),
        "total_matching_count": len(cards),
        "empty_state": empty_state,
    }


def deepen_handoff_payload(
    *,
    card_id: str,
    cwd: str | Path | None = None,
    store_path: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_store_path(store_path, cwd=cwd)
    card = current_handoff_cards(load_events(path)).get(card_id)
    if card is None:
        return _error_payload(
            "handoff_not_found",
            "No Telepathy handoff card matched the requested card_id.",
            card_id=card_id,
            store_path=str(path),
        )
    return {
        "ok": True,
        "kind": DEEPEN_KIND,
        "schema_version": SCHEMA_VERSION,
        "write_mode": "no_write_deepen",
        "authority_level": "navigation_only_not_fact",
        "store_path": str(path),
        "card": card,
        "source_reopen": {
            "required_before_claim": True,
            "allowed_selector_fields": sorted(SAFE_SOURCE_REF_KEYS),
            "source_refs": card.get("source_refs") or [],
        },
        "cannot_claim": [
            "source_truth_without_reopen",
            "shared_private_memory",
            "shared_chain_of_thought",
            "distributed_lock_correctness",
        ],
    }


def release_handoff(
    *,
    card_id: str,
    cwd: str | Path | None = None,
    store_path: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_store_path(store_path, cwd=cwd)
    events = load_events(path)
    card = current_handoff_cards(events).get(card_id)
    if card is None:
        return _error_payload(
            "handoff_not_found",
            "No Telepathy handoff card matched the requested card_id.",
            card_id=card_id,
            store_path=str(path),
        )
    now = core.now_utc()
    released_card = _card_with_lifecycle(card, status="released", event_time=now)
    event = {
        "kind": EVENT_KIND,
        "schema_version": SCHEMA_VERSION,
        "event_id": _stable_event_id(card_id, "release", now, len(events)),
        "event_type": "release",
        "event_time": now,
        "card_id": card_id,
        "card": released_card,
    }
    _append_event(path, event)
    return {
        "ok": True,
        "kind": "aippocampus_telepathy_handoff_released",
        "schema_version": SCHEMA_VERSION,
        "write_mode": "explicit_cli_append_only",
        "store_path": str(path),
        "event": event,
        "card": _card_summary(released_card),
    }


def diagnose_handoffs_payload(
    *,
    cwd: str | Path | None = None,
    store_path: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_store_path(store_path, cwd=cwd)
    cards = _ordered_cards(current_handoff_cards(load_events(path)).values())
    lifecycle_counts: Counter[str] = Counter(_text(card.get("status")) for card in cards)
    active_cards = [
        card for card in cards if _text(card.get("status")) in ACTIVE_LIFECYCLE_STATUSES
    ]
    active_scope_counts = Counter(_text(card.get("scope")) for card in active_cards)
    duplicate_active_scopes = {
        scope: count for scope, count in active_scope_counts.items() if scope and count > 1
    }
    topology_rows = [packets.topology_row_from_coordination_packet(card) for card in cards]
    topology_report = coordination_topology.build_coordination_topology_report(topology_rows)
    packet_report = packets.build_telepathy_coordination_report(cards)
    public_projection = _public_projection(
        {
            "cards": [_card_summary(card) for card in cards],
            "store_path": str(path),
        }
    )
    encoded = json.dumps(public_projection, ensure_ascii=False, sort_keys=True)
    forbidden_marker_count = sum(
        1 for marker in packets.FORBIDDEN_MARKERS if marker in encoded
    )
    red_lines = {
        "raw_private_text_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "shared_cot_emitted_count": 0,
        "mcp_write_surface_count": 0,
        "candidate_promoted_to_evidence_count": sum(
            1
            for card in cards
            if card.get("source_support") == "candidate_only"
            and card.get("claim_permission") != "navigation_only_not_fact"
        ),
    }
    metrics = {
        "card_count": len(cards),
        "active_card_count": len(active_cards),
        "released_card_count": lifecycle_counts["released"],
        "duplicate_active_scope_count": len(duplicate_active_scopes),
        "next_safe_action_clarity_count": sum(
            1 for card in cards if _text(card.get("next_safe_action"))
        ),
        "source_backed_handoff_count": sum(
            1
            for card in cards
            if card.get("source_support")
            in {"source_open", "bounded_evidence", "reopenable_route"}
        ),
        "candidate_only_handoff_count": sum(
            1 for card in cards if card.get("source_support") == "candidate_only"
        ),
    }
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    usefulness_gate_ok = (
        metrics["active_card_count"] == 0
        or metrics["next_safe_action_clarity_count"] >= metrics["active_card_count"]
    )
    return {
        "ok": safety_gate_ok,
        "kind": DIAGNOSE_KIND,
        "schema_version": SCHEMA_VERSION,
        "write_mode": "no_write_diagnostic_only",
        "store_path": str(path),
        "authority_level": "navigation_only",
        "safety_gate_ok": safety_gate_ok,
        "usefulness_gate_ok": usefulness_gate_ok,
        "metrics": metrics,
        "duplicate_active_scopes": duplicate_active_scopes,
        "red_lines": red_lines,
        "topology": {
            "ok": topology_report["ok"],
            "metrics": topology_report["metrics"],
            "red_lines": topology_report["red_lines"],
        },
        "coordination_packets": {
            "ok": packet_report["ok"],
            "metrics": packet_report["metrics"],
            "red_lines": packet_report["red_lines"],
        },
        "cannot_claim": [
            "distributed_lock_correctness",
            "automatic_multi_agent_assignment",
            "source_truth_without_reopen",
            "live_telepathy_usefulness_without_dogfood",
        ],
    }


def _load_source_ref_json(value: str | None) -> list[Any]:
    if not value:
        return []
    parsed = json.loads(value)
    if isinstance(parsed, list):
        return parsed
    return [parsed]


def _render_diagnose_text(payload: Mapping[str, Any]) -> str:
    raw_metrics = payload.get("metrics")
    metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    active = int(metrics.get("active_card_count") or 0)
    candidate_only = int(metrics.get("candidate_only_handoff_count") or 0)
    if active:
        next_action = (
            "run `aippocampus telepathy list --status active`, then deepen or continue "
            "from the selected handoff card"
        )
    else:
        next_action = (
            "no active handoff found; create an explicit handoff or keep working normally"
        )
    lines = [
        "AIppocampus Telepathy handoff status",
        f"status: {'ok' if payload.get('ok') else 'blocked'}",
        f"active: {active}",
        f"released: {metrics.get('released_card_count', 0)}",
        f"source-backed: {metrics.get('source_backed_handoff_count', 0)}",
        f"candidate-only: {candidate_only}",
        f"write mode: {payload.get('write_mode')}",
        f"authority: {payload.get('authority_level')}",
        f"next: {next_action}",
    ]
    if candidate_only:
        lines.append("boundary: candidate-only handoffs require source reopen before reliance.")
    lines.append("diagnostic: no write performed")
    return "\n".join(lines)


def _print_payload(payload: Mapping[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if payload.get("kind") == DIAGNOSE_KIND:
        print(_render_diagnose_text(payload))
        return
    status = "ok" if payload.get("ok") else "blocked"
    print(f"{payload.get('kind', 'telepathy_handoff')}: {status}")
    if "count" in payload:
        print(f"count: {payload['count']}")
    empty_state = payload.get("empty_state")
    if isinstance(empty_state, Mapping):
        print(f"next: {empty_state.get('agent_next_action')}")
        examples = empty_state.get("create_examples")
        if isinstance(examples, list) and examples:
            print(f"example: {examples[0]}")
    if "card" in payload and isinstance(payload["card"], Mapping):
        card = payload["card"]
        print(f"card_id: {card.get('card_id')}")
        print(f"next_safe_action: {card.get('next_safe_action')}")


def _preset_help() -> str:
    lines = ["presets:"]
    for name, preset in HANDOFF_PRESETS.items():
        lines.append(f"  {name}: {preset['label']}")
    lines.append(
        'example: aippocampus telepathy create --preset handoff --scope "issue:#123" --owner codex'
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aippocampus telepathy", description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cwd", default=os.getcwd(), help="Workspace used for default store lookup.")
    common.add_argument("--store-path", help="Explicit Telepathy handoff JSONL store.")
    common.add_argument("--include-private-paths", action="store_true")
    common.add_argument("--json", action="store_true", help="Emit JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", parents=[common], epilog=_preset_help())
    create.add_argument("--preset", choices=sorted(HANDOFF_PRESETS), default="handoff")
    create.add_argument("--scope", required=True)
    create.add_argument("--owner", required=True)
    create.add_argument(
        "--coordination-mode",
        default=None,
        choices=sorted(packets.COORDINATION_MODES),
    )
    create.add_argument(
        "--source-support",
        default=None,
        choices=sorted(packets.SOURCE_SUPPORT),
    )
    create.add_argument("--status", choices=sorted(packets.STATUSES))
    create.add_argument("--handoff-readiness", choices=sorted(packets.HANDOFF_READINESS))
    create.add_argument("--boundary-flag", action="append", default=[])
    create.add_argument("--source-ref-json", help="JSON object/list with clean source selectors.")
    create.add_argument("--case-id")

    list_cmd = subparsers.add_parser("list", parents=[common])
    list_cmd.add_argument("--scope")
    list_cmd.add_argument("--status", default="active")
    list_cmd.add_argument("--max", type=int, default=20)

    deepen = subparsers.add_parser("deepen", parents=[common])
    deepen.add_argument("card_id")

    release = subparsers.add_parser("release", parents=[common])
    release.add_argument("card_id")

    subparsers.add_parser("diagnose", parents=[common])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            preset = HANDOFF_PRESETS.get(args.preset, HANDOFF_PRESETS["handoff"])
            boundary_flags = list(preset.get("boundary_flags") or []) + list(args.boundary_flag)
            payload = create_handoff(
                scope=args.scope,
                owner=args.owner,
                coordination_mode=args.coordination_mode or preset["coordination_mode"],
                source_support=args.source_support or preset["source_support"],
                status=args.status or preset["status"],
                handoff_readiness=args.handoff_readiness or preset["handoff_readiness"],
                boundary_flags=boundary_flags,
                source_refs=_load_source_ref_json(args.source_ref_json),
                case_id=args.case_id,
                cwd=args.cwd,
                store_path=args.store_path,
            )
        elif args.command == "list":
            payload = list_handoffs_payload(
                cwd=args.cwd,
                store_path=args.store_path,
                scope=args.scope,
                status=args.status,
                limit=args.max,
            )
        elif args.command == "deepen":
            payload = deepen_handoff_payload(
                card_id=args.card_id,
                cwd=args.cwd,
                store_path=args.store_path,
            )
        elif args.command == "release":
            payload = release_handoff(
                card_id=args.card_id,
                cwd=args.cwd,
                store_path=args.store_path,
            )
        else:
            payload = diagnose_handoffs_payload(cwd=args.cwd, store_path=args.store_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = _error_payload(type(exc).__name__, str(exc))

    payload = _public_projection(payload, include_private_paths=args.include_private_paths)
    _print_payload(payload, json_output=bool(args.json))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
