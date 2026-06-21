"""Compact public projection for agent recall results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    command_value_needs_input,
    foreground_template_action,
    normalize_foreground_action,
    shell_quote,
)
from aippocampus_runtime.mcp import agent_recall_compact_choices as recall_choices
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


def _without_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _without_empty(item)) not in (None, "", [])
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _without_empty(item)) not in (None, "", [])]
    return value


def _compact_claim_boundary(
    *,
    can_use_for: list[str],
    must_reopen_for: list[str],
    detail_command: str | None = None,
    detail_command_template: str | None = None,
) -> dict[str, Any]:
    boundary: dict[str, Any] = {
        "can_use_for": can_use_for,
        "must_reopen_for": must_reopen_for,
    }
    if detail_command:
        boundary["detail_available_with"] = detail_command
    elif detail_command_template:
        boundary["detail_available_with_template"] = detail_command_template
        boundary["detail_requires"] = ["cue"]
    return boundary


_RECALL_DETAIL_COMMAND_TEMPLATE = 'aippocampus agent recall "{cue}" --json --detail full'


def _recall_detail_command_fields(cue: str) -> dict[str, Any]:
    if cue and not command_value_needs_input(cue):
        return {
            "operator_detail_command": (
                f"aippocampus agent recall {shell_quote(cue)} --json --detail full"
            )
        }
    return {
        "operator_detail_command_template": _RECALL_DETAIL_COMMAND_TEMPLATE,
        "operator_detail_requires": ["cue"],
        "operator_detail_template_only": True,
    }


def _canonical_agent_action(card: Any) -> dict[str, Any]:
    card_map = card if isinstance(card, dict) else {}
    action = card_map.get("canonical_action") if isinstance(card_map.get("canonical_action"), dict) else {}
    if action:
        result = _without_empty(normalize_foreground_action(action))
        result.setdefault("label", "Open selected recall route")
        result.setdefault("mutation_risk", "read_only")
        result.setdefault(
            "why",
            "Recall surfaced route-shaped context; deepen before using it for source-backed claims.",
        )
        return result
    return {
        "action_id": "continue_normally",
        "arguments": {},
        "claim_boundary": "no_route_claim",
    }


def _has_current_source_window_receipt(
    payload: Mapping[str, Any],
    packets: list[dict[str, Any]],
) -> bool:
    receipt_keys = {
        "source_window_receipt",
        "opened_source_window_receipt",
        "source_window_summary",
        "source_window_scope",
        "primary_source_snippet",
        "source_snippet_summary",
    }
    for key in receipt_keys:
        if payload.get(key):
            return True
    for packet in packets[:3]:
        for key in receipt_keys:
            if packet.get(key):
                return True
    return False


def _opened_route_reopen_action(
    request_index: int,
    *,
    recall_selector: str = "",
) -> dict[str, Any]:
    action = route_deepen_action(request_index, recall_selector=recall_selector)
    action["id"] = "reopen_already_opened_route_context"
    action["why"] = (
        "The route was opened earlier, but the current compact payload has no "
        "source-window receipt; reopen read-only before making source-backed claims."
    )
    action["claim_boundary"] = "no_claim_before_reopen"
    return action


def _recall_miss_recovery_card(status: Any) -> dict[str, Any]:
    miss_class = "no_route" if str(status or "") == "no_routes" else "weak_or_unavailable_route"
    return {
        "miss_class": miss_class,
        "summary": (
            "No compact source-backed route surfaced."
            if miss_class == "no_route"
            else "Recall did not produce a route that is safe to use directly."
        ),
        "primary_action": "refine_cue_or_run_exact_search",
        "recovery_actions": [
            "refine the cue with a project, object, person, or time clue",
            "run exact search after providing exact_phrase",
            "aippocampus onboard --provider auto --status --json",
        ],
        "safe_next_actions": [
            foreground_template_action(
                action_id="search_exact_phrase",
                label="Search exact clean-source wording",
                command_template='aippocampus search "{exact_phrase}" --json',
                requires=["exact_phrase"],
                why="Search only after the caller supplies real remembered wording.",
                mutation_risk="read_only",
                claim_boundary="search_result_requires_source_boundary",
            ),
            {
                "id": "check_onboarding_status",
                "label": "Check source registration",
                "command": "aippocampus onboard --provider auto --status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "setup_status_not_memory_evidence",
            },
        ],
        "do_not": [
            "do not claim from scent or route silence",
            "do not broaden into manual search before checking source/index readiness when continuity was expected",
        ],
        "claim_boundary": "no_route_claim",
    }


def _weak_route_recovery_card() -> dict[str, Any]:
    return {
        "miss_class": "weak_route",
        "summary": "Recall returned route-shaped context, but no safe deepen request was available.",
        "primary_action": "refine_cue_or_run_exact_search",
        "recovery_actions": [
            "refine cue before relying on the route",
            "run exact search for distinctive source wording",
            "request full diagnostics only if this route should have been reopenable",
        ],
        "do_not": [
            "do not treat direction-only context as evidence",
            "do not quote or decide from a route without reopened source",
        ],
        "claim_boundary": "no_claim_before_reopen",
    }


def _with_recall_selector(action: Mapping[str, Any], recall_selector: str) -> dict[str, Any]:
    clean_selector = str(recall_selector or "").strip()
    payload = dict(action)
    if not clean_selector or payload.get("tool_name") != "agent_deepen":
        return payload
    raw_arguments = payload.get("arguments")
    arguments = dict(raw_arguments) if isinstance(raw_arguments, Mapping) else {}
    try:
        request_index = int(arguments.get("request_index") or 1)
    except (TypeError, ValueError):
        request_index = 1
    arguments.pop("last_recall", None)
    arguments["request_index"] = request_index
    arguments["recall_selector"] = clean_selector
    payload["arguments"] = arguments
    payload["command"] = (
        f"aippocampus agent deepen --request {request_index} "
        f"--recall-selector {shell_quote(clean_selector)} --json"
    )
    payload.pop("cli_command", None)
    return payload


def _public_route_label(packet: Mapping[str, Any]) -> str:
    raw = str(
        packet.get("route_topic")
        or packet.get("route_label")
        or packet.get("display_hint")
        or "memory route"
    )
    label = raw.removeprefix("thread_candidate:")
    label = label.replace("_", " ").replace("·", " ")
    label = " ".join(label.split())
    return core.compact_text(label[:1].upper() + label[1:] if label else "Memory route", 90)


def _route_label_key(label: str) -> str:
    return " ".join(str(label or "").casefold().split())


def _route_choice_explanation(
    packet: Mapping[str, Any],
    *,
    index: int,
    route_count: int,
    labels_low_specificity: bool,
) -> str:
    if labels_low_specificity:
        return "Potential route, but compact labels are not specific enough; refine or search source before choosing."
    if route_count <= 1:
        return "Best available route; reopen it before using source-backed details."
    output_mode = str(packet.get("output_mode") or packet.get("route_kind") or "")
    if output_mode == "reopenable_route":
        return f"Route {index} of {route_count}; it can be reopened for source-backed details."
    if output_mode == "direction_only":
        return f"Route {index} of {route_count}; use as navigation only until source is reopened."
    return f"Route {index} of {route_count}; inspect it before treating it as evidence."


def route_deepen_action(
    request_index: int,
    *,
    recall_selector: str = "",
    low_confidence: bool = False,
) -> dict[str, Any]:
    clean_selector = str(recall_selector or "").strip()
    arguments: dict[str, Any] = {"request_index": request_index}
    if clean_selector:
        arguments["recall_selector"] = clean_selector
        command = (
            f"aippocampus agent deepen --request {request_index} "
            f"--recall-selector {shell_quote(clean_selector)} --json"
        )
    else:
        arguments["last_recall"] = True
        command = f"aippocampus agent deepen --request {request_index} --last-recall --json"
    action = {
        "id": "deepen_this_route",
        "tool_name": "agent_deepen",
        "arguments": arguments,
        "command": command,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
    }
    if low_confidence:
        action["route_choice_posture"] = "labels_low_specificity"
        action["confidence"] = "low_confidence_navigation"
    return action


def _compact_associative_path_fallback_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _without_empty(
        {
            "kind": value.get("kind"),
            "schema_version": value.get("schema_version"),
            "status": value.get("status"),
            "decision": value.get("decision"),
            "ordinary_recall_status": value.get("ordinary_recall_status"),
            "request_index": value.get("request_index"),
            "label": value.get("label"),
            "why_this_route": value.get("why_this_route"),
            "route_posture": value.get("route_posture"),
            "action_grammar": value.get("action_grammar"),
            "reason_codes": value.get("reason_codes"),
            "risk_flags": value.get("risk_flags"),
            "summary": value.get("summary"),
            "opt_in_required": True,
            "applied_to_default_ranking": False,
            "source_shape_guarded": value.get("source_shape_guarded"),
            "source_reopen_required_before_claim": True,
        }
    )


def _associative_path_fallback_action(
    card: Mapping[str, Any] | None,
    *,
    recall_selector: str,
    cache_available: bool,
) -> dict[str, Any] | None:
    if not isinstance(card, Mapping) or card.get("status") != "route_candidate":
        return None
    try:
        request_index = int(card.get("request_index") or 0)
    except (TypeError, ValueError):
        request_index = 0
    if request_index <= 0 or not cache_available:
        return None
    action = route_deepen_action(request_index, recall_selector=recall_selector)
    action["id"] = "deepen_associative_path_fallback"
    action["label"] = "Open APW fallback source"
    action["why"] = str(
        card.get("why_this_route")
        or "APW found a source-ref-backed fallback; reopen it before using it."
    )
    action["claim_boundary"] = "no_claim_before_reopen"
    action["route_choice_posture"] = "associative_path_opt_in_fallback"
    return action


def compact_agent_recall_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project agent_recall into one foreground action plus compact route receipts."""

    recovery_cue = str(
        redact_sensitive_values(
            redact_private_paths(str(payload.get("query") or payload.get("intent") or payload.get("cue") or "").strip())
        )
        or ""
    ).strip()
    if command_value_needs_input(recovery_cue):
        recovery_cue = ""
    search_fields = (
        {
            "arguments": {"query": recovery_cue, "max": 5},
            "cli_command": f"aippocampus search {shell_quote(recovery_cue)} --json",
        }
        if recovery_cue
        else {
            "arguments_template": {"query": "{exact_phrase}", "max": 5},
            "requires": ["exact_phrase"],
            "template_only": True,
            "cli_command_template": 'aippocampus search "{exact_phrase}" --json',
        }
    )
    memory_packets = [
        packet for packet in payload.get("memory_packets") or [] if isinstance(packet, dict)
    ]
    raw_metrics = payload.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    labels_low_specificity = recall_choices.low_specificity_route_choices(
        metrics, len(memory_packets)
    )
    repeated_route_label = recall_choices.repeated_low_distinctiveness_label(
        metrics,
        memory_packets,
    )
    labels_low_specificity = labels_low_specificity or bool(repeated_route_label) or recall_choices.distinctive_cue_anchor_gap(
        recovery_cue,
        memory_packets,
    )
    cache_available = bool(payload.get("last_recall_cache_available"))
    recall_selector = str(payload.get("recall_selector_id") or "").strip() if cache_available else ""
    displayed_packets: list[tuple[int, dict[str, Any]]] = []
    duplicate_label_omissions: dict[str, dict[str, Any]] = {}
    if labels_low_specificity:
        seen_labels: dict[str, dict[str, Any]] = {}
        for index, packet in enumerate(memory_packets, start=1):
            label = _public_route_label(packet)
            label_key = _route_label_key(label)
            if label_key and label_key in seen_labels:
                summary = duplicate_label_omissions.setdefault(
                    label_key,
                    {
                        "route_label": label,
                        "kept_route_index": seen_labels[label_key]["route_index"],
                        "omitted_count": 0,
                    },
                )
                summary["omitted_count"] = int(summary["omitted_count"]) + 1
                continue
            if label_key:
                seen_labels[label_key] = {"route_index": index, "route_label": label}
            if len(displayed_packets) < 3:
                displayed_packets.append((index, packet))
    else:
        displayed_packets = list(enumerate(memory_packets[:3], start=1))
    route_receipts: list[dict[str, Any]] = []
    for index, packet in displayed_packets:
        already_opened = bool(packet.get("already_opened"))
        route_is_callable = (
            cache_available
            and str(packet.get("output_mode") or "") == "reopenable_route"
        )
        callable_selector = (
            {
                "kind": "recall_selector_request_index" if recall_selector else "last_recall_request_index",
                "request_index": index,
                **(
                    {"recall_selector": recall_selector}
                    if recall_selector
                    else {"last_recall": True}
                ),
            }
            if route_is_callable
            else {
                "kind": "not_callable_from_compact_card",
                "reason": (
                    "route_already_opened_in_this_session"
                    if already_opened
                    else "route_not_reopenable_or_last_recall_cache_missing"
                ),
            }
        )
        route_receipts.append(
            _without_empty(
                {
                    "index": index,
                    "label": _public_route_label(packet),
                    "why_this_route": _route_choice_explanation(
                        packet,
                        index=index,
                        route_count=len(memory_packets),
                        labels_low_specificity=labels_low_specificity,
                    ),
                    "callable_selector": callable_selector,
                    "private_handle_boundary": (
                        "compact_output_redacts_local_private_handle_use_callable_selector"
                    ),
                    "already_opened": already_opened or None,
                    "claim_permission": packet.get("claim_permission"),
                    "next_action_boundary": "reopen_required_before_claim",
                    "action": route_deepen_action(
                        index,
                        recall_selector=recall_selector,
                        low_confidence=labels_low_specificity,
                    )
                    if route_is_callable
                    else None,
                }
            )
        )
    suppressed_low_confidence_route_count = 0
    if labels_low_specificity and route_receipts:
        suppressed_low_confidence_route_count = len(memory_packets)
        route_receipts = []
    semantic = payload.get("semantic_gate_diagnostics")
    semantic_compact = None
    if isinstance(semantic, dict):
        semantic_compact = _without_empty(
            {
                "requested": semantic.get("requested"),
                "mode": semantic.get("mode"),
                "overall_recall_diagnostic": semantic.get("overall_recall_diagnostic"),
                "semantic_sidecar": semantic.get("semantic_sidecar"),
                "foreground_action": semantic.get("foreground_action"),
                "boundary": semantic.get("boundary"),
            }
        )
    status = payload.get("status")
    miss_recovery_card = None if memory_packets else _recall_miss_recovery_card(status)
    weak_route_recovery_card = None
    safe_next_actions: list[dict[str, Any]] = []
    foreground_action = _canonical_agent_action(payload.get("foreground_action_card"))
    if miss_recovery_card is not None:
        registry_fallback = recall_choices.registry_source_search_fallback_action(recovery_cue)
        foreground_action = registry_fallback or {
            "action_id": "recover_recall_miss",
            "label": "Recover recall miss",
            "tool_name": "search_memory",
            "why": "No route surfaced; try exact source-backed search or check onboarding/index freshness.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_route_claim",
        } | search_fields
        if registry_fallback:
            foreground_action["secondary_action"] = {
                "id": "refine_recall_cue_after_registry_search",
                "label": "Refine the recall cue",
                "tool_name": "agent_recall",
                "command_template": 'aippocampus agent recall "{tighter_cue}" --json',
                "requires": ["tighter_cue"],
                "template_only": True,
                "mutation_risk": "read_only",
                "claim_boundary": "no_claim_before_reopen",
                "why": "Use if registry-wide source search still cannot find a useful anchor.",
            }
    elif foreground_action.get("action_id") == "continue_normally" or foreground_action.get("id") == "continue_normally":
        weak_route_recovery_card = _weak_route_recovery_card()
        registry_fallback = recall_choices.registry_source_search_fallback_action(recovery_cue)
        foreground_action = registry_fallback or {
            "action_id": "recover_weak_route",
            "label": "Recover weak route",
            "tool_name": "search_memory",
            "why": "A route surfaced without a safe deepen action; refine or exact-search before relying on it.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        } | search_fields
    elif labels_low_specificity and foreground_action.get("tool_name") == "agent_deepen":
        foreground_action = _with_recall_selector(foreground_action, recall_selector)
        foreground_action = recall_choices.with_low_specificity_foreground_action(
            foreground_action,
            metrics=metrics,
            cue=recovery_cue,
            repeated_route_label=repeated_route_label,
        )
        raw_safe_actions = foreground_action.pop("_safe_next_actions", [])
        if isinstance(raw_safe_actions, list):
            safe_next_actions = [
                action for action in raw_safe_actions if isinstance(action, dict)
            ]
    else:
        foreground_action = _with_recall_selector(foreground_action, recall_selector)
    if (
        (foreground_action.get("id") or foreground_action.get("action_id"))
        == "use_opened_route_context"
        and not _has_current_source_window_receipt(payload, memory_packets)
        and memory_packets
    ):
        foreground_action = _opened_route_reopen_action(1, recall_selector=recall_selector)
    associative_path_fallback = _compact_associative_path_fallback_card(
        payload.get("associative_path_fallback")
    )
    associative_path_action = _associative_path_fallback_action(
        associative_path_fallback,
        recall_selector=recall_selector,
        cache_available=cache_available,
    )
    if associative_path_action:
        ordinary_recovery_action = _without_empty(normalize_foreground_action(foreground_action))
        ordinary_action_id = str(
            ordinary_recovery_action.get("id") or ordinary_recovery_action.get("action_id") or ""
        )
        if ordinary_recovery_action:
            safe_next_actions = [ordinary_recovery_action, *safe_next_actions]
        foreground_action = associative_path_action
        if isinstance(associative_path_fallback, dict):
            associative_path_fallback["primary_action"] = "deepen_associative_path_fallback"
            if ordinary_action_id:
                associative_path_fallback["ordinary_recovery_action_id"] = ordinary_action_id
    detail_fields = _recall_detail_command_fields(recovery_cue)
    detail_command = str(detail_fields.get("operator_detail_command") or "")
    detail_command_template = str(detail_fields.get("operator_detail_command_template") or "")
    displayed_route_count = len(route_receipts)
    hidden_route_count_fields: dict[str, int] = {}
    omitted_route_count = max(0, len(memory_packets) - displayed_route_count)
    if omitted_route_count:
        hidden_route_count_fields = {
            "displayed_route_count": displayed_route_count,
            "omitted_route_count": omitted_route_count,
        }
    duplicate_omission_rows = sorted(
        duplicate_label_omissions.values(),
        key=lambda row: (int(row["kept_route_index"]), str(row["route_label"])),
    )
    if labels_low_specificity and memory_packets:
        safe_action_ids = [
            str(action.get("id") or action.get("action_id") or "")
            for action in safe_next_actions
        ]
        refine_action_id = next(
            (action_id for action_id in safe_action_ids if action_id.startswith("refine")),
            None,
        )
        deepen_action_id = next(
            (action_id for action_id in safe_action_ids if action_id.startswith("deepen")),
            None,
        )
        weak_route_recovery_card = _without_empty(
            {
                **(weak_route_recovery_card or {}),
                "posture": "labels_low_specificity",
                "route_count": len(memory_packets),
                "displayed_as_choices": 0,
                "primary_action": foreground_action.get("id") or foreground_action.get("action_id"),
                "source_search_fallback_action_id": foreground_action.get("id")
                or foreground_action.get("action_id"),
                "refine_action_id": refine_action_id,
                "deepen_action_id": deepen_action_id,
            }
        )
    can_use_for = ["next_action_choice"]
    if not labels_low_specificity:
        can_use_for.append("route_selection")
    result = {
        "detail": "compact",
        "kind": payload.get("kind"),
        "schema_version": payload.get("schema_version"),
        "mode": payload.get("mode"),
        "surface": "mcp_agent_recall_compact",
        "status": status,
        "opt_in_required": payload.get("opt_in_required"),
        "last_recall_cache_available": cache_available,
        "recall_selector_available": bool(recall_selector),
        "foreground_action": foreground_action,
        "miss_recovery_card": miss_recovery_card,
        "weak_route_recovery_card": weak_route_recovery_card,
        "routes": route_receipts,
        "route_count": len(memory_packets),
        **hidden_route_count_fields,
        "hidden_low_confidence_route_count": suppressed_low_confidence_route_count or None,
        "omitted_duplicate_route_label_count": sum(
            int(row["omitted_count"]) for row in duplicate_omission_rows
        )
        or None,
        "omitted_duplicate_route_labels": duplicate_omission_rows[:3] or None,
        "semantic_gate_diagnostics": semantic_compact,
        "associative_path_fallback": associative_path_fallback,
        "provider_key_bridge": payload.get("provider_key_bridge"),
        "claim_boundary": _compact_claim_boundary(
            can_use_for=can_use_for,
            must_reopen_for=["source_backed_claims", "exact_wording", "sensitive_or_stale_facts"],
            detail_command=detail_command or None,
            detail_command_template=detail_command_template or None,
        ),
        **detail_fields,
    }
    result.update(
        canonical_foreground_action_fields(
            foreground_action,
            safe_next_actions=safe_next_actions,
        )
    )
    return _without_empty(result)
