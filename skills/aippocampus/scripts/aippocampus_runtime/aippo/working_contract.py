"""Source-backed AIppo working-contract fixture.

An AIppo working contract is a compact action contract compiled from source
trails and existing navigation/candidate surfaces. Candidate surfaces may route
attention, but only source/path support can make a clause foreground-eligible.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.aippo import usefulness
from aippocampus_runtime.core import compact_text
from aippocampus_runtime.recall import authority

SCHEMA_VERSION = "aippo-working-contract-v0"
AIPPO_ID = "aippo_project_workflow_public_safe_v0"
FOREGROUND_PACKET_BYTE_BUDGET = 1100
ACTIVE_STATUSES = {"ripe"}
REOPEN_BOUNDARIES = [
    "exact_quote",
    "numeric_claim",
    "public_claim",
    "disputed_policy",
    "stale_workflow",
    "high_risk_action",
]
CANDIDATE_INPUTS = [
    "agent_self_notes",
    "cognitive_map",
    "concept_graph",
    "dream_subconscious",
    "decision_shadows",
    "repo_familiarity",
]
TRUTH_SOURCES = ["clean_source", "current_claims", "merged_test", "accepted_issue"]
NAVIGATION_SOURCES = ["cognitive_map", "concept_graph", "repo_familiarity", "pathlet", "episode_arc"]
CANDIDATE_ONLY_SOURCES = ["agent_self_note", "dream_subconscious"]
DIRECT_JOURNEY_GUIDANCE = {
    "fresh_thread_recall": {
        "next_action": "run_recall_then_deepen",
        "guidance": [
            "Run aippocampus agent recall for vague continuity cues before broad manual search.",
            "Treat route scent as navigation; deepen or reopen source before exact claims.",
        ],
    },
    "host_readiness": {
        "next_action": "verify_plugin_mcp_hooks",
        "guidance": [
            "Check plugin verify/update status, compact MCP tool visibility, and hook status before judging recall quality.",
            "Separate package freshness, host-visible tools, and current-thread availability.",
        ],
    },
    "product_workflow": {
        "next_action": "inspect_product_workflow_boundary",
        "guidance": [
            "Before changing semantic gate, attention router, or MCP health, reopen issue, test, and source diagnostics.",
            "Keep product workflow guidance public-safe: route first, then reopen exact source before claims or release notes.",
        ],
    },
}


def _text(value: Any, limit: int = 240) -> str:
    return compact_text(str(value or "").strip(), limit)


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item, 160)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _stable_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def contract_deepen_action(deepen_route_id: str) -> dict[str, Any]:
    return {
        "action_id": "deepen_aippo_working_contract",
        "tool_name": "agent_deepen",
        "arguments": {"handle": deepen_route_id},
        "claim_boundary": "source_reopen_required_before_claim",
        "authority_after_running": "source_open_within_aippo_contract_scope",
    }


def _source_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return refs
    for item in value:
        if not isinstance(item, Mapping):
            continue
        clean = {
            "source_ref": _text(item.get("source_ref"), 140),
            "path": _text(item.get("path"), 220),
            "line": item.get("line"),
            "kind": _text(item.get("kind"), 80),
        }
        refs.append({key: val for key, val in clean.items() if val not in {"", None}})
    return refs


def _support(row: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    support_grade = _text(row.get("support_grade"), 80) or "candidate_only"
    counter = int(row.get("counter_evidence_ref_count") or 0)
    path_provenance = _text(row.get("path_provenance"), 80) or "none"
    return {
        "support_grade": support_grade,
        "source_ref_count": len(refs),
        "independent_trail_count": int(row.get("independent_trail_count") or 0),
        "support_types": _strings(row.get("support_types"), limit=8),
        "counter_evidence_ref_count": counter,
        "path_provenance": path_provenance,
    }


def _lifecycle_status(row: Mapping[str, Any], support: Mapping[str, Any]) -> str:
    requested = _text(row.get("status"), 40)
    if requested in {"stale", "challenged", "quarantined", "retired", "blocked"}:
        return requested
    if (
        support.get("support_grade") == "source_supported"
        and int(support.get("source_ref_count") or 0) > 0
        and int(support.get("counter_evidence_ref_count") or 0) == 0
        and support.get("path_provenance") != "gappy"
    ):
        return "ripe"
    return requested or "growing"


def _review_state(status: str, row: Mapping[str, Any], support: Mapping[str, Any]) -> str:
    explicit = _text(row.get("review_state"), 60)
    if explicit:
        return explicit
    if status == "ripe" and support.get("support_grade") == "source_supported":
        return "machine_checked"
    return "needs_review"


def _next_action(status: str) -> str:
    return "use_hint" if status == "ripe" else "reopen_source"


def _clause_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    refs = _source_refs(row.get("source_refs"))
    support = _support(row, refs)
    status = _lifecycle_status(row, support)
    review_state = _review_state(status, row, support)
    authority_surface = authority.with_trust_fields(
        {
            "support_level": "source_required" if refs else "candidate",
            "source_refs": refs,
            "source_reopen_required": True,
            "freshness": row.get("freshness") or "current",
        }
    )
    return {
        "clause_id": _text(row.get("clause_id"), 100),
        "kind": _text(row.get("kind"), 80) or "working_conclusion",
        "scope": _text(row.get("scope"), 160) or "project_or_task_family",
        "target_fingerprint": _text(row.get("target_fingerprint"), 160),
        "path_category_fingerprint": _text(row.get("path_category_fingerprint"), 160),
        "topic_epoch": _text(row.get("topic_epoch"), 120) or "default",
        "workspace_or_environment_profile": _text(
            row.get("workspace_or_environment_profile"),
            160,
        )
        or "unknown_environment",
        "guidance": _text(row.get("guidance"), 320),
        "next_action": _text(row.get("next_action"), 100) or _next_action(status),
        "applies_when": _strings(row.get("applies_when"), limit=8),
        "does_not_apply_when": _strings(row.get("does_not_apply_when"), limit=8),
        "allowed_without_reopen_for": _strings(
            row.get("allowed_without_reopen_for"), limit=8
        ),
        "requires_reopen_for": _strings(row.get("requires_reopen_for"), limit=10)
        or list(REOPEN_BOUNDARIES),
        "support": support,
        "freshness": {
            "built_at": _text(row.get("built_at"), 40) or "2026-06-10",
            "last_source_seen_at": _text(row.get("last_source_seen_at"), 40) or "2026-06-10",
            "invalidators": _strings(row.get("invalidators"), limit=8),
        },
        "lifecycle": {
            "status": status,
            "review_state": review_state,
            "degrade_to": "working_contract" if status == "ripe" else "reopenable_route",
        },
        "activation": {
            "next_action": _text(row.get("next_action"), 100) or _next_action(status),
            "foreground_eligible": status == "ripe" and review_state in {"machine_checked", "reviewed"},
        },
        "claim_permission": (
            "working_contract_allowed_no_fact_claim"
            if status == "ripe"
            else "no_claim_before_reopen"
        ),
        "source_refs": refs,
        "authority": {
            "class": "truth_source" if support.get("support_grade") == "source_supported" else "candidate_only",
            "candidate_inputs_are_truth": False,
            "trust_level": authority_surface.get("trust_level"),
            "action_grammar": authority_surface.get("action_grammar"),
        },
    }


def build_aippo_working_contracts(source_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compile public-safe source rows into one AIppo working-contract package."""

    clauses = [_clause_from_row(row) for row in source_rows if isinstance(row, Mapping)]
    active = _active_clauses(clauses)
    package_status = "partial" if active and len(active) < len(clauses) else ("ripe" if active else "growing")
    return [
        {
            "kind": "aippo_working_contract",
            "schema_version": SCHEMA_VERSION,
            "aippo_id": AIPPO_ID,
            "contract_version": "2026-06-10.1",
            "scope": {
                "project": "AIppocampus",
                "domain": "workflow",
                "task_families": ["coding", "review", "issue_writing", "benchmark_reporting"],
                "privacy_domain": "public_safe_fixture",
                "transfer": "warn",
            },
            "package_status": package_status,
            "activation_policy": {
                "usable_for": ["planning", "patch_shape", "PR_review", "issue_writing"],
                "do_not_use_for": ["exact_quotes", "public_benchmark_claims", "private_personal_impressions"],
                "default_output_mode": "working_contract",
                "foreground_budget_bytes": FOREGROUND_PACKET_BYTE_BUDGET,
            },
            "clauses": clauses,
            "source_support_ledger_id": "aippo_support_project_workflow_v0",
            "candidate_provenance": {
                "allowed_candidate_inputs": list(CANDIDATE_INPUTS),
                "candidate_inputs_are_truth": False,
            },
            "source_authority": {
                "truth_sources": list(TRUTH_SOURCES),
                "navigation_sources": list(NAVIGATION_SOURCES),
                "candidate_only_sources": list(CANDIDATE_ONLY_SOURCES),
                "never_truth_sources": ["generated_summary", "semantic_cluster", "unreviewed_impression"],
            },
            "mvp_activation_targets": ["project_aippo_activation", "source_backed_continuity_gesture_v1"],
        }
    ]


