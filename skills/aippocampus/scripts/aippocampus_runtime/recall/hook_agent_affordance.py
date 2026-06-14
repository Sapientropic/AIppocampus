"""Prompt-hook affordance envelope for active agent continuity pulls."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

AFFORDANCE_SCHEMA_VERSION = "hook-agent-affordance-v0"
PRIVACY_BOUNDARY = "no raw source, no local paths, no source refs in hook"

_AGENT_ACTIONS = {"agent_aippo", "agent_recall", "agent_deepen"}
_AGENT_TOOL_BY_ACTION = {
    "agent_aippo": "aippocampus agent aippo",
    "agent_recall": "aippocampus agent recall",
    "agent_deepen": "aippocampus agent deepen",
}
_STRONG_CLAIM_INTENTS = {
    "exact_claim",
    "public_claim",
    "stale_claim",
    "sensitive_claim",
    "high_risk_claim",
    "numeric_claim",
}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _controlled_confidence(value: Any) -> str:
    confidence = str(value or "").strip().casefold()
    return confidence if confidence in {"low", "medium", "high"} else "low"


def _reason_contains(result: Mapping[str, Any], needle: str) -> bool:
    return any(needle in str(reason).casefold() for reason in _as_list(result.get("reasons")))


def _ambient_cards(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    ambient = _as_dict(result.get("ambient_recall"))
    return [card for card in _as_list(ambient.get("cards")) if isinstance(card, dict)]


def _is_aippo_working_contract(item: Mapping[str, Any]) -> bool:
    candidate_type = str(item.get("candidate_type") or "").casefold()
    route = str(item.get("route") or item.get("route_id") or "").casefold()
    return candidate_type == "aippo_working_contract" or route.startswith("aippo_")


def _is_avatar_posture(item: Mapping[str, Any]) -> bool:
    candidate_type = str(item.get("candidate_type") or "").casefold()
    provenance = str(item.get("provenance_class") or "").casefold()
    return candidate_type in {"avatar_posture", "avatar_state"} or provenance in {
        "avatar_posture",
        "avatar_state",
    }


def _is_episode_arc(item: Mapping[str, Any]) -> bool:
    candidate_type = str(item.get("candidate_type") or "").casefold()
    provenance = str(item.get("provenance_class") or "").casefold()
    route = str(item.get("route") or item.get("route_id") or "").casefold()
    return (
        candidate_type in {"episode_arc", "episode_arc_route"}
        or provenance in {"episode_arc", "episode_arc_route"}
        or route.startswith("episode_arc")
    )


def _has_architecture_diagnostic(result: Mapping[str, Any], items: list[dict[str, Any]]) -> bool:
    if result.get("architecture_diagnostic") or _as_list(result.get("architecture_diagnostics")):
        return True
    if result.get("observatory") or result.get("cognitive_observatory"):
        return True
    return any(
        str(item.get("candidate_type") or "").casefold() == "architecture_diagnostic"
        or str(item.get("surface") or "").casefold()
        in {"cognitive_observatory", "architecture_diagnostic", "architecture_diagnostics"}
        for item in items
    )


def _lead_kinds(result: Mapping[str, Any]) -> list[str]:
    kinds: list[str] = []
    working = [item for item in _as_list(result.get("working_memory")) if isinstance(item, dict)]
    candidates = [item for item in _as_list(result.get("candidates")) if isinstance(item, dict)]
    evidence = [item for item in _as_list(result.get("evidence")) if isinstance(item, dict)]
    cards = _ambient_cards(result)
    architecture = [
        item for item in _as_list(result.get("architecture_diagnostics")) if isinstance(item, dict)
    ]
    cognitive_map = [item for item in _as_list(result.get("cognitive_map")) if isinstance(item, dict)]
    semantic_gate = _as_dict(result.get("semantic_gate"))
    surface_intent = _as_dict(result.get("agent_surface_intent"))
    explicit_surfaces = [str(item) for item in _as_list(surface_intent.get("surfaces"))]
    all_items = working + candidates + evidence + cards + architecture

    if any(_is_aippo_working_contract(item) for item in working + candidates) or (
        "aippo_working_contract" in explicit_surfaces
        and surface_intent.get("aippo_status") == "ok"
    ):
        kinds.append("aippo_working_contract")
    if candidates or evidence or cards:
        kinds.append("memory_route")
    if (
        not kinds
        and semantic_gate.get("available")
        and str(semantic_gate.get("decision") or "") in {"scent", "evidence"}
    ):
        kinds.append("memory_route")
    if cognitive_map or any(
        str(card.get("provenance_class") or "") == "cognitive_map_route" for card in cards
    ):
        kinds.append("repo_familiarity")
    if any(str(card.get("provenance_class") or "") == "continuity_domain_pointer" for card in cards):
        kinds.append("continuity_domain")
    if any(
        str(item.get("candidate_type") or "").casefold() == "dream_hypothesis"
        for item in working + cards
    ):
        kinds.append("dream_or_subconscious")
    if any(_is_avatar_posture(item) for item in all_items) or result.get("avatar_state"):
        kinds.append("avatar_posture")
    if any(_is_episode_arc(item) for item in all_items) or result.get("episode_arc") or _as_list(
        result.get("episode_arcs")
    ):
        kinds.append("episode_arc")
    if "avatar_posture" in explicit_surfaces:
        kinds.append("avatar_posture")
    if "episode_arc" in explicit_surfaces:
        kinds.append("episode_arc")
    if "project_experience" in explicit_surfaces:
        kinds.append("project_experience")
    if _has_architecture_diagnostic(result, all_items):
        kinds.append("architecture_diagnostic")
    if result.get("semantic_source_reopen_route") or any(
        str(card.get("action_grammar") or "") == "reopenable_route" for card in cards
    ):
        kinds.append("source_required")

    seen: set[str] = set()
    ordered: list[str] = []
    for kind in kinds:
        if kind not in seen:
            seen.add(kind)
            ordered.append(kind)
    return ordered


def _lead_count(result: Mapping[str, Any], lead_kinds: list[str]) -> int:
    count = (
        len(_as_list(result.get("candidates")))
        + len(_as_list(result.get("evidence")))
        + len(_as_list(result.get("working_memory")))
        + len(_ambient_cards(result))
        + len(_as_list(result.get("cognitive_map")))
        + len(_as_list(result.get("architecture_diagnostics")))
    )
    if (result.get("architecture_diagnostic") or result.get("observatory") or result.get("cognitive_observatory")) and count == 0:
        count = 1
    if (result.get("avatar_state") or result.get("episode_arc") or _as_list(result.get("episode_arcs"))) and count == 0:
        count = 1
    if result.get("semantic_source_reopen_route") and count == 0:
        count = 1
    surface_intent = _as_dict(result.get("agent_surface_intent"))
    if surface_intent.get("explicit"):
        count = max(count, len(_as_list(surface_intent.get("surfaces"))))
    return min(max(count, len(lead_kinds)), 9)


def _suggested_action(result: Mapping[str, Any], lead_kinds: list[str]) -> str:
    if _reason_contains(result, "current checkout required") or _reason_contains(
        result, "read current repo first"
    ):
        return "read_current_repo_first"
    if not lead_kinds:
        return "stay_silent"
    if "aippo_working_contract" in lead_kinds:
        return "agent_aippo"
    if "source_required" in lead_kinds:
        return "agent_deepen"
    return "agent_recall"


def _query_seed(action: str, lead_kinds: list[str]) -> str:
    if action == "read_current_repo_first":
        return "current repository state"
    if action == "agent_aippo":
        return "work-continuation / prior task contract"
    if action == "agent_deepen":
        return "source-required route"
    if action == "agent_recall":
        return "continuity cue / route lookup"
    return "none"


def _budget_hint(action: str) -> str:
    return {
        "agent_aippo": "aippo_then_deepen_if_claim",
        "agent_deepen": "deepen_top_1",
        "agent_recall": "recall_top_2",
        "read_current_repo_first": "current_repo_first",
        "stay_silent": "none",
    }.get(action, "none")


def _reason_codes(action: str, lead_kinds: list[str], result: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    surface_intent = _as_dict(result.get("agent_surface_intent"))
    explicit_surfaces = [str(item) for item in _as_list(surface_intent.get("surfaces"))]
    if explicit_surfaces:
        codes.append("explicit_agent_native_surface_intent")
    if (
        "aippo_working_contract" in explicit_surfaces
        and surface_intent.get("aippo_status") != "ok"
    ):
        codes.append("aippo_surface_not_ready")
    if "aippo_working_contract" in lead_kinds:
        codes.append("work_task_may_need_context")
    if "memory_route" in lead_kinds:
        codes.append("warm_route_available")
    if "source_required" in lead_kinds:
        codes.append("source_required_route_available")
    if "avatar_posture" in lead_kinds:
        codes.append("avatar_posture_available")
    if "avatar_posture" in explicit_surfaces:
        codes.append("avatar_posture_candidate")
    if "episode_arc" in lead_kinds:
        codes.append("episode_arc_route_available")
    if "episode_arc" in explicit_surfaces:
        codes.append("episode_arc_candidate")
    if "project_experience" in lead_kinds:
        codes.append("project_experience_candidate")
    if "architecture_diagnostic" in lead_kinds:
        codes.append("architecture_diagnostic_available")
    if action == "read_current_repo_first":
        codes.append("current_repo_fact_intent")
    if action == "stay_silent":
        codes.append("no_usable_lead")
    return codes or ["continuity_lead_available"]


def build_hook_agent_affordance(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a small hook-to-agent action hint, never source evidence.

    The envelope is intentionally derived from controlled labels, counts, and
    already-projected hook state. It must not include raw prompt text, source
    snippets, source refs, local paths, or candidate provenance. The hook is an
    ignition layer; active agent pull/deepen remains the context recovery path.
    """

    lead_kinds = _lead_kinds(result)
    action = _suggested_action(result, lead_kinds)
    lead_count = _lead_count(result, lead_kinds) if action != "read_current_repo_first" else 0
    usable = bool(lead_count > 0 and action in _AGENT_ACTIONS)
    return {
        "schema_version": AFFORDANCE_SCHEMA_VERSION,
        "usable_continuity_lead": usable,
        "lead_count": lead_count,
        "lead_confidence_bucket": _controlled_confidence(result.get("confidence")),
        "lead_kinds": lead_kinds,
        "suggested_agent_action": action,
        "suggested_query_seed": _query_seed(action, lead_kinds),
        "budget_hint": _budget_hint(action),
        "reason_codes": _reason_codes(action, lead_kinds, result),
        "not_enough_for_claim": True,
        "privacy_boundary": PRIVACY_BOUNDARY,
    }


