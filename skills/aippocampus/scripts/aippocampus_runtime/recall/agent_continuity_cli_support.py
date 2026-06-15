"""CLI-only support helpers for the opt-in agent continuity facade."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.macro import state as macro_state

LAST_RECALL_CACHE_ENV = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
DEFAULT_MACRO_STATE_RELATIVE_PATHS = (
    Path(".aippocampus") / "macro-orientation.jsonl",
    Path(".aippocampus") / "macro_orientation.jsonl",
)
LOCAL_PRIVATE_HANDLE_FIELDS = [
    "suggested_next_command",
    "deepen_requests[].handle",
    "deepen_requests[].callable_handle",
    "deepen_requests[].machine_next_command",
    "deepen_requests[].copy_paste_command",
]


def handle_boundary_fields() -> dict[str, Any]:
    return {
        "local_private_fields": list(LOCAL_PRIVATE_HANDLE_FIELDS),
        "public_safe_command_preview": "aippocampus agent deepen <local-private-handle>",
        "handle_boundary": "local_private_reopen_token",
        "public_safe_recall_command": "aippocampus agent recall <query> --json --public",
    }


def policy_boundary() -> dict[str, Any]:
    return {
        "opt_in_required": True,
        "default_hook_foreground": False,
        "navigation_only_not_fact": True,
        "source_reopen_required_for_strong_claims": True,
        "low_risk_guidance_allowed_without_reopen": True,
        "public_sdk_stability_claim": False,
        "hosted_api_claim": False,
    }


def public_recall_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return recall JSON suitable for issue/discussion/log paste.

    Full deepen handles are useful local reopen tokens, but they may encode
    source-route material. Keep local execution easy in default JSON while
    giving agents a no-handle projection for public handoff.
    """

    projected = dict(payload)
    projected.update(handle_boundary_fields())
    projected["suggested_next_command"] = projected.get("public_safe_command_preview")
    projected["output_boundary"] = "public_safe_no_local_private_handles"
    redacted_requests: list[dict[str, Any]] = []
    for raw_request in projected.get("deepen_requests") or []:
        if not isinstance(raw_request, Mapping):
            continue
        request = dict(raw_request)
        for key in ("handle", "callable_handle", "machine_next_command", "copy_paste_command"):
            request.pop(key, None)
        request["handle_redacted"] = True
        request["handle_boundary"] = "local_private_reopen_token"
        request["public_safe_command_preview"] = "aippocampus agent deepen <local-private-handle>"
        redacted_requests.append(request)
    projected["deepen_requests"] = redacted_requests
    return projected


def last_recall_cache_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get(LAST_RECALL_CACHE_ENV)
    if env:
        return Path(env).resolve()
    return core.aippocampus_registry_dir().resolve() / "agent" / "last-recall.json"


