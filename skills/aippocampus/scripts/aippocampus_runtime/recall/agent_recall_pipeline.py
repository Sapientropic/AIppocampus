"""Staged implementation for the agent recall hot path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.mcp.recall_navigation import (
    RecallNavigationError,
    navigation_error_payload,
    recall_context_packet,
)
from aippocampus_runtime.navigation import attention_route_projection
from aippocampus_runtime.recall import (
    agent_deepen_requests,
    agent_semantic_diagnostics,
    architecture_navigation_affordance,
    attention_router_policy,
    foreground_action_card,
    macro_field_live,
    macro_live_recall,
    recall_recovery_layers,
)
from aippocampus_runtime.recall import associative_path_fallback as apw_fallback
from aippocampus_runtime.recall import (
    repo_familiarity_fallback as repo_familiarity_recovery,
)
from aippocampus_runtime.recall import (
    source_anchor_gate as recall_source_anchor_gate,
)
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    handle_boundary_fields,
    normalize_route_limit,
    policy_boundary,
)
from aippocampus_runtime.recall.agent_recall_primitives import (
    KIND,
    MAX_ROUTES,
    SCHEMA_VERSION,
    _annotate_route_selection_hints,
    _as_path,
    _clean_source_dir,
    _clean_source_has_messages,
    _count_forbidden_keys,
    _load_macro_projection,
    _mark_already_opened_routes,
    _memory_packet_for_route,
    _memory_packet_triage_metrics,
    _public_payload,
)
from aippocampus_runtime.recall.feedback import events as feedback_events
from aippocampus_runtime.recall.source_gate_context import (
    attach_source_gate_context_to_deepen_requests,
)
from aippocampus_runtime.source.discussion_atlas_pointer import discussion_atlas_pointer_for_query


@dataclass(frozen=True)
class RecallInputStage:
    query: str
    cwd_path: Path
    source_dir: Path
    registry_path: Path
    project: str
    requested_limit: int
    macro_projection: Mapping[str, Any]
    macro_context: Mapping[str, Any] | None
    effective_limit: int


@dataclass(frozen=True)
class RecallRouteStage:
    packet: Mapping[str, Any]
    routes: list[dict[str, Any]]
    macro_projection: Mapping[str, Any]
    macro_context: Mapping[str, Any] | None
    macro_navigation: dict[str, Any]
    macro_metrics: dict[str, Any]


@dataclass(frozen=True)
class RecallPacketStage:
    routes: list[dict[str, Any]]
    memory_packets: list[dict[str, Any]]
    deepen_requests: list[dict[str, Any]]
    attention_navigation: dict[str, Any]
    source_anchor_gate: dict[str, Any]
    triage_metrics: dict[str, Any]


@dataclass(frozen=True)
class RecallRecoveryStage:
    background_recovery_card: dict[str, Any] | None
    associative_path_policy: dict[str, Any] | None
    associative_path_fallback: dict[str, Any] | None
    already_opened_count: int


@dataclass(frozen=True)
class RecallActionStage:
    action_card: dict[str, Any]
    repo_familiarity_fallback: dict[str, Any] | None
    current_source_anchor_probe: dict[str, Any] | None
    suggested_next: str
    suggested_next_command: str | None


def run_agent_recall_pipeline(
    query: str,
    *,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    macro_state_path: str | Path | None = None,
    project: str = "AIppocampus",
    max_routes: int = MAX_ROUTES,
    attention_router: bool | str = False,
    run_semantic_gate: bool = False,
    semantic_gate_mode: str = "off",
    semantic_timeout: int = 12,
    feedback_path: str | Path | None = None,
    opened_route_keys: set[str] | None = None,
    include_associative_fallback: bool = False,
    associative_path_sidecar_dir: str | Path | None = None,
    associative_path_bridge_path: str | Path | None = None,
    associative_path_navigation_path: str | Path | None = None,
    associative_path_active_lock_path: str | Path | None = None,
    associative_path_feedback_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run recall through explicit load, evaluate, recovery, and render stages."""

    inputs = _resolve_recall_inputs(
        query,
        cwd=cwd,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        macro_state_path=macro_state_path,
        project=project,
        max_routes=max_routes,
    )
    try:
        routes = _load_and_bias_recall_routes(inputs)
    except RecallNavigationError as exc:
        return _navigation_error_result(exc, inputs)
    packets = _build_recall_packets(
        inputs,
        routes,
        attention_router=attention_router,
        feedback_path=feedback_path,
    )
    recovery = _build_recall_recovery(
        inputs,
        packets,
        opened_route_keys=opened_route_keys or set(),
        include_associative_fallback=include_associative_fallback,
        associative_path_sidecar_dir=associative_path_sidecar_dir,
        associative_path_bridge_path=associative_path_bridge_path,
        associative_path_navigation_path=associative_path_navigation_path,
        associative_path_active_lock_path=associative_path_active_lock_path,
        associative_path_feedback_path=associative_path_feedback_path,
        feedback_path=feedback_path,
    )
    actions = _select_recall_action(inputs, packets)
    return _public_payload(
        _assemble_recall_result(
            inputs,
            routes,
            packets,
            recovery,
            actions,
            run_semantic_gate=run_semantic_gate,
            semantic_gate_mode=semantic_gate_mode,
            semantic_timeout=semantic_timeout,
            include_associative_fallback=include_associative_fallback,
        )
    )