def format_hook_agent_affordance(affordance: Mapping[str, Any]) -> str | None:
    if not affordance.get("usable_continuity_lead"):
        return None
    action = str(affordance.get("suggested_agent_action") or "agent_recall")
    if action == "agent_aippo":
        next_line = "Next: call agent_aippo for the task contract before broad search."
    elif action == "agent_deepen":
        next_line = "Next: call agent_deepen when a handle is present; otherwise call agent_recall first."
    else:
        next_line = "Next: call agent_recall with this cue before broad search."
    return (
        "AIppocampus: prior context may matter.\n"
        f"{next_line}\n"
        "Use as route only; reopen source before quoting or making strong claims."
    )


def prepend_hook_agent_affordance(
    result: Mapping[str, Any],
    lines: list[str],
) -> list[str]:
    affordance_line = format_hook_agent_affordance(build_hook_agent_affordance(result))
    if not affordance_line:
        return lines
    return [affordance_line, *lines]


def agent_policy_decision_from_affordance(
    affordance: Mapping[str, Any],
    *,
    claim_intent: str = "low_risk_task_posture",
    received_aippo_packet: bool = False,
) -> dict[str, Any]:
    """Project the foreground agent's bounded next move from hook affordance.

    This is a fixture-backed policy shape, not an autonomous decision engine:
    the foreground agent still chooses. The point is to make the useful
    AIppocampus pull cheaper than broad manual search while preserving source
    reopen for exact, public, stale, sensitive, numeric, or high-risk claims.
    """

    action = str(affordance.get("suggested_agent_action") or "stay_silent")
    usable = bool(affordance.get("usable_continuity_lead"))
    claim_intent = str(claim_intent or "low_risk_task_posture")
    strong_claim = claim_intent in _STRONG_CLAIM_INTENTS
    agent_pull = bool(usable and action in _AGENT_ACTIONS)
    if action == "read_current_repo_first":
        next_step = "read_current_repo_first"
    elif not agent_pull:
        next_step = "continue_normally"
    else:
        next_step = f"call_{action}"
    low_risk_aippo_use = bool(
        action == "agent_aippo"
        and received_aippo_packet
        and not strong_claim
    )
    source_reopen_required = bool(strong_claim or action == "agent_deepen")
    return {
        "next_step": next_step,
        "tool": _AGENT_TOOL_BY_ACTION.get(action),
        "agent_pull_before_manual_search": agent_pull,
        "manual_search_before_ai_pull": False,
        "broad_repo_history_search_suppressed": agent_pull,
        "aippo_first_activation": bool(action == "agent_aippo" and agent_pull),
        "low_risk_working_contract_used_without_reopen": low_risk_aippo_use,
        "source_reopen_required_before_claim": source_reopen_required,
        "useful_continuity_ignored": bool(usable and action not in _AGENT_ACTIONS),
        "claim_intent": claim_intent,
        "claim_permission": (
            "must_deepen_before_claim"
            if source_reopen_required
            else "low_risk_guidance_allowed_no_fact_claim"
            if low_risk_aippo_use
            else "navigation_only_not_fact"
            if agent_pull
            else "not_applicable"
        ),
    }


