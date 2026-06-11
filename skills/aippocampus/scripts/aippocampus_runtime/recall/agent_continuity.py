"""Opt-in agent continuity path over existing recall and AIppo contracts.

This module is deliberately a thin adapter. It gives coding agents one
callable path for the #1130 pull gesture without creating a new memory store,
new ranking layer, or claim authority. Foreground packets stay compact; source
refs and support ledgers only appear after an explicit deepen call.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.aippo import working_contract as aippo
from aippocampus_runtime.mcp.recall_navigation import (
    RecallNavigationError,
    navigation_error_payload,
    normalize_handle,
    recall_context_packet,
    recall_deepen_packet,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import agent_facade_contract as facade
from aippocampus_runtime.recall import feedback_events

SCHEMA_VERSION = "agent-opt-in-continuity-v0"
KIND = "aippocampus_agent_continuity_path"
MAX_ROUTES = 5
FOREGROUND_FORBIDDEN_KEYS = {
    "source_refs",
    "source_handles",
    "source_id",
    "message_id",
    "turn_id",
    "head_votes",
    "masks_applied",
    "raw_text",
}


def _as_path(value: str | Path | None, fallback: Path) -> Path:
    if value is None or value == "":
        return fallback
    return Path(value).resolve() if isinstance(value, Path) else Path(str(value)).resolve()


def _clean_source_dir(cwd: Path, explicit: str | Path | None = None) -> Path:
    if explicit:
        return core.canonical_path(explicit)
    global_dir = core.default_thread_clean_source_dir(cwd)
    legacy_dir = cwd / ".aippocampus" / "clean-source"
    if (global_dir / "messages.jsonl").exists() or not (legacy_dir / "messages.jsonl").exists():
        return global_dir
    return legacy_dir


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _count_forbidden_keys(value: Any) -> int:
    if isinstance(value, Mapping):
        count = sum(1 for key in value if str(key) in FOREGROUND_FORBIDDEN_KEYS)
        return count + sum(_count_forbidden_keys(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_forbidden_keys(item) for item in value)
    return 0


def _policy_boundary() -> dict[str, Any]:
    return {
        "opt_in_required": True,
        "default_hook_foreground": False,
        "navigation_only_not_fact": True,
        "source_reopen_required_for_strong_claims": True,
        "low_risk_guidance_allowed_without_reopen": True,
        "public_sdk_stability_claim": False,
        "hosted_api_claim": False,
    }


def _route_kind(route: Mapping[str, Any]) -> str:
    return str(route.get("kind") or "navigation_route").strip() or "navigation_route"


def _route_label(route: Mapping[str, Any]) -> str:
    explicit = str(route.get("route_label") or "").strip()
    if explicit:
        return explicit
    kind = _route_kind(route)
    title = str(route.get("title") or "").strip()
    if title:
        return f"{kind}: {title}"
    return kind


def _route_why(route: Mapping[str, Any]) -> str:
    explicit = str(route.get("why_this_may_matter") or "").strip()
    if explicit and route.get("route_label"):
        return explicit
    kind = _route_kind(route)
    if kind == "continuity_domain":
        return "Continuity domain matched the cue; deepen before using details."
    if kind == "pathlet":
        return "Ordered route chain matched the cue; reopen source before claims."
    if kind == "thread_candidate":
        return "Thread candidate matched the cue; locate source refs before relying on it."
    return "Clean-source route matched the cue; reopen before using details."


def _triage_reason_codes(route: Mapping[str, Any], output_mode: str) -> list[str]:
    explicit = [
        str(code)
        for code in route.get("triage_rank_reason_codes") or []
        if str(code).strip()
    ]
    if explicit:
        return explicit[:4]
    reason_codes = [f"route_kind_{_route_kind(route)}"]
    if output_mode == "reopenable_route":
        reason_codes.append("source_reopen_required")
    if route.get("scope_labels"):
        reason_codes.append("scope_label_available")
    if str(route.get("evidence_level") or "") in {"needs_reopen", "needs_domain_deepen"}:
        reason_codes.append("reopen_before_claim")
    return reason_codes[:4]


def _triage_risk_flags(route: Mapping[str, Any], output_mode: str) -> list[str]:
    flags: list[str] = []
    if output_mode == "reopenable_route":
        flags.append("source_reopen_required")
    currentness = str(route.get("currentness") or "").casefold()
    conflict = str(route.get("conflict") or "").casefold()
    if currentness in {"stale", "needs_reopen", "superseded"}:
        flags.append("check_currentness")
    if conflict and conflict not in {"none", "unknown"}:
        flags.append("conflict_requires_deepen")
    return flags


def _route_packet_from_navigation_route(route: Mapping[str, Any]) -> dict[str, Any]:
    action = str(route.get("action_grammar") or "")
    if action == "ignore_or_blocked":
        output_mode = "ignore_or_blocked"
    elif route.get("reopenable") or route.get("handle"):
        output_mode = "reopenable_route"
    else:
        output_mode = "direction_only"
    return {
        "route_id": str(route.get("route_id") or "route:unknown"),
        "output_mode": output_mode,
        "claim_permission": "blocked" if output_mode == "ignore_or_blocked" else "no_claim_before_reopen",
        "source_handles": [{"handle": route.get("handle"), "kind": route.get("kind")}]
        if route.get("handle")
        else [],
        "head_votes": [],
        "masks_applied": ["blocked"] if output_mode == "ignore_or_blocked" else [],
        "route_label": _route_label(route),
        "why_may_matter": _route_why(route),
        "preview_permission": "route_selection_only",
        "route_kind": _route_kind(route),
        "matched_cue_family": route.get("matched_cue_family"),
        "scope_bucket": route.get("scope_bucket"),
        "risk_flags": _triage_risk_flags(route, output_mode),
        "triage_rank_reason_codes": _triage_reason_codes(route, output_mode),
    }


def _memory_packet_for_route(route: Mapping[str, Any]) -> dict[str, Any]:
    packet = facade.memory_packet_from_route_packet(_route_packet_from_navigation_route(route))
    if packet["next_action"] == "use_hint" and route.get("handle"):
        packet["next_action"] = "reopen_source"
    return packet


def _deepen_request_for_route(route: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "route_id": packet.get("route_id"),
        "deepen_route_id": packet.get("deepen_route_id"),
        "tool": "agent deepen",
        "handle": route.get("handle"),
        "boundary": "opaque_navigation_handle_not_fact",
        "claim_boundary": "source_reopen_required_before_strong_claim",
    }


def _selection_hint_present(packet: Mapping[str, Any]) -> bool:
    label = str(packet.get("route_label") or "").strip()
    hint = str(packet.get("display_hint") or "").strip()
    return bool(label) and bool(
        hint
        and hint != "A source route may matter; reopen it before using the detail."
    )


def _triage_signature(packet: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(packet.get("route_label") or "").casefold(),
            str(packet.get("display_hint") or "").casefold(),
            ",".join(str(code) for code in packet.get("triage_rank_reason_codes") or []),
        ]
    )


def _memory_packet_triage_metrics(memory_packets: list[dict[str, Any]]) -> dict[str, Any]:
    triage_packets = [
        packet
        for packet in memory_packets
        if packet.get("output_mode") in {"bounded_summary_as_route", "reopenable_route"}
    ]
    signatures = {
        _triage_signature(packet)
        for packet in triage_packets
        if _selection_hint_present(packet)
    }
    distinctiveness = round(len(signatures) / len(triage_packets), 3) if triage_packets else 0.0
    return {
        "packet_triage_distinctiveness": distinctiveness,
        "blind_deepen_required_count": sum(
            1
            for packet in triage_packets
            if packet.get("output_mode") == "reopenable_route"
            and packet.get("next_action") == "reopen_source"
            and not _selection_hint_present(packet)
        ),
        "top_route_selection_hint_present_count": sum(
            1 for packet in triage_packets if _selection_hint_present(packet)
        ),
    }


def _is_aippo_deepen_id(value: Any) -> bool:
    text = str(value or "")
    aippo_id = aippo.AIPPO_ID
    return text in {aippo_id, f"deepen:{aippo_id}"} or text.startswith("deepen:aippo_")


def _project_workflow_contract() -> dict[str, Any]:
    return aippo.build_project_workflow_public_safe_contract()


def _aippo_red_lines(contract: Mapping[str, Any], activation: Mapping[str, Any]) -> dict[str, int]:
    active_ids = set(activation.get("active_clause_ids") or [])
    clauses = [clause for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    return {
        "stale_clause_activated_as_current": sum(
            1
            for clause in clauses
            if clause.get("clause_id") in active_ids
            and (clause.get("lifecycle") or {}).get("status")
            in {"stale", "challenged", "blocked", "retired"}
        ),
        "candidate_only_signal_promoted_without_source": sum(
            1
            for clause in clauses
            if clause.get("clause_id") in active_ids
            and (clause.get("authority") or {}).get("class") != "truth_source"
        ),
        "feedback_promoted_without_source": 0,
    }


def recall(
    query: str,
    *,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    max_routes: int = MAX_ROUTES,
) -> dict[str, Any]:
    """Return compact MemoryPackets plus explicit deepen handles for an agent pull."""

    cwd_path = core.canonical_path(cwd or Path.cwd())
    source_dir = _clean_source_dir(cwd_path, clean_source_dir)
    registry_path = _as_path(registry_dir, Path()) if registry_dir else None
    try:
        packet = recall_context_packet(
            intent=str(query or ""),
            cwd=cwd_path,
            clean_source_dir=source_dir,
            registry_dir=registry_path,
            max_routes=max(1, min(25, int(max_routes or MAX_ROUTES))),
        )
    except RecallNavigationError as exc:
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "recall",
                "surface": "agent_cli_or_mcp_adapter",
                "status": "cannot_verify",
                "opt_in_required": True,
                "memory_packets": [],
                "deepen_requests": [],
                "result": navigation_error_payload(exc),
                "policy_boundary": _policy_boundary(),
                "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
            }
        )
    routes = [route for route in packet.get("routes") or [] if isinstance(route, Mapping)]
    memory_packets = [_memory_packet_for_route(route) for route in routes]
    deepen_requests = [
        _deepen_request_for_route(route, memory_packet)
        for route, memory_packet in zip(routes, memory_packets, strict=True)
        if route.get("handle")
    ]
    forbidden_count = _count_forbidden_keys(memory_packets)
    triage_metrics = _memory_packet_triage_metrics(memory_packets)
    result = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "recall",
        "surface": "agent_cli_or_mcp_adapter",
        "status": "ok" if memory_packets else "no_routes",
        "opt_in_required": True,
        "memory_packets": memory_packets,
        "deepen_requests": deepen_requests,
        "suggested_next": "agent deepen" if deepen_requests else "search_memory",
        "policy_boundary": _policy_boundary(),
        "metrics": {
            "memory_packet_count": len(memory_packets),
            "deepen_request_count": len(deepen_requests),
            "foreground_forbidden_key_count": forbidden_count,
            **triage_metrics,
            "source_reopen_success_rate_observed": None,
            "wrong_or_stale_handle_rate_observed": None,
        },
        "red_lines": {
            "foreground_source_dump_count": forbidden_count,
            "source_backed_claim_without_reopen": 0,
            "feedback_promoted_without_source": 0,
        },
        "cannot_claim": [
            "source_truth_without_deepen",
            "default_agent_hook_activation",
            "public_sdk_stability",
        ],
    }
    return _public_payload(result)


def activate_aippo(*, task: str = "") -> dict[str, Any]:
    """Return the compact project/workflow AIppo activation packet."""

    contract = _project_workflow_contract()
    activation = aippo.activation_packet_from_working_contract(contract, task=task)
    usefulness = aippo.usefulness.usefulness_metrics(contract, activation)
    red_lines = _aippo_red_lines(contract, activation)
    result = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "aippo",
        "surface": "project_workflow_ai_ppocampus",
        "status": "ok" if activation.get("active_clause_count") else "no_active_contract",
        "opt_in_required": True,
        "task_hint_used": bool(str(task or "").strip()),
        "activation_packet": activation,
        "policy_boundary": _policy_boundary(),
        "metrics": {
            "active_clause_count": activation.get("active_clause_count", 0),
            **usefulness,
            "foreground_forbidden_key_count": _count_forbidden_keys(activation),
        },
        "red_lines": red_lines,
        "cannot_claim": [
            "aippo_marketplace_readiness",
            "claim_ready_facts_without_source_reopen",
            "default_foreground_activation",
        ],
    }
    return _public_payload(result)


def deepen(
    handle: Any,
    *,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    max_matches: int = MAX_ROUTES,
) -> dict[str, Any]:
    """Deepen a recall navigation handle or project AIppo activation id."""

    if _is_aippo_deepen_id(handle):
        contract = _project_workflow_contract()
        result = {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "deepen",
            "surface": "aippo",
            "status": "ok",
            "result": aippo.deepen_aippo_working_contract(contract),
            "policy_boundary": _policy_boundary(),
            "cannot_claim": ["facts_outside_opened_source_scope"],
        }
        return _public_payload(result)

    cwd_path = core.canonical_path(cwd or Path.cwd())
    source_dir = _clean_source_dir(cwd_path, clean_source_dir)
    registry_path = _as_path(registry_dir, Path()) if registry_dir else None
    try:
        payload = recall_deepen_packet(
            handle=handle,
            clean_source_dir=source_dir,
            registry_dir=registry_path,
            max_matches=max(1, min(25, int(max_matches or MAX_ROUTES))),
        )
    except RecallNavigationError as exc:
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "deepen",
                "surface": "recall",
                "status": "cannot_verify",
                "result": navigation_error_payload(exc),
                "policy_boundary": _policy_boundary(),
                "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
            }
        )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "deepen",
            "surface": "recall",
            "status": "ok",
            "result": payload,
            "policy_boundary": _policy_boundary(),
            "cannot_claim": ["facts_outside_opened_source_scope"],
        }
    )


def explain(handle: Any) -> dict[str, Any]:
    """Return public-safe reason codes for a recall handle or AIppo id."""

    if _is_aippo_deepen_id(handle):
        contract = _project_workflow_contract()
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "explain",
                "surface": "aippo",
                "status": "ok",
                "explanation": aippo.explain_aippo_working_contract(contract),
                "policy_boundary": _policy_boundary(),
            }
        )
    try:
        normalized = normalize_handle(handle)
    except RecallNavigationError as exc:
        return _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "explain",
                "surface": "recall",
                "status": "cannot_verify",
                "explanation": navigation_error_payload(exc),
                "policy_boundary": _policy_boundary(),
                "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
            }
        )
    kind = str(normalized.get("kind") or "source_ref")
    route_id = str(
        normalized.get("route_id") or normalized.get("domain_id") or normalized.get("lock_id") or ""
    )
    reason = "reopenable_route_available"
    if kind == "continuity_domain":
        reason = "continuity_domain_route_available"
    elif kind == "active_recall_lock":
        reason = "active_recall_lock_route_available"
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "explain",
            "surface": "recall",
            "status": "ok",
            "explanation": {
                "kind": "aippocampus_route_explanation",
                "schema_version": facade.SCHEMA_VERSION,
                "route_id": route_id,
                "decision": "why_recall",
                "output_mode": "reopenable_route",
                "claim_permission": "no_claim_before_reopen",
                "next_safe_action": "reopen_source",
                "reason_codes": [reason, "handle_is_navigation_not_fact"],
                "cannot_claim": ["source_truth_without_deepen", "foreground_packet_as_full_provenance"],
            },
            "policy_boundary": _policy_boundary(),
        }
    )


def capture_feedback(
    *,
    route_id: str,
    outcome: str,
    route_kind: str = "active_path",
    reason: str = "",
    feedback_path: str | Path | None = None,
) -> dict[str, Any]:
    """Capture low-authority outcome feedback without changing source truth."""

    event = feedback_events.active_flow_event(
        route_id=route_id,
        route_kind=route_kind,
        signal=outcome,
        source_id=route_id,
        reason=reason,
    )
    wrote_event = False
    if feedback_path:
        target = Path(feedback_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        wrote_event = True
    report = feedback_events.recall_feedback_report([event])
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "feedback",
            "status": "captured",
            "authority": "low_authority_feedback_signal",
            "event": event,
            "feedback_report": report,
            "wrote_event": wrote_event,
            "storage": "jsonl" if wrote_event else "receipt_only",
            "policy_boundary": {
                **_policy_boundary(),
                "feedback_is_source_truth": False,
                "feedback_can_ripen_candidate_without_source": False,
                "source_reopen_required_for_claims": True,
            },
            "red_lines": {
                "feedback_promoted_without_source": 0,
                "source_truth_changed_by_feedback": 0,
            },
        }
    )


def _json_out(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus agent",
        description="Opt-in agent recall, AIppo activation, deepen, explain, and feedback.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    recall_parser = sub.add_parser("recall")
    recall_parser.add_argument("query", nargs="*")
    recall_parser.add_argument("--query", dest="query_flag")
    recall_parser.add_argument("--cwd")
    recall_parser.add_argument("--clean-source-dir")
    recall_parser.add_argument("--registry-dir")
    recall_parser.add_argument("--max", type=int, default=MAX_ROUTES)
    recall_parser.add_argument("--json", action="store_true")

    aippo_parser = sub.add_parser("aippo")
    aippo_parser.add_argument("task", nargs="*")
    aippo_parser.add_argument("--task", dest="task_flag")
    aippo_parser.add_argument("--json", action="store_true")

    deepen_parser = sub.add_parser("deepen")
    deepen_parser.add_argument("handle")
    deepen_parser.add_argument("--cwd")
    deepen_parser.add_argument("--clean-source-dir")
    deepen_parser.add_argument("--registry-dir")
    deepen_parser.add_argument("--max", type=int, default=MAX_ROUTES)
    deepen_parser.add_argument("--json", action="store_true")

    explain_parser = sub.add_parser("explain")
    explain_parser.add_argument("handle")
    explain_parser.add_argument("--json", action="store_true")

    feedback_parser = sub.add_parser("feedback")
    feedback_parser.add_argument("route_id")
    feedback_parser.add_argument("--outcome", default="candidate_delivered")
    feedback_parser.add_argument("--route-kind", default="active_path")
    feedback_parser.add_argument("--reason", default="")
    feedback_parser.add_argument("--feedback-jsonl")
    feedback_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "recall":
        query = args.query_flag or " ".join(args.query)
        _json_out(
            recall(
                query,
                cwd=args.cwd,
                clean_source_dir=args.clean_source_dir,
                registry_dir=args.registry_dir,
                max_routes=args.max,
            )
        )
        return 0
    if args.command == "aippo":
        task = args.task_flag or " ".join(args.task)
        _json_out(activate_aippo(task=task))
        return 0
    if args.command == "deepen":
        _json_out(
            deepen(
                args.handle,
                cwd=args.cwd,
                clean_source_dir=args.clean_source_dir,
                registry_dir=args.registry_dir,
                max_matches=args.max,
            )
        )
        return 0
    if args.command == "explain":
        _json_out(explain(args.handle))
        return 0
    if args.command == "feedback":
        _json_out(
            capture_feedback(
                route_id=args.route_id,
                outcome=args.outcome,
                route_kind=args.route_kind,
                reason=args.reason,
                feedback_path=args.feedback_jsonl,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
