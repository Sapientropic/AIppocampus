"""Cross-agent recall isolation hard-negative fixtures for #1135.

This module models the shared read-path boundary that search, recall, deepen,
hot-cache, semantic sidecar, and cached-summary surfaces must apply before they
emit memory-like material. It is deliberately fixture-backed: it proves the
contract shape and red-line counters without claiming enterprise authorization
or benchmarking a live external memory system.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "cross-agent-recall-isolation-v0"
READ_PATHS = {
    "search_memory",
    "recall_context",
    "recall_deepen",
    "prompt_hot_path",
    "semantic_sidecar",
    "cached_summary",
}
PUBLIC_SAFE_FORBIDDEN_MARKERS = (
    "AGENT_A_PRIVATE_SOURCE_SENTINEL",
    "AGENT_B_PRIVATE_SOURCE_SENTINEL",
    "raw_private_source_text",
    "C:\\",
    "/Users/",
)


def stable_hash(*parts: Any, length: int = 16) -> str:
    digest = hashlib.sha256("\u241f".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return digest[:length]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _scope(case: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = case.get(key)
    return value if isinstance(value, Mapping) else {}


def _is_same_private_scope(request: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    return (
        _text(source.get("sharing")) == "private"
        and _text(request.get("provider")) == _text(source.get("provider"))
        and _text(request.get("agent_id")) == _text(source.get("agent_id"))
    )


def _is_declared_shared_scope(request: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    allowed_projects = set(_strings(source.get("shared_scope_ids")))
    allowed_agents = set(_strings(source.get("allowed_agent_ids")))
    project_scope_id = _text(request.get("project_scope_id"))
    agent_id = _text(request.get("agent_id"))
    return (
        _text(source.get("sharing")) == "shared_project"
        and project_scope_id in allowed_projects
        and agent_id in allowed_agents
    )


def scope_allows_source(case: Mapping[str, Any]) -> bool:
    request = _scope(case, "request_scope")
    source = _scope(case, "source_scope")
    return _is_same_private_scope(request, source) or _is_declared_shared_scope(request, source)


def _sanitized_source_handle(case: Mapping[str, Any]) -> dict[str, Any]:
    source = _scope(case, "source_scope")
    return {
        "source_ref_hash": stable_hash(
            source.get("provider"),
            source.get("agent_id"),
            source.get("sharing"),
            case.get("marker_hash"),
        ),
        "reopenable": bool(case.get("source_reopenable", True)),
        "scope_boundary": _text(source.get("sharing")) or "private",
    }


def _blocked_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "aippocampus_scope_isolation_read_result",
        "schema_version": SCHEMA_VERSION,
        "case_id": _text(case.get("case_id")) or "case",
        "read_path": _text(case.get("read_path")) or "unknown",
        "decision": "blocked",
        "output_mode": "ignore_or_blocked",
        "claim_permission": "blocked",
        "next_action": "stay_silent",
        "blocked_reason_codes": ["cross_agent_scope"],
        "candidate_marker_hash": _text(case.get("marker_hash")),
        "source_handle_count": 0,
        "public_safe": True,
    }


def _allowed_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    read_path = _text(case.get("read_path")) or "unknown"
    handle = _sanitized_source_handle(case)
    result = {
        "kind": "aippocampus_scope_isolation_read_result",
        "schema_version": SCHEMA_VERSION,
        "case_id": _text(case.get("case_id")) or "case",
        "read_path": read_path,
        "decision": "allowed",
        "output_mode": "reopenable_route",
        "claim_permission": "no_claim_before_reopen",
        "next_action": "reopen_source",
        "route_id": "route:" + stable_hash("route", case.get("case_id")),
        "source_handles": [handle],
        "source_handle_count": 1,
        "public_safe": True,
    }
    if read_path == "search_memory":
        result["output_mode"] = "scent"
        result["next_action"] = "use_hint"
    if read_path == "recall_deepen":
        result["status"] = "source_route"
    return result


def _leaky_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return the shape a missed scope filter would have leaked.

    This is used only by tests that intentionally construct a violating case so
    the red-line counters prove they can catch a bypass.
    """

    result = _allowed_projection(case)
    result["decision"] = "leaked"
    result["leak_simulation"] = True
    return result


def evaluate_scope_read_case(case: Mapping[str, Any]) -> dict[str, Any]:
    allowed = scope_allows_source(case)
    would_match_without_filter = bool(case.get("would_match_without_scope_filter"))
    if not allowed and bool(case.get("simulate_filter_bypass")):
        result = _leaky_projection(case)
    elif not allowed:
        result = _blocked_projection(case)
    else:
        result = _allowed_projection(case)

    route_leak = int(not allowed and "route_id" in result)
    source_leak = int(not allowed and int(result.get("source_handle_count") or 0) > 0)
    recall_leak = int(
        not allowed
        and _text(result.get("output_mode")) not in {"ignore_or_blocked", "silence"}
    )
    evidence_leak = int(
        not allowed
        and _text(result.get("claim_permission")) in {"bounded_claim_allowed", "source_open"}
    )
    result["scope_allowed"] = allowed
    result["would_match_without_scope_filter"] = would_match_without_filter
    result["blocked_scope_hit_count"] = int(not allowed and result["decision"] == "blocked")
    result["fast_path_bypass_prevented_count"] = int(
        not allowed and would_match_without_filter and result["decision"] == "blocked"
    )
    result["cross_scope_recall_leak_count"] = recall_leak
    result["cross_scope_route_leak_count"] = route_leak
    result["cross_scope_evidence_leak_count"] = evidence_leak + source_leak
    return result


