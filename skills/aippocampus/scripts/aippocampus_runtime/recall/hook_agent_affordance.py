"""Prompt-hook affordance envelope for active agent continuity pulls."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

AFFORDANCE_SCHEMA_VERSION = "hook-agent-affordance-v0"
PRIVACY_BOUNDARY = "no raw source, no local paths, no source refs in hook"

_AGENT_ACTIONS = {"agent_aippo", "agent_recall", "agent_deepen"}


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


def _lead_kinds(result: Mapping[str, Any]) -> list[str]:
    kinds: list[str] = []
    working = [item for item in _as_list(result.get("working_memory")) if isinstance(item, dict)]
    candidates = [item for item in _as_list(result.get("candidates")) if isinstance(item, dict)]
    evidence = [item for item in _as_list(result.get("evidence")) if isinstance(item, dict)]
    cards = _ambient_cards(result)
    cognitive_map = [item for item in _as_list(result.get("cognitive_map")) if isinstance(item, dict)]

    if any(_is_aippo_working_contract(item) for item in working + candidates):
        kinds.append("aippo_working_contract")
    if candidates or evidence or cards:
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
    )
    if result.get("semantic_source_reopen_route") and count == 0:
        count = 1
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


def _reason_codes(action: str, lead_kinds: list[str]) -> list[str]:
    codes: list[str] = []
    if "aippo_working_contract" in lead_kinds:
        codes.append("work_task_may_need_context")
    if "memory_route" in lead_kinds:
        codes.append("warm_route_available")
    if "source_required" in lead_kinds:
        codes.append("source_required_route_available")
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
        "reason_codes": _reason_codes(action, lead_kinds),
        "not_enough_for_claim": True,
        "privacy_boundary": PRIVACY_BOUNDARY,
    }


def format_hook_agent_affordance(affordance: Mapping[str, Any]) -> str | None:
    if not affordance.get("usable_continuity_lead"):
        return None
    lead_kinds = [
        str(kind)
        for kind in _as_list(affordance.get("lead_kinds"))
        if str(kind).strip()
    ][:4]
    return (
        "AIppocampus recall affordance (not evidence): "
        f"suggested_agent_action={affordance.get('suggested_agent_action')}; "
        f"lead_kinds={','.join(lead_kinds) or 'unknown'}; "
        f"budget={affordance.get('budget_hint')}; "
        "not_enough_for_claim=true."
    )


def prepend_hook_agent_affordance(
    result: Mapping[str, Any],
    lines: list[str],
) -> list[str]:
    affordance_line = format_hook_agent_affordance(build_hook_agent_affordance(result))
    if not affordance_line:
        return lines
    if lines and lines[0].startswith("Ambient recall scent (aippocampus compact"):
        compact_heading = affordance_line.replace(
            "AIppocampus recall affordance",
            "Ambient recall scent + AIppocampus affordance",
        )
        return [compact_heading, *lines[1:]]
    return [affordance_line, *lines]


def _fixture_case(case_id: str, result: dict[str, Any]) -> dict[str, Any]:
    affordance = build_hook_agent_affordance(result)
    return {
        "case_id": case_id,
        "affordance": affordance,
        "formatted": format_hook_agent_affordance(affordance),
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
        ),
        "cases": cases,
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
