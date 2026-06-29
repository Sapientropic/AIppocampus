"""Compact public projection for agent recall results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    command_value_needs_input,
    foreground_template_action,
    normalize_foreground_action,
    shell_quote,
)
from aippocampus_runtime.mcp import agent_recall_apw_meta_echo as apw_meta_echo_projection
from aippocampus_runtime.mcp import (
    agent_recall_background_recovery as background_recovery_projection,
)
from aippocampus_runtime.mcp import agent_recall_compact_choices as recall_choices
from aippocampus_runtime.mcp import agent_recall_discussion_projection as discussion_projection
from aippocampus_runtime.mcp import agent_recall_recovery_projection as recovery_projection
from aippocampus_runtime.mcp import agent_recall_repo_projection as repo_projection
from aippocampus_runtime.mcp import agent_recall_result_assembly as result_assembly
from aippocampus_runtime.mcp import agent_recall_route_projection as route_projection
from aippocampus_runtime.mcp import agent_recall_semantic_recovery as semantic_recovery_projection
from aippocampus_runtime.mcp import current_source_route_policy
from aippocampus_runtime.mcp.contracts import MCPCompactResponseContract
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.query_profile import classify_query_profile


@dataclass(frozen=True)
class RecallProjectionContext:
    recovery_cue: str
    exact_wording_source_search_requested: bool
    search_fields: dict[str, Any]
    memory_packets: list[dict[str, Any]]
    metrics: dict[str, Any]
    labels_low_specificity: bool
    repeated_route_label: str
    cache_available: bool
    recall_selector: str
    status: str
    current_source_anchor_matched: bool
    current_source_anchor_query: str


@dataclass(frozen=True)
class ForegroundSelection:
    foreground_action: dict[str, Any]
    miss_recovery_card: dict[str, Any] | None
    weak_route_recovery_card: dict[str, Any] | None
    safe_next_actions: list[dict[str, Any]]


@dataclass(frozen=True)
class FallbackPromotionState:
    foreground_action: dict[str, Any]
    safe_next_actions: list[dict[str, Any]]
    repo_familiarity_fallback: dict[str, Any] | None
    background_recovery: dict[str, Any] | None


def _canonical_agent_action(card: Any) -> dict[str, Any]:
    card_map = card if isinstance(card, dict) else {}
    action = card_map.get("canonical_action") if isinstance(card_map.get("canonical_action"), dict) else {}
    if action:
        result = core.strip_empty(normalize_foreground_action(action))
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
    action = route_projection.route_deepen_action(
        request_index,
        recall_selector=recall_selector,
    )
    action["id"] = "reopen_already_opened_route_context"
    action["why"] = (
        "The route was opened earlier, but the current compact payload has no "
        "source-window receipt; reopen read-only before making source-backed claims."
    )
    action["claim_boundary"] = "no_claim_before_reopen"
    return action


def _source_open_primary_action(action: Mapping[str, Any]) -> bool:
    action_id = str(action.get("id") or action.get("action_id") or "")
    if action_id in {
        "use_opened_route_context",
        "reopen_already_opened_route_context",
        "open_registry_search_source_window",
        "reopen_search_match_source",
        "use_opened_source_window",
    }:
        return True
    return str(action.get("claim_boundary") or "") in {
        "source_open_within_opened_context",
        "source_window_opened_for_claim",
    }


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
    payload.pop("command_template", None)
    payload.pop("template_only", None)
    payload.pop("requires", None)
    payload.pop("cli_command", None)
    payload.pop("last_recall_fallback_command", None)
    payload.pop("last_recall_fallback_boundary", None)
    return payload


def _projection_context(payload: Mapping[str, Any]) -> RecallProjectionContext:
    recovery_cue = str(
        redact_sensitive_values(
            redact_private_paths(str(payload.get("query") or payload.get("intent") or payload.get("cue") or "").strip())
        )
        or ""
    ).strip()
    if command_value_needs_input(recovery_cue):
        recovery_cue = ""
    query_profile = classify_query_profile(recovery_cue) if recovery_cue else {}
    exact_wording_source_search_requested = recall_choices.exact_wording_source_search_first_intent(
        recovery_cue,
        query_profile,
    )
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
        metrics,
        len(memory_packets),
    )
    repeated_route_label = str(
        recall_choices.repeated_low_distinctiveness_label(
            metrics,
            memory_packets,
        )
        or ""
    )
    labels_low_specificity = (
        labels_low_specificity
        or bool(repeated_route_label)
        or recall_choices.distinctive_cue_anchor_gap(
            recovery_cue,
            memory_packets,
        )
    )
    if current_source_route_policy.primary_current_source_reopenable(memory_packets):
        labels_low_specificity = False
    cache_available = bool(payload.get("last_recall_cache_available"))
    recall_selector = str(payload.get("recall_selector_id") or "").strip() if cache_available else ""
    current_source_anchor_probe = payload.get("current_source_anchor_probe")
    if not isinstance(current_source_anchor_probe, Mapping):
        current_source_anchor_probe = {}
    return RecallProjectionContext(
        recovery_cue=recovery_cue,
        exact_wording_source_search_requested=exact_wording_source_search_requested,
        search_fields=search_fields,
        memory_packets=memory_packets,
        metrics=metrics,
        labels_low_specificity=labels_low_specificity,
        repeated_route_label=repeated_route_label,
        cache_available=cache_available,
        recall_selector=recall_selector,
        status=str(payload.get("status") or ""),
        current_source_anchor_matched=int(current_source_anchor_probe.get("match_count") or 0) > 0,
        current_source_anchor_query=str(current_source_anchor_probe.get("anchor_query") or "").strip(),
    )

def _select_initial_foreground_action(
    payload: Mapping[str, Any],
    context: RecallProjectionContext,
) -> ForegroundSelection:
    miss_recovery_card = (
        None
        if context.memory_packets
        else _recall_miss_recovery_card(context.status)
    )
    weak_route_recovery_card = None
    safe_next_actions: list[dict[str, Any]] = []
    foreground_action = _canonical_agent_action(payload.get("foreground_action_card"))
    if miss_recovery_card is not None:
        registry_fallback = recall_choices.registry_source_search_fallback_action(
            context.recovery_cue
        )
        foreground_action = registry_fallback or {
            "action_id": "recover_recall_miss",
            "label": "Recover recall miss",
            "tool_name": "search_memory",
            "why": "No route surfaced; try exact source-backed search or check onboarding/index freshness.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_route_claim",
        } | context.search_fields
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
        registry_fallback = recall_choices.registry_source_search_fallback_action(
            context.recovery_cue
        )
        foreground_action = registry_fallback or {
            "action_id": "recover_weak_route",
            "label": "Recover weak route",
            "tool_name": "search_memory",
            "why": "A route surfaced without a safe deepen action; refine or exact-search before relying on it.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        } | context.search_fields
    elif context.labels_low_specificity and foreground_action.get("tool_name") == "agent_deepen":
        foreground_action = _with_recall_selector(
            foreground_action,
            context.recall_selector,
        )
        foreground_action = recall_choices.with_low_specificity_foreground_action(
            foreground_action,
            metrics=context.metrics,
            cue=context.recovery_cue,
            repeated_route_label=context.repeated_route_label,
        )
        raw_safe_actions = foreground_action.pop("_safe_next_actions", [])
        if isinstance(raw_safe_actions, list):
            safe_next_actions = [
                action for action in raw_safe_actions if isinstance(action, dict)
            ]
    else:
        foreground_action = _with_recall_selector(
            foreground_action,
            context.recall_selector,
        )
    return ForegroundSelection(
        foreground_action=foreground_action,
        miss_recovery_card=miss_recovery_card,
        weak_route_recovery_card=weak_route_recovery_card,
        safe_next_actions=safe_next_actions,
    )


def _apply_source_open_and_exact_search_actions(
    payload: Mapping[str, Any],
    context: RecallProjectionContext,
    *,
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    exact_wording_source_search_primary = False
    if (
        (foreground_action.get("id") or foreground_action.get("action_id"))
        == "use_opened_route_context"
        and not _has_current_source_window_receipt(payload, context.memory_packets)
        and context.memory_packets
    ):
        foreground_action = _opened_route_reopen_action(
            1,
            recall_selector=context.recall_selector,
        )
    if (
        context.exact_wording_source_search_requested
        and not _source_open_primary_action(foreground_action)
    ):
        exact_search_action = recall_choices.exact_wording_source_search_action(
            context.recovery_cue
        )
        if exact_search_action:
            ordinary_recovery_action = core.strip_empty(
                normalize_foreground_action(foreground_action),
                drop_empty_dicts=True,
            )
            ordinary_action_id = str(
                ordinary_recovery_action.get("id")
                or ordinary_recovery_action.get("action_id")
                or ""
            )
            if (
                ordinary_recovery_action
                and ordinary_action_id != "search_registry_sources_for_original_cue_anchors"
            ):
                safe_next_actions = [ordinary_recovery_action, *safe_next_actions]
            foreground_action = exact_search_action
            exact_wording_source_search_primary = True
    elif (
        context.current_source_anchor_matched
        and not _source_open_primary_action(foreground_action)
    ):
        current_source_action = recall_choices.current_source_anchor_search_action(
            context.recovery_cue,
            anchor_query=context.current_source_anchor_query,
        )
        if current_source_action:
            ordinary_recovery_action = core.strip_empty(
                normalize_foreground_action(foreground_action),
                drop_empty_dicts=True,
            )
            if ordinary_recovery_action:
                safe_next_actions = [ordinary_recovery_action, *safe_next_actions]
            foreground_action = current_source_action
    return foreground_action, safe_next_actions, exact_wording_source_search_primary


def _apply_fallback_promotions(
    payload: Mapping[str, Any],
    context: RecallProjectionContext,
    *,
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
) -> FallbackPromotionState:
    if not recall_choices.is_exact_wording_source_search_action(foreground_action):
        (
            foreground_action,
            safe_next_actions,
            _discussion_atlas_pointer,
        ) = discussion_projection.maybe_promote_discussion_atlas_action(
            payload=payload,
            foreground_action=foreground_action,
            followup_actions=safe_next_actions,
            status=context.status,
            labels_low_specificity=context.labels_low_specificity,
            recovery_cue=context.recovery_cue,
        )
    repo_familiarity_fallback = recovery_projection.compact_repo_familiarity_fallback_card(
        payload.get("repo_familiarity_fallback")
    )
    repo_familiarity_action = recovery_projection.repo_familiarity_fallback_action(
        repo_familiarity_fallback
    )
    (
        foreground_action,
        safe_next_actions,
        repo_familiarity_fallback,
    ) = repo_projection.maybe_promote_repo_familiarity_action(
        payload=payload,
        foreground_action=foreground_action,
        safe_next_actions=safe_next_actions,
        repo_familiarity_fallback=repo_familiarity_fallback,
        repo_familiarity_action=repo_familiarity_action,
    )
    (
        foreground_action,
        safe_next_actions,
        background_recovery,
    ) = background_recovery_projection.apply_background_recovery(
        payload=payload,
        foreground_action=foreground_action,
        followup_actions=safe_next_actions,
    )
    return FallbackPromotionState(
        foreground_action=foreground_action,
        safe_next_actions=safe_next_actions,
        repo_familiarity_fallback=repo_familiarity_fallback,
        background_recovery=background_recovery,
    )


def compact_agent_recall_payload(payload: dict[str, Any]) -> MCPCompactResponseContract:
    """Project agent_recall into one foreground action plus compact route receipts.

    aippocampus-stage-map: sanitize cue -> choose primary action -> keep APW
    and weak-route proof internal/detail-only -> render compact receipts ->
    strip debug fields. Do not carry source-open proof material in default MCP.
    """

    context = _projection_context(payload)
    route_projection_result = route_projection.project_route_receipts(
        context.memory_packets,
        labels_low_specificity=context.labels_low_specificity,
        cache_available=context.cache_available,
        recall_selector=context.recall_selector,
        deepen_requests=payload.get("deepen_requests"),
    )
    selection = _select_initial_foreground_action(payload, context)
    foreground_action, safe_next_actions, exact_wording_source_search_primary = (
        _apply_source_open_and_exact_search_actions(
            payload,
            context,
            foreground_action=selection.foreground_action,
            safe_next_actions=selection.safe_next_actions,
        )
    )
    foreground_action, safe_next_actions = semantic_recovery_projection.maybe_promote_semantic_recovery(
        memory_packets=context.memory_packets,
        foreground_action=foreground_action,
        followup_actions=safe_next_actions,
        recall_selector=context.recall_selector,
        anchor_gate=payload.get("source_anchor_gate"),
    )
    apw_state = recovery_projection.apply_associative_path_recovery(
        payload,
        recovery_cue=context.recovery_cue,
        recall_selector=context.recall_selector,
        cache_available=context.cache_available,
        labels_low_specificity=context.labels_low_specificity,
        foreground_action=foreground_action,
        safe_next_actions=safe_next_actions,
        weak_route_recovery_card=selection.weak_route_recovery_card,
        deepen_action_builder=route_projection.route_deepen_action,
        source_open_primary_action=_source_open_primary_action,
    )
    fallback_state = _apply_fallback_promotions(
        payload,
        context,
        foreground_action=apw_state.foreground_action,
        safe_next_actions=apw_state.safe_next_actions,
    )
    foreground_action, safe_next_actions = (
        apw_meta_echo_projection.promote_original_anchor_search_from_safe_actions(
            source_anchor_gate=payload.get("source_anchor_gate"),
            foreground_action=fallback_state.foreground_action,
            safe_next_actions=fallback_state.safe_next_actions,
        )
    )
    return result_assembly.assemble_compact_recall_payload(
        payload,
        context,
        route_projection_result=route_projection_result,
        foreground_action=foreground_action,
        safe_next_actions=safe_next_actions,
        miss_recovery_card=selection.miss_recovery_card,
        weak_route_recovery_card=apw_state.weak_route_recovery_card,
        apw_recovery=apw_state.apw_recovery,
        repo_familiarity_fallback=fallback_state.repo_familiarity_fallback,
        background_recovery=fallback_state.background_recovery,
        exact_wording_source_search_primary=exact_wording_source_search_primary,
    )