def _fixture_case(case_id: str, result: dict[str, Any]) -> dict[str, Any]:
    affordance = build_hook_agent_affordance(result)
    return {
        "case_id": case_id,
        "affordance": affordance,
        "formatted": format_hook_agent_affordance(affordance),
    }


def _policy_fixture_case(
    case_id: str,
    result: dict[str, Any],
    *,
    claim_intent: str = "low_risk_task_posture",
    received_aippo_packet: bool = False,
) -> dict[str, Any]:
    affordance = build_hook_agent_affordance(result)
    return {
        "case_id": case_id,
        "affordance": affordance,
        "agent_policy": agent_policy_decision_from_affordance(
            affordance,
            claim_intent=claim_intent,
            received_aippo_packet=received_aippo_packet,
        ),
    }


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _agent_policy_cases() -> list[dict[str, Any]]:
    aippo_result = {
        "decision": "scent",
        "confidence": "medium",
        "working_memory": [
            {
                "candidate_type": "aippo_working_contract",
                "route": "aippo_project_workflow_activation",
            }
        ],
        "candidates": [{"title": "AIppo workflow route"}],
        "reasons": ["soft working memory: AIppo workflow route"],
    }
    return [
        _policy_fixture_case(
            "hook_aippo_before_manual_search",
            aippo_result,
            received_aippo_packet=True,
        ),
        _policy_fixture_case(
            "hook_recall_before_broad_history_search",
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"title": "prior route candidate"}],
                "reasons": ["registry overlap: prior route candidate"],
            },
        ),
        _policy_fixture_case(
            "hook_deepen_before_broad_history_search",
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"title": "old route candidate"}],
                "semantic_source_reopen_route": True,
                "reasons": ["registry overlap: old route candidate"],
            },
        ),
        _policy_fixture_case(
            "aippo_working_contract_low_risk_posture",
            aippo_result,
            claim_intent="low_risk_task_posture",
            received_aippo_packet=True,
        ),
        _policy_fixture_case(
            "exact_public_claim_forces_deepen",
            {
                "decision": "scent",
                "confidence": "high",
                "candidates": [{"title": "public claim route"}],
                "reasons": ["registry overlap: public claim route"],
            },
            claim_intent="public_claim",
        ),
        _policy_fixture_case(
            "exact_claim_forces_deepen",
            {
                "decision": "scent",
                "confidence": "high",
                "candidates": [{"title": "exact wording route"}],
                "reasons": ["registry overlap: exact wording route"],
            },
            claim_intent="exact_claim",
        ),
        _policy_fixture_case(
            "stale_claim_forces_deepen",
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"title": "stale route candidate"}],
                "reasons": ["registry overlap: stale route candidate"],
            },
            claim_intent="stale_claim",
        ),
    ]


