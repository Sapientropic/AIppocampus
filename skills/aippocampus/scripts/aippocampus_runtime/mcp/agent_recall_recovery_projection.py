"""Recovery-action projection helpers for compact agent recall output."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    command_value_needs_input,
    normalize_foreground_action,
    shell_quote,
)
from aippocampus_runtime.mcp import agent_recall_apw_meta_echo as apw_meta_echo_projection
from aippocampus_runtime.mcp import agent_recall_compact_choices as recall_choices
from aippocampus_runtime.mcp import current_source_route_policy
from aippocampus_runtime.mcp.agent_recall_compact_choices import (
    EXACT_WORDING_SOURCE_SEARCH_ACTION_ID,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

DeepenActionBuilder = Callable[..., dict[str, Any]]
SourceOpenPrimaryPredicate = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class ApwProjectionState:
    foreground_action: dict[str, Any]
    safe_next_actions: list[dict[str, Any]]
    weak_route_recovery_card: dict[str, Any] | None
    associative_path_fallback: dict[str, Any] | None
    associative_path_policy: dict[str, Any] | None
    apw_recovery: dict[str, Any] | None


def compact_associative_path_fallback_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return core.strip_empty(
        {
            "kind": value.get("kind"),
            "schema_version": value.get("schema_version"),
            "status": value.get("status"),
            "decision": value.get("decision"),
            "ordinary_recall_status": value.get("ordinary_recall_status"),
            "current_build_posture": value.get("current_build_posture"),
            "policy_mode": value.get("policy_mode"),
            "promotion_surface": value.get("promotion_surface"),
            "promotion_gate": value.get("promotion_gate"),
            "route_choice_posture": value.get("route_choice_posture"),
            "request_index": value.get("request_index"),
            "source_ref_digest": value.get("source_ref_digest"),
            "selected_source_ref_count": value.get("selected_source_ref_count"),
            "source_anchor_gate": value.get("source_anchor_gate"),
            "label": value.get("label"),
            "why_this_route": value.get("why_this_route"),
            "matched_cue_anchors": value.get("matched_cue_anchors"),
            "meaningful_cue_anchors": value.get("meaningful_cue_anchors"),
            "anchor_quality": value.get("anchor_quality"),
            "candidate_source_kind": value.get("candidate_source_kind"),
            "route_posture": value.get("route_posture"),
            "action_grammar": value.get("action_grammar"),
            "reason_codes": value.get("reason_codes"),
            "risk_flags": value.get("risk_flags"),
            "summary": value.get("summary"),
            "opt_in_required": value.get("opt_in_required"),
            "applied_to_default_ranking": False,
            "rollback_env": value.get("rollback_env"),
            "rollback_behavior": value.get("rollback_behavior"),
            "source_shape_guarded": value.get("source_shape_guarded"),
            "source_reopen_required_before_claim": True,
        }
    )


def compact_associative_path_policy(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return core.strip_empty(
        {
            "kind": value.get("kind"),
            "schema_version": value.get("schema_version"),
            "current_build_posture": value.get("current_build_posture"),
            "promotion_mode": value.get("promotion_mode"),
            "promotion_surface": value.get("promotion_surface"),
            "promotion_gate": value.get("promotion_gate"),
            "explicit_requested": value.get("explicit_requested"),
            "ordinary_recall_recovery_needed": value.get("ordinary_recall_recovery_needed"),
            "apw_candidate_input_available": value.get("apw_candidate_input_available"),
            "run_fallback": value.get("run_fallback"),
            "run_reason": value.get("run_reason"),
            "opt_in_required_for_this_run": value.get("opt_in_required_for_this_run"),
            "applied_to_default_ranking": False,
            "default_ranking_influence_allowed": False,
            "default_mode_allowed": False,
            "rollback_env": value.get("rollback_env"),
            "hard_off_env": value.get("hard_off_env"),
            "rollback_behavior": value.get("rollback_behavior"),
            "source_reopen_required_before_claim": True,
        }
    )


def associative_path_recovery_state(
    policy: Mapping[str, Any] | None,
    fallback: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(policy, Mapping):
        return None
    run_reason = str(policy.get("run_reason") or "")
    fallback_status = str(fallback.get("status") or "") if isinstance(fallback, Mapping) else ""
    available = bool(policy.get("apw_candidate_input_available"))
    ran = bool(policy.get("run_fallback"))
    requires_opt_in = bool(policy.get("opt_in_required_for_this_run"))
    if fallback_status == "route_candidate":
        state = "already_run"
    elif run_reason == "apw_fallback_policy_off":
        state = "blocked"
    elif available and not ran and requires_opt_in:
        state = "available_requires_explicit_opt_in"
    elif not available:
        state = "unavailable"
    elif not bool(policy.get("ordinary_recall_recovery_needed")):
        state = "not_needed"
    else:
        state = "available"
    return core.strip_empty(
        {
            "state": state,
            "available": available,
            "requires_explicit_opt_in": requires_opt_in and state == "available_requires_explicit_opt_in",
            "already_run": state == "already_run",
            "run_reason": run_reason,
            "source_reopen_required_before_claim": True,
        }
    )


def associative_path_fallback_action(
    card: Mapping[str, Any] | None,
    *,
    recall_selector: str,
    cache_available: bool,
    deepen_action_builder: DeepenActionBuilder,
) -> dict[str, Any] | None:
    if not isinstance(card, Mapping) or card.get("status") != "route_candidate":
        return None
    gate = card.get("source_anchor_gate")
    gate_map = gate if isinstance(gate, Mapping) else {}
    anchor_quality = card.get("anchor_quality")
    anchor_quality_map = anchor_quality if isinstance(anchor_quality, Mapping) else {}
    if gate_map and gate_map.get("target_source_matched") is not True:
        return None
    if str(anchor_quality_map.get("status") or "") in {
        "low_signal_anchors_only",
        "missing_meaningful_anchor",
        "no_anchor_hits",
    }:
        return None
    try:
        request_index = int(card.get("request_index") or 0)
    except (TypeError, ValueError):
        request_index = 0
    if request_index <= 0 or not cache_available:
        return None
    action = deepen_action_builder(request_index, recall_selector=recall_selector)
    action["id"] = "deepen_associative_path_fallback"
    route_label = core.compact_text(str(card.get("label") or ""), 96)
    action["label"] = f"Open {route_label}" if route_label else "Open APW source route"
    anchors = [
        str(anchor)
        for anchor in (card.get("meaningful_cue_anchors") or card.get("matched_cue_anchors") or [])
        if str(anchor).strip()
    ]
    action["why"] = (
        "APW matched cue anchors: "
        + " / ".join(anchors[:3])
        + "; reopen before claims."
        if anchors
        else str(
            card.get("why_this_route")
            or "APW found a source-ref-backed fallback; reopen it before using it."
        )
    )
    action["claim_boundary"] = "no_claim_before_reopen"
    action["actionability"] = "low_confidence_reopenable"
    action["route_choice_posture"] = str(
        card.get("route_choice_posture") or "associative_path_opt_in_fallback"
    )
    return action


def _associative_path_fallback_action_for_projection(
    card: Mapping[str, Any] | None,
    *,
    recall_selector: str,
    cache_available: bool,
    deepen_action_builder: DeepenActionBuilder,
) -> dict[str, Any] | None:
    if not isinstance(card, Mapping) or card.get("status") != "route_candidate":
        return None
    try:
        request_index = int(card.get("request_index") or 0)
    except (TypeError, ValueError):
        request_index = 0
    if request_index <= 0 or not cache_available:
        return None
    return associative_path_fallback_action(
        card,
        recall_selector=recall_selector,
        cache_available=cache_available,
        deepen_action_builder=deepen_action_builder,
    )


def apply_associative_path_recovery(
    payload: Mapping[str, Any],
    *,
    recovery_cue: str,
    recall_selector: str,
    cache_available: bool,
    labels_low_specificity: bool,
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
    weak_route_recovery_card: dict[str, Any] | None,
    deepen_action_builder: DeepenActionBuilder,
    source_open_primary_action: SourceOpenPrimaryPredicate,
) -> ApwProjectionState:
    raw_associative_path_fallback = payload.get("associative_path_fallback")
    raw_associative_path_fallback = (
        raw_associative_path_fallback if isinstance(raw_associative_path_fallback, Mapping) else None
    )
    associative_path_fallback = compact_associative_path_fallback_card(
        raw_associative_path_fallback
    )
    associative_path_policy = compact_associative_path_policy(
        payload.get("associative_path_policy")
    )
    apw_recovery = associative_path_recovery_state(
        associative_path_policy,
        associative_path_fallback,
    )
    associative_path_action = _associative_path_fallback_action_for_projection(
        associative_path_fallback,
        recall_selector=recall_selector,
        cache_available=cache_available,
        deepen_action_builder=deepen_action_builder,
    )
    apw_requested_but_unwired = (
        isinstance(associative_path_policy, dict)
        and associative_path_policy.get("explicit_requested")
        and isinstance(associative_path_fallback, dict)
        and associative_path_fallback.get("status") == "abstained"
        and not associative_path_policy.get("apw_candidate_input_available")
    )
    if apw_requested_but_unwired and labels_low_specificity:
        foreground_action, safe_next_actions, weak_route_recovery_card = (
            _prefer_apw_recovery_over_low_confidence_routes(
                raw_associative_path_fallback=raw_associative_path_fallback,
                associative_path_fallback=associative_path_fallback,
                foreground_action=foreground_action,
                safe_next_actions=safe_next_actions,
                weak_route_recovery_card=weak_route_recovery_card,
                recovery_cue=recovery_cue,
            )
        )
    if associative_path_action:
        ordinary_recovery_action = core.strip_empty(
            normalize_foreground_action(foreground_action)
        )
        ordinary_action_id = str(ordinary_recovery_action.get("id") or ordinary_recovery_action.get("action_id") or "")
        apw_primary = current_source_route_policy.apw_allows_primary_for_current_foreground(
            should_replace=apw_should_replace_foreground_action(foreground_action),
            associative_path_policy=associative_path_policy,
            raw_associative_path_fallback=raw_associative_path_fallback,
            foreground_action=ordinary_recovery_action,
            recall_payload=payload,
        )
        if apw_primary:
            if ordinary_recovery_action:
                safe_next_actions = [ordinary_recovery_action, *safe_next_actions]
            foreground_action = associative_path_action
        if isinstance(associative_path_fallback, dict):
            if apw_primary:
                associative_path_fallback["primary_action"] = "deepen_associative_path_fallback"
                if ordinary_action_id:
                    associative_path_fallback["ordinary_recovery_action_id"] = ordinary_action_id
            else:
                # APW is a foreground recovery surface, not a parallel route chooser.
                # Keep it in detail when ordinary recall has a safe primary.
                associative_path_fallback = None
                associative_path_policy = None
    else:
        foreground_action, safe_next_actions = (
            apw_meta_echo_projection.maybe_promote_original_anchor_search(
                associative_path_fallback=associative_path_fallback,
                foreground_action=foreground_action,
                safe_next_actions=safe_next_actions,
                recovery_cue=recovery_cue,
                source_open_primary_action=source_open_primary_action,
            )
        )
        associative_policy_action = associative_path_policy_recovery_action(
            associative_path_policy,
            recovery_cue=recovery_cue,
        )
        if associative_policy_action and "secondary_action" not in foreground_action:
            foreground_action["secondary_action"] = associative_policy_action
            if isinstance(associative_path_policy, dict):
                associative_path_policy["secondary_action"] = associative_policy_action["id"]
    return ApwProjectionState(
        foreground_action=foreground_action,
        safe_next_actions=safe_next_actions,
        weak_route_recovery_card=weak_route_recovery_card,
        associative_path_fallback=associative_path_fallback,
        associative_path_policy=associative_path_policy,
        apw_recovery=apw_recovery,
    )


def _prefer_apw_recovery_over_low_confidence_routes(
    *,
    raw_associative_path_fallback: Mapping[str, Any] | None,
    associative_path_fallback: dict[str, Any] | None,
    foreground_action: dict[str, Any],
    safe_next_actions: list[dict[str, Any]],
    weak_route_recovery_card: dict[str, Any] | None,
    recovery_cue: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    # A foreground APW request is stronger evidence of user intent than a
    # generic relationship/task-management route. When APW cannot produce a
    # source-openable candidate, keep ordinary low-confidence routes as
    # secondary navigation only and make the primary action recover the cue.
    ordinary_recovery_action = core.strip_empty(normalize_foreground_action(foreground_action))
    if ordinary_recovery_action:
        ordinary_recovery_action["route_choice_posture"] = (
            ordinary_recovery_action.get("route_choice_posture")
            or "ordinary_low_confidence_not_apw"
        )
        safe_next_actions = [ordinary_recovery_action, *safe_next_actions]
    registry_match_count = 0
    if isinstance(raw_associative_path_fallback, Mapping):
        registry_match_count = int(raw_associative_path_fallback.get("registry_match_count") or 0)
    registry_fallback = (
        recall_choices.registry_source_search_fallback_action(recovery_cue)
        if registry_match_count > 0
        else None
    )
    foreground_action = registry_fallback or {
        "id": "refine_apw_recovery_cue",
        "label": "Refine APW recovery cue",
        "tool_name": "agent_recall",
        "command_template": 'aippocampus agent recall "{tighter_cue}" --apw-fallback --json',
        "requires": ["tighter_cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "apw_navigation_only_until_source_reopened",
        "why": (
            "APW was explicitly requested but found no source-reopenable route; "
            "tighten the cue instead of deepening a low-confidence ordinary route."
        ),
    }
    foreground_action["route_choice_posture"] = "apw_requested_no_source_reopenable_candidate"
    foreground_action["why"] = (
        "APW was explicitly requested but did not find a source-reopenable candidate; "
        "search or refine the original cue before choosing an ordinary low-confidence route."
    )
    if isinstance(associative_path_fallback, dict):
        associative_path_fallback["primary_action"] = (
            foreground_action.get("id") or foreground_action.get("action_id")
        )
        associative_path_fallback["ordinary_low_confidence_routes_demoted"] = True
    if isinstance(weak_route_recovery_card, dict):
        weak_route_recovery_card["primary_action"] = (
            foreground_action.get("id") or foreground_action.get("action_id")
        )
        weak_route_recovery_card["posture"] = "apw_requested_no_source_reopenable_candidate"
    return foreground_action, safe_next_actions, weak_route_recovery_card


def associative_path_policy_recovery_action(
    policy: Mapping[str, Any] | None,
    *,
    recovery_cue: str,
) -> dict[str, Any] | None:
    if not isinstance(policy, Mapping):
        return None
    if policy.get("run_reason") != "apw_label_weakness_requires_explicit_opt_in":
        return None
    if not (
        policy.get("ordinary_recall_recovery_needed")
        and policy.get("apw_candidate_input_available")
        and policy.get("run_fallback") is False
    ):
        return None
    cue = core.compact_text(str(recovery_cue or "").strip(), 160)
    action: dict[str, Any] = {
        "id": "run_apw_opt_in_recovery",
        "label": "Try APW recovery",
        "tool_name": "agent_recall",
        "mutation_risk": "read_only",
        "claim_boundary": "apw_navigation_only_until_source_reopened",
        "route_choice_posture": "associative_path_opt_in_recovery",
        "source_reopen_required_before_claim": True,
        "why": (
            "Ordinary recall surfaced a weak route while APW has candidate input; "
            "run explicit APW recovery before broad manual search."
        ),
    }
    if cue and not command_value_needs_input(cue):
        action["arguments"] = {"cue": cue, "apw_fallback": True}
        action["command"] = f"aippocampus agent recall {shell_quote(cue)} --apw-fallback --json"
    else:
        action["arguments"] = {"apw_fallback": True}
        action["command_template"] = 'aippocampus agent recall "{cue}" --apw-fallback --json'
        action["requires"] = ["cue"]
        action["template_only"] = True
    return action


def apw_should_replace_foreground_action(action: Mapping[str, Any]) -> bool:
    """Return whether APW recovery should become the compact primary action."""

    action_id = str(action.get("id") or action.get("action_id") or "")
    route_posture = str(action.get("route_choice_posture") or "")
    if route_posture == "labels_low_specificity":
        return True
    # `inspect_low_confidence_route` is already an admission that the ordinary
    # route needs source-anchor recovery before it can guide the foreground
    # agent. If APW has a gated current-source candidate, prefer that direct
    # reopen path instead of asking the agent to inspect the known-weak sibling
    # first. A target-matched ordinary route is still protected by
    # `apw_allows_primary_for_current_foreground`.
    if action_id in {"inspect_low_confidence_route", "deepen_top_route_low_confidence"}:
        return True
    if action_id.startswith("recover_"):
        return True
    return action_id in {
        "search_registry_sources_for_original_cue_anchors",
        "refine_low_specificity_recall_cue",
    }


def compact_repo_familiarity_fallback_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return core.strip_empty(
        {
            "kind": value.get("kind"),
            "schema_version": value.get("schema_version"),
            "status": value.get("status"),
            "route_choice_posture": value.get("route_choice_posture"),
            "landmark": value.get("landmark"),
            "category": value.get("category"),
            "why_now": value.get("why_now"),
            "action_delta_required": value.get("action_delta_required"),
            "first_source_to_reopen": value.get("first_source_to_reopen"),
            "source_line": value.get("source_line"),
            "source_ref_count": value.get("source_ref_count"),
            "selected_card_count": value.get("selected_card_count"),
            "query_anchor_count": value.get("query_anchor_count"),
            "query_anchor_match_count": value.get("query_anchor_match_count"),
            "query_anchor_alignment": value.get("query_anchor_alignment"),
            "current_checkout_checked": value.get("current_checkout_checked"),
            "invalidation_present": value.get("invalidation_present"),
            "stale_fast_reject_count": value.get("stale_fast_reject_count"),
            "irrelevant_reject_count": value.get("irrelevant_reject_count"),
            "source_reopen_required_before_claim": True
            if value.get("status") == "route_candidate"
            else None,
            "claim_boundary": value.get("claim_boundary"),
        }
    )


def _repo_file_read_command(path: str) -> str:
    script = (
        "import pathlib,sys; "
        "p=pathlib.Path(sys.argv[1]); "
        "print(p.read_text(encoding='utf-8')[:6000])"
    )
    return f'python -c "{script}" {shell_quote(path)}'


def repo_familiarity_fallback_action(card: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(card, Mapping) or card.get("status") != "route_candidate":
        return None
    path = str(
        redact_sensitive_values(
            redact_private_paths(str(card.get("first_source_to_reopen") or "").strip())
        )
        or ""
    ).strip()
    if not path or command_value_needs_input(path) or ":" in path or "\\" in path:
        return None
    line = card.get("source_line")
    arguments: dict[str, Any] = {"path": path}
    if isinstance(line, int) and line > 0:
        arguments["line"] = line
    label = core.compact_text(str(card.get("landmark") or "repo source"), 80)
    return {
        "id": "open_repo_familiarity_source",
        "label": f"Open {label}",
        "tool_name": "shell",
        "arguments": arguments,
        "command": _repo_file_read_command(path),
        "mutation_risk": "read_only",
        "claim_boundary": "repo_familiarity_navigation_only_until_source_opened",
        "route_choice_posture": str(
            card.get("route_choice_posture") or "repo_familiarity_current_checkout_fallback"
        ),
        "why": core.compact_text(
            str(
                card.get("action_delta_required")
                or card.get("why_now")
                or "Current checkout familiarity found a repo doc; open it before making claims."
            ),
            220,
        ),
        "source_reopen_required_before_claim": True,
    }


def repo_familiarity_should_replace_foreground_action(action: Mapping[str, Any]) -> bool:
    action_id = str(action.get("id") or action.get("action_id") or "")
    if action_id == EXACT_WORDING_SOURCE_SEARCH_ACTION_ID:
        return False
    if action_id == "deepen_associative_path_fallback":
        return False
    route_posture = str(action.get("route_choice_posture") or "")
    if route_posture == "labels_low_specificity":
        return True
    if action_id.startswith("recover_"):
        return True
    if action_id in {
        "search_registry_sources_for_original_cue_anchors",
        "refine_low_specificity_recall_cue",
        "repair_last_recall_cache",
    }:
        return True
    return str(action.get("tool_name") or "") == "search_memory"


def repo_familiarity_query_anchor_alignment(card: Mapping[str, Any] | None) -> str:
    if not isinstance(card, Mapping):
        return "unknown"
    alignment = str(card.get("query_anchor_alignment") or "").strip()
    if alignment:
        return alignment
    try:
        total = int(card.get("query_anchor_count") or 0)
        matched = int(card.get("query_anchor_match_count") or 0)
    except (TypeError, ValueError):
        return "unknown"
    if total <= 0:
        return "no_distinctive_query_anchors"
    return "overlap" if matched > 0 else "no_overlap"
