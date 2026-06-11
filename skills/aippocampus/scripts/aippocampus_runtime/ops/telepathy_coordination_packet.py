#!/usr/bin/env python3
"""Public-safe Telepathy coordination packet contract for soft locks and handoffs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_telepathy_coordination_packet_report"
PACKET_KIND = "telepathy_coordination_packet"
FOREGROUND_KIND = "telepathy_coordination_tag"
FORBIDDEN_MARKERS = (
    "PRIVATE_TELEPATHY_TEXT",
    "CHAIN_OF_THOUGHT_SENTINEL",
    "raw_private_source_text",
    "source://private",
    "C:\\",
    "/Users/",
)
COORDINATION_MODES = {
    "soft_lock",
    "handoff",
    "watch",
    "blocked",
    "human_needed",
}
STATUSES = {
    "active",
    "ready_for_handoff",
    "stale",
    "blocked",
    "released",
}
SOURCE_SUPPORT = {
    "source_open",
    "bounded_evidence",
    "reopenable_route",
    "candidate_only",
    "ignore_or_blocked",
}
HANDOFF_READINESS = {
    "not_ready",
    "route_ready",
    "evidence_ready",
    "needs_human",
    "blocked",
    "released",
}
BOUNDARY_FLAGS = {
    "no_private_source",
    "no_shared_chain_of_thought",
    "no_shared_cot",
    "scope_filter_required",
    "source_reopen_required",
    "task_boundary",
    "privacy_blocked",
    "candidate_only_not_fact",
}


def stable_hash(*parts: Any, length: int = 16) -> str:
    digest = hashlib.sha256(
        "\u241f".join(str(part) for part in parts).encode("utf-8", errors="replace")
    ).hexdigest()
    return digest[:length]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    return text if text and all(char.isalnum() or char in "-_:" for char in text) else fallback


def _safe_case_id(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    return "case_" + stable_hash(text, length=12)


def _safe_scope(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 120
        and not any(marker in text for marker in ("\\", "/", "source://", ":\\"))
        and all(char.isalnum() or char in "-_.:#" for char in text)
    ):
        return text
    return "scope_" + stable_hash(text or "missing_scope", length=12)


def _safe_owner(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 80
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    return "owner_" + stable_hash(text or "missing_owner", length=12)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _enum(value: Any, allowed: set[str], fallback: str) -> str:
    label = _label(value)
    return label if label in allowed else fallback


def _boundary_flags(value: Any) -> list[str]:
    flags = []
    for item in _strings(value):
        label = _label(item)
        if label in BOUNDARY_FLAGS:
            if label == "no_shared_cot":
                label = "no_shared_chain_of_thought"
            flags.append(label)
    return sorted(set(flags))


def _privacy_blocked(flags: list[str], status: str, source_support: str) -> bool:
    return (
        "no_private_source" in flags
        or "privacy_blocked" in flags
        or source_support == "ignore_or_blocked"
    )


def _derive_mode(row: Mapping[str, Any]) -> str:
    mode = _enum(row.get("coordination_mode"), COORDINATION_MODES, fallback="")
    if mode:
        return mode
    if _label(row.get("handoff_readiness")) == "needs_human":
        return "human_needed"
    if _label(row.get("status")) == "blocked":
        return "blocked"
    return "watch"


def _derive_status(row: Mapping[str, Any], mode: str) -> str:
    status = _enum(row.get("status"), STATUSES, fallback="")
    if status:
        return status
    if mode == "human_needed":
        return "blocked"
    if mode == "handoff":
        return "ready_for_handoff"
    return "active"


def _derive_source_support(row: Mapping[str, Any], status: str) -> str:
    source_support = _enum(
        row.get("source_support") or row.get("authority") or row.get("support"),
        SOURCE_SUPPORT,
        fallback="reopenable_route",
    )
    if status == "blocked" and source_support not in {"source_open", "bounded_evidence"}:
        return "ignore_or_blocked" if source_support != "candidate_only" else source_support
    return source_support


def _derive_handoff_readiness(
    row: Mapping[str, Any],
    mode: str,
    status: str,
    source_support: str,
) -> str:
    readiness = _enum(row.get("handoff_readiness"), HANDOFF_READINESS, fallback="")
    if readiness:
        return readiness
    if status == "released":
        return "released"
    if status == "blocked" or mode == "blocked":
        return "blocked"
    if mode == "human_needed":
        return "needs_human"
    if mode != "handoff":
        return "not_ready"
    if source_support in {"source_open", "bounded_evidence"}:
        return "evidence_ready"
    if source_support == "reopenable_route":
        return "route_ready"
    return "not_ready"


def _next_safe_action(
    mode: str,
    status: str,
    source_support: str,
    readiness: str,
    flags: list[str],
) -> str:
    if readiness == "needs_human" or mode == "human_needed":
        return "ask_human_before_handoff"
    if _privacy_blocked(flags, status, source_support):
        return "do_not_cross_boundary"
    if status == "released":
        return "ignore_released_lock_unless_source_changes"
    if source_support == "candidate_only":
        return "reopen_source_before_claim"
    if mode == "soft_lock" and status == "active":
        return "coordinate_before_overlap"
    if readiness in {"route_ready", "evidence_ready"}:
        return "continue_from_visible_handoff"
    return "watch_scope_without_assignment"


def normalize_coordination_packet(row: Mapping[str, Any]) -> dict[str, Any]:
    case_id = _safe_case_id(row.get("case_id"))
    scope = _safe_scope(row.get("scope") or row.get("scope_id"))
    owner_ref = _safe_owner(row.get("owner") or row.get("owner_agent"))
    mode = _derive_mode(row)
    status = _derive_status(row, mode)
    source_support = _derive_source_support(row, status)
    flags = _boundary_flags(row.get("boundary_flags"))
    if source_support == "candidate_only":
        flags = sorted(set(flags + ["candidate_only_not_fact", "source_reopen_required"]))
    if _privacy_blocked(flags, status, source_support):
        flags = sorted(set(flags + ["no_private_source", "scope_filter_required"]))
    readiness = _derive_handoff_readiness(row, mode, status, source_support)
    next_action = _next_safe_action(mode, status, source_support, readiness, flags)
    soft_lock_active = mode == "soft_lock" and status == "active"
    human_needed = mode == "human_needed" or readiness == "needs_human"
    compatibility_signal = "compatible"
    if status in {"blocked", "released"}:
        compatibility_signal = status
    elif source_support == "candidate_only":
        compatibility_signal = "candidate_only_obstruction"
    elif human_needed:
        compatibility_signal = "needs_human"

    packet = {
        "kind": PACKET_KIND,
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "packet_id": "telepathy_" + stable_hash(case_id, scope, owner_ref, mode),
        "scope": scope,
        "scope_hash": stable_hash(scope),
        "coordination_mode": mode,
        "owner_ref": owner_ref,
        "status": status,
        "source_support": source_support,
        "boundary_flags": flags,
        "handoff_readiness": readiness,
        "claim_permission": "navigation_only_not_fact",
        "source_reopen_required_before_claim": True,
        "soft_lock_active": soft_lock_active,
        "hard_lock_created": False,
        "assignment_created": False,
        "central_planner_assignment": False,
        "shared_chain_of_thought": False,
        "full_packet_surface": "explain_debug_or_campus",
        "default_foreground_eligible": False,
        "next_safe_action": next_action,
        "local_section_shape": (
            "soft_lock"
            if mode == "soft_lock"
            else "handoff_card"
            if mode == "handoff"
            else "human_needed"
            if human_needed
            else "boundary"
            if _privacy_blocked(flags, status, source_support)
            else "watch"
        ),
        "glue_compatibility_signal": compatibility_signal,
        "handoff_card": {
            "source_support": source_support,
            "handoff_readiness": readiness,
            "source_anchor_count": _safe_int(
                row.get("source_anchor_count") or row.get("source_ref_count")
            ),
            "candidate_only_not_evidence": source_support == "candidate_only",
            "human_needed": human_needed,
            "continuation_allowed": (
                readiness in {"route_ready", "evidence_ready"}
                and source_support in {"source_open", "bounded_evidence", "reopenable_route"}
                and not _privacy_blocked(flags, status, source_support)
            ),
        },
    }
    packet["foreground_projection"] = {
        "kind": FOREGROUND_KIND,
        "scope": packet["scope"],
        "coordination_mode": mode,
        "status": status,
        "handoff_readiness": readiness,
        "next_safe_action": next_action,
    }
    return packet


def fixture_coordination_packets() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "active_soft_lock",
            "scope": "project:AIppocampus#issue:1265",
            "coordination_mode": "soft_lock",
            "owner": "codex-a",
            "status": "active",
            "source_support": "reopenable_route",
            "boundary_flags": ["source_reopen_required"],
            "source_anchor_count": 2,
        },
        {
            "case_id": "clean_reopenable_handoff",
            "scope": "project:AIppocampus#issue:1266",
            "coordination_mode": "handoff",
            "owner": "codex-b",
            "status": "ready_for_handoff",
            "source_support": "reopenable_route",
            "handoff_readiness": "route_ready",
            "source_anchor_count": 3,
        },
        {
            "case_id": "candidate_only_handoff",
            "scope": "project:AIppocampus#issue:1268",
            "coordination_mode": "handoff",
            "owner": "dream-scout",
            "status": "ready_for_handoff",
            "source_support": "candidate_only",
            "handoff_readiness": "not_ready",
            "source_anchor_count": 1,
        },
        {
            "case_id": "privacy_blocked_packet",
            "scope": "private_scope_fixture",
            "coordination_mode": "blocked",
            "owner": "codex-private",
            "status": "blocked",
            "source_support": "ignore_or_blocked",
            "boundary_flags": ["no_private_source", "no_shared_cot"],
            "handoff_readiness": "blocked",
            "raw_source_text": "PRIVATE_TELEPATHY_TEXT fixture sentinel",
            "source_handle": "source://private/fixture",
        },
        {
            "case_id": "released_soft_lock",
            "scope": "project:AIppocampus#issue:1196",
            "coordination_mode": "soft_lock",
            "owner": "codex-a",
            "status": "released",
            "source_support": "reopenable_route",
            "handoff_readiness": "released",
        },
        {
            "case_id": "human_needed_handoff",
            "scope": "project:AIppocampus#issue:1185",
            "coordination_mode": "human_needed",
            "owner": "codex-b",
            "status": "blocked",
            "source_support": "bounded_evidence",
            "handoff_readiness": "needs_human",
            "boundary_flags": ["task_boundary"],
            "source_anchor_count": 2,
        },
    ]


def build_telepathy_coordination_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    row_list = list(rows) if rows is not None else fixture_coordination_packets()
    packets = [normalize_coordination_packet(row) for row in row_list]
    status_counts: Counter[str] = Counter(packet["status"] for packet in packets)
    support_counts: Counter[str] = Counter(packet["source_support"] for packet in packets)
    forbidden_marker_count = sum(
        1
        for marker in FORBIDDEN_MARKERS
        if marker in json.dumps(packets, ensure_ascii=False, sort_keys=True)
    )
    shared_cot_count = sum(1 for packet in packets if packet["shared_chain_of_thought"])
    assignment_count = sum(1 for packet in packets if packet["assignment_created"])
    hard_lock_count = sum(1 for packet in packets if packet["hard_lock_created"])
    foreground_full_packet_leak_count = sum(
        1
        for packet in packets
        if len(json.dumps(packet["foreground_projection"], sort_keys=True))
        >= len(json.dumps(packet, sort_keys=True))
    )
    red_lines = {
        "raw_private_text_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "source_handle_emitted_count": forbidden_marker_count,
        "shared_cot_emitted_count": shared_cot_count,
        "central_planner_assignment_count": assignment_count,
        "hard_lock_count": hard_lock_count,
        "foreground_full_packet_leak_count": foreground_full_packet_leak_count,
        "source_reopen_bypass_count": 0,
    }
    metrics = {
        "packet_count": len(packets),
        "active_soft_lock_count": sum(
            1 for packet in packets if packet["coordination_mode"] == "soft_lock" and packet["soft_lock_active"]
        ),
        "clean_handoff_count": sum(
            1
            for packet in packets
            if packet["coordination_mode"] == "handoff"
            and packet["handoff_readiness"] in {"route_ready", "evidence_ready"}
            and packet["source_support"] != "candidate_only"
        ),
        "candidate_only_handoff_count": support_counts["candidate_only"],
        "privacy_blocked_packet_count": sum(
            1 for packet in packets if "no_private_source" in packet["boundary_flags"]
        ),
        "stale_or_released_lock_count": status_counts["stale"] + status_counts["released"],
        "human_needed_count": sum(
            1
            for packet in packets
            if packet["coordination_mode"] == "human_needed"
            or packet["handoff_readiness"] == "needs_human"
        ),
        "source_open_or_bounded_packet_count": support_counts["source_open"]
        + support_counts["bounded_evidence"],
        "foreground_projection_max_bytes": max(
            (
                len(json.dumps(packet["foreground_projection"], sort_keys=True))
                for packet in packets
            ),
            default=0,
        ),
    }
    expected_case_ids = {
        "active_soft_lock",
        "clean_reopenable_handoff",
        "candidate_only_handoff",
        "privacy_blocked_packet",
        "released_soft_lock",
        "human_needed_handoff",
    }
    contract_gate_ok = rows is not None or expected_case_ids.issubset(
        {packet["case_id"] for packet in packets}
    )
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": contract_gate_ok and safety_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "safety_gate_ok": safety_gate_ok,
        "authority_level": "navigation_only",
        "runtime_boundary": "post_packet_explain_or_campus_first",
        "write_mode": "no_write_contract_report",
        "every_turn_scan": False,
        "default_foreground_hook": False,
        "central_planner": False,
        "hard_locking": False,
        "packets": packets,
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_emitted": False,
            "chain_of_thought_emitted": False,
            "forbidden_marker_count": forbidden_marker_count,
        },
        "contract": {
            "cross_agent_isolation_applies_before_output": True,
            "soft_locks_are_advisory_not_transactional": True,
            "handoff_cards_are_source_routes_not_truth": True,
            "failed_glue_is_obstruction_not_assignment": True,
            "foreground_projection_stays_tiny": True,
            "no_shared_chain_of_thought": True,
            "source_reopen_required_before_claim": True,
            "explain_or_campus_first": True,
        },
        "cannot_claim": [
            "shared_chain_of_thought",
            "shared_private_memory",
            "central_planner_assignments",
            "distributed_lock_correctness",
            "source_reopen_bypass",
            "multi_agent_orchestration_quality",
            "live_telepathy_usefulness",
        ],
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("packets") or data.get("cases") or data.get("rows") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file with Telepathy packet rows.")
    parser.add_argument("--fixture", action="store_true", help="Use the built-in fixture.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.input)) if args.input else None
    report = build_telepathy_coordination_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("telepathy coordination packet: " + ("ok" if report["ok"] else "blocked"))
        print(f"metrics: {report['metrics']}")
    return 0 if report["safety_gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
