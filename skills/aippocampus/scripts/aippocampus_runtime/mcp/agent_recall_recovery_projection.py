"""Recovery-action projection helpers for compact agent recall output."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import command_value_needs_input, shell_quote
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

DeepenActionBuilder = Callable[..., dict[str, Any]]


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


def compact_associative_path_fallback_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _without_empty(
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
            "apw_route_identity": value.get("apw_route_identity"),
            "label": value.get("label"),
            "why_this_route": value.get("why_this_route"),
            "matched_cue_anchors": value.get("matched_cue_anchors"),
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
    return _without_empty(
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


def associative_path_fallback_action(
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
    action = deepen_action_builder(request_index, recall_selector=recall_selector)
    action["id"] = "deepen_associative_path_fallback"
    route_label = core.compact_text(str(card.get("label") or ""), 96)
    action["label"] = f"Open {route_label}" if route_label else "Open APW source route"
    anchors = [
        str(anchor)
        for anchor in card.get("matched_cue_anchors") or []
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
    action["route_choice_posture"] = str(
        card.get("route_choice_posture") or "associative_path_opt_in_fallback"
    )
    identity = card.get("apw_route_identity")
    if isinstance(identity, Mapping):
        action_identity = dict(identity)
        if recall_selector:
            action_identity["recall_selector"] = recall_selector
        action_identity["request_index"] = request_index
        action["apw_route_identity"] = _without_empty(action_identity)
    return action


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
    if action_id.startswith("recover_"):
        return True
    return action_id in {
        "search_registry_sources_for_original_cue_anchors",
        "refine_low_specificity_recall_cue",
    }


def compact_repo_familiarity_fallback_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _without_empty(
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
    literal = json.dumps(path)
    script = (
        "from pathlib import Path; "
        f"p=Path({literal}); "
        "print(p.read_text(encoding='utf-8')[:6000])"
    )
    return f"python -c {shell_quote(script)}"


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