def _resolve_recall_inputs(
    query: str,
    *,
    cwd: str | Path | None,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    macro_state_path: str | Path | None,
    project: str,
    max_routes: int,
) -> RecallInputStage:
    cwd_path = core.canonical_path(cwd or Path.cwd())
    source_dir = _clean_source_dir(cwd_path, clean_source_dir)
    registry_path = (
        _as_path(registry_dir, Path()) if registry_dir else core.aippocampus_registry_dir().resolve()
    )
    requested_limit = normalize_route_limit(max_routes, default=MAX_ROUTES)
    macro_projection = _load_macro_projection(
        project=project,
        macro_state_path=macro_state_path,
        cwd=cwd_path,
    ) or {}
    macro_context = macro_live_recall.context_from_projection(macro_projection)
    effective_limit = macro_live_recall.effective_route_limit(
        requested_limit=requested_limit,
        context=macro_context,
    )
    return RecallInputStage(
        query=str(query or ""),
        cwd_path=cwd_path,
        source_dir=source_dir,
        registry_path=registry_path,
        project=project,
        requested_limit=requested_limit,
        macro_projection=macro_projection,
        macro_context=macro_context,
        effective_limit=effective_limit,
    )


def _navigation_error_result(
    exc: RecallNavigationError,
    inputs: RecallInputStage,
) -> dict[str, Any]:
    action_card = foreground_action_card.build_recall_foreground_action_card(
        status="cannot_verify",
        memory_packets=[],
        deepen_requests=[],
        query=inputs.query,
    )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "recall",
            "surface": "agent_cli_or_mcp_adapter",
            "status": "cannot_verify",
            "opt_in_required": False,
            "foreground_action_card": action_card,
            "audit_available": True,
            "memory_packets": [],
            "deepen_requests": [],
            "result": navigation_error_payload(exc),
            "macro_navigation": macro_live_recall.navigation_diagnostics(
                projection=inputs.macro_projection,
                context=inputs.macro_context,
                requested_limit=inputs.requested_limit,
                effective_limit=inputs.effective_limit,
            ),
            "policy_boundary": policy_boundary(),
            "cannot_claim": ["source_backed_claim", "route_handle_as_fact"],
        }
    )


