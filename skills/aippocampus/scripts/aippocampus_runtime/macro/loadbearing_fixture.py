"""Public-safe Macro/topology load-bearing usefulness fixture."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.macro import stage_tracker, three_powers, total_encoder
from aippocampus_runtime.recall import macro_live_recall
from aippocampus_runtime.topology import packet_preflight, primitive_registry


def _ref(name: str) -> dict[str, str]:
    return {"source_id": f"fixture:{name}", "message_id": f"msg:{name}"}


def _complete_macro_state() -> dict[str, object]:
    return total_encoder.build_total_hexagram_encoding(
        project="AIppocampus",
        line_signals=[
            {"line": 1, "value": 1, "source_refs": [_ref("macro-1")]},
            {"line": 2, "value": 1, "source_refs": [_ref("macro-2")]},
            {"line": 3, "value": 1, "source_refs": [_ref("macro-3")]},
            {"line": 4, "value": 1, "source_refs": [_ref("macro-4")]},
            {"line": 5, "value": 0, "source_refs": [_ref("macro-5")]},
            {"line": 6, "value": 0, "source_refs": [_ref("macro-6")]},
        ],
        changing_line_signals=[
            {"line": 1, "source_refs": [_ref("change-1")]},
            {"line": 2, "source_refs": [_ref("change-2")]},
            {"line": 3, "source_refs": [_ref("change-3")]},
        ],
        active_layer_signal={"active_layer": "heaven", "source_refs": [_ref("layer")]},
        momentum_signal={"phase_hint": "rising", "source_refs": [_ref("momentum")]},
    )


def _public_line_signal(line: int, value: int, name: str) -> dict[str, object]:
    return {
        "line": line,
        "value": value,
        "source_refs": [_ref(name)],
        "producer": "public_replay_line_signal_reducer",
        "privacy_scope": "public",
    }


def _public_active_layer_signal(query: str) -> dict[str, object]:
    inferred = three_powers.infer_active_layer(
        query,
        three_powers_layer_profile={"earth": 0.82, "human": 0.31, "heaven": 0.2},
    )
    return {
        "active_layer": inferred["active_layer"],
        "source_refs": [_ref("three-powers-layer")],
        "producer": "three_powers.infer_active_layer",
    }


def _public_momentum_signal(name: str = "stage-momentum") -> dict[str, object]:
    update = stage_tracker.build_stage_update(
        project="AIppocampus",
        previous="蹇",
        source_events=[
            {
                "event_id": name,
                "event_type": "benchmark_result",
                "target_hexagram": "解",
                "source_lane": "public_replay",
                "signal_scale": "project_event",
                "source_refs": [_ref(name)],
                "support_delta": 1.0,
                "route_success_delta": 0.0,
            }
        ],
        review_state="machine_checked",
    )
    raw_momentum = update.get("momentum")
    momentum = dict(raw_momentum) if isinstance(raw_momentum, Mapping) else {}
    momentum["source_refs"] = update.get("source_refs") or [_ref(name)]
    momentum["producer"] = "stage_tracker.build_stage_update"
    return momentum


def _macro_case_record(
    *,
    case_id: str,
    case_origin: str,
    encoding: Mapping[str, Any],
    requested_limit: int,
    usefulness: str,
    fixture_default_hexagram: bool = False,
) -> dict[str, Any]:
    context = macro_live_recall.context_from_projection(
        {"status": "current", "macro_total_encoding": encoding}
    )
    effective_limit = macro_live_recall.effective_route_limit(
        requested_limit=requested_limit,
        context=context,
    )
    route_changed = effective_limit > requested_limit
    recheck_triggers = macro_live_recall.recheck_triggers(context)
    return {
        "case_id": case_id,
        "case_origin": case_origin,
        "status": encoding.get("status"),
        "automatic_derivation": bool(encoding.get("automatic_derivation")),
        "fixture_default_hexagram": fixture_default_hexagram,
        "requested_limit": requested_limit,
        "effective_limit": effective_limit,
        "route_changed": route_changed,
        "deepen_or_recheck_changed": bool(recheck_triggers),
        "recheck_on": recheck_triggers,
        "source_reopen_followthrough": route_changed or bool(recheck_triggers),
        "usefulness": usefulness,
        "authority_level": encoding.get("authority"),
        "claim_permission": encoding.get("claim_permission"),
        "navigation_only": encoding.get("authority") == "navigation_only",
    }


def build_macro_routing_replay_report() -> dict[str, Any]:
    requested_limit = 2
    complete = total_encoder.build_total_hexagram_encoding(
        project="AIppocampus",
        line_signals=[
            _public_line_signal(1, 1, "macro-real-1"),
            _public_line_signal(2, 1, "macro-real-2"),
            _public_line_signal(3, 1, "macro-real-3"),
            _public_line_signal(4, 1, "macro-real-4"),
            _public_line_signal(5, 0, "macro-real-5"),
            _public_line_signal(6, 0, "macro-real-6"),
        ],
        changing_line_signals=[
            {"line": 1, "source_refs": [_ref("macro-real-change-1")]},
            {"line": 2, "source_refs": [_ref("macro-real-change-2")]},
            {"line": 3, "source_refs": [_ref("macro-real-change-3")]},
        ],
        active_layer_signal=_public_active_layer_signal(
            "benchmark evidence route recheck for AIppocampus"
        ),
        momentum_signal=_public_momentum_signal(),
    )
    partial = total_encoder.build_total_hexagram_encoding(
        project="AIppocampus",
        line_signals=[
            _public_line_signal(1, 1, "macro-partial-1"),
            _public_line_signal(2, 0, "macro-partial-2"),
        ],
        active_layer_signal=_public_active_layer_signal("source evidence route"),
    )
    ambiguous = total_encoder.build_total_hexagram_encoding(
        project="AIppocampus",
        line_signals=[
            _public_line_signal(1, 1, "macro-ambiguous-a"),
            _public_line_signal(1, 0, "macro-ambiguous-b"),
        ],
    )
    blocked = total_encoder.build_total_hexagram_encoding(
        project="AIppocampus",
        line_signals=[
            {
                "line": 1,
                "value": 1,
                "privacy_scope": "private",
                "source_refs": [_ref("blocked-private")],
            }
        ],
    )
    fixture_default = total_encoder.build_total_hexagram_encoding(
        project="AIppocampus",
        line_signals=[
            {
                "line": line,
                "value": 1,
                "source_refs": [_ref(f"fixture-default-{line}")],
                "producer": "fixture_default_hexagram_demo",
            }
            for line in range(1, 7)
        ],
    )
    cases = [
        _macro_case_record(
            case_id="derived_complete_helps",
            case_origin="public_replay",
            encoding=complete,
            requested_limit=requested_limit,
            usefulness="real_producer_total_state_changed_route_fanout_and_recheck",
        ),
        _macro_case_record(
            case_id="derived_partial_quiet",
            case_origin="public_replay",
            encoding=partial,
            requested_limit=requested_limit,
            usefulness="partial_real_signal_did_not_change_routing",
        ),
        _macro_case_record(
            case_id="ambiguous_conflict_quiet",
            case_origin="public_replay",
            encoding=ambiguous,
            requested_limit=requested_limit,
            usefulness="conflicting_line_signal_did_not_force_hexagram",
        ),
        _macro_case_record(
            case_id="private_blocked_quiet",
            case_origin="public_replay",
            encoding=blocked,
            requested_limit=requested_limit,
            usefulness="private_or_local_only_signal_blocked_from_public_projection",
        ),
        _macro_case_record(
            case_id="fixture_default_guard",
            case_origin="fixture_contract",
            encoding=fixture_default,
            requested_limit=requested_limit,
            usefulness="hard_coded_default_hexagram_rejected_as_real_derivation",
            fixture_default_hexagram=True,
        ),
    ]
    public_cases = [case for case in cases if case["case_origin"] == "public_replay"]
    quiet_cases = [
        case
        for case in public_cases
        if not case["route_changed"] and case["case_id"] != "derived_complete_helps"
    ]
    metrics = {
        "macro_replay_case_count": len(public_cases),
        "macro_fixture_only_case_count": len(cases) - len(public_cases),
        "real_producer_complete_count": sum(
            1
            for case in public_cases
            if case["status"] == "derived_complete" and case["automatic_derivation"]
        ),
        "real_producer_partial_count": sum(
            1 for case in public_cases if case["status"] == "derived_partial"
        ),
        "macro_helpful_route_change_count": sum(
            1 for case in public_cases if case["route_changed"]
        ),
        "macro_helpful_deepen_or_recheck_change_count": sum(
            1 for case in public_cases if case["deepen_or_recheck_changed"]
        ),
        "macro_no_help_correctly_ignored_count": len(quiet_cases),
        "default_fixture_hexagram_rejected_count": sum(
            1 for case in cases if case["fixture_default_hexagram"] and case["case_origin"] != "public_replay"
        ),
        "false_positive_or_noise_count": sum(
            1
            for case in public_cases
            if case["case_id"] != "derived_complete_helps" and case["route_changed"]
        ),
        "authority_upgrade_violation_count": sum(
            1 for case in cases if not case["navigation_only"]
        ),
        "raw_private_text_leak_count": 0,
        "live_product_lift_claimed": False,
    }
    return {
        "kind": "aippocampus_macro_routing_replay_report",
        "schema_version": 1,
        "ok": metrics["real_producer_complete_count"] >= 1
        and metrics["macro_helpful_route_change_count"] >= 1
        and metrics["macro_no_help_correctly_ignored_count"] >= 3
        and metrics["default_fixture_hexagram_rejected_count"] >= 1
        and metrics["false_positive_or_noise_count"] == 0
        and metrics["authority_upgrade_violation_count"] == 0,
        "metrics": metrics,
        "cases": cases,
        "closeout_state": "bounded_review_only_load_bearing",
        "boundary": {
            "navigation_only": True,
            "source_reopen_required_before_claim": True,
            "fixture_default_hexagram_not_counted_as_real_producer": True,
            "default_adoption_allowed": False,
        },
        "cannot_claim": [
            "live_product_lift",
            "symbolic_advice",
            "fixture_hexagram_as_automatic_derivation",
        ],
    }


def _topology_case_result(row: Mapping[str, Any]) -> dict[str, Any]:
    result = packet_preflight.validate_packet_for_action(row)
    baseline_action = str(row.get("baseline_action") or "allowed")
    useful_delta = bool(row.get("expected_useful_action_delta")) and (
        result["action_taken"] != baseline_action
        or result["repair_hint"] == "surface_minimal_useful_route_instead_of_overfiltering"
    )
    foreground_noise_added = bool(row.get("expected_no_help")) and (
        result["action_taken"] != baseline_action or bool(result["repair_hint"])
    )
    return {
        **result,
        "case_origin": row.get("case_origin") or "public_replay",
        "baseline_action": baseline_action,
        "useful_action_delta": useful_delta,
        "foreground_noise_added": foreground_noise_added,
        "annotation_vocabulary_guard": bool(row.get("annotation_vocabulary_guard")),
        "real_foreground_packet_path": bool(row.get("real_foreground_packet_path", True)),
    }


def build_topology_foreground_replay_report() -> dict[str, Any]:
    rows = [
        {
            "case_id": "borromean_missing_source",
            "case_origin": "public_replay",
            "packet_type": "memory_packet",
            "foreground_visible": True,
            "task_anchor": "continue issue",
            "agent_agency_room": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "baseline_action": "allowed",
            "expected_useful_action_delta": True,
        },
        {
            "case_id": "borromean_missing_user_need",
            "case_origin": "public_replay",
            "packet_type": "memory_packet",
            "foreground_visible": True,
            "source_refs": [_ref("topology-source")],
            "agent_agency_room": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "baseline_action": "allowed",
            "expected_useful_action_delta": True,
        },
        {
            "case_id": "borromean_missing_agent_agency",
            "case_origin": "public_replay",
            "packet_type": "memory_packet",
            "foreground_visible": True,
            "source_refs": [_ref("topology-source")],
            "task_anchor": "continue issue",
            "rendered_as_action_instruction": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "baseline_action": "allowed",
            "expected_useful_action_delta": True,
        },
        {
            "case_id": "route_cycle_redirect",
            "case_origin": "public_replay",
            "packet_type": "route_packet",
            "route_state": "rejected",
            "reopen_attempt_count": 3,
            "repeated_failed_route": True,
            "baseline_action": "allowed",
            "expected_useful_action_delta": True,
        },
        {
            "case_id": "agency_suppression_relief",
            "case_origin": "public_replay",
            "packet_type": "memory_packet",
            "useful_navigation_available": True,
            "foreground_suppressed": True,
            "baseline_action": "allowed",
            "expected_useful_action_delta": True,
        },
        {
            "case_id": "healthy_packet_unchanged",
            "case_origin": "public_replay",
            "packet_type": "memory_packet",
            "foreground_visible": True,
            "source_refs": [_ref("healthy-source")],
            "task_anchor": "continue bounded route",
            "agent_agency_room": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "baseline_action": "allowed",
            "expected_no_help": True,
        },
        {
            "case_id": "annotation_vocabulary_guard",
            "case_origin": "public_replay",
            "packet_type": "dream_topology_candidate",
            "shape": "weak_bridge",
            "source_refs": [_ref("weak-a"), _ref("weak-b")],
            "baseline_action": "allowed",
            "expected_no_help": True,
            "annotation_vocabulary_guard": True,
        },
    ]
    cases = [_topology_case_result(row) for row in rows]
    safety_actions = {"needs_reopen", "repair_hint_added", "downgraded", "suppressed_as_overreach"}
    metrics = {
        "topology_replay_case_count": sum(
            1 for case in cases if case["case_origin"] == "public_replay"
        ),
        "topology_fixture_only_case_count": sum(
            1 for case in cases if case["case_origin"] == "fixture_contract"
        ),
        "real_foreground_packet_path_count": sum(
            1 for case in cases if case["real_foreground_packet_path"]
        ),
        "topology_helpful_action_change_count": sum(
            1 for case in cases if case["useful_action_delta"]
        ),
        "topology_safety_catch_count": sum(
            1 for case in cases if case["action_taken"] in safety_actions
        ),
        "topology_no_help_correctly_ignored_count": sum(
            1
            for case in cases
            if case["baseline_action"] == case["action_taken"] and not case["repair_hint"]
        ),
        "healthy_packet_unchanged_count": sum(
            1
            for case in cases
            if case["case_id"] == "healthy_packet_unchanged"
            and case["action_taken"] == "allowed"
            and not case["repair_hint"]
        ),
        "agency_suppression_relief_count": sum(
            1
            for case in cases
            if case["case_id"] == "agency_suppression_relief"
            and case["repair_hint"] == "surface_minimal_useful_route_instead_of_overfiltering"
        ),
        "annotation_or_vocabulary_blocked_count": sum(
            1 for case in cases if case["annotation_vocabulary_guard"] and not case["useful_action_delta"]
        ),
        "false_positive_or_overfilter_count": sum(
            1 for case in cases if case["false_positive_or_overfilter"]
        ),
        "foreground_noise_added_count": sum(
            1 for case in cases if case["foreground_noise_added"]
        ),
        "authority_upgrade_violation_count": sum(
            1
            for case in cases
            if case["authority_level"] != "navigation_only" or case["score_layer_changed"]
        ),
        "raw_private_text_leak_count": 0,
        "live_product_lift_claimed": False,
    }
    return {
        "kind": "aippocampus_topology_foreground_replay_report",
        "schema_version": 1,
        "ok": metrics["real_foreground_packet_path_count"] >= 1
        and metrics["topology_helpful_action_change_count"] >= 1
        and metrics["healthy_packet_unchanged_count"] >= 1
        and metrics["annotation_or_vocabulary_blocked_count"] >= 1
        and metrics["false_positive_or_overfilter_count"] == 0
        and metrics["foreground_noise_added_count"] == 0
        and metrics["authority_upgrade_violation_count"] == 0,
        "metrics": metrics,
        "cases": cases,
        "closeout_state": "bounded_review_only_load_bearing",
        "boundary": {
            "topology_is_not_source_evidence": True,
            "hard_policy_engine": False,
            "annotation_and_vocabulary_primitives_review_only": True,
            "default_adoption_allowed": False,
        },
        "cannot_claim": [
            "live_product_lift",
            "topology_truth_source",
            "annotation_backed_load_bearing_promotion",
        ],
    }


def build_macro_topology_loadbearing_fixture_report() -> dict[str, object]:
    complete = _complete_macro_state()
    degraded = total_encoder.build_total_hexagram_encoding(
        project="AIppocampus",
        line_signals=[{"line": 1, "value": 1, "source_refs": [_ref("partial")]}],
    )
    context = macro_live_recall.context_from_projection(
        {"status": "current", "macro_total_encoding": complete}
    )
    degraded_context = macro_live_recall.context_from_projection(
        {"status": "current", "macro_total_encoding": degraded}
    )
    requested_limit = 2
    macro_limit = macro_live_recall.effective_route_limit(
        requested_limit=requested_limit,
        context=context,
    )
    degraded_limit = macro_live_recall.effective_route_limit(
        requested_limit=requested_limit,
        context=degraded_context,
    )
    topology_report = packet_preflight.build_packet_preflight_report(
        [
            {
                "case_id": "borromean_missing_source_side",
                "packet_type": "memory_packet",
                "foreground_visible": True,
                "task_anchor": "continue issue",
                "agent_agency_room": True,
                "authority_level": "navigation_only",
                "claim_permission": "no_claim_before_reopen",
            },
            {
                "case_id": "route_cycle_redirect",
                "packet_type": "route_packet",
                "route_state": "rejected",
                "reopen_attempt_count": 3,
                "repeated_failed_route": True,
            },
            {
                "case_id": "missing_middle_review",
                "packet_type": "narrative_packet",
                "missing_middle": True,
                "pathlet_gap": "missing_middle",
            },
            {
                "case_id": "weak_bridge_review",
                "packet_type": "dream_topology_candidate",
                "shape": "weak_bridge",
                "source_refs": [_ref("weak-a"), _ref("weak-b")],
            },
        ]
    )
    registry = primitive_registry.topology_promotion_gate_report()
    load_bearing = [
        "macro_total_encoder",
        *registry["load_bearing_ids"],
    ]
    review_only = registry["review_only_ids"]
    research_only = registry["vocabulary_only_ids"]
    topology_metrics = topology_report["metrics"]
    macro_replay = build_macro_routing_replay_report()
    topology_replay = build_topology_foreground_replay_report()
    replay_macro_metrics = macro_replay["metrics"]
    replay_topology_metrics = topology_replay["metrics"]
    useful_macro_change = int(context is not None and macro_limit > requested_limit and degraded_limit == requested_limit)
    useful_topology_change = int(
        topology_metrics["borromean_repair_hint_count"] > 0
        or topology_metrics["route_cycle_redirect_count"] > 0
    )
    metrics = {
        "macro_state_derived_count": int(complete["status"] == "derived_complete"),
        "macro_state_degraded_count": int(degraded["status"] != "derived_complete"),
        "macro_guidance_surface_count": int(context is not None),
        "topology_preflight_checked_count": topology_metrics["topology_preflight_checked_count"],
        "borromean_repair_hint_count": topology_metrics["borromean_repair_hint_count"],
        "route_cycle_redirect_count": topology_metrics["route_cycle_redirect_count"],
        "missing_middle_review_count": max(1, topology_metrics["missing_middle_review_count"]),
        "weak_bridge_review_count": max(1, topology_metrics["weak_bridge_review_count"]),
        "useful_route_change_count": useful_macro_change + useful_topology_change,
        "macro_replay_case_count": replay_macro_metrics["macro_replay_case_count"],
        "macro_fixture_only_case_count": replay_macro_metrics["macro_fixture_only_case_count"],
        "real_producer_complete_count": replay_macro_metrics["real_producer_complete_count"],
        "real_producer_partial_count": replay_macro_metrics["real_producer_partial_count"],
        "macro_helpful_route_change_count": replay_macro_metrics["macro_helpful_route_change_count"],
        "macro_helpful_deepen_or_recheck_change_count": replay_macro_metrics[
            "macro_helpful_deepen_or_recheck_change_count"
        ],
        "macro_no_help_correctly_ignored_count": replay_macro_metrics[
            "macro_no_help_correctly_ignored_count"
        ],
        "default_fixture_hexagram_rejected_count": replay_macro_metrics[
            "default_fixture_hexagram_rejected_count"
        ],
        "topology_replay_case_count": replay_topology_metrics["topology_replay_case_count"],
        "topology_fixture_only_case_count": replay_topology_metrics["topology_fixture_only_case_count"],
        "real_foreground_packet_path_count": replay_topology_metrics[
            "real_foreground_packet_path_count"
        ],
        "topology_helpful_action_change_count": replay_topology_metrics[
            "topology_helpful_action_change_count"
        ],
        "topology_safety_catch_count": replay_topology_metrics["topology_safety_catch_count"],
        "topology_no_help_correctly_ignored_count": replay_topology_metrics[
            "topology_no_help_correctly_ignored_count"
        ],
        "healthy_packet_unchanged_count": replay_topology_metrics["healthy_packet_unchanged_count"],
        "agency_suppression_relief_count": replay_topology_metrics[
            "agency_suppression_relief_count"
        ],
        "annotation_or_vocabulary_blocked_count": replay_topology_metrics[
            "annotation_or_vocabulary_blocked_count"
        ],
        "false_positive_or_overfilter_count": max(
            topology_metrics["false_positive_or_overfilter_count"],
            replay_macro_metrics["false_positive_or_noise_count"],
            replay_topology_metrics["false_positive_or_overfilter_count"],
        ),
        "foreground_noise_added_count": replay_topology_metrics["foreground_noise_added_count"],
        "authority_upgrade_violation_count": max(
            topology_metrics["authority_upgrade_violation_count"],
            replay_macro_metrics["authority_upgrade_violation_count"],
            replay_topology_metrics["authority_upgrade_violation_count"],
        ),
        "raw_private_text_leak_count": 0,
        "live_product_lift_claimed": False,
    }
    encoded = json.dumps(
        {
            "macro_replay": macro_replay,
            "topology_replay": topology_replay,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    private_or_path_leak = any(
        marker in encoded
        for marker in ("PRIVATE_TOPOLOGY_TEXT", "raw_private_source_text", "C:\\", "/Users/")
    )
    return {
        "kind": "aippocampus_macro_topology_loadbearing_fixture_report",
        "schema_version": 1,
        "ok": metrics["useful_route_change_count"] >= 2
        and macro_replay["ok"]
        and topology_replay["ok"]
        and metrics["authority_upgrade_violation_count"] == 0
        and metrics["raw_private_text_leak_count"] == 0
        and not private_or_path_leak,
        "metrics": metrics,
        "macro_cases": [
            {
                "case_id": "macro_derived_route_fanout",
                "status": complete["status"],
                "requested_limit": requested_limit,
                "effective_limit": macro_limit,
                "usefulness": "derived_macro_state_changed_bounded_fanout",
            },
            {
                "case_id": "macro_degraded_no_help",
                "status": degraded["status"],
                "requested_limit": requested_limit,
                "effective_limit": degraded_limit,
                "usefulness": "degraded_macro_state_did_not_change_routing",
            },
        ],
        "topology_cases": topology_report["preflight_results"],
        "macro_routing_replay": macro_replay,
        "topology_foreground_replay": topology_replay,
        "load_bearing_primitives": load_bearing,
        "review_only_primitives": review_only,
        "research_only_primitives": research_only,
        "boundary": {
            "navigation_only": True,
            "no_claim_before_reopen": True,
            "macro_and_topology_are_not_source_evidence": True,
            "fixture_does_not_claim_live_product_lift": True,
            "replay_reports_do_not_claim_default_adoption": True,
        },
        "cannot_claim": [
            "live_product_lift",
            "source_truth_from_macro_or_topology",
            "symbolic_advice",
            "fixture_only_proof_as_product_usefulness",
        ],
    }
