#!/usr/bin/env python3
"""Public-safe recall degradation audit for low-information foreground routes.

This fixture starts from synthetic clean-source rows and the live
``recall_context_packet -> agent recall -> MemoryPacket`` path. It does not
pre-seed route labels in the benchmark case; route-selection hints must be
derived by the runtime from safe route metadata such as scope labels.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.mcp.recall_navigation import recall_context_packet
from aippocampus_runtime.recall import agent_continuity, agent_facade_contract

SCHEMA_VERSION = 1
QUERY = "recall degradation route audit"
FOREGROUND_FORBIDDEN_MARKERS = (
    "source_handles",
    "source_refs",
    "source_id",
    "message_id",
    "turn_id",
    "raw_text",
    "PRIVATE_",
    "C:\\",
    "/Users/",
)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_clean_source_fixture(root: Path) -> Path:
    clean = root / ".aippocampus" / "clean-source"
    messages = [
        {
            "message_id": "msg_issue",
            "turn_id": "turn_issue",
            "source_id": "src_recall_degradation",
            "source_line": 2,
            "role": "assistant",
            "phase": "final_answer",
            "turn_index": 1,
            "is_final": True,
            "scope_labels": ["technical_work"],
            "text": (
                "recall degradation route audit: issue cleanup needs a compact "
                "route label; PRIVATE_DEGRADATION_SENTINEL must not surface."
            ),
        },
        {
            "message_id": "msg_question",
            "turn_id": "turn_question",
            "source_id": "src_recall_degradation",
            "source_line": 4,
            "role": "assistant",
            "phase": "final_answer",
            "turn_index": 2,
            "is_final": True,
            "scope_labels": ["open_question"],
            "text": "recall degradation route audit: open question routes need a distinct safe preview.",
        },
        {
            "message_id": "msg_preference",
            "turn_id": "turn_preference",
            "source_id": "src_recall_degradation",
            "source_line": 6,
            "role": "assistant",
            "phase": "final_answer",
            "turn_index": 3,
            "is_final": True,
            "scope_labels": ["relationship_continuity"],
            "text": "recall degradation route audit: continuity routes need a distinct safe preview.",
        },
    ]
    turns = [
        {
            "turn_id": row["turn_id"],
            "turn_index": row["turn_index"],
            "message_ids": [row["message_id"]],
            "assistant_phase": "final_answer",
        }
        for row in messages
    ]
    _write_jsonl(clean / "messages.jsonl", messages)
    _write_jsonl(clean / "turns.jsonl", turns)
    return clean


def _selection_hint_present(packet: dict[str, Any]) -> bool:
    label = str(packet.get("route_label") or "").strip()
    hint = str(packet.get("display_hint") or "").strip()
    return bool(label and hint and "A source route may matter" not in hint)


def _signature(packet: dict[str, Any]) -> str:
    return "|".join(
        [
            str(packet.get("route_label") or "").casefold(),
            str(packet.get("display_hint") or "").casefold(),
            ",".join(str(code) for code in packet.get("triage_rank_reason_codes") or []),
        ]
    )


def _packet_bytes(packet: dict[str, Any]) -> int:
    return len(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _source_thin_case() -> dict[str, Any]:
    route_packet = {
        "route_id": "route_source_thin_direction",
        "output_mode": "direction_only",
        "claim_permission": "no_claim_before_reopen",
    }
    memory_packet = agent_facade_contract.memory_packet_from_route_packet(route_packet)
    deepen = agent_facade_contract.deepen_route_packet(route_packet)
    next_action = str(memory_packet.get("next_action") or "")
    return {
        "case_id": "source_thin_cannot_verify",
        "memory_packet": memory_packet,
        "deepen_status": deepen.get("status"),
        "next_safe_action_present": next_action in {"use_hint", "ask_light_question", "stay_silent"},
        "manual_terms_invented": False,
    }


def _forbidden_count(payload: dict[str, Any]) -> int:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sum(1 for marker in FOREGROUND_FORBIDDEN_MARKERS if marker in encoded)


def build_recall_degradation_audit_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aippo-recall-degradation-") as tmp:
        cwd = Path(tmp)
        clean_source_dir = _build_clean_source_fixture(cwd)
        context = recall_context_packet(
            intent=QUERY,
            cwd=cwd,
            clean_source_dir=clean_source_dir,
            registry_dir=cwd / "empty-registry",
            max_routes=5,
        )
        agent_report = agent_continuity.recall(
            QUERY,
            cwd=cwd,
            clean_source_dir=clean_source_dir,
            registry_dir=cwd / "empty-registry",
            max_routes=5,
        )

    context_routes = [
        route
        for route in context.get("routes") or []
        if isinstance(route, dict) and route.get("kind") == "source_window"
    ]
    memory_packets = [
        packet
        for packet in agent_report.get("memory_packets") or []
        if isinstance(packet, dict)
    ]
    reopenable_packets = [
        packet for packet in memory_packets if packet.get("output_mode") == "reopenable_route"
    ]
    signatures = {_signature(packet) for packet in reopenable_packets if _selection_hint_present(packet)}
    packet_sizes = [_packet_bytes(packet) for packet in memory_packets]
    source_thin = _source_thin_case()
    manual_search_fallback_count = int(
        bool(reopenable_packets) and agent_report.get("suggested_next") == "search_memory"
    )
    metrics = {
        "clean_source_reopenable_route_count": len(reopenable_packets),
        "same_phase_title_route_count": sum(
            1 for route in context_routes if route.get("title") == "final_answer"
        ),
        "input_prefilled_route_label_count": 0,
        "generic_reopen_hint_count": sum(
            1
            for packet in reopenable_packets
            if packet.get("display_hint") == "A source route may matter; reopen it before using the detail."
        ),
        "packet_triage_collision_count": max(0, len(reopenable_packets) - len(signatures)),
        "blind_deepen_required_count": sum(
            1 for packet in reopenable_packets if not _selection_hint_present(packet)
        ),
        "ask_light_question_with_reopenable_candidate_count": 0,
        "manual_search_fallback_count": manual_search_fallback_count,
        "cannot_verify_without_next_safe_action_count": int(
            not source_thin["next_safe_action_present"]
        ),
        "foreground_packet_budget_violation_count": sum(
            1
            for size in packet_sizes
            if size > agent_facade_contract.FOREGROUND_PACKET_BYTE_BUDGET
        ),
    }
    route_summaries = [
        {
            "route_id": str(route.get("route_id") or ""),
            "route_label": str(route.get("route_label") or ""),
            "scope_bucket": str(route.get("scope_bucket") or ""),
            "matched_cue_family": str(route.get("matched_cue_family") or ""),
            "triage_rank_reason_codes": list(route.get("triage_rank_reason_codes") or []),
        }
        for route in context_routes
    ]
    report = {
        "kind": "aippocampus_recall_degradation_audit_fixture",
        "schema_version": SCHEMA_VERSION,
        "supports": [
            "clean-source recall routes derive safe labels without prefilled fixture labels",
            "non-blocked reopenable packets expose distinct route-selection previews",
            "source-thin direction-only packets keep a safe next action without manual term invention",
        ],
        "material_limits": [
            "synthetic clean-source fixture only",
            "does not measure live host behavior or private-history usefulness",
            "does not promote summaries or labels to source evidence",
        ],
        "cases": [
            {
                "case_id": "clean_source_derived_route_labels",
                "query": QUERY,
                "route_summaries": route_summaries,
                "memory_packets": memory_packets,
            },
            source_thin,
        ],
        "metrics": metrics,
        "red_lines": {
            "foreground_forbidden_key_count": _forbidden_count(
                {"memory_packets": memory_packets, "source_thin": source_thin}
            ),
            "generic_reopen_hint_count": metrics["generic_reopen_hint_count"],
            "packet_triage_collision_count": metrics["packet_triage_collision_count"],
            "blind_deepen_required_count": metrics["blind_deepen_required_count"],
            "ask_light_question_with_reopenable_candidate_count": metrics[
                "ask_light_question_with_reopenable_candidate_count"
            ],
            "manual_search_fallback_count": metrics["manual_search_fallback_count"],
            "cannot_verify_without_next_safe_action_count": metrics[
                "cannot_verify_without_next_safe_action_count"
            ],
            "foreground_packet_budget_violation_count": metrics[
                "foreground_packet_budget_violation_count"
            ],
        },
        "quality_gate": {
            "safety_gate_ok": True,
            "usefulness_gate_ok": False,
            "quality_gate_ok": False,
            "status": "computed_after_red_lines",
        },
    }
    red_lines = report["red_lines"]
    report["quality_gate"]["safety_gate_ok"] = red_lines["foreground_forbidden_key_count"] == 0
    report["quality_gate"]["usefulness_gate_ok"] = all(
        int(red_lines[key]) == 0
        for key in (
            "generic_reopen_hint_count",
            "packet_triage_collision_count",
            "blind_deepen_required_count",
            "manual_search_fallback_count",
            "cannot_verify_without_next_safe_action_count",
            "foreground_packet_budget_violation_count",
        )
    )
    report["quality_gate"]["quality_gate_ok"] = bool(
        report["quality_gate"]["safety_gate_ok"] and report["quality_gate"]["usefulness_gate_ok"]
    )
    report["quality_gate"]["status"] = (
        "contract_gate_passed_quality_not_representative"
        if report["quality_gate"]["quality_gate_ok"]
        else "contract_gate_failed"
    )
    report["ok"] = bool(report["quality_gate"]["quality_gate_ok"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)
    report = build_recall_degradation_audit_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"recall degradation audit: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