def _load_and_bias_recall_routes(inputs: RecallInputStage) -> RecallRouteStage:
    packet = recall_context_packet(
        intent=inputs.query,
        cwd=inputs.cwd_path,
        clean_source_dir=inputs.source_dir,
        registry_dir=inputs.registry_path,
        max_routes=inputs.effective_limit,
    )
    routes = [dict(route) for route in packet.get("routes") or [] if isinstance(route, Mapping)]
    macro_projection = inputs.macro_projection
    macro_context = inputs.macro_context
    if macro_context is not None:
        foreground_outcomes = [
            outcome
            for route in routes
            for outcome in (route.get("foreground_outcomes") or route.get("runtime_outcomes") or [])
            if isinstance(outcome, Mapping)
        ]
        macro_transition_history = [
            state
            for route in routes
            for state in (route.get("macro_transition_history") or [])
            if state
        ]
        live_macro = macro_field_live.materialize_for_recall(
            query=inputs.query,
            routes=routes,
            foreground_outcomes=foreground_outcomes,
            macro_transition_history=macro_transition_history,
        )
        macro_projection = macro_field_live.merge_projection(macro_projection, live_macro)
        macro_context = macro_live_recall.context_from_projection(macro_projection)
    macro_navigation = macro_live_recall.navigation_diagnostics(
        projection=macro_projection,
        context=macro_context,
        requested_limit=inputs.requested_limit,
        effective_limit=inputs.effective_limit,
    )
    macro_metrics: dict[str, Any] = {
        "macro_selected_route_count": 0,
        "macro_wrong_layer_route_count": 0,
        "macro_recheck_trigger_count": 0,
        "macro_reason_code_count": len(macro_navigation["reason_codes"]),
    }
    if macro_context is not None:
        routes, macro_navigation, macro_metrics = macro_live_recall.apply_recall_bias(
            query=inputs.query,
            routes=routes,
            context=macro_context,
            requested_limit=inputs.requested_limit,
            effective_limit=inputs.effective_limit,
        )
    return RecallRouteStage(
        packet=packet,
        routes=routes,
        macro_projection=macro_projection,
        macro_context=macro_context,
        macro_navigation=macro_navigation,
        macro_metrics=macro_metrics,
    )


def _build_recall_packets(
    inputs: RecallInputStage,
    routes: RecallRouteStage,
    *,
    attention_router: bool | str,
    feedback_path: str | Path | None,
) -> RecallPacketStage:
    router_policy = attention_router_policy.resolve_policy(attention_router)
    feedback_calibration = feedback_events.load_feedback_calibration_report(feedback_path)
    ranked_routes, attention_navigation = (
        attention_route_projection.maybe_rerank_routes_with_attention_router(
            enabled=bool(router_policy["enabled"]),
            query=inputs.query,
            routes=routes.routes,
            max_routes=inputs.effective_limit,
            project=inputs.project,
            feedback_calibration=feedback_calibration,
        )
    )
    attention_navigation["policy"] = router_policy
    ranked_routes = _annotate_route_selection_hints(
        ranked_routes,
        macro_navigation=routes.macro_navigation,
        attention_navigation=attention_navigation,
    )
    memory_packets = [_memory_packet_for_route(route) for route in ranked_routes]
    deepen_requests = [
        agent_deepen_requests.deepen_request_for_route(route, memory_packet, request_index=index)
        for index, (route, memory_packet) in enumerate(
            zip(ranked_routes, memory_packets, strict=True),
            start=1,
        )
        if route.get("handle") and memory_packet.get("output_mode") == "reopenable_route"
    ]
    source_anchor_gate = recall_source_anchor_gate.apply_top_route_source_anchor_gate(
        query=inputs.query,
        routes=ranked_routes,
        deepen_requests=deepen_requests,
        memory_packets=memory_packets,
        clean_source_dir=inputs.source_dir,
        registry_dir=inputs.registry_path,
    )
    attach_source_gate_context_to_deepen_requests(
        source_anchor_gate=source_anchor_gate,
        routes=ranked_routes,
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
    )
    return RecallPacketStage(
        routes=ranked_routes,
        memory_packets=memory_packets,
        deepen_requests=deepen_requests,
        attention_navigation=attention_navigation,
        source_anchor_gate=source_anchor_gate,
        triage_metrics=_memory_packet_triage_metrics(memory_packets),
    )


