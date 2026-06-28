"""Compact foreground projection for action-hint probe reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.foreground_compact_language import (
    compact_details_flag,
    strip_compact_policy_vocabulary,
)

SCHEMA_VERSION = 1


def _primary_probe_handle(hint: Mapping[str, Any]) -> dict[str, Any] | None:
    for handle in hint.get("source_handles") or []:
        if isinstance(handle, Mapping):
            return dict(handle)
    return None


def compact_probe_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the foreground probe card without feature extraction diagnostics."""

    raw_hint = report.get("hint")
    hint = raw_hint if isinstance(raw_hint, Mapping) else {}
    raw_auto_chain = report.get("auto_chain")
    auto_chain = raw_auto_chain if isinstance(raw_auto_chain, Mapping) else {}
    primary_handle = _primary_probe_handle(hint)
    useful = bool(report.get("useful"))
    action: dict[str, Any]
    if useful and primary_handle and primary_handle.get("command"):
        raw_arguments = primary_handle.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, Mapping) else {}
        action = {
            "id": "deepen_probe_source_route",
            "label": "Deepen probe source route",
            "command": str(primary_handle.get("command") or ""),
            "tool_name": str(primary_handle.get("tool_name") or "agent_deepen"),
            "arguments": dict(arguments),
            "why": "The probe matched a prepared action-time hint; open its source route before claims.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        }
    else:
        refresh_query = str((primary_handle or {}).get("query") or "").strip()
        chained_action = auto_chain.get("foreground_action")
        if auto_chain.get("status") == "auto_chained" and isinstance(chained_action, Mapping):
            action = dict(chained_action)
        else:
            refresh_command = (
                f"aippocampus agent recall {json.dumps(refresh_query, ensure_ascii=False)} --json"
                if refresh_query
                else "aippocampus hooks action refresh-cache --write --json"
            )
            action = {
                "id": "refresh_probe_source_route",
                "label": "Refresh probe source route",
                "command": refresh_command,
                "why": (
                    "The probe did not validate a live source route; refresh recall/source "
                    "routing before treating action-time hints as useful."
                ),
                "mutation_risk": "read_only" if refresh_query else "explicit_local_cache_write",
                "claim_boundary": "action_hints_are_navigation_not_source_truth",
            }
    compact_hint = None
    if hint:
        compact_hint = {
            "hint_id": str(hint.get("hint_id") or ""),
            "provider_family": str(hint.get("provider_family") or ""),
            "action_hint_kind": str(hint.get("action_hint_kind") or ""),
            "message": str(hint.get("message") or ""),
            "recommended_action": str(hint.get("recommended_action") or ""),
            "navigation_only": bool(hint.get("navigation_only", True)),
            "source_reopen_required": bool(hint.get("source_reopen_required", True)),
            "authority": str(hint.get("authority") or "navigation_only"),
            "source_ref_count": int(hint.get("source_ref_count") or 0),
        }
    payload = {
        "schema_version": int(report.get("schema_version") or SCHEMA_VERSION),
        "kind": "aippocampus_action_hint_probe_compact",
        "detail": "compact",
        "ok": bool(report.get("ok", True)),
        "decision": str(report.get("decision") or ""),
        "reason": str(report.get("reason") or ""),
        "useful": useful,
        "usefulness_stage": str(report.get("usefulness_stage") or ""),
        "auto_chained": auto_chain.get("status") == "auto_chained",
        "auto_chain_status": str(auto_chain.get("status") or "not_applicable"),
        "deferred_auto_chain_reason": (
            str(auto_chain.get("reason") or "")
            if auto_chain.get("status") in {"deferred", "failed"}
            else ""
        ),
        "hint": compact_hint,
        "foreground_action": action,
        "source_reopen_boundary": (
            "Probe usefulness means a navigation handle exists; deepen or reopen "
            "that source before factual claims."
        ),
        "claim_boundary": str(
            report.get("claim_boundary")
            or "action_hints_are_navigation_not_source_truth"
        ),
        "operator_detail_command": "aippocampus hooks action probe --json",
    }
    payload.update(compact_details_flag(payload))
    return strip_compact_policy_vocabulary(payload)


__all__ = ["compact_probe_report"]