def fixture_cases() -> list[dict[str, Any]]:
    agent_a_private = {
        "provider": "codex",
        "agent_id": "agent_a",
        "sharing": "private",
    }
    shared_project = {
        "provider": "codex",
        "agent_id": "agent_a",
        "sharing": "shared_project",
        "shared_scope_ids": ["project:AIppocampus"],
        "allowed_agent_ids": ["agent_a", "agent_b"],
    }
    agent_b_request = {
        "provider": "codex",
        "agent_id": "agent_b",
        "project_scope_id": "project:AIppocampus",
    }
    private_marker_hash = stable_hash("AGENT_A_PRIVATE_SOURCE_SENTINEL")
    shared_marker_hash = stable_hash("SHARED_PROJECT_SYNTHETIC_MARKER")
    return [
        {
            "case_id": "agent_b_search_private_agent_a",
            "read_path": "search_memory",
            "request_scope": agent_b_request,
            "source_scope": agent_a_private,
            "marker_hash": private_marker_hash,
            "would_match_without_scope_filter": True,
        },
        {
            "case_id": "agent_b_recall_context_private_agent_a",
            "read_path": "recall_context",
            "request_scope": agent_b_request,
            "source_scope": agent_a_private,
            "marker_hash": private_marker_hash,
            "would_match_without_scope_filter": True,
        },
        {
            "case_id": "agent_b_deepen_private_agent_a",
            "read_path": "recall_deepen",
            "request_scope": agent_b_request,
            "source_scope": agent_a_private,
            "marker_hash": private_marker_hash,
            "would_match_without_scope_filter": True,
        },
        {
            "case_id": "agent_b_hot_cache_private_agent_a",
            "read_path": "prompt_hot_path",
            "request_scope": agent_b_request,
            "source_scope": agent_a_private,
            "marker_hash": private_marker_hash,
            "would_match_without_scope_filter": True,
        },
        {
            "case_id": "agent_b_semantic_sidecar_private_agent_a",
            "read_path": "semantic_sidecar",
            "request_scope": agent_b_request,
            "source_scope": agent_a_private,
            "marker_hash": private_marker_hash,
            "would_match_without_scope_filter": True,
        },
        {
            "case_id": "agent_b_cached_summary_private_agent_a",
            "read_path": "cached_summary",
            "request_scope": agent_b_request,
            "source_scope": agent_a_private,
            "marker_hash": private_marker_hash,
            "would_match_without_scope_filter": True,
        },
        {
            "case_id": "agent_b_search_shared_project",
            "read_path": "search_memory",
            "request_scope": agent_b_request,
            "source_scope": shared_project,
            "marker_hash": shared_marker_hash,
            "would_match_without_scope_filter": True,
        },
        {
            "case_id": "agent_b_deepen_shared_project",
            "read_path": "recall_deepen",
            "request_scope": agent_b_request,
            "source_scope": shared_project,
            "marker_hash": shared_marker_hash,
            "would_match_without_scope_filter": True,
        },
    ]


def build_cross_agent_isolation_report() -> dict[str, Any]:
    results = [evaluate_scope_read_case(case) for case in fixture_cases()]
    by_path = Counter(_text(result.get("read_path")) for result in results)
    metrics = {
        "case_count": len(results),
        "read_path_counts": dict(sorted(by_path.items())),
        "blocked_scope_hit_count": sum(int(result["blocked_scope_hit_count"]) for result in results),
        "allowed_shared_scope_count": sum(
            1
            for result in results
            if result["scope_allowed"] and result["decision"] == "allowed"
        ),
        "fast_path_bypass_prevented_count": sum(
            int(result["fast_path_bypass_prevented_count"]) for result in results
        ),
        "cross_scope_recall_leak_count": sum(
            int(result["cross_scope_recall_leak_count"]) for result in results
        ),
        "cross_scope_route_leak_count": sum(
            int(result["cross_scope_route_leak_count"]) for result in results
        ),
        "cross_scope_evidence_leak_count": sum(
            int(result["cross_scope_evidence_leak_count"]) for result in results
        ),
    }
    red_lines = {
        "cross_scope_recall_leak_count": metrics["cross_scope_recall_leak_count"],
        "cross_scope_route_leak_count": metrics["cross_scope_route_leak_count"],
        "cross_scope_evidence_leak_count": metrics["cross_scope_evidence_leak_count"],
    }
    encoded = json.dumps(results, ensure_ascii=False, sort_keys=True)
    return {
        "kind": "aippocampus_cross_agent_recall_isolation_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values()),
        "read_paths": sorted(READ_PATHS),
        "results": results,
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
            "enterprise_multi_tenant_authorization_complete",
            "live_agentmemory_behavior",
            "private_real_history_isolation_proven",
            "blanket_suppression_as_product_policy",
        ],
    }