def _build_recall_recovery(
    inputs: RecallInputStage,
    packets: RecallPacketStage,
    *,
    opened_route_keys: set[str],
    include_associative_fallback: bool,
    associative_path_sidecar_dir: str | Path | None,
    associative_path_bridge_path: str | Path | None,
    associative_path_navigation_path: str | Path | None,
    associative_path_active_lock_path: str | Path | None,
    associative_path_feedback_path: str | Path | None,
    feedback_path: str | Path | None,
) -> RecallRecoveryStage:
    (
        background_recovery_card,
        associative_path_policy,
        associative_path_fallback,
    ) = recall_recovery_layers.weak_recall_recovery_layers(
        query=inputs.query,
        cwd=inputs.cwd_path,
        clean_source_dir=inputs.source_dir,
        project=inputs.project,
        registry_dir=inputs.registry_path,
        memory_packets=packets.memory_packets,
        deepen_requests=packets.deepen_requests,
        triage_metrics=packets.triage_metrics,
        include_associative_fallback=include_associative_fallback,
        associative_path_sidecar_dir=associative_path_sidecar_dir,
        associative_path_bridge_path=associative_path_bridge_path,
        associative_path_navigation_path=associative_path_navigation_path,
        associative_path_active_lock_path=associative_path_active_lock_path,
        associative_path_feedback_path=associative_path_feedback_path,
        feedback_path=feedback_path,
    )
    already_opened_count = _mark_already_opened_routes(
        packets.memory_packets,
        packets.deepen_requests,
        opened_route_keys=opened_route_keys,
    )
    return RecallRecoveryStage(
        background_recovery_card=background_recovery_card,
        associative_path_policy=associative_path_policy,
        associative_path_fallback=associative_path_fallback,
        already_opened_count=already_opened_count,
    )


def _select_recall_action(
    inputs: RecallInputStage,
    packets: RecallPacketStage,
) -> RecallActionStage:
    action_card = foreground_action_card.build_recall_foreground_action_card(
        status="ok" if packets.memory_packets else "no_routes",
        memory_packets=packets.memory_packets,
        deepen_requests=packets.deepen_requests,
        query=inputs.query,
        source_registered=_clean_source_has_messages(inputs.source_dir),
    )
    repo_familiarity_fallback = repo_familiarity_recovery.repo_familiarity_fallback_card(
        inputs.query,
        inputs.cwd_path,
    )
    current_source_anchor_probe = (
        repo_familiarity_recovery.current_source_anchor_probe(
            inputs.query,
            inputs.cwd_path,
            clean_source_dir=inputs.source_dir,
        )
        if isinstance(repo_familiarity_fallback, dict)
        and repo_familiarity_fallback.get("status") == "route_candidate"
        else None
    )
    repo_action_card, repo_suggested_next_command = (
        repo_familiarity_recovery.repo_familiarity_action_card(
            repo_familiarity_fallback=repo_familiarity_fallback,
            previous_card=action_card,
            triage_metrics=packets.triage_metrics,
            memory_packets=packets.memory_packets,
            query=inputs.query,
            current_source_probe=current_source_anchor_probe,
        )
    )
    if repo_action_card:
        action_card = repo_action_card
    suggested_next_command = (
        repo_suggested_next_command
        if repo_suggested_next_command
        else packets.deepen_requests[0].get("copy_paste_command")
        if packets.deepen_requests
        else None
    )
    suggested_next = (
        "open_repo_familiarity_source"
        if repo_action_card
        else "agent deepen"
        if packets.deepen_requests
        else "search_memory"
    )
    return RecallActionStage(
        action_card=action_card,
        repo_familiarity_fallback=repo_familiarity_fallback,
        current_source_anchor_probe=current_source_anchor_probe,
        suggested_next=suggested_next,
        suggested_next_command=suggested_next_command,
    )