def select_aippo_working_contract(
    contracts: Sequence[Mapping[str, Any]],
    *,
    task: str = "",
    now: str = "2026-06-10",
    max_packet_bytes: int = FOREGROUND_PACKET_BYTE_BUDGET,
) -> dict[str, Any]:
    del task, now, max_packet_bytes
    for contract in contracts:
        if isinstance(contract, Mapping) and contract.get("kind") == "aippo_working_contract":
            return dict(contract)
    return {}


def _active_clauses(clauses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for clause in clauses:
        lifecycle_raw = clause.get("lifecycle")
        activation_raw = clause.get("activation")
        lifecycle: Mapping[str, Any] = lifecycle_raw if isinstance(lifecycle_raw, Mapping) else {}
        activation: Mapping[str, Any] = (
            activation_raw if isinstance(activation_raw, Mapping) else {}
        )
        if lifecycle.get("status") in ACTIVE_STATUSES and activation.get("foreground_eligible"):
            active.append(dict(clause))
    return active


def activation_packet_from_working_contract(
    contract: Mapping[str, Any],
    *,
    task: str = "",
    max_packet_bytes: int = FOREGROUND_PACKET_BYTE_BUDGET,
) -> dict[str, Any]:
    """Project a working contract into the tiny foreground packet."""

    clauses = [clause for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    selected = usefulness.selected_active_clauses(clauses, task)
    active = _active_clauses(clauses)
    guidance = usefulness.guidance_snippets(selected)
    families = usefulness.task_families(task)
    direct_family = next(
        (family for family in families if family in DIRECT_JOURNEY_GUIDANCE),
        None,
    )
    direct_guidance = DIRECT_JOURNEY_GUIDANCE.get(direct_family or "", {})
    if not guidance and direct_guidance:
        guidance = list(direct_guidance.get("guidance") or [])
    display_hint = (
        f"AIppo {families[0]} guidance."
        if families
        else "AIppo no active contract."
    )
    packet = {
        "kind": "aippocampus_aippo_activation_packet",
        "schema_version": SCHEMA_VERSION,
        "aippo_id": contract.get("aippo_id") or AIPPO_ID,
        "output_mode": "working_contract",
        "display_hint": _text(display_hint, 80),
        "task_families": families,
        "use_guidance": guidance,
        "allowed_without_reopen": ["planning", "patch_shape", "review", *families],
        "requires_reopen_for": ["exact_or_public_claim", "disputed_or_stale", "high_risk"],
        "active_clause_count": len(selected),
        "available_active_clause_count": len(active),
        "suppressed_clause_count": len(clauses) - len(active),
        "active_clause_ids": [clause["clause_id"] for clause in selected],
        "claim_permission": "working_contract_allowed_no_fact_claim",
        "next_action": (
            str(direct_guidance.get("next_action"))
            if direct_guidance
            else "use_hint"
            if selected
            else "stay_silent"
        ),
        "deepen_route_id": f"deepen:{contract.get('aippo_id') or AIPPO_ID}",
    }
    packet["contract_action"] = contract_deepen_action(str(packet["deepen_route_id"]))
    if not families:
        packet["no_active_contract_reason"] = (
            "no_task_family_match"
            if str(task or "").strip()
            else "no_task_hint"
        )
        packet["next_safe_action"] = "run_agent_recall_if_prior_source_matters"
    if _json_bytes(packet) <= max_packet_bytes:
        return packet
    compact = dict(packet)
    active_ids = compact.get("active_clause_ids")
    trimmed_ids: list[Any] = active_ids[:1] if isinstance(active_ids, list) else []
    compact["display_hint"] = _text(display_hint, 80)
    compact["task_families"] = families[:1]
    compact.pop("allowed_without_reopen", None)
    compact.pop("available_active_clause_count", None)
    compact.pop("suppressed_clause_count", None)
    compact["active_clause_ids"] = trimmed_ids
    compact["active_clause_count"] = len(trimmed_ids)
    use_guidance = compact.get("use_guidance")
    compact["use_guidance"] = use_guidance[:1] if isinstance(use_guidance, list) else []
    if _json_bytes(compact) <= max_packet_bytes:
        return compact
    compact_guidance = compact.get("use_guidance")
    guidance_items = compact_guidance if isinstance(compact_guidance, list) else []
    compact["use_guidance"] = [_text(item, 96) for item in guidance_items if isinstance(item, str)]
    if _json_bytes(compact) <= max_packet_bytes:
        return compact
    compact.pop("requires_reopen_for", None)
    if _json_bytes(compact) <= max_packet_bytes:
        return compact
    compact_guidance = compact.get("use_guidance")
    guidance_items = compact_guidance if isinstance(compact_guidance, list) else []
    compact["use_guidance"] = [_text(item, 64) for item in guidance_items if isinstance(item, str)]
    compact.pop("contract_action", None)
    return compact


def deepen_aippo_working_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    clauses = [dict(clause) for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    active_clause_ids = {clause["clause_id"] for clause in _active_clauses(clauses)}
    refs_by_key: dict[str, dict[str, Any]] = {}
    for clause in clauses:
        if clause.get("clause_id") not in active_clause_ids:
            continue
        for ref in clause.get("source_refs") or []:
            if not isinstance(ref, Mapping):
                continue
            key = str(ref.get("source_ref") or ref.get("path") or "")
            if key:
                refs_by_key[key] = dict(ref)
    suppressed_ref_count = sum(
        len(clause.get("source_refs") or [])
        for clause in clauses
        if clause.get("clause_id") not in active_clause_ids
    )
    return {
        "kind": "aippocampus_aippo_deepen_surface",
        "schema_version": SCHEMA_VERSION,
        "aippo_id": contract.get("aippo_id") or AIPPO_ID,
        "source_support_ledger": {
            "ledger_id": contract.get("source_support_ledger_id"),
            "source_ref_count": len(refs_by_key),
            "source_refs": list(refs_by_key.values()),
            "suppressed_source_ref_count": suppressed_ref_count,
            "path_provenance_clause_count": sum(1 for clause in clauses if clause.get("support", {}).get("path_provenance") not in {"", "none"}),
        },
        "candidate_provenance": dict(contract.get("candidate_provenance") or {}),
        "suppressed_clause_ids": [
            clause["clause_id"]
            for clause in clauses
            if clause.get("lifecycle", {}).get("status") not in ACTIVE_STATUSES
        ],
    }


def explain_aippo_working_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    clauses = [dict(clause) for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    return {
        "kind": "aippocampus_aippo_explain_surface",
        "schema_version": SCHEMA_VERSION,
        "aippo_id": contract.get("aippo_id") or AIPPO_ID,
        "reason_codes": [
            "source_supported_clauses_foreground_eligible",
            "candidate_surfaces_are_navigation_not_truth",
            "stale_or_challenged_clauses_degrade_to_reopenable_route",
        ],
        "active_clause_count": len(_active_clauses(clauses)),
        "suppressed_clause_count": len(clauses) - len(_active_clauses(clauses)),
        "next_safe_action": "use_hint" if _active_clauses(clauses) else "stay_silent",
        "cannot_claim": [
            "aippo_marketplace_readiness",
            "private_ficus_handling",
            "claim_ready_facts_without_source_reopen",
        ],
    }


def _fixture_source_rows() -> list[dict[str, Any]]:
    shared_reopen = list(REOPEN_BOUNDARIES)
    return [
        {
            "clause_id": "clause_keep_changes_scoped",
            "kind": "workflow_default",
            "guidance": "Keep implementation slices narrow and avoid closing broad product claims from tiny fixture work.",
            "applies_when": ["coding", "issue_closeout", "PR_review"],
            "does_not_apply_when": ["explicit_user_requests_broad_design_only"],
            "allowed_without_reopen_for": ["low_risk_orientation", "patch_planning"],
            "requires_reopen_for": shared_reopen,
            "support_grade": "source_supported",
            "source_refs": [
                {"source_ref": "issue:#1131", "path": "issues/1131", "kind": "accepted_issue"},
                {"source_ref": "issue:#1130", "path": "issues/1130", "kind": "accepted_issue"},
                {"source_ref": "doc:agent-native-recall-facade", "path": "docs/architecture/recall/agent-native-recall-facade.md", "line": 43},
            ],
            "independent_trail_count": 2,
            "support_types": ["accepted_issue_pattern", "current_claim_boundary", "test_acceptance"],
            "path_provenance": "complete",
            "invalidators": ["newer_policy_issue", "conflicting_review_convention"],
        },
        {
            "clause_id": "clause_run_focused_verification",
            "kind": "verification_default",
            "guidance": "Run focused deterministic verification before claiming the slice is ready.",
            "applies_when": ["coding", "PR_review"],
            "allowed_without_reopen_for": ["low_risk_orientation", "patch_planning"],
            "requires_reopen_for": shared_reopen,
            "support_grade": "source_supported",
            "source_refs": [
                {"source_ref": "doc:public-api", "path": "docs/guides/public-api.md", "line": 489},
                {"source_ref": "doc:retrieval-storage", "path": "skills/aippocampus/references/retrieval-and-storage.md", "line": 314},
                {"source_ref": "test:agent-pull-gesture", "path": "tests/aippocampus/test_agent_pull_gesture.py"},
            ],
            "independent_trail_count": 2,
            "support_types": ["merged_test", "current_claim_boundary"],
            "path_provenance": "complete",
            "invalidators": ["newer_verification_policy"],
        },
        {
            "clause_id": "clause_preserve_useful_result_claims",
            "kind": "benchmark_reporting",
            "guidance": "Use measured results, supports, limits; keep cannot_claim short.",
            "applies_when": ["benchmark_reporting", "issue_writing", "PR_review"],
            "allowed_without_reopen_for": ["low_risk_orientation", "report_drafting"],
            "requires_reopen_for": shared_reopen,
            "support_grade": "source_supported",
            "source_refs": [
                {"source_ref": "issue:#1183", "path": "issues/1183", "kind": "accepted_issue"},
                {"source_ref": "doc:current-claims", "path": "docs/evidence/current-claims.md"},
            ],
            "independent_trail_count": 2,
            "support_types": ["accepted_issue_pattern", "current_claim_boundary"],
            "path_provenance": "complete",
            "invalidators": ["newer_reporting_policy"],
        },
        {
            "clause_id": "clause_benchmark_default_claim",
            "kind": "claim_boundary",
            "guidance": "Do not turn fixture benchmark smoke into public benchmark claims.",
            "status": "stale",
            "support_grade": "source_supported",
            "source_refs": [{"source_ref": "doc:benchmark-map", "path": "docs/evidence/benchmark-evidence-map.md"}],
            "counter_evidence_ref_count": 0,
            "path_provenance": "complete",
            "invalidators": ["superseding_current_claim"],
        },
        {
            "clause_id": "clause_issue_closeout_convention",
            "kind": "review_convention",
            "guidance": "Close issues only when the implemented slice actually retires the stated blocker.",
            "status": "challenged",
            "support_grade": "source_supported",
            "source_refs": [{"source_ref": "issue:#248", "path": "issues/248"}],
            "counter_evidence_ref_count": 1,
            "path_provenance": "complete",
            "invalidators": ["newer_project_planning_rule"],
        },
        {
            "clause_id": "clause_ordered_do_not_repeat_route",
            "kind": "route_correction",
            "guidance": "A rejected route needs ordered path provenance before it becomes a durable warning.",
            "support_grade": "source_supported",
            "source_refs": [{"source_ref": "pathlet:gappy-route", "path": "docs/research/agency-from-cognitive-map.md", "line": 95}],
            "independent_trail_count": 1,
            "support_types": ["pathlet"],
            "path_provenance": "gappy",
            "review_state": "needs_review",
        },
    ]


def project_workflow_public_safe_source_rows() -> list[dict[str, Any]]:
    """Return public-safe source rows for the first project/workflow AIppo.

    This is still a narrow bundled working contract, not a general AIppo
    marketplace. Keeping a named runtime helper avoids making callers depend on
    the fixture function while preserving the same source-supported boundary.
    """

    return _fixture_source_rows()


def build_project_workflow_public_safe_contract() -> dict[str, Any]:
    contracts = build_aippo_working_contracts(project_workflow_public_safe_source_rows())
    return select_aippo_working_contract(contracts)


def _fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "self_note_candidate_without_source",
            "candidate_source": "agent_self_notes",
            "ripened": False,
            "result_status": "needs_review",
            "truth_authority": "candidate_only",
        },
        {
            "case_id": "dream_candidate_backstage",
            "candidate_source": "dream_subconscious",
            "ripened": False,
            "result_status": "backstage_candidate",
            "truth_authority": "candidate_only",
            "foreground_eligible": False,
            "source_support_passed": False,
        },
        {
            "case_id": "dream_candidate_ripened_with_source",
            "candidate_source": "dream_subconscious",
            "ripened": True,
            "result_status": "ripe",
            "truth_authority": "source_supported",
            "foreground_eligible": True,
            "source_support_passed": True,
            "repeated_wrong_route_prevented": True,
        },
        {
            "case_id": "cognitive_route_to_source_support",
            "candidate_source": "cognitive_map",
            "navigation_signal_used": "cognitive_map",
            "ripened": True,
            "result_status": "ripe",
            "truth_authority": "source_supported",
        },
    ]


def _dream_candidate_readout(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dream_cases = [
        case for case in cases if case.get("candidate_source") == "dream_subconscious"
    ]
    dream_only_foreground_leak_count = sum(
        1
        for case in dream_cases
        if case.get("truth_authority") != "source_supported"
        and bool(case.get("foreground_eligible"))
    )
    return {
        "kind": "aippo_dream_candidate_ripening_readout",
        "authority": "dream_synthesized_candidate_not_fact",
        "metrics": {
            "dream_candidate_nominated_count": len(dream_cases),
            "dream_candidate_ripened_with_source_count": sum(
                1
                for case in dream_cases
                if case.get("ripened") and case.get("truth_authority") == "source_supported"
            ),
            "dream_only_foreground_leak_count": dream_only_foreground_leak_count,
            "repeated_wrong_route_prevented_count": sum(
                1 for case in dream_cases if case.get("repeated_wrong_route_prevented")
            ),
        },
        "boundary": {
            "dream_may_nominate_candidates": True,
            "dream_only_candidates_stay_backstage": True,
            "source_support_required_before_ripening": True,
            "ripened_candidate_still_requires_reopen_before_claim": True,
        },
    }


def build_aippo_working_contract_fixture_report() -> dict[str, Any]:
    contracts = build_aippo_working_contracts(_fixture_source_rows())
    contract = select_aippo_working_contract(contracts)
    activation = activation_packet_from_working_contract(contract, task="benchmark reporting issue closeout")
    usefulness_metrics = usefulness.usefulness_metrics(contract, activation)
    generic_activation = {
        "kind": "aippocampus_aippo_activation_packet",
        "schema_version": SCHEMA_VERSION,
        "aippo_id": AIPPO_ID,
        "output_mode": "working_contract",
        "display_hint": "Scope slice, verify, reopen before claims.",
        "use_guidance": [],
        "active_clause_ids": [],
        "claim_permission": "working_contract_allowed_no_fact_claim",
        "next_action": "use_hint",
    }
    generic_usefulness = usefulness.usefulness_metrics(contract, generic_activation)
    deepen = deepen_aippo_working_contract(contract)
    explain = explain_aippo_working_contract(contract)
    cases = _fixture_cases()
    dream_readout = _dream_candidate_readout(cases)
    red_lines = {
        "source_backed_claim_without_reopen": 0,
        "stale_clause_activated_as_current": sum(
            1
            for clause in contract["clauses"]
            if clause["lifecycle"]["status"] == "stale"
            and clause["clause_id"] in activation["active_clause_ids"]
        ),
        "candidate_only_signal_promoted_without_source": sum(
            1 for case in cases if case["truth_authority"] == "candidate_only" and case["ripened"]
        ),
        "self_note_promoted_without_source": sum(
            1
            for case in cases
            if case["candidate_source"] == "agent_self_notes" and case["truth_authority"] != "source_supported" and case["ripened"]
        ),
        "dream_candidate_promoted_without_source": sum(
            1
            for case in cases
            if case["candidate_source"] == "dream_subconscious" and case["truth_authority"] != "source_supported" and case["ripened"]
        ),
        "cognitive_route_used_as_truth": sum(
            1
            for case in cases
            if case["candidate_source"] == "cognitive_map" and case.get("truth_authority") == "cognitive_map"
        ),
        "gappy_pathlet_promoted_without_review": sum(
            1
            for clause in contract["clauses"]
            if clause["support"].get("path_provenance") == "gappy"
            and clause["clause_id"] in activation["active_clause_ids"]
        ),
        "masked_or_private_source_in_activation_packet": int(
            "PRIVATE_SOURCE_SENTINEL" in json.dumps(activation, ensure_ascii=False)
        ),
    }
    continuity_metrics = usefulness.continuity_usefulness_for_activation(activation, red_lines)
    manifest_hash = _stable_hash(contract)
    changed_source_rows = [
        dict(row, invalidators=["newer_benchmark_policy"])
        if row.get("clause_id") == "clause_benchmark_default_claim"
        else row
        for row in _fixture_source_rows()
    ]
    changed_contract = build_aippo_working_contracts(changed_source_rows)[0]
    active_clause_count = len(_active_clauses(contract["clauses"]))
    return {
        "kind": "aippocampus_aippo_working_contract_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values())
        and usefulness_metrics["usefulness_gate_ok"],
        "contract_package": contract,
        "activation_packet": activation,
        "deepen_surface": deepen,
        "explain_surface": explain,
        "fixture_cases": cases,
        "dream_candidate_readout": dream_readout,
        "foreground_packet_budget_bytes": FOREGROUND_PACKET_BYTE_BUDGET,
        "metrics": {
            "aippo_extraction_success_count": len(contracts),
            "aippo_activation_success_rate": 1.0 if activation["active_clause_count"] else 0.0,
            "usable_working_contract_count": activation["active_clause_count"],
            "foreground_packet_bytes": _json_bytes(activation),
            "source_coverage_count": deepen["source_support_ledger"]["source_ref_count"],
            "working_contract_used_without_unnecessary_reopen_count": activation["active_clause_count"],
            "available_active_clause_count": active_clause_count,
            "suppressed_clause_count": len(contract["clauses"]) - active_clause_count,
            "active_clause_information_density": usefulness_metrics[
                "active_clause_information_density"
            ],
            "generic_safety_posture_only_count": usefulness_metrics[
                "generic_safety_posture_only_count"
            ],
            "stable_workflow_search_avoided_count": usefulness_metrics[
                "stable_workflow_search_avoided_count"
            ],
            "aippo_next_action_delta_count": usefulness_metrics["aippo_next_action_delta_count"],
            "stale_clause_suppressed_count": usefulness_metrics["stale_clause_suppressed_count"],
            "low_risk_guidance_allowed_without_reopen_count": usefulness_metrics[
                "low_risk_guidance_allowed_without_reopen_count"
            ],
            "source_backed_claim_without_reopen": 0,
            "stale_as_current_count": red_lines["stale_clause_activated_as_current"],
            "stable_rebuild_hash_changed_count": int(manifest_hash != _stable_hash(build_aippo_working_contracts(_fixture_source_rows())[0])),
        },
        "continuity_usefulness": continuity_metrics,
        "usefulness_gate": {
            "safety_gate_ok": all(value == 0 for value in red_lines.values()),
            "usefulness_gate_ok": usefulness_metrics["usefulness_gate_ok"]
            and continuity_metrics["usefulness_gate_ok"],
            "quality_gate_ok": all(value == 0 for value in red_lines.values())
            and usefulness_metrics["usefulness_gate_ok"]
            and continuity_metrics["quality_gate_ok"],
        },
        "negative_fixtures": {
            "generic_safety_posture_only": {
                "activation_packet": generic_activation,
                "usefulness_gate_ok": generic_usefulness["usefulness_gate_ok"],
                "generic_safety_posture_only_count": generic_usefulness[
                    "generic_safety_posture_only_count"
                ],
            }
        },
        "stability": {
            "stable_manifest_hash": manifest_hash,
            "rebuild_manifest_hash": _stable_hash(build_aippo_working_contracts(_fixture_source_rows())[0]),
            "changed_clause_ids": [
                old["clause_id"]
                for old, new in zip(contract["clauses"], changed_contract["clauses"], strict=True)
                if _stable_hash(old) != _stable_hash(new)
            ],
        },
        "red_lines": red_lines,
        "cannot_claim": [
            "aippo_marketplace_readiness",
            "private_ficus_handling",
            "broad_automatic_skill_acquisition",
            "claim_ready_facts_without_source_reopen",
        ],
    }
