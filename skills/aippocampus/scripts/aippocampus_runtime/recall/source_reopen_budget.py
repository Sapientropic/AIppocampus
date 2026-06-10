"""Hot/warm/cold source-reopen budget fixture for #1124."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "source-reopen-budget-v0"
PATH_BUDGETS = {
    "hot": {"latency_ms_proxy": 25, "token_proxy": 120},
    "warm": {"latency_ms_proxy": 180, "token_proxy": 700},
    "cold": {"latency_ms_proxy": 1200, "token_proxy": 3200},
}
MANDATORY_REOPEN_TRIGGERS = {
    "exact_quote",
    "public_claim",
    "high_risk",
    "stale_currentness_dispute",
    "conflict_set",
    "sensitive_private",
    "code_change_depends_on_old_source_fact",
}
PUBLIC_SAFE_FORBIDDEN_MARKERS = (
    "PRIVATE_SOURCE_SENTINEL",
    "C:\\",
    "/Users/",
    "raw_source_text",
)


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _has_mandatory_trigger(case: Mapping[str, Any]) -> bool:
    return bool(MANDATORY_REOPEN_TRIGGERS.intersection(_strings(case.get("triggers"))))


def _budget_for(path: str) -> dict[str, int]:
    return dict(PATH_BUDGETS.get(path, PATH_BUDGETS["cold"]))


def classify_source_reopen_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one source-reopen decision without opening private source."""

    triggers = _strings(case.get("triggers"))
    mandatory = bool(case.get("requires_source_reopen")) or _has_mandatory_trigger(case)
    bounded_summary_allowed = bool(
        case.get("output_mode") == "bounded_summary_as_route"
        and not mandatory
        and not case.get("conflicted")
        and not case.get("stale")
        and not case.get("high_risk")
    )
    path = str(case.get("path") or "").strip()
    if not path:
        if mandatory:
            path = "cold"
        elif case.get("selected_source_span") or case.get("cheap_verifier"):
            path = "warm"
        else:
            path = "hot"

    budget = _budget_for(path)
    estimated_latency = int(case.get("estimated_latency_ms_proxy") or budget["latency_ms_proxy"])
    estimated_tokens = int(case.get("estimated_token_proxy") or budget["token_proxy"])
    timed_out = bool(case.get("foreground_hook")) and estimated_latency > budget["latency_ms_proxy"]
    timeout_fail_open = bool(timed_out and case.get("fail_open_on_timeout", True))
    attempted_full_reopen = bool(case.get("attempted_full_reopen"))
    source_reopened = bool(case.get("source_reopened"))
    attempted_claim = bool(case.get("attempted_claim"))
    unnecessary_reopen = int(attempted_full_reopen and bounded_summary_allowed)
    claim_without_reopen = int(mandatory and attempted_claim and not source_reopened)

    if timeout_fail_open:
        next_action = "fail_open_no_claim"
    elif mandatory and not source_reopened:
        next_action = "reopen_source"
    elif bounded_summary_allowed:
        next_action = "use_bounded_route"
    elif path == "warm":
        next_action = "run_cheap_verifier_or_selected_span"
    else:
        next_action = "use_within_scope"

    return {
        "case_id": str(case.get("case_id") or "case"),
        "path": path,
        "triggers": triggers,
        "source_reopen_required": mandatory,
        "bounded_summary_allowed": bounded_summary_allowed,
        "source_reopened": source_reopened,
        "next_action": next_action,
        "latency_ms_proxy": estimated_latency,
        "token_proxy": estimated_tokens,
        "timeout_fail_open": timeout_fail_open,
        "unnecessary_reopen_count": unnecessary_reopen,
        "source_backed_claim_without_reopen": claim_without_reopen,
        "claim_permission": (
            "no_claim_before_reopen"
            if mandatory and not source_reopened
            else str(case.get("claim_permission") or "no_claim_before_reopen")
        ),
        "public_safe": True,
    }


def fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "hot_bounded_summary_route",
            "path": "hot",
            "output_mode": "bounded_summary_as_route",
            "claim_permission": "no_claim_before_reopen",
            "estimated_latency_ms_proxy": 18,
            "estimated_token_proxy": 90,
        },
        {
            "case_id": "hot_verified_cached_route",
            "path": "hot",
            "output_mode": "direction_only",
            "verified_cached_route": True,
            "estimated_latency_ms_proxy": 11,
            "estimated_token_proxy": 60,
        },
        {
            "case_id": "warm_selected_span_verifier",
            "path": "warm",
            "selected_source_span": True,
            "cheap_verifier": True,
            "estimated_latency_ms_proxy": 140,
            "estimated_token_proxy": 520,
        },
        {
            "case_id": "cold_exact_quote_reopened",
            "triggers": ["exact_quote"],
            "source_reopened": True,
            "attempted_claim": True,
            "estimated_latency_ms_proxy": 980,
            "estimated_token_proxy": 2600,
            "claim_permission": "bounded_claim_allowed",
        },
        {
            "case_id": "cold_public_claim_reopen_required",
            "triggers": ["public_claim"],
            "source_reopened": False,
            "attempted_claim": False,
            "estimated_latency_ms_proxy": 900,
            "estimated_token_proxy": 2300,
        },
        {
            "case_id": "cold_stale_conflict_reopen_required",
            "triggers": ["stale_currentness_dispute", "conflict_set"],
            "source_reopened": False,
            "attempted_claim": False,
            "estimated_latency_ms_proxy": 1100,
            "estimated_token_proxy": 2800,
        },
        {
            "case_id": "hot_hook_timeout_fail_open",
            "path": "hot",
            "foreground_hook": True,
            "output_mode": "reopenable_route",
            "estimated_latency_ms_proxy": 160,
            "estimated_token_proxy": 480,
            "fail_open_on_timeout": True,
        },
    ]


def build_source_reopen_budget_report() -> dict[str, Any]:
    decisions = [classify_source_reopen_case(case) for case in fixture_cases()]
    by_path = Counter(str(decision["path"]) for decision in decisions)
    latency_by_path = {
        path: sum(int(decision["latency_ms_proxy"]) for decision in decisions if decision["path"] == path)
        for path in PATH_BUDGETS
    }
    token_by_path = {
        path: sum(int(decision["token_proxy"]) for decision in decisions if decision["path"] == path)
        for path in PATH_BUDGETS
    }
    metrics = {
        "case_count": len(decisions),
        "hot_path_case_count": by_path["hot"],
        "warm_path_case_count": by_path["warm"],
        "cold_path_case_count": by_path["cold"],
        "latency_ms_proxy_by_path": latency_by_path,
        "token_proxy_by_path": token_by_path,
        "source_reopen_required_count": sum(
            1 for decision in decisions if decision["source_reopen_required"]
        ),
        "bounded_summary_allowed_count": sum(
            1 for decision in decisions if decision["bounded_summary_allowed"]
        ),
        "timeout_fail_open_count": sum(1 for decision in decisions if decision["timeout_fail_open"]),
        "unnecessary_reopen_count": sum(
            int(decision["unnecessary_reopen_count"]) for decision in decisions
        ),
        "source_backed_claim_without_reopen": sum(
            int(decision["source_backed_claim_without_reopen"]) for decision in decisions
        ),
    }
    red_lines = {
        "unnecessary_reopen_count": metrics["unnecessary_reopen_count"],
        "source_backed_claim_without_reopen": metrics["source_backed_claim_without_reopen"],
    }
    encoded = json.dumps(decisions, ensure_ascii=False, sort_keys=True)
    return {
        "kind": "aippocampus_source_reopen_budget_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values()),
        "policy": {
            "hot": "tiny hint, bounded_summary_as_route, or verified cached route",
            "warm": "cheap verifier plus selected source span",
            "cold": "full source reopen, audit, or high-risk/public claim lane",
            "foreground_timeout": "fail_open_no_claim",
        },
        "path_budgets": PATH_BUDGETS,
        "mandatory_reopen_triggers": sorted(MANDATORY_REOPEN_TRIGGERS),
        "decisions": decisions,
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "forbidden_marker_count": sum(
                1 for marker in PUBLIC_SAFE_FORBIDDEN_MARKERS if marker in encoded
            ),
        },
        "cannot_claim": [
            "source_reopen_is_free",
            "summary_as_evidence",
            "default_hook_adoption",
            "live_latency_quality",
            "private_history_reopen_quality",
        ],
    }