def _assemble_recall_result(
    inputs: RecallInputStage,
    routes: RecallRouteStage,
    packets: RecallPacketStage,
    recovery: RecallRecoveryStage,
    actions: RecallActionStage,
    *,
    run_semantic_gate: bool,
    semantic_gate_mode: str,
    semantic_timeout: int,
    include_associative_fallback: bool,
) -> dict[str, Any]:
    navigation_signals = architecture_navigation_affordance.navigation_signals_for_recall(
        query=inputs.query,
        macro_navigation=routes.macro_navigation,
        attention_navigation=packets.attention_navigation,
        memory_packets=packets.memory_packets,
    )
    semantic_diagnostics = agent_semantic_diagnostics.agent_semantic_gate_diagnostics(
        query=inputs.query,
        cwd=inputs.cwd_path,
        clean_source_dir=inputs.source_dir,
        registry_dir=inputs.registry_path,
        max_routes=inputs.effective_limit,
        run_semantic_gate=run_semantic_gate,
        semantic_gate_mode=semantic_gate_mode,
        semantic_timeout=semantic_timeout,
    )
    forbidden_count = _count_forbidden_keys(packets.memory_packets)
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "recall",
        "surface": "agent_cli_or_mcp_adapter",
        "status": "ok" if packets.memory_packets else "no_routes",
        "opt_in_required": False,
        "foreground_action_card": actions.action_card,
        "audit_available": True,
        "memory_packets": packets.memory_packets,
        "deepen_requests": packets.deepen_requests,
        "macro_navigation": routes.macro_navigation,
        "attention_router_navigation": packets.attention_navigation,
        "navigation_signals": navigation_signals,
        "recall_context_diagnostics": {
            "route_count": routes.packet.get("route_count"),
            "metrics": routes.packet.get("metrics"),
            "semantic_trigger_diagnostics": routes.packet.get("semantic_trigger_diagnostics"),
            "warnings": routes.packet.get("warnings") or [],
        },
        "semantic_gate_diagnostics": semantic_diagnostics,
        "associative_path_policy": recovery.associative_path_policy,
        "associative_path_fallback": recovery.associative_path_fallback,
        "background_recovery": recovery.background_recovery_card,
        "repo_familiarity_fallback": actions.repo_familiarity_fallback,
        "current_source_anchor_probe": actions.current_source_anchor_probe,
        "source_anchor_gate": packets.source_anchor_gate,
        "discussion_atlas_pointer": discussion_atlas_pointer_for_query(
            inputs.query,
            cwd=inputs.cwd_path,
        ),
        "suggested_next": actions.suggested_next,
        "suggested_next_command": actions.suggested_next_command,
        **handle_boundary_fields(),
        "policy_boundary": policy_boundary(),
        "metrics": {
            "memory_packet_count": len(packets.memory_packets),
            "deepen_request_count": len(packets.deepen_requests),
            "already_opened_route_count": recovery.already_opened_count,
            "macro_orientation_applied": bool(routes.macro_context is not None),
            **attention_route_projection.metrics_for_attention_navigation(
                packets.attention_navigation
            ),
            "requested_max_routes": inputs.requested_limit,
            "effective_max_routes": inputs.effective_limit,
            "foreground_forbidden_key_count": forbidden_count,
            **foreground_action_card.card_metrics(actions.action_card),
            **packets.triage_metrics,
            **routes.macro_metrics,
            "source_reopen_success_rate_observed": None,
            "wrong_or_stale_handle_rate_observed": None,
            **apw_fallback.recall_fallback_metrics(
                include_associative_fallback,
                recovery.associative_path_policy or {},
                recovery.associative_path_fallback or {},
            ),
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