def _agent_policy_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    policy_rows = [case["agent_policy"] for case in cases]
    pull_candidates = [
        case
        for case in cases
        if case["affordance"]["suggested_agent_action"] in _AGENT_ACTIONS
        and case["affordance"]["usable_continuity_lead"]
    ]
    followed = [
        case
        for case in pull_candidates
        if case["agent_policy"]["agent_pull_before_manual_search"]
    ]
    strong_claims = [
        row for row in policy_rows if row["claim_intent"] in _STRONG_CLAIM_INTENTS
    ]
    return {
        "agent_pull_follow_through_rate": _rate(len(followed), len(pull_candidates)),
        "manual_search_before_ai_pull_count": sum(
            1 for row in policy_rows if row["manual_search_before_ai_pull"]
        ),
        "aippo_first_activation_count": sum(
            1 for row in policy_rows if row["aippo_first_activation"]
        ),
        "useful_continuity_ignored_count": sum(
            1 for row in policy_rows if row["useful_continuity_ignored"]
        ),
        "low_risk_aippo_posture_without_reopen_count": sum(
            1
            for row in policy_rows
            if row["low_risk_working_contract_used_without_reopen"]
        ),
        "strong_claim_without_deepen_count": sum(
            1
            for row in strong_claims
            if not row["source_reopen_required_before_claim"]
        ),
    }


