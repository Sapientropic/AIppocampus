"""CLI-only support helpers for the opt-in agent continuity facade."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.mcp.public_projection import compact_agent_recall_payload

LAST_RECALL_CACHE_ENV = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
DEFAULT_MACRO_STATE_RELATIVE_PATHS = (
    Path(".aippocampus") / "macro-orientation.jsonl",
    Path(".aippocampus") / "macro_orientation.jsonl",
)
LOCAL_PRIVATE_HANDLE_FIELDS = [
    "suggested_next_command",
    "foreground_action_card.callable_handle",
    "deepen_requests[].handle",
    "deepen_requests[].callable_handle",
    "deepen_requests[].machine_next_command",
    "deepen_requests[].copy_paste_command",
]
LOCAL_REOPEN_TOKEN_ENCODING = "utf8_xor_v1_not_encryption"
_LOCAL_REOPEN_TOKEN_MASK = 0xA5
MIN_ROUTE_LIMIT = 1
MAX_ROUTE_LIMIT = 25


class RouteLimitError(ValueError):
    """Raised when a caller passes an explicit, unsafe recall route limit."""


def normalize_route_limit(
    value: Any,
    *,
    default: int,
    field: str = "max",
    minimum: int = MIN_ROUTE_LIMIT,
    maximum: int = MAX_ROUTE_LIMIT,
) -> int:
    """Validate route limits without treating explicit zero as "use default".

    The recall facade used to coerce ``0`` through ``value or default`` and then
    clamp other invalid values. That made omitted limits and explicit invalid
    limits indistinguishable, which is surprising in both CLI and MCP surfaces.
    Keep omission ergonomic, but reject values that would silently change the
    caller's requested route budget.
    """

    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RouteLimitError(f"{field} must be an integer") from exc
    if parsed < minimum:
        raise RouteLimitError(f"{field} must be >= {minimum}")
    if parsed > maximum:
        raise RouteLimitError(f"{field} must be <= {maximum}")
    return parsed


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
    """Return compact recall JSON suitable for issue/discussion/log paste.

    Plain ``--json`` stays the local diagnostic surface with private reopen
    handles. The public/compact JSON path should be the same frontstage shape a
    foreground agent can actually use: one action, route receipts, and a clear
    source boundary, not a redacted audit dump.
    """

    source = dict(payload)
    source.update(handle_boundary_fields())
    projected = compact_agent_recall_payload(source)
    projected.update(handle_boundary_fields())
    projected["surface"] = "agent_cli_public_compact"
    projected["output_boundary"] = "public_compact_no_local_private_handles"
    projected["last_recall_cache_available"] = bool(source.get("last_recall_cache_available"))
    if projected.get("foreground_action"):
        projected["suggested_next_command"] = projected["foreground_action"].get(
            "cli_command",
            projected.get("public_safe_command_preview"),
        )
    return projected


def last_recall_cache_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get(LAST_RECALL_CACHE_ENV)
    if env:
        return Path(env).resolve()
    return core.aippocampus_registry_dir().resolve() / "agent" / "last-recall.json"


def _encode_local_reopen_token(value: Any) -> dict[str, Any]:
    """Encode a local reopen token so it is not stored as ordinary text.

    This is an accidental-disclosure guard for a same-machine cache, not a
    cryptographic promise. The handle remains local-private navigation material;
    public output should keep using `--public` / `--compact-json`.
    """

    raw = str(value or "").encode("utf-8")
    return {
        "encoding": LOCAL_REOPEN_TOKEN_ENCODING,
        "bytes": [byte ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw],
    }


def _decode_local_reopen_token(value: Any) -> str:
    if isinstance(value, Mapping) and value.get("encoding") == LOCAL_REOPEN_TOKEN_ENCODING:
        raw_bytes = value.get("bytes")
        if not isinstance(raw_bytes, list):
            return ""
        try:
            return bytes(int(byte) ^ _LOCAL_REOPEN_TOKEN_MASK for byte in raw_bytes).decode(
                "utf-8"
            )
        except (TypeError, ValueError, UnicodeDecodeError):
            return ""
    return ""


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def write_last_recall_cache(
    deepen_requests: Iterable[Any],
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
    requests: list[dict[str, Any]] = []
    for request in deepen_requests:
        if not isinstance(request, Mapping) or not request.get("handle"):
            continue
        requests.append(
            {
                "request_index": request.get("request_index"),
                "route_id": request.get("route_id"),
                "local_reopen_token": _encode_local_reopen_token(request.get("handle")),
            }
        )
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
            "project": project,
            "max": max_matches,
            "path_scope": "cwd_only_explicit_overrides_required",
        },
        "privacy_boundary": {
            "local_cache_only": True,
            "default_human_output_prints_cache_path": False,
            "derived_local_source_paths_persisted": False,
            "opaque_handles_are_navigation_not_facts": True,
            "opaque_handles_cleartext_persisted": False,
            "local_reopen_token_encoding": LOCAL_REOPEN_TOKEN_ENCODING,
            "local_reopen_token_encoding_is_encryption": False,
        },
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        # Local-only reopen handles are not credentials, but they are still
        # intentionally private navigation tokens. The cache stores an encoded
        # token for same-machine follow-through only; keep it out of human
        # output and avoid persisting derived source/registry paths above.
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
            handle = _decode_local_reopen_token(request.get("local_reopen_token"))
            if not handle and request.get("handle"):
                # Backward compatibility for caches written before the
                # local-reopen-token boundary existed.
                handle = str(request.get("handle") or "")
            return handle, dict(cache.get("context") or {})
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
    data = _mapping_or_empty(result)
    if status != "ok":
        error = _mapping_or_empty(data.get("error"))
        message = error.get("message") or data.get("message") or "Could not verify this handle."
        lines.append("Why: " + core.compact_text(str(message), 180))
        lines.append("Next: rerun agent recall and use the fresh handle.")
    elif surface == "aippo":
        ledger = _mapping_or_empty(data.get("source_support_ledger"))
        lines.append(f"Source support refs: {ledger.get('source_ref_count', 0)}")
        lines.append("Next: use --json only when auditing the working contract source ledger.")
    elif surface == "macro":
        validation = _mapping_or_empty(data.get("validation"))
        lines.append(f"Macro validation: {'ok' if validation.get('ok') else 'needs_attention'}")
        lines.append("Next: inspect --json before using source refs or derivation details.")
    else:
        window = _mapping_or_empty(data.get("source_window"))
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
