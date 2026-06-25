#!/usr/bin/env python3
"""Opt-in host-event capture for correction reconsolidation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, stable_json_tuple_id
from aippocampus_runtime.learning_loop import core as learning_core
from aippocampus_runtime.reflection import reconsolidation as corr
from aippocampus_runtime.source import behavior_events

CORRECTION_SIGNAL_RE = re.compile(
    r"(?i)\b(correction|correcting|actually|instead|not that|wrong route|wrong source|"
    r"do not|don't|avoid|fix scope|use the source|source-backed)\b|"
    r"(修正|纠正|更正|不是|不要|别|错了|路线|范围)"
)


def _host_event_name(payload: Mapping[str, Any]) -> str:
    return compact_text(
        str(payload.get("hook_event_name") or payload.get("event_name") or payload.get("event") or ""),
        80,
    )


def _host_thread_id(payload: Mapping[str, Any]) -> str:
    return compact_text(
        str(
            payload.get("thread_id")
            or payload.get("thread_key")
            or payload.get("session_id")
            or "unknown_thread"
        ),
        140,
    )


def _host_workspace(payload: Mapping[str, Any]) -> str:
    return str(payload.get("workspace") or payload.get("cwd") or "")


def _host_topic_epoch(payload: Mapping[str, Any]) -> str:
    return compact_text(str(payload.get("topic_epoch") or payload.get("topic") or "default"), 100)


def _host_source_refs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    policies: list[dict[str, Any]] = []
    refs = corr.sanitize_source_refs(
        payload.get("source_refs") or payload.get("evidence_refs") or [],
        policies=policies,
    )
    if refs:
        return refs
    thread_key = str(payload.get("thread_key") or payload.get("thread_id") or payload.get("session_id") or "")
    message_id = str(payload.get("message_id") or payload.get("source_message_id") or "")
    turn_id = str(payload.get("turn_id") or "")
    turn_index = str(payload.get("turn_index") or "")
    source_line = payload.get("source_line") or payload.get("line")
    if not thread_key or not (message_id or turn_id or turn_index or source_line):
        return []
    return corr.sanitize_source_refs(
        [
            {
                "thread_key": thread_key,
                "message_id": message_id,
                "turn_id": turn_id,
                "turn_index": turn_index,
                "source_line": source_line,
                "timestamp": payload.get("timestamp") or payload.get("created_at"),
            }
        ],
        policies=policies,
    )


def _host_target_type(payload: Mapping[str, Any], text: str) -> str:
    explicit = str(payload.get("target_type") or "")
    if explicit in corr.TARGET_TYPES:
        return explicit
    lowered = text.casefold()
    if any(token in lowered for token in ("route", "path", "wrong source", "source-backed", "路线")):
        return "route"
    if any(token in lowered for token in ("scope", "范围")):
        return "scope"
    if any(token in lowered for token in ("default", "默认")):
        return "default"
    if "test" in lowered or "测试" in lowered:
        return "test"
    if any(token in lowered for token in ("handoff", "交接")):
        return "handoff"
    return "claim"


def _host_importance(payload: Mapping[str, Any]) -> str:
    value = str(payload.get("provisional_importance") or "")
    return value if value in corr.PROVISIONAL_IMPORTANCE else "unknown"


def _host_adoption_signal(payload: Mapping[str, Any], text: str) -> str:
    explicit = str(payload.get("adoption_signal") or "")
    if explicit in corr.OUTCOME_SIGNALS:
        return explicit
    lowered = text.casefold()
    if any(token in lowered for token in ("adopted", "followed", "fixed", "kept", "used")):
        return "adopted"
    if any(token in lowered for token in ("ignored", "missed", "did not use")):
        return "ignored"
    if any(token in lowered for token in ("contradicted", "refuted", "wrong")):
        return "contradicted"
    return "unclear"


def _optional_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _host_scope(payload: Mapping[str, Any]) -> str:
    return compact_text(str(payload.get("scope") or "project_or_task_family"), 160)


def _host_workspace_profile(payload: Mapping[str, Any]) -> str:
    return compact_text(
        str(payload.get("workspace_or_environment_profile") or payload.get("environment_profile") or "host_runtime"),
        160,
    )


def _post_tool_exit_code(payload: Mapping[str, Any]) -> int | None:
    raw = payload.get("exit_code")
    if raw is None:
        raw = payload.get("tool_exit_code") or payload.get("returncode")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    text = str(payload.get("tool_response") or payload.get("output") or payload.get("error") or "")
    return behavior_events.parse_tool_exit_code(text)


def _post_tool_failed(payload: Mapping[str, Any]) -> bool:
    status = str(payload.get("status") or payload.get("tool_status") or "").casefold()
    if status in {"failed", "failure", "error", "timeout", "cancelled"}:
        return True
    if payload.get("success") is False:
        return True
    exit_code = _post_tool_exit_code(payload)
    if exit_code is not None:
        return exit_code != 0
    return bool(payload.get("error") or payload.get("exception") or payload.get("tool_error"))


def _expected_or_exploratory_failure(payload: Mapping[str, Any]) -> bool:
    phase = str(payload.get("failure_phase") or payload.get("review_semantics") or "").casefold()
    return bool(
        payload.get("expected_local_red")
        or payload.get("expected_red")
        or payload.get("exploratory_failure")
        or phase in {"expected_local_red", "review_only_expected_red", "exploratory", "tdd_red"}
    )


def _post_tool_behavior_event(
    payload: Mapping[str, Any],
    *,
    refs: Sequence[Mapping[str, Any]],
    created_at: str | None,
) -> dict[str, Any]:
    tool_name = compact_text(
        str(payload.get("tool_name") or payload.get("name") or payload.get("tool") or "tool"),
        120,
    )
    raw_input = payload.get("tool_input") or payload.get("arguments") or payload.get("args") or {}
    command = ""
    if isinstance(raw_input, Mapping):
        command = str(raw_input.get("command") or raw_input.get("cmd") or raw_input.get("script") or "")
    command_family = str(payload.get("command_family") or "") or behavior_events.classify_command_family(
        tool_name,
        command,
    )
    command_class = str(payload.get("command_class") or "") or behavior_events.classify_tool_command(
        tool_name,
        command,
    )
    target_class = str(payload.get("target_class") or "") or behavior_events.classify_target_class(
        command_family,
        command,
    )
    exit_code = _post_tool_exit_code(payload)
    output_text = str(payload.get("tool_response") or payload.get("output") or payload.get("stderr") or payload.get("error") or "")
    failure_family = str(payload.get("failure_family") or "") or behavior_events.classify_failure_family(
        output_text,
        exit_code if exit_code is not None else 1,
    )
    path_bits = behavior_events.path_breadcrumbs(raw_input, command)
    path_fingerprint = str(payload.get("path_category_fingerprint") or "")
    if not path_fingerprint:
        path_fingerprint = stable_json_tuple_id(
            "host_pathcat",
            path_bits.get("path_categories"),
            path_bits.get("path_extensions"),
            path_bits.get("path_fingerprints"),
            ensure_ascii=False,
        )
    target_fingerprint = str(payload.get("target_fingerprint") or "")
    if not target_fingerprint:
        target_fingerprint = stable_json_tuple_id(
            "host_target",
            command_family,
            target_class,
            path_fingerprint,
            payload.get("issue_ids") or [],
            ensure_ascii=False,
        )
    event_id = compact_text(
        str(payload.get("event_id") or payload.get("tool_call_id") or payload.get("call_id") or ""),
        160,
    ) or stable_json_tuple_id(
        "host_post_tool",
        tool_name,
        command_family,
        failure_family,
        refs,
        ensure_ascii=False,
    )
    row: dict[str, Any] = {
        "kind": "behavior_event",
        "event_id": event_id,
        "timestamp": created_at or payload.get("timestamp") or payload.get("created_at"),
        "event_kind": "tool_call_observed",
        "hard_event_kind": "tool_call_failed",
        "tool_payload_kind": "host_post_tool_use",
        "tool_name": tool_name,
        "command_class": command_class,
        "tool_intent": behavior_events.classify_tool_intent(tool_name, command_class, command),
        "command_family": command_family,
        "target_class": target_class,
        "failure_family": failure_family,
        "exit_code": exit_code,
        "status": "failed",
        "target_fingerprint": target_fingerprint,
        "path_category_fingerprint": path_fingerprint,
        "workspace_or_environment_profile": _host_workspace_profile(payload),
        "scope": _host_scope(payload),
        "freshness_window": str(payload.get("freshness_window") or "recent"),
        "source_refs": [dict(ref) for ref in refs],
        "sequence_index": int(payload.get("sequence_index") or payload.get("turn_index") or 1),
        "expected_local_red": _expected_or_exploratory_failure(payload),
        "behavior_backed": True,
    }
    row.update(path_bits)
    return row


def _capture_post_tool_learning_activation(
    payload: Mapping[str, Any],
    *,
    refs: Sequence[Mapping[str, Any]],
    host_event_name: str,
    created_at: str | None,
) -> dict[str, Any]:
    event = _post_tool_behavior_event(payload, refs=refs, created_at=created_at)
    signals = learning_core.adapt_behavior_events_to_review_signals([event])
    activations = learning_core.extract_learning_activations(signals)
    for activation in activations:
        activation["source"] = "live_host_event_capture"
        activation["host_event_name"] = host_event_name
        activation["capture_mode"] = "post_tool_failure_source_ref_gated"
    return {
        "ok": True,
        "kind": "aippocampus_correction_host_event_capture",
        "schema_version": corr.SCHEMA_VERSION,
        "created": bool(activations),
        "event_kind": learning_core.ACTIVATION_KIND,
        "host_event_name": host_event_name,
        "events": activations,
        "review_signals": signals,
        "cannot_claim": [
            "formal_memory_promotion",
            "live_semantic_adjudication_quality",
            "private_real_history_quality",
            "learning_activation_is_not_source_truth",
        ],
    }


def _host_blocked_result(
    reason: str,
    *,
    host_event_name: str,
    cannot_claim: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "kind": "aippocampus_correction_host_event_capture",
        "schema_version": corr.SCHEMA_VERSION,
        "created": False,
        "reason": reason,
        "host_event_name": host_event_name,
        "events": [],
        "cannot_claim": cannot_claim
        or [
            "host_payload_without_source_refs",
            "formal_memory_promotion",
            "private_real_history_quality",
        ],
    }


def capture_host_correction_event(payload: Mapping[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    """Create sanitized correction rows from an opt-in host hook payload.

    The adapter is source-ref gated on purpose. Hook payload text can open a
    correction window, but it cannot become reconsolidation evidence unless the
    host also provides source refs or stable source-locating fields. This keeps
    live capture from quietly turning private prompt text into user/personality
    truth or durable memory.
    """

    host_event_name = _host_event_name(payload)
    if host_event_name not in corr.HOOK_STAGES:
        return _host_blocked_result("unsupported_host_event", host_event_name=host_event_name)
    refs = _host_source_refs(payload)
    if not refs:
        return _host_blocked_result("missing_source_refs", host_event_name=host_event_name)

    if host_event_name == "UserPromptSubmit":
        surface = str(
            payload.get("correction_surface")
            or payload.get("prompt")
            or payload.get("text")
            or ""
        )
        if not (payload.get("force_correction_capture") or CORRECTION_SIGNAL_RE.search(surface)):
            return _host_blocked_result("no_correction_signal", host_event_name=host_event_name)
        event = corr.build_activation_event(
            thread_id=_host_thread_id(payload),
            workspace=_host_workspace(payload),
            topic_epoch=_host_topic_epoch(payload),
            correction_surface=surface,
            source_refs=refs,
            corrected_claim_source_refs=corr.sanitize_source_refs(
                payload.get("corrected_claim_source_refs") or [],
                policies=[],
            ),
            target_type=_host_target_type(payload, surface),
            provisional_importance=_host_importance(payload),
            hook_stage=host_event_name,
            created_at=created_at,
            event_id=str(payload.get("event_id") or ""),
        )
        event["source"] = "live_host_event_capture"
        event["host_event_name"] = host_event_name
        event["capture_mode"] = "opt_in_source_ref_gated"
        return {
            "ok": True,
            "kind": "aippocampus_correction_host_event_capture",
            "schema_version": corr.SCHEMA_VERSION,
            "created": True,
            "event_kind": corr.ACTIVATION_KIND,
            "host_event_name": host_event_name,
            "events": [event],
            "cannot_claim": [
                "formal_memory_promotion",
                "live_semantic_adjudication_quality",
                "private_real_history_quality",
            ],
        }

    if host_event_name in {"Stop", "PostToolUse", "SubagentStop", "PreCompact"}:
        activation_id = compact_text(str(payload.get("activation_event_id") or ""), 120)
        if not activation_id:
            if host_event_name == "PostToolUse" and _post_tool_failed(payload):
                return _capture_post_tool_learning_activation(
                    payload,
                    refs=refs,
                    host_event_name=host_event_name,
                    created_at=created_at,
                )
            return _host_blocked_result(
                "missing_activation_event_id",
                host_event_name=host_event_name,
                cannot_claim=["unlinked_outcome_event", "formal_memory_promotion"],
            )
        summary = str(
            payload.get("outcome_summary")
            or payload.get("final_response")
            or payload.get("tool_response")
            or payload.get("text")
            or ""
        )
        event = corr.build_outcome_event(
            activation_event_id=activation_id,
            thread_id=_host_thread_id(payload),
            workspace=_host_workspace(payload),
            topic_epoch=_host_topic_epoch(payload),
            outcome_summary=summary,
            source_refs=refs,
            adoption_signal=_host_adoption_signal(payload, summary),
            final_claim_source_refs=corr.sanitize_source_refs(
                payload.get("final_claim_source_refs") or [],
                policies=[],
            ),
            changed_files=_optional_list(payload.get("changed_files") or payload.get("changed_paths")),
            verification_evidence=_optional_list(payload.get("verification_evidence")),
            tool_evidence=_optional_list(payload.get("tool_evidence")),
            texture_evidence=_optional_list(payload.get("texture_evidence")),
            follow_up_source_refs=corr.sanitize_source_refs(
                payload.get("follow_up_source_refs") or [],
                policies=[],
            ),
            adjudication_hint=(
                str(payload.get("adjudication_hint"))
                if str(payload.get("adjudication_hint") or "") in corr.ADJUDICATION_STATUSES
                else None
            ),
            superseded_by_activation_event_id=payload.get("superseded_by_activation_event_id"),
            created_at=created_at,
            event_id=str(payload.get("event_id") or ""),
        )
        event["source"] = "live_host_event_capture"
        event["host_event_name"] = host_event_name
        event["capture_mode"] = "opt_in_source_ref_gated"
        return {
            "ok": True,
            "kind": "aippocampus_correction_host_event_capture",
            "schema_version": corr.SCHEMA_VERSION,
            "created": True,
            "event_kind": corr.OUTCOME_KIND,
            "host_event_name": host_event_name,
            "events": [event],
            "cannot_claim": [
                "formal_memory_promotion",
                "live_semantic_adjudication_quality",
                "private_real_history_quality",
            ],
        }

    return _host_blocked_result("host_event_not_correction_capture_stage", host_event_name=host_event_name)


def aggregate_private_history_adjudication(
    events: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates = list(candidates) if candidates is not None else corr.adjudicate_events(events)
    buckets: dict[str, dict[str, Any]] = {
        status: {
            "count": 0,
            "active_anchor_eligible_count": 0,
            "source_ref_count": 0,
            "routes": {},
        }
        for status in corr.ADJUDICATION_STATUSES
    }
    for candidate in candidates:
        status = str(candidate.get("adjudication_status") or "uncertain")
        if status not in buckets:
            status = "uncertain"
        bucket = buckets[status]
        bucket["count"] += 1
        bucket["source_ref_count"] += len(candidate.get("source_refs") or [])
        if status in corr.ACTIVE_ANCHOR_STATUSES and str(candidate.get("route") or "") == "active_task_anchor":
            bucket["active_anchor_eligible_count"] += 1
        route = str(candidate.get("route") or "unknown")
        routes = bucket["routes"]
        routes[route] = int(routes.get(route) or 0) + 1
    return {
        "ok": True,
        "kind": "aippocampus_correction_real_history_adjudication_report",
        "schema_version": corr.SCHEMA_VERSION,
        "created_at": now_utc(),
        "metrics": {
            "event_count": len(events),
            "activation_event_count": sum(1 for event in events if event.get("kind") == corr.ACTIVATION_KIND),
            "outcome_event_count": sum(1 for event in events if event.get("kind") == corr.OUTCOME_KIND),
            "candidate_count": len(candidates),
            "active_anchor_eligible_count": sum(
                bucket["active_anchor_eligible_count"] for bucket in buckets.values()
            ),
        },
        "buckets": buckets,
        "privacy_boundary": {
            "aggregate_only": True,
            "raw_correction_text_emitted": False,
            "raw_outcome_text_emitted": False,
            "source_refs_emitted": False,
            "local_paths_emitted": False,
            "formal_memory_promoted": False,
        },
        "cannot_claim": [
            "broad_private_real_history_quality",
            "live_semantic_adjudication_quality",
            "formal_memory_promotion",
            "user_visible_recall_lift",
        ],
    }