def write_last_recall_cache(
    payload: Mapping[str, Any],
    *,
    cwd: str | Path | None,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    macro_state_path: str | Path | None,
    project: str,
    max_matches: int,
    schema_version: str,
    path: str | Path | None = None,
) -> bool:
    requests = [
        {
            "request_index": request.get("request_index"),
            "route_id": request.get("route_id"),
            "handle": request.get("handle"),
        }
        for request in payload.get("deepen_requests") or []
        if isinstance(request, Mapping) and request.get("handle")
    ]
    if not requests:
        return False
    target = last_recall_cache_path(path)
    cache = {
        "kind": "aippocampus_agent_last_recall",
        "schema_version": schema_version,
        "written_at": core.now_utc(),
        "requests": requests[:25],
        "context": {
            "cwd": str(cwd) if cwd else None,
            "clean_source_dir": str(clean_source_dir) if clean_source_dir else None,
            "registry_dir": str(registry_dir) if registry_dir else None,
            "macro_state_jsonl": str(macro_state_path) if macro_state_path else None,
            "project": project,
            "max": max_matches,
        },
        "privacy_boundary": {
            "local_cache_only": True,
            "default_human_output_prints_cache_path": False,
            "opaque_handles_are_navigation_not_facts": True,
        },
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        return False
    return True


def read_last_recall_cache(path: str | Path | None = None) -> dict[str, Any]:
    target = last_recall_cache_path(path)
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("kind") != "aippocampus_agent_last_recall":
        raise ValueError("last recall cache has an unsupported shape")
    return data


def handle_from_last_recall_cache(
    *,
    request_index: int,
    path: str | Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    cache = read_last_recall_cache(path)
    requests = [request for request in cache.get("requests") or [] if isinstance(request, Mapping)]
    for request in requests:
        try:
            index = int(request.get("request_index") or 0)
        except (TypeError, ValueError):
            index = 0
        if index == request_index:
            return request.get("handle"), dict(cache.get("context") or {})
    raise ValueError(f"last recall cache does not contain request {request_index}")


def macro_state_template(project: str) -> dict[str, Any]:
    return dict(
        macro_state.build_macro_orientation_state(
            project=project,
            hexagram="乾",
            changing_lines=(1,),
            source_refs=({"source_id": "replace-with-clean-source-or-review-ref"},),
            updated_at=macro_state.utc_now_iso(),
        )
    )


def macro_schema_help(project: str, *, schema_version: str) -> dict[str, Any]:
    return {
        "kind": "aippocampus_macro_orientation_schema_help",
        "schema_version": schema_version,
        "project": project,
        "jsonl_path_candidates": [str(path) for path in DEFAULT_MACRO_STATE_RELATIVE_PATHS],
        "required_fields": [
            "kind=macro_orientation_state",
            "schema_version=0.1",
            "scope.kind=project",
            "scope.project",
            "hexagram",
            "changing_lines",
            "source_refs",
            "updated_at",
            "authority_level=navigation_only",
            "claim_permission=no_claim_before_reopen",
        ],
        "producer_hint": (
            "Append one JSON object per line to .aippocampus/macro-orientation.jsonl, "
            "or pass --macro-state-jsonl explicitly."
        ),
        "template": macro_state_template(project),
        "boundary": "macro_orientation_is_navigation_only_not_fact",
    }


def render_macro_schema_human(payload: Mapping[str, Any]) -> str:
    del payload
    lines = [
        "AIppocampus agent macro schema",
        "Required: project scope, hexagram, changing_lines, source_refs, updated_at.",
        "Default file: .aippocampus/macro-orientation.jsonl",
        "Boundary: navigation only; source refs are reopen routes, not proof.",
        "Use --init-template --json for a copyable JSONL row.",
    ]
    return "\n".join(lines)


def render_aippo_human(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    lines = [f"AIppo: {status}"]
    packet = payload.get("activation_packet")
    activation = packet if isinstance(packet, Mapping) else {}
    guidance = [str(item) for item in activation.get("use_guidance") or [] if str(item).strip()]
    if status == "no_active_contract":
        lines.append("No active working contract matched this task.")
        lines.append("Use instead: aippocampus agent recall <query> if prior source matters.")
    elif guidance:
        lines.append("Use: " + " | ".join(core.compact_text(item, 96) for item in guidance[:2]))
    else:
        lines.append("No compact guidance surfaced.")
    deepen_route = str(activation.get("deepen_route_id") or "").strip()
    if deepen_route:
        lines.append(f"Next: aippocampus agent deepen {deepen_route}")
    else:
        lines.append("Next: continue normally; use --json for diagnostics.")
    lines.append("Boundary: working guidance only; reopen source before factual claims.")
    return "\n".join(lines)


def render_macro_human(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    lines = [f"AIppocampus agent macro: {status}"]
    packets = [packet for packet in payload.get("memory_packets") or [] if isinstance(packet, Mapping)]
    if packets:
        packet = packets[0]
        lines.append(core.compact_text(str(packet.get("foreground_text") or "Macro route available."), 160))
        deepen_route = str(packet.get("deepen_route_id") or "").strip()
        if deepen_route:
            lines.append(f"Next: aippocampus agent deepen {deepen_route}")
    else:
        diagnostics = [str(item) for item in payload.get("diagnostics") or [] if str(item)]
        if diagnostics:
            lines.append("Why: " + ", ".join(diagnostics[:3]))
        lines.append("Expected: .aippocampus/macro-orientation.jsonl or --macro-state-jsonl.")
        lines.append("Repair: aippocampus agent macro --explain-schema")
    lines.append("Boundary: macro orientation is navigation only, not source truth.")
    return "\n".join(lines)


def render_deepen_human(payload: Mapping[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    surface = str(payload.get("surface") or "unknown")
    lines = [f"AIppocampus agent deepen: {status}", f"Surface: {surface}"]
    result = payload.get("result")
    data = result if isinstance(result, Mapping) else {}
    if status != "ok":
        error = data.get("error") if isinstance(data.get("error"), Mapping) else {}
        message = error.get("message") or data.get("message") or "Could not verify this handle."
        lines.append("Why: " + core.compact_text(str(message), 180))
        lines.append("Next: rerun agent recall and use the fresh handle.")
    elif surface == "aippo":
        ledger = data.get("source_support_ledger") if isinstance(data.get("source_support_ledger"), Mapping) else {}
        lines.append(f"Source support refs: {ledger.get('source_ref_count', 0)}")
        lines.append("Next: use --json only when auditing the working contract source ledger.")
    elif surface == "macro":
        validation = data.get("validation") if isinstance(data.get("validation"), Mapping) else {}
        lines.append(f"Macro validation: {'ok' if validation.get('ok') else 'needs_attention'}")
        lines.append("Next: inspect --json before using source refs or derivation details.")
    else:
        window = data.get("source_window") if isinstance(data.get("source_window"), Mapping) else {}
        message_count = int(window.get("message_count") or len(window.get("messages") or []))
        evidence = data.get("evidence_level") or data.get("support_level") or "source_open"
        lines.append(f"Evidence: {evidence}; source windows opened: {message_count}")
        why = str(data.get("why_this_may_matter") or "").strip()
        if why:
            lines.append("Why: " + core.compact_text(why, 160))
        lines.append("Next: rerun with --json to inspect the source window for exact wording.")
    lines.append("Boundary: use opened source only within scope; no broad claims from the handle.")
    return "\n".join(lines)


def render_recall_human(payload: Mapping[str, Any]) -> str:
    packets = [packet for packet in payload.get("memory_packets") or [] if isinstance(packet, Mapping)]
    deepen_requests = [
        request for request in payload.get("deepen_requests") or [] if isinstance(request, Mapping)
    ]
    lines = [f"AIppocampus agent recall: {payload.get('status') or 'unknown'}"]
    if not packets:
        lines.append("No compact route surfaced.")
    for index, packet in enumerate(packets[:3], start=1):
        label = (
            packet.get("route_topic")
            or packet.get("route_label")
            or packet.get("route_id")
            or "memory route"
        )
        next_action = packet.get("recommended_next") or packet.get("next_action") or "reopen_source"
        lines.append(f"{index}. {label} -> {next_action}")
        hint = packet.get("selection_hint")
        if isinstance(hint, Mapping) and hint.get("source"):
            lines.append(f"   why: {hint.get('source')}:{hint.get('why') or 'selected'}")
        reason_codes = packet.get("route_delta_reason_codes") or packet.get("triage_rank_reason_codes")
        if isinstance(reason_codes, list) and reason_codes:
            lines.append("   codes: " + ", ".join(str(code) for code in reason_codes[:3]))
    navigation = payload.get("navigation_signals")
    if isinstance(navigation, Mapping):
        signals = [str(signal) for signal in navigation.get("signals") or [] if str(signal)]
        if signals:
            action = str(navigation.get("next_safe_action") or "deepen_before_claim")
            lines.append(f"Navigation: {', '.join(signals[:3])} -> {action}")
    suggested_command = str(payload.get("suggested_next_command") or "").strip()
    if deepen_requests:
        first = deepen_requests[0]
        next_action = str(first.get("human_next_action") or "").strip()
        if payload.get("last_recall_cache_available") and "--json for callable handle" in next_action:
            request_index = int(first.get("request_index") or 1)
            next_action = f"aippocampus agent deepen --request {request_index} --last-recall"
        if not next_action:
            request_index = int(first.get("request_index") or 1)
            next_action = f"deepen route {request_index}; rerun with --json for callable handle"
        lines.append(f"Next: {next_action}.")
    elif suggested_command and "aippo-nav:" not in suggested_command and len(suggested_command) <= 160:
        lines.append(f"Next: {suggested_command}")
    else:
        lines.append(f"Next: {payload.get('suggested_next') or 'continue_normally'}")
    lines.append("Boundary: route only; reopen source before quoting or making strong claims.")
    return "\n".join(lines)