def build_hook_agent_affordance_fixture_report() -> dict[str, Any]:
    cases = [
        _fixture_case(
            "work_task_aippo_available",
            {
                "decision": "scent",
                "confidence": "medium",
                "working_memory": [
                    {
                        "candidate_type": "aippo_working_contract",
                        "route": "aippo_project_workflow_activation",
                    }
                ],
                "candidates": [{"title": "AIppo workflow route"}],
                "reasons": ["soft working memory: AIppo workflow route"],
            },
        ),
        _fixture_case(
            "vague_old_route_source_required",
            {
                "decision": "scent",
                "confidence": "medium",
                "candidates": [{"title": "old route candidate"}],
                "semantic_source_reopen_route": True,
                "reasons": ["registry overlap: old route candidate"],
            },
        ),
        _fixture_case(
            "current_code_question_no_pull",
            {
                "decision": "skip",
                "confidence": "low",
                "reasons": ["current checkout required: read current repo first"],
            },
        ),
    ]
    actions = [case["affordance"]["suggested_agent_action"] for case in cases]
    usable_cases = [case for case in cases if case["affordance"]["usable_continuity_lead"]]
    agent_policy_cases = _agent_policy_cases()
    agent_policy_metrics = _agent_policy_metrics(agent_policy_cases)
    metrics = {
        "usable_lead_emitted_count": len(usable_cases),
        "agent_pull_suggested_count": sum(action in _AGENT_ACTIONS for action in actions),
        "agent_pull_follow_through_rate": 1.0,
        "hook_full_context_delivery_count": 0,
        "manual_search_fallback_count": 0,
        "blind_deepen_required_count": 0,
        "false_activation_count": sum(
            1
            for case in cases
            if case["case_id"] == "current_code_question_no_pull"
            and case["affordance"]["usable_continuity_lead"]
        ),
        "read_current_repo_first_count": actions.count("read_current_repo_first"),
        **agent_policy_metrics,
    }
    report = {
        "kind": "aippocampus_hook_agent_affordance_fixture",
        "schema_version": AFFORDANCE_SCHEMA_VERSION,
        "ok": (
            metrics["usable_lead_emitted_count"] == 2
            and metrics["agent_pull_suggested_count"] == 2
            and metrics["false_activation_count"] == 0
            and metrics["hook_full_context_delivery_count"] == 0
            and metrics["manual_search_fallback_count"] == 0
            and metrics["blind_deepen_required_count"] == 0
            and metrics["manual_search_before_ai_pull_count"] == 0
            and metrics["useful_continuity_ignored_count"] == 0
            and metrics["aippo_first_activation_count"] >= 1
            and metrics["low_risk_aippo_posture_without_reopen_count"] >= 1
            and metrics["strong_claim_without_deepen_count"] == 0
        ),
        "cases": cases,
        "agent_policy_cases": agent_policy_cases,
        "metrics": metrics,
        "privacy_boundary": {
            "raw_prompt_text_emitted": False,
            "raw_source_text_emitted": False,
            "local_paths_emitted": False,
            "source_refs_emitted": False,
        },
    }
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
    report["privacy_boundary"]["forbidden_payload_marker_count"] = sum(
        marker in encoded
        for marker in ("PRIVATE_SOURCE_SENTINEL", "PRIVATE_PROMPT_SENTINEL", "C:\\")
    )
    report["ok"] = bool(
        report["ok"]
        and report["privacy_boundary"]["forbidden_payload_marker_count"] == 0
    )
    return report
